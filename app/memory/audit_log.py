"""
UF Stock Assistant — Agent Gateway 审计日志
记录每个 Agent Token 调用的 route、scope、status、duration
参考 QuantDinger 审计日志设计
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, func
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.memory.audit_log")

Base = declarative_base()


class AuditLogModel(Base):
    """Agent 审计日志表"""
    __tablename__ = "agent_audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String(64), nullable=False, index=True)
    token_name = Column(String(128), nullable=True)
    scope = Column(String(16), nullable=False)
    route = Column(String(256), nullable=False)
    method = Column(String(16), nullable=False)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    request_body = Column(Text, nullable=True)
    response_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditLogStore:
    """
    审计日志存储管理器
    
    职责：
    1. 记录每次 Agent Gateway 调用
    2. 按 Token hash 查询历史
    3. 自动清理过期日志
    """
    
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or get_settings().database.url
        self._engine = create_engine(self._database_url, echo=False, future=True)
        self._session_factory = sessionmaker(bind=self._engine)
        self._ensure_tables()
    
    def _ensure_tables(self) -> None:
        """确保审计日志表存在"""
        Base.metadata.create_all(self._engine)
    
    def _get_session(self) -> Session:
        return self._session_factory()
    
    def log(
        self,
        token_hash: str,
        scope: str,
        route: str,
        method: str,
        status_code: int,
        duration_ms: int,
        token_name: str | None = None,
        request_body: dict[str, Any] | None = None,
        response_summary: str | None = None,
    ) -> int:
        """
        记录一次 Agent 调用
        
        Returns:
            日志记录 ID
        """
        try:
            with self._get_session() as session:
                log = AuditLogModel(
                    token_hash=token_hash,
                    token_name=token_name,
                    scope=scope,
                    route=route,
                    method=method,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    request_body=json.dumps(request_body, ensure_ascii=False, default=str)[:2000] if request_body else None,
                    response_summary=response_summary[:1000] if response_summary else None,
                )
                session.add(log)
                session.commit()
                log_id = log.id
                
            logger.info(
                "agent_audit_logged",
                log_id=log_id,
                route=route,
                scope=scope,
                status=status_code,
                duration_ms=duration_ms,
            )
            return log_id
        except Exception as exc:
            logger.error("audit_log_failed", error=str(exc), route=route)
            return -1
    
    def query_by_token(
        self,
        token_hash: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """按 Token hash 查询审计日志"""
        with self._get_session() as session:
            logs = (
                session.query(AuditLogModel)
                .filter(AuditLogModel.token_hash == token_hash)
                .order_by(AuditLogModel.created_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            return [
                {
                    "id": log.id,
                    "scope": log.scope,
                    "route": log.route,
                    "method": log.method,
                    "status_code": log.status_code,
                    "duration_ms": log.duration_ms,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ]
    
    def cleanup_old_logs(self, retention_days: int | None = None) -> int:
        """
        清理过期审计日志
        
        Returns:
            删除的记录数
        """
        if retention_days is None:
            retention_days = get_settings().agent.audit_log_retention_days
        
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = cutoff.timestamp() - retention_days * 86400
        
        try:
            with self._get_session() as session:
                from sqlalchemy import delete
                stmt = delete(AuditLogModel).where(
                    func.strftime("%s", AuditLogModel.created_at) < str(int(cutoff))
                )
                result = session.execute(stmt)
                session.commit()
                deleted = result.rowcount
                logger.info("audit_log_cleanup", deleted=deleted, retention_days=retention_days)
                return deleted
        except Exception as exc:
            logger.error("audit_log_cleanup_failed", error=str(exc))
            return 0
    
    def get_stats(self, token_hash: str | None = None) -> dict[str, Any]:
        """获取审计统计"""
        with self._get_session() as session:
            query = session.query(AuditLogModel)
            if token_hash:
                query = query.filter(AuditLogModel.token_hash == token_hash)
            
            total = query.count()
            recent_24h = query.filter(
                func.strftime("%s", AuditLogModel.created_at) > str(int(time.time()) - 86400)
            ).count()
            
            return {
                "total_logs": total,
                "recent_24h": recent_24h,
            }
