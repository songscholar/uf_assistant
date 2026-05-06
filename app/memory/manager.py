"""
UF Stock Assistant — 记忆管理器
整合对话存储与上下文压缩，提供统一的上下文获取接口
"""

from __future__ import annotations

from typing import Any

from app.core.constants import CONTEXT_COMPRESS_TARGET
from app.core.exceptions import MemoryError
from app.core.llm_adapter import LlmService
from app.core.logging import get_logger

from .compressor import ContextCompressor
from .conversation import ConversationStore

logger = get_logger("app.memory.manager")


class MemoryManager:
    """
    记忆管理器
    
    职责：
    1. 管理对话历史的持久化存储
    2. 监控对话长度，自动触发上下文压缩
    3. 组装适合 LLM 的上下文（摘要 + 最近消息 + 系统提示）
    """
    
    def __init__(
        self,
        store: ConversationStore | None = None,
        compressor: ContextCompressor | None = None,
    ) -> None:
        self._store = store or ConversationStore()
        self._compressor = compressor
    
    @classmethod
    def from_env(cls) -> "MemoryManager":
        """从环境变量创建记忆管理器"""
        store = ConversationStore()
        compressor = ContextCompressor.from_env()
        return cls(store=store, compressor=compressor)
    
    def create_conversation(
        self,
        user_id: str = "default",
        title: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """
        创建新会话
        
        Args:
            user_id: 用户标识
            title: 会话标题
            system_prompt: 系统提示词（将作为第一条消息存入）
            
        Returns:
            会话 ID
        """
        conversation_id = self._store.create_conversation(user_id=user_id, title=title)
        
        if system_prompt:
            self._store.add_message(
                conversation_id=conversation_id,
                role="system",
                content=system_prompt,
                metadata={"type": "system_prompt"},
            )
        
        logger.info(
            "conversation_initialized",
            conversation_id=conversation_id,
            user_id=user_id,
            has_system_prompt=bool(system_prompt),
        )
        return conversation_id
    
    def add_user_message(
        self,
        conversation_id: str,
        content: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> int:
        """添加用户消息"""
        metadata = {"attachments": attachments} if attachments else None
        return self._store.add_message(
            conversation_id=conversation_id,
            role="user",
            content=content,
            metadata=metadata,
        )
    
    def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> int:
        """添加助手消息"""
        metadata = {"tool_calls": tool_calls} if tool_calls else None
        return self._store.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            metadata=metadata,
        )
    
    def add_tool_message(
        self,
        conversation_id: str,
        tool_call_id: str,
        content: str,
    ) -> int:
        """添加工具执行结果消息"""
        return self._store.add_message(
            conversation_id=conversation_id,
            role="tool",
            content=content,
            metadata={"tool_call_id": tool_call_id},
        )
    
    def get_context(
        self,
        conversation_id: str,
        include_system: bool = True,
    ) -> list[dict[str, Any]]:
        """
        获取组装好的 LLM 上下文
        
        返回格式为 OpenAI 消息格式：
        [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
        ]
        
        逻辑：
        1. 获取会话信息和消息
        2. 如果已压缩，在 system 消息中附加摘要
        3. 检查消息数量，需要时触发压缩
        4. 返回组装后的上下文
        """
        # 获取会话信息
        conv = self._store.get_conversation(conversation_id)
        if not conv:
            raise MemoryError(f"会话不存在: {conversation_id}")
        
        # 获取所有消息（正序）
        messages = self._store.get_messages(
            conversation_id=conversation_id,
            limit=1000,  # 足够大的限制
            include_system=include_system,
        )
        
        # 检查是否需要压缩
        msg_count = self._store.get_message_count(
            conversation_id=conversation_id,
            include_system=False,
        )
        
        if self._compressor and self._compressor.should_compress(msg_count):
            logger.info(
                "compression_triggered",
                conversation_id=conversation_id,
                message_count=msg_count,
                threshold=self._compressor.threshold,
            )
            self._perform_compression(conversation_id, messages)
            # 重新获取消息（压缩后）
            messages = self._store.get_messages(
                conversation_id=conversation_id,
                limit=1000,
                include_system=include_system,
            )
        
        # 组装上下文
        context = []
        
        # 如果有摘要，作为 system 消息的一部分
        if conv.get("summary") and conv.get("is_compressed"):
            summary_text = f"【历史对话摘要】{conv['summary']}"
            
            # 找到现有的 system 消息并附加摘要，或创建新的
            system_msg = None
            for msg in messages:
                if msg["role"] == "system":
                    system_msg = msg
                    break
            
            if system_msg:
                system_msg["content"] = f"{system_msg['content']}\n\n{summary_text}"
                context.append(system_msg)
            else:
                context.append({"role": "system", "content": summary_text})
            
            # 添加非 system 消息
            for msg in messages:
                if msg["role"] != "system":
                    context.append({
                        "role": msg["role"],
                        "content": msg["content"],
                    })
        else:
            # 无压缩，直接返回所有消息
            for msg in messages:
                context.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })
        
        return context
    
    def _perform_compression(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """执行压缩操作"""
        if not self._compressor:
            return
        
        try:
            # 过滤出可压缩的消息（排除 system）
            compressible = [m for m in messages if m["role"] != "system"]
            
            summary, keep_recent = self._compressor.compress(compressible)
            
            # 更新会话摘要
            self._store.update_summary(conversation_id, summary, is_compressed=True)
            
            # 清空旧消息，保留最近消息
            self._store.clear_messages(conversation_id)
            
            # 重新添加 system 消息（如果存在）
            system_messages = [m for m in messages if m["role"] == "system"]
            for msg in system_messages:
                self._store.add_message(
                    conversation_id=conversation_id,
                    role="system",
                    content=msg["content"],
                    metadata=msg.get("metadata"),
                )
            
            # 添加保留的最近消息
            for msg in keep_recent:
                self._store.add_message(
                    conversation_id=conversation_id,
                    role=msg["role"],
                    content=msg["content"],
                    metadata=msg.get("metadata"),
                )
            
            logger.info(
                "compression_completed",
                conversation_id=conversation_id,
                summary_length=len(summary),
                kept_messages=len(keep_recent),
            )
            
        except Exception as exc:
            logger.error("compression_failed", conversation_id=conversation_id, error=str(exc))
            raise MemoryError(f"上下文压缩失败: {exc}") from exc
    
    def get_conversation_info(self, conversation_id: str) -> dict[str, Any] | None:
        """获取会话信息"""
        return self._store.get_conversation(conversation_id)
    
    def list_conversations(
        self,
        user_id: str = "default",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """列出用户会话"""
        return self._store.list_conversations(user_id=user_id, limit=limit)
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """删除会话"""
        return self._store.delete_conversation(conversation_id)
    
    def get_stats(self, conversation_id: str) -> dict[str, Any]:
        """获取会话统计信息"""
        conv = self._store.get_conversation(conversation_id)
        if not conv:
            raise MemoryError(f"会话不存在: {conversation_id}")
        
        msg_count = self._store.get_message_count(conversation_id, include_system=False)
        
        return {
            "conversation_id": conversation_id,
            "message_count": msg_count,
            "is_compressed": conv.get("is_compressed", False),
            "has_summary": bool(conv.get("summary")),
            "created_at": conv.get("created_at"),
            "updated_at": conv.get("updated_at"),
            "compression_threshold": self._compressor.threshold if self._compressor else None,
            "needs_compression": self._compressor.should_compress(msg_count) if self._compressor else False,
        }
