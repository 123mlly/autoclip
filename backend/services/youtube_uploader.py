"""
YouTube Data API v3 上传器
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_OAUTH_PKCE_TTL_SEC = 600
_OAUTH_PKCE_REDIS_PREFIX = "youtube_oauth:pkce:"
# Redis 不可用时的单进程内存兜底（开发环境）
_oauth_pkce_memory: Dict[str, Tuple[float, str]] = {}

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
SCOPES = [YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE]

# YouTube snippet.tags 总字符上限约 500；标题最多 100 字，优先塞 hashtag
_YOUTUBE_TAGS_CHAR_LIMIT = 500
_YOUTUBE_TITLE_HASHTAG_LIMIT = 5
_YOUTUBE_DESC_HASHTAG_LIMIT = 5


def _normalize_tag_list(tags: Any) -> List[str]:
    """Normalize tags from list / JSON string / comma-separated string."""
    if not tags:
        return []
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            if isinstance(parsed, list):
                tags = parsed
            else:
                tags = [t.strip() for t in tags.split(",") if t.strip()]
        except Exception:
            tags = [t.strip() for t in tags.split(",") if t.strip()]
    if not isinstance(tags, list):
        return []

    result: List[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        cleaned = tag.strip().lstrip("#").strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _tag_to_hashtag(tag: str) -> str:
    cleaned = tag.strip().lstrip("#").replace(" ", "")
    return f"#{cleaned}" if cleaned else ""


def _fit_tags_char_limit(tags: List[str], limit: int = _YOUTUBE_TAGS_CHAR_LIMIT) -> List[str]:
    """Trim tags to YouTube's ~500 character budget (commas / quotes count)."""
    result: List[str] = []
    used = 0
    for tag in tags:
        extra = 2 if " " in tag else 0
        cost = len(tag) + extra + (1 if result else 0)
        if used + cost > limit:
            break
        result.append(tag)
        used += cost
    return result


def _append_hashtags_to_text(
    text: str,
    tags: List[str],
    *,
    max_hashtags: int,
    max_len: Optional[int] = None,
) -> tuple[str, List[str]]:
    """Append hashtags to text. Returns (new_text, tags_not_used)."""
    existing = (text or "").rstrip()
    existing_lower = existing.lower()
    used_hashtags: List[str] = []
    unused_tags: List[str] = []

    for i, tag in enumerate(tags):
        ht = _tag_to_hashtag(tag)
        if not ht:
            continue
        if ht.lower() in existing_lower or ht in used_hashtags:
            continue
        if len(used_hashtags) >= max_hashtags:
            unused_tags.extend(tags[i:])
            break
        candidate = f"{existing} {ht}".strip() if existing else ht
        if max_len is not None and len(candidate) > max_len:
            unused_tags.extend(tags[i:])
            break
        existing = candidate
        existing_lower = existing.lower()
        used_hashtags.append(ht)

    if max_len is not None:
        existing = existing[:max_len]
    return existing, unused_tags


def _append_hashtags_to_title(
    title: str,
    tags: List[str],
    max_hashtags: int = _YOUTUBE_TITLE_HASHTAG_LIMIT,
    max_len: int = 100,
) -> tuple[str, List[str]]:
    """Prefer putting hashtags in the title; return leftover tags."""
    return _append_hashtags_to_text(
        title, tags, max_hashtags=max_hashtags, max_len=max_len
    )


def _append_hashtags_to_description(
    description: str,
    tags: List[str],
    max_hashtags: int = _YOUTUBE_DESC_HASHTAG_LIMIT,
) -> str:
    """Append leftover hashtags to description when they did not fit in title."""
    text, _ = _append_hashtags_to_text(
        description, tags, max_hashtags=max_hashtags, max_len=None
    )
    return text


def get_youtube_oauth_config() -> Dict[str, str]:
    """从环境变量读取 OAuth 配置。"""
    from ..core.youtube_settings import get_youtube_oauth_config as _get_cfg

    cfg = _get_cfg()
    return {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": cfg["redirect_uri"],
    }


def oauth_configured() -> bool:
    from ..core.youtube_settings import oauth_configured as _configured

    return _configured()


def get_oauth_frontend_redirect_base() -> str:
    from ..core.youtube_settings import get_oauth_frontend_redirect_base as _base

    return _base()


def _oauth_pkce_redis():
    import redis

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(redis_url, decode_responses=True)


def _store_oauth_pkce(state: str, code_verifier: str, nickname: Optional[str] = None) -> None:
    payload = json.dumps({"code_verifier": code_verifier, "nickname": nickname})
    key = f"{_OAUTH_PKCE_REDIS_PREFIX}{state}"
    try:
        client = _oauth_pkce_redis()
        client.setex(key, _OAUTH_PKCE_TTL_SEC, payload)
        return
    except Exception as e:
        logger.warning("Redis 不可用，OAuth PKCE 使用内存存储（单进程）: %s", e)
    _oauth_pkce_memory[state] = (time.time() + _OAUTH_PKCE_TTL_SEC, payload)


def _pop_oauth_pkce(state: str) -> Optional[Dict[str, Any]]:
    if not state:
        return None
    key = f"{_OAUTH_PKCE_REDIS_PREFIX}{state}"
    try:
        client = _oauth_pkce_redis()
        raw = client.get(key)
        if raw:
            client.delete(key)
            return json.loads(raw)
    except Exception as e:
        logger.warning("从 Redis 读取 OAuth PKCE 失败，尝试内存: %s", e)

    entry = _oauth_pkce_memory.pop(state, None)
    if not entry:
        return None
    expires_at, payload = entry
    if time.time() > expires_at:
        return None
    return json.loads(payload)


def _create_oauth_flow(state: Optional[str] = None):
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
    return flow


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

            raw_title = metadata.get("title") or path.stem
            raw_description = metadata.get("description") or metadata.get("desc") or ""
            tags = _normalize_tag_list(metadata.get("tags"))
            # 发现力：hashtag 优先写入标题；放不下的再补到描述；snippet.tags 仍保留
            title, leftover_tags = _append_hashtags_to_title(str(raw_title)[:100], tags)
            description = _append_hashtags_to_description(
                str(raw_description) if raw_description else "",
                leftover_tags,
            )
            if not description.strip():
                description = str(raw_title)
            snippet_tags = _fit_tags_char_limit(tags)
            category_id = str(metadata.get("category_id") or "22")
            privacy = metadata.get("privacy_status") or "private"
            if privacy not in ("private", "unlisted", "public"):
                privacy = "private"

            logger.info(
                "YouTube 元数据: title=%s leftover_to_desc=%s tags=%s",
                title,
                leftover_tags,
                snippet_tags,
            )

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": snippet_tags,
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


def build_authorization_url(nickname: Optional[str] = None) -> Tuple[str, str]:
    """返回 (auth_url, state)。state 用于回调时取回 PKCE code_verifier。"""
    oauth_state = secrets.token_urlsafe(32)
    flow = _create_oauth_flow(state=oauth_state)
    auth_url, oauth_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    code_verifier = getattr(flow, "code_verifier", None)
    if not code_verifier:
        raise RuntimeError("OAuth Flow 未生成 code_verifier，无法完成 PKCE 授权")
    _store_oauth_pkce(oauth_state, code_verifier, nickname=nickname)
    logger.info("YouTube OAuth 已生成 state=%s…", oauth_state[:8])
    return auth_url, oauth_state


def exchange_code_for_credentials(code: str, state: Optional[str] = None) -> Dict[str, Any]:
    """用授权码换取 credentials 字典（需与 /oauth/start 返回的 state 配对）。"""
    pkce = _pop_oauth_pkce(state or "")
    if not pkce or not pkce.get("code_verifier"):
        raise ValueError(
            "OAuth 会话已过期或 state 无效。请重新点击「Google 授权登录」，"
            "不要刷新或重复使用旧的授权回调链接。"
        )

    flow = _create_oauth_flow(state=state)
    flow.code_verifier = pkce["code_verifier"]
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
        "_oauth_nickname": pkce.get("nickname"),
    }
