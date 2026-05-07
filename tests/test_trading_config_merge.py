"""
测试策略 trading_config merge 逻辑 — 运行时字段保护
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.strategies.models import Base, StrategyModel
from app.strategies.strategy_service import update_strategy
from app.strategies.trading_executor import init_strategy_tables


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def strategy(db_session):
    """创建一个带有 trading_config 的策略"""
    s = StrategyModel(
        strategy_name="Test Strategy",
        strategy_type="indicator",
        symbol="BTC/USDT",
        trading_config={
            "stop_loss_pct": 0.03,
            "script_runtime_state": {"layer": 2, "total_cost": 1500},
            "last_signal_time": "2026-05-01T12:00:00Z",
            "bot_runtime_stats": {"trades": 10},
            "custom_param": "original",
        },
    )
    db_session.add(s)
    db_session.commit()
    return s


class TestTradingConfigMerge:
    def test_direct_override_when_explicitly_provided(self, db_session, strategy):
        """前端显式传入 script_runtime_state 时应被覆盖"""
        update_strategy(
            strategy.id,
            {
                "trading_config": {
                    "script_runtime_state": {"layer": 99},
                    "new_param": "hello",
                }
            },
            session=db_session,
        )
        db_session.refresh(strategy)
        tc = strategy.trading_config or {}
        assert tc["script_runtime_state"] == {"layer": 99}
        assert tc["new_param"] == "hello"

    def test_protected_runtime_fields_preserved(self, db_session, strategy):
        """前端未传入运行时字段时，原有值应被保留"""
        update_strategy(
            strategy.id,
            {"trading_config": {"stop_loss_pct": 0.05}},
            session=db_session,
        )
        db_session.refresh(strategy)
        tc = strategy.trading_config or {}
        # 传入的字段被覆盖
        assert tc["stop_loss_pct"] == 0.05
        # 受保护的运行时字段保留原值
        assert tc["script_runtime_state"] == {"layer": 2, "total_cost": 1500}
        assert tc["last_signal_time"] == "2026-05-01T12:00:00Z"
        assert tc["bot_runtime_stats"] == {"trades": 10}
        # 未传入的普通字段保留
        assert tc["custom_param"] == "original"

    def test_shallow_merge_for_nested_dict(self, db_session, strategy):
        """浅合并：嵌套 dict 的键会被整体覆盖"""
        update_strategy(
            strategy.id,
            {"trading_config": {"script_runtime_state": {"new_key": "new_val"}}},
            session=db_session,
        )
        db_session.refresh(strategy)
        tc = strategy.trading_config or {}
        # 传入的嵌套 dict 整体替换原有值
        assert tc["script_runtime_state"] == {"new_key": "new_val"}

    def test_no_trading_config_in_payload_keeps_existing(self, db_session, strategy):
        """payload 不含 trading_config 时，完全保留原有值"""
        original_tc = dict(strategy.trading_config or {})
        update_strategy(
            strategy.id,
            {"strategy_name": "Renamed Strategy"},
            session=db_session,
        )
        db_session.refresh(strategy)
        assert strategy.strategy_name == "Renamed Strategy"
        assert strategy.trading_config == original_tc
