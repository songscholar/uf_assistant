"""
UF Stock Assistant — Agent Token 认证管理
参考 QuantDinger Agent Gateway 设计
支持 Token 生成、SHA-256 验证、Scope 检查、paper-only 安全模式
"""

from __future__ import annotations

import hashlib
import secrets
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


@dataclass
class AgentTokenRecord:
    """Agent Token 记录（服务端存储）"""
    token_hash: str          # SHA-256 哈希值
    name: str                # Token 名称
    scopes: list[str]        # 权限范围 ["R", "W", "B", "T"]
    paper_only: bool         # 是否仅模拟交易
    created_at: float        # 创建时间戳
    expires_at: float | None # 过期时间戳（None 表示永不过期）
    last_used_at: float | None = None
    use_count: int = 0


class AgentAuthManager:
    """
    Agent Token 管理器
    
    职责：
    1. 签发 Token（生成随机 token + SHA-256 哈希存储）
    2. 验证 Token（比对哈希）
    3. Scope 权限检查
    4. paper-only 安全模式控制
    """

    @classmethod
    def issue_token(
        cls,
        name: str,
        scopes: list[str],
        paper_only: bool = True,
        ttl_hours: int | None = None,
    ) -> str:
        """
        签发新的 Agent Token
        
        Args:
            name: Token 名称（如 "cursor-mcp"）
            scopes: 权限范围列表 ["R", "W", "B", "T"]
            paper_only: 是否仅允许模拟交易（默认 True）
            ttl_hours: 有效期（小时），None 表示使用默认配置
            
        Returns:
            明文 Token（仅返回一次，需立即保存）
        """
        # 生成随机 token
        random_part = secrets.token_hex(24)
        raw_token = f"{AGENT_TOKEN_PREFIX}{random_part}"
        token_hash = cls._hash_token(raw_token)
        
        # 计算过期时间
        if ttl_hours is None:
            ttl_hours = get_settings().agent.token_ttl_hours
        expires_at = time.time() + ttl_hours * 3600 if ttl_hours > 0 else None
        
        # 规范化 scopes
        valid_scopes = [s for s in scopes if s in {AgentScope.READ, AgentScope.WRITE, AgentScope.BACKTEST, AgentScope.TRADE}]
        
        record = AgentTokenRecord(
            token_hash=token_hash,
            name=name,
            scopes=valid_scopes,
            paper_only=paper_only,
            created_at=time.time(),
            expires_at=expires_at,
        )
        
        _token_store[token_hash] = record
        
        logger.info(
            "agent_token_issued",
            name=name,
            scopes=valid_scopes,
            paper_only=paper_only,
            expires_at=expires_at,
        )
        
        return raw_token

    @classmethod
    def verify_token(cls, raw_token: str) -> AgentTokenRecord:
        """
        验证 Token 并返回记录
        
        Raises:
            ValidationError: Token 无效、过期或不存在
        """
        if not raw_token or not raw_token.startswith(AGENT_TOKEN_PREFIX):
            raise ValidationError("Invalid agent token format", details={"code": "INVALID_TOKEN"})
        
        token_hash = cls._hash_token(raw_token)
        record = _token_store.get(token_hash)
        
        if record is None:
            raise ValidationError("Agent token not found", details={"code": "TOKEN_NOT_FOUND"})
        
        # 检查过期
        if record.expires_at and time.time() > record.expires_at:
            raise ValidationError("Agent token expired", details={"code": "TOKEN_EXPIRED"})
        
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
                f"Agent token lacks required scope: {scope}",
                details={"code": "INSUFFICIENT_SCOPE", "required": scope, "granted": record.scopes},
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
                details={"code": "PAPER_ONLY", "message": "This agent token is restricted to paper trading"},
            )
        
        if not get_settings().agent.live_trading_enabled:
            raise ValidationError(
                "Live trading is disabled on server",
                details={"code": "LIVE_TRADING_DISABLED", "message": "Set AGENT_LIVE_TRADING_ENABLED=true to enable"},
            )

    @classmethod
    def revoke_token(cls, token_hash: str) -> bool:
        """吊销 Token"""
        if token_hash in _token_store:
            del _token_store[token_hash]
            logger.info("agent_token_revoked", token_hash=token_hash[:16])
            return True
        return False

    @classmethod
    def list_tokens(cls) -> list[dict[str, Any]]:
        """列出所有 Token（不包含哈希）"""
        return [
            {
                "name": r.name,
                "scopes": r.scopes,
                "paper_only": r.paper_only,
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
