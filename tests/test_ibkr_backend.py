"""
测试 IBKR Backend 模块
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.trading.backends import BackendRouter


# ---------------------------------------------------------------------------
# Helper: build a fake ib_insync module tree
# ---------------------------------------------------------------------------

def _build_fake_ib_insync():
    """Return a MagicMock tree that looks enough like ib_insync."""
    fake = MagicMock()
    fake.IB = MagicMock

    # Fake Contract
    fake.Stock = lambda **kw: MagicMock(**kw, _as=dict(kw))

    # Fake Orders
    fake.MarketOrder = lambda **kw: MagicMock(**kw, _type="MarketOrder")
    fake.LimitOrder = lambda **kw: MagicMock(**kw, _type="LimitOrder")

    return fake


@pytest.fixture(autouse=True)
def _ensure_ib_insync_mock():
    """Ensure ib_insync is mocked in sys.modules before any import under test."""
    fake = _build_fake_ib_insync()
    with patch.dict(sys.modules, {"ib_insync": fake}):
        yield


# ---------------------------------------------------------------------------
# LocalBrokerSettings / SaaS gating
# ---------------------------------------------------------------------------

class TestLocalBrokerSettings:
    """测试本地券商配置加载"""

    def test_defaults(self):
        from app.core.config import LocalBrokerSettings
        s = LocalBrokerSettings()
        assert s.allowed is False
        assert s.ibkr_default_host == "127.0.0.1"
        assert s.ibkr_default_port == 7497
        assert s.ibkr_default_client_id == 1
        assert s.ibkr_readonly is False

    def test_env_override(self, monkeypatch):
        from app.core.config import LocalBrokerSettings
        monkeypatch.setenv("STOCK_ASSISTANT_LOCAL_BROKER__ALLOWED", "true")
        monkeypatch.setenv("STOCK_ASSISTANT_LOCAL_BROKER__IBKR_DEFAULT_PORT", "7496")
        s = LocalBrokerSettings()
        assert s.allowed is True
        assert s.ibkr_default_port == 7496


class TestBackendRouter:
    """测试 BackendRouter 对 IBKR 的注册与 SaaS 拦截"""

    def test_supported_markets_without_local_broker(self):
        with patch("app.trading.backends.settings.local_broker.allowed", False):
            markets = BackendRouter.supported_markets()
            assert "ibkr" not in markets

    def test_supported_markets_with_local_broker(self):
        with patch("app.trading.backends.settings.local_broker.allowed", True):
            markets = BackendRouter.supported_markets()
            assert "ibkr" in markets

    def test_create_ibkr_blocked_when_not_allowed(self):
        with patch("app.trading.backends.settings.local_broker.allowed", False):
            with pytest.raises(RuntimeError, match="Local desktop brokers"):
                BackendRouter.create("ibkr")

    def test_create_ibkr_allowed(self):
        with patch("app.trading.backends.settings.local_broker.allowed", True):
            with patch.dict(sys.modules, {"ib_insync": _build_fake_ib_insync()}):
                from app.trading.backends.ibkr_backend import IBKRBackend
                backend = BackendRouter.create("ibkr")
                assert isinstance(backend, IBKRBackend)


# ---------------------------------------------------------------------------
# IBKRBackend 核心方法
# ---------------------------------------------------------------------------

class TestIBKRBackend:
    """测试 IBKRBackend 各方法（全 mock，无需真实 TWS）"""

    @pytest.fixture
    def backend(self):
        with patch.dict(sys.modules, {"ib_insync": _build_fake_ib_insync()}):
            from app.trading.backends.ibkr_backend import IBKRBackend
            return IBKRBackend()

    @pytest.fixture
    def fake_ib(self):
        """Return a mock IB instance that looks real enough."""
        ib = MagicMock()
        ib.managedAccounts.return_value = ["DU12345"]
        ib.positions.return_value = []
        ib.accountSummary.return_value = []
        ib.openTrades.return_value = []
        ib.qualifyContracts.return_value = [MagicMock()]
        ib.reqMktData.return_value = MagicMock(
            last=150.0,
            bid=149.95,
            ask=150.05,
            volume=10000,
        )
        ib.sleep = MagicMock()
        return ib

    @pytest.mark.asyncio
    async def test_connect(self, backend, fake_ib):
        backend._ib = fake_ib
        cred = {
            "extra_config": {
                "ibkr_host": "192.168.1.10",
                "ibkr_port": "7496",
                "ibkr_client_id": "5",
                "ibkr_readonly": True,
                "ibkr_timeout": "30",
            }
        }
        await backend.connect(cred)
        assert backend._account == "DU12345"
        assert backend._config["host"] == "192.168.1.10"
        assert backend._config["port"] == 7496
        assert backend._config["client_id"] == 5
        assert backend._config["readonly"] is True

    @pytest.mark.asyncio
    async def test_connect_defaults(self, backend, fake_ib):
        backend._ib = fake_ib
        await backend.connect({"extra_config": {}})
        assert backend._config["host"] == "127.0.0.1"
        assert backend._config["port"] == 7497

    @pytest.mark.asyncio
    async def test_place_market_order(self, backend, fake_ib):
        backend._ib = fake_ib
        backend._account = "DU12345"

        fake_trade = MagicMock()
        fake_trade.order.orderId = 42
        fake_trade.orderStatus.status = "Filled"
        fake_trade.orderStatus.filled = 10
        fake_trade.orderStatus.avgFillPrice = 150.0
        fake_trade.orderStatus.remaining = 0
        fake_ib.placeOrder.return_value = fake_trade

        result = await backend.place_order("AAPL", "buy", "market", 10)
        assert result.exchange_order_id == "42"
        assert result.status == "filled"
        assert result.filled_quantity == 10
        assert result.filled_price == 150.0

    @pytest.mark.asyncio
    async def test_place_limit_order(self, backend, fake_ib):
        backend._ib = fake_ib
        backend._account = "DU12345"

        fake_trade = MagicMock()
        fake_trade.order.orderId = 43
        fake_trade.orderStatus.status = "Submitted"
        fake_trade.orderStatus.filled = 0
        fake_trade.orderStatus.avgFillPrice = None
        fake_trade.orderStatus.remaining = 5
        fake_ib.placeOrder.return_value = fake_trade

        result = await backend.place_order("TSLA", "sell", "limit", 5, price=200.0)
        assert result.exchange_order_id == "43"
        assert result.status == "submitted"
        assert result.filled_quantity == 0

    @pytest.mark.asyncio
    async def test_place_order_invalid_type(self, backend, fake_ib):
        backend._ib = fake_ib
        backend._account = "DU12345"
        fake_ib.qualifyContracts.return_value = [MagicMock()]

        with pytest.raises(ValueError, match="Unsupported order type"):
            await backend.place_order("AAPL", "buy", "stop", 1)

    @pytest.mark.asyncio
    async def test_cancel_order(self, backend, fake_ib):
        backend._ib = fake_ib
        backend._account = "DU12345"

        fake_trade = MagicMock()
        fake_trade.order.orderId = 42
        fake_ib.openTrades.return_value = [fake_trade]

        ok = await backend.cancel_order("42", "AAPL")
        assert ok is True
        fake_ib.cancelOrder.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, backend, fake_ib):
        backend._ib = fake_ib
        fake_ib.openTrades.return_value = []

        ok = await backend.cancel_order("99", "AAPL")
        assert ok is False

    @pytest.mark.asyncio
    async def test_get_order_status(self, backend, fake_ib):
        backend._ib = fake_ib

        fake_trade = MagicMock()
        fake_trade.order.orderId = 42
        fake_trade.orderStatus.status = "Filled"
        fake_trade.orderStatus.filled = 5
        fake_trade.orderStatus.avgFillPrice = 151.0
        fake_ib.openTrades.return_value = [fake_trade]

        result = await backend.get_order_status("42", "AAPL")
        assert result.exchange_order_id == "42"
        assert result.status == "filled"
        assert result.filled_quantity == 5
        assert result.filled_price == 151.0

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self, backend, fake_ib):
        backend._ib = fake_ib
        fake_ib.openTrades.return_value = []

        result = await backend.get_order_status("99", "AAPL")
        assert result.status == "unknown"

    @pytest.mark.asyncio
    async def test_get_positions(self, backend, fake_ib):
        backend._ib = fake_ib
        backend._account = "DU12345"

        pos = MagicMock()
        pos.contract.symbol = "AAPL"
        pos.position = 100
        pos.avgCost = 145.0
        fake_ib.positions.return_value = [pos]

        results = await backend.get_positions()
        assert len(results) == 1
        assert results[0].symbol == "AAPL"
        assert results[0].quantity == 100
        assert results[0].avg_cost == 145.0

    @pytest.mark.asyncio
    async def test_get_balance(self, backend, fake_ib):
        backend._ib = fake_ib
        backend._account = "DU12345"

        item = MagicMock()
        item.tag = "NetLiquidation"
        item.value = "100000.50"
        fake_ib.accountSummary.return_value = [item]

        bal = await backend.get_balance()
        assert bal["NetLiquidation"] == 100000.50

    @pytest.mark.asyncio
    async def test_get_ticker(self, backend, fake_ib):
        backend._ib = fake_ib
        backend._account = "DU12345"

        ticker = await backend.get_ticker("AAPL")
        assert ticker["last"] == 150.0
        assert ticker["bid"] == 149.95
        assert ticker["ask"] == 150.05
        assert ticker["volume"] == 10000

    def test_normalize_symbol(self):
        from app.trading.backends.ibkr_backend import _normalize_symbol
        assert _normalize_symbol("aapl", "USStock") == ("AAPL", "SMART", "USD")
        assert _normalize_symbol("  tsla  ", "") == ("TSLA", "SMART", "USD")
