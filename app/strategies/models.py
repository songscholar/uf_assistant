"""
UF Stock Assistant — 策略引擎数据模型
移植自 QuantDinger，适配 SQLAlchemy + SQLite
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Boolean,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class StrategyModel(Base):
    """策略表"""
    __tablename__ = "strategies"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(64), nullable=False, default="default", index=True)
    strategy_name = Column(String(256), nullable=False)
    strategy_type = Column(String(32), nullable=False, default="indicator")  # indicator / script
    status = Column(String(32), nullable=False, default="stopped")  # stopped / running / error
    symbol = Column(String(64), nullable=True)
    timeframe = Column(String(16), nullable=True, default="1D")
    strategy_code = Column(Text, nullable=True)
    indicator_config = Column(JSON, nullable=True)
    trading_config = Column(JSON, nullable=True)
    initial_capital = Column(Float, default=100000.0)
    leverage = Column(Integer, default=1)
    market_type = Column(String(32), default="stock")  # stock / crypto
    exchange_config = Column(JSON, nullable=True)
    trade_direction = Column(String(16), default="long")  # long / short / both
    commission = Column(Float, default=0.001)
    slippage = Column(Float, default=0.0)
    execution_mode = Column(String(32), default="signal")  # signal / live
    market_category = Column(String(32), default="Crypto")  # Crypto / stock
    strategy_mode = Column(String(32), default="signal")  # signal / bot
    notification_config = Column(JSON, nullable=True)
    ai_model_config = Column(JSON, nullable=True)
    strategy_group_id = Column(String(32), default="", index=True)
    group_base_name = Column(String(255), default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class IndicatorModel(Base):
    """指标代码表"""
    __tablename__ = "indicators"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(64), nullable=False, default="default", index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    code = Column(Text, nullable=False)
    is_builtin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_indicators_user_name", "user_id", "name"),
    )


class StrategyPosition(Base):
    """持仓表"""
    __tablename__ = "strategy_positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String(36), nullable=False, index=True)
    symbol = Column(String(64), nullable=False)
    side = Column(String(16), nullable=False)  # long / short
    size = Column(Float, nullable=False, default=0.0)
    entry_price = Column(Float, nullable=False, default=0.0)
    amount = Column(Float, nullable=False, default=0.0)
    highest_price = Column(Float, default=0.0)
    lowest_price = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    current_price = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("strategy_id", "symbol", "side", name="uq_strategy_position"),
    )


class StrategyTrade(Base):
    """交易记录表"""
    __tablename__ = "strategy_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String(36), nullable=False, index=True)
    symbol = Column(String(64), nullable=False)
    trade_type = Column(String(32), nullable=False)  # open_long, close_long, open_short, close_short, etc.
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    profit = Column(Float, default=0.0)
    commission = Column(Float, default=0.0)
    value = Column(Float, default=0.0)
    balance = Column(Float, default=0.0)
    exchange_order_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class PendingOrder(Base):
    """挂单表（QuantDinger 兼容：完整信号队列）"""
    __tablename__ = "pending_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String(36), nullable=False, index=True)
    symbol = Column(String(64), nullable=False)
    signal_type = Column(String(32), nullable=False)  # open_long, close_long, open_short, close_short, add_*, reduce_*
    signal_ts = Column(Integer, default=0)  # 蜡烛时间戳，用于去重
    trigger_price = Column(Float, nullable=True)
    position_size = Column(Float, nullable=True)
    payload_json = Column(Text, nullable=True)  # 完整信号载荷 JSON
    execution_mode = Column(String(32), default="signal")  # signal / live
    status = Column(String(32), default="pending")  # pending / processing / sent / failed / cancelled / deferred
    priority = Column(Integer, default=0)  # 越大越先处理
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=10)
    last_error = Column(Text, nullable=True)
    dispatch_note = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)  # 兼容旧字段
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    executed_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)


class BacktestRun(Base):
    """回测运行记录表"""
    __tablename__ = "backtest_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    strategy_id = Column(String(36), nullable=True, index=True)
    user_id = Column(String(64), nullable=False, default="default")
    symbol = Column(String(64), nullable=False)
    timeframe = Column(String(16), default="1D")
    strategy_type = Column(String(32), default="indicator")
    code = Column(Text, nullable=True)
    initial_capital = Column(Float, default=100000.0)
    commission = Column(Float, default=0.001)
    leverage = Column(Integer, default=1)
    trade_direction = Column(String(16), default="long")
    start_date = Column(String(32), nullable=True)
    end_date = Column(String(32), nullable=True)
    total_return = Column(Float, default=0.0)
    annual_return = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    win_rate = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    total_profit = Column(Float, default=0.0)
    total_commission = Column(Float, default=0.0)
    config_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class BacktestTrade(Base):
    """回测交易记录表"""
    __tablename__ = "backtest_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False, index=True)
    trade_time = Column(String(32), nullable=False)
    trade_type = Column(String(32), nullable=False)
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    profit = Column(Float, default=0.0)
    balance = Column(Float, default=0.0)


class BacktestEquityPoint(Base):
    """回测权益曲线点表"""
    __tablename__ = "backtest_equity_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False, index=True)
    point_time = Column(String(32), nullable=False)
    value = Column(Float, nullable=False)


class StrategyLog(Base):
    """策略运行日志表"""
    __tablename__ = "strategy_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String(36), nullable=False, index=True)
    level = Column(String(16), default="INFO")
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class SignalNotification(Base):
    """信号通知表"""
    __tablename__ = "signal_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String(36), nullable=False, index=True)
    signal_type = Column(String(32), nullable=False)
    symbol = Column(String(64), nullable=False)
    price = Column(Float, nullable=True)
    message = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    channel = Column(String(32), nullable=True)  # telegram / email / webhook
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)


class StrategyFeeRate(Base):
    """策略手续费率缓存表"""
    __tablename__ = "strategy_fee_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String(36), nullable=False, index=True)
    maker = Column(Float, default=0.0002)
    taker = Column(Float, default=0.0005)
    updated_at = Column(DateTime, default=_utcnow)
