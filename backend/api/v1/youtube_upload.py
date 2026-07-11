"""
YouTube 投稿 API
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...services.youtube_upload_service import YouTubeAccountService, YouTubeUploadService
from ...services.youtube_uploader import build_authorization_url, oauth_configured
from ...tasks.upload import upload_youtube_clip_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/youtube-upload", tags=["YouTube投稿"])


class YouTubeAccountResponse(BaseModel):
    id: int
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    email: Optional[str] = None
    status: str
    is_default: bool = False
    upload_count: int = 0

    class Config:
        from_attributes = True


class RefreshTokenImportRequest(BaseModel):
    refresh_token: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    nickname: Optional[str] = None


class OAuthCodeRequest(BaseModel):
    code: str
    nickname: Optional[str] = None


class YouTubeUploadRequest(BaseModel):
    clip_ids: List[str]
    account_id: int
    title: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    category_id: str = "22"
    privacy_status: str = "private"


def get_account_service(db: Session = Depends(get_db)) -> YouTubeAccountService:
    return YouTubeAccountService(db)


def get_upload_service(db: Session = Depends(get_db)) -> YouTubeUploadService:
    return YouTubeUploadService(db)


@router.get("/config")
async def get_youtube_upload_config():
    """检查 YouTube OAuth 是否已配置。"""
    return {
        "configured": oauth_configured(),
        "message": (
            "已配置 Google OAuth"
            if oauth_configured()
            else "请在 .env 中设置 YOUTUBE_CLIENT_ID 与 YOUTUBE_CLIENT_SECRET"
        ),
    }


@router.get("/oauth/start")
async def start_oauth(nickname: Optional[str] = None):
    """获取 Google OAuth 授权链接。"""
    try:
        state = nickname or "autoclip"
        auth_url, state = build_authorization_url(state=state)
        return {"auth_url": auth_url, "state": state}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/oauth/callback")
async def oauth_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    account_service: YouTubeAccountService = Depends(get_account_service),
):
    """OAuth 回调：换取 token 并保存账号，然后跳转前端设置页。"""
    frontend_redirect = "http://localhost:3000/settings?youtube=1"
    if error:
        return RedirectResponse(f"{frontend_redirect}&error={error}")
    if not code:
        raise HTTPException(status_code=400, detail="缺少授权码 code")
    try:
        nickname = state if state and state != "autoclip" else None
        account = account_service.create_from_oauth_code(code, nickname=nickname)
        return RedirectResponse(
            f"{frontend_redirect}&success=1&channel={account.channel_title or ''}"
        )
    except Exception as e:
        logger.exception("YouTube OAuth 回调失败")
        from urllib.parse import quote
        return RedirectResponse(f"{frontend_redirect}&error={quote(str(e))}")


@router.post("/oauth/code")
async def import_oauth_code(
    request: OAuthCodeRequest,
    account_service: YouTubeAccountService = Depends(get_account_service),
):
    """手动提交授权码（适用于无法自动回调的场景）。"""
    try:
        account = account_service.create_from_oauth_code(request.code, nickname=request.nickname)
        return YouTubeAccountResponse.from_orm(account)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/accounts/import-refresh-token")
async def import_refresh_token(
    request: RefreshTokenImportRequest,
    account_service: YouTubeAccountService = Depends(get_account_service),
):
    """通过 refresh_token 导入账号。"""
    try:
        account = account_service.create_from_refresh_token(
            refresh_token=request.refresh_token,
            client_id=request.client_id,
            client_secret=request.client_secret,
            nickname=request.nickname,
        )
        return YouTubeAccountResponse.from_orm(account)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/accounts")
async def list_accounts(account_service: YouTubeAccountService = Depends(get_account_service)):
    accounts = account_service.list_accounts()
    return [YouTubeAccountResponse.from_orm(a) for a in accounts]


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int,
    account_service: YouTubeAccountService = Depends(get_account_service),
):
    if account_service.delete_account(account_id):
        return {"message": "账号已删除"}
    raise HTTPException(status_code=404, detail="账号不存在")


@router.post("/projects/{project_id}/upload")
async def create_youtube_upload_task(
    project_id: UUID,
    request: YouTubeUploadRequest,
    upload_service: YouTubeUploadService = Depends(get_upload_service),
):
    """创建 YouTube 投稿任务。"""
    try:
        if not request.clip_ids:
            raise HTTPException(status_code=400, detail="请至少选择一个切片")
        if not request.title.strip():
            raise HTTPException(status_code=400, detail="请填写标题")

        record = upload_service.create_upload_record(
            project_id,
            clip_ids=request.clip_ids,
            account_id=request.account_id,
            title=request.title.strip(),
            description=request.description or "",
            tags=request.tags or [],
            category_id=request.category_id,
            privacy_status=request.privacy_status,
        )
        upload_youtube_clip_task.delay(str(record.id), request.clip_ids[0])
        return {
            "message": "YouTube 投稿任务创建成功",
            "record_id": str(record.id),
            "clip_count": len(request.clip_ids),
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("创建 YouTube 投稿任务失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/records")
async def list_records(
    project_id: Optional[UUID] = None,
    upload_service: YouTubeUploadService = Depends(get_upload_service),
):
    return upload_service.list_records(project_id)


@router.get("/records/{record_id}")
async def get_record(
    record_id: int,
    upload_service: YouTubeUploadService = Depends(get_upload_service),
):
    record = upload_service.get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="投稿记录不存在")
    return {
        "id": record.id,
        "status": record.status,
        "video_id": record.video_id,
        "video_url": record.video_url,
        "error_message": record.error_message,
        "progress": record.progress or 0,
        "title": record.title,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.post("/records/{record_id}/retry")
async def retry_record(
    record_id: int,
    upload_service: YouTubeUploadService = Depends(get_upload_service),
):
    try:
        upload_service.retry(record_id)
        return {"message": "重试已启动"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/records/{record_id}/cancel")
async def cancel_record(
    record_id: int,
    upload_service: YouTubeUploadService = Depends(get_upload_service),
):
    try:
        upload_service.cancel(record_id)
        return {"message": "任务已取消"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/records/{record_id}")
async def delete_record(
    record_id: int,
    upload_service: YouTubeUploadService = Depends(get_upload_service),
):
    try:
        upload_service.delete(record_id)
        return {"message": "任务已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/categories")
async def list_categories():
    """常用 YouTube 视频分类。"""
    return [
        {"id": "22", "name": "People & Blogs"},
        {"id": "24", "name": "Entertainment"},
        {"id": "23", "name": "Comedy"},
        {"id": "10", "name": "Music"},
        {"id": "20", "name": "Gaming"},
        {"id": "27", "name": "Education"},
        {"id": "28", "name": "Science & Technology"},
        {"id": "1", "name": "Film & Animation"},
        {"id": "26", "name": "Howto & Style"},
        {"id": "17", "name": "Sports"},
        {"id": "15", "name": "Pets & Animals"},
        {"id": "19", "name": "Travel & Events"},
        {"id": "25", "name": "News & Politics"},
        {"id": "2", "name": "Autos & Vehicles"},
    ]
