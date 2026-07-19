"""
解说分镜 API
"""

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.base import PaginationParams
from ...schemas.storyboard import (
    StoryboardAIGenerateRequest,
    StoryboardBatchReplaceRequest,
    StoryboardBatchTranslateRequest,
    StoryboardExportClipResponse,
    StoryboardCreate,
    StoryboardListResponse,
    StoryboardProjectListResponse,
    StoryboardResponse,
    StoryboardUpdate,
    StoryboardVideoSourceListResponse,
    StoryboardVideoUploadResponse,
)
from ...services.project_service import ProjectService
from ...services.storyboard_ai_service import StoryboardAIService
from ...services.storyboard_service import StoryboardService, is_allowed_storyboard_video

logger = logging.getLogger(__name__)
router = APIRouter()


def get_storyboard_service(db: Session = Depends(get_db)) -> StoryboardService:
    return StoryboardService(db)


def get_storyboard_ai_service(db: Session = Depends(get_db)) -> StoryboardAIService:
    return StoryboardAIService(db)


def get_project_service(db: Session = Depends(get_db)) -> ProjectService:
    return ProjectService(db)


def _ensure_project(project_service: ProjectService, project_id: str) -> None:
    if not project_service.get(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")


@router.post("/", response_model=StoryboardResponse)
async def create_storyboard(
    data: StoryboardCreate,
    service: StoryboardService = Depends(get_storyboard_service),
    project_service: ProjectService = Depends(get_project_service),
):
    _ensure_project(project_service, data.project_id)
    try:
        storyboard = service.create_storyboard(data)
        return service._to_response(storyboard)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ai-generate", response_model=StoryboardResponse)
async def ai_generate_storyboard(
    data: StoryboardAIGenerateRequest,
    ai_service: StoryboardAIService = Depends(get_storyboard_ai_service),
    project_service: ProjectService = Depends(get_project_service),
):
    _ensure_project(project_service, data.project_id)
    try:
        storyboard = ai_service.generate(data)
        return ai_service.storyboard_service._to_response(storyboard)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("AI 分镜生成失败: %s", e)
        raise HTTPException(status_code=500, detail=f"AI 分镜生成失败: {str(e)}")


@router.post("/setup-project", response_model=StoryboardVideoUploadResponse)
async def setup_storyboard_project(
    video_files: List[UploadFile] = File(...),
    srt_file: Optional[UploadFile] = File(None),
    project_name: str = Form(...),
    project_service: ProjectService = Depends(get_project_service),
    storyboard_service: StoryboardService = Depends(get_storyboard_service),
):
    """上传视频/字幕供解说分镜使用（不启动完整切片流水线）。支持多集 MP4 按顺序合并。"""
    if not video_files:
        raise HTTPException(status_code=400, detail="请上传至少一个视频文件")

    for upload in video_files:
        if not is_allowed_storyboard_video(upload.filename):
            raise HTTPException(status_code=400, detail="请上传有效视频文件")

    if srt_file and not srt_file.filename.lower().endswith(".srt"):
        raise HTTPException(status_code=400, detail="字幕请使用 .srt 格式")

    try:
        video_payloads = []
        for upload in video_files:
            content = await upload.read()
            video_payloads.append((upload.filename or "video.mp4", content))

        srt_payload = None
        if srt_file:
            srt_payload = (srt_file.filename or "input.srt", await srt_file.read())

        result = storyboard_service.create_storyboard_project(
            project_service,
            project_name,
            video_payloads,
            srt_payload,
        )
        return StoryboardVideoUploadResponse(
            project_id=result["project_id"],
            source_count=result["source_count"],
            items=result["items"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("解说分镜项目创建失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/subtitle")
async def upload_storyboard_subtitle(
    project_id: str,
    srt_file: UploadFile = File(...),
    project_service: ProjectService = Depends(get_project_service),
    db: Session = Depends(get_db),
):
    """为 AI 混剪项目补传字幕文件。"""
    from ...core.path_utils import get_project_raw_directory
    from ...models.project import Project

    _ensure_project(project_service, project_id)
    if not srt_file.filename or not srt_file.filename.lower().endswith(".srt"):
        raise HTTPException(status_code=400, detail="字幕请使用 .srt 格式")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    raw_dir = get_project_raw_directory(project_id)
    srt_path = raw_dir / "input.srt"
    with open(srt_path, "wb") as f:
        f.write(await srt_file.read())
    project.subtitle_path = str(srt_path)
    db.commit()

    return {
        "project_id": project_id,
        "subtitle_path": str(srt_path),
    }


@router.get("/projects/{project_id}/sources", response_model=StoryboardVideoSourceListResponse)
async def list_storyboard_video_sources(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    storyboard_service: StoryboardService = Depends(get_storyboard_service),
):
    _ensure_project(project_service, project_id)
    try:
        return storyboard_service.list_project_video_sources(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/videos", response_model=StoryboardVideoUploadResponse)
async def append_storyboard_videos(
    project_id: str,
    video_files: List[UploadFile] = File(...),
    project_service: ProjectService = Depends(get_project_service),
    storyboard_service: StoryboardService = Depends(get_storyboard_service),
):
    """向已有混剪项目追加视频，按上传顺序合并。"""
    _ensure_project(project_service, project_id)
    if not video_files:
        raise HTTPException(status_code=400, detail="请上传至少一个视频文件")
    for upload in video_files:
        if not is_allowed_storyboard_video(upload.filename):
            raise HTTPException(status_code=400, detail="请上传有效视频文件")
    try:
        payloads = []
        for upload in video_files:
            payloads.append((upload.filename or "video.mp4", await upload.read()))
        return storyboard_service.append_project_videos(project_id, payloads)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("追加混剪视频失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}/sources/{source_id}", response_model=StoryboardVideoSourceListResponse)
async def delete_storyboard_video_source(
    project_id: str,
    source_id: str,
    project_service: ProjectService = Depends(get_project_service),
    storyboard_service: StoryboardService = Depends(get_storyboard_service),
):
    _ensure_project(project_service, project_id)
    try:
        return storyboard_service.remove_project_video_source(project_id, source_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects", response_model=StoryboardProjectListResponse)
async def list_storyboard_projects(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    service: StoryboardService = Depends(get_storyboard_service),
):
    """列出 AI 混剪专用项目（含最近分镜摘要）。"""
    pagination = PaginationParams(page=page, size=size)
    return service.list_storyboard_projects(pagination)


@router.get("/", response_model=StoryboardListResponse)
async def list_storyboards(
    project_id: str = Query(..., description="项目 ID"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    service: StoryboardService = Depends(get_storyboard_service),
    project_service: ProjectService = Depends(get_project_service),
):
    _ensure_project(project_service, project_id)
    pagination = PaginationParams(page=page, size=size)
    return service.list_by_project(project_id, pagination)


@router.get("/{storyboard_id}", response_model=StoryboardResponse)
async def get_storyboard(
    storyboard_id: str,
    service: StoryboardService = Depends(get_storyboard_service),
):
    storyboard = service.get_storyboard(storyboard_id)
    if not storyboard:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return service._to_response(storyboard)


@router.put("/{storyboard_id}", response_model=StoryboardResponse)
async def update_storyboard(
    storyboard_id: str,
    data: StoryboardUpdate,
    service: StoryboardService = Depends(get_storyboard_service),
):
    storyboard = service.update_storyboard(storyboard_id, data)
    if not storyboard:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return service._to_response(storyboard)


@router.delete("/{storyboard_id}")
async def delete_storyboard(
    storyboard_id: str,
    service: StoryboardService = Depends(get_storyboard_service),
):
    if not service.delete_storyboard(storyboard_id):
        raise HTTPException(status_code=404, detail="分镜不存在")
    return {"success": True, "message": "分镜已删除"}


@router.post("/{storyboard_id}/render", response_model=StoryboardResponse)
async def render_storyboard(
    storyboard_id: str,
    sync: bool = Query(False, description="同步渲染"),
    with_narration: bool = Query(False, description="烧录旁白字幕"),
    service: StoryboardService = Depends(get_storyboard_service),
):
    try:
        if sync:
            storyboard = service.render_storyboard(storyboard_id, with_narration=with_narration)
        else:
            storyboard = service.queue_render(storyboard_id, with_narration=with_narration)
        return service._to_response(storyboard)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("分镜渲染失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{storyboard_id}/export-clip", response_model=StoryboardExportClipResponse)
async def prepare_storyboard_upload(
    storyboard_id: str,
    service: StoryboardService = Depends(get_storyboard_service),
):
    """将分镜导出视频同步为投稿切片。"""
    try:
        return service.ensure_export_clip(storyboard_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("准备分镜投稿失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{storyboard_id}/extract-narrations", response_model=StoryboardResponse)
async def extract_storyboard_narrations(
    storyboard_id: str,
    ai_service: StoryboardAIService = Depends(get_storyboard_ai_service),
):
    try:
        storyboard = ai_service.extract_narrations(storyboard_id)
        return ai_service.storyboard_service._to_response(storyboard)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{storyboard_id}/batch-translate", response_model=StoryboardResponse)
async def batch_translate_storyboard(
    storyboard_id: str,
    data: StoryboardBatchTranslateRequest,
    ai_service: StoryboardAIService = Depends(get_storyboard_ai_service),
):
    try:
        storyboard = ai_service.batch_translate(storyboard_id, data.target_language, data.replace)
        return ai_service.storyboard_service._to_response(storyboard)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("批量翻译失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{storyboard_id}/batch-replace", response_model=StoryboardResponse)
async def batch_replace_storyboard_text(
    storyboard_id: str,
    data: StoryboardBatchReplaceRequest,
    service: StoryboardService = Depends(get_storyboard_service),
):
    try:
        storyboard = service.batch_replace_narration(storyboard_id, data.find_text, data.replace_text)
        return service._to_response(storyboard)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
