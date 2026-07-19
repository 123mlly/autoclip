"""
混剪服务
"""

import logging
from pathlib import Path
from typing import Any, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..core.path_utils import get_project_directory, resolve_clip_video_file
from ..models.clip import Clip
from ..models.montage import Montage, MontageStatus
from ..models.project import Project, ProjectStatus
from ..repositories.montage_repository import MontageRepository
from ..schemas.base import PaginationParams, PaginationResponse
from ..schemas.montage import (
    MontageClipItem,
    MontageClipSourceGroup,
    MontageClipSourcesResponse,
    MontageCreate,
    MontageListResponse,
    MontageResponse,
    MontageUpdate,
)
from ..utils.montage_processor import MontageProcessor
from ..utils.thumbnail_generator import ThumbnailGenerator

logger = logging.getLogger(__name__)


class MontageService:
    def __init__(self, db: Session):
        self.repository = MontageRepository(db)
        self.db = db

    def _to_response(self, montage: Montage) -> MontageResponse:
        timeline = montage.timeline or {}
        segments = timeline.get("segments") or []
        status = montage.status.value if hasattr(montage.status, "value") else str(montage.status)
        return MontageResponse(
            id=str(montage.id),
            project_id=str(montage.project_id),
            name=montage.name,
            description=montage.description,
            status=status,
            timeline=timeline,
            total_duration=montage.total_duration,
            export_path=montage.export_path,
            thumbnail_path=montage.thumbnail_path,
            error_message=montage.error_message,
            created_at=montage.created_at,
            updated_at=montage.updated_at,
            segment_count=len(segments),
        )

    def create_montage(self, data: MontageCreate) -> Montage:
        timeline: dict[str, Any] = {
            "segments": [],
            "audio": {"bgm_volume": 0.25, "keep_original": True},
            "output": {"aspect_ratio": "9:16"},
        }
        if data.timeline:
            timeline = data.timeline.model_dump()

        montage = self.repository.create(
            project_id=data.project_id,
            name=data.name,
            description=data.description,
            status=MontageStatus.DRAFT,
            timeline=timeline,
            montage_metadata={"source": "manual"},
        )
        return montage

    def get_montage(self, montage_id: str) -> Optional[Montage]:
        return self.repository.get_by_id(montage_id)

    def update_montage(self, montage_id: str, data: MontageUpdate) -> Optional[Montage]:
        update_data: dict[str, Any] = {}
        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.timeline is not None:
            update_data["timeline"] = data.timeline.model_dump()
            update_data["status"] = MontageStatus.DRAFT
            update_data["error_message"] = None
        if not update_data:
            return self.get_montage(montage_id)
        return self.repository.update(montage_id, **update_data)

    def delete_montage(self, montage_id: str) -> bool:
        montage = self.get_montage(montage_id)
        if not montage:
            return False
        if montage.export_path:
            try:
                Path(montage.export_path).unlink(missing_ok=True)
            except OSError:
                pass
        return self.repository.delete(montage_id)

    def list_by_project(
        self,
        project_id: str,
        pagination: Optional[PaginationParams] = None,
    ) -> MontageListResponse:
        if pagination is None:
            pagination = PaginationParams(page=1, size=100)
        skip = (pagination.page - 1) * pagination.size
        items, total = self.repository.get_paginated_by_project(
            project_id, skip=skip, limit=pagination.size
        )
        pages = (total + pagination.size - 1) // pagination.size if pagination.size else 0
        return MontageListResponse(
            items=[self._to_response(m) for m in items],
            pagination=PaginationResponse(
                page=pagination.page,
                size=pagination.size,
                total=total,
                pages=pages,
                has_next=pagination.page < pages,
                has_prev=pagination.page > 1,
            ),
        )

    def _resolve_clip_path(self, project_id: str, clip: Clip) -> Optional[Path]:
        return resolve_clip_video_file(
            project_id=project_id,
            clip_id=str(clip.id),
            video_path=clip.video_path,
            title=clip.title,
        )

    def _segment_duration(self, clip: Clip, in_offset: float, out_offset: Optional[float]) -> float:
        clip_duration = float(clip.duration or max(0, (clip.end_time or 0) - (clip.start_time or 0)))
        if out_offset is not None:
            return max(0.1, out_offset - in_offset)
        return max(0.1, clip_duration - in_offset)

    def _clip_to_item(self, clip: Clip, project: Project) -> MontageClipItem:
        return MontageClipItem(
            id=str(clip.id),
            title=str(clip.title or "未命名切片"),
            duration=int(clip.duration or max(0, (clip.end_time or 0) - (clip.start_time or 0))),
            score=clip.score,
            project_id=str(project.id),
            project_name=str(project.name),
        )

    def get_clip_sources(self, project_id: str, limit_per_project: int = 50) -> MontageClipSourcesResponse:
        current = self.db.query(Project).filter(Project.id == project_id).first()
        if not current:
            raise ValueError("项目不存在")

        current_clips = (
            self.db.query(Clip)
            .filter(Clip.project_id == project_id)
            .order_by(desc(Clip.score))
            .limit(limit_per_project)
            .all()
        )
        current_group = MontageClipSourceGroup(
            project_id=str(current.id),
            project_name=str(current.name),
            clips=[self._clip_to_item(c, current) for c in current_clips],
        )

        other_projects: List[MontageClipSourceGroup] = []
        projects = (
            self.db.query(Project)
            .filter(Project.id != project_id, Project.status == ProjectStatus.COMPLETED)
            .order_by(Project.updated_at.desc())
            .limit(20)
            .all()
        )
        for project in projects:
            clips = (
                self.db.query(Clip)
                .filter(Clip.project_id == project.id)
                .order_by(desc(Clip.score))
                .limit(limit_per_project)
                .all()
            )
            if not clips:
                continue
            other_projects.append(
                MontageClipSourceGroup(
                    project_id=str(project.id),
                    project_name=str(project.name),
                    clips=[self._clip_to_item(c, project) for c in clips],
                )
            )

        return MontageClipSourcesResponse(
            current_project=current_group,
            other_projects=other_projects,
        )

    def save_bgm(self, montage_id: str, filename: str, content: bytes) -> Montage:
        montage = self.get_montage(montage_id)
        if not montage:
            raise ValueError("混剪不存在")

        suffix = Path(filename).suffix.lower() or ".mp3"
        if suffix not in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
            raise ValueError("不支持的 BGM 格式，请上传 mp3/wav/m4a/aac/ogg")

        project_id = str(montage.project_id)
        montages_dir = get_project_directory(project_id) / "output" / "montages"
        montages_dir.mkdir(parents=True, exist_ok=True)
        bgm_path = montages_dir / f"{montage_id}_bgm{suffix}"
        bgm_path.write_bytes(content)

        timeline = dict(montage.timeline or {})
        audio = dict(timeline.get("audio") or {})
        audio.update(
            {
                "bgm_path": str(bgm_path),
                "bgm_filename": filename,
                "bgm_volume": audio.get("bgm_volume", 0.25),
                "keep_original": audio.get("keep_original", True),
            }
        )
        timeline["audio"] = audio

        updated = self.repository.update(
            montage_id,
            timeline=timeline,
            status=MontageStatus.DRAFT,
        )
        return updated or montage

    def queue_render(self, montage_id: str) -> Montage:
        montage = self.get_montage(montage_id)
        if not montage:
            raise ValueError("混剪不存在")
        segments = (montage.timeline or {}).get("segments") or []
        if not segments:
            raise ValueError("时间轴为空，请先添加片段")
        if montage.status == MontageStatus.RENDERING:
            return montage

        from ..tasks.video import render_montage_task

        self.repository.update(
            montage_id,
            status=MontageStatus.RENDERING,
            error_message=None,
        )
        render_montage_task.delay(montage_id)
        updated = self.get_montage(montage_id)
        return updated or montage

    def render_montage(self, montage_id: str) -> Montage:
        montage = self.get_montage(montage_id)
        if not montage:
            raise ValueError("混剪不存在")

        timeline = montage.timeline or {}
        segments = timeline.get("segments") or []
        if not segments:
            raise ValueError("时间轴为空，请先添加片段")

        project_id = str(montage.project_id)
        self.repository.update(
            montage_id,
            status=MontageStatus.RENDERING,
            error_message=None,
        )

        try:
            clip_ids = [s.get("clip_id") for s in segments if s.get("clip_id")]
            clips = {
                str(c.id): c
                for c in self.db.query(Clip).filter(Clip.id.in_(clip_ids)).all()
            }
            if len(clips) != len(set(clip_ids)):
                missing = set(clip_ids) - set(clips.keys())
                raise ValueError(f"部分切片不存在: {', '.join(missing)}")

            clip_paths: dict[str, Path] = {}
            enriched_segments: List[dict[str, Any]] = []
            total_duration = 0.0

            for segment in segments:
                clip_id = str(segment.get("clip_id"))
                clip = clips.get(clip_id)
                if not clip:
                    raise ValueError(f"切片不存在: {clip_id}")

                segment_project_id = str(segment.get("project_id") or clip.project_id)
                if str(clip.project_id) != segment_project_id:
                    raise ValueError(f"切片项目信息不匹配: {clip_id}")

                path_key = f"{segment_project_id}:{clip_id}"
                path = self._resolve_clip_path(segment_project_id, clip)
                if not path:
                    raise ValueError(f"找不到切片视频文件: {clip_id}")

                in_offset = float(segment.get("in_offset") or 0)
                out_offset = segment.get("out_offset")
                out_val = float(out_offset) if out_offset is not None else None
                seg_duration = self._segment_duration(clip, in_offset, out_val)
                total_duration += seg_duration

                clip_paths[path_key] = path
                enriched_segments.append(
                    {
                        **segment,
                        "project_id": segment_project_id,
                        "_path_key": path_key,
                        "duration": seg_duration,
                        "in_offset": in_offset,
                        "out_offset": out_val,
                        "transition": segment.get("transition") or "none",
                        "transition_duration": float(segment.get("transition_duration") or 0.5),
                    }
                )

            project_dir = get_project_directory(project_id)
            montages_dir = project_dir / "output" / "montages"
            montages_dir.mkdir(parents=True, exist_ok=True)
            output_path = montages_dir / f"{montage_id}.mp4"

            audio_settings = (timeline.get("audio") or {}) if isinstance(timeline, dict) else {}
            output_settings = (timeline.get("output") or {}) if isinstance(timeline, dict) else {}
            MontageProcessor.render_timeline(
                enriched_segments,
                clip_paths,
                output_path,
                audio_settings=audio_settings,
                output_settings=output_settings,
            )

            thumbnail_path = None
            try:
                thumb_dir = montages_dir / "thumbnails"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                thumb_file = thumb_dir / f"{montage_id}.jpg"
                generator = ThumbnailGenerator()
                if generator.generate_thumbnail(output_path, thumb_file, time_offset=1.0):
                    thumbnail_path = str(thumb_file)
            except Exception as e:
                logger.warning("混剪缩略图生成失败: %s", e)
                thumbnail_path = None

            updated = self.repository.update(
                montage_id,
                status=MontageStatus.COMPLETED,
                export_path=str(output_path),
                thumbnail_path=thumbnail_path,
                total_duration=max(1, int(round(total_duration))),
                error_message=None,
            )
            return updated or montage
        except Exception as e:
            logger.error("混剪渲染失败: %s", e)
            self.repository.update(
                montage_id,
                status=MontageStatus.FAILED,
                error_message=str(e),
            )
            raise
