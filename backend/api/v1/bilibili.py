"""
B站相关API路由
处理B站视频解析和下载功能
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Form, UploadFile, File
from pydantic import BaseModel
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from ...utils.bilibili_downloader import BilibiliDownloader, get_bilibili_video_info
from ...core.config import get_data_directory
import uuid
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# 存储下载任务的状态
download_tasks = {}

class BilibiliParseRequest(BaseModel):
    url: str
    browser: Optional[str] = None

class BilibiliDownloadRequest(BaseModel):
    url: str
    project_name: str
    video_category: Optional[str] = "default"
    browser: Optional[str] = None

class BilibiliVideoInfo(BaseModel):
    title: str
    description: str
    duration: int
    uploader: str
    upload_date: str
    view_count: int
    like_count: int
    thumbnail: str

class BilibiliDownloadTask(BaseModel):
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

@router.post("/parse")
async def parse_bilibili_video(
    url: str = Form(...),
    browser: Optional[str] = Form(None)
):
    """解析B站视频信息"""
    try:
        logger.info(f"开始解析B站视频: {url}")
        
        # 验证URL格式
        downloader = BilibiliDownloader(browser=browser)
        if not downloader.validate_bilibili_url(url):
            raise HTTPException(status_code=400, detail="无效的B站视频链接")
        
        # 获取真实的视频信息
        video_info = await downloader.get_video_info(url)
        
        logger.info(f"视频信息解析成功: {video_info.title}")
        
        return {
            "success": True,
            "video_info": {
                "title": video_info.title,
                "description": video_info.description,
                "duration": video_info.duration,
                "uploader": video_info.uploader,
                "upload_date": video_info.upload_date,
                "view_count": video_info.view_count,
                "like_count": 0,  # B站API可能不提供点赞数
                "thumbnail": video_info.thumbnail_url
            }
        }
        
    except Exception as e:
        logger.error(f"解析B站视频失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")

@router.post("/download")
async def create_bilibili_download_task(request: BilibiliDownloadRequest):
    """创建B站视频下载任务 - 立即创建项目"""
    try:
        logger.info(f"创建B站下载任务: {request.url}")
        
        # 先获取视频信息以获取缩略图
        from ...utils.bilibili_downloader import BilibiliDownloader
        downloader = BilibiliDownloader(browser=request.browser)
        video_info = await downloader.get_video_info(request.url)
        
        # 立即创建项目记录
        from ...core.database import SessionLocal
        from ...services.project_service import ProjectService
        from ...schemas.project import ProjectCreate, ProjectType, ProjectStatus
        
        db = SessionLocal()
        try:
            project_service = ProjectService(db)
            
            # 处理缩略图 - 直接使用解析出来的封面图
            thumbnail_data = None
            if video_info.thumbnail_url:
                try:
                    import requests
                    import base64
                    
                    # 下载缩略图
                    response = requests.get(video_info.thumbnail_url, timeout=10)
                    if response.status_code == 200:
                        # 转换为base64
                        thumbnail_base64 = base64.b64encode(response.content).decode('utf-8')
                        thumbnail_data = f"data:image/jpeg;base64,{thumbnail_base64}"
                        logger.info(f"B站缩略图获取成功: {video_info.title}")
                    else:
                        logger.warning(f"下载B站缩略图失败: {response.status_code}")
                except Exception as e:
                    logger.error(f"处理B站缩略图失败: {e}")
                    # 缩略图处理失败不影响主流程
            
            # 创建项目数据
            project_data = ProjectCreate(
                name=request.project_name,
                description=f"从B站下载: {video_info.title}",
                project_type=ProjectType(request.video_category),
                status=ProjectStatus.PENDING,  # 初始状态为等待中
                source_url=request.url,
                source_file=None,  # 暂时为空，下载完成后更新
                settings={
                    "download_status": "downloading",
                    "download_progress": 0.0,
                    "bilibili_info": {
                        "url": request.url,
                        "browser": request.browser,
                        "title": video_info.title,
                        "uploader": video_info.uploader,
                        "duration": video_info.duration,
                        "view_count": video_info.view_count,
                        "thumbnail_url": video_info.thumbnail_url
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
            task = BilibiliDownloadTask(
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
                f"bilibili_download_{task_id}", 
                process_download_task, 
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
        logger.error(f"创建下载任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")

@router.get("/tasks/{task_id}")
async def get_bilibili_task_status(task_id: str):
    """获取下载任务状态"""
    if task_id not in download_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    return download_tasks[task_id]

@router.get("/tasks")
async def get_all_bilibili_tasks():
    """获取所有下载任务"""
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

async def process_download_task(task_id: str, request: BilibiliDownloadRequest, project_id: str):
    """处理下载任务"""
    try:
        # 更新任务状态为处理中
        download_tasks[task_id].status = "processing"
        download_tasks[task_id].progress = 10.0
        
        # 更新项目状态和进度
        await update_project_download_progress(project_id, 10.0, "正在获取视频信息...")
        
        # 获取视频信息
        video_info = await get_bilibili_video_info(request.url, request.browser)
        download_tasks[task_id].progress = 30.0
        
        # 更新项目进度
        await update_project_download_progress(project_id, 30.0, "正在下载视频...")
        
        # 下载视频
        data_dir = get_data_directory()
        download_dir = data_dir / "temp"
        download_dir.mkdir(exist_ok=True)
        
        from ...utils.bilibili_downloader import download_bilibili_video
        download_result = await download_bilibili_video(
            request.url, 
            download_dir, 
            request.browser
        )
        
        video_path = download_result.get('video_path', '')
        subtitle_path = download_result.get('subtitle_path', '') or ''
        
        # Whisper 交给 Celery；API 只整理文件
        await update_project_download_progress(project_id, 60.0, "视频下载完成，正在整理文件...")
        
        download_tasks[task_id].progress = 80.0
        
        from ...services.project_service import ProjectService
        from ...core.database import SessionLocal
        
        db = SessionLocal()
        try:
            project_service = ProjectService(db)
            
            project = project_service.get(project_id)
            if not project:
                raise Exception(f"项目 {project_id} 不存在")
            
            project.description = f"从B站下载: {video_info.title}"
            
            if not project.processing_config:
                project.processing_config = {}
            
            project.processing_config.update({
                "bilibili_info": {
                    "title": video_info.title,
                    "uploader": video_info.uploader,
                    "duration": video_info.duration,
                    "view_count": video_info.view_count
                },
                "subtitle_path": subtitle_path if subtitle_path else None,
                "download_status": "completed",
                "download_progress": 100.0
            })
            
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
            
            if subtitle_path and subtitle_path.strip():
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
            
            logger.info(f"B站下载任务完成: {task_id}, 项目ID: {project.id}")
            
            try:
                from ...tasks.import_processing import process_import_task
                celery_task = process_import_task.delay(
                    str(project.id),
                    str(new_video_path),
                    str(new_subtitle_path) if new_subtitle_path and new_subtitle_path.exists() else None,
                )
                logger.info(f"B站项目 {project.id} 已提交 Celery 导入处理: {celery_task.id}")
            except Exception as e:
                logger.error(f"提交 Celery 导入任务失败: {e}")
            
        except Exception as e:
            logger.error(f"创建项目失败: {str(e)}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"处理下载任务失败: {str(e)}")
        err_msg = str(e)
        if task_id in download_tasks:
            download_tasks[task_id].status = "failed"
            download_tasks[task_id].error_message = err_msg
            download_tasks[task_id].progress = 0.0
            download_tasks[task_id].project_id = project_id
            download_tasks[task_id].updated_at = datetime.now().isoformat()
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
                        "download_message": err_msg,
                        "error_message": err_msg,
                    })
                    db.commit()
            finally:
                db.close()
        except Exception as mark_err:
            logger.error(f"标记B站项目下载失败状态时出错: {mark_err}")
