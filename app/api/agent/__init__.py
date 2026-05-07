"""
UF Stock Assistant — Agent Gateway 路由注册
提供 /api/agent/v1 下的所有端点
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.agent_auth import AgentAuthManager, AgentTokenRecord
from app.core.constants import AgentScope
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.memory.audit_log import AuditLogStore

logger = get_logger("app.api.agent")

# Security scheme
agent_bearer = HTTPBearer(auto_error=False)

# Global audit log store
_audit_store: AuditLogStore | None = None


def _get_audit_store() -> AuditLogStore:
    global _audit_store
    if _audit_store is None:
        _audit_store = AuditLogStore()
    return _audit_store


async def verify_agent_token(
    credentials: HTTPAuthorizationCredentials | None = Security(agent_bearer),
) -> AgentTokenRecord:
    """FastAPI 依赖：验证 Agent Token"""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing agent token")
    try:
        return AgentAuthManager.verify_token(credentials.credentials)
    except ValidationError as exc:
        raise HTTPException(status_code=401, detail=exc.message)


def require_scope(scope: str):
    """FastAPI 依赖工厂：检查指定 Scope"""
    def _check_scope(record: AgentTokenRecord = Depends(verify_agent_token)) -> AgentTokenRecord:
        try:
            AgentAuthManager.require_scope(record, scope)
        except ValidationError as exc:
            raise HTTPException(status_code=403, detail=exc.message)
        return record
    return _check_scope


# 创建子路由
from .markets import router as markets_router
from .chat import router as chat_router
from .strategies import router as strategies_router
from .trading import router as trading_router

router = APIRouter(prefix="/agent/v1")

router.include_router(markets_router, prefix="/markets", tags=["Agent-市场"])
router.include_router(chat_router, prefix="/chat", tags=["Agent-对话"])
router.include_router(strategies_router, prefix="/strategies", tags=["Agent-策略"])
router.include_router(trading_router, prefix="/trading", tags=["Agent-交易"])
