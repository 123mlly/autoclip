"""
AI 混剪编排服务
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..core.shared_config import PROMPT_FILES
from ..models.clip import Clip
from ..models.montage import Montage, MontageStatus
from ..models.project import Project, ProjectStatus
from ..repositories.montage_repository import MontageRepository
from ..schemas.montage import MontageAIGenerateRequest, MontageResponse
from ..utils.llm_client import LLMClient
from ..utils.montage_transitions import normalize_transition
from .montage_service import MontageService

logger = logging.getLogger(__name__)


class MontageAIService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = MontageRepository(db)
        self.montage_service = MontageService(db)
        self.llm_client = LLMClient()

    def generate_montage(self, data: MontageAIGenerateRequest) -> Montage:
        project = self.db.query(Project).filter(Project.id == data.project_id).first()
        if not project:
            raise ValueError("项目不存在")

        candidates = self._collect_candidates(data.project_id, data.include_other_projects)
        if len(candidates) < 2:
            raise ValueError("可用切片不足，至少需要 2 个切片才能生成混剪")

        plan = self._generate_plan_with_llm(data, candidates)
        timeline = self._build_timeline(plan, candidates, data, allow_fallback=True)

        montage = self.repository.create(
            project_id=data.project_id,
            name=plan.get("name") or "AI 混剪",
            description=plan.get("description"),
            status=MontageStatus.DRAFT,
            timeline=timeline,
            montage_metadata={
                "source": "ai",
                "prompt": data.prompt,
                "aspect_ratio": timeline.get("output", {}).get("aspect_ratio"),
            },
        )

        if data.auto_render:
            self.montage_service.queue_render(str(montage.id))

        return montage

    def _collect_candidates(
        self,
        project_id: str,
        include_other_projects: bool,
        limit_per_project: int = 50,
    ) -> Dict[str, Dict[str, Any]]:
        """返回 key=`project_id:clip_id` 的候选切片索引。"""
        candidates: Dict[str, Dict[str, Any]] = {}

        current = self.db.query(Project).filter(Project.id == project_id).first()
        if not current:
            return candidates

        current_clips = (
            self.db.query(Clip)
            .filter(Clip.project_id == project_id)
            .order_by(desc(Clip.score))
            .limit(limit_per_project)
            .all()
        )
        for clip in current_clips:
            key = f"{project_id}:{clip.id}"
            candidates[key] = self._clip_payload(clip, current)

        if include_other_projects:
            other_projects = (
                self.db.query(Project)
                .filter(Project.id != project_id, Project.status == ProjectStatus.COMPLETED)
                .order_by(Project.updated_at.desc())
                .limit(10)
                .all()
            )
            for project in other_projects:
                clips = (
                    self.db.query(Clip)
                    .filter(Clip.project_id == project.id)
                    .order_by(desc(Clip.score))
                    .limit(limit_per_project)
                    .all()
                )
                for clip in clips:
                    key = f"{project.id}:{clip.id}"
                    candidates[key] = self._clip_payload(clip, project)

        return candidates

    def _clip_payload(self, clip: Clip, project: Project) -> Dict[str, Any]:
        duration = int(clip.duration or max(0, (clip.end_time or 0) - (clip.start_time or 0)))
        return {
            "clip_id": str(clip.id),
            "project_id": str(project.id),
            "project_name": str(project.name),
            "title": str(clip.title or "未命名切片"),
            "summary": str(clip.recommendation_reason or clip.description or ""),
            "duration": duration,
            "score": float(clip.score or 0),
        }

    def _generate_plan_with_llm(
        self,
        data: MontageAIGenerateRequest,
        candidates: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        prompt_path = PROMPT_FILES["montage"]
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()

        aspect_ratio = "16:9" if data.aspect_ratio == "16:9" else "9:16"
        clip_lines: List[str] = []
        sorted_candidates = sorted(
            candidates.values(),
            key=lambda item: (item["score"], item["duration"]),
            reverse=True,
        )
        for index, clip in enumerate(sorted_candidates, 1):
            clip_lines.append(
                f"{index}. clip_id={clip['clip_id']}, project_id={clip['project_id']}, "
                f"项目={clip['project_name']}, 标题={clip['title']}, "
                f"时长={clip['duration']}s, 评分={clip['score']:.2f}, "
                f"摘要={clip['summary'][:120]}"
            )

        user_block = (
            f"\n\n用户需求：{data.prompt.strip()}\n"
            f"目标总时长：约 {data.target_duration} 秒\n"
            f"最多片段数：{data.max_segments}\n"
            f"输出比例：{aspect_ratio}\n"
            f"允许跨项目选片：{'是' if data.include_other_projects else '否（仅当前项目）'}\n\n"
            f"候选切片列表（共 {len(sorted_candidates)} 条）：\n"
            + "\n".join(clip_lines)
        )
        full_prompt = system_prompt + user_block

        try:
            response = self.llm_client.call_with_retry(full_prompt)
            parsed = self.llm_client.parse_json_response(response)
            if isinstance(parsed, dict) and parsed.get("segments"):
                return parsed
            logger.warning("LLM 混剪返回格式异常，使用兜底方案")
        except Exception as e:
            logger.error("AI 混剪编排失败，使用兜底方案: %s", e)

        return self._fallback_plan(data, sorted_candidates)

    def _fallback_plan(
        self,
        data: MontageAIGenerateRequest,
        sorted_candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """按评分选取片段，凑近目标时长。"""
        segments: List[Dict[str, Any]] = []
        total = 0.0
        target = float(data.target_duration)

        for index, clip in enumerate(sorted_candidates):
            if len(segments) >= data.max_segments:
                break
            duration = float(clip["duration"] or 0)
            if duration <= 0:
                continue
            if segments and total + duration > target * 1.2:
                continue
            segments.append(
                {
                    "clip_id": clip["clip_id"],
                    "project_id": clip["project_id"],
                    "in_offset": 0,
                    "out_offset": None,
                    "transition": "fade" if index > 0 else "none",
                    "transition_duration": 0.5,
                }
            )
            total += duration
            if total >= target * 0.8 and len(segments) >= 3:
                break

        if len(segments) < 2:
            for clip in sorted_candidates[: min(data.max_segments, 5)]:
                if any(s["clip_id"] == clip["clip_id"] for s in segments):
                    continue
                segments.append(
                    {
                        "clip_id": clip["clip_id"],
                        "project_id": clip["project_id"],
                        "in_offset": 0,
                        "out_offset": None,
                        "transition": "fade" if segments else "none",
                        "transition_duration": 0.5,
                    }
                )
                if len(segments) >= 2:
                    break

        aspect_ratio = "16:9" if data.aspect_ratio == "16:9" else "9:16"
        return {
            "name": "AI 混剪",
            "description": data.prompt.strip()[:200],
            "aspect_ratio": aspect_ratio,
            "segments": segments,
        }

    def _build_timeline(
        self,
        plan: Dict[str, Any],
        candidates: Dict[str, Dict[str, Any]],
        data: MontageAIGenerateRequest,
        allow_fallback: bool = False,
    ) -> Dict[str, Any]:
        raw_segments = plan.get("segments") or []
        validated: List[Dict[str, Any]] = []

        for index, raw in enumerate(raw_segments):
            if len(validated) >= data.max_segments:
                break
            if not isinstance(raw, dict):
                continue

            clip_id = str(raw.get("clip_id") or "").strip()
            if not clip_id:
                continue

            project_id = str(raw.get("project_id") or data.project_id).strip()
            key = f"{project_id}:{clip_id}"
            if key not in candidates:
                alt_key = next(
                    (k for k, v in candidates.items() if v["clip_id"] == clip_id),
                    None,
                )
                if not alt_key:
                    continue
                key = alt_key
                project_id = candidates[key]["project_id"]

            clip = candidates[key]
            clip_duration = float(clip["duration"] or 0)
            if clip_duration <= 0:
                continue

            in_offset = max(0.0, float(raw.get("in_offset") or 0))
            out_raw = raw.get("out_offset")
            out_offset: Optional[float] = None
            if out_raw is not None:
                out_offset = float(out_raw)
                if out_offset <= in_offset:
                    out_offset = None
                else:
                    out_offset = min(out_offset, clip_duration)

            transition = normalize_transition(raw.get("transition") if index > 0 else "none")
            transition_duration = float(raw.get("transition_duration") or 0.5)
            transition_duration = max(0.1, min(3.0, transition_duration))

            validated.append(
                {
                    "id": f"seg-{uuid.uuid4()}",
                    "clip_id": clip_id,
                    "project_id": project_id,
                    "in_offset": round(in_offset, 2),
                    "out_offset": round(out_offset, 2) if out_offset is not None else None,
                    "transition": transition,
                    "transition_duration": round(transition_duration, 2),
                }
            )

        if len(validated) < 2:
            if allow_fallback:
                fallback = self._fallback_plan(data, list(candidates.values()))
                return self._build_timeline(fallback, candidates, data, allow_fallback=False)
            raise ValueError("AI 未能生成有效的时间轴，请调整需求后重试")

        aspect_ratio = plan.get("aspect_ratio") or data.aspect_ratio
        if aspect_ratio not in {"9:16", "16:9"}:
            aspect_ratio = "9:16" if data.aspect_ratio != "16:9" else "16:9"

        return {
            "segments": validated,
            "audio": {"bgm_volume": 0.25, "keep_original": True},
            "output": {"aspect_ratio": aspect_ratio},
        }

    def to_response(self, montage: Montage) -> MontageResponse:
        return self.montage_service._to_response(montage)
