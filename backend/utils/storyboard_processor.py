"""
解说分镜渲染：按镜头裁剪原片并拼接
"""

import logging
import uuid
from pathlib import Path
from typing import Any, List, Optional

from .montage_processor import MontageProcessor
from .montage_transitions import resolve_output_size
from .thumbnail_generator import ThumbnailGenerator

logger = logging.getLogger(__name__)


class StoryboardProcessor:
    @staticmethod
    def render_shots(
        source_video: Path,
        shots: List[dict[str, Any]],
        output_path: Path,
        aspect_ratio: Optional[str] = "9:16",
        with_narration: bool = False,
    ) -> float:
        if not source_video.is_file():
            raise RuntimeError(f"源视频不存在: {source_video}")
        if not shots:
            raise RuntimeError("分镜列表为空")

        width, height = resolve_output_size(aspect_ratio)
        temp_dir = output_path.parent / f"_storyboard_tmp_{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        segment_paths: List[Path] = []
        total_duration = 0.0

        try:
            sorted_shots = sorted(shots, key=lambda s: int(s.get("index") or 0))
            for i, shot in enumerate(sorted_shots):
                start = float(shot.get("start_time") or 0)
                end = float(shot.get("end_time") or 0)
                if end <= start:
                    continue
                seg_path = temp_dir / f"shot_{i:03d}.mp4"
                MontageProcessor.trim_clip(
                    source_video,
                    seg_path,
                    in_offset=start,
                    out_offset=end,
                    width=width,
                    height=height,
                )
                if with_narration:
                    narration = str(shot.get("narration") or "").strip()
                    if narration:
                        overlay_path = temp_dir / f"shot_{i:03d}_narr.mp4"
                        MontageProcessor.burn_narration_overlay(
                            seg_path,
                            overlay_path,
                            narration,
                            width,
                            height,
                        )
                        segment_paths.append(overlay_path)
                    else:
                        segment_paths.append(seg_path)
                else:
                    segment_paths.append(seg_path)
                total_duration += end - start

            if not segment_paths:
                raise RuntimeError("没有有效的分镜片段")

            output_path.parent.mkdir(parents=True, exist_ok=True)
            MontageProcessor.concat_clips(segment_paths, output_path)
            return total_duration
        finally:
            import shutil

            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def generate_shot_thumbnails(
        source_video: Path,
        shots: List[dict[str, Any]],
        thumb_dir: Path,
    ) -> List[dict[str, Any]]:
        thumb_dir.mkdir(parents=True, exist_ok=True)
        generator = ThumbnailGenerator()
        updated: List[dict[str, Any]] = []

        for shot in sorted(shots, key=lambda s: int(s.get("index") or 0)):
            item = dict(shot)
            start = float(item.get("start_time") or 0)
            end = float(item.get("end_time") or start + 1)
            offset = start + max(0.1, (end - start) * 0.15)
            shot_id = str(item.get("id") or uuid.uuid4())
            thumb_path = thumb_dir / f"{shot_id}.jpg"
            if generator.generate_thumbnail(source_video, thumb_path, time_offset=offset):
                item["thumbnail_path"] = str(thumb_path)
            updated.append(item)
        return updated

    @staticmethod
    def generate_cover(output_video: Path, cover_path: Path) -> Optional[str]:
        generator = ThumbnailGenerator()
        if generator.generate_thumbnail(output_video, cover_path, time_offset=1.0):
            return str(cover_path)
        return None
