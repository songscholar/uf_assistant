"""
UF Stock Assistant — 对话历史管理
基于 SQLAlchemy 的对话持久化存储
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, create_engine, func
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings
from app.core.constants import DEFAULT_HISTORY_LIMIT
from app.core.exceptions import MemoryError
from app.core.logging import get_logger

logger = get_logger("app.memory.conversation")

Base = declarative_base()


class ConversationModel(Base):
    """会话表"""
    __tablename__ = "conversations"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), nullable=False, index=True, default="default")
    title = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    is_compressed = Column(Integer, default=0)  # 0=False, 1=True
    summary = Column(Text, nullable=True)  # 压缩后的摘要
    metadata_json = Column("metadata", JSON, nullable=True)


class MessageModel(Base):
    """消息表"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    role = Column(String(32), nullable=False)  # system, user, assistant, tool
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    metadata_json = Column("metadata", JSON, nullable=True)  # 附件、工具调用等


class ConversationStore:
    """
    对话存储管理器
    提供会话和消息的 CRUD 操作
    """
    
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or get_settings().database.url
        self._engine = create_engine(self._database_url, echo=False, future=True)
        self._session_factory = sessionmaker(bind=self._engine)
        self._ensure_tables()
    
    def _ensure_tables(self) -> None:
        """确保数据表存在"""
        Base.metadata.create_all(self._engine)
    
    def _get_session(self) -> Session:
        """获取数据库会话"""
        return self._session_factory()
    
    def create_conversation(
        self,
        user_id: str = "default",
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        创建新会话
        
        Returns:
            会话 ID
        """
        conversation_id = str(uuid.uuid4())
        session = self._get_session()
        try:
            conv = ConversationModel(
                id=conversation_id,
                user_id=user_id,
                title=title or f"会话 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
                metadata_json=metadata,
            )
            session.add(conv)
            session.commit()
            logger.info(
                "conversation_created",
                conversation_id=conversation_id,
                user_id=user_id,
            )
            return conversation_id
        except Exception as exc:
            session.rollback()
            raise MemoryError(f"创建会话失败: {exc}") from exc
        finally:
            session.close()
    
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """
        添加消息到会话
        
        Returns:
            消息 ID
        """
        session = self._get_session()
        try:
            msg = MessageModel(
                conversation_id=conversation_id,
                role=role,
                content=content,
                metadata_json=metadata,
            )
            session.add(msg)
            session.commit()
            msg_id = msg.id
            
            # 更新会话时间
            conv = session.query(ConversationModel).filter_by(id=conversation_id).first()
            if conv:
                conv.updated_at = datetime.now(timezone.utc)
                session.add(conv)
                session.commit()
            
            logger.debug(
                "message_added",
                conversation_id=conversation_id,
                role=role,
                msg_id=msg_id,
            )
            return msg_id
        except Exception as exc:
            session.rollback()
            raise MemoryError(f"添加消息失败: {exc}") from exc
        finally:
            session.close()
    
    def get_messages(
        self,
        conversation_id: str,
        limit: int = DEFAULT_HISTORY_LIMIT,
        offset: int = 0,
        include_system: bool = True,
    ) -> list[dict[str, Any]]:
        """
        获取会话消息历史
        
        Args:
            conversation_id: 会话 ID
            limit: 返回消息数量上限
            offset: 偏移量
            include_system: 是否包含 system 消息
            
        Returns:
            消息列表，按时间正序排列
        """
        session = self._get_session()
        try:
            query = (
                session.query(MessageModel)
                .filter_by(conversation_id=conversation_id)
                .order_by(MessageModel.created_at.desc())
            )
            
            if not include_system:
                query = query.filter(MessageModel.role != "system")
            
            messages = query.offset(offset).limit(limit).all()
            
            # 转换为 dict 并反转回正序
            result = []
            for msg in reversed(messages):
                result.append({
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    "metadata": msg.metadata_json,
                })
            
            return result
        except Exception as exc:
            raise MemoryError(f"获取消息失败: {exc}") from exc
        finally:
            session.close()
    
    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """获取会话信息"""
        session = self._get_session()
        try:
            conv = session.query(ConversationModel).filter_by(id=conversation_id).first()
            if not conv:
                return None
            return {
                "id": conv.id,
                "user_id": conv.user_id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "is_compressed": bool(conv.is_compressed),
                "summary": conv.summary,
                "metadata": conv.metadata_json,
            }
        except Exception as exc:
            raise MemoryError(f"获取会话失败: {exc}") from exc
        finally:
            session.close()
    
    def list_conversations(
        self,
        user_id: str = "default",
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """列出用户的会话列表"""
        session = self._get_session()
        try:
            convs = (
                session.query(ConversationModel)
                .filter_by(user_id=user_id)
                .order_by(ConversationModel.updated_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": c.id,
                    "title": c.title,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                    "is_compressed": bool(c.is_compressed),
                }
                for c in convs
            ]
        except Exception as exc:
            raise MemoryError(f"列会话失败: {exc}") from exc
        finally:
            session.close()
    
    def update_summary(
        self,
        conversation_id: str,
        summary: str,
        is_compressed: bool = True,
    ) -> None:
        """更新会话摘要（压缩后使用）"""
        session = self._get_session()
        try:
            conv = session.query(ConversationModel).filter_by(id=conversation_id).first()
            if conv:
                conv.summary = summary
                conv.is_compressed = 1 if is_compressed else 0
                session.commit()
                logger.info(
                    "conversation_summary_updated",
                    conversation_id=conversation_id,
                    is_compressed=is_compressed,
                )
        except Exception as exc:
            session.rollback()
            raise MemoryError(f"更新摘要失败: {exc}") from exc
        finally:
            session.close()
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """删除会话及其所有消息"""
        session = self._get_session()
        try:
            # 删除消息
            session.query(MessageModel).filter_by(conversation_id=conversation_id).delete()
            # 删除会话
            result = session.query(ConversationModel).filter_by(id=conversation_id).delete()
            session.commit()
            logger.info("conversation_deleted", conversation_id=conversation_id, deleted=bool(result))
            return bool(result)
        except Exception as exc:
            session.rollback()
            raise MemoryError(f"删除会话失败: {exc}") from exc
        finally:
            session.close()
    
    def get_message_count(self, conversation_id: str, include_system: bool = True) -> int:
        """获取会话消息数量"""
        session = self._get_session()
        try:
            query = session.query(MessageModel).filter_by(conversation_id=conversation_id)
            if not include_system:
                query = query.filter(MessageModel.role != "system")
            return query.count()
        except Exception as exc:
            raise MemoryError(f"统计消息失败: {exc}") from exc
        finally:
            session.close()
    
    def clear_messages(self, conversation_id: str) -> None:
        """清空会话消息（保留会话本身）"""
        session = self._get_session()
        try:
            session.query(MessageModel).filter_by(conversation_id=conversation_id).delete()
            session.commit()
            logger.info("messages_cleared", conversation_id=conversation_id)
        except Exception as exc:
            session.rollback()
            raise MemoryError(f"清空消息失败: {exc}") from exc
        finally:
            session.close()
