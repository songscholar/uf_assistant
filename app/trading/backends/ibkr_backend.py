"""
UF Stock Assistant — Interactive Brokers (IBKR) Trading Backend

基于 ib_insync 连接 TWS/IB Gateway，支持美股交易。

迁移自 QuantDinger app/services/ibkr_trading/client.py，适配：
- Flask → FastAPI (async)
- Singleton IBKRClient → ExchangeBackend 实例
- 同步 ib_insync API → async 包装
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger
from app.trading.backends import ExchangeBackend, OrderResult, PositionResult

logger = get_logger("app.trading.backends.ibkr")


# Lazy import ib_insync to avoid ImportError when not installed
_ib_insync = None


def _ensure_ib_insync():
    """Lazy import ib_insync."""
    global _ib_insync
    if _ib_insync is None:
        try:
            import ib_insync as _ib
            _ib_insync = _ib
        except ImportError as exc:
            raise ImportError(
                "ib_insync is not installed. Run: pip install ib_insync"
            ) from exc
    return _ib_insync


def _ensure_event_loop():
    """Ensure an asyncio event loop exists in the current thread."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def _normalize_symbol(symbol: str, market_type: str = "USStock") -> tuple[str, str, str]:
    """Convert system symbol to IB contract parameters."""
    symbol = (symbol or "").strip().upper()
    if market_type == "USStock":
        return symbol, "SMART", "USD"
    return symbol, "SMART", "USD"


class IBKRBackend(ExchangeBackend):
    """Interactive Brokers TWS/Gateway backend for US stocks."""

    def __init__(self) -> None:
        self._ib = None
        self._account = ""
        self._config: dict[str, Any] = {}

    async def connect(self, credential: dict[str, Any]) -> None:
        """Connect to TWS/IB Gateway."""
        extra = credential.get("extra_config") or {}
        self._config = {
            "host": extra.get("ibkr_host", "127.0.0.1"),
            "port": int(extra.get("ibkr_port", 7497)),
            "client_id": int(extra.get("ibkr_client_id", 1)),
            "readonly": extra.get("ibkr_readonly", False),
            "timeout": float(extra.get("ibkr_timeout", 20.0)),
        }

        _ensure_event_loop()
        ib = _ensure_ib_insync()

        if self._ib is None:
            self._ib = ib.IB()

        def _do_connect():
            self._ib.connect(
                host=self._config["host"],
                port=self._config["port"],
                clientId=self._config["client_id"],
                readonly=self._config["readonly"],
                timeout=self._config["timeout"],
            )

        await asyncio.to_thread(_do_connect)

        accounts = await asyncio.to_thread(lambda: self._ib.managedAccounts())
        if accounts:
            self._account = accounts[0]
            logger.info("ibkr_connected", account=self._account)
        else:
            logger.warning("ibkr_connected_no_account")

    def _create_contract(self, symbol: str, market_type: str = "USStock"):
        ib = _ensure_ib_insync()
        ib_symbol, exchange, currency = _normalize_symbol(symbol, market_type)
        return ib.Stock(symbol=ib_symbol, exchange=exchange, currency=currency)

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> OrderResult:
        """Place a market or limit order."""
        ib = _ensure_ib_insync()
        contract = self._create_contract(symbol)

        def _qualify():
            qualified = self._ib.qualifyContracts(contract)
            return len(qualified) > 0

        ok = await asyncio.to_thread(_qualify)
        if not ok:
            raise ValueError(f"Invalid contract: {symbol}")

        action = "BUY" if side.lower() == "buy" else "SELL"

        if order_type.lower() == "market":
            order = ib.MarketOrder(action=action, totalQuantity=quantity, account=self._account)
        elif order_type.lower() == "limit":
            if price is None:
                raise ValueError("Limit order requires price")
            order = ib.LimitOrder(action=action, totalQuantity=quantity, lmtPrice=price, account=self._account)
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

        def _place():
            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(2)
            return trade

        trade = await asyncio.to_thread(_place)
        status = trade.orderStatus.status
        rejected = status in ("Cancelled", "ApiCancelled", "Inactive")

        return OrderResult(
            exchange_order_id=str(trade.order.orderId),
            status="rejected" if rejected else "filled" if status == "Filled" else "submitted",
            filled_quantity=float(trade.orderStatus.filled or 0),
            filled_price=float(trade.orderStatus.avgFillPrice or 0) if trade.orderStatus.avgFillPrice else None,
            raw={
                "orderId": trade.order.orderId,
                "status": status,
                "remaining": float(trade.orderStatus.remaining or 0),
            },
        )

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        """Cancel an order by ID."""
        oid = int(exchange_order_id)

        def _cancel():
            for trade in self._ib.openTrades():
                if trade.order.orderId == oid:
                    self._ib.cancelOrder(trade.order)
                    return True
            return False

        return await asyncio.to_thread(_cancel)

    async def get_order_status(self, exchange_order_id: str, symbol: str) -> OrderResult:
        """Query order status."""
        oid = int(exchange_order_id)

        def _query():
            for trade in self._ib.openTrades():
                if trade.order.orderId == oid:
                    return trade
            return None

        trade = await asyncio.to_thread(_query)
        if trade is None:
            return OrderResult(exchange_order_id=exchange_order_id, status="unknown")

        status = trade.orderStatus.status
        return OrderResult(
            exchange_order_id=str(trade.order.orderId),
            status="filled" if status == "Filled" else "submitted",
            filled_quantity=float(trade.orderStatus.filled or 0),
            filled_price=float(trade.orderStatus.avgFillPrice or 0) if trade.orderStatus.avgFillPrice else None,
        )

    async def get_positions(self) -> list[PositionResult]:
        """Get current positions."""
        def _query():
            return self._ib.positions(self._account)

        positions = await asyncio.to_thread(_query)
        results: list[PositionResult] = []
        for pos in positions:
            results.append(
                PositionResult(
                    symbol=str(pos.contract.symbol),
                    quantity=float(pos.position),
                    avg_cost=float(pos.avgCost) if hasattr(pos, "avgCost") else None,
                )
            )
        return results

    async def get_balance(self) -> dict[str, float]:
        """Get account balance."""
        def _query():
            summary = self._ib.accountSummary(self._account)
            result: dict[str, float] = {}
            for item in summary:
                if item.tag in ("AvailableFunds", "NetLiquidation", "BuyingPower"):
                    try:
                        result[item.tag] = float(item.value)
                    except (ValueError, TypeError):
                        pass
            return result

        return await asyncio.to_thread(_query)

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get latest quote."""
        contract = self._create_contract(symbol)

        def _query():
            qualified = self._ib.qualifyContracts(contract)
            if not qualified:
                return {}
            ticker = self._ib.reqMktData(contract, "", False, False)
            self._ib.sleep(1)
            return {
                "last": float(ticker.last) if ticker.last else None,
                "bid": float(ticker.bid) if ticker.bid else None,
                "ask": float(ticker.ask) if ticker.ask else None,
                "volume": float(ticker.volume) if ticker.volume else None,
            }

        return await asyncio.to_thread(_query)
