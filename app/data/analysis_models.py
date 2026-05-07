"""
UF Stock Assistant — AI 分析记忆与校准数据模型
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
    JSON,
)

from app.memory.conversation import Base


class AnalysisMemoryModel(Base):
    """AI 分析记忆表：存储每次 AI 分析的历史记录，用于反思和校准"""
    __tablename__ = "analysis_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=True, index=True)
    market = Column(String(50), nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    decision = Column(String(10), nullable=False)  # BUY / SELL / HOLD
    confidence = Column(Integer, default=50)
    price_at_analysis = Column(Numeric(24, 8), nullable=True)
    summary = Column(Text, nullable=True)
    reasons = Column(JSON, default=list)
    scores = Column(JSON, default=dict)
    indicators_snapshot = Column(JSON, default=dict)
    raw_result = Column(JSON, default=dict)
    consensus_score = Column(Numeric(24, 8), nullable=True)
    consensus_abs = Column(Numeric(24, 8), nullable=True)
    agreement_ratio = Column(Numeric(10, 6), nullable=True)
    quality_multiplier = Column(Numeric(10, 6), nullable=True)
    task_status = Column(String(20), default="completed")  # completed / processing / failed
    task_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    validated_at = Column(DateTime, nullable=True)
    actual_outcome = Column(String(20), nullable=True)
    actual_return_pct = Column(Numeric(10, 4), nullable=True)
    was_correct = Column(Boolean, nullable=True)
    user_feedback = Column(String(20), nullable=True)  # helpful / not_helpful / accurate / inaccurate
    feedback_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_analysis_memory_symbol", "market", "symbol"),
        Index("idx_analysis_memory_created", "created_at"),
        Index("idx_analysis_memory_validated", "validated_at"),
        Index("idx_analysis_memory_user", "user_id"),
    )


class AICalibrationModel(Base):
    """AI 校准结果表：存储各市场的最优决策阈值"""
    __tablename__ = "ai_calibration"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(50), nullable=False, index=True)
    buy_threshold = Column(Numeric(10, 4), nullable=False, default=20.0)
    sell_threshold = Column(Numeric(10, 4), nullable=False, default=-20.0)
    min_consensus_abs_override = Column(Numeric(10, 4), nullable=False, default=15.0)
    quality_hold_threshold = Column(Numeric(10, 4), nullable=False, default=0.7)
    best_accuracy = Column(Numeric(10, 4), nullable=True)
    sample_count = Column(Integer, default=0)
    validated_count = Column(Integer, default=0)
    coverage = Column(JSON, default=dict)  # {"BUY": N, "SELL": N, "HOLD": N}
    validated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_ai_calibration_market_validated", "market", "validated_at"),
    )
