"""
UF Stock Assistant — LLM 统一调用层
参考 condex 项目 (uses-indexer) 的 LlmService 设计
支持多提供商切换，兼容 LangChain BaseChatModel 接口
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterator
from urllib import error, request

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from .exceptions import LlmConfigError, LlmRequestError
from .logging import get_logger

logger = get_logger("app.core.llm")

# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------

_PROVIDER_ENV_PREFIXES: dict[str, str] = {
    "kimi": "KIMI_LLM",
    "xiaomi": "XIAOMI_LLM",
    "openai": "OPENAI_LLM",
    "deepseek": "DEEPSEEK_LLM",
}

_PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "kimi": "kimi-k2",
    "xiaomi": "mimo-v2.5-pro",
    "openai": "gpt-4o",
    "deepseek": "deepseek-chat",
}


@dataclass(slots=True)
class LlmProviderConfig:
    """LLM 提供商配置"""
    name: str
    api_key: str
    model: str
    base_url: str
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout_seconds: float = 180.0
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    user_agent: str | None = None


def _load_provider_config(name: str) -> LlmProviderConfig | None:
    """从环境变量加载单个提供商配置"""
    prefix = _PROVIDER_ENV_PREFIXES.get(name)
    if not prefix:
        return None

    api_key = os.getenv(f"{prefix}_API_KEY", "").strip()
    base_url = os.getenv(f"{prefix}_BASE_URL", "").strip()
    model = os.getenv(f"{prefix}_MODEL", "").strip() or _PROVIDER_DEFAULT_MODELS.get(name, "")

    if not api_key or not base_url:
        return None

    return LlmProviderConfig(
        name=name,
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=float(os.getenv(f"{prefix}_TEMPERATURE", "0.1")),
        max_tokens=int(os.getenv(f"{prefix}_MAX_TOKENS", "4096")),
        timeout_seconds=float(os.getenv(f"{prefix}_TIMEOUT", "180")),
        max_retries=int(os.getenv(f"{prefix}_MAX_RETRIES", "2")),
        retry_backoff_seconds=float(os.getenv(f"{prefix}_RETRY_BACKOFF", "1.0")),
        user_agent=os.getenv(f"{prefix}_USER_AGENT") or None,
    )


# ---------------------------------------------------------------------------
# LlmService — 统一调用入口（参考 condex 项目）
# ---------------------------------------------------------------------------

class LlmService:
    """
    统一 LLM 调用入口，参考 condex 项目的 LlmService 设计
    支持多提供商路由、参数覆盖、重试机制
    """

    def __init__(
        self,
        providers: dict[str, LlmProviderConfig],
        default_provider: str,
    ) -> None:
        self._providers = providers
        self._default_provider = default_provider

    @classmethod
    def from_env(cls, provider: str | None = None) -> "LlmService":
        """从环境变量创建 LLM 服务实例"""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        default = provider or os.getenv("STOCK_ASSISTANT_LLM_PROVIDER", "kimi").strip() or "kimi"

        providers: dict[str, LlmProviderConfig] = {}
        for name in _PROVIDER_ENV_PREFIXES:
            cfg = _load_provider_config(name)
            if cfg is not None:
                providers[name] = cfg

        if default not in providers:
            if providers:
                default = next(iter(providers))
            else:
                return cls({}, default)

        return cls(providers, default)

    @property
    def default_provider(self) -> str:
        return self._default_provider

    def is_configured(self, provider: str | None = None) -> bool:
        name = provider or self._default_provider
        return name in self._providers

    def list_providers(self) -> list[dict[str, Any]]:
        """列出所有已配置的提供商"""
        return [
            {
                "name": cfg.name,
                "model": cfg.model,
                "base_url": cfg.base_url,
                "default": cfg.name == self._default_provider,
            }
            for cfg in self._providers.values()
        ]

    def get_config(self, provider: str | None = None) -> LlmProviderConfig | None:
        name = provider or self._default_provider
        return self._providers.get(name)

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        统一 LLM 调用
        
        Returns:
            {
                "provider": str,
                "model": str,
                "base_url": str,
                "content": str,
                "tool_calls": list[dict],
                "usage": dict | None,
                "raw_response": dict,
            }
        """
        name = provider or self._default_provider
        cfg = self._providers.get(name)
        if cfg is None:
            raise LlmConfigError(
                f"LLM provider '{name}' is not configured. "
                f"Available: {list(self._providers.keys())}. "
                f"Set {name.upper()}_LLM_API_KEY and {name.upper()}_LLM_BASE_URL in .env."
            )

        effective_model = model or cfg.model
        effective_temperature = temperature if temperature is not None else cfg.temperature
        effective_max_tokens = max_tokens if max_tokens is not None else cfg.max_tokens
        effective_timeout = timeout if timeout is not None else cfg.timeout_seconds

        payload: dict[str, Any] = {
            "model": effective_model,
            "temperature": effective_temperature,
            "max_tokens": effective_max_tokens,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        if cfg.user_agent:
            headers["User-Agent"] = cfg.user_agent

        http_request = request.Request(
            cfg.base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        started_at = time.perf_counter()
        try:
            raw = _perform_request(http_request, cfg, effective_timeout)
        except Exception as exc:
            logger.error(
                "llm_request_failed",
                message=str(exc),
                provider=name,
                model=effective_model,
                base_url=cfg.base_url,
            )
            raise LlmRequestError(f"LLM request failed: {exc}") from exc

        parsed = json.loads(raw)
        content = _extract_content(parsed)
        tool_calls = _extract_tool_calls(parsed)

        if not content and not tool_calls:
            exc = LlmRequestError("LLM response did not contain assistant content or tool calls")
            logger.error(
                "llm_empty_response",
                message=str(exc),
                provider=name,
                model=effective_model,
            )
            raise exc

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "llm_chat_completed",
            provider=name,
            model=effective_model,
            latency_ms=latency_ms,
            prompt_chars=sum(len(str(m.get("content", ""))) for m in messages),
            response_chars=len(content or ""),
            has_tool_calls=bool(tool_calls),
        )

        return {
            "provider": name,
            "model": effective_model,
            "base_url": cfg.base_url,
            "content": content,
            "tool_calls": tool_calls,
            "usage": parsed.get("usage"),
            "raw_response": parsed,
        }


# ---------------------------------------------------------------------------
# HTTP request with retry
# ---------------------------------------------------------------------------

def _perform_request(
    http_request: request.Request,
    cfg: LlmProviderConfig,
    timeout: float | None = None,
) -> str:
    effective_timeout = timeout if timeout is not None else cfg.timeout_seconds
    attempts = cfg.max_retries + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            with request.urlopen(http_request, timeout=effective_timeout) as resp:
                return resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = LlmRequestError(f"LLM request failed with status {exc.code}: {detail}")
        except error.URLError as exc:
            last_error = LlmRequestError(f"LLM request failed: {exc.reason}")
        except TimeoutError as exc:
            last_error = LlmRequestError(f"LLM request timed out: {exc}")

        if attempt < attempts:
            time.sleep(cfg.retry_backoff_seconds * attempt)

    if last_error is not None:
        raise last_error
    raise LlmRequestError("LLM request failed for an unknown reason")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first = choices[0]
    if not isinstance(first, dict):
        return ""

    message = first.get("message")
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    # Kimi-style reasoning_content fallback
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning.strip()

    # List-of-text-parts format
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        return "\n".join(part.strip() for part in text_parts if part.strip())

    return ""


def _extract_tool_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tool calls from OpenAI-format response"""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return []

    first = choices[0]
    if not isinstance(first, dict):
        return []

    message = first.get("message")
    if not isinstance(message, dict):
        return []

    raw_calls = message.get("tool_calls")
    if not isinstance(raw_calls, list):
        return []

    result: list[dict[str, Any]] = []
    for tc in raw_calls:
        if not isinstance(tc, dict):
            continue
        func = tc.get("function")
        if not isinstance(func, dict):
            continue
        name = func.get("name", "")
        raw_args = func.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}
        result.append({
            "id": tc.get("id", ""),
            "name": name,
            "arguments": args,
        })

    return result


# ---------------------------------------------------------------------------
# LangChain 兼容适配器
# ---------------------------------------------------------------------------

class LangChainLlmAdapter(BaseChatModel):
    """
    LangChain 兼容的 LLM 适配器
    将 LlmService 包装为 LangChain BaseChatModel，可直接用于 Agent
    """

    llm_service: LlmService = Field(description="底层 LLM 服务")
    provider: str | None = Field(default=None, description="指定提供商（None 使用默认）")
    model: str | None = Field(default=None, description="指定模型（None 使用配置默认）")
    temperature: float | None = Field(default=None, description="温度参数")
    max_tokens: int | None = Field(default=None, description="最大 token 数")
    timeout: float | None = Field(default=None, description="超时时间")

    @property
    def _llm_type(self) -> str:
        return "uf_llm_adapter"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "provider": self.provider or self.llm_service.default_provider,
            "model": self.model,
            "temperature": self.temperature,
        }

    def _convert_messages(
        self, messages: list[BaseMessage]
    ) -> list[dict[str, Any]]:
        """将 LangChain Message 转换为 OpenAI 格式"""
        result: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                ai_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    ai_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"], ensure_ascii=False),
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                result.append(ai_msg)
            elif isinstance(msg, ToolMessage):
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })
            else:
                result.append({"role": "user", "content": str(msg.content)})
        return result

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """同步生成（LangChain 接口）"""
        openai_messages = self._convert_messages(messages)
        
        result = self.llm_service.chat(
            openai_messages,
            provider=self.provider,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            tools=kwargs.get("tools"),
            response_format=kwargs.get("response_format"),
        )

        message = AIMessage(content=result["content"] or "")
        if result["tool_calls"]:
            message.tool_calls = [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "args": tc["arguments"],
                }
                for tc in result["tool_calls"]
            ]
            message.additional_kwargs["tool_calls"] = result["tool_calls"]

        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGeneration]:
        """流式生成（当前退化为同步，后续可扩展 SSE）"""
        result = self._generate(messages, stop, run_manager, **kwargs)
        yield result.generations[0]

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGeneration]:
        """异步流式生成"""
        result = self._generate(messages, stop, run_manager, **kwargs)
        yield result.generations[0]

    @classmethod
    def from_env(cls, provider: str | None = None, **kwargs: Any) -> "LangChainLlmAdapter":
        """从环境变量创建适配器"""
        service = LlmService.from_env(provider)
        return cls(llm_service=service, provider=provider, **kwargs)
