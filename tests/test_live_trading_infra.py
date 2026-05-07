"""
Tests for live_trading infrastructure (Stage 2):
- base.py : BaseRestClient, LiveTradingError
- factory.py : exchange_demo_mode_enabled, merge_root_exchange_config_overlay
- symbols.py : symbol normalization per exchange
- records.py : normalize_strategy_symbol, apply_fill_to_local_position logic
- execution.py : _signal_to_sides, _normalize_symbol_for_order
"""

from __future__ import annotations

import pytest

from app.strategies.live_trading.base import BaseRestClient, LiveOrderResult, LiveTradingError
from app.strategies.live_trading.factory import (
    exchange_demo_mode_enabled,
    merge_root_exchange_config_overlay,
)
from app.strategies.live_trading.symbols import (
    to_binance_futures_symbol,
    to_binance_spot_symbol,
    to_okx_swap_inst_id,
    to_okx_spot_inst_id,
    to_bitget_um_symbol,
    to_bybit_symbol,
    to_coinbase_product_id,
    to_kraken_pair,
    to_kucoin_symbol,
    to_kucoin_futures_symbol,
    to_kraken_futures_symbol,
    to_gate_currency_pair,
    to_deepcoin_symbol,
    to_htx_spot_symbol,
    to_htx_contract_code,
)
from app.strategies.live_trading.records import normalize_strategy_symbol
from app.strategies.live_trading.execution import _signal_to_sides, _normalize_symbol_for_order


# ---------------------------------------------------------------------------
# base.py
# ---------------------------------------------------------------------------
class TestBaseRestClient:
    def test_url_with_slash(self):
        c = BaseRestClient("https://api.example.com")
        assert c._url("/v1/test") == "https://api.example.com/v1/test"

    def test_url_without_slash(self):
        c = BaseRestClient("https://api.example.com")
        assert c._url("v1/test") == "https://api.example.com/v1/test"

    def test_now_ms(self):
        c = BaseRestClient("https://api.example.com")
        ms = c._now_ms()
        assert isinstance(ms, int) and ms > 1700000000000

    def test_json_dumps(self):
        c = BaseRestClient("https://api.example.com")
        assert c._json_dumps({"a": 1}) == '{"a":1}'


class TestLiveOrderResult:
    def test_dataclass(self):
        r = LiveOrderResult(
            exchange_id="binance",
            exchange_order_id="12345",
            filled=1.5,
            avg_price=50000.0,
            raw={"status": "FILLED"},
        )
        assert r.exchange_id == "binance"
        assert r.filled == 1.5


class TestLiveTradingError:
    def test_exception(self):
        with pytest.raises(LiveTradingError, match="test error"):
            raise LiveTradingError("test error")


# ---------------------------------------------------------------------------
# factory.py
# ---------------------------------------------------------------------------
class TestExchangeDemoMode:
    def test_true_values(self):
        assert exchange_demo_mode_enabled({"sandbox": True}) is True
        assert exchange_demo_mode_enabled({"use_testnet": "true"}) is True
        assert exchange_demo_mode_enabled({"network": "testnet"}) is True
        assert exchange_demo_mode_enabled({"environment": "demo"}) is True
        assert exchange_demo_mode_enabled({"paper_trading": 1}) is True

    def test_false_values(self):
        assert exchange_demo_mode_enabled({}) is False
        assert exchange_demo_mode_enabled({"sandbox": False}) is False
        assert exchange_demo_mode_enabled({"use_testnet": "false"}) is False
        assert exchange_demo_mode_enabled({"network": "mainnet"}) is False

    def test_non_dict(self):
        assert exchange_demo_mode_enabled(None) is False
        assert exchange_demo_mode_enabled("string") is False


class TestMergeRootOverlay:
    def test_overlay(self):
        root = {"sandbox": True, "base_url": "https://test.example.com"}
        cfg = {"exchange_id": "binance"}
        result = merge_root_exchange_config_overlay(root=root, exchange_config=cfg)
        assert result["exchange_id"] == "binance"
        assert result["sandbox"] is True
        assert result["base_url"] == "https://test.example.com"

    def test_no_overlay(self):
        cfg = {"exchange_id": "okx"}
        result = merge_root_exchange_config_overlay(root={}, exchange_config=cfg)
        assert result == cfg


# ---------------------------------------------------------------------------
# symbols.py
# ---------------------------------------------------------------------------
class TestSymbolNormalization:
    def test_binance_futures(self):
        assert to_binance_futures_symbol("BTC/USDT:USDT") == "BTCUSDT"

    def test_binance_spot(self):
        assert to_binance_spot_symbol("BTC/USDT") == "BTCUSDT"

    def test_okx_swap(self):
        assert to_okx_swap_inst_id("BTC/USDT:USDT") == "BTC-USDT-SWAP"

    def test_okx_spot(self):
        assert to_okx_spot_inst_id("BTC/USDT") == "BTC-USDT"

    def test_bitget_um(self):
        assert to_bitget_um_symbol("ETH/USDT:USDT") == "ETHUSDT"

    def test_bybit(self):
        assert to_bybit_symbol("SOL/USDT:USDT") == "SOLUSDT"

    def test_coinbase(self):
        assert to_coinbase_product_id("BTC/USDT") == "BTC-USDT"

    def test_kraken_btc_to_xbt(self):
        assert to_kraken_pair("BTC/USDT") == "XBTUSDT"
        assert to_kraken_pair("ETH/USDT") == "ETHUSDT"

    def test_kucoin(self):
        assert to_kucoin_symbol("BTC/USDT") == "BTC-USDT"

    def test_kucoin_futures_btc_to_xbt(self):
        assert to_kucoin_futures_symbol("BTC/USDT:USDT") == "XBTUSDTM"

    def test_kraken_futures(self):
        assert to_kraken_futures_symbol("BTC/USDT:USDT") == "PF_XBTUSD"

    def test_gate(self):
        assert to_gate_currency_pair("BTC/USDT") == "BTC_USDT"

    def test_deepcoin_spot(self):
        assert to_deepcoin_symbol("BTC/USDT") == "BTC-USDT"

    def test_deepcoin_swap(self):
        assert to_deepcoin_symbol("BTC/USDT:USDT") == "BTC-USDT-SWAP"

    def test_htx_spot_lowercase(self):
        assert to_htx_spot_symbol("BTC/USDT") == "btcusdt"

    def test_htx_contract(self):
        assert to_htx_contract_code("BTC/USDT:USDT") == "BTC-USDT"


# ---------------------------------------------------------------------------
# records.py
# ---------------------------------------------------------------------------
class TestNormalizeStrategySymbol:
    def test_strip_colon_usdt(self):
        assert normalize_strategy_symbol("BTC/USDT:USDT") == "BTC/USDT"

    def test_underscore_to_slash(self):
        assert normalize_strategy_symbol("BTC_USDT") == "BTC/USDT"

    def test_dash_to_slash(self):
        assert normalize_strategy_symbol("BTC-USDT") == "BTC/USDT"

    def test_bare_symbol(self):
        assert normalize_strategy_symbol("BTC") == "BTC"

    def test_empty(self):
        assert normalize_strategy_symbol("") == ""


# ---------------------------------------------------------------------------
# execution.py
# ---------------------------------------------------------------------------
class TestSignalToSides:
    def test_open_long(self):
        assert _signal_to_sides("open_long") == ("buy", "long", False)

    def test_close_long(self):
        assert _signal_to_sides("close_long") == ("sell", "long", True)

    def test_open_short(self):
        assert _signal_to_sides("open_short") == ("sell", "short", False)

    def test_close_short(self):
        assert _signal_to_sides("close_short") == ("buy", "short", True)

    def test_unknown(self):
        # Default fallback
        assert _signal_to_sides("unknown") == ("buy", "long", False)


class TestNormalizeSymbolForOrder:
    def test_strip_colon(self):
        assert _normalize_symbol_for_order("BTC/USDT:USDT") == "BTC/USDT"

    def test_bare_symbol(self):
        assert _normalize_symbol_for_order("TRX") == "TRX/USDT"

    def test_already_normalized(self):
        assert _normalize_symbol_for_order("BTC/USDT") == "BTC/USDT"

    def test_empty(self):
        assert _normalize_symbol_for_order("") == ""
