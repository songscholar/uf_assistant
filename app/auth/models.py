"""
UF Stock Assistant — 认证模块数据模型
SQLAlchemy ORM 模型：用户、验证码、登录尝试、OAuth、安全日志、Agent Token、积分日志
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.auth.models")

Base = declarative_base()


class User(Base):
    """用户表"""
    __tablename__ = "uf_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False, default="")
    email = Column(String(100), unique=True, index=True)
    nickname = Column(String(50))
    avatar = Column(String(255), default="/avatar.jpg")
    status = Column(String(20), default="active", index=True)  # active/disabled/pending
    role = Column(String(20), default="user")  # admin/manager/user/viewer
    credits = Column(Numeric(20, 2), default=Decimal("0"))
    vip_expires_at = Column(DateTime)
    vip_plan = Column(String(20), default="")
    vip_is_lifetime = Column(Boolean, default=False)
    vip_monthly_credits_last_grant = Column(DateTime)
    email_verified = Column(Boolean, default=False)
    referred_by = Column(Integer, ForeignKey("uf_users.id"))
    notification_settings = Column(Text, default="")
    chart_templates = Column(Text, default="")
    timezone = Column(String(64), default="")
    token_version = Column(Integer, default=1)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VerificationCode(Base):
    """邮箱验证码表"""
    __tablename__ = "uf_verification_codes"

    id = Column(Integer, primary_key=True)
    email = Column(String(100), nullable=False, index=True)
    code = Column(String(10), nullable=False)
    type = Column(String(30), nullable=False)  # register/login/reset_password/change_password/change_email
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_uf_vcode_email_type", "email", "type"),
    )


class LoginAttempt(Base):
    """登录尝试记录表"""
    __tablename__ = "uf_login_attempts"

    id = Column(Integer, primary_key=True)
    identifier = Column(String(100), nullable=False, index=True)  # IP or username
    identifier_type = Column(String(20), nullable=False)  # ip/account
    success = Column(Boolean, default=False)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)


class OAuthLink(Base):
    """第三方 OAuth 绑定表"""
    __tablename__ = "uf_oauth_links"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("uf_users.id"), nullable=False, index=True)
    provider = Column(String(20), nullable=False)  # google/github
    provider_user_id = Column(String(100), nullable=False)
    provider_email = Column(String(100))
    provider_name = Column(String(100))
    provider_avatar = Column(String(500))
    access_token = Column(Text)
    refresh_token = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_uf_oauth_provider_uid", "provider", "provider_user_id", unique=True),
    )


class OAuthState(Base):
    """OAuth 授权状态表"""
    __tablename__ = "uf_oauth_states"

    id = Column(Integer, primary_key=True)
    state = Column(String(100), unique=True, nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    redirect = Column(String(500))
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SecurityLog(Base):
    """安全审计日志表"""
    __tablename__ = "uf_security_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("uf_users.id"), index=True)
    action = Column(String(50), nullable=False)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    details = Column(Text)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentToken(Base):
    """Agent API Token 表"""
    __tablename__ = "uf_agent_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("uf_users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    token_prefix = Column(String(20))
    token_hash = Column(String(64), nullable=False)
    scopes = Column(String(100))  # R,W,B,N,C,T comma-separated
    markets = Column(Text)  # JSON array
    instruments = Column(Text)  # JSON array
    paper_only = Column(Boolean, default=False)
    rate_limit_per_min = Column(Integer, default=60)
    status = Column(String(20), default="active")  # active/revoked
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime)


class AgentAudit(Base):
    """Agent 操作审计日志表"""
    __tablename__ = "uf_agent_audit"

    id = Column(Integer, primary_key=True)
    token_id = Column(Integer, ForeignKey("uf_agent_tokens.id"), index=True)
    user_id = Column(Integer, ForeignKey("uf_users.id"))
    action = Column(String(100))
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    details = Column(Text)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)


class CreditsLog(Base):
    """积分变动日志表"""
    __tablename__ = "uf_credits_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("uf_users.id"), nullable=False, index=True)
    amount = Column(Numeric(20, 2), nullable=False)
    balance_after = Column(Numeric(20, 2))
    reason = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)


# ── 数据库初始化（单例模式，与 trading/models.py 保持一致）──────────────────

_engine = None
_session_factory = None


def get_engine():
    """获取数据库引擎（单例）"""
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database.url, echo=False, future=True)
    return _engine


def get_session_factory():
    """获取会话工厂（单例）"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory


def get_auth_db_session() -> Session:
    """获取认证模块数据库会话"""
    return get_session_factory()()


def init_auth_tables() -> None:
    """创建认证模块所有表"""
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("auth_tables_initialized")
