"""
视频缩略图生成工具 - 稳定版
针对 Docker/WSL2 环境优化，修复了渐进式 JPEG 导致的解码崩溃及 Redis 断连问题
"""
import subprocess
import logging
from pathlib import Path
from typing import Optional
import base64
import json

logger = logging.getLogger(__name__)

class ThumbnailGenerator:
    """视频缩略图生成器"""

    def __init__(self):
        # 移除了 pil 相关导入，完全依赖 ffmpeg 处理以减少内存占用
        self.supported_formats = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv']

    def generate_thumbnail(self, video_path: Path, output_path: Optional[Path] = None,
                          time_offset: Optional[float] = None, width: int = 320, height: int = 180) -> Optional[Path]:
        """
        生成视频缩略图 - 使用稳定截图策略
        """
        try:
            video_path = Path(video_path)
            if not video_path.exists():
                logger.error(f"视频文件不存在: {video_path}")
                return None

            if video_path.suffix.lower() not in self.supported_formats:
                logger.error(f"不支持的视频格式: {video_path.suffix}")
                return None

            if output_path is None:
                output_path = video_path.parent / f"{video_path.stem}_thumbnail.jpg"

            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 智能选择时间点 (已在下方函数中屏蔽了不稳定的封面提取)
            if time_offset is None or time_offset == -1.0:
                time_offset = self._get_optimal_thumbnail_time(video_path)
            
            # 修正 time_offset，如果是 -1.0 说明提取封面失败或被禁用，强制设为 1.0 秒
            if time_offset < 0:
                time_offset = 1.0

            # 核心命令：直接从视频源截帧
            # 添加了 -threads 1 和 具体的滤镜以确保输出标准的 JPEG
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(time_offset),
                '-i', str(video_path),
                '-vframes', '1',
                '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black',
                '-q:v', '2',
                '-threads', '1',
                str(output_path)
            ]

            logger.info(f"正在执行 FFmpeg 截图: {video_path.name} at {time_offset}s")
            # 限制超时时间，防止进程僵死
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

            if result.returncode == 0:
                logger.info(f"缩略图生成成功: {output_path.name}")
                return output_path
            else:
                # 关键修复：只保留最后 200 字符，防止冲垮 Redis
                err_msg = result.stderr[-200:].strip() if result.stderr else "FFmpeg 未返回具体错误"
                logger.error(f"FFmpeg 报错 (截断后): {err_msg}")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"缩略图生成超时: {video_path.name}")
            return None
        except Exception as e:
            logger.error(f"缩略图生成异常: {str(e)}")
            return None

    def _get_optimal_thumbnail_time(self, video_path: Path) -> float:
        """
        智能选择最佳的缩略图时间点
        """
        try:
            # 【策略变更】不再尝试 _extract_video_cover，因为它在处理嵌入式 MJPEG 时极不稳定
            # 直接通过 ffprobe 获取时长并计算截图位置
            video_info = self.get_video_info(video_path)
            if not video_info:
                return 1.0

            duration = float(video_info.get('format', {}).get('duration', 0))
            if duration <= 0:
                return 1.0

            if duration < 30:
                optimal_time = duration * 0.5
            elif duration < 300:
                optimal_time = duration * 0.1
            else:
                optimal_time = duration * 0.05

            return max(1.0, min(optimal_time, duration - 1))

        except Exception as e:
            logger.debug(f"计算最佳时间点失败: {e}")
            return 1.0

    def generate_thumbnail_base64(self, video_path: Path, time_offset: Optional[float] = None,
                                 width: int = 320, height: int = 180) -> Optional[str]:
        """
        生成缩略图并返回base64编码
        """
        temp_path = video_path.parent / f"temp_{video_path.stem}.jpg"
        try:
            thumbnail_path = self.generate_thumbnail(video_path, temp_path, time_offset, width, height)

            if thumbnail_path and thumbnail_path.exists():
                with open(thumbnail_path, 'rb') as f:
                    image_data = f.read()
                    base64_data = base64.b64encode(image_data).decode('utf-8')
                
                # 成功读取后立即清理
                if temp_path.exists():
                    temp_path.unlink()
                    
                return f"data:image/jpeg;base64,{base64_data}"
            return None

        except Exception as e:
            logger.error(f"Base64 转换失败: {e}")
            return None
        finally:
            if temp_path.exists():
                try: temp_path.unlink()
                except: pass

    def get_video_info(self, video_path: Path) -> Optional[dict]:
        """获取视频信息"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return json.loads(result.stdout)
            return None
        except:
            return None

# 便捷函数
def generate_project_thumbnail(project_id: str, video_path: Path) -> Optional[str]:
    generator = ThumbnailGenerator()
    return generator.generate_thumbnail_base64(Path(video_path))
