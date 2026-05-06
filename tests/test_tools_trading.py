"""
测试交易工具模块
"""

import json

import pytest

from app.core.constants import OrderSide, OrderStatus, OrderType
from app.core.exceptions import TradingError
from app.tools.trading import (
    MockTradingBackend,
    cancel_order,
    get_orders,
    get_portfolio,
    get_position,
    get_positions,
    submit_order,
)


class TestMockTradingBackend:
    """测试模拟交易后端"""

    def test_submit_buy_order(self):
        """测试提交买入订单"""
        backend = MockTradingBackend()
        order = backend.submit_order({
            "symbol": "000001",
            "side": OrderSide.BUY.value,
            "quantity": 100,
            "price": 10.5,
            "order_type": OrderType.LIMIT.value,
        })
        
        assert order["id"] is not None
        assert order["status"] == OrderStatus.FILLED.value
        assert order["filled_quantity"] == 100
        assert order["filled_price"] == 10.5

    def test_position_after_buy(self):
        """测试买入后持仓"""
        backend = MockTradingBackend()
        backend.submit_order({
            "symbol": "000001",
            "side": OrderSide.BUY.value,
            "quantity": 100,
            "price": 10.0,
            "order_type": OrderType.MARKET.value,
        })
        
        pos = backend.get_position("000001")
        assert pos is not None
        assert pos["quantity"] == 100
        assert pos["avg_cost"] == 10.0

    def test_position_after_sell(self):
        """测试卖出后持仓"""
        backend = MockTradingBackend()
        backend.submit_order({
            "symbol": "000001",
            "side": OrderSide.BUY.value,
            "quantity": 100,
            "price": 10.0,
            "order_type": OrderType.MARKET.value,
        })
        backend.submit_order({
            "symbol": "000001",
            "side": OrderSide.SELL.value,
            "quantity": 50,
            "price": 12.0,
            "order_type": OrderType.MARKET.value,
        })
        
        pos = backend.get_position("000001")
        assert pos["quantity"] == 50
        assert pos["realized_pnl"] == 100.0  # (12-10) * 50

    def test_cancel_order(self):
        """测试取消订单"""
        backend = MockTradingBackend()
        order = backend.submit_order({
            "symbol": "000001",
            "side": OrderSide.BUY.value,
            "quantity": 100,
            "price": 10.0,
            "order_type": OrderType.LIMIT.value,
        })
        
        # 已成交的订单无法取消
        assert backend.cancel_order(order["id"]) is False

    def test_portfolio_summary(self):
        """测试投资组合摘要"""
        backend = MockTradingBackend()
        backend.submit_order({
            "symbol": "000001",
            "side": OrderSide.BUY.value,
            "quantity": 100,
            "price": 10.0,
            "order_type": OrderType.MARKET.value,
        })
        
        summary = backend.get_portfolio_summary()
        assert summary["total_positions"] == 1
        assert summary["total_cost"] == 1000.0


class TestTradingTools:
    """测试交易工具函数"""

    def test_submit_order_success(self):
        """测试成功下单"""
        result = submit_order("000001", "buy", 100, 10.5, "limit")
        data = json.loads(result)
        assert data["success"] is True
        assert data["order"]["symbol"] == "000001"
        assert data["order"]["side"] == "buy"

    def test_submit_order_invalid_side(self):
        """测试无效订单方向"""
        with pytest.raises(TradingError):
            submit_order("000001", "invalid", 100, 10.5, "limit")

    def test_get_positions(self):
        """测试获取持仓"""
        # 先下单
        submit_order("000002", "buy", 200, 20.0, "limit")
        
        result = get_positions()
        data = json.loads(result)
        assert "positions" in data
        assert "summary" in data

    def test_get_position(self):
        """测试获取单个持仓"""
        submit_order("000003", "buy", 300, 30.0, "limit")
        
        result = get_position("000003")
        data = json.loads(result)
        assert data["has_position"] is True

    def test_get_position_not_found(self):
        """测试无持仓"""
        result = get_position("999999")
        data = json.loads(result)
        assert data["has_position"] is False

    def test_get_orders(self):
        """测试获取订单"""
        result = get_orders()
        data = json.loads(result)
        assert "orders" in data
        assert "count" in data

    def test_cancel_order(self):
        """测试取消订单"""
        result = submit_order("000004", "buy", 100, 10.0, "limit")
        order_data = json.loads(result)
        order_id = order_data["order"]["id"]
        
        # 已成交的订单无法取消
        result = cancel_order(order_id)
        data = json.loads(result)
        assert data["success"] is False

    def test_get_portfolio(self):
        """测试获取投资组合"""
        result = get_portfolio()
        data = json.loads(result)
        assert "summary" in data
        assert "positions" in data
