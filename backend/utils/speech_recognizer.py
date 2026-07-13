"""
语音识别工具 - 支持多种语音识别服务
支持本地 Whisper、SenseVoice（FunASR）、以及若干云端 API 占位
"""
import logging
import subprocess
import json
import os
import re
import asyncio
from typing import Optional, List, Dict, Any, Union, Tuple
from pathlib import Path
from enum import Enum
import requests
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# bcut-asr 已停用
BCUT_ASR_AVAILABLE = False

# SenseVoice / faster-whisper 模型缓存（避免 Celery worker 每次重新加载）
_SENSEVOICE_MODEL = None
_SENSEVOICE_MODEL_KEY: Optional[Tuple[str, str]] = None
_FASTER_WHISPER_MODEL = None
_FASTER_WHISPER_MODEL_KEY: Optional[Tuple[str, str, str]] = None

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]
FASTER_WHISPER_MODELS = [
    "tiny", "base", "small", "medium", "large", "large-v2", "large-v3", "distil-large-v3"
]
SENSEVOICE_DEFAULT_MODEL = "iic/SenseVoiceSmall"
SENSEVOICE_MODEL_ALIASES = {
    "sensevoice": SENSEVOICE_DEFAULT_MODEL,
    "sensevoicesmall": SENSEVOICE_DEFAULT_MODEL,
    "small": SENSEVOICE_DEFAULT_MODEL,
    "iic/sensevoicesmall": SENSEVOICE_DEFAULT_MODEL,
}


class SpeechRecognitionMethod(str, Enum):
    """语音识别方法枚举"""
    BCUT_ASR = "bcut_asr"  # 已停用，保留枚举值兼容旧配置
    WHISPER_LOCAL = "whisper_local"
    FASTER_WHISPER = "faster_whisper"
    SENSEVOICE = "sensevoice"
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
    model: str = "base"  # Whisper 模型大小，或 SenseVoice 模型名
    timeout: int = 0  # 超时时间（秒），0表示无限制
    output_format: str = "srt"  # 输出格式
    enable_timestamps: bool = True  # 是否启用时间戳
    enable_punctuation: bool = True  # 是否启用标点符号
    enable_speaker_diarization: bool = False  # 是否启用说话人分离
    enable_fallback: bool = False  # 默认关闭回退
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
        
        # 验证模型（按方法区分）
        if self.method == SpeechRecognitionMethod.WHISPER_LOCAL:
            if self.model not in WHISPER_MODELS:
                raise ValueError(f"不支持的Whisper模型: {self.model}")
        elif self.method == SpeechRecognitionMethod.FASTER_WHISPER:
            self.model = normalize_faster_whisper_model(self.model)
        elif self.method == SpeechRecognitionMethod.SENSEVOICE:
            self.model = normalize_sensevoice_model(self.model)
        elif self.model in WHISPER_MODELS or self.model:
            pass  # 其他方法暂不严格校验模型名
        
        # 验证超时时间
        if self.timeout < 0:
            raise ValueError("超时时间不能为负数")
        
        # 验证输出格式
        valid_formats = ["srt", "vtt", "txt", "json"]
        if self.output_format not in valid_formats:
            raise ValueError(f"不支持的输出格式: {self.output_format}")


def normalize_sensevoice_model(model: Optional[str]) -> str:
    """将别名归一为 FunASR SenseVoice 模型 ID"""
    if not model or model in WHISPER_MODELS:
        return SENSEVOICE_DEFAULT_MODEL
    key = model.strip().lower().replace("_", "")
    return SENSEVOICE_MODEL_ALIASES.get(key, model.strip())


def normalize_faster_whisper_model(model: Optional[str]) -> str:
    """归一 faster-whisper 模型名"""
    if not model:
        return "base"
    name = model.strip()
    # SenseVoice 模型名误配时回退
    if "sensevoice" in name.lower() or name.startswith("iic/"):
        return "base"
    if name in FASTER_WHISPER_MODELS:
        return name
    if name in WHISPER_MODELS:
        return name
    return "base"


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

        # 检查 faster-whisper
        methods[SpeechRecognitionMethod.FASTER_WHISPER] = self._check_faster_whisper_availability()

        # 检查 SenseVoice（FunASR）
        methods[SpeechRecognitionMethod.SENSEVOICE] = self._check_sensevoice_availability()
        
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
    
    def _check_faster_whisper_availability(self) -> bool:
        """检查 faster-whisper 是否可用"""
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            logger.debug("faster-whisper 不可用：未安装")
            return False

    def _check_sensevoice_availability(self) -> bool:
        """检查 SenseVoice（funasr）是否可用"""
        try:
            import funasr  # noqa: F401
            return True
        except ImportError:
            logger.debug("SenseVoice 不可用：未安装 funasr")
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
            elif config.method == SpeechRecognitionMethod.FASTER_WHISPER:
                return self._generate_subtitle_faster_whisper(video_path, output_path, config)
            elif config.method == SpeechRecognitionMethod.SENSEVOICE:
                return self._generate_subtitle_sensevoice(video_path, output_path, config)
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
            "bcut-asr 已停用，请使用 faster_whisper / whisper_local / sensevoice"
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

    def _resolve_asr_device(self) -> str:
        """解析 SenseVoice / ASR 设备：SENSEVOICE_DEVICE 优先，否则 WHISPER_DEVICE / auto"""
        override = (
            os.getenv("SENSEVOICE_DEVICE")
            or os.getenv("WHISPER_DEVICE")
            or "auto"
        ).strip().lower()
        if override and override != "auto":
            return override
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    @staticmethod
    def _map_sensevoice_language(language: LanguageCode) -> str:
        """映射到 SenseVoice 支持的 language 参数"""
        mapping = {
            LanguageCode.AUTO: "auto",
            LanguageCode.CHINESE_SIMPLIFIED: "zh",
            LanguageCode.CHINESE_TRADITIONAL: "zh",
            LanguageCode.ENGLISH: "en",
            LanguageCode.ENGLISH_US: "en",
            LanguageCode.ENGLISH_UK: "en",
            LanguageCode.JAPANESE: "ja",
            LanguageCode.KOREAN: "ko",
        }
        return mapping.get(language, "auto")

    @staticmethod
    def _clean_sensevoice_text(text: str) -> str:
        """去掉 SenseVoice 的语言/情绪等标签"""
        if not text:
            return ""
        try:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
            text = rich_transcription_postprocess(text)
        except Exception:
            text = re.sub(r"<\|[^|]*\|>", "", text)
        return (text or "").strip()

    @staticmethod
    def _format_srt_timestamp(ms: int) -> str:
        ms = max(0, int(ms))
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        ms_rem = ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms_rem:03d}"

    def _get_sensevoice_model(self, model_name: str, device: str):
        """加载并缓存 SenseVoice AutoModel（带 VAD，便于产出带时间戳的句段）"""
        global _SENSEVOICE_MODEL, _SENSEVOICE_MODEL_KEY
        key = (model_name, device, "vad")
        if _SENSEVOICE_MODEL is not None and _SENSEVOICE_MODEL_KEY == key:
            return _SENSEVOICE_MODEL

        try:
            from funasr import AutoModel
        except ImportError as e:
            raise SpeechRecognitionError(
                "SenseVoice 不可用，请安装: pip install funasr\n"
                f"原始错误: {e}"
            ) from e

        logger.info(f"加载 SenseVoice 模型: {model_name} (device={device})")
        kwargs: Dict[str, Any] = {
            "model": model_name,
            "vad_model": "fsmn-vad",
            "vad_kwargs": {"max_single_segment_time": 30000},
            "device": device,
            "disable_update": True,
        }
        # cam++ 可带来 sentence_info 时间戳；加载失败则退回纯 VAD
        try:
            kwargs["spk_model"] = "cam++"
            _SENSEVOICE_MODEL = AutoModel(**kwargs)
        except Exception as e:
            logger.warning(f"SenseVoice 加载 cam++ 失败，改用纯 VAD: {e}")
            kwargs.pop("spk_model", None)
            _SENSEVOICE_MODEL = AutoModel(**kwargs)
        _SENSEVOICE_MODEL_KEY = key
        return _SENSEVOICE_MODEL

    def _get_audio_duration_ms(self, audio_path: Path) -> int:
        """获取音频时长（毫秒）"""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return max(1000, int(float(result.stdout.strip()) * 1000))
        except Exception as e:
            logger.warning(f"ffprobe 获取时长失败: {e}")

        try:
            import wave
            with wave.open(str(audio_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate() or 16000
                return max(1000, int(frames / rate * 1000))
        except Exception as e:
            logger.warning(f"wave 获取时长失败: {e}")
        return 0

    @staticmethod
    def _split_text_for_subtitles(text: str, max_chars: int = 42) -> List[str]:
        """按标点/长度切成适合字幕的短句"""
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return []
        parts = re.split(r"(?<=[。！？；!?.;])\s*", text)
        lines: List[str] = []
        buf = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if not buf:
                buf = part
            elif len(buf) + len(part) <= max_chars:
                buf += part
            else:
                lines.append(buf)
                buf = part
            # 过长再硬切
            while len(buf) > max_chars * 2:
                lines.append(buf[:max_chars])
                buf = buf[max_chars:]
        if buf:
            lines.append(buf)
        return lines or [text]

    def _distribute_text_over_duration(
        self, text: str, duration_ms: int, start_ms: int = 0
    ) -> List[Dict[str, Any]]:
        """无句级时间戳时：按全文比例铺到真实音频时长，避免退化成 1 秒"""
        duration_ms = max(duration_ms, 1000)
        lines = self._split_text_for_subtitles(text)
        if not lines:
            return []
        weights = [max(len(x), 1) for x in lines]
        total_w = sum(weights)
        segments: List[Dict[str, Any]] = []
        cursor = start_ms
        end_limit = start_ms + duration_ms
        for i, (line, w) in enumerate(zip(lines, weights)):
            if i == len(lines) - 1:
                end = end_limit
            else:
                span = max(800, int(duration_ms * w / total_w))
                end = min(end_limit, cursor + span)
            if end <= cursor:
                end = min(end_limit, cursor + 800)
            segments.append({"start": cursor, "end": end, "text": line})
            cursor = end
            if cursor >= end_limit:
                break
        return segments

    def _normalize_ts_ms(self, value: Any) -> Optional[int]:
        """把秒/毫秒混用的时间值统一成毫秒"""
        if value is None:
            return None
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if v < 0:
            return None
        # 小数基本是秒；整数按 FunASR 惯例视为毫秒
        if abs(v - int(v)) > 1e-6:
            return int(v * 1000)
        return int(v)

    def _segment_from_dict(self, seg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        text = self._clean_sensevoice_text(seg.get("sentence") or seg.get("text", ""))
        if not text:
            return None
        start = self._normalize_ts_ms(seg.get("start", seg.get("start_time")))
        end = self._normalize_ts_ms(seg.get("end", seg.get("end_time")))
        if start is None or end is None or end <= start:
            return None
        return {"start": start, "end": end, "text": text}

    def _extract_sensevoice_segments(
        self, result: Any, audio_duration_ms: int = 0
    ) -> List[Dict[str, Any]]:
        """从 FunASR 结果提取带真实时间轴的字幕片段"""
        items = result if isinstance(result, list) else [result]
        segments: List[Dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            # 1) sentence_info（带 VAD/说话人时最可靠）
            for seg in item.get("sentence_info", []) or []:
                if isinstance(seg, dict):
                    parsed = self._segment_from_dict(seg)
                    if parsed:
                        segments.append(parsed)

        if segments:
            return segments

        # 2) 多段结果：每项自带 start/end（VAD 切段后逐段识别）
        for item in items:
            if not isinstance(item, dict):
                continue
            parsed = self._segment_from_dict(item)
            if parsed:
                segments.append(parsed)
                continue
            # 有文本但时间在 timestamp 字段
            text = self._clean_sensevoice_text(item.get("text", ""))
            if not text:
                continue
            bounds = None
            for key in ("timestamp", "timestamps"):
                values = item.get(key) or []
                starts_ends = []
                for ts in values:
                    if isinstance(ts, dict):
                        start = self._normalize_ts_ms(
                            ts.get("start_time", ts.get("start"))
                        )
                        end = self._normalize_ts_ms(ts.get("end_time", ts.get("end")))
                    elif isinstance(ts, (list, tuple)) and len(ts) >= 2:
                        start = self._normalize_ts_ms(ts[0])
                        end = self._normalize_ts_ms(ts[1])
                    else:
                        continue
                    if start is not None and end is not None and end > start:
                        starts_ends.append((start, end))
                if starts_ends:
                    bounds = (
                        min(s for s, _ in starts_ends),
                        max(e for _, e in starts_ends),
                    )
                    break
            if bounds:
                segments.append({"start": bounds[0], "end": bounds[1], "text": text})

        if segments:
            return segments

        # 3) 最后回退：全文 + 真实音频时长按标点切分（绝不用 1 秒假时间轴）
        full_text = " ".join(
            self._clean_sensevoice_text(item.get("text", ""))
            for item in items
            if isinstance(item, dict)
        ).strip()
        if not full_text:
            return []
        duration = audio_duration_ms if audio_duration_ms > 0 else 0
        if duration <= 0:
            logger.warning("SenseVoice 无时间戳且无法获取音频时长，拒绝写入假 1 秒字幕")
            return []
        logger.warning(
            f"SenseVoice 未返回句级时间戳，按音频时长 {duration}ms 比例切分字幕"
        )
        return self._distribute_text_over_duration(full_text, duration)

    def _write_srt(self, segments: List[Dict[str, Any]], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                f.write(
                    f"{i}\n"
                    f"{self._format_srt_timestamp(seg['start'])} --> "
                    f"{self._format_srt_timestamp(seg['end'])}\n"
                    f"{seg['text']}\n\n"
                )

    def _generate_subtitle_sensevoice(
        self, video_path: Path, output_path: Path, config: SpeechRecognitionConfig
    ) -> Path:
        """使用 SenseVoice（FunASR）生成字幕"""
        if not self.available_methods.get(SpeechRecognitionMethod.SENSEVOICE, False):
            self.available_methods[SpeechRecognitionMethod.SENSEVOICE] = (
                self._check_sensevoice_availability()
            )
        if not self.available_methods[SpeechRecognitionMethod.SENSEVOICE]:
            raise SpeechRecognitionError(
                "SenseVoice 不可用，请安装: pip install funasr\n"
                "并确保已安装 ffmpeg"
            )

        if not video_path.exists():
            raise SpeechRecognitionError(f"视频文件不存在: {video_path}")
        if video_path.stat().st_size == 0:
            raise SpeechRecognitionError(f"视频文件为空: {video_path}")

        try:
            logger.info(f"开始使用 SenseVoice 生成字幕: {video_path}")
            audio_path = self._extract_audio_from_video(video_path, output_path.parent)
            device = self._resolve_asr_device()
            model_name = normalize_sensevoice_model(config.model)
            language = self._map_sensevoice_language(config.language)
            model = self._get_sensevoice_model(model_name, device)
            audio_duration_ms = self._get_audio_duration_ms(audio_path)

            # 不 merge_vad，保留 VAD 切段时间戳，避免整段文本丢失时间轴
            generate_kwargs: Dict[str, Any] = {
                "input": str(audio_path),
                "cache": {},
                "language": language,
                "use_itn": True,
                "batch_size_s": 60,
                "merge_vad": False,
                "sentence_timestamp": True,
            }
            logger.info(
                f"SenseVoice 推理: model={model_name}, device={device}, "
                f"language={language}, duration_ms={audio_duration_ms}"
            )
            result = model.generate(**generate_kwargs)
            if not result:
                raise SpeechRecognitionError("SenseVoice 未返回识别结果")

            segments = self._extract_sensevoice_segments(result, audio_duration_ms)
            if not segments:
                raise SpeechRecognitionError(
                    "SenseVoice 未检测到可用字幕时间轴（无 sentence_info 且无法回退）"
                )

            # 若只得到一条且时长异常短（<2s），而音频明显更长，按全文重铺
            if (
                len(segments) == 1
                and audio_duration_ms > 5000
                and (segments[0]["end"] - segments[0]["start"]) < 2000
            ):
                logger.warning(
                    "SenseVoice 仅返回异常短时间轴，改用音频时长比例切分"
                )
                segments = self._distribute_text_over_duration(
                    segments[0]["text"], audio_duration_ms
                )

            self._write_srt(segments, output_path)
            if not output_path.exists():
                raise SpeechRecognitionError(f"SenseVoice 执行成功但未写出字幕: {output_path}")

            logger.info(f"SenseVoice 字幕生成成功: {output_path} ({len(segments)} 条)")
            return output_path
        except SpeechRecognitionError:
            raise
        except Exception as e:
            error_msg = (
                f"SenseVoice 生成字幕失败: {e}\n"
                "请检查: funasr 是否安装、模型是否可下载、内存是否充足"
            )
            logger.error(error_msg)
            raise SpeechRecognitionError(error_msg) from e

    def _resolve_faster_whisper_device_and_compute(self) -> Tuple[str, str]:
        """返回 (device, compute_type)"""
        device = (
            os.getenv("FASTER_WHISPER_DEVICE")
            or os.getenv("WHISPER_DEVICE")
            or "auto"
        ).strip().lower()
        if device in ("", "auto"):
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        if device.startswith("cuda"):
            device = "cuda"

        compute_type = (os.getenv("FASTER_WHISPER_COMPUTE_TYPE") or "").strip()
        if not compute_type:
            compute_type = "float16" if device == "cuda" else "int8"
        return device, compute_type

    def _get_faster_whisper_model(self, model_name: str, device: str, compute_type: str):
        """加载并缓存 faster-whisper 模型"""
        global _FASTER_WHISPER_MODEL, _FASTER_WHISPER_MODEL_KEY
        key = (model_name, device, compute_type)
        if _FASTER_WHISPER_MODEL is not None and _FASTER_WHISPER_MODEL_KEY == key:
            return _FASTER_WHISPER_MODEL
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise SpeechRecognitionError(
                "faster-whisper 不可用，请安装: pip install faster-whisper\n"
                f"原始错误: {e}"
            ) from e

        logger.info(
            f"加载 faster-whisper: model={model_name}, device={device}, compute_type={compute_type}"
        )
        _FASTER_WHISPER_MODEL = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )
        _FASTER_WHISPER_MODEL_KEY = key
        return _FASTER_WHISPER_MODEL

    @staticmethod
    def _map_faster_whisper_language(language: LanguageCode) -> Optional[str]:
        """auto -> None（自动检测）；其余映射为 Whisper 语言码"""
        if language == LanguageCode.AUTO:
            return None
        mapping = {
            LanguageCode.CHINESE_SIMPLIFIED: "zh",
            LanguageCode.CHINESE_TRADITIONAL: "zh",
            LanguageCode.ENGLISH: "en",
            LanguageCode.ENGLISH_US: "en",
            LanguageCode.ENGLISH_UK: "en",
            LanguageCode.JAPANESE: "ja",
            LanguageCode.KOREAN: "ko",
            LanguageCode.FRENCH: "fr",
            LanguageCode.GERMAN: "de",
            LanguageCode.SPANISH: "es",
            LanguageCode.RUSSIAN: "ru",
            LanguageCode.ARABIC: "ar",
            LanguageCode.PORTUGUESE: "pt",
            LanguageCode.ITALIAN: "it",
        }
        return mapping.get(language, language.value if language.value != "auto" else None)

    def _generate_subtitle_faster_whisper(
        self, video_path: Path, output_path: Path, config: SpeechRecognitionConfig
    ) -> Path:
        """使用 faster-whisper 生成带段级时间戳的 SRT"""
        if not self.available_methods.get(SpeechRecognitionMethod.FASTER_WHISPER, False):
            self.available_methods[SpeechRecognitionMethod.FASTER_WHISPER] = (
                self._check_faster_whisper_availability()
            )
        if not self.available_methods[SpeechRecognitionMethod.FASTER_WHISPER]:
            raise SpeechRecognitionError(
                "faster-whisper 不可用，请安装: pip install faster-whisper\n"
                "并确保已安装 ffmpeg"
            )

        if not video_path.exists():
            raise SpeechRecognitionError(f"视频文件不存在: {video_path}")
        if video_path.stat().st_size == 0:
            raise SpeechRecognitionError(f"视频文件为空: {video_path}")

        try:
            logger.info(f"开始使用 faster-whisper 生成字幕: {video_path}")
            audio_path = self._extract_audio_from_video(video_path, output_path.parent)
            model_name = normalize_faster_whisper_model(config.model)
            device, compute_type = self._resolve_faster_whisper_device_and_compute()
            model = self._get_faster_whisper_model(model_name, device, compute_type)
            language = self._map_faster_whisper_language(config.language)

            beam_size = int(os.getenv("FASTER_WHISPER_BEAM_SIZE", "5"))
            vad_filter = (os.getenv("FASTER_WHISPER_VAD_FILTER", "true")).strip().lower() in (
                "1", "true", "yes", "on"
            )

            logger.info(
                f"faster-whisper 推理: model={model_name}, device={device}, "
                f"compute_type={compute_type}, language={language or 'auto'}, vad={vad_filter}"
            )
            segments_iter, info = model.transcribe(
                str(audio_path),
                language=language,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=False,
            )

            segments: List[Dict[str, Any]] = []
            for seg in segments_iter:
                text = (seg.text or "").strip()
                if not text:
                    continue
                start_ms = max(0, int(float(seg.start) * 1000))
                end_ms = max(start_ms + 1, int(float(seg.end) * 1000))
                segments.append({"start": start_ms, "end": end_ms, "text": text})

            if not segments:
                raise SpeechRecognitionError("faster-whisper 未检测到语音内容")

            self._write_srt(segments, output_path)
            if not output_path.exists():
                raise SpeechRecognitionError(
                    f"faster-whisper 执行成功但未写出字幕: {output_path}"
                )

            detected = getattr(info, "language", None) or language or "auto"
            logger.info(
                f"faster-whisper 字幕生成成功: {output_path} "
                f"({len(segments)} 条, lang={detected})"
            )
            return output_path
        except SpeechRecognitionError:
            raise
        except Exception as e:
            error_msg = (
                f"faster-whisper 生成字幕失败: {e}\n"
                "请检查: faster-whisper 是否安装、模型是否可下载、内存是否充足"
            )
            logger.error(error_msg)
            raise SpeechRecognitionError(error_msg) from e

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
        return list(WHISPER_MODELS)

    def get_sensevoice_models(self) -> List[str]:
        """获取推荐的 SenseVoice 模型列表"""
        return [SENSEVOICE_DEFAULT_MODEL, "iic/SenseVoiceSmall"]


def generate_subtitle_for_video(video_path: Path, output_path: Optional[Path] = None, 
                               method: str = "auto", language: str = "auto", 
                               model: str = "base", enable_fallback: bool = False) -> Path:
    """
    为视频生成字幕文件的便捷函数。

    method=auto 时读取 SPEECH_RECOGNITION_METHOD；仍为 auto 则优先 faster-whisper。
    """
    if method == "auto":
        env_method = (os.getenv("SPEECH_RECOGNITION_METHOD") or "").strip().lower()
        if env_method and env_method not in ("auto", ""):
            method = env_method

    recognizer = SpeechRecognizer()
    lang = LanguageCode(language)
    env_model = (os.getenv("SPEECH_RECOGNITION_MODEL") or "").strip()

    def _build_config(selected: SpeechRecognitionMethod, selected_model: str) -> SpeechRecognitionConfig:
        if selected == SpeechRecognitionMethod.SENSEVOICE:
            selected_model = normalize_sensevoice_model(selected_model)
        elif selected == SpeechRecognitionMethod.FASTER_WHISPER:
            selected_model = normalize_faster_whisper_model(selected_model)
        elif selected == SpeechRecognitionMethod.WHISPER_LOCAL and selected_model not in WHISPER_MODELS:
            selected_model = "base"
        return SpeechRecognitionConfig(
            method=selected,
            language=lang,
            model=selected_model,
            enable_fallback=enable_fallback,
        )

    if method == "auto":
        available_methods = recognizer.get_available_methods()
        priority_methods = [
            SpeechRecognitionMethod.FASTER_WHISPER,
            SpeechRecognitionMethod.SENSEVOICE,
            SpeechRecognitionMethod.WHISPER_LOCAL,
            SpeechRecognitionMethod.OPENAI_API,
            SpeechRecognitionMethod.AZURE_SPEECH,
            SpeechRecognitionMethod.GOOGLE_SPEECH,
            SpeechRecognitionMethod.ALIYUN_SPEECH,
        ]
        selected_method = next(
            (m for m in priority_methods if available_methods.get(m, False)),
            None,
        )
        if selected_method is None:
            raise SpeechRecognitionError(
                "没有可用的语音识别服务，请安装: "
                "pip install faster-whisper 或 funasr 或 openai-whisper"
            )
        if selected_method == SpeechRecognitionMethod.SENSEVOICE:
            selected_model = env_model or SENSEVOICE_DEFAULT_MODEL
        elif selected_method == SpeechRecognitionMethod.FASTER_WHISPER:
            selected_model = normalize_faster_whisper_model(env_model or model or "base")
        else:
            selected_model = model if model in WHISPER_MODELS else (env_model or "base")
        config = _build_config(selected_method, selected_model)
    else:
        selected_method = SpeechRecognitionMethod(method)
        if selected_method == SpeechRecognitionMethod.BCUT_ASR:
            raise SpeechRecognitionError(
                "bcut-asr 已停用，请使用 method=faster_whisper / whisper_local / sensevoice"
            )
        if selected_method == SpeechRecognitionMethod.SENSEVOICE:
            selected_model = (
                model if model and model not in WHISPER_MODELS
                else (env_model or SENSEVOICE_DEFAULT_MODEL)
            )
        elif selected_method == SpeechRecognitionMethod.FASTER_WHISPER:
            selected_model = normalize_faster_whisper_model(model or env_model or "base")
        else:
            selected_model = model
        config = _build_config(selected_method, selected_model)

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
    return list(WHISPER_MODELS)


def get_sensevoice_models() -> List[str]:
    """获取推荐的 SenseVoice 模型列表"""
    return [SENSEVOICE_DEFAULT_MODEL]
