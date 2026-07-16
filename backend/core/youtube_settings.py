"""
YouTube OAuth 配置读取（优先 settings.json，回退 .env）
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from .path_utils import get_settings_file_path

logger = logging.getLogger(__name__)

DEFAULT_REDIRECT_URI = "http://localhost:8000/api/v1/youtube-upload/oauth/callback"


def _read_settings_file() -> Dict[str, Any]:
    path = get_settings_file_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        logger.warning("读取 settings.json 失败: %s", e)
        return {}


def get_youtube_oauth_config() -> Dict[str, str]:
    """合并 UI 设置与环境变量，供 OAuth / 上传使用。"""
    saved = _read_settings_file()
    client_id = (saved.get("youtube_client_id") or os.getenv("YOUTUBE_CLIENT_ID", "")).strip()
    client_secret = (saved.get("youtube_client_secret") or os.getenv("YOUTUBE_CLIENT_SECRET", "")).strip()
    redirect_uri = (
        saved.get("youtube_redirect_uri")
        or os.getenv("YOUTUBE_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    ).strip()
    frontend_url = (
        saved.get("youtube_oauth_frontend_url")
        or os.getenv("YOUTUBE_OAUTH_FRONTEND_URL")
        or os.getenv("FRONTEND_URL", "http://localhost:3000")
    ).strip().rstrip("/")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri or DEFAULT_REDIRECT_URI,
        "frontend_url": frontend_url,
    }


def oauth_configured() -> bool:
    cfg = get_youtube_oauth_config()
    return bool(cfg["client_id"] and cfg["client_secret"])


def get_oauth_frontend_redirect_base() -> str:
    cfg = get_youtube_oauth_config()
    return f"{cfg['frontend_url']}/settings?youtube=1"


def apply_youtube_oauth_to_env(settings: Dict[str, Any]) -> None:
    """保存设置后同步到进程环境变量（兼容旧逻辑）。"""
    if settings.get("youtube_client_id") is not None:
        os.environ["YOUTUBE_CLIENT_ID"] = settings.get("youtube_client_id") or ""
    if settings.get("youtube_client_secret") is not None:
        os.environ["YOUTUBE_CLIENT_SECRET"] = settings.get("youtube_client_secret") or ""
    if settings.get("youtube_redirect_uri") is not None:
        os.environ["YOUTUBE_REDIRECT_URI"] = settings.get("youtube_redirect_uri") or DEFAULT_REDIRECT_URI
    if settings.get("youtube_oauth_frontend_url") is not None:
        os.environ["YOUTUBE_OAUTH_FRONTEND_URL"] = settings.get("youtube_oauth_frontend_url") or ""
