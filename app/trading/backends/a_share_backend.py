"""
UF Stock Assistant — A股交易后端
东方财富模拟盘 / 同花顺 Mini / 未来扩展真实券商
"""

from __future__ import annotations

from typing import Any

from app.core.constants import OrderStatus
from app.core.logging import get_logger

from . import ExchangeBackend, OrderResult, PositionResult

logger = get_logger("app.trading.a_share_backend")


class AShareBackend(ExchangeBackend):
    """A股交易后端

    当前实现：东方财富模拟盘（免费，无需真实资金）
    未来可扩展：同花顺 Mini、真实券商接口

    A股特性：
    - 必须限价单（T+1 交易制度）
    - 最小单位 100 股（1 手）
    - 涨跌停限制
    """

    def __init__(self) -> None:
        self._connected = False
        self._session_id: str | None = None
        self._broker: str = "eastmoney"

    async def connect(self, credential: dict[str, Any]) -> None:
        """连接 A股 交易接口

        credential.extra_config 包含:
            - broker: "eastmoney" | "ths"
            - account_id: 资金账号（模拟盘可留空）
        """
        extra = credential.get("extra_config", {})
        self._broker = extra.get("broker", "eastmoney")

        if self._broker == "eastmoney":
            # 东方财富模拟盘 — 无需真实凭证
            self._session_id = "em_simulated"
            self._connected = True
            logger.info("a_share_connected", broker="eastmoney", mode="simulated")
        else:
            raise NotImplementedError(f"暂不支持 A股 券商: {self._broker}，请使用 eastmoney 模拟盘")

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> OrderResult:
        if not self._connected:
            raise RuntimeError("未连接，请先调用 connect()")

        # A股 必须限价单
        if order_type == "market":
            logger.warning("a_share_market_order_converted_to_limit", symbol=symbol)
            order_type = "limit"

        if price is None:
            return OrderResult(
                exchange_order_id="",
                status=OrderStatus.REJECTED,
                raw={"error": "A股必须指定价格（限价单）"},
            )

        # 检查最小单位（100 股）
        if quantity % 100 != 0:
            return OrderResult(
                exchange_order_id="",
                status=OrderStatus.REJECTED,
                raw={"error": "A股最小交易单位为 100 股"},
            )

        # 模拟盘：立即成交
        import uuid
        order_id = str(uuid.uuid4())
        logger.info(
            "a_share_order_placed",
            broker=self._broker,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_id=order_id,
        )

        return OrderResult(
            exchange_order_id=order_id,
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            filled_price=price,
            fee=round(price * quantity * 0.0003, 2),  # 万三佣金
            fee_currency="CNY",
            raw={"broker": self._broker, "simulated": True},
        )

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        logger.info("a_share_order_cancelled", order_id=exchange_order_id)
        return True

    async def get_order_status(self, exchange_order_id: str, symbol: str) -> OrderResult:
        return OrderResult(
            exchange_order_id=exchange_order_id,
            status=OrderStatus.FILLED,
            raw={"broker": self._broker},
        )

    async def get_positions(self) -> list[PositionResult]:
        # 模拟盘：返回空持仓
        return []

    async def get_balance(self) -> dict[str, float]:
        return {"CNY": 1_000_000}  # 模拟盘默认 100 万

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        # 复用现有东财实时行情
        try:
            from app.tools.eastmoney_api import get_stock_realtime
            data = get_stock_realtime(symbol)
            return {"last": data.get("price", 0)}
        except Exception:
            return {"last": 0}
