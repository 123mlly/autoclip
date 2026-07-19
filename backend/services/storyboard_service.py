"""
解说分镜服务
"""

import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..core.path_utils import get_project_directory, get_project_raw_directory
from ..models.clip import Clip, ClipStatus
from ..models.project import Project, ProjectStatus
from ..models.storyboard import Storyboard, StoryboardStatus
from ..repositories.storyboard_repository import StoryboardRepository
from ..schemas.base import PaginationParams, PaginationResponse
from ..schemas.project import ProjectCreate, ProjectType
from ..schemas.storyboard import (
    StoryboardCreate,
    StoryboardListResponse,
    StoryboardProjectListResponse,
    StoryboardProjectSummary,
    StoryboardResponse,
    StoryboardStatus as StoryboardStatusSchema,
    StoryboardUpdate,
    StoryboardVideoSource,
    StoryboardVideoSourceListResponse,
    StoryboardVideoUploadResponse,
)
from ..utils.storyboard_processor import StoryboardProcessor

logger = logging.getLogger(__name__)

ALLOWED_VIDEO_EXT = (".mp4", ".avi", ".mov", ".mkv", ".webm")


def is_allowed_storyboard_video(filename: Optional[str]) -> bool:
    return bool(filename) and filename.lower().endswith(ALLOWED_VIDEO_EXT)


class StoryboardService:
    def __init__(self, db: Session):
        self.repository = StoryboardRepository(db)
        self.db = db

    def resolve_media_paths(
        self, project_id: str, project: Optional[Project] = None
    ) -> Tuple[Optional[Path], Optional[Path]]:
        if project is None:
            project = self.db.query(Project).filter(Project.id == project_id).first()
        raw_dir = get_project_raw_directory(project_id)
        video_candidates = [
            raw_dir / "input.mp4",
        ]
        if project and project.video_path:
            video_candidates.insert(0, Path(project.video_path))

        video_path = next((p for p in video_candidates if p.is_file()), None)

        subtitle_candidates = [raw_dir / "input.srt"]
        if project and project.subtitle_path:
            subtitle_candidates.insert(0, Path(project.subtitle_path))
        subtitle_path = next((p for p in subtitle_candidates if p.is_file()), None)
        return video_path, subtitle_path

    def _to_response(self, storyboard: Storyboard) -> StoryboardResponse:
        shots = storyboard.shots or []
        status = (
            storyboard.status.value
            if hasattr(storyboard.status, "value")
            else str(storyboard.status)
        )
        return StoryboardResponse(
            id=str(storyboard.id),
            project_id=str(storyboard.project_id),
            name=storyboard.name,
            description=storyboard.description,
            status=status,
            config=storyboard.config or {},
            shots=shots,
            source_video_path=storyboard.source_video_path,
            subtitle_path=storyboard.subtitle_path,
            total_duration=storyboard.total_duration,
            export_path=storyboard.export_path,
            thumbnail_path=storyboard.thumbnail_path,
            error_message=storyboard.error_message,
            created_at=storyboard.created_at,
            updated_at=storyboard.updated_at,
            shot_count=len(shots),
        )

    def create_storyboard(self, data: StoryboardCreate) -> Storyboard:
        project = self.db.query(Project).filter(Project.id == data.project_id).first()
        if not project:
            raise ValueError("项目不存在")

        video_path, subtitle_path = self.resolve_media_paths(data.project_id, project)
        config = {
            "duration_ratio": 0.5,
            "scene_align": True,
            "subtitle_align": True,
            "golden_opening": True,
            "aspect_ratio": "9:16",
        }
        if data.config:
            config.update(data.config.model_dump())

        return self.repository.create(
            project_id=data.project_id,
            name=data.name or "解说分镜",
            status=StoryboardStatus.DRAFT,
            config=config,
            shots=[],
            source_video_path=str(video_path) if video_path else None,
            subtitle_path=str(subtitle_path) if subtitle_path else None,
            storyboard_metadata={"source": "manual"},
        )

    def get_storyboard(self, storyboard_id: str) -> Optional[Storyboard]:
        return self.repository.get_by_id(storyboard_id)

    def update_storyboard(
        self, storyboard_id: str, data: StoryboardUpdate
    ) -> Optional[Storyboard]:
        update_data: dict[str, Any] = {}
        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.config is not None:
            existing = self.get_storyboard(storyboard_id)
            merged = dict((existing.config if existing else {}) or {})
            merged.update(data.config.model_dump())
            update_data["config"] = merged
        if data.shots is not None:
            update_data["shots"] = [s.model_dump() for s in data.shots]
            update_data["status"] = StoryboardStatus.READY
            update_data["error_message"] = None
            total = sum(
                float(s.end_time) - float(s.start_time) for s in data.shots
            )
            update_data["total_duration"] = max(1, int(round(total)))
        if not update_data:
            return self.get_storyboard(storyboard_id)
        return self.repository.update(storyboard_id, **update_data)

    def delete_storyboard(self, storyboard_id: str) -> bool:
        storyboard = self.get_storyboard(storyboard_id)
        if not storyboard:
            return False
        if storyboard.export_path:
            try:
                Path(storyboard.export_path).unlink(missing_ok=True)
            except OSError:
                pass
        return self.repository.delete(storyboard_id)

    def list_by_project(
        self, project_id: str, pagination: Optional[PaginationParams] = None
    ) -> StoryboardListResponse:
        if pagination is None:
            pagination = PaginationParams(page=1, size=100)
        skip = (pagination.page - 1) * pagination.size
        items, total = self.repository.get_paginated_by_project(
            project_id, skip=skip, limit=pagination.size
        )
        pages = (total + pagination.size - 1) // pagination.size if pagination.size else 0
        return StoryboardListResponse(
            items=[self._to_response(s) for s in items],
            pagination=PaginationResponse(
                page=pagination.page,
                size=pagination.size,
                total=total,
                pages=pages,
                has_next=pagination.page < pages,
                has_prev=pagination.page > 1,
            ),
        )

    def queue_render(self, storyboard_id: str, with_narration: bool = False) -> Storyboard:
        storyboard = self.get_storyboard(storyboard_id)
        if not storyboard:
            raise ValueError("分镜不存在")
        shots = storyboard.shots or []
        if not shots:
            raise ValueError("分镜表为空，请先生成或编辑镜头")
        if with_narration and not any(str(s.get("narration") or "").strip() for s in shots):
            raise ValueError("分镜表中没有旁白文案，无法导出旁白版本")
        if storyboard.status == StoryboardStatus.RENDERING:
            return storyboard

        from ..tasks.video import render_storyboard_task

        self.repository.update(
            storyboard_id,
            status=StoryboardStatus.RENDERING,
            error_message=None,
        )
        render_storyboard_task.delay(storyboard_id, with_narration=with_narration)
        return self.get_storyboard(storyboard_id) or storyboard

    def render_storyboard(self, storyboard_id: str, with_narration: bool = False) -> Storyboard:
        storyboard = self.get_storyboard(storyboard_id)
        if not storyboard:
            raise ValueError("分镜不存在")
        shots = storyboard.shots or []
        if not shots:
            raise ValueError("分镜表为空")
        if with_narration and not any(str(s.get("narration") or "").strip() for s in shots):
            raise ValueError("分镜表中没有旁白文案，无法导出旁白版本")

        project_id = str(storyboard.project_id)
        video_path = Path(storyboard.source_video_path) if storyboard.source_video_path else None
        if not video_path or not video_path.is_file():
            project = self.db.query(Project).filter(Project.id == project_id).first()
            video_path, _ = self.resolve_media_paths(project_id, project)
        if not video_path or not video_path.is_file():
            raise ValueError("找不到源视频文件")

        self.repository.update(
            storyboard_id,
            status=StoryboardStatus.RENDERING,
            error_message=None,
        )

        try:
            config = storyboard.config or {}
            aspect_ratio = config.get("aspect_ratio", "9:16")
            out_dir = get_project_directory(project_id) / "output" / "storyboards"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / (
                f"{storyboard_id}_narration.mp4" if with_narration else f"{storyboard_id}.mp4"
            )

            total_duration = StoryboardProcessor.render_shots(
                video_path,
                shots,
                output_path,
                aspect_ratio=aspect_ratio,
                with_narration=with_narration,
            )

            thumb_path = out_dir / "thumbnails" / f"{storyboard_id}.jpg"
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            cover = StoryboardProcessor.generate_cover(output_path, thumb_path)

            updated = self.repository.update(
                storyboard_id,
                status=StoryboardStatus.COMPLETED,
                export_path=str(output_path),
                thumbnail_path=cover,
                total_duration=max(1, int(round(total_duration))),
                error_message=None,
            )
            if updated:
                self.ensure_export_clip(storyboard_id, storyboard=updated)
            return updated or storyboard
        except Exception as e:
            logger.error("分镜渲染失败: %s", e)
            self.repository.update(
                storyboard_id,
                status=StoryboardStatus.FAILED,
                error_message=str(e),
            )
            raise

    def ensure_export_clip(
        self,
        storyboard_id: str,
        storyboard: Optional[Storyboard] = None,
    ) -> dict[str, str]:
        """将分镜导出视频同步为可投稿切片，供 B 站 / YouTube 上传复用。"""
        storyboard = storyboard or self.get_storyboard(storyboard_id)
        if not storyboard:
            raise ValueError("分镜不存在")
        if storyboard.status != StoryboardStatus.COMPLETED:
            raise ValueError("请先完成视频导出")
        if not storyboard.export_path:
            raise ValueError("导出文件不存在，请重新导出")

        export_path = Path(storyboard.export_path)
        if not export_path.is_file():
            raise ValueError("导出文件不存在，请重新导出")

        project_id = str(storyboard.project_id)
        clips_dir = get_project_directory(project_id) / "output" / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        config = dict(storyboard.config or {})
        clip_id = config.get("export_clip_id")
        clip = self.db.query(Clip).filter(Clip.id == clip_id).first() if clip_id else None
        duration = max(1, int(storyboard.total_duration or 1))
        title = (storyboard.name or "AI混剪成片").strip() or "AI混剪成片"

        if clip is None:
            clip = Clip(
                title=title,
                status=ClipStatus.COMPLETED,
                start_time=0,
                end_time=duration,
                duration=duration,
                project_id=project_id,
                clip_metadata={
                    "source": "storyboard",
                    "storyboard_id": storyboard_id,
                },
            )
            self.db.add(clip)
            self.db.flush()
            config["export_clip_id"] = str(clip.id)
            self.repository.update(storyboard_id, config=config)

        clip_dest = clips_dir / f"{clip.id}.mp4"
        if (
            not clip_dest.is_file()
            or export_path.stat().st_mtime > clip_dest.stat().st_mtime
        ):
            shutil.copy2(export_path, clip_dest)

        clip.title = title
        clip.duration = duration
        clip.end_time = duration
        clip.video_path = str(clip_dest)
        clip.thumbnail_path = storyboard.thumbnail_path
        clip.status = ClipStatus.COMPLETED
        metadata = dict(clip.clip_metadata or {})
        metadata.update({"source": "storyboard", "storyboard_id": storyboard_id})
        clip.clip_metadata = metadata
        self.db.commit()
        self.db.refresh(clip)
        return {"clip_id": str(clip.id), "title": clip.title}

    def batch_replace_narration(
        self, storyboard_id: str, find_text: str, replace_text: str
    ):
        storyboard = self.get_storyboard(storyboard_id)
        if not storyboard:
            raise ValueError("分镜不存在")
        shots = list(storyboard.shots or [])
        if not shots:
            raise ValueError("分镜表为空")

        updated = []
        for shot in shots:
            item = dict(shot)
            narration = str(item.get("narration") or "")
            if find_text in narration:
                item["narration"] = narration.replace(find_text, replace_text)
            updated.append(item)

        return self.repository.update(
            storyboard_id,
            shots=updated,
            status=StoryboardStatus.READY,
        )

    def list_storyboard_projects(
        self, pagination: Optional[PaginationParams] = None
    ) -> StoryboardProjectListResponse:
        from sqlalchemy import desc, func

        if pagination is None:
            pagination = PaginationParams(page=1, size=20)

        storyboard_flag = func.json_extract(Project.processing_config, "$.storyboard_only")
        query = self.db.query(Project).filter(storyboard_flag == 1)
        total = query.count()
        skip = (pagination.page - 1) * pagination.size
        projects = (
            query.order_by(desc(Project.updated_at))
            .offset(skip)
            .limit(pagination.size)
            .all()
        )

        items: List[StoryboardProjectSummary] = []
        for project in projects:
            project_id = str(project.id)
            latest = (
                self.db.query(Storyboard)
                .filter(Storyboard.project_id == project_id)
                .order_by(desc(Storyboard.updated_at))
                .first()
            )
            shots = latest.shots or [] if latest else []
            status_value = None
            if latest:
                status_value = (
                    latest.status.value
                    if hasattr(latest.status, "value")
                    else str(latest.status)
                )
            items.append(
                StoryboardProjectSummary(
                    project_id=project_id,
                    name=str(project.name),
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                    thumbnail=getattr(project, "thumbnail", None),
                    storyboard_id=str(latest.id) if latest else None,
                    storyboard_name=latest.name if latest else None,
                    storyboard_status=(
                        StoryboardStatusSchema(status_value) if status_value else None
                    ),
                    shot_count=len(shots),
                    total_duration=latest.total_duration if latest else None,
                )
            )

        pages = (total + pagination.size - 1) // pagination.size if pagination.size else 0
        return StoryboardProjectListResponse(
            items=items,
            pagination=PaginationResponse(
                page=pagination.page,
                size=pagination.size,
                total=total,
                pages=pages,
                has_next=pagination.page < pages,
                has_prev=pagination.page > 1,
            ),
        )

    def _parts_dir(self, project_id: str) -> Path:
        parts_dir = get_project_raw_directory(project_id) / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        return parts_dir

    def _parse_uploaded_at(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.utcnow()

    def _source_models(self, project: Project) -> List[dict]:
        cfg = dict(project.processing_config or {})
        sources = cfg.get("storyboard_sources") or []
        if sources:
            return sorted(sources, key=lambda item: int(item.get("order", 0)))

        project_id = str(project.id)
        parts_dir = self._parts_dir(project_id)
        parts = sorted(parts_dir.glob("part_*"))
        if not parts and project.video_path:
            legacy = Path(project.video_path)
            if legacy.is_file():
                parts = [legacy]

        rebuilt: List[dict] = []
        for idx, part in enumerate(parts):
            rebuilt.append(
                {
                    "id": part.stem.replace("part_", "") or uuid.uuid4().hex[:8],
                    "filename": part.name,
                    "original_name": part.name,
                    "size": part.stat().st_size,
                    "order": idx,
                    "uploaded_at": datetime.utcfromtimestamp(part.stat().st_mtime).isoformat(),
                }
            )
        if rebuilt:
            cfg["storyboard_sources"] = rebuilt
            project.processing_config = cfg
            self.db.commit()
        return rebuilt

    def _persist_sources(self, project: Project, sources: List[dict]) -> None:
        cfg = dict(project.processing_config or {})
        cfg["storyboard_sources"] = sources
        cfg["storyboard_only"] = True
        cfg.setdefault("download_status", "completed")
        project.processing_config = cfg

    def _to_source_response(self, raw: dict) -> StoryboardVideoSource:
        return StoryboardVideoSource(
            id=str(raw["id"]),
            filename=str(raw.get("filename") or ""),
            original_name=str(raw.get("original_name") or raw.get("filename") or ""),
            size=int(raw.get("size") or 0),
            order=int(raw.get("order") or 0),
            uploaded_at=self._parse_uploaded_at(raw.get("uploaded_at")),
        )

    def _remix_project_video(self, project_id: str, sources: List[dict]) -> None:
        from ..utils.montage_processor import MontageProcessor

        parts_dir = self._parts_dir(project_id)
        part_paths: List[Path] = []
        for item in sorted(sources, key=lambda s: int(s.get("order", 0))):
            filename = item.get("filename")
            if not filename:
                continue
            part_path = parts_dir / filename
            if not part_path.is_file():
                part_path = parts_dir / Path(str(filename)).name
            if part_path.is_file():
                part_paths.append(part_path)

        video_path = get_project_raw_directory(project_id) / "input.mp4"
        if not part_paths:
            return
        if len(part_paths) == 1:
            shutil.copy2(part_paths[0], video_path)
        else:
            MontageProcessor.concat_clips(part_paths, video_path)

    def create_storyboard_project(
        self,
        project_service: Any,
        project_name: str,
        video_payloads: List[Tuple[str, bytes]],
        srt_payload: Optional[Tuple[str, bytes]] = None,
    ) -> dict:
        project_data = ProjectCreate(
            name=project_name.strip() or "AI 混剪项目",
            description="AI 混剪专用项目",
            project_type=ProjectType.CONTENT_REVIEW,
            settings={"storyboard_only": True, "download_status": "completed"},
        )
        project = project_service.create_project(project_data)
        project_id = str(project.id)

        sources = self._write_video_payloads(project_id, [], video_payloads)
        self._remix_project_video(project_id, sources)
        video_path = get_project_raw_directory(project_id) / "input.mp4"
        project.video_path = str(video_path)

        srt_path = None
        if srt_payload:
            srt_path = get_project_raw_directory(project_id) / "input.srt"
            with open(srt_path, "wb") as f:
                f.write(srt_payload[1])
            project.subtitle_path = str(srt_path)

        self._persist_sources(project, sources)
        project.status = ProjectStatus.COMPLETED
        self.db.commit()
        self.db.refresh(project)

        return {
            "project_id": project_id,
            "name": project.name,
            "video_path": str(video_path),
            "subtitle_path": str(srt_path) if srt_path else None,
            "source_count": len(sources),
            "items": [self._to_source_response(item) for item in sources],
        }

    def _write_video_payloads(
        self,
        project_id: str,
        existing_sources: List[dict],
        video_payloads: List[Tuple[str, bytes]],
    ) -> List[dict]:
        parts_dir = self._parts_dir(project_id)
        sources = list(existing_sources)
        next_order = max([int(item.get("order", 0)) for item in sources], default=-1) + 1

        for original_name, content in video_payloads:
            source_id = uuid.uuid4().hex[:12]
            suffix = Path(original_name or "video.mp4").suffix.lower() or ".mp4"
            filename = f"part_{next_order:03d}_{source_id}{suffix}"
            part_path = parts_dir / filename
            with open(part_path, "wb") as f:
                f.write(content)
            sources.append(
                {
                    "id": source_id,
                    "filename": filename,
                    "original_name": original_name or filename,
                    "size": len(content),
                    "order": next_order,
                    "uploaded_at": datetime.utcnow().isoformat(),
                }
            )
            next_order += 1
        return sources

    def append_project_videos(
        self, project_id: str, video_payloads: List[Tuple[str, bytes]]
    ) -> StoryboardVideoUploadResponse:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("项目不存在")
        if not video_payloads:
            raise ValueError("请上传至少一个视频文件")

        sources = self._source_models(project)
        sources = self._write_video_payloads(project_id, sources, video_payloads)
        self._persist_sources(project, sources)
        self._remix_project_video(project_id, sources)
        project.video_path = str(get_project_raw_directory(project_id) / "input.mp4")
        project.status = ProjectStatus.COMPLETED
        self.db.commit()

        return StoryboardVideoUploadResponse(
            project_id=project_id,
            source_count=len(sources),
            items=[self._to_source_response(item) for item in sources],
        )

    def list_project_video_sources(self, project_id: str) -> StoryboardVideoSourceListResponse:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("项目不存在")
        sources = self._source_models(project)
        return StoryboardVideoSourceListResponse(
            project_id=project_id,
            source_count=len(sources),
            items=[self._to_source_response(item) for item in sources],
        )

    def remove_project_video_source(
        self, project_id: str, source_id: str
    ) -> StoryboardVideoSourceListResponse:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("项目不存在")

        sources = self._source_models(project)
        target = next((item for item in sources if str(item.get("id")) == source_id), None)
        if not target:
            raise ValueError("上传记录不存在")

        parts_dir = self._parts_dir(project_id)
        part_path = parts_dir / str(target.get("filename", ""))
        if part_path.is_file():
            part_path.unlink(missing_ok=True)

        sources = [item for item in sources if str(item.get("id")) != source_id]
        for idx, item in enumerate(sorted(sources, key=lambda s: int(s.get("order", 0)))):
            item["order"] = idx

        self._persist_sources(project, sources)
        if sources:
            self._remix_project_video(project_id, sources)
            project.video_path = str(get_project_raw_directory(project_id) / "input.mp4")
        else:
            merged = get_project_raw_directory(project_id) / "input.mp4"
            if merged.is_file():
                merged.unlink(missing_ok=True)
            project.video_path = None

        self.db.commit()
        return self.list_project_video_sources(project_id)
