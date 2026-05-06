"""
UF Stock Assistant — 上下文自动压缩
当对话轮数超过阈值时，使用 LLM 将历史对话总结为摘要
"""

from __future__ import annotations

from typing import Any

from app.core.constants import CONTEXT_COMPRESS_TARGET, CONTEXT_COMPRESS_THRESHOLD
from app.core.exceptions import CompressionError
from app.core.llm_adapter import LlmService
from app.core.logging import get_logger

logger = get_logger("app.memory.compressor")


COMPRESSION_PROMPT = """你是一位专业的对话摘要助手。请将以下用户与股票助手之间的对话历史总结为简洁的摘要。

要求：
1. 保留所有关键的股票代码、交易决策、策略名称、市场分析结论
2. 保留用户明确表达的投资偏好和风险承受能力
3. 保留用户持仓信息和交易记录
4. 摘要应包含：讨论过的主题、做出的决策、待跟进的事项
5. 使用中文输出
6. 控制在 300 字以内

对话历史：
{history}

请输出摘要："""


class ContextCompressor:
    """
    上下文压缩器
    
    当对话消息数超过阈值时，自动触发压缩：
    1. 提取历史对话（排除 system 消息）
    2. 调用 LLM 生成摘要
    3. 将摘要保存到会话，清空旧消息（保留最近的 N 轮）
    """
    
    def __init__(
        self,
        llm_service: LlmService | None = None,
        threshold: int = CONTEXT_COMPRESS_THRESHOLD,
        keep_recent: int = CONTEXT_COMPRESS_TARGET,
    ) -> None:
        self._llm_service = llm_service
        self._threshold = threshold
        self._keep_recent = keep_recent
    
    @classmethod
    def from_env(cls, **kwargs: Any) -> "ContextCompressor":
        """从环境变量创建压缩器"""
        service = LlmService.from_env()
        return cls(llm_service=service, **kwargs)
    
    def should_compress(self, message_count: int) -> bool:
        """
        判断是否需要压缩
        
        Args:
            message_count: 当前消息数量（不含 system）
            
        Returns:
            是否需要压缩
        """
        return message_count >= self._threshold
    
    def compress(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        压缩对话历史
        
        Args:
            messages: 完整消息列表
            
        Returns:
            (摘要文本, 保留的最近消息列表)
        """
        if not self._llm_service or not self._llm_service.is_configured():
            logger.warning("llm_not_configured_fallback")
            # LLM 未配置时，使用简单截断策略
            return self._fallback_compress(messages)
        
        if len(messages) <= self._keep_recent:
            return "", messages
        
        # 分离需要压缩的历史和保留的最近消息
        to_compress = messages[:-self._keep_recent]
        keep_recent = messages[-self._keep_recent:]
        
        # 构建历史文本
        history_text = self._format_history(to_compress)
        
        try:
            # 调用 LLM 生成摘要
            result = self._llm_service.chat([
                {"role": "system", "content": "你是一位专业的对话摘要助手。"},
                {"role": "user", "content": COMPRESSION_PROMPT.format(history=history_text)},
            ])
            
            summary = result.get("content", "").strip()
            if not summary:
                raise CompressionError("LLM 返回空摘要")
            
            logger.info(
                "context_compressed",
                original_messages=len(messages),
                compressed_messages=len(to_compress),
                kept_messages=len(keep_recent),
                summary_length=len(summary),
            )
            
            return summary, keep_recent
            
        except Exception as exc:
            logger.error("compression_failed", error=str(exc))
            raise CompressionError(f"压缩失败: {exc}") from exc
    
    def _fallback_compress(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        fallback 压缩策略（LLM 不可用时）
        
        策略：保留最近消息，对早期消息做简单文本截断
        """
        if len(messages) <= self._keep_recent:
            return "", messages
        
        to_compress = messages[:-self._keep_recent]
        keep_recent = messages[-self._keep_recent:]
        
        # 简单提取关键信息作为摘要
        topics = set()
        for msg in to_compress:
            content = msg.get("content", "")
            # 提取可能的股票代码（简单模式匹配）
            import re
            codes = re.findall(r'\b\d{6}\b', content)
            topics.update(codes)
        
        summary = f"历史对话涉及股票: {', '.join(topics)}" if topics else "历史对话（已压缩）"
        
        logger.info(
            "fallback_compression_used",
            original_messages=len(messages),
            summary=summary,
        )
        
        return summary, keep_recent
    
    def _format_history(self, messages: list[dict[str, Any]]) -> str:
        """将消息列表格式化为文本"""
        lines = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            role_label = {"user": "用户", "assistant": "助手", "tool": "工具"}.get(role, role)
            lines.append(f"{role_label}: {content}")
        return "\n\n".join(lines)
    
    @property
    def threshold(self) -> int:
        return self._threshold
    
    @property
    def keep_recent(self) -> int:
        return self._keep_recent
