"""
AI 解说分镜生成服务
"""

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..core.path_utils import get_project_raw_directory
from ..core.shared_config import (
    PROMPT_FILES,
    SPEECH_RECOGNITION_METHOD,
    SPEECH_RECOGNITION_MODEL,
)
from ..models.project import Project
from ..models.storyboard import Storyboard, StoryboardStatus
from ..repositories.storyboard_repository import StoryboardRepository
from ..schemas.storyboard import StoryboardAIGenerateRequest
from ..utils.llm_client import LLMClient
from ..utils.montage_processor import MontageProcessor
from ..utils.storyboard_processor import StoryboardProcessor
from ..utils.subtitle_processor import SubtitleProcessor
from .storyboard_service import StoryboardService

logger = logging.getLogger(__name__)

NARRATION_STYLE_LABELS = {
    "colloquial": "口语化解说（撰写文字，非配音）",
    "punchy": "快节奏短句，信息密度高",
    "suspense": "悬念抓人，多用提问与反转",
    "documentary": "客观叙述，语气平静清晰",
    "minimal": "轻量补充，不重复原声对白",
}

LEGACY_VOICE_STYLE = {
    "mandarin": "colloquial",
    "original": "minimal",
}


def normalize_voice_style(value: Optional[str]) -> str:
    raw = value or "colloquial"
    mapped = LEGACY_VOICE_STYLE.get(raw, raw)
    return mapped if mapped in NARRATION_STYLE_LABELS else "colloquial"


class StoryboardAIService:
    @staticmethod
    def _clamp_narration(text: str, max_chars: int) -> str:
        cleaned = " ".join((text or "").replace("\n", " ").split()).strip()
        if not cleaned or max_chars <= 0:
            return cleaned
        return cleaned[:max_chars]

    def __init__(self, db: Session):
        self.db = db
        self.repository = StoryboardRepository(db)
        self.storyboard_service = StoryboardService(db)
        self.llm_client = LLMClient()
        self.subtitle_processor = SubtitleProcessor()

    def _call_llm(self, prompt: str, model_name: Optional[str] = None) -> str:
        return self.llm_client.llm_manager.call_with_model(model_name, prompt)

    def _auto_generate_subtitle(
        self, video_path: Path, project_id: str, project: Project
    ) -> Optional[Path]:
        raw_srt = get_project_raw_directory(project_id) / "input.srt"
        if raw_srt.exists() and raw_srt.stat().st_size > 0:
            return raw_srt

        from ..utils.speech_recognizer import generate_subtitle_for_video

        method = (SPEECH_RECOGNITION_METHOD or "faster_whisper").strip().lower()
        model = SPEECH_RECOGNITION_MODEL or "base"
        logger.info("解说分镜：未找到字幕，开始自动语音识别 (%s)...", method)
        try:
            result = generate_subtitle_for_video(
                video_path,
                output_path=raw_srt,
                method=method,
                model=model,
            )
            if not result:
                return None
            srt_path = Path(result)
            if not srt_path.is_file() or srt_path.stat().st_size == 0:
                return None
            if srt_path.resolve() != raw_srt.resolve():
                shutil.copy2(srt_path, raw_srt)
            project.subtitle_path = str(raw_srt)
            self.db.commit()
            logger.info("解说分镜：ASR 字幕已生成 %s", raw_srt)
            return raw_srt
        except Exception as e:
            logger.error("解说分镜 ASR 失败: %s", e)
            return None

    def _resolve_subtitles(
        self,
        project_id: str,
        project: Project,
        video_path: Path,
        scene_align: bool,
        subtitle_align: bool,
    ) -> Tuple[Optional[Path], List[Dict]]:
        _, subtitle_path = self.storyboard_service.resolve_media_paths(project_id, project)
        segments: List[Dict] = []
        if subtitle_path and subtitle_path.exists() and subtitle_path.stat().st_size > 0:
            segments = self.subtitle_processor.parse_srt_to_word_level(subtitle_path)

        if not segments and (scene_align or subtitle_align):
            generated = self._auto_generate_subtitle(video_path, project_id, project)
            if generated:
                subtitle_path = generated
                segments = self.subtitle_processor.parse_srt_to_word_level(generated)

        if not segments and (scene_align or subtitle_align):
            raise ValueError(
                "未能获取字幕：请上传 SRT 文件，或关闭「场景对齐/字幕对齐」后重试"
            )
        return subtitle_path, segments

    def generate(self, data: StoryboardAIGenerateRequest) -> Storyboard:
        project = self.db.query(Project).filter(Project.id == data.project_id).first()
        if not project:
            raise ValueError("项目不存在")

        video_path, subtitle_path = self.storyboard_service.resolve_media_paths(data.project_id, project)
        if not video_path:
            raise ValueError("未找到项目源视频，请先上传或处理项目")

        video_duration = MontageProcessor.probe_duration(video_path)
        subtitle_path, subtitle_segments = self._resolve_subtitles(
            data.project_id,
            project,
            video_path,
            data.scene_align,
            data.subtitle_align,
        )

        config = {
            "duration_ratio": data.duration_ratio,
            "scene_align": data.scene_align,
            "subtitle_align": data.subtitle_align,
            "golden_opening": data.golden_opening,
            "aspect_ratio": data.aspect_ratio,
            "custom_prompt": data.custom_prompt,
            "user_custom_prompt": (data.user_custom_prompt or "").strip() or None,
            "max_shots": data.max_shots,
            "narration_max_chars": data.narration_max_chars,
            "model_name": data.model_name,
            "voice_style": normalize_voice_style(data.voice_style),
            "source_duration": round(video_duration, 2),
        }

        storyboard = self.repository.create(
            project_id=data.project_id,
            name=data.name or "解说分镜",
            status=StoryboardStatus.GENERATING,
            config=config,
            shots=[],
            source_video_path=str(video_path),
            subtitle_path=str(subtitle_path) if subtitle_path else None,
            storyboard_metadata={"source": "ai"},
        )

        try:
            plan = self._generate_plan_with_llm(
                data, video_duration, subtitle_segments, config
            )
            shots = self._build_shots(
                plan,
                video_duration,
                subtitle_segments,
                data.scene_align,
                data.max_shots,
                data.narration_max_chars,
            )
            if len(shots) < 2:
                raise ValueError("AI 未能生成足够有效的分镜镜头")

            thumb_dir = (
                get_project_raw_directory(data.project_id).parent
                / "output"
                / "storyboards"
                / str(storyboard.id)
                / "thumbnails"
            )
            shots = StoryboardProcessor.generate_shot_thumbnails(video_path, shots, thumb_dir)

            target_duration = sum(
                float(s["end_time"]) - float(s["start_time"]) for s in shots
            )
            updated = self.repository.update(
                str(storyboard.id),
                name=plan.get("name") or data.name or "解说分镜",
                description=plan.get("description"),
                status=StoryboardStatus.READY,
                shots=shots,
                total_duration=max(1, int(round(target_duration))),
                error_message=None,
            )
            result = updated or storyboard

            if data.auto_render:
                self.storyboard_service.queue_render(str(result.id))

            return result
        except Exception as e:
            logger.error("AI 分镜生成失败: %s", e)
            self.repository.update(
                str(storyboard.id),
                status=StoryboardStatus.FAILED,
                error_message=str(e),
            )
            raise

    def _generate_plan_with_llm(
        self,
        data: StoryboardAIGenerateRequest,
        video_duration: float,
        subtitle_segments: List[Dict],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        with open(PROMPT_FILES["storyboard"], "r", encoding="utf-8") as f:
            system_prompt = f.read()

        target_duration = video_duration * data.duration_ratio
        lines = [
            f"\n原视频时长：{video_duration:.1f} 秒",
            f"目标成片时长：约 {target_duration:.1f} 秒（duration_ratio={data.duration_ratio}）",
            f"最多镜头数：{data.max_shots}",
            f"单镜旁白字数上限：{data.narration_max_chars} 字",
            f"场景对齐：{'是' if data.scene_align else '否'}",
            f"黄金开头：{'是' if data.golden_opening else '否'}",
            f"输出比例：{data.aspect_ratio}",
            f"旁白文风：{NARRATION_STYLE_LABELS[normalize_voice_style(data.voice_style)]}",
        ]
        if data.custom_prompt:
            lines.append(f"用户额外要求：{data.custom_prompt.strip()}")

        if subtitle_segments:
            lines.append("\n字幕段落（时间单位：秒）：")
            for seg in subtitle_segments[:120]:
                text = (seg.get("text") or "").replace("\n", " ").strip()
                if not text:
                    continue
                lines.append(
                    f"- [{seg.get('startTime', 0):.2f} ~ {seg.get('endTime', 0):.2f}] {text[:100]}"
                )
        else:
            lines.append("\n（无字幕，请按常见短视频解说节奏自行划分时间段）")

        full_prompt = system_prompt + "\n".join(lines)

        try:
            response = self._call_llm(full_prompt, data.model_name)
            parsed = self.llm_client.parse_json_response(response)
            if isinstance(parsed, dict) and parsed.get("shots"):
                return parsed
        except Exception as e:
            logger.error("LLM 分镜调用失败: %s", e)

        return self._fallback_plan(
            subtitle_segments,
            video_duration,
            data.duration_ratio,
            data.max_shots,
            data.narration_max_chars,
        )

    def _fallback_plan(
        self,
        subtitle_segments: List[Dict],
        video_duration: float,
        duration_ratio: float,
        max_shots: int,
        narration_max_chars: int,
    ) -> Dict[str, Any]:
        target = video_duration * duration_ratio
        shots: List[Dict[str, Any]] = []
        if subtitle_segments:
            for seg in subtitle_segments:
                start = float(seg.get("startTime") or 0)
                end = float(seg.get("endTime") or start + 1)
                text = (seg.get("text") or "").strip()
                if end <= start or not text:
                    continue
                dur = end - start
                if dur > 8:
                    mid = start + dur / 2
                    shots.append(
                        {
                            "index": len(shots) + 1,
                            "start_time": round(start, 2),
                            "end_time": round(mid, 2),
                            "narration": self._clamp_narration(text, narration_max_chars),
                            "subtitle_ref": text[:80],
                        }
                    )
                    shots.append(
                        {
                            "index": len(shots) + 1,
                            "start_time": round(mid, 2),
                            "end_time": round(end, 2),
                            "narration": self._clamp_narration(
                                text[narration_max_chars : narration_max_chars * 2] or text,
                                narration_max_chars,
                            ),
                            "subtitle_ref": text[:80],
                        }
                    )
                else:
                    shots.append(
                        {
                            "index": len(shots) + 1,
                            "start_time": round(start, 2),
                            "end_time": round(end, 2),
                            "narration": self._clamp_narration(text, narration_max_chars),
                            "subtitle_ref": text[:80],
                        }
                    )
                total = sum(s["end_time"] - s["start_time"] for s in shots)
                if total >= target * 0.9 or len(shots) >= max_shots:
                    break
        else:
            step = max(3.0, target / min(max_shots, 12))
            t = 0.0
            idx = 1
            while t < video_duration and len(shots) < max_shots:
                end = min(t + step, video_duration)
                if end - t < 1:
                    break
                shots.append(
                    {
                        "index": idx,
                        "start_time": round(t, 2),
                        "end_time": round(end, 2),
                        "narration": self._clamp_narration(f"第{idx}段精彩画面", narration_max_chars),
                        "subtitle_ref": None,
                    }
                )
                t = end
                idx += 1

        return {
            "name": "解说分镜",
            "description": "基于字幕自动划分的分镜方案",
            "shots": shots[:max_shots],
        }

    def _build_shots(
        self,
        plan: Dict[str, Any],
        video_duration: float,
        subtitle_segments: List[Dict],
        scene_align: bool,
        max_shots: int,
        narration_max_chars: int,
    ) -> List[Dict[str, Any]]:
        raw_shots = plan.get("shots") or []
        validated: List[Dict[str, Any]] = []

        for raw in raw_shots:
            if len(validated) >= max_shots:
                break
            if not isinstance(raw, dict):
                continue
            start = max(0.0, float(raw.get("start_time") or 0))
            end = float(raw.get("end_time") or 0)
            if end <= start:
                continue
            start = min(start, video_duration - 0.5)
            end = min(end, video_duration)
            if end <= start:
                continue

            if scene_align and subtitle_segments:
                start, end = self._align_to_subtitles(start, end, subtitle_segments)

            narration = self._clamp_narration(
                str(raw.get("narration") or "") or str(raw.get("subtitle_ref") or "精彩画面"),
                narration_max_chars,
            )
            if not narration:
                narration = self._clamp_narration("精彩画面", narration_max_chars)

            validated.append(
                {
                    "id": f"shot-{uuid.uuid4()}",
                    "index": len(validated) + 1,
                    "start_time": round(start, 2),
                    "end_time": round(end, 2),
                    "narration": narration,
                    "subtitle_ref": raw.get("subtitle_ref"),
                    "thumbnail_path": None,
                }
            )

        return validated

    def _align_to_subtitles(
        self,
        start: float,
        end: float,
        subtitle_segments: List[Dict],
    ) -> tuple[float, float]:
        """将起止时间吸附到最近的字幕段边界。"""
        if not subtitle_segments:
            return start, end

        boundaries: List[float] = []
        for seg in subtitle_segments:
            boundaries.append(float(seg.get("startTime") or 0))
            boundaries.append(float(seg.get("endTime") or 0))
        boundaries = sorted(set(boundaries))

        def snap(value: float) -> float:
            if not boundaries:
                return value
            return min(boundaries, key=lambda b: abs(b - value))

        aligned_start = snap(start)
        aligned_end = snap(end)
        if aligned_end <= aligned_start:
            aligned_end = min(aligned_start + max(1.0, end - start), boundaries[-1] if boundaries else end)
        return aligned_start, aligned_end

    def extract_narrations(self, storyboard_id: str):
        from ..models.storyboard import StoryboardStatus

        storyboard = self.repository.get_by_id(storyboard_id)
        if not storyboard:
            raise ValueError("分镜不存在")
        shots = list(storyboard.shots or [])
        if not shots:
            raise ValueError("分镜表为空")

        subtitle_path = Path(storyboard.subtitle_path) if storyboard.subtitle_path else None
        if not subtitle_path or not subtitle_path.exists():
            project = self.db.query(Project).filter(Project.id == storyboard.project_id).first()
            _, subtitle_path = self.storyboard_service.resolve_media_paths(
                str(storyboard.project_id), project
            )
        if not subtitle_path or not subtitle_path.exists():
            raise ValueError("未找到字幕文件，请先导入字幕")

        segments = self.subtitle_processor.parse_srt_to_word_level(subtitle_path)
        max_chars = int((storyboard.config or {}).get("narration_max_chars") or 10)
        updated_shots = []
        for shot in sorted(shots, key=lambda s: int(s.get("index") or 0)):
            item = dict(shot)
            start = float(item.get("start_time") or 0)
            end = float(item.get("end_time") or start)
            texts = []
            for seg in segments:
                seg_start = float(seg.get("startTime") or 0)
                seg_end = float(seg.get("endTime") or 0)
                if seg_end > start and seg_start < end:
                    text = (seg.get("text") or "").strip()
                    if text:
                        texts.append(text)
            if texts:
                item["narration"] = self._clamp_narration(" ".join(texts), max_chars)
                item["subtitle_ref"] = " ".join(texts)[:200]
            updated_shots.append(item)

        return self.repository.update(
            storyboard_id,
            shots=updated_shots,
            status=StoryboardStatus.READY,
        )

    def batch_translate(self, storyboard_id: str, target_language: str, replace: bool = True):
        from ..models.storyboard import StoryboardStatus

        storyboard = self.repository.get_by_id(storyboard_id)
        if not storyboard:
            raise ValueError("分镜不存在")
        shots = list(storyboard.shots or [])
        if not shots:
            raise ValueError("分镜表为空")

        lang_label = {"en": "英文", "ja": "日文", "ko": "韩文"}.get(target_language, target_language)
        max_chars = int((storyboard.config or {}).get("narration_max_chars") or 10)
        items = [{"index": s.get("index"), "narration": s.get("narration", "")} for s in shots]
        prompt = (
            f"请将以下旁白文案批量翻译为{lang_label}，保持口语化、适合短视频朗读。"
            f"每项 narration 不超过 {max_chars} 字。"
            f"严格输出 JSON 数组，每项包含 index 与 narration 字段：\n"
            + json.dumps(items, ensure_ascii=False)
        )
        model_name = (storyboard.config or {}).get("model_name")
        response = self._call_llm(prompt, model_name)
        parsed = self.llm_client.parse_json_response(response)
        if not isinstance(parsed, list):
            raise ValueError("翻译结果格式错误")

        trans_map = {
            int(item.get("index")): str(item.get("narration") or "")
            for item in parsed
            if isinstance(item, dict) and item.get("index") is not None
        }
        updated = []
        for shot in shots:
            item = dict(shot)
            idx = int(item.get("index") or 0)
            if idx in trans_map and trans_map[idx].strip():
                translated = self._clamp_narration(trans_map[idx].strip(), max_chars)
                if replace:
                    item["narration"] = translated
                else:
                    item["narration"] = self._clamp_narration(
                        f"{item.get('narration', '')} / {translated}",
                        max_chars,
                    )
            updated.append(item)

        return self.repository.update(
            storyboard_id,
            shots=updated,
            status=StoryboardStatus.READY,
        )
