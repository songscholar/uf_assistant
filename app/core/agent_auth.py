"""
UF Stock Assistant — Agent Token 认证管理
参考 QuantDinger Agent Gateway 设计 (docs/agent/AI_INTEGRATION_DESIGN.md)

支持：
  - Token 生成、SHA-256 验证
  - Scope 检查（R/W/B/N/C/T）
  - markets / instruments 白名单
  - 速率限制（内存滑动窗口）
  - paper-only 安全模式
  - Token 状态（active / inactive / revoked）
  - last_used_at 追踪
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.core.constants import AGENT_TOKEN_PREFIX, AgentScope
from app.core.exceptions import ValidationError
from app.core.logging import get_logger

logger = get_logger("app.core.agent_auth")

# 内存存储（生产环境应迁移到数据库）
_token_store: dict[str, AgentTokenRecord] = {}

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


# ─────────────────────────── token record ───────────────────────────

@dataclass
class AgentTokenRecord:
    """Agent Token 记录（服务端存储）"""

    token_hash: str          # SHA-256 哈希值
    name: str                # Token 名称
    scopes: list[str]        # 权限范围
    markets: list[str]       # 市场白名单（["*"] 表示全部）
    instruments: list[str]   # 品种白名单（["*"] 表示全部）
    paper_only: bool         # 是否仅模拟交易
    status: str              # active / inactive / revoked
    rate_limit_per_min: int  # 每分钟请求上限
    created_at: float        # 创建时间戳
    expires_at: float | None # 过期时间戳（None 表示永不过期）
    last_used_at: float | None = None
    use_count: int = 0


# ─────────────────────────── auth manager ───────────────────────────

class AgentAuthManager:
    """
    Agent Token 管理器

    职责：
    1. 签发 Token（生成随机 token + SHA-256 哈希存储）
    2. 验证 Token（比对哈希 + 状态 + 过期 + 速率限制）
    3. Scope 权限检查
    4. markets / instruments 白名单检查
    5. paper-only 安全模式控制
    """

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

        Args:
            name: Token 名称（如 "cursor-mcp"）
            scopes: 权限范围列表
            markets: 允许的市场列表，None 表示全部（["*"]）
            instruments: 允许的品种列表，None 表示全部（["*"]）
            paper_only: 是否仅允许模拟交易（默认 True）
            status: 初始状态（默认 active）
            rate_limit_per_min: 每分钟请求上限（默认 60）
            ttl_hours: 有效期（小时），None 表示使用默认配置

        Returns:
            明文 Token（仅返回一次，需立即保存）
        """
        # 生成随机 token（参考 QuantDinger：token_urlsafe(32) 提供 256-bit 熵）
        body = secrets.token_urlsafe(32).rstrip("=")
        raw_token = f"{AGENT_TOKEN_PREFIX}{body}"
        token_hash = cls._hash_token(raw_token)

        # 计算过期时间
        if ttl_hours is None:
            ttl_hours = get_settings().agent.token_ttl_hours
        expires_at = time.time() + ttl_hours * 3600 if ttl_hours > 0 else None

        # 规范化 scopes
        valid_scopes_set = {
            AgentScope.READ,
            AgentScope.WRITE,
            AgentScope.BACKTEST,
            AgentScope.NOTIFY,
            AgentScope.CREDENTIALS,
            AgentScope.TRADE,
        }
        valid_scopes = [s for s in scopes if s in valid_scopes_set]

        # 规范化 markets / instruments
        _markets = markets if markets is not None else ["*"]
        _instruments = instruments if instruments is not None else ["*"]

        record = AgentTokenRecord(
            token_hash=token_hash,
            name=name,
            scopes=valid_scopes,
            markets=_markets,
            instruments=_instruments,
            paper_only=paper_only,
            status=status,
            rate_limit_per_min=rate_limit_per_min,
            created_at=time.time(),
            expires_at=expires_at,
        )

        _token_store[token_hash] = record

        logger.info(
            "agent_token_issued",
            name=name,
            scopes=valid_scopes,
            markets=_markets,
            instruments=_instruments,
            paper_only=paper_only,
            status=status,
            rate_limit_per_min=rate_limit_per_min,
            expires_at=expires_at,
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

        token_hash = cls._hash_token(raw_token)
        record = _token_store.get(token_hash)

        if record is None:
            raise ValidationError(
                "Unknown agent token",
                details={"code": "TOKEN_NOT_FOUND"},
            )

        # 检查状态
        if record.status == "revoked":
            raise ValidationError(
                "Token has been revoked",
                details={"code": "TOKEN_REVOKED"},
            )
        if record.status == "inactive":
            raise ValidationError(
                f"Token is {record.status}",
                details={"code": "TOKEN_INACTIVE"},
            )

        # 检查过期
        if record.expires_at and time.time() > record.expires_at:
            raise ValidationError(
                "Token expired",
                details={"code": "TOKEN_EXPIRED"},
            )

        # 速率限制
        if not _check_rate_limit(token_hash, record.rate_limit_per_min):
            raise ValidationError(
                "Rate limit exceeded for this token",
                details={"code": "RATE_LIMITED", "retriable": True},
            )

        # 更新使用统计
        record.last_used_at = time.time()
        record.use_count += 1

        return record

    @classmethod
    def require_scope(cls, record: AgentTokenRecord, scope: str) -> None:
        """
        检查 Token 是否具备指定 Scope

        Raises:
            ValidationError: 权限不足
        """
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
        """
        检查交易权限（双重安全：Scope + paper_only + 服务端开关）

        Raises:
            ValidationError: 无权限或处于 paper-only 模式
        """
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
        """检查 token 是否允许访问指定市场"""
        if not record.markets or "*" in record.markets:
            return True
        needle = (market or "").strip().upper()
        return any(needle == a.strip().upper() for a in record.markets)

    @classmethod
    def instrument_allowed(cls, record: AgentTokenRecord, symbol: str) -> bool:
        """检查 token 是否允许访问指定品种"""
        if not record.instruments or "*" in record.instruments:
            return True
        needle = (symbol or "").strip().upper()
        return any(needle == a.strip().upper() for a in record.instruments)

    # ─────────────────────── lifecycle ───────────────────────

    @classmethod
    def revoke_token(cls, token_hash: str) -> bool:
        """吊销 Token（设置状态为 revoked，保留记录用于审计）"""
        record = _token_store.get(token_hash)
        if record is not None:
            record.status = "revoked"
            logger.info("agent_token_revoked", token_hash=token_hash[:16])
            return True
        return False

    @classmethod
    def deactivate_token(cls, token_hash: str) -> bool:
        """停用 Token"""
        record = _token_store.get(token_hash)
        if record is not None:
            record.status = "inactive"
            logger.info("agent_token_deactivated", token_hash=token_hash[:16])
            return True
        return False

    @classmethod
    def activate_token(cls, token_hash: str) -> bool:
        """激活 Token"""
        record = _token_store.get(token_hash)
        if record is not None:
            record.status = "active"
            logger.info("agent_token_activated", token_hash=token_hash[:16])
            return True
        return False

    @classmethod
    def get_token(cls, token_hash: str) -> AgentTokenRecord | None:
        """获取 Token 记录（内部使用）"""
        return _token_store.get(token_hash)

    @classmethod
    def list_tokens(cls) -> list[dict[str, Any]]:
        """列出所有 Token（不包含完整哈希）"""
        return [
            {
                "name": r.name,
                "scopes": r.scopes,
                "markets": r.markets,
                "instruments": r.instruments,
                "paper_only": r.paper_only,
                "status": r.status,
                "rate_limit_per_min": r.rate_limit_per_min,
                "created_at": r.created_at,
                "expires_at": r.expires_at,
                "last_used_at": r.last_used_at,
                "use_count": r.use_count,
            }
            for r in _token_store.values()
        ]

    @classmethod
    def _hash_token(cls, raw_token: str) -> str:
        """SHA-256 哈希 Token"""
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
