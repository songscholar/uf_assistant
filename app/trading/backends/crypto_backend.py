"""
UF Stock Assistant — 加密货币交易后端
基于 CCXT，默认 Gate.io（国内可访问）
"""

from __future__ import annotations

from typing import Any

import ccxt

from app.core.constants import OrderStatus, OrderSide
from app.core.logging import get_logger

from . import ExchangeBackend, OrderResult, PositionResult

logger = get_logger("app.trading.crypto_backend")


class CryptoBackend(ExchangeBackend):
    """加密货币交易后端 — 通过 CCXT 连接交易所"""

    def __init__(self) -> None:
        self.exchange: ccxt.Exchange | None = None
        self._exchange_id: str = "gate"

    async def connect(self, credential: dict[str, Any]) -> None:
        """使用凭证连接交易所

        credential 字典包含:
            - api_key: API Key
            - api_secret: API Secret
            - passphrase: 部分交易所需要（如 OKX）
            - extra_config: {"exchange": "gate"} 指定交易所
        """
        self._exchange_id = credential.get("extra_config", {}).get("exchange", "gate")
        exchange_class = getattr(ccxt, self._exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"不支持的交易所: {self._exchange_id}")

        config: dict[str, Any] = {
            "apiKey": credential["api_key"],
            "secret": credential["api_secret"],
            "enableRateLimit": True,
            "timeout": 30000,
        }
        if credential.get("passphrase"):
            config["password"] = credential["passphrase"]

        self.exchange = exchange_class(config)
        # 加载市场数据
        self.exchange.load_markets()
        logger.info("crypto_backend_connected", exchange=self._exchange_id)

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> OrderResult:
        if not self.exchange:
            raise RuntimeError("未连接交易所，请先调用 connect()")

        # CCXT 标准化 symbol: "BTC/USDT"
        ccxt_type = "market" if order_type == "market" else "limit"
        ccxt_side = side  # "buy" / "sell"

        try:
            order = self.exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=ccxt_side,
                amount=quantity,
                price=price,
            )

            status = self._map_status(order.get("status", "open"))
            result = OrderResult(
                exchange_order_id=str(order.get("id", "")),
                status=status,
                filled_quantity=float(order.get("filled", 0) or 0),
                filled_price=float(order.get("average", 0) or 0) or None,
                fee=order.get("fee", {}).get("cost"),
                fee_currency=order.get("fee", {}).get("currency"),
                raw=order,
            )

            logger.info(
                "crypto_order_placed",
                exchange=self._exchange_id,
                symbol=symbol,
                side=side,
                order_id=result.exchange_order_id,
                status=result.status,
            )
            return result

        except ccxt.InsufficientFunds as exc:
            return OrderResult(
                exchange_order_id="",
                status=OrderStatus.REJECTED,
                raw={"error": "余额不足", "detail": str(exc)},
            )
        except ccxt.InvalidOrder as exc:
            return OrderResult(
                exchange_order_id="",
                status=OrderStatus.REJECTED,
                raw={"error": "无效订单", "detail": str(exc)},
            )
        except Exception as exc:
            logger.error("crypto_order_failed", symbol=symbol, error=str(exc))
            return OrderResult(
                exchange_order_id="",
                status=OrderStatus.REJECTED,
                raw={"error": str(exc)},
            )

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        if not self.exchange:
            raise RuntimeError("未连接交易所")
        try:
            self.exchange.cancel_order(exchange_order_id, symbol)
            logger.info("crypto_order_cancelled", order_id=exchange_order_id, symbol=symbol)
            return True
        except Exception as exc:
            logger.error("crypto_cancel_failed", order_id=exchange_order_id, error=str(exc))
            return False

    async def get_order_status(self, exchange_order_id: str, symbol: str) -> OrderResult:
        if not self.exchange:
            raise RuntimeError("未连接交易所")
        try:
            order = self.exchange.fetch_order(exchange_order_id, symbol)
            status = self._map_status(order.get("status", "open"))
            return OrderResult(
                exchange_order_id=exchange_order_id,
                status=status,
                filled_quantity=float(order.get("filled", 0) or 0),
                filled_price=float(order.get("average", 0) or 0) or None,
                fee=order.get("fee", {}).get("cost"),
                fee_currency=order.get("fee", {}).get("currency"),
                raw=order,
            )
        except Exception as exc:
            logger.error("crypto_order_status_failed", order_id=exchange_order_id, error=str(exc))
            return OrderResult(exchange_order_id=exchange_order_id, status=OrderStatus.REJECTED, raw={"error": str(exc)})

    async def get_positions(self) -> list[PositionResult]:
        if not self.exchange:
            raise RuntimeError("未连接交易所")
        try:
            balance = self.exchange.fetch_balance()
            positions = []
            for currency, info in balance.get("total", {}).items():
                total = float(info or 0)
                if total > 0:
                    symbol = f"{currency}/USDT"
                    ticker = self._safe_ticker(symbol)
                    positions.append(
                        PositionResult(
                            symbol=symbol,
                            quantity=total,
                            current_price=ticker.get("last") if ticker else None,
                        )
                    )
            return positions
        except Exception as exc:
            logger.error("crypto_positions_failed", error=str(exc))
            return []

    async def get_balance(self) -> dict[str, float]:
        if not self.exchange:
            raise RuntimeError("未连接交易所")
        try:
            balance = self.exchange.fetch_balance()
            result = {}
            for currency, amount in balance.get("free", {}).items():
                val = float(amount or 0)
                if val > 0:
                    result[currency] = val
            return result
        except Exception as exc:
            logger.error("crypto_balance_failed", error=str(exc))
            return {}

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        if not self.exchange:
            raise RuntimeError("未连接交易所")
        try:
            return self.exchange.fetch_ticker(symbol)
        except Exception as exc:
            logger.error("crypto_ticker_failed", symbol=symbol, error=str(exc))
            return {"last": 0}

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _map_status(self, ccxt_status: str) -> str:
        """CCXT 状态 → 内部 OrderStatus"""
        mapping = {
            "open": OrderStatus.SUBMITTED,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "expired": OrderStatus.REJECTED,
        }
        return mapping.get(ccxt_status, OrderStatus.SUBMITTED)

    def _safe_ticker(self, symbol: str) -> dict[str, Any] | None:
        try:
            if self.exchange:
                return self.exchange.fetch_ticker(symbol)
        except Exception:
            pass
        return None
