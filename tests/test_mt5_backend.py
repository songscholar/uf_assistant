"""
测试 MT5 Backend 模块
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from app.trading.backends import BackendRouter


# ---------------------------------------------------------------------------
# Helper: build a fake MetaTrader5 module tree
# ---------------------------------------------------------------------------

def _make_fake_mt5():
    """Return a MagicMock tree that looks enough like MetaTrader5."""
    fake = MagicMock()
    fake.TRADE_RETCODE_DONE = 10009
    fake.TRADE_ACTION_DEAL = 1
    fake.TRADE_ACTION_PENDING = 5
    fake.TRADE_ACTION_REMOVE = 3
    fake.ORDER_TYPE_BUY = 0
    fake.ORDER_TYPE_SELL = 1
    fake.ORDER_TYPE_BUY_LIMIT = 2
    fake.ORDER_TYPE_SELL_LIMIT = 3
    fake.ORDER_TYPE_BUY_STOP = 4
    fake.ORDER_TYPE_SELL_STOP = 5
    fake.ORDER_TIME_GTC = 0
    fake.ORDER_FILLING_IOC = 1
    fake.ORDER_FILLING_FOK = 2
    fake.ORDER_FILLING_RETURN = 3
    fake.POSITION_TYPE_BUY = 0
    fake.POSITION_TYPE_SELL = 1
    return fake


@pytest.fixture(autouse=True)
def _patch_mt5_module():
    """Ensure MetaTrader5 is mocked in sys.modules; yield the shared mock."""
    fake = _make_fake_mt5()
    with patch.dict(sys.modules, {"MetaTrader5": fake}):
        # Reset backend module-level cache so each test starts clean
        from app.trading.backends import mt5_backend
        mt5_backend._mt5 = None
        yield fake


# ---------------------------------------------------------------------------
# BackendRouter MT5 gating
# ---------------------------------------------------------------------------

class TestBackendRouterMT5:
    """测试 BackendRouter 对 MT5 的注册与 SaaS 拦截"""

    def test_supported_markets_without_local_broker(self):
        with patch("app.trading.backends.settings.local_broker.allowed", False):
            markets = BackendRouter.supported_markets()
            assert "mt5" not in markets

    def test_supported_markets_with_local_broker(self):
        with patch("app.trading.backends.settings.local_broker.allowed", True):
            markets = BackendRouter.supported_markets()
            assert "mt5" in markets

    def test_create_mt5_blocked_when_not_allowed(self):
        with patch("app.trading.backends.settings.local_broker.allowed", False):
            with pytest.raises(RuntimeError, match="Local desktop brokers"):
                BackendRouter.create("mt5")

    def test_create_mt5_allowed(self):
        with patch("app.trading.backends.settings.local_broker.allowed", True):
            backend = BackendRouter.create("mt5")
            from app.trading.backends.mt5_backend import MT5Backend
            assert isinstance(backend, MT5Backend)


# ---------------------------------------------------------------------------
# MT5Backend 核心方法
# ---------------------------------------------------------------------------

class TestMT5Backend:
    """测试 MT5Backend 各方法（全 mock，无需真实 MT5）"""

    @pytest.fixture
    def backend(self, _patch_mt5_module):
        from app.trading.backends.mt5_backend import MT5Backend
        return MT5Backend()

    def _configure_mt5(self, fake_mt5):
        """Configure the shared mock with sensible defaults."""
        fake_mt5.initialize.return_value = True
        fake_mt5.account_info.return_value = MagicMock(
            login=12345,
            server="ICMarkets-Demo",
            balance=10000.0,
        )
        fake_mt5.last_error.return_value = (0, "")
        fake_mt5.positions_get.return_value = []
        fake_mt5.orders_get.return_value = []
        fake_mt5.history_deals_get.return_value = []
        fake_mt5.order_send.return_value = MagicMock(
            retcode=fake_mt5.TRADE_RETCODE_DONE,
            order=42,
            deal=43,
            volume=0.1,
            price=1.0850,
            comment="Done",
            _asdict=lambda: {"order": 42, "deal": 43},
        )
        fake_mt5.symbol_info.return_value = MagicMock(
            visible=True,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            point=0.00001,
            filling_mode=fake_mt5.ORDER_FILLING_IOC,
        )
        fake_mt5.symbol_info_tick.return_value = MagicMock(
            bid=1.0849,
            ask=1.0851,
            last=1.0850,
            volume=1000,
            time=1234567890,
        )
        fake_mt5.symbol_select.return_value = True

    @pytest.mark.asyncio
    async def test_connect(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        cred = {
            "extra_config": {
                "mt5_login": "12345",
                "mt5_password": "secret",
                "mt5_server": "ICMarkets-Demo",
                "mt5_terminal_path": "C:/MT5/terminal64.exe",
                "mt5_magic_number": "999",
            }
        }
        await backend.connect(cred)
        assert backend._config["login"] == 12345
        assert backend._config["magic_number"] == 999
        assert backend._connected is True

    @pytest.mark.asyncio
    async def test_place_market_order(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        backend._config = {"magic_number": 123456}
        result = await backend.place_order("EURUSD", "buy", "market", 0.1)
        assert result.exchange_order_id == "42"
        assert result.status == "filled"
        assert result.filled_quantity == 0.1
        assert result.filled_price == 1.0850

    @pytest.mark.asyncio
    async def test_place_limit_order(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        backend._config = {"magic_number": 123456}
        result = await backend.place_order("GBPUSD", "sell", "limit", 0.05, price=1.3000)
        assert result.exchange_order_id == "42"
        assert result.status == "submitted"

    @pytest.mark.asyncio
    async def test_place_order_invalid_type(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        backend._config = {"magic_number": 123456}
        with pytest.raises(ValueError, match="Unsupported order type"):
            await backend.place_order("EURUSD", "buy", "stop", 0.1)

    @pytest.mark.asyncio
    async def test_cancel_order(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        _patch_mt5_module.order_send.return_value = MagicMock(
            retcode=_patch_mt5_module.TRADE_RETCODE_DONE,
        )
        ok = await backend.cancel_order("42", "EURUSD")
        assert ok is True

    @pytest.mark.asyncio
    async def test_cancel_order_failed(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        _patch_mt5_module.order_send.return_value = MagicMock(
            retcode=10018,
            comment="Invalid order",
        )
        ok = await backend.cancel_order("99", "EURUSD")
        assert ok is False

    @pytest.mark.asyncio
    async def test_get_order_status_pending(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        fake_order = MagicMock(ticket=42, type=2, volume_current=0.05)
        _patch_mt5_module.orders_get.return_value = [fake_order]
        _patch_mt5_module.history_deals_get.return_value = []
        result = await backend.get_order_status("42", "EURUSD")
        assert result.status == "submitted"

    @pytest.mark.asyncio
    async def test_get_order_status_filled(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        _patch_mt5_module.orders_get.return_value = []
        fake_deal = MagicMock(ticket=43, volume=0.1, price=1.0850)
        _patch_mt5_module.history_deals_get.return_value = [fake_deal]
        result = await backend.get_order_status("42", "EURUSD")
        assert result.status == "filled"
        assert result.filled_quantity == 0.1
        assert result.filled_price == 1.0850

    @pytest.mark.asyncio
    async def test_get_order_status_unknown(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        _patch_mt5_module.orders_get.return_value = []
        _patch_mt5_module.history_deals_get.return_value = []
        result = await backend.get_order_status("99", "EURUSD")
        assert result.status == "unknown"

    @pytest.mark.asyncio
    async def test_get_positions(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        fake_pos = MagicMock(
            symbol="EURUSD",
            type=_patch_mt5_module.POSITION_TYPE_BUY,
            volume=0.1,
            price_open=1.0800,
        )
        _patch_mt5_module.positions_get.return_value = [fake_pos]
        results = await backend.get_positions()
        assert len(results) == 1
        assert results[0].symbol == "EURUSD"
        assert results[0].quantity == 0.1
        assert results[0].avg_cost == 1.0800

    @pytest.mark.asyncio
    async def test_get_positions_sell(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        fake_pos = MagicMock(
            symbol="GBPUSD",
            type=_patch_mt5_module.POSITION_TYPE_SELL,
            volume=0.2,
            price_open=1.3000,
        )
        _patch_mt5_module.positions_get.return_value = [fake_pos]
        results = await backend.get_positions()
        assert results[0].quantity == -0.2

    @pytest.mark.asyncio
    async def test_get_balance(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        _patch_mt5_module.account_info.return_value = MagicMock(
            balance=5000.0,
            equity=5100.0,
            margin=100.0,
            margin_free=4900.0,
            margin_level=5000.0,
            profit=100.0,
        )
        bal = await backend.get_balance()
        assert bal["balance"] == 5000.0
        assert bal["equity"] == 5100.0

    @pytest.mark.asyncio
    async def test_get_ticker(self, backend, _patch_mt5_module):
        self._configure_mt5(_patch_mt5_module)
        backend._connected = True
        ticker = await backend.get_ticker("EURUSD")
        assert ticker["bid"] == 1.0849
        assert ticker["ask"] == 1.0851
        assert ticker["last"] == 1.0850

    def test_normalize_symbol(self):
        from app.trading.backends.mt5_backend import _normalize_symbol
        assert _normalize_symbol("eur/usd") == "EURUSD"
        assert _normalize_symbol("  gbp-usd  ") == "GBPUSD"
        assert _normalize_symbol("XAU_USD") == "XAUUSD"

    def test_round_volume(self):
        from app.trading.backends.mt5_backend import _round_volume
        assert _round_volume(0.123, 0.01) == 0.12
        # Python banker's rounding: round(0.125, 2) -> 0.12
        assert _round_volume(0.126, 0.01) == 0.13
