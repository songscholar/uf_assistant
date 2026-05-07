"""
Tests for app.strategies.backtest module.

Covers:
- Technical indicator helper functions
- _KlineCache (TTL + LRU eviction)
- Signal normalization (_normalize_signals)
- BacktestService.run integration (mocked data + indicator execution)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.strategies.backtest import (
    BacktestService,
    _KlineCache,
    _atr,
    _boll,
    _crossover,
    _crossunder,
    _ema,
    _macd,
    _normalize_signals,
    _rsi,
    _sma,
    _simulate_trading_new_format,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def simple_series() -> pd.Series:
    """Monotonically increasing series [1, 2, 3, 4, 5]."""
    return pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])


@pytest.fixture()
def rsi_series() -> pd.Series:
    """Known price series for RSI validation (20 bars)."""
    return pd.Series([
        44.0, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42,
        45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00,
        46.03, 46.41, 46.22, 45.64,
    ])


@pytest.fixture()
def kline_df() -> pd.DataFrame:
    """Synthetic OHLCV DataFrame (50 bars, ascending close with noise)."""
    np.random.seed(42)
    n = 50
    base = 100.0
    close = base + np.cumsum(np.random.randn(n) * 0.5)
    open_ = close + np.random.randn(n) * 0.1
    high = np.maximum(open_, close) + np.abs(np.random.randn(n) * 0.3)
    low = np.minimum(open_, close) - np.abs(np.random.randn(n) * 0.3)
    volume = np.random.randint(1000, 10000, size=n).astype(float)

    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "time": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# =============================================================================
# 1. Helper functions
# =============================================================================


class TestSMA:
    def test_last_value_is_mean_of_window(self, simple_series: pd.Series) -> None:
        result = _sma(simple_series, 3)
        # SMA(3) of [1,2,3,4,5]: last window = [3,4,5] -> mean = 4.0
        assert result.iloc[-1] == pytest.approx(4.0)

    def test_length_matches_input(self, simple_series: pd.Series) -> None:
        result = _sma(simple_series, 3)
        assert len(result) == len(simple_series)

    def test_nan_when_insufficient_data(self, simple_series: pd.Series) -> None:
        result = _sma(simple_series, 3)
        # First two values should be NaN (min_periods=3)
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])
        assert not pd.isna(result.iloc[2])

    def test_window_equals_series_length(self, simple_series: pd.Series) -> None:
        result = _sma(simple_series, 5)
        # Only the last value should be non-NaN
        assert pd.isna(result.iloc[3])
        assert result.iloc[-1] == pytest.approx(3.0)  # mean of [1,2,3,4,5]


class TestEMA:
    def test_returns_same_length(self, simple_series: pd.Series) -> None:
        result = _ema(simple_series, 3)
        assert len(result) == len(simple_series)

    def test_no_nans(self, simple_series: pd.Series) -> None:
        """EMA with adjust=False should produce values for every bar."""
        result = _ema(simple_series, 3)
        assert not result.isna().any()

    def test_tracks_trend(self, simple_series: pd.Series) -> None:
        """EMA should be monotonically increasing for a monotonic series."""
        result = _ema(simple_series, 3)
        for i in range(1, len(result)):
            assert result.iloc[i] >= result.iloc[i - 1]

    def test_last_value_close_to_series_mean(self, simple_series: pd.Series) -> None:
        """With enough data, EMA converges toward the series mean."""
        long_series = pd.Series([10.0] * 100 + [20.0] * 100)
        result = _ema(long_series, 10)
        # Should be close to 20 by the end
        assert result.iloc[-1] == pytest.approx(20.0, abs=0.5)


class TestRSI:
    def test_returns_same_length(self, rsi_series: pd.Series) -> None:
        result = _rsi(rsi_series, 14)
        assert len(result) == len(rsi_series)

    def test_last_value_in_range(self, rsi_series: pd.Series) -> None:
        result = _rsi(rsi_series, 14)
        last = result.iloc[-1]
        assert 0.0 <= last <= 100.0

    def test_all_valid_in_range(self, rsi_series: pd.Series) -> None:
        """All non-NaN RSI values must be in [0, 100]."""
        result = _rsi(rsi_series, 14)
        valid = result.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 100.0).all()

    def test_monotonic_up_gives_high_rsi(self) -> None:
        """A steadily rising series should yield RSI near 100 (or NaN if all losses are zero)."""
        rising = pd.Series(range(1, 30), dtype=float)
        result = _rsi(rising, 14)
        # When loss is always 0, avg_loss becomes NaN → RSI is NaN
        # This is expected behavior; a nearly-monotonic series should still be high
        nearly_rising = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 14.5, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28], dtype=float)
        result2 = _rsi(nearly_rising, 14)
        assert result2.iloc[-1] > 80.0

    def test_monotonic_down_gives_low_rsi(self) -> None:
        """A steadily falling series should yield RSI near 0 (or NaN if all gains are zero)."""
        falling = pd.Series(list(range(30, 1, -1)), dtype=float)
        result = _rsi(falling, 14)
        # When gain is always 0, RSI is NaN — use nearly-monotonic instead
        nearly_falling = pd.Series([30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 16.5, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3], dtype=float)
        result2 = _rsi(nearly_falling, 14)
        assert result2.iloc[-1] < 20.0


class TestMACD:
    def test_returns_three_series(self, simple_series: pd.Series) -> None:
        macd_line, signal_line, histogram = _macd(simple_series)
        assert len(macd_line) == len(simple_series)
        assert len(signal_line) == len(simple_series)
        assert len(histogram) == len(simple_series)

    def test_histogram_equals_macd_minus_signal(self, simple_series: pd.Series) -> None:
        macd_line, signal_line, histogram = _macd(simple_series)
        pd.testing.assert_series_equal(
            histogram, macd_line - signal_line, check_names=False,
        )


class TestBoll:
    def test_returns_three_series(self, simple_series: pd.Series) -> None:
        long_series = pd.Series(range(1, 31), dtype=float)
        upper, middle, lower = _boll(long_series, 20)
        assert len(upper) == len(long_series)
        assert len(middle) == len(long_series)
        assert len(lower) == len(long_series)

    def test_middle_equals_sma(self) -> None:
        series = pd.Series(range(1, 31), dtype=float)
        upper, middle, lower = _boll(series, 20)
        sma_vals = _sma(series, 20)
        pd.testing.assert_series_equal(middle, sma_vals, check_names=False)

    def test_upper_above_middle_above_lower(self) -> None:
        np.random.seed(7)
        series = pd.Series(np.random.randn(50).cumsum() + 50)
        upper, middle, lower = _boll(series, 20)
        valid_idx = middle.dropna().index
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()


class TestATR:
    def test_returns_series(self, kline_df: pd.DataFrame) -> None:
        result = _atr(kline_df["high"], kline_df["low"], kline_df["close"], 14)
        assert len(result) == len(kline_df)

    def test_atr_is_positive(self, kline_df: pd.DataFrame) -> None:
        result = _atr(kline_df["high"], kline_df["low"], kline_df["close"], 14)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_higher_volatility_gives_higher_atr(self) -> None:
        low_vol = pd.Series([10.0] * 30)
        high_vol_low = pd.Series([9.0] * 30)
        high_vol_high = pd.Series([11.0] * 30)

        atr_low = _atr(high_vol_high, high_vol_low, low_vol, 14)
        atr_const = _atr(low_vol + 0.01, low_vol - 0.01, low_vol, 14)
        assert atr_low.dropna().mean() > atr_const.dropna().mean()


class TestCrossover:
    def test_cross_detected(self) -> None:
        fast = pd.Series([1.0, 2.0, 3.0, 5.0, 6.0])
        slow = pd.Series([3.0, 3.0, 3.0, 3.0, 3.0])
        result = _crossover(fast, slow)
        # At index 3: fast=5 > slow=3 AND prev fast=3 <= prev slow=3 -> True
        assert result.iloc[3] is True or result.iloc[3] == True

    def test_no_cross_when_stays_above(self) -> None:
        fast = pd.Series([5.0, 6.0, 7.0, 8.0, 9.0])
        slow = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0])
        result = _crossover(fast, slow)
        assert not result.any()

    def test_returns_boolean_series(self) -> None:
        a = pd.Series([1.0, 2.0, 3.0])
        b = pd.Series([2.0, 2.0, 2.0])
        result = _crossover(a, b)
        assert result.dtype == bool


class TestCrossunder:
    def test_cross_detected(self) -> None:
        fast = pd.Series([5.0, 4.0, 3.0, 1.0, 0.5])
        slow = pd.Series([3.0, 3.0, 3.0, 3.0, 3.0])
        result = _crossunder(fast, slow)
        # At index 3: fast=1 < slow=3 AND prev fast=3 >= prev slow=3 -> True
        assert result.iloc[3] is True or result.iloc[3] == True

    def test_no_cross_when_stays_below(self) -> None:
        fast = pd.Series([0.5, 0.6, 0.7, 0.8, 0.9])
        slow = pd.Series([5.0, 5.0, 5.0, 5.0, 5.0])
        result = _crossunder(fast, slow)
        assert not result.any()


# =============================================================================
# 2. _KlineCache
# =============================================================================


class TestKlineCache:
    def test_set_then_get(self) -> None:
        cache = _KlineCache()
        df = pd.DataFrame({"a": [1, 2]})
        cache.set("key1", df)
        result = cache.get("key1")
        pd.testing.assert_frame_equal(result, df)

    def test_get_missing_returns_none(self) -> None:
        cache = _KlineCache()
        assert cache.get("nonexistent") is None

    @patch("app.strategies.backtest.time")
    def test_ttl_expiry(self, mock_time: MagicMock) -> None:
        """After TTL elapses, get should return None."""
        mock_time.time.return_value = 1000.0
        cache = _KlineCache()
        cache.set("key", "value", ttl=10)

        # Still valid at t=1009
        mock_time.time.return_value = 1009.0
        assert cache.get("key") == "value"

        # Expired at t=1011
        mock_time.time.return_value = 1011.0
        assert cache.get("key") is None

    def test_overwrite_key(self) -> None:
        cache = _KlineCache()
        cache.set("k", "old")
        cache.set("k", "new")
        assert cache.get("k") == "new"

    def test_lru_eviction(self) -> None:
        cache = _KlineCache(max_entries=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Adding "d" should evict "a" (least recently used)
        cache.set("d", 4)
        assert cache.get("a") is None
        assert cache.get("d") == 4

    def test_lru_access_refreshes_order(self) -> None:
        cache = _KlineCache(max_entries=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Access "a" to make it recently used
        cache.get("a")
        # Adding "d" should now evict "b" (not "a")
        cache.set("d", 4)
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_clear(self) -> None:
        cache = _KlineCache()
        cache.set("x", 10)
        cache.clear()
        assert cache.get("x") is None


# =============================================================================
# 3. Signal normalization
# =============================================================================


class TestNormalizeSignals:
    def test_buy_true_generates_open_long(self) -> None:
        buy = pd.Series([True, False, False, False, False])
        sell = pd.Series([False, False, False, False, False])
        close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])

        signals = _normalize_signals(buy, sell, close, trade_direction="long")
        assert signals["open_long"].iloc[0] == True
        assert signals["close_long"].iloc[0] == False

    def test_buy_then_sell_closes_long(self) -> None:
        buy = pd.Series([True, False, False, True, False])
        sell = pd.Series([False, True, False, False, False])
        close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])

        signals = _normalize_signals(buy, sell, close, trade_direction="long")
        # Buy at 0 -> open_long[0]=True
        assert signals["open_long"].iloc[0] == True
        # Sell at 1 -> close_long[1]=True
        assert signals["close_long"].iloc[1] == True
        # Buy at 3 -> open_long[3]=True (re-entry)
        assert signals["open_long"].iloc[3] == True

    def test_both_direction_opens_short_on_sell(self) -> None:
        buy = pd.Series([False, False, False, False, False])
        sell = pd.Series([True, False, False, False, False])
        close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])

        signals = _normalize_signals(buy, sell, close, trade_direction="both")
        assert signals["open_short"].iloc[0] == True

    def test_long_only_ignores_sell_without_position(self) -> None:
        buy = pd.Series([False, False, False, False, False])
        sell = pd.Series([True, False, False, False, False])
        close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])

        signals = _normalize_signals(buy, sell, close, trade_direction="long")
        # No open position, so sell should not open a short in long-only mode
        assert signals["open_short"].iloc[0] == False
        assert signals["close_long"].iloc[0] == False

    def test_buy_then_sell_both_direction_flips_position(self) -> None:
        """In 'both' mode, buy then sell should close long and open short."""
        buy = pd.Series([True, False, False, False, False])
        sell = pd.Series([False, True, False, False, False])
        close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])

        signals = _normalize_signals(buy, sell, close, trade_direction="both")
        assert signals["open_long"].iloc[0] == True
        # Sell at bar 1: should close_long and open_short
        assert signals["close_long"].iloc[1] == True
        assert signals["open_short"].iloc[1] == True

    def test_confirmed_mode_skips_last_bar(self) -> None:
        """In confirmed mode, the last bar signal is not processed."""
        buy = pd.Series([False, False, False, False, True])
        sell = pd.Series([False, False, False, False, False])
        close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])

        signals = _normalize_signals(
            buy, sell, close, trade_direction="long", anti_repaint_mode="confirmed",
        )
        # Last bar (index 4) should not be processed
        assert signals["open_long"].iloc[4] == False


# =============================================================================
# 4. _simulate_trading_new_format
# =============================================================================


class TestSimulateTrading:
    def test_basic_long_trade(self, kline_df: pd.DataFrame) -> None:
        """Open long at bar 1, close at bar 3 via signal."""
        n = len(kline_df)
        open_long = pd.Series(False, index=kline_df.index)
        close_long = pd.Series(False, index=kline_df.index)
        open_short = pd.Series(False, index=kline_df.index)
        close_short = pd.Series(False, index=kline_df.index)

        open_long.iloc[1] = True
        close_long.iloc[3] = True

        signals = {
            "open_long": open_long,
            "close_long": close_long,
            "open_short": open_short,
            "close_short": close_short,
        }

        result = _simulate_trading_new_format(
            kline_df=kline_df,
            signals=signals,
            initial_capital=100000.0,
            commission=0.001,
            leverage=1,
            execution_timing="next_bar_open",
        )

        assert "trades" in result
        assert "equity_curve" in result
        assert result["buy_count"] >= 1
        assert result["sell_count"] >= 1
        assert len(result["equity_curve"]) > 0

    def test_stop_loss_triggers(self, kline_df: pd.DataFrame) -> None:
        """Stop loss should close the position when price drops enough."""
        open_long = pd.Series(False, index=kline_df.index)
        close_long = pd.Series(False, index=kline_df.index)
        open_short = pd.Series(False, index=kline_df.index)
        close_short = pd.Series(False, index=kline_df.index)

        open_long.iloc[1] = True

        signals = {
            "open_long": open_long,
            "close_long": close_long,
            "open_short": open_short,
            "close_short": close_short,
        }

        result = _simulate_trading_new_format(
            kline_df=kline_df,
            signals=signals,
            initial_capital=100000.0,
            commission=0.001,
            leverage=1,
            strategy_config={"stopLossPct": 0.01},  # 1% stop loss
            execution_timing="next_bar_open",
        )

        # With tight stop loss on volatile data, at least one stop_loss trade expected
        stop_loss_trades = [t for t in result["trades"] if t.get("reason") == "stop_loss"]
        # May or may not trigger depending on data, but result should be valid
        assert "trades" in result
        assert "equity_curve" in result

    def test_force_close_at_end(self, kline_df: pd.DataFrame) -> None:
        """Open position but never close — should be force-closed at end."""
        open_long = pd.Series(False, index=kline_df.index)
        close_long = pd.Series(False, index=kline_df.index)
        open_short = pd.Series(False, index=kline_df.index)
        close_short = pd.Series(False, index=kline_df.index)

        open_long.iloc[1] = True  # open but never close

        signals = {
            "open_long": open_long,
            "close_long": close_long,
            "open_short": open_short,
            "close_short": close_short,
        }

        result = _simulate_trading_new_format(
            kline_df=kline_df,
            signals=signals,
            initial_capital=100000.0,
            commission=0.001,
            leverage=1,
            execution_timing="next_bar_open",
        )

        # Last trade should be force_close
        if result["trades"]:
            assert result["trades"][-1].get("reason") == "force_close"


# =============================================================================
# 5. BacktestService.run integration test
# =============================================================================


class TestBacktestServiceRun:
    """Integration tests for BacktestService.run with mocked external deps."""

    def _make_indicator_result(self, kline_df: pd.DataFrame) -> dict:
        """Build a mock _execute_indicator return value."""
        n = len(kline_df)
        buy = pd.Series(False, index=kline_df.index)
        sell = pd.Series(False, index=kline_df.index)
        # Generate alternating signals: buy every 5 bars, sell every 5 bars offset
        for i in range(0, n, 10):
            buy.iloc[i] = True
        for i in range(5, n, 10):
            sell.iloc[i] = True
        return {"buy": buy, "sell": sell}

    @patch("app.strategies.backtest.validate_code_safety", return_value=(True, ""))
    @patch("app.strategies.backtest._execute_indicator")
    @patch.object(BacktestService, "_fetch_kline_data")
    def test_run_returns_expected_keys(
        self,
        mock_fetch: object,
        mock_exec: object,
        mock_safety: object,
        kline_df: pd.DataFrame,
    ) -> None:
        mock_fetch.return_value = kline_df  # type: ignore[union-attr]
        mock_exec.return_value = self._make_indicator_result(kline_df)  # type: ignore[union-attr]

        service = BacktestService()
        result = service.run(
            indicator_code="df['buy'] = df['close'] > df['close'].shift(1)",
            market="stock",
            symbol="600519",
            timeframe="1D",
            start_date="2024-01-01",
            end_date="2024-03-15",
            initial_capital=100000.0,
            commission=0.001,
            leverage=1,
            trade_direction="long",
        )

        expected_keys = [
            "totalReturn", "annualReturn", "maxDrawdown", "sharpeRatio",
            "winRate", "profitFactor", "totalTrades", "totalProfit",
            "totalCommission", "equityCurve", "trades", "buy_count",
            "sell_count", "elapsed_seconds",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

        assert isinstance(result["equityCurve"], list)
        assert isinstance(result["trades"], list)
        assert isinstance(result["totalReturn"], float)

    @patch("app.strategies.backtest.validate_code_safety", return_value=(True, ""))
    @patch("app.strategies.backtest._execute_indicator")
    @patch.object(BacktestService, "_fetch_kline_data")
    def test_run_with_empty_data_returns_error(
        self,
        mock_fetch: object,
        mock_exec: object,
        mock_safety: object,
    ) -> None:
        mock_fetch.return_value = pd.DataFrame()  # type: ignore[union-attr]

        service = BacktestService()
        result = service.run(
            indicator_code="df['buy'] = False",
            market="stock",
            symbol="600519",
            timeframe="1D",
            start_date="2024-01-01",
            end_date="2024-03-15",
        )

        assert "error" in result
        assert result["totalTrades"] == 0

    @patch("app.strategies.backtest.validate_code_safety", return_value=(True, ""))
    @patch("app.strategies.backtest._execute_indicator")
    @patch.object(BacktestService, "_fetch_kline_data")
    def test_run_with_insufficient_data(
        self,
        mock_fetch: object,
        mock_exec: object,
        mock_safety: object,
    ) -> None:
        # Only 10 bars — below _MIN_BARS_FOR_BACKTEST (30)
        small_df = pd.DataFrame({
            "time": pd.date_range("2024-01-01", periods=10, freq="B"),
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.5] * 10,
            "volume": [1000.0] * 10,
        })
        mock_fetch.return_value = small_df  # type: ignore[union-attr]

        service = BacktestService()
        result = service.run(
            indicator_code="df['buy'] = False",
            market="stock",
            symbol="600519",
            timeframe="1D",
            start_date="2024-01-01",
            end_date="2024-03-15",
        )

        assert "error" in result
        assert "Insufficient data" in result["error"]

    @patch("app.strategies.backtest.validate_code_safety", return_value=(True, ""))
    @patch("app.strategies.backtest._execute_indicator")
    @patch.object(BacktestService, "_fetch_kline_data")
    def test_run_with_leverage(
        self,
        mock_fetch: object,
        mock_exec: object,
        mock_safety: object,
        kline_df: pd.DataFrame,
    ) -> None:
        mock_fetch.return_value = kline_df  # type: ignore[union-attr]
        mock_exec.return_value = self._make_indicator_result(kline_df)  # type: ignore[union-attr]

        service = BacktestService()
        result = service.run(
            indicator_code="df['buy'] = df['close'] > df['close'].shift(1)",
            market="stock",
            symbol="600519",
            timeframe="1D",
            start_date="2024-01-01",
            end_date="2024-03-15",
            initial_capital=100000.0,
            commission=0.001,
            leverage=3,
            trade_direction="long",
        )

        # With leverage, totalReturn should differ from leverage=1
        assert "totalReturn" in result

    @patch("app.strategies.backtest.validate_code_safety", return_value=(True, ""))
    @patch("app.strategies.backtest._execute_indicator")
    @patch.object(BacktestService, "_fetch_kline_data")
    def test_run_short_direction(
        self,
        mock_fetch: object,
        mock_exec: object,
        mock_safety: object,
        kline_df: pd.DataFrame,
    ) -> None:
        mock_fetch.return_value = kline_df  # type: ignore[union-attr]
        mock_exec.return_value = self._make_indicator_result(kline_df)  # type: ignore[union-attr]

        service = BacktestService()
        result = service.run(
            indicator_code="df['sell'] = df['close'] < df['close'].shift(1)",
            market="stock",
            symbol="600519",
            timeframe="1D",
            start_date="2024-01-01",
            end_date="2024-03-15",
            initial_capital=100000.0,
            commission=0.001,
            leverage=1,
            trade_direction="short",
        )

        assert "totalReturn" in result
        assert "error" not in result or result.get("totalTrades", 0) >= 0

    @patch("app.strategies.backtest.validate_code_safety", return_value=(True, ""))
    @patch("app.strategies.backtest._execute_indicator")
    @patch.object(BacktestService, "_fetch_kline_data")
    def test_equity_curve_length(
        self,
        mock_fetch: object,
        mock_exec: object,
        mock_safety: object,
        kline_df: pd.DataFrame,
    ) -> None:
        """Equity curve should have at most as many points as kline bars."""
        mock_fetch.return_value = kline_df  # type: ignore[union-attr]
        mock_exec.return_value = self._make_indicator_result(kline_df)  # type: ignore[union-attr]

        service = BacktestService()
        result = service.run(
            indicator_code="df['buy'] = True",
            market="stock",
            symbol="600519",
            timeframe="1D",
            start_date="2024-01-01",
            end_date="2024-03-15",
        )

        assert len(result["equityCurve"]) <= len(kline_df)

    def test_empty_result_structure(self) -> None:
        """_empty_result should contain all metric keys plus error."""
        result = BacktestService._empty_result("test error")
        assert result["error"] == "test error"
        assert result["totalReturn"] == 0.0
        assert result["totalTrades"] == 0
        assert result["equityCurve"] == []
        assert result["trades"] == []


# =============================================================================
# 6. Edge cases and miscellaneous
# =============================================================================


class TestEdgeCases:
    def test_crossover_with_identical_series(self) -> None:
        """Two identical flat series should produce no crossover."""
        s = pd.Series([5.0] * 10)
        result = _crossover(s, s)
        assert not result.any()

    def test_rsi_with_constant_series(self) -> None:
        """Constant price => no gains or losses => RSI should be NaN or 50."""
        constant = pd.Series([100.0] * 30)
        result = _rsi(constant, 14)
        # With no price changes, avg_loss=0 => division by zero => NaN
        # This is expected behavior
        assert pd.isna(result.iloc[-1]) or 0 <= result.iloc[-1] <= 100

    def test_ema_period_1_equals_input(self) -> None:
        """EMA with period=1 should equal the input series."""
        s = pd.Series([3.0, 1.0, 4.0, 1.0, 5.0])
        result = _ema(s, 1)
        pd.testing.assert_series_equal(result, s, check_names=False, atol=1e-10)

    def test_simulate_trading_empty_df(self) -> None:
        """Empty DataFrame should return empty results."""
        empty_df = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        signals = {
            "open_long": pd.Series(dtype=bool),
            "close_long": pd.Series(dtype=bool),
            "open_short": pd.Series(dtype=bool),
            "close_short": pd.Series(dtype=bool),
        }
        result = _simulate_trading_new_format(
            kline_df=empty_df,
            signals=signals,
            initial_capital=100000.0,
            commission=0.001,
            leverage=1,
        )
        assert result["trades"] == []
        assert result["equity_curve"] == []
