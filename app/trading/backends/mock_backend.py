"""
UF Stock Assistant — 模拟交易后端
内存模拟，不连接真实交易所。兼容现有 MockTradingBackend 逻辑。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.constants import OrderStatus, OrderSide
from app.core.logging import get_logger

from . import ExchangeBackend, OrderResult, PositionResult

logger = get_logger("app.trading.mock_backend")


class MockBackend(ExchangeBackend):
    """模拟交易后端 — 内存中模拟下单和持仓"""

    def __init__(self) -> None:
        self._balance: dict[str, float] = {"USDT": 100_000, "CNY": 100_000, "USD": 100_000}
        self._positions: dict[str, dict] = {}  # symbol -> {quantity, avg_cost, total_cost}
        self._orders: dict[str, dict] = {}
        self._connected = False

    async def connect(self, credential: dict[str, Any] | None = None) -> None:
        self._connected = True
        logger.info("mock_backend_connected")

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> OrderResult:
        """模拟下单 — 市价单立即成交，限价单也立即成交（简化）"""
        if not self._connected:
            await self.connect()

        order_id = str(uuid.uuid4())
        filled_price = price or self._get_mock_price(symbol)

        # 检查余额/持仓
        cost = filled_price * quantity
        if side == OrderSide.BUY:
            currency = self._infer_currency(symbol)
            if self._balance.get(currency, 0) < cost:
                return OrderResult(
                    exchange_order_id=order_id,
                    status=OrderStatus.REJECTED,
                    raw={"error": "余额不足"},
                )
            self._balance[currency] = self._balance.get(currency, 0) - cost
            self._update_position_buy(symbol, quantity, filled_price)
        else:
            pos = self._positions.get(symbol)
            if not pos or pos["quantity"] < quantity:
                return OrderResult(
                    exchange_order_id=order_id,
                    status=OrderStatus.REJECTED,
                    raw={"error": "持仓不足"},
                )
            pnl = self._update_position_sell(symbol, quantity, filled_price)
            currency = self._infer_currency(symbol)
            self._balance[currency] = self._balance.get(currency, 0) + cost

        result = OrderResult(
            exchange_order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            filled_price=filled_price,
            fee=round(cost * 0.001, 4),  # 0.1% 手续费
            fee_currency=self._infer_currency(symbol),
            raw={"simulated": True},
        )

        self._orders[order_id] = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "filled_price": filled_price,
            "status": OrderStatus.FILLED,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("mock_order_filled", order_id=order_id, symbol=symbol, side=side, price=filled_price)
        return result

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        if exchange_order_id in self._orders:
            self._orders[exchange_order_id]["status"] = OrderStatus.CANCELLED
            return True
        return False

    async def get_order_status(self, exchange_order_id: str, symbol: str) -> OrderResult:
        order = self._orders.get(exchange_order_id)
        if not order:
            return OrderResult(exchange_order_id=exchange_order_id, status=OrderStatus.REJECTED, raw={"error": "订单不存在"})
        return OrderResult(
            exchange_order_id=exchange_order_id,
            status=order["status"],
            filled_quantity=order["quantity"] if order["status"] == OrderStatus.FILLED else 0,
            filled_price=order.get("filled_price"),
        )

    async def get_positions(self) -> list[PositionResult]:
        results = []
        for symbol, pos in self._positions.items():
            if pos["quantity"] > 0:
                current_price = self._get_mock_price(symbol)
                unrealized = (current_price - pos["avg_cost"]) * pos["quantity"]
                results.append(
                    PositionResult(
                        symbol=symbol,
                        quantity=pos["quantity"],
                        avg_cost=pos["avg_cost"],
                        current_price=current_price,
                        unrealized_pnl=round(unrealized, 4),
                    )
                )
        return results

    async def get_balance(self) -> dict[str, float]:
        return dict(self._balance)

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        price = self._get_mock_price(symbol)
        return {"last": price, "bid": price * 0.999, "ask": price * 1.001}

    # ── 内部辅助方法 ──────────────────────────────────────────────────────────

    def _get_mock_price(self, symbol: str) -> float:
        """返回模拟价格（基于 symbol hash 生成稳定价格）"""
        mock_prices = {
            "BTC/USDT": 65000, "ETH/USDT": 3500, "BNB/USDT": 600,
            "SOL/USDT": 150, "DOGE/USDT": 0.15, "XRP/USDT": 0.55,
            "600519": 1800, "000858": 150, "601318": 50,  # A股
            "AAPL": 185, "TSLA": 250, "NVDA": 900,  # 美股
        }
        return mock_prices.get(symbol, 100.0)

    def _infer_currency(self, symbol: str) -> str:
        if "/" in symbol:
            return symbol.split("/")[1]
        if symbol.isdigit() or (len(symbol) == 6 and symbol[:2] in ("60", "00", "30")):
            return "CNY"
        return "USD"

    def _update_position_buy(self, symbol: str, quantity: float, price: float) -> None:
        pos = self._positions.get(symbol)
        if pos:
            total_cost = pos["avg_cost"] * pos["quantity"] + price * quantity
            pos["quantity"] += quantity
            pos["avg_cost"] = total_cost / pos["quantity"]
        else:
            self._positions[symbol] = {
                "quantity": quantity,
                "avg_cost": price,
                "total_cost": price * quantity,
            }

    def _update_position_sell(self, symbol: str, quantity: float, price: float) -> float:
        pos = self._positions.get(symbol)
        if not pos:
            return 0
        pnl = (price - pos["avg_cost"]) * quantity
        pos["quantity"] -= quantity
        return round(pnl, 4)
