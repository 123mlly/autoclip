"""
混剪 API
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.base import PaginationParams
from ...schemas.montage import (
    MontageAIGenerateRequest,
    MontageClipSourcesResponse,
    MontageCreate,
    MontageListResponse,
    MontageResponse,
    MontageUpdate,
)
from ...services.montage_ai_service import MontageAIService
from ...services.montage_service import MontageService
from ...services.project_service import ProjectService

logger = logging.getLogger(__name__)
router = APIRouter()


def get_montage_service(db: Session = Depends(get_db)) -> MontageService:
    return MontageService(db)


def get_montage_ai_service(db: Session = Depends(get_db)) -> MontageAIService:
    return MontageAIService(db)


def get_project_service(db: Session = Depends(get_db)) -> ProjectService:
    return ProjectService(db)


def _ensure_project(project_service: ProjectService, project_id: str) -> None:
    if not project_service.get(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")


@router.post("/", response_model=MontageResponse)
async def create_montage(
    data: MontageCreate,
    montage_service: MontageService = Depends(get_montage_service),
    project_service: ProjectService = Depends(get_project_service),
):
    _ensure_project(project_service, data.project_id)
    try:
        montage = montage_service.create_montage(data)
        return montage_service._to_response(montage)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=MontageListResponse)
async def list_montages(
    project_id: str = Query(..., description="项目 ID"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    montage_service: MontageService = Depends(get_montage_service),
    project_service: ProjectService = Depends(get_project_service),
):
    _ensure_project(project_service, project_id)
    pagination = PaginationParams(page=page, size=size)
    return montage_service.list_by_project(project_id, pagination)


@router.get("/transitions")
async def list_montage_transitions():
    from ...utils.montage_transitions import TRANSITION_LABELS, XFADE_TRANSITIONS

    items = [{"value": "none", "label": TRANSITION_LABELS["none"]}]
    for name in sorted(XFADE_TRANSITIONS):
        items.append({"value": name, "label": TRANSITION_LABELS.get(name, name)})
    return {"items": items}


@router.get("/clip-sources", response_model=MontageClipSourcesResponse)
async def get_montage_clip_sources(
    project_id: str = Query(..., description="当前项目 ID"),
    montage_service: MontageService = Depends(get_montage_service),
    project_service: ProjectService = Depends(get_project_service),
):
    _ensure_project(project_service, project_id)
    try:
        return montage_service.get_clip_sources(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ai-generate", response_model=MontageResponse)
async def ai_generate_montage(
    data: MontageAIGenerateRequest,
    ai_service: MontageAIService = Depends(get_montage_ai_service),
    project_service: ProjectService = Depends(get_project_service),
):
    """根据用户需求，由大模型自动编排混剪时间轴。"""
    _ensure_project(project_service, data.project_id)
    try:
        montage = ai_service.generate_montage(data)
        return ai_service.to_response(montage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("AI 混剪生成失败: %s", e)
        raise HTTPException(status_code=500, detail=f"AI 混剪生成失败: {str(e)}")


@router.get("/{montage_id}", response_model=MontageResponse)
async def get_montage(
    montage_id: str,
    montage_service: MontageService = Depends(get_montage_service),
):
    montage = montage_service.get_montage(montage_id)
    if not montage:
        raise HTTPException(status_code=404, detail="混剪不存在")
    return montage_service._to_response(montage)


@router.put("/{montage_id}", response_model=MontageResponse)
async def update_montage(
    montage_id: str,
    data: MontageUpdate,
    montage_service: MontageService = Depends(get_montage_service),
):
    montage = montage_service.update_montage(montage_id, data)
    if not montage:
        raise HTTPException(status_code=404, detail="混剪不存在")
    return montage_service._to_response(montage)


@router.delete("/{montage_id}")
async def delete_montage(
    montage_id: str,
    montage_service: MontageService = Depends(get_montage_service),
):
    if not montage_service.delete_montage(montage_id):
        raise HTTPException(status_code=404, detail="混剪不存在")
    return {"success": True, "message": "混剪已删除"}


@router.post("/{montage_id}/bgm", response_model=MontageResponse)
async def upload_montage_bgm(
    montage_id: str,
    file: UploadFile = File(...),
    montage_service: MontageService = Depends(get_montage_service),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择 BGM 文件")
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="BGM 文件为空")
        montage = montage_service.save_bgm(montage_id, file.filename, content)
        return montage_service._to_response(montage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("上传 BGM 失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{montage_id}/render", response_model=MontageResponse)
async def render_montage(
    montage_id: str,
    sync: bool = Query(False, description="同步渲染（阻塞，适合调试）"),
    montage_service: MontageService = Depends(get_montage_service),
):
    try:
        if sync:
            montage = montage_service.render_montage(montage_id)
        else:
            montage = montage_service.queue_render(montage_id)
        return montage_service._to_response(montage)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("渲染混剪失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
