"""
YouTube相关API路由
处理YouTube视频解析和下载功能
"""

import logging
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Form, UploadFile, File
from pydantic import BaseModel
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from ...core.config import get_data_directory
import uuid
import asyncio
from datetime import datetime
import yt_dlp

logger = logging.getLogger(__name__)
router = APIRouter()

# 存储下载任务的状态
download_tasks = {}

# YouTube 常被判定为 bot，需浏览器 Cookie；解析时按顺序自动尝试
_YOUTUBE_BROWSER_CANDIDATES = ("chrome", "safari", "edge", "firefox", "chromium", "brave")
_YOUTUBE_COOKIE_FILENAME = "youtube.txt"


def _running_in_docker() -> bool:
    """容器内通常没有宿主机浏览器 Cookie 库。"""
    return Path("/.dockerenv").exists() or os.environ.get("RUNNING_IN_DOCKER", "").lower() in (
        "1",
        "true",
        "yes",
    )


def get_youtube_cookiefile_path() -> Path:
    """固定路径：data/cookies/youtube.txt（Docker 已挂载 ./data）。"""
    return get_data_directory() / "cookies" / _YOUTUBE_COOKIE_FILENAME


def resolve_youtube_cookiefile() -> Optional[Path]:
    path = get_youtube_cookiefile_path()
    if path.is_file() and path.stat().st_size > 0:
        return path
    return None


def _resolve_js_runtimes() -> dict:
    """
    YouTube 需要 JS 挑战求解（EJS）。默认只启用 deno；本机常见是 Node，
    因此同时启用 node（若在 PATH 中），避免签名/n challenge 失败后只剩图片格式。
    Docker 生产镜像应包含 Node ≥ 20。
    """
    import shutil

    runtimes: dict = {"deno": {}}
    node_path = shutil.which("node")
    if node_path:
        runtimes["node"] = {"path": node_path}
        logger.debug(f"yt-dlp js_runtimes: node={node_path}")
    else:
        logger.warning(
            "未找到 Node.js：YouTube n challenge 可能失败。"
            "Docker 请使用已包含 Node 22 的镜像并重建；本机请安装 Node ≥ 20。"
        )
    return runtimes


def _build_youtube_ydl_opts(
    browser: Optional[str] = None,
    for_download: bool = False,
    extra: Optional[dict] = None,
    *,
    use_cookiefile: bool = True,
) -> dict:
    """构建 yt-dlp 选项（含 EJS / Node 运行时）。优先 cookie 文件，其次浏览器 Cookie。"""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": not for_download,
        # 仅解析元数据时，即使暂无可用格式也继续返回标题/封面等
        "ignore_no_formats_error": not for_download,
        # 关键：启用 Node，配合已安装的 yt-dlp-ejs 求解签名
        "js_runtimes": _resolve_js_runtimes(),
    }
    if for_download:
        # 放宽格式：优先 mp4，否则任意最佳音视频再合并
        opts["format"] = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
        opts["merge_output_format"] = "mp4"

    cookiefile = resolve_youtube_cookiefile() if use_cookiefile else None
    if cookiefile:
        opts["cookiefile"] = str(cookiefile)
    elif browser:
        opts["cookiesfrombrowser"] = (browser.lower(),)
    if extra:
        opts.update(extra)
    return opts


def _is_bot_or_auth_error(error: Exception) -> bool:
    msg = str(error).lower()
    return any(
        key in msg
        for key in (
            "sign in to confirm",
            "not a bot",
            "cookiesfrombrowser",
            "cookiefile",
            "login required",
            "confirm you’re not a bot",
            "confirm you're not a bot",
            "could not find chrome cookies",
            "cookies database",
        )
    )


def _youtube_auth_hint() -> str:
    if _running_in_docker():
        return (
            "Docker 内无法读取本机浏览器 Cookie。"
            "请在链接导入页上传 YouTube 的 cookies.txt"
            f"（保存为 data/cookies/{_YOUTUBE_COOKIE_FILENAME}），或改用本机模式。"
        )
    return (
        "YouTube 需要登录态才能解析。请上传 cookies.txt，"
        "或选择已登录 YouTube 的浏览器（Chrome / Safari 等）。"
    )


def extract_youtube_info(url: str, browser: Optional[str] = None) -> tuple[dict, Optional[str], bool]:
    """
    解析 YouTube 视频信息。
    优先使用已上传的 cookies.txt；否则按 browser / 本机浏览器候选尝试。
    Docker 内跳过浏览器 Cookie（容器无 Chrome 配置）。
    返回 (info_dict, used_browser, used_cookiefile)
    """
    last_error: Optional[Exception] = None
    cookiefile = resolve_youtube_cookiefile()

    if cookiefile:
        opts = _build_youtube_ydl_opts(None, for_download=False, use_cookiefile=True)
        try:
            logger.info(f"解析 YouTube（cookiefile={cookiefile}）: {url}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                raise RuntimeError("未获取到视频信息")
            return info, None, True
        except Exception as e:
            last_error = e
            logger.warning(f"YouTube 解析失败 cookiefile: {e}")
            # cookie 文件无效时继续尝试浏览器（本机）或无 cookie

    browsers_to_try: list[Optional[str]] = []
    if browser:
        browsers_to_try.append(browser.lower())
    else:
        browsers_to_try.append(None)
        # Docker 内没有宿主机浏览器配置，盲试 chrome 只会刷错误日志
        if not _running_in_docker():
            browsers_to_try.extend(_YOUTUBE_BROWSER_CANDIDATES)

    for candidate in browsers_to_try:
        # 已试过 cookiefile；此处仅浏览器 / 无 cookie
        opts = _build_youtube_ydl_opts(
            candidate, for_download=False, use_cookiefile=False
        )
        try:
            logger.info(f"解析 YouTube（browser={candidate or 'none'}）: {url}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if not info:
                raise RuntimeError("未获取到视频信息")
            return info, candidate, False
        except Exception as e:
            last_error = e
            logger.warning(f"YouTube 解析失败 browser={candidate or 'none'}: {e}")
            if browser:
                break
            if candidate is None and not _is_bot_or_auth_error(e):
                continue

    hint = _youtube_auth_hint()
    if last_error and _is_bot_or_auth_error(last_error):
        raise RuntimeError(f"{hint} 原始错误: {last_error}") from last_error
    raise RuntimeError(f"解析 YouTube 失败: {last_error}") from last_error


class YouTubeParseRequest(BaseModel):
    url: str
    browser: Optional[str] = None

class YouTubeDownloadRequest(BaseModel):
    url: str
    project_name: str
    video_category: Optional[str] = "default"
    browser: Optional[str] = None

class YouTubeVideoInfo(BaseModel):
    title: str
    description: str
    duration: int
    uploader: str
    upload_date: str
    view_count: int
    like_count: int
    thumbnail: str

class YouTubeDownloadTask(BaseModel):
    id: str
    url: str
    project_name: str
    video_category: str
    status: str  # pending, processing, completed, failed
    progress: float
    error_message: Optional[str] = None
    project_id: Optional[str] = None
    created_at: str
    updated_at: str


@router.get("/cookies/status")
async def youtube_cookies_status():
    """查询已上传的 YouTube cookies.txt 状态（Docker 推荐）。"""
    path = resolve_youtube_cookiefile()
    if not path:
        return {
            "configured": False,
            "path": str(get_youtube_cookiefile_path()),
            "in_docker": _running_in_docker(),
            "hint": _youtube_auth_hint(),
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
async def upload_youtube_cookies(file: UploadFile = File(...)):
    """
    上传 Netscape 格式的 YouTube cookies.txt。
    可用浏览器扩展「Get cookies.txt LOCALLY」从已登录的 youtube.com 导出。
    """
    filename = (file.filename or "").lower()
    if filename and not (
        filename.endswith(".txt") or filename.endswith(".cookies") or "cookie" in filename
    ):
        # 仍允许无扩展名；仅拦截明显非文本类型
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

    # Netscape cookies.txt 通常含 # Netscape 或域名行；也接受简单的 name=value 导出
    lowered = text.lower()
    if "youtube" not in lowered and ".youtube." not in lowered and "netscape" not in lowered:
        # 宽松：只要像 cookie 表或含 SID/HSID 等也可
        if "\t" not in text and "youtube.com" not in lowered:
            logger.warning("上传的 cookie 文件未检测到 youtube 域名，仍将保存供 yt-dlp 使用")

    dest = get_youtube_cookiefile_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    logger.info(f"已保存 YouTube cookies: {dest} ({dest.stat().st_size} bytes)")

    return {
        "success": True,
        "configured": True,
        "path": str(dest),
        "size": dest.stat().st_size,
        "message": "cookies.txt 已保存，可重新解析 YouTube 链接",
    }


@router.delete("/cookies")
async def delete_youtube_cookies():
    """删除已上传的 YouTube cookies.txt。"""
    path = get_youtube_cookiefile_path()
    if path.is_file():
        path.unlink()
        logger.info(f"已删除 YouTube cookies: {path}")
    return {"success": True, "configured": False}


@router.post("/parse")
async def parse_youtube_video(
    url: str = Form(...),
    browser: Optional[str] = Form(None)
):
    """解析YouTube视频信息"""
    try:
        logger.info(f"开始解析YouTube视频: {url}")
        
        # 简单的URL验证
        if "youtube.com" not in url and "youtu.be" not in url:
            raise HTTPException(status_code=400, detail="无效的YouTube视频链接")
        
        loop = asyncio.get_event_loop()
        info_dict, used_browser, used_cookiefile = await loop.run_in_executor(
            None, extract_youtube_info, url, browser
        )
        
        logger.info(
            f"YouTube视频信息解析成功: {info_dict.get('title', 'Unknown')} "
            f"(browser={used_browser or 'none'}, cookiefile={used_cookiefile})"
        )
        
        return {
            "success": True,
            "used_browser": used_browser,
            "used_cookiefile": used_cookiefile,
            "video_info": {
                "title": info_dict.get('title', 'Unknown'),
                "description": info_dict.get('description', ''),
                "duration": info_dict.get('duration', 0),
                "uploader": info_dict.get('uploader', 'Unknown'),
                "upload_date": info_dict.get('upload_date', ''),
                "view_count": info_dict.get('view_count', 0),
                "like_count": info_dict.get('like_count', 0),
                "thumbnail": info_dict.get('thumbnail', '')
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"解析YouTube视频失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/download")
async def create_youtube_download_task(request: YouTubeDownloadRequest):
    """创建YouTube视频下载任务 - 立即创建项目"""
    try:
        logger.info(f"创建YouTube下载任务: {request.url}")
        
        # 先获取视频信息以获取缩略图（cookie 文件或浏览器 Cookie）
        loop = asyncio.get_event_loop()
        video_info, used_browser, used_cookiefile = await loop.run_in_executor(
            None, extract_youtube_info, request.url, request.browser
        )
        if used_cookiefile:
            logger.info("下载任务将使用已上传的 cookies.txt")
        elif used_browser and not request.browser:
            request.browser = used_browser
            logger.info(f"下载任务将使用自动检测到的浏览器 Cookie: {used_browser}")
        
        # 立即创建项目记录
        from ...core.database import SessionLocal
        from ...services.project_service import ProjectService
        from ...schemas.project import ProjectCreate, ProjectType, ProjectStatus
        
        db = SessionLocal()
        try:
            project_service = ProjectService(db)
            
            # 处理缩略图 - 直接使用解析出来的封面图
            thumbnail_data = None
            thumbnail_url = video_info.get('thumbnail', '')
            if thumbnail_url:
                try:
                    import requests
                    import base64
                    
                    # 下载缩略图
                    response = requests.get(thumbnail_url, timeout=10)
                    if response.status_code == 200:
                        # 转换为base64
                        thumbnail_base64 = base64.b64encode(response.content).decode('utf-8')
                        thumbnail_data = f"data:image/jpeg;base64,{thumbnail_base64}"
                        logger.info(f"YouTube缩略图获取成功: {video_info.get('title', 'Unknown')}")
                    else:
                        logger.warning(f"下载YouTube缩略图失败: {response.status_code}")
                except Exception as e:
                    logger.error(f"处理YouTube缩略图失败: {e}")
                    # 缩略图处理失败不影响主流程
            
            # 创建项目数据
            project_data = ProjectCreate(
                name=request.project_name,
                description=f"从YouTube下载: {video_info.get('title', 'Unknown')}",
                project_type=ProjectType(request.video_category),
                status=ProjectStatus.PENDING,  # 初始状态为等待中
                source_url=request.url,
                source_file=None,  # 暂时为空，下载完成后更新
                settings={
                    "download_status": "downloading",
                    "download_progress": 0.0,
                    "youtube_info": {
                        "url": request.url,
                        "browser": request.browser,
                        "title": video_info.get('title', 'Unknown'),
                        "uploader": video_info.get('uploader', 'Unknown'),
                        "duration": video_info.get('duration', 0),
                        "view_count": video_info.get('view_count', 0),
                        "thumbnail_url": thumbnail_url
                    }
                }
            )
            
            project = project_service.create_project(project_data)
            project_id = str(project.id)
            
            # 设置缩略图
            if thumbnail_data:
                project.thumbnail = thumbnail_data
                db.commit()
                logger.info(f"项目 {project_id} 缩略图已设置")
            
            # 创建项目目录
            from ...core.path_utils import get_project_directory
            project_dir = get_project_directory(project_id)
            raw_dir = project_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"项目已创建: {project_id}")
            
            # 生成下载任务ID
            task_id = str(uuid.uuid4())
            
            # 创建任务记录
            task = YouTubeDownloadTask(
                id=task_id,
                url=request.url,
                project_name=request.project_name,
                video_category=request.video_category,
                status="pending",
                progress=0.0,
                project_id=project_id,  # 关联项目ID
                created_at=str(uuid.uuid1().time),
                updated_at=str(uuid.uuid1().time)
            )
            
            # 存储任务
            download_tasks[task_id] = task
            
            # 异步启动下载任务 - 使用安全的任务管理器
            from .async_task_manager import task_manager
            await task_manager.create_safe_task(
                f"youtube_download_{task_id}", 
                process_youtube_download_task, 
                task_id, 
                request, 
                project_id
            )
            
            # 返回项目信息而不是任务信息
            return {
                "project_id": project_id,
                "task_id": task_id,
                "status": "created",
                "message": "项目已创建，正在下载中..."
            }
            
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"创建YouTube下载任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")

@router.get("/tasks/{task_id}")
async def get_youtube_task_status(task_id: str):
    """获取YouTube下载任务状态"""
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return download_tasks[task_id]

@router.get("/tasks")
async def get_all_youtube_tasks():
    """获取所有YouTube下载任务"""
    return list(download_tasks.values())

async def update_project_download_progress(project_id: str, progress: float, message: str):
    """更新项目下载进度"""
    try:
        from ...core.database import SessionLocal
        from ...services.project_service import ProjectService
        
        db = SessionLocal()
        try:
            project_service = ProjectService(db)
            project = project_service.get(project_id)
            
            if project:
                # 更新项目设置中的下载进度
                if not project.processing_config:
                    project.processing_config = {}
                
                project.processing_config.update({
                    "download_progress": progress,
                    "download_message": message
                })
                
                # 如果进度达到100%，更新状态为等待处理
                if progress >= 100.0:
                    from ...schemas.project import ProjectStatus
                    project.status = ProjectStatus.PENDING
                
                db.commit()
                logger.info(f"项目 {project_id} 下载进度更新: {progress}% - {message}")
                
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"更新项目下载进度失败: {e}")


def _format_youtube_download_error(error: Exception) -> str:
    """把 yt-dlp / Cookie 相关错误整理成前端可读文案。"""
    raw = str(error)
    lower = raw.lower()
    if any(
        k in lower
        for k in (
            "sign in to confirm",
            "not a bot",
            "login required",
            "cookiesfrombrowser",
            "cookiefile",
        )
    ):
        return (
            "YouTube 需要有效登录 Cookie（可能已失效）。"
            "请在链接导入页重新上传从已登录 youtube.com 导出的 cookies.txt 后再试。"
            f" 详情: {raw}"
        )
    return raw


async def _mark_youtube_download_failed(project_id: Optional[str], error: Exception) -> str:
    """标记内存任务与项目为失败，返回给前端的错误文案。"""
    msg = _format_youtube_download_error(error)
    if not project_id:
        return msg
    try:
        from ...core.database import SessionLocal
        from ...services.project_service import ProjectService
        from ...schemas.project import ProjectStatus

        db = SessionLocal()
        try:
            project_service = ProjectService(db)
            project = project_service.get(project_id)
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
                logger.info(f"项目 {project_id} 已标记为下载失败")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"标记项目下载失败状态时出错: {e}")
    return msg

async def process_youtube_download_task(task_id: str, request: YouTubeDownloadRequest, project_id: str):
    """处理YouTube下载任务"""
    try:
        # 更新任务状态为处理中
        download_tasks[task_id].status = "processing"
        download_tasks[task_id].progress = 10.0
        
        # 更新项目状态和进度
        await update_project_download_progress(project_id, 10.0, "正在获取视频信息...")
        
        # 使用yt-dlp下载视频
        import yt_dlp
        import asyncio
        from ...core.config import get_data_directory
        
        data_dir = get_data_directory()
        download_dir = data_dir / "temp"
        download_dir.mkdir(exist_ok=True)
        
        # 更新项目进度
        await update_project_download_progress(project_id, 30.0, "正在下载视频...")

        # 优先 cookies.txt；未配置时用请求中的 browser。Docker 内不再默认 chrome。
        cookiefile = resolve_youtube_cookiefile()
        browser = None if cookiefile else (request.browser.lower() if request.browser else None)
        if cookiefile:
            logger.info(f"YouTube 下载使用 cookiefile={cookiefile}")
        elif browser:
            logger.info(f"YouTube 下载使用 browser={browser}")
        else:
            logger.info("YouTube 下载未使用 Cookie（可能因反爬失败）")

        ydl_opts = _build_youtube_ydl_opts(
            browser,
            for_download=True,
            use_cookiefile=True,
            extra={
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["en", "zh-Hans", "zh", "en-US", "auto"],
                "subtitlesformat": "srt",
                "outtmpl": str(download_dir / "%(title)s.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": False,
            },
        )

        def download_sync(url, ydl_opts):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.download([url])

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, download_sync, request.url, ydl_opts)
        except Exception as download_err:
            err_msg = str(download_err)
            # 签名/格式失败时给出可操作提示
            if any(
                k in err_msg.lower()
                for k in ("signature", "n challenge", "format is not available", "only images")
            ):
                raise RuntimeError(
                    "YouTube 视频格式不可用（签名挑战求解失败）。"
                    "请确认已安装 yt-dlp[default]（含 yt-dlp-ejs），且本机 Node.js ≥ 22 在 PATH 中。"
                    f" 原始错误: {download_err}"
                ) from download_err
            raise
        
        # 查找下载的文件
        video_files = list(download_dir.glob("*.mp4"))
        subtitle_files = list(download_dir.glob("*.srt"))
        
        if not video_files:
            raise Exception("未找到下载的视频文件")
        
        video_path = str(video_files[0])
        subtitle_path = str(subtitle_files[0]) if subtitle_files else ""
        
        download_tasks[task_id].progress = 80.0
        
        # 平台字幕（轻量）；Whisper 交给 Celery，避免堵 API
        await update_project_download_progress(project_id, 60.0, "视频下载完成，正在整理文件...")
        if not subtitle_path:
            logger.info("未附带 SRT，尝试拉取 YouTube 平台字幕（Whisper 将在 Celery 中执行）")
            try:
                subtitle_path = await _try_youtube_subtitle_strategies(
                    request.url, download_dir, request.browser
                )
                if subtitle_path:
                    logger.info(f"平台字幕获取成功: {subtitle_path}")
            except Exception as e:
                logger.warning(f"平台字幕获取失败（将由 Celery Whisper 补全）: {e}")
                subtitle_path = ""
        
        logger.info(f"下载完成 - 视频文件: {video_path}, 字幕文件: {subtitle_path or '无（待 Celery Whisper）'}")
        
        # 更新项目信息（项目已在开始时创建）
        from ...services.project_service import ProjectService
        from ...core.database import SessionLocal
        
        db = SessionLocal()
        try:
            project_service = ProjectService(db)
            
            # 获取已创建的项目
            project = project_service.get(project_id)
            if not project:
                raise Exception(f"项目 {project_id} 不存在")
            
            # 更新项目信息
            project.description = f"从YouTube下载: {request.project_name}"
            
            # 更新项目设置
            if not project.processing_config:
                project.processing_config = {}
            
            project.processing_config.update({
                "youtube_info": {
                    "title": request.project_name,
                    "uploader": "YouTube",
                    "duration": 0,
                    "view_count": 0,
                    "like_count": 0
                },
                "subtitle_path": subtitle_path or None,
                "download_status": "completed",
                "download_progress": 100.0
            })
            
            # 移动文件到项目目录
            from ...core.path_utils import get_project_directory
            project_dir = get_project_directory(project_id)
            raw_dir = project_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            
            import shutil
            new_video_path = raw_dir / "input.mp4"
            new_subtitle_path = None
            
            if video_path:
                video_file_path = Path(video_path)
                if video_file_path.exists():
                    shutil.move(str(video_file_path), str(new_video_path))
                    logger.info(f"视频文件已移动到: {new_video_path}")
                    project.video_path = str(new_video_path)
            
            if subtitle_path:
                subtitle_file_path = Path(subtitle_path)
                if subtitle_file_path.exists():
                    new_subtitle_path = raw_dir / "input.srt"
                    shutil.move(str(subtitle_file_path), str(new_subtitle_path))
                    logger.info(f"字幕文件已移动到: {new_subtitle_path}")
                    project.processing_config["subtitle_path"] = str(new_subtitle_path)
            
            from ...schemas.project import ProjectStatus
            project.status = ProjectStatus.PENDING
            db.commit()
            
            await update_project_download_progress(
                project_id, 100.0, "下载完成，已提交后台生成字幕/处理"
            )
            
            download_tasks[task_id].status = "completed"
            download_tasks[task_id].progress = 100.0
            download_tasks[task_id].project_id = str(project.id)
            download_tasks[task_id].updated_at = datetime.now().isoformat()
            
            logger.info(f"YouTube下载任务完成: {task_id}, 项目ID: {project.id}")
            
            # Whisper + 流水线交给 Celery（与本地上传一致）
            try:
                from ...tasks.import_processing import process_import_task
                celery_task = process_import_task.delay(
                    str(project.id),
                    str(new_video_path),
                    str(new_subtitle_path) if new_subtitle_path and new_subtitle_path.exists() else None,
                )
                logger.info(
                    f"YouTube项目 {project.id} 已提交 Celery 导入处理: {celery_task.id}"
                )
            except Exception as e:
                logger.error(f"提交 Celery 导入任务失败: {e}")
            
        except Exception as e:
            logger.error(f"创建项目失败: {str(e)}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"处理下载任务失败: {str(e)}")
        err_msg = await _mark_youtube_download_failed(project_id, e)
        if task_id in download_tasks:
            download_tasks[task_id].status = "failed"
            download_tasks[task_id].error_message = err_msg
            download_tasks[task_id].progress = 0.0
            download_tasks[task_id].project_id = project_id
            download_tasks[task_id].updated_at = datetime.now().isoformat()


async def _try_youtube_subtitle_strategies(url: str, download_dir: Path, browser: Optional[str] = None) -> str:
    """尝试多种YouTube字幕获取策略"""
    strategies = [
        lambda: _try_download_with_different_formats(url, download_dir, browser),
        lambda: _try_download_with_different_langs(url, download_dir, browser),
        lambda: _try_extract_from_metadata(url, download_dir, browser)
    ]
    
    for strategy in strategies:
        try:
            subtitle_path = await strategy()
            if subtitle_path:
                logger.info(f"YouTube备用字幕策略成功")
                return subtitle_path
        except Exception as e:
            logger.warning(f"YouTube备用字幕策略失败: {e}")
            continue
    
    logger.warning("所有YouTube字幕获取策略都失败了")
    return ""


async def _try_download_with_different_formats(url: str, download_dir: Path, browser: Optional[str] = None) -> str:
    """尝试下载不同格式的字幕"""
    import asyncio
    logger.info("尝试下载不同格式的YouTube字幕...")
    
    formats = ['srt', 'vtt', 'json3']
    
    for fmt in formats:
        try:
            ydl_opts = _build_youtube_ydl_opts(
                browser,
                for_download=True,
                extra={
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitleslangs": ["en", "zh-Hans", "zh"],
                    "subtitlesformat": fmt,
                    "outtmpl": str(download_dir / f"subtitle_%(title)s.%(ext)s"),
                    "noplaylist": True,
                    "quiet": True,
                    # 字幕备用策略不需要真正下视频
                    "skip_download": True,
                },
            )
            
            def download_sync(url, ydl_opts):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.download([url])
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, download_sync, url, ydl_opts)
            
            # 查找下载的字幕文件
            subtitle_files = list(download_dir.glob(f"*.{fmt}"))
            if subtitle_files:
                subtitle_path = str(subtitle_files[0])
                
                # 如果是VTT格式，转换为SRT
                if fmt == 'vtt':
                    srt_path = subtitle_path.replace('.vtt', '.srt')
                    await _convert_vtt_to_srt(subtitle_path, srt_path)
                    return srt_path
                
                return subtitle_path
                
        except Exception as e:
            logger.debug(f"尝试格式 {fmt} 失败: {e}")
            continue
    
    return ""


async def _try_download_with_different_langs(url: str, download_dir: Path, browser: Optional[str] = None) -> str:
    """尝试下载不同语言的字幕"""
    import asyncio
    logger.info("尝试下载不同语言的YouTube字幕...")
    
    lang_combinations = [
        ['en', 'en-US'],      # 英文
        ['zh-Hans', 'zh'],    # 中文
        ['ja', 'ja-JP'],      # 日文
        ['ko', 'ko-KR'],      # 韩文
        ['auto']              # 自动检测
    ]
    
    for langs in lang_combinations:
        try:
            ydl_opts = _build_youtube_ydl_opts(
                browser,
                for_download=True,
                extra={
                    "writesubtitles": True,
                    "writeautomaticsub": True,
                    "subtitleslangs": langs,
                    "subtitlesformat": "srt",
                    "outtmpl": str(download_dir / f"lang_%(title)s.%(ext)s"),
                    "noplaylist": True,
                    "quiet": True,
                    "skip_download": True,
                },
            )
            
            def download_sync(url, ydl_opts):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.download([url])
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, download_sync, url, ydl_opts)
            
            # 查找下载的字幕文件
            subtitle_files = list(download_dir.glob("*.srt"))
            if subtitle_files:
                return str(subtitle_files[0])
                
        except Exception as e:
            logger.debug(f"尝试语言 {langs} 失败: {e}")
            continue
    
    return ""


async def _try_extract_from_metadata(url: str, download_dir: Path, browser: Optional[str] = None) -> str:
    """尝试从视频元数据中提取字幕信息"""
    import asyncio
    logger.info("尝试从YouTube视频元数据提取字幕信息...")
    
    try:
        ydl_opts = _build_youtube_ydl_opts(browser, for_download=False)
        
        def extract_info_sync(url, ydl_opts):
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        loop = asyncio.get_event_loop()
        info_dict = await loop.run_in_executor(None, extract_info_sync, url, ydl_opts)
        
        # 检查是否有字幕信息
        subtitles = info_dict.get('subtitles', {})
        auto_subtitles = info_dict.get('automatic_captions', {})
        
        if subtitles or auto_subtitles:
            logger.info(f"发现YouTube字幕信息: {list(subtitles.keys()) + list(auto_subtitles.keys())}")
            # 这里可以进一步处理字幕信息，但目前返回空字符串
            return ""
        
        return ""
        
    except Exception as e:
        logger.debug(f"提取YouTube视频元数据失败: {e}")
        return ""


async def _convert_vtt_to_srt(vtt_path: str, srt_path: str):
    """将VTT字幕文件转换为SRT格式"""
    try:
        with open(vtt_path, 'r', encoding='utf-8') as vtt_file:
            vtt_content = vtt_file.read()
        
        # 简单的VTT到SRT转换
        lines = vtt_content.split('\n')
        srt_lines = []
        subtitle_count = 1
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # 跳过VTT头部信息
            if line.startswith('WEBVTT') or line.startswith('NOTE') or not line:
                i += 1
                continue
            
            # 查找时间戳行
            if '-->' in line:
                # 转换时间格式 (VTT使用点，SRT使用逗号)
                time_line = line.replace('.', ',')
                srt_lines.append(str(subtitle_count))
                srt_lines.append(time_line)
                
                # 获取字幕文本
                i += 1
                subtitle_text = []
                while i < len(lines) and lines[i].strip():
                    subtitle_text.append(lines[i].strip())
                    i += 1
                
                srt_lines.extend(subtitle_text)
                srt_lines.append('')  # 空行分隔
                subtitle_count += 1
            
            i += 1
        
        # 写入SRT文件
        with open(srt_path, 'w', encoding='utf-8') as srt_file:
            srt_file.write('\n'.join(srt_lines))
            
        logger.info(f"VTT转SRT转换成功: {vtt_path} -> {srt_path}")
        
    except Exception as e:
        logger.error(f"VTT转SRT转换失败: {e}")
        raise
