"""
UF Stock Assistant — 交易所后端抽象基类
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.constants import OrderStatus, OrderSide


@dataclass
class OrderResult:
    """交易所返回的订单结果"""
    exchange_order_id: str
    status: str
    filled_quantity: float = 0
    filled_price: float | None = None
    fee: float | None = None
    fee_currency: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class PositionResult:
    """持仓快照"""
    symbol: str
    quantity: float
    avg_cost: float | None = None
    current_price: float | None = None
    unrealized_pnl: float | None = None


class ExchangeBackend(ABC):
    """交易所后端抽象接口

    所有市场（加密货币、A股、美股）的交易后端都实现此接口。
    """

    @abstractmethod
    async def connect(self, credential: dict[str, Any]) -> None:
        """使用凭证连接交易所

        Args:
            credential: 解密后的凭证字典，包含 api_key, api_secret, passphrase, extra_config
        """

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> OrderResult:
        """下单

        Args:
            symbol: 交易对/股票代码
            side: "buy" 或 "sell"
            order_type: "market", "limit", "stop", "stop_limit"
            quantity: 数量
            price: 价格（限价单必填）

        Returns:
            OrderResult 包含交易所订单ID和状态
        """

    @abstractmethod
    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        """取消订单

        Returns:
            True if cancelled successfully
        """

    @abstractmethod
    async def get_order_status(self, exchange_order_id: str, symbol: str) -> OrderResult:
        """查询订单状态"""

    @abstractmethod
    async def get_positions(self) -> list[PositionResult]:
        """获取所有持仓"""

    @abstractmethod
    async def get_balance(self) -> dict[str, float]:
        """获取账户余额

        Returns:
            {currency: available_amount, ...}
        """

    @abstractmethod
    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """获取最新行情

        Returns:
            至少包含 {last, bid, ask, ...}
        """


class BackendRouter:
    """根据 market_type 返回对应后端实例"""

    @staticmethod
    def create(market_type: str) -> ExchangeBackend:
        """创建指定市场的交易后端实例"""
        mt = (market_type or "").lower().strip()

        if mt in ("crypto", "cryptocurrency"):
            from app.trading.backends.crypto_backend import CryptoBackend
            return CryptoBackend()
        elif mt in ("a_share", "ashare", "cn", "china"):
            from app.trading.backends.a_share_backend import AShareBackend
            return AShareBackend()
        elif mt in ("us_stock", "usstock", "us", "america"):
            from app.trading.backends.us_stock_backend import USStockBackend
            return USStockBackend()
        elif mt == "ibkr":
            if not settings.local_broker.allowed:
                raise RuntimeError("Local desktop brokers (IBKR) are not allowed in this deployment.")
            from app.trading.backends.ibkr_backend import IBKRBackend
            return IBKRBackend()
        else:
            raise ValueError(f"Unsupported market_type: {market_type}")

    @staticmethod
    def supported_markets() -> list[str]:
        """返回支持的市场类型列表"""
        base = ["crypto", "a_share", "us_stock"]
        if settings.local_broker.allowed:
            base.append("ibkr")
        return base
