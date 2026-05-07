"""
UF Stock Assistant — Agent Gateway 路由注册
提供 /api/agent/v1 下的所有端点

参考 QuantDinger Agent Gateway 设计：
  - 统一错误格式 {code, message, details, retriable}
  - 每请求审计日志
  - 速率限制（含 X-RateLimit-* 响应头）
  - markets / instruments 白名单
  - 幂等性（Idempotency-Key）
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
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
    credentials: HTTPAuthorizationCredentials | None = Depends(agent_bearer),
) -> AgentTokenRecord:
    """FastAPI 依赖：验证 Agent Token

    抛出 ValidationError（由全局异常处理器转换为统一错误格式）
    """
    if not credentials or not credentials.credentials:
        raise ValidationError(
            "Missing agent token",
            details={"code": "INVALID_TOKEN"},
        )
    return AgentAuthManager.verify_token(credentials.credentials)


def require_scope(scope: str):
    """FastAPI 依赖工厂：检查指定 Scope"""
    def _check_scope(record: AgentTokenRecord = Depends(verify_agent_token)) -> AgentTokenRecord:
        AgentAuthManager.require_scope(record, scope)
        return record
    return _check_scope


# ─────────────────────────── rate limit headers helper ───────────────────────────

def _inject_rate_limit(request: Request, record: AgentTokenRecord) -> None:
    """将 RateLimit 头写入 request.state，供外层中间件注入到 response"""
    headers = AgentAuthManager.get_rate_limit_headers(record)
    if not hasattr(request.state, "agent_headers"):
        request.state.agent_headers = {}
    request.state.agent_headers.update(headers)


# ─────────────────────────── audit middleware ───────────────────────────

async def _audit_log_request(
    request: Request,
    record: AgentTokenRecord,
    scope: str,
    status_code: int,
    duration_ms: int,
    request_body: dict[str, Any] | None = None,
    response_summary: str | None = None,
) -> None:
    """记录审计日志"""
    try:
        store = _get_audit_store()
        store.log(
            token_hash=record.token_hash,
            token_name=record.name,
            scope=scope,
            route=request.url.path,
            method=request.method,
            status_code=status_code,
            duration_ms=duration_ms,
            request_body=request_body,
            response_summary=response_summary,
        )
    except Exception as exc:
        logger.warning("audit_log_failed", error=str(exc))


# ─────────────────────────── sub-routers ───────────────────────────

from .markets import router as markets_router
from .chat import router as chat_router
from .strategies import router as strategies_router
from .trading import router as trading_router

router = APIRouter(prefix="/agent/v1")

router.include_router(markets_router, prefix="/markets", tags=["Agent-市场"])
router.include_router(chat_router, prefix="/chat", tags=["Agent-对话"])
router.include_router(strategies_router, prefix="/strategies", tags=["Agent-策略"])
router.include_router(trading_router, prefix="/trading", tags=["Agent-交易"])


# ─────────────────────────── whoami ───────────────────────────

@router.get("/whoami")
async def agent_whoami(
    request: Request,
    record: AgentTokenRecord = Depends(verify_agent_token),
):
    """返回当前 Token 的身份、Scope 和白名单信息"""
    _inject_rate_limit(request, record)
    return {
        "name": record.name,
        "scopes": record.scopes,
        "markets": record.markets,
        "instruments": record.instruments,
        "paper_only": record.paper_only,
        "status": record.status,
        "rate_limit_per_min": record.rate_limit_per_min,
        "created_at": record.created_at.isoformat() if hasattr(record.created_at, "isoformat") else record.created_at,
        "expires_at": record.expires_at.isoformat() if record.expires_at and hasattr(record.expires_at, "isoformat") else record.expires_at,
        "last_used_at": record.last_used_at.isoformat() if record.last_used_at and hasattr(record.last_used_at, "isoformat") else record.last_used_at,
        "use_count": getattr(record, "use_count", 0),
    }


# ─────────────────────────── admin (token lifecycle) ───────────────────────────

@router.get("/admin/tokens")
async def admin_list_tokens(
    request: Request,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.CREDENTIALS)),
):
    """列出所有 Agent Token（需要 C scope 或 CREDENTIALS 权限）"""
    _inject_rate_limit(request, record)
    return {"tokens": AgentAuthManager.list_tokens()}


@router.post("/admin/tokens/{token_hash}/revoke")
async def admin_revoke_token(
    request: Request,
    token_hash: str,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.CREDENTIALS)),
):
    """吊销指定 Token"""
    _inject_rate_limit(request, record)
    ok = AgentAuthManager.revoke_token(token_hash)
    return {"revoked": ok}


@router.post("/admin/tokens/{token_hash}/activate")
async def admin_activate_token(
    request: Request,
    token_hash: str,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.CREDENTIALS)),
):
    """激活指定 Token"""
    _inject_rate_limit(request, record)
    ok = AgentAuthManager.activate_token(token_hash)
    return {"activated": ok}


@router.post("/admin/tokens/{token_hash}/deactivate")
async def admin_deactivate_token(
    request: Request,
    token_hash: str,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.CREDENTIALS)),
):
    """停用指定 Token"""
    _inject_rate_limit(request, record)
    ok = AgentAuthManager.deactivate_token(token_hash)
    return {"deactivated": ok}


# ─────────────────────────── jobs ───────────────────────────

@router.get("/jobs/{job_id}")
async def agent_get_job(
    request: Request,
    job_id: str,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """查询异步任务状态"""
    _inject_rate_limit(request, record)
    job = AgentAuthManager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs")
async def agent_list_jobs(
    request: Request,
    kind: str | None = None,
    limit: int = 50,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """列出最近任务"""
    _inject_rate_limit(request, record)
    return {"jobs": AgentAuthManager.list_jobs(kind=kind, limit=limit)}
