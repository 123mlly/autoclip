"""
任务提交工具
独立的工具函数，避免循环导入问题
"""

import logging
import os
from typing import Dict, Any, Optional

from ..core.celery_app import celery_app

logger = logging.getLogger(__name__)

PIPELINE_LOCK_PREFIX = "autoclip:pipeline:lock:"
PIPELINE_LOCK_TTL_SECONDS = 7200  # 2h，防止 worker 异常退出后死锁


def _redis_client():
    import redis

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(redis_url, decode_responses=True)


def pipeline_lock_key(project_id: str) -> str:
    return f"{PIPELINE_LOCK_PREFIX}{project_id}"


def acquire_pipeline_lock(project_id: str, owner: str = "1") -> bool:
    """
    尝试获取项目流水线锁。同一项目同时只允许一个 pipeline。
    返回 True 表示拿到锁。
    """
    try:
        client = _redis_client()
        ok = client.set(
            pipeline_lock_key(project_id),
            owner,
            nx=True,
            ex=PIPELINE_LOCK_TTL_SECONDS,
        )
        if ok:
            logger.info(f"已获取流水线锁: {project_id} (owner={owner})")
        else:
            logger.warning(f"流水线锁已被占用，跳过提交: {project_id}")
        return bool(ok)
    except Exception as e:
        # Redis 不可用时不阻塞本地开发；记录警告后放行
        logger.warning(f"获取流水线锁失败（放行）: {project_id}, {e}")
        return True


def release_pipeline_lock(project_id: str) -> None:
    """释放项目流水线锁。"""
    try:
        client = _redis_client()
        client.delete(pipeline_lock_key(project_id))
        logger.info(f"已释放流水线锁: {project_id}")
    except Exception as e:
        logger.warning(f"释放流水线锁失败: {project_id}, {e}")


def refresh_pipeline_lock(project_id: str, owner: Optional[str] = None) -> None:
    """延长锁 TTL（长任务如 Whisper 期间保活）。"""
    try:
        client = _redis_client()
        key = pipeline_lock_key(project_id)
        if owner is not None:
            client.set(key, owner, ex=PIPELINE_LOCK_TTL_SECONDS)
        else:
            client.expire(key, PIPELINE_LOCK_TTL_SECONDS)
    except Exception as e:
        logger.debug(f"刷新流水线锁失败: {project_id}, {e}")


def submit_video_pipeline_task(
    project_id: str, input_video_path: str, input_srt_path: Optional[str]
) -> Dict[str, Any]:
    """
    提交视频流水线任务（带项目级去重锁）
    """
    try:
        logger.info(f"提交视频流水线任务: {project_id}")

        if not acquire_pipeline_lock(project_id, owner="queued"):
            return {
                "success": False,
                "skipped": True,
                "error": "project already processing",
                "message": "该项目已有流水线任务在队列或执行中",
            }

        logger.info("准备提交任务到队列...")
        logger.info("任务名称: backend.tasks.processing.process_video_pipeline")
        logger.info(f"任务参数: {[project_id, input_video_path, input_srt_path]}")

        try:
            celery_task = celery_app.send_task(
                "backend.tasks.processing.process_video_pipeline",
                args=[project_id, input_video_path, input_srt_path],
            )
            refresh_pipeline_lock(project_id, owner=celery_task.id)
            logger.info(f"视频流水线任务已提交: {celery_task.id}")
        except Exception as e:
            release_pipeline_lock(project_id)
            logger.error(f"任务提交过程中出现异常: {e}")
            raise

        try:
            import redis

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            r = redis.Redis.from_url(redis_url)
            queue_length = r.llen("processing")
            logger.info(f"Redis队列长度: {queue_length}")
        except Exception as e:
            logger.warning(f"读取Redis队列长度失败（可忽略）: {e}")

        return {
            "success": True,
            "task_id": celery_task.id,
            "status": "PENDING",
            "message": "视频流水线任务已提交",
        }

    except Exception as e:
        logger.error(f"提交视频流水线任务失败: {project_id}, 错误: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "任务提交失败",
        }


def submit_single_step_task(
    project_id: str, step: str, config: Dict[str, Any]
) -> Dict[str, Any]:
    """提交单个步骤任务"""
    try:
        logger.info(f"提交单个步骤任务: {project_id}, {step}")

        celery_task = celery_app.send_task(
            "tasks.processing.process_single_step",
            args=[project_id, step, config],
        )

        logger.info(f"单个步骤任务已提交: {celery_task.id}")

        return {
            "success": True,
            "task_id": celery_task.id,
            "step": step,
            "status": "PENDING",
            "message": f"步骤 {step} 任务已提交",
        }

    except Exception as e:
        logger.error(f"提交单个步骤任务失败: {project_id}, {step}, 错误: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "任务提交失败",
        }
