"""
混剪视频渲染：裁剪、转场拼接、BGM 混音
"""

import logging
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, List, Optional

from .montage_transitions import normalize_transition, resolve_output_size

logger = logging.getLogger(__name__)


class MontageProcessor:
    @staticmethod
    def _run_ffmpeg(cmd: List[str], cwd: Optional[Path] = None) -> None:
        logger.info("FFmpeg: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            cwd=str(cwd) if cwd else None,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "FFmpeg 执行失败")

    @staticmethod
    def probe_duration(path: Path) -> float:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if result.returncode != 0:
            raise RuntimeError(f"无法读取视频时长: {path}")
        try:
            return max(0.1, float(result.stdout.strip()))
        except ValueError as exc:
            raise RuntimeError(f"无法解析视频时长: {path}") from exc

    @staticmethod
    def _build_scale_crop_filter(width: int, height: int) -> str:
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        )

    @staticmethod
    def trim_clip(
        input_path: Path,
        output_path: Path,
        in_offset: float = 0,
        out_offset: Optional[float] = None,
        width: int = 1080,
        height: int = 1920,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration = None
        if out_offset is not None:
            duration = max(0.1, out_offset - in_offset)

        vf = MontageProcessor._build_scale_crop_filter(width, height)
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(max(0, in_offset)),
            "-i",
            str(input_path),
        ]
        if duration is not None:
            cmd.extend(["-t", str(duration)])
        cmd.extend(
            [
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        MontageProcessor._run_ffmpeg(cmd)
        if not output_path.is_file() or output_path.stat().st_size < 1024:
            raise RuntimeError(f"裁剪输出无效: {output_path}")
        return output_path

    @staticmethod
    def _wrap_narration_lines(text: str, max_chars: int = 16) -> List[str]:
        cleaned = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
        if not cleaned:
            return []

        lines: List[str] = []
        current = ""
        for ch in cleaned:
            current += ch
            if len(current) >= max_chars:
                line = current.strip()
                if line:
                    lines.append(line)
                current = ""
                continue
            if ch in "，。！？、；：,.;:!?" and len(current.strip()) >= max(4, max_chars // 2):
                line = current.strip()
                if line:
                    lines.append(line)
                current = ""
        if current.strip():
            lines.append(current.strip())
        return lines[:3]

    @staticmethod
    def _load_cjk_font(font_size: int, bold: bool = False):
        from PIL import ImageFont

        regular_candidates = [
            (Path("/System/Library/Fonts/PingFang.ttc"), 0),
            (Path("/System/Library/Fonts/Hiragino Sans GB.ttc"), 0),
            (Path("/System/Library/Fonts/STHeiti Light.ttc"), 0),
            (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), None),
            (Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"), None),
        ]
        bold_candidates = [
            (Path("/System/Library/Fonts/PingFang.ttc"), 1),
            (Path("/System/Library/Fonts/Hiragino Sans GB.ttc"), 0),
            (Path("/System/Library/Fonts/STHeiti Medium.ttc"), 0),
            (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"), None),
            (Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"), None),
        ]
        candidates = bold_candidates if bold else regular_candidates
        for font_path, index in candidates:
            if not font_path.is_file():
                continue
            try:
                if index is None:
                    return ImageFont.truetype(str(font_path), font_size)
                return ImageFont.truetype(str(font_path), font_size, index=index)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _render_narration_overlay_png(
        narration: str,
        width: int,
        height: int,
        output_png: Path,
    ) -> int:
        from PIL import Image, ImageDraw

        font_size = max(34, min(58, int(width * 0.046)))
        font = MontageProcessor._load_cjk_font(font_size, bold=True)
        max_chars = max(8, min(18, int(width / max(font_size * 0.55, 1))))
        lines = MontageProcessor._wrap_narration_lines(narration, max_chars=max_chars)
        if not lines:
            lines = [narration[: max_chars * 2]]
        text = "\n".join(lines)

        line_spacing = max(8, int(font_size * 0.24))
        stroke_width = max(3, int(font_size * 0.08))
        padding = max(10, stroke_width + 4)
        bottom_margin = max(56, int(height * 0.08))

        measure = Image.new("RGBA", (1, 1))
        measure_draw = ImageDraw.Draw(measure)
        bbox = measure_draw.multiline_textbbox(
            (0, 0),
            text,
            font=font,
            spacing=line_spacing,
            align="center",
            stroke_width=stroke_width,
        )
        text_w = int(bbox[2] - bbox[0])
        text_h = int(bbox[3] - bbox[1])

        box_w = text_w + padding * 2
        box_h = text_h + padding * 2
        text_x = padding - int(bbox[0])
        text_y = padding - int(bbox[1])

        overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.multiline_text(
            (text_x, text_y),
            text,
            font=font,
            fill=(255, 255, 255, 255),
            spacing=line_spacing,
            align="center",
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 240),
        )
        output_png.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(output_png)
        return bottom_margin

    @staticmethod
    def burn_narration_overlay(
        input_path: Path,
        output_path: Path,
        narration: str,
        width: int,
        height: int,
    ) -> Path:
        narration = (narration or "").strip()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not narration:
            shutil.copy2(input_path, output_path)
            return output_path

        work_dir = input_path.parent.resolve()
        token = uuid.uuid4().hex[:8]
        png_name = f"narr_{token}.png"
        png_path = work_dir / png_name

        try:
            bottom_margin = MontageProcessor._render_narration_overlay_png(
                narration,
                width,
                height,
                png_path,
            )
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                input_path.name,
                "-loop",
                "1",
                "-i",
                png_name,
                "-filter_complex",
                f"overlay=(W-w)/2:H-h-{bottom_margin}:shortest=1",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                output_path.name,
            ]
            MontageProcessor._run_ffmpeg(cmd, cwd=work_dir)
        finally:
            png_path.unlink(missing_ok=True)

        if not output_path.is_file() or output_path.stat().st_size < 1024:
            raise RuntimeError(f"旁白字幕输出无效: {output_path}")
        return output_path

    @staticmethod
    def concat_clips(segment_paths: List[Path], output_path: Path) -> Path:
        if not segment_paths:
            raise RuntimeError("没有可拼接的片段")
        if len(segment_paths) == 1:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(segment_paths[0], output_path)
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        concat_file = output_path.parent / f"montage_concat_{uuid.uuid4().hex[:8]}.txt"
        try:
            with open(concat_file, "w", encoding="utf-8") as f:
                for clip_path in segment_paths:
                    escaped = str(clip_path.absolute()).replace("'", "'\"'\"'")
                    f.write(f"file '{escaped}'\n")

            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            MontageProcessor._run_ffmpeg(cmd)
        finally:
            concat_file.unlink(missing_ok=True)

        if not output_path.is_file() or output_path.stat().st_size < 1024:
            raise RuntimeError("混剪输出文件无效")
        return output_path

    @staticmethod
    def _merge_two_with_transition(
        left_path: Path,
        right_path: Path,
        output_path: Path,
        transition: str,
        transition_duration: float,
    ) -> Path:
        transition = normalize_transition(transition)
        if transition == "none":
            return MontageProcessor.concat_clips([left_path, right_path], output_path)

        left_duration = MontageProcessor.probe_duration(left_path)
        td = min(transition_duration, max(0.1, left_duration - 0.05))
        offset = max(0, left_duration - td)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(left_path),
            "-i",
            str(right_path),
            "-filter_complex",
            (
                f"[0:v][1:v]xfade=transition={transition}:duration={td}:offset={offset}[vout];"
                f"[0:a][1:a]acrossfade=d={td}[aout]"
            ),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        MontageProcessor._run_ffmpeg(cmd)
        return output_path

    @staticmethod
    def concat_with_transitions(
        segment_paths: List[Path],
        segments: List[dict[str, Any]],
        output_path: Path,
    ) -> Path:
        if not segment_paths:
            raise RuntimeError("没有可拼接的片段")

        current = segment_paths[0]
        temp_dir = output_path.parent / f"_tmp_{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_files: List[Path] = []

        try:
            for index in range(1, len(segment_paths)):
                segment = segments[index] if index < len(segments) else {}
                transition = segment.get("transition") or "none"
                transition_duration = float(segment.get("transition_duration") or 0.5)
                next_path = segment_paths[index]
                merged_path = temp_dir / f"merge_{index:03d}.mp4"
                temp_files.append(merged_path)
                current = MontageProcessor._merge_two_with_transition(
                    current,
                    next_path,
                    merged_path,
                    transition=transition,
                    transition_duration=transition_duration,
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(current, output_path)
            return output_path
        finally:
            for path in temp_files:
                path.unlink(missing_ok=True)
            try:
                temp_dir.rmdir()
            except OSError:
                pass

    @staticmethod
    def mix_bgm(
        video_path: Path,
        bgm_path: Path,
        output_path: Path,
        bgm_volume: float = 0.25,
        keep_original: bool = True,
    ) -> Path:
        if not bgm_path.is_file():
            raise RuntimeError(f"BGM 文件不存在: {bgm_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        volume = max(0.0, min(1.0, bgm_volume))

        if keep_original:
            filter_complex = (
                f"[1:a]volume={volume}[bgm];"
                f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(bgm_path),
                "-filter_complex",
                filter_complex,
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(bgm_path),
                "-filter_complex",
                f"[1:a]volume={volume}[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output_path),
            ]

        MontageProcessor._run_ffmpeg(cmd)
        return output_path

    @staticmethod
    def render_timeline(
        segments: List[dict[str, Any]],
        clip_paths: dict[str, Path],
        output_path: Path,
        audio_settings: Optional[dict[str, Any]] = None,
        output_settings: Optional[dict[str, Any]] = None,
    ) -> int:
        if not segments:
            raise RuntimeError("时间轴为空，请至少添加一个片段")

        output = output_settings or {}
        width, height = resolve_output_size(output.get("aspect_ratio"))
        temp_dir = Path(tempfile.mkdtemp(prefix="montage_"))
        prepared: List[Path] = []
        total_duration = 0.0

        try:
            for index, segment in enumerate(segments):
                clip_id = segment.get("clip_id")
                path_key = segment.get("_path_key") or clip_id
                if not clip_id or path_key not in clip_paths:
                    raise RuntimeError(f"找不到切片视频: {clip_id}")

                in_offset = float(segment.get("in_offset") or 0)
                out_offset = segment.get("out_offset")
                out_val = float(out_offset) if out_offset is not None else None

                seg_path = temp_dir / f"seg_{index:03d}.mp4"
                MontageProcessor.trim_clip(
                    clip_paths[path_key],
                    seg_path,
                    in_offset=in_offset,
                    out_offset=out_val,
                    width=width,
                    height=height,
                )
                seg_duration = MontageProcessor.probe_duration(seg_path)
                prepared.append(seg_path)
                total_duration += seg_duration

            merged_temp = temp_dir / "merged.mp4"
            has_transition = any(
                normalize_transition(segments[i].get("transition")) != "none"
                for i in range(1, len(segments))
            )
            if has_transition:
                MontageProcessor.concat_with_transitions(prepared, segments, merged_temp)
            else:
                MontageProcessor.concat_clips(prepared, merged_temp)

            audio = audio_settings or {}
            bgm_path = audio.get("bgm_path")
            if bgm_path and Path(bgm_path).is_file():
                MontageProcessor.mix_bgm(
                    merged_temp,
                    Path(bgm_path),
                    output_path,
                    bgm_volume=float(audio.get("bgm_volume") or 0.25),
                    keep_original=bool(audio.get("keep_original", True)),
                )
            else:
                shutil.copy2(merged_temp, output_path)

            if has_transition and len(segments) > 1:
                fade_total = sum(
                    float(segments[i].get("transition_duration") or 0.5)
                    for i in range(1, len(segments))
                    if normalize_transition(segments[i].get("transition")) != "none"
                )
                total_duration = max(0.1, total_duration - fade_total)
        finally:
            for path in prepared:
                path.unlink(missing_ok=True)
            merged_candidate = temp_dir / "merged.mp4"
            merged_candidate.unlink(missing_ok=True)
            try:
                temp_dir.rmdir()
            except OSError:
                pass

        return max(1, int(round(total_duration)))
