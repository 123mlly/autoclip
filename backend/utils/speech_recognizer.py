"""
语音识别工具 - 支持多种语音识别服务
支持本地Whisper、OpenAI API、Azure Speech Services等多种语音识别服务
"""
import logging
import subprocess
import json
import os
import asyncio
from typing import Optional, List, Dict, Any, Union
from pathlib import Path
from enum import Enum
import requests
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# bcut-asr 已停用：统一使用本地 Whisper
BCUT_ASR_AVAILABLE = False


class SpeechRecognitionMethod(str, Enum):
    """语音识别方法枚举"""
    BCUT_ASR = "bcut_asr"  # 已停用，保留枚举值兼容旧配置
    WHISPER_LOCAL = "whisper_local"
    OPENAI_API = "openai_api"
    AZURE_SPEECH = "azure_speech"
    GOOGLE_SPEECH = "google_speech"
    ALIYUN_SPEECH = "aliyun_speech"


class LanguageCode(str, Enum):
    """支持的语言代码"""
    # 中文
    CHINESE_SIMPLIFIED = "zh"
    CHINESE_TRADITIONAL = "zh-TW"
    # 英文
    ENGLISH = "en"
    ENGLISH_US = "en-US"
    ENGLISH_UK = "en-GB"
    # 日文
    JAPANESE = "ja"
    # 韩文
    KOREAN = "ko"
    # 法文
    FRENCH = "fr"
    # 德文
    GERMAN = "de"
    # 西班牙文
    SPANISH = "es"
    # 俄文
    RUSSIAN = "ru"
    # 阿拉伯文
    ARABIC = "ar"
    # 葡萄牙文
    PORTUGUESE = "pt"
    # 意大利文
    ITALIAN = "it"
    # 自动检测
    AUTO = "auto"


@dataclass
class SpeechRecognitionConfig:
    """语音识别配置"""
    method: SpeechRecognitionMethod = SpeechRecognitionMethod.WHISPER_LOCAL
    language: LanguageCode = LanguageCode.AUTO
    model: str = "base"  # Whisper模型大小
    timeout: int = 0  # 超时时间（秒），0表示无限制
    output_format: str = "srt"  # 输出格式
    enable_timestamps: bool = True  # 是否启用时间戳
    enable_punctuation: bool = True  # 是否启用标点符号
    enable_speaker_diarization: bool = False  # 是否启用说话人分离
    enable_fallback: bool = False  # 已固定使用 Whisper，默认关闭回退
    fallback_method: SpeechRecognitionMethod = SpeechRecognitionMethod.WHISPER_LOCAL  # 回退方法
    
    def __post_init__(self):
        """验证配置参数"""
        # 验证方法
        if not isinstance(self.method, SpeechRecognitionMethod):
            try:
                self.method = SpeechRecognitionMethod(self.method)
            except ValueError:
                raise ValueError(f"不支持的语音识别方法: {self.method}")
        
        # 验证语言
        if not isinstance(self.language, LanguageCode):
            try:
                self.language = LanguageCode(self.language)
            except ValueError:
                raise ValueError(f"不支持的语言代码: {self.language}")
        
        # 验证模型
        valid_models = ["tiny", "base", "small", "medium", "large"]
        if self.model not in valid_models:
            raise ValueError(f"不支持的Whisper模型: {self.model}")
        
        # 验证超时时间
        if self.timeout < 0:
            raise ValueError("超时时间不能为负数")
        
        # 验证输出格式
        valid_formats = ["srt", "vtt", "txt", "json"]
        if self.output_format not in valid_formats:
            raise ValueError(f"不支持的输出格式: {self.output_format}")


class SpeechRecognitionError(Exception):
    """语音识别错误"""
    pass


class SpeechRecognizer:
    """语音识别器，支持多种语音识别服务"""
    
    def __init__(self, config: Optional[SpeechRecognitionConfig] = None):
        self.config = config or SpeechRecognitionConfig()
        self.available_methods = self._check_available_methods()
    
    def _check_available_methods(self) -> Dict[SpeechRecognitionMethod, bool]:
        """检查可用的语音识别方法"""
        methods = {}
        
        # bcut-asr 已停用
        methods[SpeechRecognitionMethod.BCUT_ASR] = False
        
        # 检查本地Whisper
        methods[SpeechRecognitionMethod.WHISPER_LOCAL] = self._check_whisper_availability()
        
        # 检查OpenAI API
        methods[SpeechRecognitionMethod.OPENAI_API] = self._check_openai_availability()
        
        # 检查Azure Speech Services
        methods[SpeechRecognitionMethod.AZURE_SPEECH] = self._check_azure_speech_availability()
        
        # 检查Google Speech-to-Text
        methods[SpeechRecognitionMethod.GOOGLE_SPEECH] = self._check_google_speech_availability()
        
        # 检查阿里云语音识别
        methods[SpeechRecognitionMethod.ALIYUN_SPEECH] = self._check_aliyun_speech_availability()
        
        return methods
    
    def _check_bcut_asr_availability(self) -> bool:
        """bcut-asr 已停用"""
        return False
    
    def _check_whisper_availability(self) -> bool:
        """检查本地Whisper是否可用（CLI 或 Python 包）"""
        import shutil
        import sys

        # 1) whisper 可执行文件
        whisper_bin = shutil.which("whisper")
        if whisper_bin:
            try:
                result = subprocess.run(
                    [whisper_bin, "--help"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, OSError):
                pass

        # 2) python -m whisper
        try:
            result = subprocess.run(
                [sys.executable, "-m", "whisper", "--help"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass

        # 3) import whisper 包
        try:
            import whisper  # noqa: F401
            return True
        except ImportError:
            pass

        logger.warning("本地Whisper未安装或不可用")
        return False
    
    def _check_openai_availability(self) -> bool:
        """检查OpenAI API是否可用"""
        api_key = os.getenv("OPENAI_API_KEY")
        return api_key is not None and len(api_key.strip()) > 0
    
    def _check_azure_speech_availability(self) -> bool:
        """检查Azure Speech Services是否可用"""
        api_key = os.getenv("AZURE_SPEECH_KEY")
        region = os.getenv("AZURE_SPEECH_REGION")
        return api_key is not None and region is not None
    
    def _check_google_speech_availability(self) -> bool:
        """检查Google Speech-to-Text是否可用"""
        # 检查Google Cloud凭证文件
        cred_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_file and Path(cred_file).exists():
            return True
        
        # 检查API密钥
        api_key = os.getenv("GOOGLE_SPEECH_API_KEY")
        return api_key is not None
    
    def _check_aliyun_speech_availability(self) -> bool:
        """检查阿里云语音识别是否可用"""
        access_key = os.getenv("ALIYUN_ACCESS_KEY_ID")
        secret_key = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
        app_key = os.getenv("ALIYUN_SPEECH_APP_KEY")
        return access_key is not None and secret_key is not None and app_key is not None
    
    def _extract_audio_from_video(self, video_path: Path, output_dir: Path) -> Path:
        """
        从视频文件中提取音频
        
        Args:
            video_path: 视频文件路径
            output_dir: 输出目录
            
        Returns:
            提取的音频文件路径
        """
        try:
            # 检查ffmpeg是否可用
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                raise SpeechRecognitionError("ffmpeg不可用，请安装ffmpeg")
            
            # 生成音频文件路径
            audio_filename = f"{video_path.stem}_audio.wav"
            audio_path = output_dir / audio_filename
            
            # 如果音频文件已存在，直接返回
            if audio_path.exists():
                logger.info(f"音频文件已存在: {audio_path}")
                return audio_path
            
            logger.info(f"正在从视频提取音频: {video_path} -> {audio_path}")
            
            # 使用ffmpeg提取音频
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-vn',  # 不处理视频流
                '-acodec', 'pcm_s16le',  # 使用PCM 16位编码
                '-ar', '16000',  # 采样率16kHz
                '-ac', '1',  # 单声道
                '-y',  # 覆盖输出文件
                str(audio_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise SpeechRecognitionError(f"音频提取失败: {result.stderr}")
            
            if not audio_path.exists():
                raise SpeechRecognitionError("音频提取失败，输出文件不存在")
            
            logger.info(f"音频提取成功: {audio_path}")
            return audio_path
            
        except subprocess.TimeoutExpired:
            raise SpeechRecognitionError("音频提取超时")
        except Exception as e:
            raise SpeechRecognitionError(f"音频提取失败: {e}")
    
    def generate_subtitle(self, video_path: Path, output_path: Optional[Path] = None, 
                         config: Optional[SpeechRecognitionConfig] = None) -> Path:
        """
        生成字幕文件
        
        Args:
            video_path: 视频文件路径
            output_path: 输出字幕文件路径
            config: 语音识别配置
            
        Returns:
            生成的字幕文件路径
            
        Raises:
            SpeechRecognitionError: 语音识别失败
        """
        if not video_path.exists():
            raise SpeechRecognitionError(f"视频文件不存在: {video_path}")
        
        # 使用传入的配置或默认配置
        config = config or self.config
        
        # 确定输出路径
        if output_path is None:
            output_path = video_path.parent / f"{video_path.stem}.{config.output_format}"
        
        # 根据配置的方法选择识别服务，支持回退机制
        try:
            if config.method == SpeechRecognitionMethod.BCUT_ASR:
                return self._generate_subtitle_bcut_asr(video_path, output_path, config)
            elif config.method == SpeechRecognitionMethod.WHISPER_LOCAL:
                return self._generate_subtitle_whisper_local(video_path, output_path, config)
            elif config.method == SpeechRecognitionMethod.OPENAI_API:
                return self._generate_subtitle_openai_api(video_path, output_path, config)
            elif config.method == SpeechRecognitionMethod.AZURE_SPEECH:
                return self._generate_subtitle_azure_speech(video_path, output_path, config)
            elif config.method == SpeechRecognitionMethod.GOOGLE_SPEECH:
                return self._generate_subtitle_google_speech(video_path, output_path, config)
            elif config.method == SpeechRecognitionMethod.ALIYUN_SPEECH:
                return self._generate_subtitle_aliyun_speech(video_path, output_path, config)
            else:
                raise SpeechRecognitionError(f"不支持的语音识别方法: {config.method}")
        except SpeechRecognitionError as e:
            # 如果启用了回退机制且当前方法不是回退方法，则尝试回退
            if (config.enable_fallback and 
                config.method != config.fallback_method and 
                self.available_methods.get(config.fallback_method, False)):
                
                logger.warning(f"主方法 {config.method} 失败: {e}")
                logger.info(f"尝试回退到 {config.fallback_method}")
                
                # 创建回退配置
                fallback_config = SpeechRecognitionConfig(
                    method=config.fallback_method,
                    language=config.language,
                    model=config.model,
                    timeout=config.timeout,
                    output_format=config.output_format,
                    enable_timestamps=config.enable_timestamps,
                    enable_punctuation=config.enable_punctuation,
                    enable_speaker_diarization=config.enable_speaker_diarization,
                    enable_fallback=False  # 避免无限回退
                )
                
                return self.generate_subtitle(video_path, output_path, fallback_config)
            else:
                raise
    
    def _generate_subtitle_bcut_asr(self, video_path: Path, output_path: Path, 
                                   config: SpeechRecognitionConfig) -> Path:
        """bcut-asr 已停用"""
        raise SpeechRecognitionError(
            "bcut-asr 已停用，请使用本地 Whisper（method=whisper_local）"
        )
    
    def _whisper_command_prefix(self) -> List[str]:
        """返回可用的 whisper 启动命令前缀"""
        import shutil
        import sys

        whisper_bin = shutil.which("whisper")
        if whisper_bin:
            return [whisper_bin]
        return [sys.executable, "-m", "whisper"]

    def _resolve_whisper_device(self) -> str:
        """
        解析 Whisper 推理设备。
        - WHISPER_DEVICE=cpu|cuda|cuda:N → 强制
        - WHISPER_DEVICE=auto 或缺省 → cuda 可用则 cuda，否则 cpu
        """
        import os

        override = (os.getenv("WHISPER_DEVICE") or "auto").strip().lower()
        if override and override != "auto":
            return override

        try:
            import torch
            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0) if torch.cuda.device_count() else "cuda"
                logger.info(f"检测到 CUDA 可用: {name}")
                return "cuda"
            logger.info("未检测到 CUDA，Whisper 使用 CPU")
        except Exception as e:
            logger.info(f"CUDA 检测跳过（{e}），Whisper 使用 CPU")
        return "cpu"

    def _generate_subtitle_whisper_local(self, video_path: Path, output_path: Path, 
                                       config: SpeechRecognitionConfig) -> Path:
        """使用本地Whisper生成字幕"""
        if not self.available_methods[SpeechRecognitionMethod.WHISPER_LOCAL]:
            # 再检测一次，避免初始化时误判
            self.available_methods[SpeechRecognitionMethod.WHISPER_LOCAL] = self._check_whisper_availability()
        if not self.available_methods[SpeechRecognitionMethod.WHISPER_LOCAL]:
            raise SpeechRecognitionError(
                "本地Whisper不可用，请安装whisper: pip install openai-whisper\n"
                "同时确保已安装ffmpeg:\n"
                "  macOS: brew install ffmpeg\n"
                "  Ubuntu: sudo apt install ffmpeg\n"
                "  Windows: 下载ffmpeg并添加到PATH"
            )
        
        try:
            logger.info(f"开始使用本地Whisper生成字幕: {video_path}")
            
            # 检查视频文件是否存在
            if not video_path.exists():
                raise SpeechRecognitionError(f"视频文件不存在: {video_path}")
            
            # 检查视频文件大小
            file_size = video_path.stat().st_size
            if file_size == 0:
                raise SpeechRecognitionError(f"视频文件为空: {video_path}")
            
            # 构建whisper命令
            cmd = self._whisper_command_prefix() + [
                str(video_path),
                '--output_dir', str(output_path.parent),
                '--output_format', config.output_format,
                '--model', config.model
            ]

            # 设备：WHISPER_DEVICE=cpu|cuda|cuda:0|auto（默认 auto）
            device = self._resolve_whisper_device()
            cmd.extend(['--device', device])
            logger.info(f"Whisper 使用设备: {device}")
            
            # 添加语言参数
            if config.language != LanguageCode.AUTO:
                cmd.extend(['--language', config.language])
            
            # 添加超时处理
            logger.info(f"执行Whisper命令: {' '.join(cmd)}")
            
            # 根据超时配置决定是否设置超时
            if config.timeout > 0:
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    timeout=config.timeout,
                    cwd=str(video_path.parent)  # 设置工作目录
                )
            else:
                # 无超时限制
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    cwd=str(video_path.parent)  # 设置工作目录
                )
            
            if result.returncode == 0:
                # 检查输出文件是否存在
                if output_path.exists():
                    logger.info(f"本地Whisper字幕生成成功: {output_path}")
                    return output_path
                else:
                    # 尝试查找其他可能的输出文件
                    possible_outputs = list(output_path.parent.glob(f"{video_path.stem}*.{config.output_format}"))
                    if possible_outputs:
                        actual_output = possible_outputs[0]
                        logger.info(f"找到Whisper输出文件: {actual_output}")
                        return actual_output
                    else:
                        raise SpeechRecognitionError(f"Whisper执行成功但未找到输出文件: {output_path}")
            else:
                error_msg = f"本地Whisper执行失败 (返回码: {result.returncode}):\n"
                if result.stderr:
                    error_msg += f"错误信息: {result.stderr}\n"
                if result.stdout:
                    error_msg += f"输出信息: {result.stdout}"
                
                # 提供具体的错误解决建议
                if "command not found" in result.stderr:
                    error_msg += "\n\n解决方案: 请安装whisper: pip install openai-whisper"
                elif "ffmpeg" in result.stderr.lower():
                    error_msg += "\n\n解决方案: 请安装ffmpeg:\n  macOS: brew install ffmpeg\n  Ubuntu: sudo apt install ffmpeg"
                elif "timeout" in result.stderr.lower():
                    error_msg += f"\n\n解决方案: 视频处理超时，请尝试使用更小的模型 (--model tiny) 或增加超时时间"
                
                logger.error(error_msg)
                raise SpeechRecognitionError(error_msg)
                
        except subprocess.TimeoutExpired:
            error_msg = f"本地Whisper执行超时（{config.timeout}秒）\n"
            error_msg += "解决方案:\n"
            error_msg += "1. 使用更小的模型: --model tiny\n"
            error_msg += "2. 增加超时时间\n"
            error_msg += "3. 检查视频文件是否损坏"
            logger.error(error_msg)
            raise SpeechRecognitionError(error_msg)
        except FileNotFoundError:
            error_msg = "找不到whisper命令\n"
            error_msg += "解决方案:\n"
            error_msg += "1. 安装whisper: pip install openai-whisper\n"
            error_msg += "2. 确保whisper在PATH中: which whisper\n"
            error_msg += "3. 重新安装: pip uninstall openai-whisper && pip install openai-whisper"
            logger.error(error_msg)
            raise SpeechRecognitionError(error_msg)
        except Exception as e:
            error_msg = f"本地Whisper生成字幕时发生错误: {e}\n"
            error_msg += "请检查:\n"
            error_msg += "1. 视频文件格式是否支持\n"
            error_msg += "2. 系统是否有足够的内存\n"
            error_msg += "3. 是否有足够的磁盘空间"
            logger.error(error_msg)
            raise SpeechRecognitionError(error_msg)
    
    def _generate_subtitle_openai_api(self, video_path: Path, output_path: Path, 
                                    config: SpeechRecognitionConfig) -> Path:
        """使用OpenAI API生成字幕"""
        if not self.available_methods[SpeechRecognitionMethod.OPENAI_API]:
            raise SpeechRecognitionError("OpenAI API不可用，请设置OPENAI_API_KEY环境变量")
        
        try:
            logger.info(f"开始使用OpenAI API生成字幕: {video_path}")
            
            # 这里需要实现OpenAI API调用
            # 由于需要额外的依赖，这里先抛出异常
            raise SpeechRecognitionError("OpenAI API功能暂未实现，请使用本地Whisper")
            
        except Exception as e:
            error_msg = f"OpenAI API生成字幕时发生错误: {e}"
            logger.error(error_msg)
            raise SpeechRecognitionError(error_msg)
    
    def _generate_subtitle_azure_speech(self, video_path: Path, output_path: Path, 
                                      config: SpeechRecognitionConfig) -> Path:
        """使用Azure Speech Services生成字幕"""
        if not self.available_methods[SpeechRecognitionMethod.AZURE_SPEECH]:
            raise SpeechRecognitionError("Azure Speech Services不可用，请设置AZURE_SPEECH_KEY和AZURE_SPEECH_REGION环境变量")
        
        try:
            logger.info(f"开始使用Azure Speech Services生成字幕: {video_path}")
            
            # 这里需要实现Azure Speech Services调用
            raise SpeechRecognitionError("Azure Speech Services功能暂未实现，请使用本地Whisper")
            
        except Exception as e:
            error_msg = f"Azure Speech Services生成字幕时发生错误: {e}"
            logger.error(error_msg)
            raise SpeechRecognitionError(error_msg)
    
    def _generate_subtitle_google_speech(self, video_path: Path, output_path: Path, 
                                       config: SpeechRecognitionConfig) -> Path:
        """使用Google Speech-to-Text生成字幕"""
        if not self.available_methods[SpeechRecognitionMethod.GOOGLE_SPEECH]:
            raise SpeechRecognitionError("Google Speech-to-Text不可用，请设置GOOGLE_APPLICATION_CREDENTIALS或GOOGLE_SPEECH_API_KEY环境变量")
        
        try:
            logger.info(f"开始使用Google Speech-to-Text生成字幕: {video_path}")
            
            # 这里需要实现Google Speech-to-Text调用
            raise SpeechRecognitionError("Google Speech-to-Text功能暂未实现，请使用本地Whisper")
            
        except Exception as e:
            error_msg = f"Google Speech-to-Text生成字幕时发生错误: {e}"
            logger.error(error_msg)
            raise SpeechRecognitionError(error_msg)
    
    def _generate_subtitle_aliyun_speech(self, video_path: Path, output_path: Path, 
                                       config: SpeechRecognitionConfig) -> Path:
        """使用阿里云语音识别生成字幕"""
        if not self.available_methods[SpeechRecognitionMethod.ALIYUN_SPEECH]:
            raise SpeechRecognitionError("阿里云语音识别不可用，请设置ALIYUN_ACCESS_KEY_ID、ALIYUN_ACCESS_KEY_SECRET和ALIYUN_SPEECH_APP_KEY环境变量")
        
        try:
            logger.info(f"开始使用阿里云语音识别生成字幕: {video_path}")
            
            # 这里需要实现阿里云语音识别调用
            raise SpeechRecognitionError("阿里云语音识别功能暂未实现，请使用本地Whisper")
            
        except Exception as e:
            error_msg = f"阿里云语音识别生成字幕时发生错误: {e}"
            logger.error(error_msg)
            raise SpeechRecognitionError(error_msg)
    
    def get_available_methods(self) -> Dict[SpeechRecognitionMethod, bool]:
        """获取可用的语音识别方法"""
        return self.available_methods.copy()
    
    def get_supported_languages(self) -> List[LanguageCode]:
        """获取支持的语言列表"""
        return list(LanguageCode)
    
    def get_whisper_models(self) -> List[str]:
        """获取可用的Whisper模型列表"""
        return ["tiny", "base", "small", "medium", "large"]


def generate_subtitle_for_video(video_path: Path, output_path: Optional[Path] = None, 
                               method: str = "auto", language: str = "auto", 
                               model: str = "base", enable_fallback: bool = False) -> Path:
    """
    为视频生成字幕文件的便捷函数
    
    Args:
        video_path: 视频文件路径
        output_path: 输出字幕文件路径
        method: 生成方法 ("auto", "whisper_local", ...)；auto 固定使用本地 Whisper
        language: 语言代码
        model: Whisper模型大小（仅对whisper_local有效）
        enable_fallback: 是否启用回退机制（默认关闭）
        
    Returns:
        生成的字幕文件路径
        
    Raises:
        SpeechRecognitionError: 语音识别失败
    """
    # 创建配置（默认本地 Whisper）
    config = SpeechRecognitionConfig(
        method=SpeechRecognitionMethod(method) if method != "auto" else SpeechRecognitionMethod.WHISPER_LOCAL,
        language=LanguageCode(language),
        model=model,
        enable_fallback=enable_fallback
    )
    
    recognizer = SpeechRecognizer()
    
    if method == "auto":
        available_methods = recognizer.get_available_methods()
        
        # 仅使用本地 Whisper（bcut 已停用）
        priority_methods = [
            SpeechRecognitionMethod.WHISPER_LOCAL,
            SpeechRecognitionMethod.OPENAI_API,
            SpeechRecognitionMethod.AZURE_SPEECH,
            SpeechRecognitionMethod.GOOGLE_SPEECH,
            SpeechRecognitionMethod.ALIYUN_SPEECH
        ]
        
        for priority_method in priority_methods:
            if available_methods.get(priority_method, False):
                config.method = priority_method
                break
        else:
            raise SpeechRecognitionError("没有可用的语音识别服务，请安装whisper: pip install openai-whisper")
    
    if config.method == SpeechRecognitionMethod.BCUT_ASR:
        raise SpeechRecognitionError("bcut-asr 已停用，请使用 method=whisper_local")
    
    return recognizer.generate_subtitle(video_path, output_path, config)


def get_available_speech_recognition_methods() -> Dict[str, bool]:
    """
    获取可用的语音识别方法
    
    Returns:
        可用方法字典
    """
    recognizer = SpeechRecognizer()
    available_methods = recognizer.get_available_methods()
    
    return {
        method.value: available 
        for method, available in available_methods.items()
    }


def get_supported_languages() -> List[str]:
    """
    获取支持的语言列表
    
    Returns:
        支持的语言代码列表
    """
    return [lang.value for lang in LanguageCode]


def get_whisper_models() -> List[str]:
    """
    获取可用的Whisper模型列表
    
    Returns:
        Whisper模型列表
    """
    return ["tiny", "base", "small", "medium", "large"]
