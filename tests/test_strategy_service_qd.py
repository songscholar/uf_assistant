"""
Tests for QuantDinger-ported strategy service features:
- batch_create_strategies
- get_exchange_symbols
- _compute_runtime_metrics
- _build_bot_display
"""

from __future__ import annotations

import pytest

from app.strategies.strategy_service import (
    _build_bot_display,
    _compute_runtime_metrics,
    _display_item,
    _to_float,
    _to_int,
    get_exchange_symbols,
)


class TestBotDisplay:
    def test_martingale_display(self):
        tc = {
            "bot_type": "martingale",
            "initial_capital": 1000,
            "bot_params": {
                "multiplier": 2.0,
                "maxLayers": 5,
                "priceDropPct": 0.05,
                "takeProfitPct": 0.1,
                "stopLossPct": 0.08,
                "direction": "long",
            },
        }
        display = _build_bot_display(tc)
        assert display["bot_type"] == "martingale"
        assert display["capital_label_key"] == "trading-bot.martingale.totalBudget"
        assert len(display["strategy_params"]) == 7
        assert display["strategy_params"][0]["key"] == "initialAmount"

    def test_grid_display(self):
        tc = {
            "bot_type": "grid",
            "initial_capital": 500,
            "bot_params": {
                "upperPrice": 50000,
                "lowerPrice": 40000,
                "gridCount": 10,
                "amountPerGrid": 100,
                "gridMode": "arithmetic",
                "gridDirection": "neutral",
                "orderMode": "maker",
            },
        }
        display = _build_bot_display(tc)
        assert display["bot_type"] == "grid"
        assert len(display["strategy_params"]) == 7

    def test_trend_display(self):
        tc = {
            "bot_type": "trend",
            "bot_params": {
                "maPeriod": 20,
                "maType": "EMA",
                "confirmBars": 3,
                "positionPct": 0.1,
                "direction": "both",
            },
        }
        display = _build_bot_display(tc)
        assert display["bot_type"] == "trend"
        assert len(display["strategy_params"]) == 5

    def test_dca_display(self):
        tc = {
            "bot_type": "dca",
            "bot_params": {
                "amountEach": 100,
                "frequency": "daily",
                "totalBudget": 1000,
                "dipBuyEnabled": True,
                "dipThreshold": 0.1,
            },
        }
        display = _build_bot_display(tc)
        assert display["bot_type"] == "dca"
        assert len(display["strategy_params"]) == 5

    def test_no_bot_type(self):
        assert _build_bot_display({}) == {}
        assert _build_bot_display({"bot_type": ""}) == {}

    def test_risk_params(self):
        tc = {
            "bot_type": "grid",
            "initial_capital": 500,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.1,
            "max_position": 1000,
            "max_daily_loss": 200,
            "bot_params": {"upperPrice": 50000, "lowerPrice": 40000, "gridCount": 10},
        }
        display = _build_bot_display(tc)
        assert len(display["risk_params"]) == 4


class TestDisplayHelpers:
    def test_display_item(self):
        item = _display_item("test", "label.test", 100, "usdt")
        assert item["key"] == "test"
        assert item["value"] == 100
        assert item["value_type"] == "usdt"

    def test_to_float(self):
        assert _to_float("3.14") == 3.14
        assert _to_float("abc", 1.0) == 1.0
        assert _to_float(None, 2.0) == 2.0

    def test_to_int(self):
        assert _to_int("42") == 42
        assert _to_int("abc", 1) == 1
        assert _to_int(None, 0) == 0


class TestExchangeSymbols:
    def test_empty_exchange_id(self):
        result = get_exchange_symbols({}, user_id="default")
        assert result["success"] is False
        assert "select an exchange" in result["message"]

    def test_unsupported_exchange(self):
        result = get_exchange_symbols({"exchange_id": "nonexistent"}, user_id="default")
        assert result["success"] is False
        assert "Unsupported" in result["message"]


class TestRuntimeMetrics:
    def test_empty_strategy_ids(self):
        result = _compute_runtime_metrics([])
        assert result == {}

    def test_nonexistent_strategy(self):
        result = _compute_runtime_metrics(["nonexistent-uuid"])
        # Should not crash, returns empty metrics for unknown strategies
        assert "nonexistent-uuid" in result or result == {}
