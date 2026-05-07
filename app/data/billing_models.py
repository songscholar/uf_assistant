"""
UF Stock Assistant — 计费与商业化数据模型
基于 SQLAlchemy ORM，适配 SQLite
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    Boolean,
    Index,
)

from app.memory.conversation import Base


class UserCreditsModel(Base):
    """用户积分与会员状态表"""
    __tablename__ = "user_credits"

    user_id = Column(String(64), primary_key=True, nullable=False)
    credits = Column(Numeric(20, 2), default=0)
    vip_expires_at = Column(DateTime, nullable=True)
    vip_plan = Column(String(20), default="")
    vip_is_lifetime = Column(Boolean, default=False)
    vip_monthly_credits_last_grant = Column(DateTime, nullable=True)
    credits_expires_at = Column(DateTime, nullable=True)  # 积分过期时间（None 表示永不过期）
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CreditsLogModel(Base):
    """积分变动日志表"""
    __tablename__ = "credits_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    action = Column(String(32), nullable=False, index=True)  # consume/recharge/admin_adjust/membership_bonus/...
    amount = Column(Numeric(20, 2), nullable=False)
    balance_after = Column(Numeric(20, 2), nullable=False)
    feature = Column(String(64), nullable=True)  # 功能名（如 ai_analysis）
    reference_id = Column(String(128), nullable=True)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_credits_log_user_action", "user_id", "action"),
        Index("idx_credits_log_created_at", "created_at"),
    )


class MembershipOrderModel(Base):
    """会员购买订单表"""
    __tablename__ = "membership_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    plan = Column(String(20), nullable=False)
    price_usd = Column(Numeric(10, 2), default=0)
    credits_granted = Column(Integer, default=0)
    status = Column(String(20), default="paid")
    fulfillment_ref = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    paid_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_membership_orders_user_id", "user_id"),
    )


class UsdtOrderModel(Base):
    """USDT-TRC20 支付订单表"""
    __tablename__ = "usdt_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    plan = Column(String(20), nullable=False)  # monthly/yearly/lifetime
    chain = Column(String(20), nullable=False, default="TRC20")
    amount_usdt = Column(Numeric(20, 6), nullable=False, default=0)
    address_index = Column(Integer, nullable=False, default=0)
    address = Column(String(80), nullable=False, default="")
    status = Column(String(20), nullable=False, default="pending")  # pending/paid/confirmed/expired
    tx_hash = Column(String(120), nullable=True)
    paid_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_usdt_orders_address_unique", "chain", "address", unique=True),
        Index("idx_usdt_orders_status", "status"),
    )
