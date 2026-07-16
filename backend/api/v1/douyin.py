"""
抖音链接导入：解析 / 下载

优先走 iesdouyin 分享页（多数公开视频无需 Cookie）；失败时再回退 yt-dlp。
短链 v.douyin.com 会跟随重定向解析视频 ID。
可选上传 cookies.txt（部分受限视频需要）。
"""

import logging
import os
import uuid
import asyncio
import base64
import shutil
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Form, UploadFile, File
from pydantic import BaseModel
import yt_dlp
import requests

from ...core.config import get_data_directory
from ...utils.douyin_downloader import (
    DouyinDownloadError,
    download_douyin_direct,
    fetch_douyin_share_info,
    is_douyin_user_page,
)

logger = logging.getLogger(__name__)
router = APIRouter()

download_tasks = {}

_DOUYIN_BROWSER_CANDIDATES = ("chrome", "safari", "edge", "firefox", "chromium", "brave")
_DOUYIN_COOKIE_FILENAME = "douyin.txt"


def _running_in_docker() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("RUNNING_IN_DOCKER", "").lower() in (
        "1",
        "true",
        "yes",
    )


def get_douyin_cookiefile_path() -> Path:
    return get_data_directory() / "cookies" / _DOUYIN_COOKIE_FILENAME


def resolve_douyin_cookiefile() -> Optional[Path]:
    path = get_douyin_cookiefile_path()
    if path.is_file() and path.stat().st_size > 0:
        return path
    return None


def validate_douyin_url(url: str) -> bool:
    u = (url or "").lower()
    if is_douyin_user_page(u):
        return False
    return any(
        host in u
        for host in (
            "douyin.com",
            "v.douyin.com",
            "iesdouyin.com",
            "www.iesdouyin.com",
        )
    )


def _douyin_auth_hint() -> str:
    if _running_in_docker():
        return (
            "公开视频一般无需 Cookie。若仍失败，请在链接导入页上传抖音 cookies.txt"
            f"（保存为 data/cookies/{_DOUYIN_COOKIE_FILENAME}）。"
            "请确认粘贴的是单条视频链接，而非用户主页。"
        )
    return (
        "公开视频一般无需 Cookie。若仍失败，请上传从 douyin.com 导出的 cookies.txt，"
        "或换用 App「分享 → 复制链接」的短链。请勿粘贴用户主页。"
    )


def _is_auth_error(error: Exception) -> bool:
    msg = str(error).lower()
    return any(
        key in msg
        for key in (
            "fresh cookies",
            "cookies are needed",
            "login required",
            "cookiefile",
            "cookiesfrombrowser",
            "blocked",
            "验证",
            "登录",
            "forbidden",
            "403",
            "不可见",
            "需登录",
        )
    )


def _build_douyin_ydl_opts(
    browser: Optional[str] = None,
    for_download: bool = False,
    extra: Optional[dict] = None,
    *,
    use_cookiefile: bool = True,
) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": not for_download,
        "noplaylist": True,
    }
    if for_download:
        opts["format"] = "bv*+ba/b"
        opts["merge_output_format"] = "mp4"

    cookiefile = resolve_douyin_cookiefile() if use_cookiefile else None
    if cookiefile:
        opts["cookiefile"] = str(cookiefile)
    elif browser:
        opts["cookiesfrombrowser"] = (browser.lower(),)
    if extra:
        opts.update(extra)
    return opts


def extract_douyin_info(url: str, browser: Optional[str] = None) -> tuple[dict, Optional[str], bool]:
    """返回 (info_dict, used_browser, used_cookiefile)"""
    if is_douyin_user_page(url):
        raise RuntimeError(
            "这是抖音用户主页，不是视频链接。请粘贴单条视频链接"
            "（www.douyin.com/video/... 或 v.douyin.com 短链）。"
        )

    last_error: Optional[Exception] = None
    cookiefile = resolve_douyin_cookiefile()

    # 1) 优先：iesdouyin 分享页（多数公开视频无需 Cookie）
    try:
        logger.info(f"解析抖音（分享页）: {url}")
        info = fetch_douyin_share_info(url, cookiefile=cookiefile)
        if info:
            return info, None, bool(cookiefile)
    except DouyinDownloadError as e:
        last_error = e
        logger.warning(f"抖音分享页解析失败，回退 yt-dlp: {e}")
    except Exception as e:
        last_error = e
        logger.warning(f"抖音分享页解析异常，回退 yt-dlp: {e}")

    # 2) 回退：yt-dlp + cookiefile / 浏览器
    if cookiefile:
        opts = _build_douyin_ydl_opts(None, for_download=False, use_cookiefile=True)
        try:
            logger.info(f"解析抖音（cookiefile={cookiefile}）: {url}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                raise RuntimeError("未获取到视频信息")
            return info, None, True
        except Exception as e:
            last_error = e
            logger.warning(f"抖音解析失败 cookiefile: {e}")

    browsers_to_try: list[Optional[str]] = []
    if browser:
        browsers_to_try.append(browser.lower())
    else:
        browsers_to_try.append(None)
        if not _running_in_docker():
            browsers_to_try.extend(_DOUYIN_BROWSER_CANDIDATES)

    for candidate in browsers_to_try:
        opts = _build_douyin_ydl_opts(candidate, for_download=False, use_cookiefile=False)
        try:
            logger.info(f"解析抖音（browser={candidate or 'none'}）: {url}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                raise RuntimeError("未获取到视频信息")
            return info, candidate, False
        except Exception as e:
            last_error = e
            logger.warning(f"抖音解析失败 browser={candidate or 'none'}: {e}")
            if browser:
                break

    hint = _douyin_auth_hint()
    if last_error and _is_auth_error(last_error):
        raise RuntimeError(f"{hint} 原始错误: {last_error}") from last_error
    raise RuntimeError(f"解析抖音失败: {last_error}") from last_error


class DouyinDownloadRequest(BaseModel):
    url: str
    project_name: str
    video_category: Optional[str] = "default"
    browser: Optional[str] = None


class DouyinDownloadTask(BaseModel):
    id: str
    url: str
    project_name: str
    video_category: str
    status: str
    progress: float
    error_message: Optional[str] = None
    project_id: Optional[str] = None
    created_at: str
    updated_at: str


@router.get("/cookies/status")
async def douyin_cookies_status():
    path = resolve_douyin_cookiefile()
    if not path:
        return {
            "configured": False,
            "path": str(get_douyin_cookiefile_path()),
            "in_docker": _running_in_docker(),
            "hint": _douyin_auth_hint(),
        }
    stat = path.stat()
    return {
        "configured": True,
        "path": str(path),
        "size": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "in_docker": _running_in_docker(),
        "hint": "已配置 cookies.txt，解析/下载将优先使用该文件。",
    }


@router.post("/cookies")
async def upload_douyin_cookies(file: UploadFile = File(...)):
    """上传 Netscape 格式抖音 cookies.txt（扩展「Get cookies.txt LOCALLY」从 douyin.com 导出）。"""
    filename = (file.filename or "").lower()
    if filename and not (
        filename.endswith(".txt") or filename.endswith(".cookies") or "cookie" in filename
    ):
        if file.content_type and "text" not in file.content_type and file.content_type != "application/octet-stream":
            raise HTTPException(status_code=400, detail="请上传 cookies.txt 文本文件")

    raw = await file.read()
    if not raw or len(raw) < 20:
        raise HTTPException(status_code=400, detail="Cookie 文件为空或过短")
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Cookie 文件过大（上限 2MB）")

    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail="Cookie 文件必须是 UTF-8 文本") from e

    lowered = text.lower()
    if "douyin" not in lowered and "netscape" not in lowered and "\t" not in text:
        logger.warning("上传的 cookie 未明显包含 douyin 域名，仍将保存供 yt-dlp 使用")

    dest = get_douyin_cookiefile_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    logger.info(f"已保存抖音 cookies: {dest} ({dest.stat().st_size} bytes)")

    return {
        "success": True,
        "configured": True,
        "path": str(dest),
        "size": dest.stat().st_size,
        "message": "cookies.txt 已保存，可重新解析抖音链接",
    }


@router.delete("/cookies")
async def delete_douyin_cookies():
    path = get_douyin_cookiefile_path()
    if path.is_file():
        path.unlink()
        logger.info(f"已删除抖音 cookies: {path}")
    return {"success": True, "configured": False}


@router.post("/parse")
async def parse_douyin_video(
    url: str = Form(...),
    browser: Optional[str] = Form(None),
):
    try:
        if is_douyin_user_page(url):
            raise HTTPException(
                status_code=400,
                detail="这是抖音用户主页，不是视频链接。请粘贴单条视频链接（www.douyin.com/video/... 或 v.douyin.com 短链）。",
            )
        if not validate_douyin_url(url):
            raise HTTPException(
                status_code=400,
                detail="无效的抖音视频链接。请使用 www.douyin.com/video/... 或 App 分享短链。",
            )

        loop = asyncio.get_event_loop()
        info_dict, used_browser, used_cookiefile = await loop.run_in_executor(
            None, extract_douyin_info, url, browser
        )

        return {
            "success": True,
            "used_browser": used_browser,
            "used_cookiefile": used_cookiefile,
            "video_info": {
                "title": info_dict.get("title", "Unknown"),
                "description": info_dict.get("description", "") or "",
                "duration": info_dict.get("duration", 0) or 0,
                "uploader": info_dict.get("uploader") or info_dict.get("creator") or "Unknown",
                "upload_date": info_dict.get("upload_date", "") or "",
                "view_count": info_dict.get("view_count", 0) or 0,
                "like_count": info_dict.get("like_count", 0) or 0,
                "thumbnail": info_dict.get("thumbnail", "") or "",
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解析抖音视频失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download")
async def create_douyin_download_task(request: DouyinDownloadRequest):
    try:
        if is_douyin_user_page(request.url):
            raise HTTPException(
                status_code=400,
                detail="这是抖音用户主页，不是视频链接。请粘贴单条视频链接。",
            )
        if not validate_douyin_url(request.url):
            raise HTTPException(status_code=400, detail="无效的抖音视频链接")

        loop = asyncio.get_event_loop()
        video_info, used_browser, used_cookiefile = await loop.run_in_executor(
            None, extract_douyin_info, request.url, request.browser
        )
        if used_cookiefile:
            logger.info("下载任务将使用已上传的抖音 cookies.txt")
        elif used_browser and not request.browser:
            request.browser = used_browser

        from ...core.database import SessionLocal
        from ...services.project_service import ProjectService
        from ...schemas.project import ProjectCreate, ProjectType, ProjectStatus
        from ...core.path_utils import get_project_directory

        db = SessionLocal()
        try:
            project_service = ProjectService(db)

            thumbnail_data = None
            thumbnail_url = video_info.get("thumbnail", "") or ""
            if thumbnail_url:
                try:
                    response = requests.get(thumbnail_url, timeout=10)
                    if response.status_code == 200:
                        thumbnail_base64 = base64.b64encode(response.content).decode("utf-8")
                        thumbnail_data = f"data:image/jpeg;base64,{thumbnail_base64}"
                except Exception as e:
                    logger.warning(f"处理抖音缩略图失败: {e}")

            category = request.video_category or "default"
            try:
                project_type = ProjectType(category)
            except Exception:
                project_type = ProjectType.KNOWLEDGE

            project_data = ProjectCreate(
                name=request.project_name,
                description=f"从抖音下载: {video_info.get('title', 'Unknown')}",
                project_type=project_type,
                status=ProjectStatus.PENDING,
                source_url=request.url,
                source_file=None,
                settings={
                    "download_status": "downloading",
                    "download_progress": 0.0,
                    "douyin_info": {
                        "url": request.url,
                        "browser": request.browser,
                        "title": video_info.get("title", "Unknown"),
                        "uploader": video_info.get("uploader")
                        or video_info.get("creator")
                        or "Unknown",
                        "duration": video_info.get("duration", 0) or 0,
                        "view_count": video_info.get("view_count", 0) or 0,
                        "thumbnail_url": thumbnail_url,
                    },
                },
            )

            project = project_service.create_project(project_data)
            project_id = str(project.id)
            if thumbnail_data:
                project.thumbnail = thumbnail_data
                db.commit()

            project_dir = get_project_directory(project_id)
            raw_dir = project_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)

            task_id = str(uuid.uuid4())
            task = DouyinDownloadTask(
                id=task_id,
                url=request.url,
                project_name=request.project_name,
                video_category=category,
                status="pending",
                progress=0.0,
                project_id=project_id,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )
            download_tasks[task_id] = task

            from .async_task_manager import task_manager

            await task_manager.create_safe_task(
                f"douyin_download_{task_id}",
                process_douyin_download_task,
                task_id,
                request,
                project_id,
            )

            return {
                "project_id": project_id,
                "task_id": task_id,
                "status": "created",
                "message": "项目已创建，正在下载中...",
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建抖音下载任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {e}")


@router.get("/tasks/{task_id}")
async def get_douyin_task_status(task_id: str):
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    return download_tasks[task_id]


@router.get("/tasks")
async def get_all_douyin_tasks():
    return list(download_tasks.values())


async def update_project_download_progress(project_id: str, progress: float, message: str):
    try:
        from ...core.database import SessionLocal
        from ...services.project_service import ProjectService
        from ...schemas.project import ProjectStatus

        db = SessionLocal()
        try:
            project_service = ProjectService(db)
            project = project_service.get(project_id)
            if project:
                if not project.processing_config:
                    project.processing_config = {}
                project.processing_config.update({
                    "download_progress": progress,
                    "download_message": message,
                })
                if progress >= 100.0:
                    project.status = ProjectStatus.PENDING
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"更新抖音下载进度失败: {e}")


def _format_douyin_download_error(error: Exception) -> str:
    raw = str(error)
    if _is_auth_error(error):
        return (
            "抖音需要有效登录 Cookie（可能已失效）。"
            "请在链接导入页重新上传从已登录 douyin.com 导出的 cookies.txt。"
            f" 详情: {raw}"
        )
    return raw


async def _mark_douyin_download_failed(project_id: Optional[str], error: Exception) -> str:
    msg = _format_douyin_download_error(error)
    if not project_id:
        return msg
    try:
        from ...core.database import SessionLocal
        from ...services.project_service import ProjectService
        from ...schemas.project import ProjectStatus

        db = SessionLocal()
        try:
            project = ProjectService(db).get(project_id)
            if project:
                project.status = ProjectStatus.FAILED
                if not project.processing_config:
                    project.processing_config = {}
                project.processing_config.update({
                    "download_status": "failed",
                    "download_progress": 0.0,
                    "download_message": msg,
                    "error_message": msg,
                })
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"标记抖音下载失败状态出错: {e}")
    return msg


async def process_douyin_download_task(
    task_id: str, request: DouyinDownloadRequest, project_id: str
):
    try:
        download_tasks[task_id].status = "processing"
        download_tasks[task_id].progress = 10.0
        await update_project_download_progress(project_id, 10.0, "正在获取视频信息...")

        data_dir = get_data_directory()
        download_dir = data_dir / "temp"
        download_dir.mkdir(exist_ok=True)

        await update_project_download_progress(project_id, 30.0, "正在下载视频...")

        cookiefile = resolve_douyin_cookiefile()
        browser = None if cookiefile else (request.browser.lower() if request.browser else None)
        loop = asyncio.get_event_loop()
        video_path: Optional[Path] = None

        # 1) 优先分享页直链（无需 Chrome / 多数情况无需 Cookie）
        try:
            def share_download_sync() -> Path:
                info = fetch_douyin_share_info(request.url, cookiefile=cookiefile)
                out = download_dir / f"douyin_{info['id']}.mp4"
                return download_douyin_direct(info, out, cookiefile=cookiefile)

            video_path = await loop.run_in_executor(None, share_download_sync)
            logger.info(f"抖音分享页下载成功: {video_path}")
        except Exception as share_err:
            logger.warning(f"抖音分享页下载失败，回退 yt-dlp: {share_err}")

            ydl_opts = _build_douyin_ydl_opts(
                browser,
                for_download=True,
                use_cookiefile=True,
                extra={
                    "outtmpl": str(download_dir / "douyin_%(id)s.%(ext)s"),
                    "quiet": True,
                    "no_warnings": False,
                },
            )

            def download_sync(url: str, opts: dict):
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.download([url])

            await loop.run_in_executor(None, download_sync, request.url, ydl_opts)

            video_files = sorted(
                list(download_dir.glob("douyin_*.mp4"))
                + list(download_dir.glob("douyin_*.webm"))
                + list(download_dir.glob("douyin_*.mkv")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not video_files:
                candidates = [
                    p
                    for p in download_dir.iterdir()
                    if p.suffix.lower() in {".mp4", ".webm", ".mkv", ".flv"} and p.is_file()
                ]
                candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                video_files = candidates

            if not video_files:
                raise RuntimeError(f"未找到下载的视频文件（分享页错误: {share_err}）")
            video_path = video_files[0]
        download_tasks[task_id].progress = 80.0
        await update_project_download_progress(project_id, 60.0, "视频下载完成，正在整理文件...")

        from ...core.database import SessionLocal
        from ...services.project_service import ProjectService
        from ...schemas.project import ProjectStatus
        from ...core.path_utils import get_project_directory

        db = SessionLocal()
        try:
            project_service = ProjectService(db)
            project = project_service.get(project_id)
            if not project:
                raise RuntimeError(f"项目 {project_id} 不存在")

            if not project.processing_config:
                project.processing_config = {}
            project.processing_config.update({
                "download_status": "completed",
                "download_progress": 100.0,
            })

            raw_dir = get_project_directory(project_id) / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            new_video_path = raw_dir / "input.mp4"

            if video_path.suffix.lower() == ".mp4":
                shutil.move(str(video_path), str(new_video_path))
            else:
                # 非 mp4 先挪过去再 ffmpeg 转封装（尽量保持简单）
                tmp_path = raw_dir / f"input{video_path.suffix.lower()}"
                shutil.move(str(video_path), str(tmp_path))
                new_video_path = tmp_path
                project.video_path = str(tmp_path)

            project.video_path = str(new_video_path)
            project.status = ProjectStatus.PENDING
            db.commit()

            await update_project_download_progress(
                project_id, 100.0, "下载完成，已提交后台生成字幕/处理"
            )
            download_tasks[task_id].status = "completed"
            download_tasks[task_id].progress = 100.0
            download_tasks[task_id].project_id = project_id
            download_tasks[task_id].updated_at = datetime.now().isoformat()

            try:
                from ...tasks.import_processing import process_import_task

                celery_task = process_import_task.delay(
                    project_id,
                    str(new_video_path),
                    None,
                )
                logger.info(f"抖音项目 {project_id} 已提交 Celery: {celery_task.id}")
            except Exception as e:
                logger.error(f"提交 Celery 导入任务失败: {e}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"处理抖音下载任务失败: {e}")
        err_msg = await _mark_douyin_download_failed(project_id, e)
        if task_id in download_tasks:
            download_tasks[task_id].status = "failed"
            download_tasks[task_id].error_message = err_msg
            download_tasks[task_id].progress = 0.0
            download_tasks[task_id].project_id = project_id
            download_tasks[task_id].updated_at = datetime.now().isoformat()
