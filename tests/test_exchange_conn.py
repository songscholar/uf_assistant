"""
测试交易所连接测试增强版 — IP 检测、demo 检测、-2015 诊断
"""

from __future__ import annotations

import pytest

from app.strategies.exchange_client import (
    _hint_binance_2015,
    exchange_demo_mode_enabled,
    safe_exchange_config_for_log,
)
import app.strategies.strategy_service as strategy_service


class TestExchangeDemoModeEnabled:
    def test_env_variants(self):
        assert exchange_demo_mode_enabled({"network": "testnet"}) is True
        assert exchange_demo_mode_enabled({"environment": "sandbox"}) is True
        assert exchange_demo_mode_enabled({"env": "demo"}) is True
        assert exchange_demo_mode_enabled({"env": "paper"}) is True
        assert exchange_demo_mode_enabled({"env": "production"}) is False

    def test_bool_flags(self):
        assert exchange_demo_mode_enabled({"enable_demo_trading": True}) is True
        assert exchange_demo_mode_enabled({"use_testnet": True}) is True
        assert exchange_demo_mode_enabled({"sandbox": True}) is True
        assert exchange_demo_mode_enabled({"enable_demo_trading": False}) is False

    def test_string_flags(self):
        assert exchange_demo_mode_enabled({"is_testnet": "true"}) is True
        assert exchange_demo_mode_enabled({"is_testnet": "1"}) is True
        assert exchange_demo_mode_enabled({"is_testnet": "yes"}) is True
        assert exchange_demo_mode_enabled({"is_testnet": "no"}) is False

    def test_int_flags(self):
        assert exchange_demo_mode_enabled({"simulated_trading": 1}) is True
        assert exchange_demo_mode_enabled({"simulated_trading": 0}) is False


class TestSafeExchangeConfigForLog:
    def test_masking(self):
        cfg = {
            "api_key": "abcdefghijklmnopqrstuvwxyz",
            "secret": "1234567890abcdef",
            "passphrase": "my_secret",
            "normal_field": "visible",
        }
        safe = safe_exchange_config_for_log(cfg)
        assert safe["normal_field"] == "visible"
        assert safe["api_key"] == "abcd****wxyz"
        assert safe["secret"] == "1234****cdef"
        assert safe["passphrase"] == "my_s****cret"


class TestHintBinance2015:
    def test_contains_all_parts(self):
        hint = _hint_binance_2015("swap", "fapi.binance.com", False, True, "spot")
        assert "-2015" in hint
        assert "swap" in hint
        assert "spot" in hint
        assert "Mainnet mode" in hint
        assert "Auto-check" in hint
        assert "币安接口返回" in hint

    def test_demo_hint(self):
        hint = _hint_binance_2015("spot", "api.binance.com", True, False)
        assert "Demo mode" in hint


class TestTestExchangeConnection:
    def test_missing_exchange_id(self):
        result = strategy_service.test_exchange_connection({})
        assert result["success"] is False
        assert "Missing exchange_id" in result["message"]

    def test_invalid_exchange(self):
        result = strategy_service.test_exchange_connection({
            "exchange_id": "nonexistent_exchange",
            "api_key": "test",
            "api_secret": "test",
        })
        assert result["success"] is False
        assert "Create client failed" in result["message"] or "不支持的交易所" in result["message"]

    def test_public_ping_failure(self, monkeypatch):
        """模拟 public ping 失败"""
        calls = []

        class FakeClient:
            name = "FakeClient"
            _exchange = type("FakeEx", (), {"fetch_time": lambda self: (_ for _ in ()).throw(Exception("timeout"))})()

        def fake_init(*args, **kwargs):
            calls.append("init")
            return FakeClient()

        monkeypatch.setattr(
            "app.strategies.exchange_client.CCXTExchangeClient", fake_init
        )

        result = strategy_service.test_exchange_connection({
            "exchange_id": "binance",
            "api_key": "test",
            "api_secret": "test",
        })
        assert result["success"] is False
        assert "Public ping failed" in result["message"]

    def test_auth_failure_with_hint(self, monkeypatch):
        """模拟 Binance -2015 错误，验证提示生成"""
        calls = []

        class FakeEx:
            def fetch_time(self):
                return 1234567890
            def fetch_balance(self):
                raise Exception("-2015 Invalid API-key, IP, or permissions")

        class FakeClient:
            name = "FakeClient"
            _exchange = FakeEx()
            def get_balance(self):
                return self._exchange.fetch_balance()

        def fake_init(*args, **kwargs):
            calls.append("init")
            return FakeClient()

        monkeypatch.setattr(
            "app.strategies.exchange_client.CCXTExchangeClient", fake_init
        )

        result = strategy_service.test_exchange_connection({
            "exchange_id": "binance",
            "market_type": "swap",
            "api_key": "test",
            "api_secret": "test",
        })
        assert result["success"] is False
        assert "-2015" in result["message"]
