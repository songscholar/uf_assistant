"""
UF Stock Assistant — 美股交易后端
基于 Alpaca Markets API（免费 paper trading + 实盘）
"""

from __future__ import annotations

from typing import Any

from app.core.constants import OrderStatus
from app.core.logging import get_logger

from . import ExchangeBackend, OrderResult, PositionResult

logger = get_logger("app.trading.us_stock_backend")


class USStockBackend(ExchangeBackend):
    """美股交易后端

    支持 Alpaca Markets：
    - Paper Trading（免费模拟盘）
    - Live Trading（实盘，需要真实账户）
    - 支持碎股交易（fractional shares）

    credential.extra_config 包含:
        - broker: "alpaca"
        - paper: true/false (默认 true)
    """

    def __init__(self) -> None:
        self._connected = False
        self._client: Any = None
        self._paper: bool = True

    async def connect(self, credential: dict[str, Any]) -> None:
        extra = credential.get("extra_config", {})
        self._paper = extra.get("paper", True)

        try:
            import alpaca_trade_api as tradeapi

            base_url = "https://paper-api.alpaca.markets" if self._paper else "https://api.alpaca.markets"
            self._client = tradeapi.REST(
                key_id=credential["api_key"],
                secret_key=credential["api_secret"],
                base_url=base_url,
                api_version="v2",
            )
            # 验证连接
            account = self._client.get_account()
            self._connected = True
            logger.info(
                "us_stock_connected",
                broker="alpaca",
                paper=self._paper,
                account_status=account.status,
            )
        except ImportError:
            raise ImportError("请安装 alpaca-trade-api: pip install alpaca-trade-api")
        except Exception as exc:
            logger.error("us_stock_connect_failed", error=str(exc))
            raise

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> OrderResult:
        if not self._connected or not self._client:
            raise RuntimeError("未连接，请先调用 connect()")

        try:
            alpaca_side = "buy" if side == "buy" else "sell"
            alpaca_type = {"market": "market", "limit": "limit", "stop": "stop"}.get(order_type, "market")

            order_params: dict[str, Any] = {
                "symbol": symbol.upper(),
                "qty": str(quantity),
                "side": alpaca_side,
                "type": alpaca_type,
                "time_in_force": "day",
            }
            if price is not None and alpaca_type in ("limit", "stop"):
                order_params["limit_price"] = str(price)

            order = self._client.submit_order(**order_params)

            status = self._map_status(order.status)
            return OrderResult(
                exchange_order_id=order.id,
                status=status,
                filled_quantity=float(order.filled_qty or 0),
                filled_price=float(order.filled_avg_price) if order.filled_avg_price else None,
                raw={"alpaca_order": str(order)},
            )

        except Exception as exc:
            logger.error("us_stock_order_failed", symbol=symbol, error=str(exc))
            return OrderResult(
                exchange_order_id="",
                status=OrderStatus.REJECTED,
                raw={"error": str(exc)},
            )

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        if not self._client:
            return False
        try:
            self._client.cancel_order(exchange_order_id)
            logger.info("us_stock_order_cancelled", order_id=exchange_order_id)
            return True
        except Exception as exc:
            logger.error("us_stock_cancel_failed", order_id=exchange_order_id, error=str(exc))
            return False

    async def get_order_status(self, exchange_order_id: str, symbol: str) -> OrderResult:
        if not self._client:
            raise RuntimeError("未连接")
        try:
            order = self._client.get_order(exchange_order_id)
            return OrderResult(
                exchange_order_id=order.id,
                status=self._map_status(order.status),
                filled_quantity=float(order.filled_qty or 0),
                filled_price=float(order.filled_avg_price) if order.filled_avg_price else None,
            )
        except Exception as exc:
            logger.error("us_stock_order_status_failed", order_id=exchange_order_id, error=str(exc))
            return OrderResult(exchange_order_id=exchange_order_id, status=OrderStatus.REJECTED, raw={"error": str(exc)})

    async def get_positions(self) -> list[PositionResult]:
        if not self._client:
            return []
        try:
            positions = self._client.list_positions()
            results = []
            for pos in positions:
                results.append(
                    PositionResult(
                        symbol=pos.symbol,
                        quantity=float(pos.qty),
                        avg_cost=float(pos.avg_entry_price),
                        current_price=float(pos.current_price),
                        unrealized_pnl=float(pos.unrealized_pl),
                    )
                )
            return results
        except Exception as exc:
            logger.error("us_stock_positions_failed", error=str(exc))
            return []

    async def get_balance(self) -> dict[str, float]:
        if not self._client:
            return {}
        try:
            account = self._client.get_account()
            return {"USD": float(account.cash)}
        except Exception as exc:
            logger.error("us_stock_balance_failed", error=str(exc))
            return {}

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        if not self._client:
            return {"last": 0}
        try:
            trade = self._client.get_latest_trade(symbol.upper())
            return {"last": float(trade.price)}
        except Exception:
            return {"last": 0}

    def _map_status(self, alpaca_status: str) -> str:
        mapping = {
            "new": OrderStatus.SUBMITTED,
            "accepted": OrderStatus.SUBMITTED,
            "filled": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIAL,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.REJECTED,
        }
        return mapping.get(alpaca_status, OrderStatus.SUBMITTED)
