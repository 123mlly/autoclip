"""
YouTube Data API v3 上传器
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
SCOPES = [YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE]


def get_youtube_oauth_config() -> Dict[str, str]:
    """从环境变量读取 OAuth 配置。"""
    return {
        "client_id": os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv(
            "YOUTUBE_REDIRECT_URI",
            "http://localhost:8000/api/v1/youtube-upload/oauth/callback",
        ).strip(),
    }


def oauth_configured() -> bool:
    cfg = get_youtube_oauth_config()
    return bool(cfg["client_id"] and cfg["client_secret"])


class YouTubeUploader:
    """基于 google-api-python-client 的同步上传器。"""

    def __init__(self, credentials_json: str):
        """
        credentials_json: 解密后的 credentials 字典 JSON，至少含 refresh_token，
        也可含 token/access_token、client_id、client_secret、token_uri。
        """
        self.raw = credentials_json
        self.video_id: Optional[str] = None
        self.video_url: Optional[str] = None
        self.error_message: Optional[str] = None
        self._creds = None

    def _build_credentials(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        cfg = get_youtube_oauth_config()
        data = json.loads(self.raw) if isinstance(self.raw, str) else self.raw

        refresh_token = data.get("refresh_token")
        if not refresh_token:
            raise ValueError("缺少 refresh_token，请重新授权 YouTube 账号")

        creds = Credentials(
            token=data.get("token") or data.get("access_token"),
            refresh_token=refresh_token,
            token_uri=data.get("token_uri") or "https://oauth2.googleapis.com/token",
            client_id=data.get("client_id") or cfg["client_id"],
            client_secret=data.get("client_secret") or cfg["client_secret"],
            scopes=data.get("scopes") or SCOPES,
        )

        if not creds.valid:
            if creds.refresh_token:
                creds.refresh(Request())
            else:
                raise ValueError("凭证无效且无法刷新，请重新授权")

        self._creds = creds
        return creds

    def get_channel_info(self) -> Optional[Dict[str, Any]]:
        try:
            from googleapiclient.discovery import build

            creds = self._build_credentials()
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
            resp = youtube.channels().list(part="snippet,contentDetails", mine=True).execute()
            items = resp.get("items") or []
            if not items:
                return None
            ch = items[0]
            return {
                "channel_id": ch.get("id"),
                "channel_title": (ch.get("snippet") or {}).get("title"),
                "email": None,
            }
        except Exception as e:
            self.error_message = f"获取频道信息失败: {e}"
            logger.error(self.error_message)
            return None

    def upload_video(self, video_path: str, metadata: Dict[str, Any]) -> bool:
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            path = Path(video_path)
            if not path.exists() or path.stat().st_size == 0:
                self.error_message = f"视频文件不存在或为空: {video_path}"
                return False

            creds = self._build_credentials()
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

            title = (metadata.get("title") or path.stem)[:100]
            description = metadata.get("description") or metadata.get("desc") or title
            tags = metadata.get("tags") or []
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
            category_id = str(metadata.get("category_id") or "22")
            privacy = metadata.get("privacy_status") or "private"
            if privacy not in ("private", "unlisted", "public"):
                privacy = "private"

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags[:500],
                    "categoryId": category_id,
                },
                "status": {
                    "privacyStatus": privacy,
                    "selfDeclaredMadeForKids": False,
                },
            }

            media = MediaFileUpload(
                str(path),
                mimetype="video/*",
                resumable=True,
                chunksize=8 * 1024 * 1024,
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info("YouTube 上传进度: %.1f%%", status.progress() * 100)

            self.video_id = response.get("id")
            self.video_url = f"https://www.youtube.com/watch?v={self.video_id}" if self.video_id else None
            logger.info("YouTube 上传成功: %s", self.video_url)
            return True
        except Exception as e:
            self.error_message = str(e)
            logger.exception("YouTube 上传失败")
            return False

    def export_credentials_json(self) -> str:
        """导出可持久化的 credentials JSON（含刷新后的 token）。"""
        if not self._creds:
            self._build_credentials()
        assert self._creds is not None
        cfg = get_youtube_oauth_config()
        payload = {
            "token": self._creds.token,
            "refresh_token": self._creds.refresh_token,
            "token_uri": self._creds.token_uri,
            "client_id": self._creds.client_id or cfg["client_id"],
            "client_secret": self._creds.client_secret or cfg["client_secret"],
            "scopes": list(self._creds.scopes or SCOPES),
        }
        return json.dumps(payload)


def build_authorization_url(state: str = "autoclip") -> Tuple[str, str]:
    """返回 (auth_url, state)。"""
    from google_auth_oauthlib.flow import Flow

    if not oauth_configured():
        raise ValueError("未配置 YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET")

    cfg = get_youtube_oauth_config()
    client_config = {
        "web": {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [cfg["redirect_uri"]],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state)
    flow.redirect_uri = cfg["redirect_uri"]
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, state


def exchange_code_for_credentials(code: str) -> Dict[str, Any]:
    """用授权码换取 credentials 字典。"""
    from google_auth_oauthlib.flow import Flow

    if not oauth_configured():
        raise ValueError("未配置 YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET")

    cfg = get_youtube_oauth_config()
    client_config = {
        "web": {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [cfg["redirect_uri"]],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = cfg["redirect_uri"]
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }
