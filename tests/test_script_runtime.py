"""
Tests for app/strategies/script_runtime.py
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.strategies.script_runtime import (
    ScriptBar,
    ScriptPosition,
    StrategyScriptContext,
    compile_strategy_script_handlers,
)


# ---------------------------------------------------------------------------
# ScriptBar
# ---------------------------------------------------------------------------

class TestScriptBar:
    def test_attribute_access(self) -> None:
        bar = ScriptBar(open=10.0, high=12.0, low=9.5, close=11.0, volume=1000.0)
        assert bar.open == 10.0
        assert bar.high == 12.0
        assert bar.low == 9.5
        assert bar.close == 11.0
        assert bar.volume == 1000.0

    def test_dict_access(self) -> None:
        bar = ScriptBar(open=10.0, high=12.0, low=9.5, close=11.0, volume=1000.0)
        assert bar["open"] == 10.0
        assert bar["close"] == 11.0

    def test_missing_key_returns_default(self) -> None:
        bar = ScriptBar(open=10.0)
        assert bar.get("close") is None
        assert bar.get("close", 0.0) == 0.0

    def test_missing_attr_raises_attribute_error(self) -> None:
        bar = ScriptBar(open=10.0)
        with pytest.raises(AttributeError):
            _ = bar.nonexistent


# ---------------------------------------------------------------------------
# ScriptPosition
# ---------------------------------------------------------------------------

class TestScriptPosition:
    def test_initial_state_is_flat(self) -> None:
        pos = ScriptPosition()
        assert not pos
        assert bool(pos) is False
        assert int(pos) == 0
        assert float(pos) == 0.0

    def test_open_long(self) -> None:
        pos = ScriptPosition()
        pos.open_position("long", 100.0, 10)
        assert bool(pos) is True
        assert pos.entry_price == 100.0
        assert pos.amount == 10.0
        assert pos.size == 10.0
        assert pos.side == "long"
        assert int(pos) == 1

    def test_open_short(self) -> None:
        pos = ScriptPosition()
        pos.open_position("short", 50.0, 5)
        assert bool(pos) is True
        assert int(pos) == -1
        assert pos.side == "short"

    def test_add_position_weighted_average(self) -> None:
        pos = ScriptPosition()
        pos.open_position("long", 100.0, 10)
        pos.add_position(110.0, 5)
        # weighted avg: (100*10 + 110*5) / 15 = 103.333...
        assert pos.amount == pytest.approx(15.0)
        assert pos.size == pytest.approx(15.0)
        assert pos.entry_price == pytest.approx(103.333333)

    def test_add_position_zero_amount_is_noop(self) -> None:
        pos = ScriptPosition()
        pos.open_position("long", 100.0, 10)
        pos.add_position(110.0, 0)
        assert pos.amount == 10.0

    def test_reduce_position(self) -> None:
        pos = ScriptPosition()
        pos.open_position("long", 100.0, 10)
        pos.reduce_position(3)
        assert pos.amount == pytest.approx(7.0)
        assert pos.size == pytest.approx(7.0)
        assert bool(pos) is True

    def test_reduce_position_to_zero_clears(self) -> None:
        pos = ScriptPosition()
        pos.open_position("long", 100.0, 10)
        pos.reduce_position(10)
        assert not pos
        assert pos.amount == 0.0

    def test_clear_position(self) -> None:
        pos = ScriptPosition()
        pos.open_position("long", 100.0, 10)
        pos.clear_position()
        assert not pos
        assert pos.side == ""
        assert pos.entry_price == 0.0

    def test_comparison_operators(self) -> None:
        pos = ScriptPosition()
        assert pos == 0
        assert not (pos > 0)
        assert pos >= 0
        assert not (pos < 0)
        assert pos <= 0

        pos.open_position("long", 100.0, 5)
        assert pos > 0
        assert not (pos == 0)
        assert pos >= 0
        assert not (pos < 0)


# ---------------------------------------------------------------------------
# StrategyScriptContext
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [99.0, 100.0, 101.0],
        "close": [103.0, 104.0, 105.0],
        "volume": [1000.0, 1100.0, 1200.0],
    })


@pytest.fixture()
def ctx(sample_df: pd.DataFrame) -> StrategyScriptContext:
    c = StrategyScriptContext(bars_df=sample_df, initial_balance=100_000.0)
    c.current_index = 2  # point to last row
    return c


class TestStrategyScriptContext:
    def test_param_returns_default(self, ctx: StrategyScriptContext) -> None:
        assert ctx.param("fast_period", 12) == 12

    def test_param_returns_stored_value(self, ctx: StrategyScriptContext) -> None:
        ctx.param("fast_period", 12)
        ctx._params["fast_period"] = 5
        assert ctx.param("fast_period", 12) == 5

    def test_buy_records_order(self, ctx: StrategyScriptContext) -> None:
        ctx.buy(price=100.0, amount=10)
        assert len(ctx._orders) == 1
        assert ctx._orders[0]["action"] == "buy"
        assert ctx._orders[0]["price"] == 100.0
        assert ctx._orders[0]["amount"] == 10

    def test_sell_records_order(self, ctx: StrategyScriptContext) -> None:
        ctx.sell(price=105.0, amount=5)
        assert len(ctx._orders) == 1
        assert ctx._orders[0]["action"] == "sell"

    def test_close_position_records_order(self, ctx: StrategyScriptContext) -> None:
        ctx.close_position()
        assert len(ctx._orders) == 1
        assert ctx._orders[0]["action"] == "close"

    def test_log_does_not_raise(self, ctx: StrategyScriptContext) -> None:
        ctx.log("test message")
        assert "test message" in ctx._logs

    def test_bars_returns_script_bars(self, ctx: StrategyScriptContext) -> None:
        bars = ctx.bars(2)
        assert len(bars) == 2
        assert isinstance(bars[0], ScriptBar)
        assert bars[-1].close == 105.0

    def test_initial_balance_and_equity(self, sample_df: pd.DataFrame) -> None:
        c = StrategyScriptContext(bars_df=sample_df, initial_balance=50_000.0)
        assert c.balance == 50_000.0
        assert c.equity == 50_000.0

    def test_position_starts_flat(self, ctx: StrategyScriptContext) -> None:
        assert not ctx.position
        assert isinstance(ctx.position, ScriptPosition)


# ---------------------------------------------------------------------------
# compile_strategy_script_handlers
# ---------------------------------------------------------------------------

class TestCompileStrategyScriptHandlers:
    def test_valid_script_with_on_bar(self) -> None:
        code = "def on_bar(ctx, bar):\n    pass"
        on_init, on_bar = compile_strategy_script_handlers(code)
        assert callable(on_bar)
        assert on_init is None

    def test_valid_script_with_on_init_and_on_bar(self) -> None:
        code = (
            "def on_init(ctx):\n"
            "    pass\n"
            "\n"
            "def on_bar(ctx, bar):\n"
            "    pass\n"
        )
        on_init, on_bar = compile_strategy_script_handlers(code)
        assert callable(on_init)
        assert callable(on_bar)

    def test_missing_on_bar_raises(self) -> None:
        code = "def on_init(ctx):\n    pass"
        with pytest.raises(ValueError, match="on_bar"):
            compile_strategy_script_handlers(code)

    def test_syntax_error_raises(self) -> None:
        code = "def on_bar(ctx, bar)\n    pass"  # missing colon
        with pytest.raises(RuntimeError):
            compile_strategy_script_handlers(code)

    def test_empty_script_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            compile_strategy_script_handlers("")

    def test_none_script_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            compile_strategy_script_handlers(None)  # type: ignore[arg-type]
