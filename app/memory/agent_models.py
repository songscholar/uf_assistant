"""
UF Stock Assistant — Agent Gateway 数据模型
基于 SQLAlchemy ORM，适配 SQLite / PostgreSQL

参考 QuantDinger 设计：
  - qd_agent_tokens  → agent_tokens
  - qd_agent_jobs    → agent_jobs
  - qd_agent_paper_orders → agent_paper_orders
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.memory.agent_models")

Base = declarative_base()

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database.url, echo=False, future=True)
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=_get_engine())
    return _session_factory


def get_agent_db_session() -> Session:
    """获取 Agent 数据库会话"""
    return _get_session_factory()()


def init_agent_tables() -> None:
    """创建 Agent Gateway 所有表（运行时自动调用）"""
    Base.metadata.create_all(_get_engine())
    logger.info("agent_tables_initialized")


class AgentTokenModel(Base):
    """Agent Token 表（持久化存储）"""
    __tablename__ = "agent_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    token_prefix = Column(String(32), nullable=False)
    name = Column(String(80), nullable=False)
    scopes = Column(Text, nullable=False, default="R")
    markets = Column(Text, nullable=False, default="*")
    instruments = Column(Text, nullable=False, default="*")
    paper_only = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False, default="active")
    rate_limit_per_min = Column(Integer, nullable=False, default=60)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentJobModel(Base):
    """Agent 异步任务表（backtest / experiment / strategy evaluation）"""
    __tablename__ = "agent_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(40), nullable=False, unique=True, index=True)
    kind = Column(String(40), nullable=False)  # backtest / strategy_eval / experiment / chat
    status = Column(String(20), nullable=False, default="queued")  # queued / running / completed / failed / cancelled
    request = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    progress = Column(JSON, nullable=True)  # {percent, stage, message}
    idempotency_key = Column(String(120), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


class AgentPaperOrderModel(Base):
    """Agent Paper Order 表（模拟交易记录）"""
    __tablename__ = "agent_paper_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_uid = Column(String(40), nullable=False, unique=True, index=True)
    token_hash = Column(String(128), nullable=False, index=True)
    symbol = Column(String(60), nullable=False)
    side = Column(String(8), nullable=False)
    order_type = Column(String(16), nullable=False, default="market")
    qty = Column(Float, nullable=False)
    limit_price = Column(Float, nullable=True)
    fill_price = Column(Float, nullable=True)
    fill_value = Column(Float, nullable=True)
    status = Column(String(16), nullable=False, default="filled")  # filled / rejected / cancelled
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
