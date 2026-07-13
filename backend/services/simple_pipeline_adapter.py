"""
简化的流水线适配器 - 集成新的进度系统
"""

import logging
from typing import Dict, Any, Optional, Callable
from pathlib import Path

from backend.services.simple_progress import emit_progress, clear_progress
from backend.pipeline.step1_outline import run_step1_outline
from backend.pipeline.step2_timeline import run_step2_timeline
from backend.pipeline.step3_scoring import run_step3_scoring
from backend.pipeline.step4_title import run_step4_title
from backend.pipeline.step5_clustering import run_step5_clustering
from backend.pipeline.step6_video import run_step6_video

logger = logging.getLogger(__name__)


class SimplePipelineAdapter:
    """简化的流水线适配器，使用固定阶段进度系统"""
    
    def __init__(self, project_id: str, task_id: str):
        self.project_id = project_id
        self.task_id = task_id
        
    async def _generate_subtitle_automatically(self, video_path: str, metadata_dir: Path) -> Path:
        """
        自动生成字幕文件；成功后同步到 raw/input.srt，避免重复 Whisper。
        """
        try:
            logger.info(f"开始为视频 {video_path} 自动生成字幕")
            
            from backend.services.simple_progress import emit_progress
            emit_progress(self.project_id, "SUBTITLE", "正在使用AI生成字幕...", subpercent=25)
            
            try:
                from backend.utils.speech_recognizer import generate_subtitle_for_video
                import shutil
                
                video_file_path = Path(video_path)
                if not video_file_path.exists():
                    logger.error(f"视频文件不存在: {video_path}")
                    return None
                
                # 若 raw/input.srt 已存在，直接复用
                raw_srt = video_file_path.parent / "input.srt"
                if raw_srt.exists() and raw_srt.stat().st_size > 0:
                    logger.info(f"复用已有字幕: {raw_srt}")
                    emit_progress(self.project_id, "SUBTITLE", "使用已有字幕", subpercent=40)
                    return raw_srt
                
                from backend.core.shared_config import (
                    SPEECH_RECOGNITION_METHOD,
                    SPEECH_RECOGNITION_LANGUAGE,
                    SPEECH_RECOGNITION_MODEL,
                )
                method = (SPEECH_RECOGNITION_METHOD or "faster_whisper").strip().lower()
                language = SPEECH_RECOGNITION_LANGUAGE or "auto"
                if method == "sensevoice":
                    model = SPEECH_RECOGNITION_MODEL or "iic/SenseVoiceSmall"
                else:
                    model = SPEECH_RECOGNITION_MODEL or "base"
                logger.info(f"尝试使用 {method} 生成字幕 (model={model})")
                output_path = metadata_dir / f"{video_file_path.stem}.srt"
                srt_path = generate_subtitle_for_video(
                    video_file_path,
                    output_path=output_path,
                    method=method,
                    model=model,
                    language=language,
                )
                
                if srt_path and Path(srt_path).exists():
                    srt_path = Path(srt_path)
                    logger.info(f"字幕生成成功 ({method}): {srt_path}")
                    # 落到标准路径，供后续重试/二次启动直接使用
                    try:
                        if srt_path.resolve() != raw_srt.resolve():
                            shutil.copy2(srt_path, raw_srt)
                            logger.info(f"字幕已同步到: {raw_srt}")
                    except Exception as copy_err:
                        logger.warning(f"同步字幕到 raw/input.srt 失败: {copy_err}")
                    emit_progress(self.project_id, "SUBTITLE", "AI字幕生成完成", subpercent=40)
                    return raw_srt if raw_srt.exists() else srt_path
                else:
                    logger.warning(f"{method} 生成字幕失败")
                    
            except Exception as e:
                logger.warning(f"自动生成字幕失败: {e}")
            
            logger.error("Whisper ASR 失败")
            return None
            
        except Exception as e:
            logger.error(f"自动生成字幕过程中发生错误: {e}")
            return None
        
    async def process_project_sync(self, input_video_path: str, input_srt_path: str) -> Dict[str, Any]:
        """
        同步处理项目 - 使用简化的进度系统
        
        Args:
            input_video_path: 输入视频路径
            input_srt_path: 输入SRT路径
            
        Returns:
            处理结果
        """
        logger.info(f"开始处理项目: {self.project_id}")
        
        try:
            # 清除之前的进度数据
            clear_progress(self.project_id)
            
            # 创建必要的目录结构 - 使用正确的路径
            from backend.core.path_utils import get_project_directory
            project_dir = get_project_directory(self.project_id)
            metadata_dir = project_dir / "metadata"
            output_dir = project_dir / "output"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            # 项目内专属输出子目录
            clips_output_dir = output_dir / "clips"
            collections_output_dir = output_dir / "collections"
            clips_output_dir.mkdir(parents=True, exist_ok=True)
            collections_output_dir.mkdir(parents=True, exist_ok=True)
            
            # 阶段1: 素材准备
            emit_progress(self.project_id, "INGEST", "素材准备完成")
            
            # 阶段2: 字幕处理
            emit_progress(self.project_id, "SUBTITLE", "开始字幕处理")
            
            # Step 1: 大纲提取 — 优先 raw/input.srt，避免重复 Whisper
            logger.info("执行Step 1: 大纲提取")
            project_dir = get_project_directory(self.project_id)
            raw_srt = project_dir / "raw" / "input.srt"
            srt_candidate = None
            if raw_srt.exists() and raw_srt.stat().st_size > 0:
                srt_candidate = raw_srt
            elif input_srt_path and Path(input_srt_path).exists():
                srt_candidate = Path(input_srt_path)

            if srt_candidate:
                logger.info(f"使用现有SRT文件: {srt_candidate}")
                outlines = run_step1_outline(srt_candidate, metadata_dir=metadata_dir)
            else:
                logger.warning("没有SRT文件，尝试自动生成字幕")
                srt_path = await self._generate_subtitle_automatically(input_video_path, metadata_dir)
                if srt_path and Path(srt_path).exists():
                    logger.info(f"自动生成字幕成功: {srt_path}")
                    outlines = run_step1_outline(Path(srt_path), metadata_dir=metadata_dir)
                else:
                    logger.warning("自动生成字幕失败，创建空大纲")
                    outlines = []
                    outline_file = metadata_dir / "step1_outline.json"
                    import json
                    with open(outline_file, 'w', encoding='utf-8') as f:
                        json.dump(outlines, f, ensure_ascii=False, indent=2)
            emit_progress(self.project_id, "SUBTITLE", "字幕处理完成", subpercent=50)
            
            # 阶段3: 内容分析
            emit_progress(self.project_id, "ANALYZE", "开始内容分析")
            
            # Step 2: 时间线提取
            logger.info("执行Step 2: 时间线提取")
            if outlines:  # 只有当有大纲时才执行后续步骤
                timeline_data = run_step2_timeline(
                    metadata_dir / "step1_outline.json",
                    metadata_dir=metadata_dir
                )
                emit_progress(self.project_id, "ANALYZE", "时间线提取完成", subpercent=50)
                
                # Step 3: 内容评分
                logger.info("执行Step 3: 内容评分")
                scored_clips = run_step3_scoring(
                    metadata_dir / "step2_timeline.json",
                    metadata_dir=metadata_dir
                )
                emit_progress(self.project_id, "ANALYZE", "内容分析完成", subpercent=100)
            else:
                logger.warning("没有大纲数据，跳过时间线提取和内容评分")
                # 创建空的时间线和评分文件
                timeline_file = metadata_dir / "step2_timeline.json"
                scored_file = metadata_dir / "step3_high_score_clips.json"
                import json
                with open(timeline_file, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                with open(scored_file, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                # 初始化空变量
                timeline_data = []
                scored_clips = []
                emit_progress(self.project_id, "ANALYZE", "内容分析完成", subpercent=100)
            
            # 阶段4: 片段定位
            emit_progress(self.project_id, "HIGHLIGHT", "开始片段定位")
            
            # Step 4: 标题生成
            logger.info("执行Step 4: 标题生成")
            if outlines:  # 只有当有大纲时才执行后续步骤
                titled_clips = run_step4_title(
                    metadata_dir / "step3_high_score_clips.json",
                    metadata_dir=str(metadata_dir)
                )
                emit_progress(self.project_id, "HIGHLIGHT", "标题生成完成", subpercent=40)
                
                # Step 5: 主题聚类
                logger.info("执行Step 5: 主题聚类")
                collections = run_step5_clustering(
                    metadata_dir / "step4_titles.json",
                    metadata_dir=str(metadata_dir)
                )
                emit_progress(self.project_id, "HIGHLIGHT", "片段定位完成", subpercent=100)
                
                # 阶段5: 视频导出
                emit_progress(self.project_id, "EXPORT", "开始视频导出")
                
                # Step 6: 视频切割
                logger.info("执行Step 6: 视频切割")
                video_result = run_step6_video(
                    metadata_dir / "step4_titles.json",
                    metadata_dir / "step5_collections.json",
                    input_video_path,
                    output_dir=output_dir,
                    clips_dir=str(clips_output_dir),
                    collections_dir=str(collections_output_dir),
                    metadata_dir=str(metadata_dir)
                )
            else:
                logger.warning("没有大纲数据，跳过标题生成、主题聚类和视频切割")
                # 创建空的标题和合集文件
                titles_file = metadata_dir / "step4_titles.json"
                collections_file = metadata_dir / "step5_collections.json"
                import json
                with open(titles_file, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                with open(collections_file, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
                # 初始化空变量
                titled_clips = []
                collections = []
                emit_progress(self.project_id, "HIGHLIGHT", "片段定位完成", subpercent=100)
                emit_progress(self.project_id, "EXPORT", "开始视频导出")
                video_result = {"status": "skipped", "message": "没有内容可处理"}
            emit_progress(self.project_id, "EXPORT", "视频导出完成", subpercent=100)
            
            # 阶段6: 处理完成
            emit_progress(self.project_id, "DONE", "处理完成")
            
            # 自动同步数据到数据库
            try:
                from backend.services.data_sync_service import DataSyncService
                from backend.core.database import SessionLocal
                
                db = SessionLocal()
                try:
                    sync_service = DataSyncService(db)
                    sync_result = sync_service.sync_project_from_filesystem(self.project_id, project_dir)
                    if sync_result.get("success"):
                        logger.info(f"项目 {self.project_id} 数据同步成功: {sync_result}")
                    else:
                        logger.error(f"项目 {self.project_id} 数据同步失败: {sync_result}")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"数据同步失败: {e}")
            
            logger.info(f"项目处理完成: {self.project_id}")
            return {
                "status": "succeeded",
                "project_id": self.project_id,
                "task_id": self.task_id,
                "result": {
                    "outlines": outlines,
                    "timeline": timeline_data,
                    "scored_clips": scored_clips,
                    "titled_clips": titled_clips,
                    "collections": collections,
                    "video_result": video_result
                }
            }
            
        except Exception as e:
            error_msg = f"流水线处理失败: {str(e)}"
            logger.error(error_msg)
            
            # 发送失败状态
            emit_progress(self.project_id, "DONE", f"处理失败: {error_msg}")
            
            return {
                "status": "failed",
                "project_id": self.project_id,
                "task_id": self.task_id,
                "error": error_msg
            }


def create_simple_pipeline_adapter(project_id: str, task_id: str) -> SimplePipelineAdapter:
    """创建简化的流水线适配器实例"""
    return SimplePipelineAdapter(project_id, task_id)
