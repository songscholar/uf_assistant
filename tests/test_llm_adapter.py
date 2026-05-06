"""
测试 LLM 适配器模块
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import LlmConfigError
from app.core.llm_adapter import (
    LlmProviderConfig,
    LlmService,
    _extract_content,
    _extract_tool_calls,
    _load_provider_config,
)


class TestLoadProviderConfig:
    """测试加载提供商配置"""

    def test_load_kimi_config(self):
        """测试加载 Kimi 配置"""
        with patch.dict(os.environ, {
            "KIMI_LLM_API_KEY": "test-key",
            "KIMI_LLM_BASE_URL": "https://api.moonshot.cn/v1/chat/completions",
            "KIMI_LLM_MODEL": "kimi-test",
        }, clear=False):
            cfg = _load_provider_config("kimi")
            assert cfg is not None
            assert cfg.name == "kimi"
            assert cfg.api_key == "test-key"
            assert cfg.model == "kimi-test"
            assert cfg.base_url == "https://api.moonshot.cn/v1/chat/completions"

    def test_missing_api_key_returns_none(self):
        """测试缺少 API Key 返回 None"""
        with patch.dict(os.environ, {}, clear=True):
            cfg = _load_provider_config("kimi")
            assert cfg is None

    def test_unknown_provider_returns_none(self):
        """测试未知提供商返回 None"""
        cfg = _load_provider_config("unknown")
        assert cfg is None

    def test_default_model_fallback(self):
        """测试默认模型回退"""
        with patch.dict(os.environ, {
            "KIMI_LLM_API_KEY": "test-key",
            "KIMI_LLM_BASE_URL": "https://api.moonshot.cn/v1",
        }, clear=False):
            cfg = _load_provider_config("kimi")
            assert cfg is not None
            assert cfg.model == "kimi-k2"  # 默认值


class TestLlmService:
    """测试 LLM 服务"""

    def test_from_env_no_providers(self):
        """测试无提供商配置时"""
        with patch.dict(os.environ, {}, clear=True):
            service = LlmService.from_env()
            assert not service.is_configured()
            assert service.list_providers() == []

    def test_from_env_with_provider(self):
        """测试有提供商配置时"""
        with patch.dict(os.environ, {
            "KIMI_LLM_API_KEY": "test-key",
            "KIMI_LLM_BASE_URL": "https://api.moonshot.cn/v1/chat/completions",
        }, clear=False):
            service = LlmService.from_env()
            assert service.is_configured()
            assert service.default_provider == "kimi"
            providers = service.list_providers()
            assert len(providers) == 1
            assert providers[0]["name"] == "kimi"

    def test_from_env_override_provider(self):
        """测试指定提供商"""
        with patch.dict(os.environ, {
            "KIMI_LLM_API_KEY": "kimi-key",
            "KIMI_LLM_BASE_URL": "https://api.moonshot.cn/v1/chat/completions",
            "OPENAI_LLM_API_KEY": "openai-key",
            "OPENAI_LLM_BASE_URL": "https://api.openai.com/v1/chat/completions",
            "STOCK_ASSISTANT_LLM_PROVIDER": "openai",
        }, clear=False):
            service = LlmService.from_env()
            assert service.default_provider == "openai"

    def test_chat_unconfigured_raises(self):
        """测试未配置时调用 chat 抛出异常"""
        service = LlmService({}, "kimi")
        with pytest.raises(LlmConfigError) as exc_info:
            service.chat([{"role": "user", "content": "hello"}])
        assert "kimi" in str(exc_info.value)

    def test_get_config(self):
        """测试获取配置"""
        cfg = LlmProviderConfig(
            name="test",
            api_key="key",
            model="model",
            base_url="https://test.com",
        )
        service = LlmService({"test": cfg}, "test")
        assert service.get_config() == cfg
        assert service.get_config("test") == cfg
        assert service.get_config("missing") is None


class TestExtractContent:
    """测试内容提取"""

    def test_standard_content(self):
        """测试标准内容格式"""
        payload = {
            "choices": [{"message": {"content": "Hello world"}}]
        }
        assert _extract_content(payload) == "Hello world"

    def test_reasoning_content_fallback(self):
        """测试 reasoning_content 回退"""
        payload = {
            "choices": [{"message": {"content": "", "reasoning_content": "Reasoning here"}}]
        }
        assert _extract_content(payload) == "Reasoning here"

    def test_list_content_parts(self):
        """测试列表格式内容"""
        payload = {
            "choices": [{"message": {"content": [
                {"type": "text", "text": "Part 1"},
                {"type": "text", "text": "Part 2"},
            ]}}]
        }
        assert _extract_content(payload) == "Part 1\nPart 2"

    def test_empty_choices(self):
        """测试空 choices"""
        assert _extract_content({"choices": []}) == ""
        assert _extract_content({}) == ""


class TestExtractToolCalls:
    """测试工具调用提取"""

    def test_standard_tool_calls(self):
        """测试标准工具调用格式"""
        payload = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "get_stock_price",
                            "arguments": '{"symbol": "000001"}',
                        },
                    }]
                }
            }]
        }
        calls = _extract_tool_calls(payload)
        assert len(calls) == 1
        assert calls[0]["name"] == "get_stock_price"
        assert calls[0]["arguments"]["symbol"] == "000001"

    def test_dict_arguments(self):
        """测试字典格式参数"""
        payload = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "test",
                            "arguments": {"key": "value"},
                        },
                    }]
                }
            }]
        }
        calls = _extract_tool_calls(payload)
        assert calls[0]["arguments"]["key"] == "value"

    def test_invalid_json_arguments(self):
        """测试无效 JSON 参数"""
        payload = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "test",
                            "arguments": "invalid json",
                        },
                    }]
                }
            }]
        }
        calls = _extract_tool_calls(payload)
        assert calls[0]["arguments"] == {}

    def test_no_tool_calls(self):
        """测试无工具调用"""
        assert _extract_tool_calls({"choices": [{"message": {}}]}) == []
