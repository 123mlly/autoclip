"""
导入后处理任务（本地上传 / 链接下载共用）
在 Celery worker 中：缩略图 → Whisper 字幕 → 提交流水线
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

from backend.core.celery_app import celery_app
from backend.core.database import get_db
from backend.services.project_service import ProjectService
from backend.utils.thumbnail_generator import generate_project_thumbnail
from backend.utils.task_submission_utils import submit_video_pipeline_task

logger = logging.getLogger(__name__)


def _ensure_raw_srt(project_id: str, video_path: Path, srt_path: Path) -> Path:
    """确保字幕落在 raw/input.srt，便于流水线复用。"""
    raw_srt = video_path.parent / "input.srt"
    try:
        if srt_path.resolve() != raw_srt.resolve():
            shutil.copy2(srt_path, raw_srt)
            logger.info(f"项目 {project_id} 字幕已同步到: {raw_srt}")
        return raw_srt if raw_srt.exists() else srt_path
    except Exception as e:
        logger.warning(f"同步字幕到 raw/input.srt 失败: {e}")
        return srt_path


@celery_app.task(bind=True, name="backend.tasks.import_processing.process_import_task")
def process_import_task(
    self, project_id: str, video_path: str, srt_file_path: Optional[str] = None
):
    """
    处理导入后的异步任务：字幕生成、缩略图、启动流水线。
    """
    db = None
    try:
        logger.info(f"开始处理导入任务: {project_id}")

        db = next(get_db())
        project_service = ProjectService(db)

        self.update_state(state="PROGRESS", meta={"progress": 10, "message": "开始处理..."})

        video_file = Path(video_path)
        if not video_file.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 1. 缩略图
        logger.info(f"检查项目 {project_id} 缩略图...")
        self.update_state(state="PROGRESS", meta={"progress": 20, "message": "检查缩略图..."})

        project = project_service.get(project_id)
        if project and not project.thumbnail:
            logger.info(f"项目 {project_id} 没有缩略图，开始生成...")
            self.update_state(state="PROGRESS", meta={"progress": 25, "message": "生成缩略图..."})
            try:
                thumbnail_data = generate_project_thumbnail(project_id, video_file)
                if thumbnail_data:
                    project.thumbnail = thumbnail_data
                    db.commit()
                    logger.info(f"项目 {project_id} 缩略图生成并保存成功")
                else:
                    logger.warning(f"项目 {project_id} 缩略图生成失败")
            except Exception as e:
                logger.error(f"生成项目缩略图时发生错误: {e}")
        else:
            logger.info(f"项目 {project_id} 已有缩略图，跳过生成")

        # 2. 字幕：已有则用；否则 Whisper（在 celery-worker）
        srt_path: Optional[str] = srt_file_path
        raw_srt = video_file.parent / "input.srt"
        if srt_path and Path(srt_path).exists():
            srt_path = str(_ensure_raw_srt(project_id, video_file, Path(srt_path)))
        elif raw_srt.exists() and raw_srt.stat().st_size > 0:
            srt_path = str(raw_srt)
            logger.info(f"复用已有字幕: {srt_path}")
        else:
            logger.info(f"开始为项目 {project_id} 生成字幕（Celery Whisper）...")
            self.update_state(state="PROGRESS", meta={"progress": 40, "message": "生成字幕..."})

            try:
                from backend.utils.speech_recognizer import generate_subtitle_for_video

                project = project_service.get(project_id)
                video_category = "knowledge"
                if project and project.processing_config:
                    video_category = project.processing_config.get("video_category", "knowledge")

                # 供首页卡片展示「生成字幕中」，避免一直显示「导入中」
                if project:
                    if not project.processing_config:
                        project.processing_config = {}
                    project.processing_config.update({
                        "download_status": "preparing",
                        "download_message": "正在生成字幕...",
                        "download_progress": 100.0,
                    })
                    db.commit()

                model = "base"
                if video_category in ["business", "knowledge"]:
                    model = "small"
                elif video_category == "speech":
                    model = "medium"

                logger.info(f"使用Whisper生成字幕 - 语言: auto, 模型: {model}")

                output_path = video_file.parent / "input.srt"
                generated_subtitle = generate_subtitle_for_video(
                    video_file,
                    output_path=output_path,
                    language="auto",
                    model=model,
                    method="whisper_local",
                )
                srt_path = str(_ensure_raw_srt(project_id, video_file, Path(generated_subtitle)))
                logger.info(f"Whisper字幕生成成功: {srt_path}")

                if project:
                    if not project.processing_config:
                        project.processing_config = {}
                    project.processing_config["subtitle_path"] = srt_path
                    project.processing_config["download_message"] = "字幕已生成，准备处理"
                    db.commit()

            except Exception as e:
                logger.error(f"Whisper字幕生成失败: {str(e)}")
                srt_path = None

        # 3. 启动流水线
        logger.info(f"更新项目 {project_id} 状态为处理中...")
        self.update_state(state="PROGRESS", meta={"progress": 80, "message": "启动处理流程..."})

        if not srt_path or not Path(srt_path).exists():
            logger.error(f"字幕文件不存在: {srt_path}")
            project_service.update_project_status(project_id, "failed")
            raise FileNotFoundError(f"字幕文件不存在: {srt_path}")

        project_service.update_project_status(project_id, "processing")

        task_result = submit_video_pipeline_task(
            project_id=project_id,
            input_video_path=str(video_file),
            input_srt_path=srt_path,
        )

        if task_result.get("skipped"):
            logger.warning(f"项目 {project_id} 流水线已在运行，跳过重复提交: {task_result}")
            self.update_state(
                state="PROGRESS",
                meta={"progress": 100, "message": "流水线已在运行"},
            )
        elif task_result.get("success"):
            logger.info(
                f"项目 {project_id} 处理任务已启动，Celery任务ID: {task_result['task_id']}"
            )
            self.update_state(
                state="PROGRESS", meta={"progress": 100, "message": "处理流程已启动"}
            )
        else:
            logger.error(f"Celery任务提交失败: {task_result.get('error')}")
            project_service.update_project_status(project_id, "failed")
            raise RuntimeError(task_result.get("error") or "提交流水线失败")

        logger.info(f"导入任务完成: {project_id}")
        return {
            "status": "completed",
            "project_id": project_id,
            "message": "导入处理完成",
        }

    except Exception as e:
        logger.error(f"导入任务失败: {project_id}, 错误: {e}")
        try:
            fail_db = next(get_db())
            ProjectService(fail_db).update_project_status(project_id, "failed")
            fail_db.close()
        except Exception:
            pass
        raise
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
