"""
测试策略模块
"""

import pytest

from app.core.constants import TrendDirection
from app.strategies.base import BaseStrategy, Signal, StrategyParameter, StrategyResult
from app.strategies.builtin.bollinger import BollingerStrategy
from app.strategies.builtin.ma_crossover import MACrossoverStrategy
from app.strategies.builtin.macd import MACDStrategy
from app.strategies.builtin.rsi import RSIStrategy
from app.strategies.registry import StrategyRegistry, create_strategy, list_all_strategies


# =============================================================================
# 基础组件测试
# =============================================================================

class TestSignal:
    """测试 Signal"""

    def test_signal_creation(self):
        signal = Signal(
            symbol="000001",
            direction=TrendDirection.UP,
            confidence=0.8,
            reason="金叉",
        )
        assert signal.symbol == "000001"
        assert signal.direction == TrendDirection.UP
        assert signal.confidence == 0.8


class TestStrategyResult:
    """测试 StrategyResult"""

    def test_result_creation(self):
        result = StrategyResult(
            strategy_name="测试策略",
            symbol="000001",
            signal=Signal("000001", TrendDirection.UP, 0.8, "测试"),
        )
        assert result.strategy_name == "测试策略"
        assert result.error is None

    def test_result_with_error(self):
        result = StrategyResult(
            strategy_name="测试策略",
            symbol="000001",
            error="数据不足",
        )
        assert result.error == "数据不足"
        assert result.signal is None


class TestStrategyParameter:
    """测试 StrategyParameter"""

    def test_parameter_creation(self):
        param = StrategyParameter("window", "int", 20, 5, 100, "窗口期")
        assert param.name == "window"
        assert param.default == 20


# =============================================================================
# 内置策略测试
# =============================================================================

class TestMACrossoverStrategy:
    """测试均线交叉策略"""

    @pytest.fixture
    def strategy(self):
        return MACrossoverStrategy(short_window=3, long_window=5)

    @pytest.fixture
    def sample_data(self):
        """生成测试数据"""
        return [
            {"date": "2024-01-01", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
            {"date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 11, "volume": 1000},
            {"date": "2024-01-03", "open": 11, "high": 12, "low": 10, "close": 12, "volume": 1000},
            {"date": "2024-01-04", "open": 12, "high": 13, "low": 11, "close": 11, "volume": 1000},
            {"date": "2024-01-05", "open": 11, "high": 12, "low": 10, "close": 10, "volume": 1000},
            {"date": "2024-01-06", "open": 10, "high": 11, "low": 9, "close": 9, "volume": 1000},
            {"date": "2024-01-07", "open": 9, "high": 10, "low": 8, "close": 8, "volume": 1000},
            {"date": "2024-01-08", "open": 8, "high": 9, "low": 7, "close": 7, "volume": 1000},
        ]

    def test_strategy_properties(self, strategy):
        assert strategy.name == "均线交叉策略"
        assert "短期均线" in strategy.description
        assert len(strategy.parameters) == 2

    def test_insufficient_data(self, strategy):
        result = strategy.evaluate("000001", [])
        assert result.error is not None

    def test_evaluate_with_data(self, strategy, sample_data):
        result = strategy.evaluate("000001", sample_data)
        assert result.error is None
        assert result.signal is not None
        assert result.data is not None
        assert "ma_short" in result.data
        assert "ma_long" in result.data

    def test_golden_cross_signal(self):
        """测试金叉信号"""
        # 构造金叉数据：前期 short < long，后期 short > long
        data = [
            {"close": 10}, {"close": 10}, {"close": 10}, {"close": 10}, {"close": 10},
            {"close": 10}, {"close": 10}, {"close": 10}, {"close": 10}, {"close": 10},
            {"close": 11}, {"close": 12}, {"close": 13}, {"close": 14}, {"close": 15},
        ]
        strategy = MACrossoverStrategy(short_window=3, long_window=5)
        result = strategy.evaluate("000001", data)
        assert result.signal is not None


class TestMACDStrategy:
    """测试 MACD 策略"""

    def test_strategy_properties(self):
        strategy = MACDStrategy()
        assert strategy.name == "MACD策略"
        assert len(strategy.parameters) == 3

    def test_evaluate(self):
        data = [{"close": i} for i in range(1, 50)]
        strategy = MACDStrategy(fast=12, slow=26, signal=9)
        result = strategy.evaluate("000001", data)
        assert result.error is None
        assert result.signal is not None
        assert "dif" in result.data


class TestRSIStrategy:
    """测试 RSI 策略"""

    def test_strategy_properties(self):
        strategy = RSIStrategy()
        assert strategy.name == "RSI超卖策略"
        assert len(strategy.parameters) == 3

    def test_oversold_signal(self):
        """测试超卖信号"""
        # 构造 RSI 极低的数据（连续下跌）
        data = [{"close": 100 - i * 2} for i in range(30)]
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        result = strategy.evaluate("000001", data)
        assert result.error is None
        assert result.signal is not None
        assert "rsi" in result.data


class TestBollingerStrategy:
    """测试布林带策略"""

    def test_strategy_properties(self):
        strategy = BollingerStrategy()
        assert strategy.name == "布林带突破策略"
        assert len(strategy.parameters) == 2

    def test_evaluate(self):
        import random
        random.seed(42)
        data = [{"close": 10 + random.uniform(-2, 2)} for _ in range(30)]
        strategy = BollingerStrategy(period=20, std_dev=2.0)
        result = strategy.evaluate("000001", data)
        assert result.error is None
        assert result.signal is not None
        assert "upper" in result.data
        assert "lower" in result.data


# =============================================================================
# 注册表测试
# =============================================================================

class TestStrategyRegistry:
    """测试策略注册表"""

    def test_list_strategies(self):
        strategies = list_all_strategies()
        assert len(strategies) >= 4  # 至少 4 个内置策略

    def test_create_strategy(self):
        strategy = create_strategy("ma_crossover", short_window=5, long_window=10)
        assert strategy is not None
        assert strategy.name == "均线交叉策略"
        assert strategy.get_param("short_window") == 5

    def test_create_unknown_strategy(self):
        strategy = create_strategy("unknown")
        assert strategy is None

    def test_name_mapping(self):
        """测试名称映射"""
        strategy = create_strategy("均线交叉")
        assert strategy is not None
        assert strategy.name == "均线交叉策略"

    def test_registry_singleton(self):
        from app.strategies.registry import get_registry
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
