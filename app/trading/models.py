"""
UF Stock Assistant — 交易模块数据模型
SQLAlchemy ORM 模型：凭证、订单、持仓、成交记录、待交收任务
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings
from app.core.constants import (
    MarketType,
    OrderSide,
    OrderStatus,
    OrderType,
    SettlementMode,
    SettlementStatus,
    TradeType,
    TradingMode,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TradingCredential(Base):
    """交易所 API 凭证（加密存储）"""
    __tablename__ = "trading_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    passphrase_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Order(Base):
    """交易订单（支持多业务类型）"""
    __tablename__ = "trading_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False, default=OrderType.MARKET)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=OrderStatus.PENDING)
    exchange_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filled_quantity: Mapped[float] = mapped_column(Float, default=0)
    filled_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 业务类型 & 交收
    trade_type: Mapped[str] = mapped_column(String(20), nullable=False, default=TradeType.NORMAL)
    settlement_mode: Mapped[str] = mapped_column(String(10), nullable=False, default=SettlementMode.T1)
    settlement_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    settlement_status: Mapped[str] = mapped_column(String(20), nullable=False, default=SettlementStatus.PENDING)

    # 冻结（委托时）
    frozen_cash: Mapped[float] = mapped_column(Float, default=0)
    frozen_position: Mapped[float] = mapped_column(Float, default=0)

    # 费用明细
    commission: Mapped[float] = mapped_column(Float, default=0)
    stamp_tax: Mapped[float] = mapped_column(Float, default=0)
    exchange_fee: Mapped[float] = mapped_column(Float, default=0)
    transfer_fee: Mapped[float] = mapped_column(Float, default=0)
    system_fee: Mapped[float] = mapped_column(Float, default=0)
    portfolio_fee: Mapped[float] = mapped_column(Float, default=0)
    other_fees: Mapped[float] = mapped_column(Float, default=0)
    total_fee: Mapped[float] = mapped_column(Float, default=0)

    # 港股通汇率
    reference_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    settlement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    fee_currency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    strategy_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default=TradingMode.MOCK)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Position(Base):
    """持仓（支持冻结/可用分离）"""
    __tablename__ = "trading_positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 持仓数量分离
    total_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    available_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    frozen_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    avg_cost: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0)

    # 业务类型标识
    trade_type: Mapped[str] = mapped_column(String(20), nullable=False, default=TradeType.NORMAL)

    mode: Mapped[str] = mapped_column(String(10), nullable=False, default=TradingMode.MOCK)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class TradeLog(Base):
    """成交记录"""
    __tablename__ = "trade_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SettlementTask(Base):
    """待交收任务（多天期处理核心）"""
    __tablename__ = "settlement_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    trade_type: Mapped[str] = mapped_column(String(20), nullable=False, default=TradeType.NORMAL)

    # 任务类型
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # cash_release: 释放冻结资金（买入成交后）
    # cash_deduct:  扣减实际资金（交收日）
    # position_release: 释放冻结持仓（卖出成交后）
    # position_add:     增加实际持仓（交收日）

    symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0)

    # 计划交收日期
    settlement_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # 实际执行时间
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=SettlementStatus.PENDING)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Security(Base):
    """证券信息表（A股/币圈/美股等全市场代码信息）
    定时任务同步，前端/后端优先从本地表读取
    """
    __tablename__ = "securities"

    symbol: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    market_type: Mapped[str] = mapped_column(String(20), nullable=False, default="a_share")
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # 价格
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_up: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_down: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 成交量/额
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # 估值指标
    pe_ttm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pb: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    float_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 币圈特有
    quote_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)


class MockPortfolio(Base):
    """模拟资产账户"""
    __tablename__ = "mock_portfolios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)

    initial_capital: Mapped[float] = mapped_column(Float, default=5_000_000)
    total_assets: Mapped[float] = mapped_column(Float, default=5_000_000)
    available_cash: Mapped[float] = mapped_column(Float, default=5_000_000)
    frozen_cash: Mapped[float] = mapped_column(Float, default=0)
    position_value: Mapped[float] = mapped_column(Float, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── 数据库初始化 ──────────────────────────────────────────────────────────────

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database.url, echo=False, future=True)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory


def get_db_session() -> Session:
    """获取数据库会话"""
    factory = get_session_factory()
    return factory()


def init_trading_tables() -> None:
    """创建交易模块所有表"""
    engine = get_engine()
    Base.metadata.create_all(engine)
