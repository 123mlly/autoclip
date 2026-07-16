"""
YouTube 投稿服务
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ..models.youtube import YouTubeAccount, YouTubeUploadRecord
from ..utils.crypto import encrypt_data, decrypt_data
from .youtube_uploader import (
    YouTubeUploader,
    exchange_code_for_credentials,
    oauth_configured,
)

logger = logging.getLogger(__name__)


class YouTubeAccountService:
    def __init__(self, db: Session):
        self.db = db

    def list_accounts(self) -> List[YouTubeAccount]:
        return self.db.query(YouTubeAccount).order_by(YouTubeAccount.created_at.desc()).all()

    def get_account(self, account_id) -> Optional[YouTubeAccount]:
        try:
            return self.db.query(YouTubeAccount).filter(YouTubeAccount.id == int(account_id)).first()
        except (TypeError, ValueError):
            return None

    def create_from_credentials(self, credentials: Dict[str, Any], nickname: Optional[str] = None) -> YouTubeAccount:
        if not credentials.get("refresh_token"):
            raise ValueError("授权结果缺少 refresh_token，请使用 prompt=consent 重新授权")

        creds_json = json.dumps(credentials)
        uploader = YouTubeUploader(creds_json)
        info = uploader.get_channel_info()
        if not info or not info.get("channel_id"):
            raise ValueError(uploader.error_message or "无法获取 YouTube 频道信息，请确认账号已开通频道")

        # 刷新后的 token 一并保存
        try:
            creds_json = uploader.export_credentials_json()
        except Exception:
            pass

        existing = (
            self.db.query(YouTubeAccount)
            .filter(YouTubeAccount.channel_id == info["channel_id"])
            .first()
        )
        if existing:
            existing.credentials = encrypt_data(creds_json)
            existing.channel_title = nickname or info.get("channel_title") or existing.channel_title
            existing.status = "active"
            existing.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing

        account = YouTubeAccount(
            channel_id=info["channel_id"],
            channel_title=nickname or info.get("channel_title") or "YouTube Channel",
            email=info.get("email"),
            credentials=encrypt_data(creds_json),
            status="active",
            is_default=self.db.query(YouTubeAccount).count() == 0,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    def create_from_oauth_code(
        self, code: str, nickname: Optional[str] = None, state: Optional[str] = None
    ) -> YouTubeAccount:
        if not oauth_configured():
            raise ValueError("未配置 YouTube OAuth，请在设置页 YouTube管理 填写 Client ID / Secret")
        credentials = exchange_code_for_credentials(code, state=state)
        resolved_nickname = nickname or credentials.pop("_oauth_nickname", None)
        return self.create_from_credentials(credentials, nickname=resolved_nickname)

    def create_from_refresh_token(
        self,
        refresh_token: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        nickname: Optional[str] = None,
    ) -> YouTubeAccount:
        from .youtube_uploader import get_youtube_oauth_config

        cfg = get_youtube_oauth_config()
        credentials = {
            "refresh_token": refresh_token.strip(),
            "token": None,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": (client_id or cfg["client_id"] or "").strip(),
            "client_secret": (client_secret or cfg["client_secret"] or "").strip(),
            "scopes": [
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.readonly",
            ],
        }
        if not credentials["client_id"] or not credentials["client_secret"]:
            raise ValueError("请提供 client_id/client_secret，或在设置页 / .env 中配置 OAuth")
        return self.create_from_credentials(credentials, nickname=nickname)

    def delete_account(self, account_id) -> bool:
        account = self.get_account(account_id)
        if not account:
            return False
        records = (
            self.db.query(YouTubeUploadRecord)
            .filter(YouTubeUploadRecord.account_id == account.id)
            .all()
        )
        for r in records:
            self.db.delete(r)
        self.db.delete(account)
        self.db.commit()
        return True


class YouTubeUploadService:
    def __init__(self, db: Session):
        self.db = db
        self.account_service = YouTubeAccountService(db)

    def create_upload_record(
        self,
        project_id: UUID,
        *,
        clip_ids: List[str],
        account_id,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        category_id: str = "22",
        privacy_status: str = "private",
    ) -> YouTubeUploadRecord:
        account = self.account_service.get_account(account_id)
        if not account:
            raise ValueError("YouTube 账号不存在，请先完成授权")

        record = YouTubeUploadRecord(
            project_id=project_id,
            account_id=int(account.id),
            clip_id=",".join(clip_ids),
            title=title,
            description=description,
            tags=json.dumps(tags or []),
            category_id=str(category_id or "22"),
            privacy_status=privacy_status or "private",
            status="pending",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_record(self, record_id) -> Optional[YouTubeUploadRecord]:
        try:
            return (
                self.db.query(YouTubeUploadRecord)
                .filter(YouTubeUploadRecord.id == int(record_id))
                .first()
            )
        except (TypeError, ValueError):
            return None

    def list_records(self, project_id: Optional[UUID] = None) -> List[Dict[str, Any]]:
        query = self.db.query(YouTubeUploadRecord)
        if project_id:
            query = query.filter(YouTubeUploadRecord.project_id == project_id)
        records = query.order_by(YouTubeUploadRecord.created_at.desc()).all()
        result = []
        for r in records:
            account = self.account_service.get_account(r.account_id)
            result.append({
                "id": r.id,
                "project_id": r.project_id,
                "account_id": r.account_id,
                "clip_id": r.clip_id,
                "title": r.title,
                "description": r.description,
                "tags": r.tags,
                "category_id": r.category_id,
                "privacy_status": r.privacy_status,
                "video_path": r.video_path,
                "video_id": r.video_id,
                "video_url": r.video_url,
                "status": r.status,
                "error_message": r.error_message,
                "progress": r.progress or 0,
                "file_size": r.file_size,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "account_title": account.channel_title if account else None,
                "channel_id": account.channel_id if account else None,
            })
        return result

    def update_status(self, record_id, status: str, error_message: Optional[str] = None) -> bool:
        record = self.get_record(record_id)
        if not record:
            return False
        record.status = status
        if error_message is not None:
            record.error_message = error_message
        record.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    def cancel(self, record_id) -> bool:
        record = self.get_record(record_id)
        if not record:
            raise ValueError("投稿记录不存在")
        if record.status not in ("pending", "processing"):
            raise ValueError("只有待处理或处理中的任务可以取消")
        record.status = "cancelled"
        record.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    def delete(self, record_id) -> bool:
        record = self.get_record(record_id)
        if not record:
            raise ValueError("投稿记录不存在")
        if record.status in ("pending", "processing"):
            raise ValueError("进行中的任务不能删除，请先取消")
        self.db.delete(record)
        self.db.commit()
        return True

    def retry(self, record_id) -> bool:
        record = self.get_record(record_id)
        if not record:
            raise ValueError("投稿记录不存在")
        if record.status != "failed":
            raise ValueError("只有失败的任务可以重试")
        record.status = "pending"
        record.error_message = None
        record.updated_at = datetime.utcnow()
        self.db.commit()

        clip_ids = [c.strip() for c in (record.clip_id or "").split(",") if c.strip()]
        if not clip_ids:
            raise ValueError("记录中没有切片 ID")
        from ..tasks.upload import upload_youtube_clip_task
        upload_youtube_clip_task.delay(str(record.id), clip_ids[0])
        return True

    def upload_clip_sync(self, record_id: int, video_path: str) -> bool:
        record = self.get_record(record_id)
        if not record:
            logger.error("投稿记录不存在: %s", record_id)
            return False

        record.status = "processing"
        record.video_path = video_path
        record.updated_at = datetime.utcnow()
        self.db.commit()

        account = self.account_service.get_account(record.account_id)
        if not account:
            record.status = "failed"
            record.error_message = "YouTube 账号不存在"
            self.db.commit()
            return False

        try:
            creds_json = decrypt_data(account.credentials)
        except Exception as e:
            record.status = "failed"
            record.error_message = f"凭证解密失败: {e}"
            self.db.commit()
            return False

        tags = []
        if record.tags:
            try:
                tags = json.loads(record.tags)
            except Exception:
                tags = [t.strip() for t in record.tags.split(",") if t.strip()]

        uploader = YouTubeUploader(creds_json)
        success = uploader.upload_video(
            video_path,
            {
                "title": record.title,
                "description": record.description or record.title,
                "tags": tags,
                "category_id": record.category_id or "22",
                "privacy_status": record.privacy_status or "private",
            },
        )

        # 回写刷新后的 token
        try:
            account.credentials = encrypt_data(uploader.export_credentials_json())
        except Exception:
            pass

        if success:
            record.status = "completed"
            record.video_id = uploader.video_id
            record.video_url = uploader.video_url
            record.progress = 100
            record.error_message = None
            account.upload_count = (account.upload_count or 0) + 1
            account.last_used_at = datetime.utcnow()
        else:
            record.status = "failed"
            record.error_message = uploader.error_message or "上传失败"

        record.updated_at = datetime.utcnow()
        self.db.commit()
        return success
