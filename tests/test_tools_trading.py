"""
测试交易工具模块（即时成交模拟交易模型）
"""

import pytest

from app.core.constants import OrderSide, OrderType, TradeType
from app.core.exceptions import TradingError
from app.tools.trading import (
    MockTradingBackend,
    cancel_order,
    get_orders,
    get_portfolio,
    get_positions,
    submit_order,
)
from app.trading.models import get_db_session, MockPortfolio, Position, TradeLog, SettlementTask


class TestMockTradingBackend:
    """测试模拟交易后端"""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """每个测试前清理数据"""
        db = get_db_session()
        db.query(TradeLog).delete()
        db.query(SettlementTask).delete()
        db.query(Position).delete()
        db.query(MockPortfolio).delete()
        db.commit()
        yield
        db.close()

    def test_submit_buy_order(self):
        """测试提交买入订单（即时持仓）"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999001, initial_capital=1_000_000)
        order = backend.submit_order(
            db=db,
            symbol="000001",
            side=OrderSide.BUY.value,
            quantity=100,
            price=10.0,
            order_type=OrderType.LIMIT.value,
            trade_type=TradeType.NORMAL,
            exchange_code="SH",
        )
        assert order["order_id"] is not None
        assert order["status"] == "filled"
        assert order["quantity"] == 100
        assert order["price"] == 10.0
        assert order["fees"]["total"] > 0
        db.close()

    def test_position_after_buy(self):
        """测试买入后即时持仓"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999002, initial_capital=1_000_000)
        backend.submit_order(
            db=db,
            symbol="000001",
            side=OrderSide.BUY.value,
            quantity=100,
            price=10.0,
            order_type=OrderType.MARKET.value,
            trade_type=TradeType.NORMAL,
            exchange_code="SH",
        )
        result = get_positions(user_id=999002)
        assert len(result["positions"]) == 1
        assert result["positions"][0]["total_quantity"] == 100
        assert result["positions"][0]["available_quantity"] == 100
        assert result["positions"][0]["avg_cost"] == 10.0

        # 持仓市值已计入总资产
        pf = get_portfolio(user_id=999002)
        assert pf["summary"]["position_value"] == 1000.0
        assert pf["summary"]["frozen_cash"] == 0
        db.close()

    def test_avg_cost_weighted(self):
        """测试成本价加权平均"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999003, initial_capital=1_000_000)
        backend.submit_order(
            db=db, symbol="000001", side="buy", quantity=100, price=10.0,
            order_type="market", trade_type=TradeType.NORMAL, exchange_code="SH",
        )
        backend.submit_order(
            db=db, symbol="000001", side="buy", quantity=100, price=20.0,
            order_type="market", trade_type=TradeType.NORMAL, exchange_code="SH",
        )
        result = get_positions(user_id=999003)
        assert result["positions"][0]["avg_cost"] == 15.0
        assert result["positions"][0]["total_quantity"] == 200
        db.close()

    def test_position_after_sell(self):
        """测试卖出后持仓和收益"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999004, initial_capital=1_000_000)
        # 买入
        backend.submit_order(
            db=db, symbol="000001", side="buy", quantity=100, price=10.0,
            order_type="market", trade_type=TradeType.NORMAL, exchange_code="SH",
        )
        # 卖出
        backend.submit_order(
            db=db, symbol="000001", side="sell", quantity=50, price=12.0,
            order_type="market", trade_type=TradeType.NORMAL, exchange_code="SH",
        )
        result = get_positions(user_id=999004)
        assert result["positions"][0]["total_quantity"] == 50
        assert result["positions"][0]["available_quantity"] == 50
        assert result["positions"][0]["realized_pnl"] > 0

        pf = get_portfolio(user_id=999004)
        assert pf["summary"]["total_pnl"] > 0
        db.close()

    def test_full_sell(self):
        """测试清仓"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999005, initial_capital=1_000_000)
        backend.submit_order(
            db=db, symbol="000001", side="buy", quantity=100, price=10.0,
            order_type="market", trade_type=TradeType.NORMAL, exchange_code="SH",
        )
        backend.submit_order(
            db=db, symbol="000001", side="sell", quantity=100, price=12.0,
            order_type="market", trade_type=TradeType.NORMAL, exchange_code="SH",
        )
        result = get_positions(user_id=999005)
        assert len(result["positions"]) == 0

        pf = get_portfolio(user_id=999005)
        assert pf["summary"]["position_value"] == 0
        assert pf["summary"]["total_pnl"] > 0
        db.close()

    def test_cancel_order(self):
        """测试取消订单——已成交订单无法取消"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999006, initial_capital=1_000_000)
        order = backend.submit_order(
            db=db, symbol="000001", side="buy", quantity=100, price=10.0,
            order_type="limit", trade_type=TradeType.NORMAL, exchange_code="SH",
        )
        result = cancel_order(user_id=999006, order_id=order["order_id"])
        assert result["success"] is False
        db.close()

    def test_portfolio_summary(self):
        """测试投资组合摘要"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999007, initial_capital=1_000_000)
        backend.submit_order(
            db=db, symbol="000001", side="buy", quantity=100, price=10.0,
            order_type="market", trade_type=TradeType.NORMAL, exchange_code="SH",
        )
        result = get_portfolio(user_id=999007)
        assert result["summary"]["total_positions"] == 1
        assert result["summary"]["initial_capital"] == 1_000_000.0
        assert result["summary"]["frozen_cash"] == 0
        db.close()

    def test_insufficient_funds(self):
        """测试资金不足"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999008, initial_capital=1000)
        with pytest.raises(TradingError, match="可用资金不足"):
            backend.submit_order(
                db=db, symbol="000001", side="buy", quantity=1000, price=100.0,
                order_type="limit", trade_type=TradeType.NORMAL, exchange_code="SH",
            )
        db.close()

    def test_block_trade_min_size(self):
        """测试大宗交易限额"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999009, initial_capital=10_000_000)
        with pytest.raises(TradingError, match="大宗交易限额不足"):
            backend.submit_order(
                db=db, symbol="600519", side="buy", quantity=100, price=100.0,
                order_type="limit", trade_type=TradeType.BLOCK_TRADE, exchange_code="SH",
            )
        db.close()

    def test_stock_connect_fees(self):
        """测试港股通费用"""
        db = get_db_session()
        backend = MockTradingBackend(user_id=999010, initial_capital=1_000_000)
        order = backend.submit_order(
            db=db, symbol="00700", side="buy", quantity=100, price=400.0,
            order_type="limit", trade_type=TradeType.STOCK_CONNECT_SH, exchange_code="HK",
        )
        fees = order["fees"]
        assert fees["stamp_tax"] > 0
        assert fees["portfolio_fee"] > 0
        db.close()


class TestTradingTools:
    """测试交易工具函数"""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        db = get_db_session()
        db.query(TradeLog).delete()
        db.query(SettlementTask).delete()
        db.query(Position).delete()
        db.query(MockPortfolio).delete()
        db.commit()
        yield
        db.close()

    def test_submit_order_success(self):
        """测试成功下单"""
        result = submit_order(
            user_id=999101, symbol="000001", side="buy", quantity=100,
            price=10.5, order_type="limit", trade_type="normal", exchange_code="SH",
        )
        assert result["order_id"] is not None
        assert result["symbol"] == "000001"
        assert result["side"] == "buy"

    def test_submit_order_invalid_side(self):
        """测试无效订单方向"""
        with pytest.raises(TradingError):
            submit_order(
                user_id=999102, symbol="000001", side="invalid", quantity=100,
                price=10.5, order_type="limit", trade_type="normal", exchange_code="SH",
            )

    def test_get_positions(self):
        """测试获取持仓"""
        submit_order(
            user_id=999103, symbol="000002", side="buy", quantity=200,
            price=20.0, order_type="limit", trade_type="normal", exchange_code="SH",
        )
        result = get_positions(user_id=999103)
        assert "positions" in result
        assert "summary" in result

    def test_get_orders(self):
        """测试获取订单"""
        submit_order(
            user_id=999104, symbol="000004", side="buy", quantity=100,
            price=10.0, order_type="limit", trade_type="normal", exchange_code="SH",
        )
        result = get_orders(user_id=999104)
        assert "orders" in result
        assert "count" in result

    def test_get_portfolio(self):
        """测试获取投资组合"""
        submit_order(
            user_id=999105, symbol="000005", side="buy", quantity=100,
            price=10.0, order_type="limit", trade_type="normal", exchange_code="SH",
        )
        result = get_portfolio(user_id=999105)
        assert "summary" in result
        assert "positions" in result
