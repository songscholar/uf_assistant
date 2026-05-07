"""
UF Stock Assistant — Agent Token 认证管理
参考 QuantDinger Agent Gateway 设计 (docs/agent/AI_INTEGRATION_DESIGN.md)

支持：
  - Token 生成、SHA-256 验证（数据库存储）
  - Scope 检查（R/W/B/N/C/T）
  - markets / instruments 白名单
  - 速率限制（内存滑动窗口）
  - paper-only 安全模式
  - Token 状态（active / inactive / revoked）
  - last_used_at 追踪
  - 幂等性（Idempotency-Key）
  - SaaS 部署 guard
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.constants import AGENT_TOKEN_PREFIX, AgentScope, AgentTokenStatus
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.memory.agent_models import (
    AgentJobModel,
    AgentTokenModel,
    get_agent_db_session,
    init_agent_tables,
)

logger = get_logger("app.core.agent_auth")

# ─────────────────────────── rate limit (in-process) ───────────────────────────
_rate_state: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


def _check_rate_limit(token_hash: str, limit_per_min: int) -> bool:
    """检查 token 是否超出速率限制。返回 True 表示允许通过。"""
    now = time.time()
    window_start = now - 60.0
    with _rate_lock:
        bucket = [t for t in _rate_state.get(token_hash, []) if t >= window_start]
        if len(bucket) >= max(1, int(limit_per_min)):
            _rate_state[token_hash] = bucket
            return False
        bucket.append(now)
        _rate_state[token_hash] = bucket
        return True


def _get_rate_limit_status(token_hash: str, limit_per_min: int) -> dict[str, Any]:
    """获取当前速率限制状态，用于 X-RateLimit 响应头"""
    now = time.time()
    window_start = now - 60.0
    with _rate_lock:
        bucket = [t for t in _rate_state.get(token_hash, []) if t >= window_start]
    remaining = max(0, limit_per_min - len(bucket))
    reset_at = int(now + 60)
    return {
        "limit": limit_per_min,
        "remaining": remaining,
        "reset": reset_at,
    }


# ─────────────────────────── dataclass (runtime) ───────────────────────────

@dataclass
class AgentTokenRecord:
    """Agent Token 运行时记录（从数据库反序列化）"""

    token_hash: str
    token_prefix: str
    name: str
    scopes: list[str]
    markets: list[str]
    instruments: list[str]
    paper_only: bool
    status: str
    rate_limit_per_min: int
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


# ─────────────────────────── helpers ───────────────────────────

_all_scopes = {
    AgentScope.READ,
    AgentScope.WRITE,
    AgentScope.BACKTEST,
    AgentScope.NOTIFY,
    AgentScope.CREDENTIALS,
    AgentScope.TRADE,
}


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _parse_csv_list(raw: str | None, default: str = "*") -> list[str]:
    if not raw:
        return [default]
    items = [p.strip() for p in str(raw).split(",") if p.strip()]
    return items or [default]


def _is_saas_mode() -> bool:
    """检查是否处于 SaaS 部署模式"""
    mode = (os.environ.get("UF_ASSISTANT_DEPLOYMENT_MODE") or "").strip().lower()
    return mode in ("saas", "hosted", "shared", "multitenant", "multi-tenant")


# ─────────────────────────── auth manager ───────────────────────────

class AgentAuthManager:
    """
    Agent Token 管理器（数据库存储版）

    职责：
    1. 签发 Token（生成随机 token + SHA-256 哈希存储到数据库）
    2. 验证 Token（比对哈希 + 状态 + 过期 + 速率限制）
    3. Scope 权限检查
    4. markets / instruments 白名单检查
    5. paper-only 安全模式控制
    6. SaaS 部署 guard
    7. 幂等性支持
    """

    @classmethod
    def _ensure_schema(cls) -> None:
        """确保数据库表已创建"""
        init_agent_tables()

    @classmethod
    def _model_to_record(cls, model: AgentTokenModel) -> AgentTokenRecord:
        """将 ORM 模型转换为运行时 dataclass"""
        return AgentTokenRecord(
            token_hash=model.token_hash,
            token_prefix=model.token_prefix,
            name=model.name,
            scopes=[s.strip() for s in (model.scopes or "R").split(",") if s.strip()],
            markets=_parse_csv_list(model.markets),
            instruments=_parse_csv_list(model.instruments),
            paper_only=bool(model.paper_only),
            status=model.status or "active",
            rate_limit_per_min=model.rate_limit_per_min or 60,
            created_at=model.created_at or datetime.now(timezone.utc),
            expires_at=model.expires_at,
            last_used_at=model.last_used_at,
        )

    @classmethod
    def issue_token(
        cls,
        name: str,
        scopes: list[str],
        markets: list[str] | None = None,
        instruments: list[str] | None = None,
        paper_only: bool = True,
        status: str = "active",
        rate_limit_per_min: int = 60,
        ttl_hours: int | None = None,
    ) -> str:
        """
        签发新的 Agent Token

        SaaS 模式 guard：
          - 自动拒绝 T scope（返回 403）
          - 强制 paper_only=true
        """
        cls._ensure_schema()

        # SaaS 模式：拒绝 T scope
        if _is_saas_mode() and AgentScope.TRADE in scopes:
            raise ValidationError(
                "T scope is not allowed in SaaS mode",
                details={"code": "SAAS_T_SCOPE_REJECTED"},
            )

        # SaaS 模式：强制 paper_only
        if _is_saas_mode():
            paper_only = True

        # 生成随机 token（参考 QuantDinger：token_urlsafe(32) 提供 256-bit 熵）
        body = secrets.token_urlsafe(32).rstrip("=")
        raw_token = f"{AGENT_TOKEN_PREFIX}{body}"
        token_hash = _hash_token(raw_token)
        token_prefix = raw_token[: len(AGENT_TOKEN_PREFIX) + 8]

        # 计算过期时间
        if ttl_hours is None:
            ttl_hours = get_settings().agent.token_ttl_hours
        expires_at = None
        if ttl_hours > 0:
            expires_at = datetime.now(timezone.utc).replace(tzinfo=timezone.utc)
            expires_at = expires_at.timestamp() + ttl_hours * 3600
            expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)

        # 规范化 scopes
        valid_scopes = [s for s in scopes if s in _all_scopes]
        scopes_str = ",".join(valid_scopes) if valid_scopes else "R"

        # 规范化 markets / instruments
        markets_str = ",".join(markets) if markets else "*"
        instruments_str = ",".join(instruments) if instruments else "*"

        # 写入数据库
        session = get_agent_db_session()
        try:
            model = AgentTokenModel(
                token_hash=token_hash,
                token_prefix=token_prefix,
                name=name,
                scopes=scopes_str,
                markets=markets_str,
                instruments=instruments_str,
                paper_only=paper_only,
                status=status,
                rate_limit_per_min=rate_limit_per_min,
                expires_at=expires_at,
            )
            session.add(model)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("agent_token_issue_failed", error=str(exc))
            raise ValidationError("Failed to issue token", details={"code": "ISSUE_FAILED"})
        finally:
            session.close()

        logger.info(
            "agent_token_issued",
            name=name,
            scopes=valid_scopes,
            markets=markets_str,
            instruments=instruments_str,
            paper_only=paper_only,
            status=status,
            rate_limit_per_min=rate_limit_per_min,
        )

        return raw_token

    @classmethod
    def verify_token(cls, raw_token: str) -> AgentTokenRecord:
        """
        验证 Token 并返回记录

        Raises:
            ValidationError: Token 无效、过期、被吊销或不存在
        """
        if not raw_token or not raw_token.startswith(AGENT_TOKEN_PREFIX):
            raise ValidationError(
                "Missing or malformed agent token",
                details={"code": "INVALID_TOKEN"},
            )

        cls._ensure_schema()
        token_hash = _hash_token(raw_token)

        session = get_agent_db_session()
        try:
            model = session.query(AgentTokenModel).filter_by(token_hash=token_hash).first()
        finally:
            session.close()

        if model is None:
            raise ValidationError(
                "Unknown agent token",
                details={"code": "TOKEN_NOT_FOUND"},
            )

        # 检查状态
        if model.status == AgentTokenStatus.REVOKED:
            raise ValidationError(
                "Token has been revoked",
                details={"code": "TOKEN_REVOKED"},
            )
        if model.status == AgentTokenStatus.INACTIVE:
            raise ValidationError(
                f"Token is {model.status}",
                details={"code": "TOKEN_INACTIVE"},
            )

        # 检查过期
        if model.expires_at and datetime.now(timezone.utc) > model.expires_at:
            raise ValidationError(
                "Token expired",
                details={"code": "TOKEN_EXPIRED"},
            )

        # 速率限制
        if not _check_rate_limit(token_hash, model.rate_limit_per_min or 60):
            raise ValidationError(
                "Rate limit exceeded for this token",
                details={"code": "RATE_LIMITED", "retriable": True},
            )

        # 更新 last_used_at
        session = get_agent_db_session()
        try:
            model.last_used_at = datetime.now(timezone.utc)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

        return cls._model_to_record(model)

    @classmethod
    def get_rate_limit_headers(cls, record: AgentTokenRecord) -> dict[str, str]:
        """获取 RateLimit 响应头"""
        status = _get_rate_limit_status(record.token_hash, record.rate_limit_per_min)
        return {
            "X-RateLimit-Limit": str(status["limit"]),
            "X-RateLimit-Remaining": str(status["remaining"]),
            "X-RateLimit-Reset": str(status["reset"]),
        }

    @classmethod
    def require_scope(cls, record: AgentTokenRecord, scope: str) -> None:
        """检查 Token 是否具备指定 Scope"""
        if scope not in record.scopes:
            raise ValidationError(
                f"Token lacks required scope: {scope}",
                details={
                    "code": "INSUFFICIENT_SCOPE",
                    "required": scope,
                    "granted": record.scopes,
                },
            )

    @classmethod
    def check_trade_permission(cls, record: AgentTokenRecord) -> None:
        """检查交易权限（双重安全：Scope + paper_only + 服务端开关）"""
        cls.require_scope(record, AgentScope.TRADE)

        if record.paper_only:
            raise ValidationError(
                "Trading is paper-only for this token",
                details={"code": "PAPER_ONLY"},
            )

        if not get_settings().agent.live_trading_enabled:
            raise ValidationError(
                "Live trading is disabled on server",
                details={"code": "LIVE_TRADING_DISABLED"},
            )

    # ─────────────────────── allowlist helpers ───────────────────────

    @classmethod
    def market_allowed(cls, record: AgentTokenRecord, market: str) -> bool:
        if not record.markets or "*" in record.markets:
            return True
        needle = (market or "").strip().upper()
        return any(needle == a.strip().upper() for a in record.markets)

    @classmethod
    def instrument_allowed(cls, record: AgentTokenRecord, symbol: str) -> bool:
        if not record.instruments or "*" in record.instruments:
            return True
        needle = (symbol or "").strip().upper()
        return any(needle == a.strip().upper() for a in record.instruments)

    # ─────────────────────── lifecycle ───────────────────────

    @classmethod
    def revoke_token(cls, token_hash: str) -> bool:
        """吊销 Token（状态设为 revoked）"""
        session = get_agent_db_session()
        try:
            model = session.query(AgentTokenModel).filter_by(token_hash=token_hash).first()
            if model is not None:
                model.status = AgentTokenStatus.REVOKED
                session.commit()
                logger.info("agent_token_revoked", token_hash=token_hash[:16])
                return True
            return False
        except Exception as exc:
            session.rollback()
            logger.error("agent_token_revoke_failed", error=str(exc))
            return False
        finally:
            session.close()

    @classmethod
    def deactivate_token(cls, token_hash: str) -> bool:
        """停用 Token"""
        session = get_agent_db_session()
        try:
            model = session.query(AgentTokenModel).filter_by(token_hash=token_hash).first()
            if model is not None:
                model.status = AgentTokenStatus.INACTIVE
                session.commit()
                logger.info("agent_token_deactivated", token_hash=token_hash[:16])
                return True
            return False
        except Exception as exc:
            session.rollback()
            logger.error("agent_token_deactivate_failed", error=str(exc))
            return False
        finally:
            session.close()

    @classmethod
    def activate_token(cls, token_hash: str) -> bool:
        """激活 Token"""
        session = get_agent_db_session()
        try:
            model = session.query(AgentTokenModel).filter_by(token_hash=token_hash).first()
            if model is not None:
                model.status = AgentTokenStatus.ACTIVE
                session.commit()
                logger.info("agent_token_activated", token_hash=token_hash[:16])
                return True
            return False
        except Exception as exc:
            session.rollback()
            logger.error("agent_token_activate_failed", error=str(exc))
            return False
        finally:
            session.close()

    @classmethod
    def get_token(cls, token_hash: str) -> AgentTokenRecord | None:
        """获取 Token 记录"""
        session = get_agent_db_session()
        try:
            model = session.query(AgentTokenModel).filter_by(token_hash=token_hash).first()
            return cls._model_to_record(model) if model else None
        finally:
            session.close()

    @classmethod
    def list_tokens(cls) -> list[dict[str, Any]]:
        """列出所有 Token（不包含完整哈希）"""
        session = get_agent_db_session()
        try:
            models = session.query(AgentTokenModel).all()
            return [
                {
                    "name": m.name,
                    "token_prefix": m.token_prefix,
                    "scopes": [s.strip() for s in (m.scopes or "R").split(",") if s.strip()],
                    "markets": _parse_csv_list(m.markets),
                    "instruments": _parse_csv_list(m.instruments),
                    "paper_only": bool(m.paper_only),
                    "status": m.status,
                    "rate_limit_per_min": m.rate_limit_per_min,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "expires_at": m.expires_at.isoformat() if m.expires_at else None,
                    "last_used_at": m.last_used_at.isoformat() if m.last_used_at else None,
                }
                for m in models
            ]
        finally:
            session.close()

    # ─────────────────────── idempotency ───────────────────────

    @classmethod
    @contextmanager
    def with_idempotency(cls, kind: str, key: str | None):
        """
        幂等性上下文管理器

        如果相同的 kind+key 已存在，返回已有 job；否则 yield None 让调用方执行。
        """
        if not key:
            yield None
            return

        session = get_agent_db_session()
        try:
            existing = (
                session.query(AgentJobModel)
                .filter_by(kind=kind, idempotency_key=key)
                .order_by(AgentJobModel.id.desc())
                .first()
            )
            if existing:
                yield {
                    "job_id": existing.job_id,
                    "status": existing.status,
                    "result": existing.result,
                    "error": existing.error,
                }
                return
        except Exception as exc:
            logger.warning("idempotency_lookup_failed", error=str(exc))
        finally:
            session.close()

        yield None

    @classmethod
    def submit_job(
        cls,
        kind: str,
        request: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> str:
        """提交异步任务，返回 job_id"""
        job_id = f"job_{secrets.token_hex(16)}"
        session = get_agent_db_session()
        try:
            model = AgentJobModel(
                job_id=job_id,
                kind=kind,
                request=request,
                idempotency_key=idempotency_key,
            )
            session.add(model)
            session.commit()
            return job_id
        except Exception as exc:
            session.rollback()
            logger.error("agent_job_submit_failed", error=str(exc))
            raise ValidationError("Failed to submit job", details={"code": "JOB_SUBMIT_FAILED"})
        finally:
            session.close()

    @classmethod
    def get_job(cls, job_id: str) -> dict[str, Any] | None:
        """获取任务状态"""
        session = get_agent_db_session()
        try:
            model = session.query(AgentJobModel).filter_by(job_id=job_id).first()
            if not model:
                return None
            return {
                "job_id": model.job_id,
                "kind": model.kind,
                "status": model.status,
                "request": model.request,
                "result": model.result,
                "error": model.error,
                "progress": model.progress,
                "created_at": model.created_at.isoformat() if model.created_at else None,
                "started_at": model.started_at.isoformat() if model.started_at else None,
                "finished_at": model.finished_at.isoformat() if model.finished_at else None,
            }
        finally:
            session.close()

    @classmethod
    def update_job(
        cls,
        job_id: str,
        status: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        progress: dict[str, Any] | None = None,
    ) -> None:
        """更新任务状态"""
        session = get_agent_db_session()
        try:
            model = session.query(AgentJobModel).filter_by(job_id=job_id).first()
            if not model:
                return
            if status:
                model.status = status
                if status == "running" and not model.started_at:
                    model.started_at = datetime.now(timezone.utc)
                if status in ("completed", "failed", "cancelled"):
                    model.finished_at = datetime.now(timezone.utc)
            if result is not None:
                model.result = result
            if error is not None:
                model.error = error
            if progress is not None:
                model.progress = progress
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error("agent_job_update_failed", error=str(exc))
        finally:
            session.close()

    @classmethod
    def list_jobs(cls, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """列出最近任务"""
        session = get_agent_db_session()
        try:
            query = session.query(AgentJobModel)
            if kind:
                query = query.filter_by(kind=kind)
            models = query.order_by(AgentJobModel.id.desc()).limit(limit).all()
            return [
                {
                    "job_id": m.job_id,
                    "kind": m.kind,
                    "status": m.status,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in models
            ]
        finally:
            session.close()

    # ─────────────────────── paper orders ───────────────────────

    @classmethod
    def record_paper_order(
        cls,
        token_hash: str,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "market",
        limit_price: float | None = None,
        fill_price: float | None = None,
        status: str = "filled",
        note: str = "",
    ) -> dict[str, Any]:
        """记录模拟交易订单"""
        order_uid = f"po_{secrets.token_hex(12)}"
        fill_value = (fill_price * qty) if (fill_price is not None and qty) else None

        session = get_agent_db_session()
        try:
            model = AgentPaperOrderModel(
                order_uid=order_uid,
                token_hash=token_hash,
                symbol=symbol,
                side=side,
                order_type=order_type,
                qty=qty,
                limit_price=limit_price,
                fill_price=fill_price,
                fill_value=fill_value,
                status=status,
                note=note,
            )
            session.add(model)
            session.commit()
            return {
                "order_uid": order_uid,
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "qty": qty,
                "fill_price": fill_price,
                "fill_value": fill_value,
                "status": status,
                "paper": True,
                "note": note,
            }
        except Exception as exc:
            session.rollback()
            logger.error("agent_paper_order_failed", error=str(exc))
            raise ValidationError("Failed to record paper order", details={"code": "PAPER_ORDER_FAILED"})
        finally:
            session.close()

    @classmethod
    def list_paper_orders(cls, token_hash: str, limit: int = 100) -> list[dict[str, Any]]:
        """列出模拟交易订单"""
        session = get_agent_db_session()
        try:
            models = (
                session.query(AgentPaperOrderModel)
                .filter_by(token_hash=token_hash)
                .order_by(AgentPaperOrderModel.id.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "order_uid": m.order_uid,
                    "symbol": m.symbol,
                    "side": m.side,
                    "qty": m.qty,
                    "fill_price": m.fill_price,
                    "fill_value": m.fill_value,
                    "status": m.status,
                    "note": m.note,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in models
            ]
        finally:
            session.close()

    @classmethod
    def kill_switch_paper_orders(cls, token_hash: str) -> int:
        """取消指定 token 的所有未成交 paper orders"""
        session = get_agent_db_session()
        try:
            from sqlalchemy import update
            stmt = (
                update(AgentPaperOrderModel)
                .where(
                    AgentPaperOrderModel.token_hash == token_hash,
                    AgentPaperOrderModel.status.notin_(["filled", "cancelled", "rejected"]),
                )
                .values(status="cancelled", note=AgentPaperOrderModel.note + " [kill_switch]")
            )
            result = session.execute(stmt)
            session.commit()
            affected = result.rowcount
            logger.info("agent_kill_switch", token_hash=token_hash[:16], cancelled=affected)
            return affected
        except Exception as exc:
            session.rollback()
            logger.error("agent_kill_switch_failed", error=str(exc))
            return 0
        finally:
            session.close()
