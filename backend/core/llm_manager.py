"""
LLM管理器 - 统一管理多个模型提供商
"""
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .llm_providers import (
    LLMProvider, LLMProviderFactory, ProviderType,
)

logger = logging.getLogger(__name__)

_LLM_SETTINGS_KEYS = (
    "llm_provider",
    "dashscope_api_key",
    "openai_api_key",
    "gemini_api_key",
    "siliconflow_api_key",
    "model_name",
)


class LLMManager:
    """LLM管理器"""

    def __init__(self, settings_file: Optional[Path] = None):
        self.settings_file = settings_file or self._get_default_settings_file()
        self.current_provider: Optional[LLMProvider] = None
        self._settings_mtime: Optional[float] = None
        try:
            self.settings = self._load_settings()
        except Exception as e:
            logger.warning("初始加载 settings.json 失败，使用默认配置: %s", e)
            self.settings = {
                "llm_provider": "dashscope",
                "dashscope_api_key": "",
                "openai_api_key": "",
                "gemini_api_key": "",
                "siliconflow_api_key": "",
                "model_name": "qwen3.7-plus",
                "chunk_size": 5000,
                "min_score_threshold": 0.7,
                "max_clips_per_collection": 5,
            }
        self._initialize_provider()

    def _get_default_settings_file(self) -> Path:
        """获取默认设置文件路径（与 settings API / Docker data 卷一致）"""
        try:
            from .path_utils import get_settings_file_path
            return get_settings_file_path()
        except Exception:
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent
            return project_root / "data" / "settings.json"

    def _settings_file_mtime(self) -> Optional[float]:
        try:
            if self.settings_file.exists():
                return self.settings_file.stat().st_mtime
        except OSError:
            pass
        return None

    def _load_settings(self) -> Dict[str, Any]:
        """加载设置。成功时更新 mtime；失败时抛出，避免用默认配置覆盖内存。"""
        default_settings = {
            "llm_provider": "dashscope",
            "dashscope_api_key": "",
            "openai_api_key": "",
            "gemini_api_key": "",
            "siliconflow_api_key": "",
            "model_name": "qwen3.7-plus",
            "chunk_size": 5000,
            "min_score_threshold": 0.7,
            "max_clips_per_collection": 5
        }

        if not self.settings_file.exists():
            return default_settings

        with open(self.settings_file, 'r', encoding='utf-8') as f:
            saved_settings = json.load(f)
        if isinstance(saved_settings, dict):
            default_settings.update(saved_settings)
        self._settings_mtime = self._settings_file_mtime()
        return default_settings

    def _save_settings(self):
        """保存设置"""
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            self._settings_mtime = self._settings_file_mtime()
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            raise

    def ensure_fresh_settings(self) -> bool:
        """若 settings.json 已被其它进程更新，则重新加载并切换提供商。

        解决 UI（API 进程）改模型后 celery-worker 仍用旧内存配置的问题。
        """
        current_mtime = self._settings_file_mtime()
        if current_mtime is None:
            return False
        if self._settings_mtime is not None and current_mtime <= self._settings_mtime:
            return False

        previous = {k: self.settings.get(k) for k in _LLM_SETTINGS_KEYS}
        try:
            loaded = self._load_settings()
        except Exception as e:
            # 可能碰上 API 进程正在写文件；保留旧配置，下次再试
            logger.warning("热加载 settings.json 失败，沿用当前 LLM 配置: %s", e)
            return False

        self.settings = loaded
        changed = any(previous.get(k) != self.settings.get(k) for k in _LLM_SETTINGS_KEYS)
        if changed or self.current_provider is None:
            logger.info(
                "检测到 LLM 设置变更，重新加载: provider=%s model=%s",
                self.settings.get("llm_provider"),
                self.settings.get("model_name"),
            )
            self._initialize_provider()
            return True
        return False

    def _initialize_provider(self):
        """初始化当前提供商"""
        try:
            provider_type = ProviderType(self.settings.get("llm_provider", "dashscope"))
            model_name = self.settings.get("model_name", "qwen3.7-plus")

            api_key = self._get_api_key_for_provider(provider_type)

            if api_key:
                self.current_provider = LLMProviderFactory.create_provider(
                    provider_type, api_key, model_name
                )
                logger.info(f"已初始化{provider_type.value}提供商，模型: {model_name}")
            else:
                logger.warning(f"未找到{provider_type.value}的API密钥")
                self.current_provider = None

        except Exception as e:
            logger.error(f"初始化提供商失败: {e}")
            self.current_provider = None

    def _get_api_key_for_provider(self, provider_type: ProviderType) -> Optional[str]:
        """获取指定提供商的API密钥"""
        key_mapping = {
            ProviderType.DASHSCOPE: "dashscope_api_key",
            ProviderType.OPENAI: "openai_api_key",
            ProviderType.GEMINI: "gemini_api_key",
            ProviderType.SILICONFLOW: "siliconflow_api_key",
        }

        key_name = key_mapping.get(provider_type)
        if key_name:
            return self.settings.get(key_name, "")
        return None

    def update_settings(self, new_settings: Dict[str, Any]):
        """更新设置"""
        self.settings.update(new_settings)
        self._save_settings()
        self._initialize_provider()

    def set_provider(self, provider_type: ProviderType, api_key: str, model_name: str):
        """设置提供商"""
        try:
            provider_settings = {
                "llm_provider": provider_type.value,
                "model_name": model_name
            }

            key_mapping = {
                ProviderType.DASHSCOPE: "dashscope_api_key",
                ProviderType.OPENAI: "openai_api_key",
                ProviderType.GEMINI: "gemini_api_key",
                ProviderType.SILICONFLOW: "siliconflow_api_key",
            }

            key_name = key_mapping.get(provider_type)
            if key_name:
                provider_settings[key_name] = api_key

            self.update_settings(provider_settings)

            self.current_provider = LLMProviderFactory.create_provider(
                provider_type, api_key, model_name
            )

            logger.info(f"已切换到{provider_type.value}提供商，模型: {model_name}")

        except Exception as e:
            logger.error(f"设置提供商失败: {e}")
            raise

    def call(self, prompt: str, input_data: Any = None, **kwargs) -> str:
        """调用LLM"""
        self.ensure_fresh_settings()
        if not self.current_provider:
            raise ValueError("未配置LLM提供商，请在设置页面配置API密钥")

        try:
            response = self.current_provider.call(prompt, input_data, **kwargs)
            return response.content
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise

    def call_with_retry(self, prompt: str, input_data: Any = None, max_retries: int = 3, **kwargs) -> str:
        """带重试机制的LLM调用"""
        for attempt in range(max_retries):
            try:
                return self.call(prompt, input_data, **kwargs)
            except ValueError:  # 如果是API Key或参数错误，不重试
                raise
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"LLM调用在{max_retries}次重试后彻底失败。")
                    raise
                logger.warning(f"第{attempt + 1}次调用失败，准备重试: {str(e)}")
                import time
                time.sleep(2 ** attempt)  # 指数退避
        return ""

    def call_with_model(
        self,
        model_name: Optional[str],
        prompt: str,
        input_data: Any = None,
        max_retries: int = 3,
        **kwargs,
    ) -> str:
        """使用指定模型调用 LLM；未传或与当前模型相同时走默认配置。"""
        self.ensure_fresh_settings()
        current = self.settings.get("model_name")
        if not model_name or model_name == current:
            return self.call_with_retry(prompt, input_data, max_retries, **kwargs)

        provider_type = ProviderType(self.settings.get("llm_provider", "dashscope"))
        api_key = self._get_api_key_for_provider(provider_type)
        if not api_key:
            raise ValueError("未配置LLM提供商，请在设置页面配置API密钥")

        provider = LLMProviderFactory.create_provider(provider_type, api_key, model_name)
        for attempt in range(max_retries):
            try:
                response = provider.call(prompt, input_data, **kwargs)
                return response.content
            except ValueError:
                raise
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error("指定模型 %s 调用在 %s 次重试后失败", model_name, max_retries)
                    raise
                logger.warning("模型 %s 第 %s 次调用失败，准备重试: %s", model_name, attempt + 1, e)
                import time
                time.sleep(2 ** attempt)
        return ""

    def test_provider_connection(self, provider_type: ProviderType, api_key: str, model_name: str) -> bool:
        """测试提供商连接"""
        try:
            provider = LLMProviderFactory.create_provider(provider_type, api_key, model_name)
            return provider.test_connection()
        except Exception as e:
            logger.error(f"测试{provider_type.value}连接失败: {e}")
            return False

    def get_current_provider_info(self) -> Dict[str, Any]:
        """获取当前提供商信息"""
        self.ensure_fresh_settings()
        if not self.current_provider:
            return {"provider": None, "model": None, "available": False}

        provider_type = ProviderType(self.settings.get("llm_provider", "dashscope"))
        model_name = self.settings.get("model_name", "qwen3.7-plus")

        return {
            "provider": provider_type.value,
            "model": model_name,
            "available": True,
            "display_name": self._get_provider_display_name(provider_type)
        }

    def _get_provider_display_name(self, provider_type: ProviderType) -> str:
        """获取提供商显示名称"""
        display_names = {
            ProviderType.DASHSCOPE: "阿里通义千问",
            ProviderType.OPENAI: "OpenAI",
            ProviderType.GEMINI: "Google Gemini",
            ProviderType.SILICONFLOW: "硅基流动"
        }
        return display_names.get(provider_type, provider_type.value)

    def get_all_available_models(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有可用模型"""
        all_models = LLMProviderFactory.get_all_available_models()
        result = {}

        for provider_type, models in all_models.items():
            provider_name = provider_type.value
            result[provider_name] = [
                {
                    "name": model.name,
                    "display_name": model.display_name,
                    "max_tokens": model.max_tokens,
                    "description": model.description
                }
                for model in models
            ]

        return result

    def parse_json_response(self, response: str) -> Any:
        """解析JSON响应（保持与原LLMClient的兼容性）"""
        self.ensure_fresh_settings()
        if not self.current_provider:
            raise ValueError("未配置LLM提供商")

        from ..utils.llm_client import LLMClient
        temp_client = LLMClient()
        return temp_client.parse_json_response(response)


# 全局LLM管理器实例
_llm_manager: Optional[LLMManager] = None


def get_llm_manager() -> LLMManager:
    """获取全局LLM管理器实例（自动感知 settings.json 变更）"""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    else:
        _llm_manager.ensure_fresh_settings()
    return _llm_manager


def initialize_llm_manager(settings_file: Optional[Path] = None) -> LLMManager:
    """初始化LLM管理器"""
    global _llm_manager
    _llm_manager = LLMManager(settings_file)
    return _llm_manager
