"""
UF Stock Assistant — MetaTrader 5 (MT5) Trading Backend

基于 MetaTrader5 Python 库连接 MT5 终端，支持外汇/贵金属/指数/加密货币。

迁移自 QuantDinger app/services/mt5_trading/client.py，适配：
- Flask → FastAPI (async)
- Singleton MT5Client → ExchangeBackend 实例
- 同步 MetaTrader5 API → async 包装

注意：MetaTrader5 库仅支持 Windows，且需要安装 MT5 终端。
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger
from app.trading.backends import ExchangeBackend, OrderResult, PositionResult

logger = get_logger("app.trading.backends.mt5")


# Lazy import MetaTrader5 to avoid ImportError when not installed
_mt5 = None


def _ensure_mt5():
    """Lazy import MetaTrader5."""
    global _mt5
    if _mt5 is None:
        try:
            import MetaTrader5 as _mt5_module
            _mt5 = _mt5_module
        except ImportError as exc:
            raise ImportError(
                "MetaTrader5 is not installed. Run: pip install MetaTrader5\n"
                "Note: This library only works on Windows with MT5 terminal installed."
            ) from exc
    return _mt5


def _normalize_symbol(symbol: str) -> str:
    """Normalize symbol to MT5 format: uppercase, remove separators."""
    normalized = (symbol or "").strip().upper()
    normalized = normalized.replace("/", "").replace("-", "").replace("_", "").replace(" ", "")
    return normalized


def _round_volume(volume: float, volume_step: float) -> float:
    """Round volume to symbol's lot step."""
    if volume_step > 0:
        return round(volume / volume_step) * volume_step
    return volume


class MT5Backend(ExchangeBackend):
    """MetaTrader 5 terminal backend for Forex, Metals, Indices, and Crypto."""

    def __init__(self) -> None:
        self._connected = False
        self._config: dict[str, Any] = {}

    async def connect(self, credential: dict[str, Any]) -> None:
        """Connect to MT5 terminal."""
        extra = credential.get("extra_config") or {}
        self._config = {
            "login": int(extra.get("mt5_login", 0)),
            "password": extra.get("mt5_password", ""),
            "server": extra.get("mt5_server", ""),
            "terminal_path": extra.get("mt5_terminal_path", ""),
            "timeout": int(extra.get("mt5_timeout", 60000)),
            "magic_number": int(extra.get("mt5_magic_number", 123456)),
        }

        mt5 = _ensure_mt5()

        def _do_connect():
            init_params: dict[str, Any] = {}
            if self._config["terminal_path"]:
                init_params["path"] = self._config["terminal_path"]
            if self._config["login"] and self._config["password"] and self._config["server"]:
                init_params["login"] = self._config["login"]
                init_params["password"] = self._config["password"]
                init_params["server"] = self._config["server"]
                init_params["timeout"] = self._config["timeout"]

            if init_params:
                initialized = mt5.initialize(**init_params)
            else:
                initialized = mt5.initialize()

            if not initialized:
                error = mt5.last_error()
                raise ConnectionError(f"MT5 initialization failed: {error}")

            self._connected = True
            account_info = mt5.account_info()
            if account_info:
                logger.info(
                    "mt5_connected",
                    login=account_info.login,
                    server=account_info.server,
                    balance=account_info.balance,
                )
            else:
                logger.warning("mt5_connected_no_account_info")

        await asyncio.to_thread(_do_connect)

    def _ensure_connected(self):
        if not self._connected:
            raise ConnectionError("Not connected to MT5 terminal")

    def _select_symbol(self, symbol: str):
        mt5 = _ensure_mt5()
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            raise ValueError(f"Symbol not found: {symbol}")
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                raise ValueError(f"Failed to select symbol: {symbol}")
        return symbol_info

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> OrderResult:
        """Place a market or limit order."""
        mt5 = _ensure_mt5()
        self._ensure_connected()
        symbol = _normalize_symbol(symbol)

        def _place():
            symbol_info = self._select_symbol(symbol)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise ValueError(f"Failed to get tick for: {symbol}")

            volume_float = _round_volume(float(quantity), symbol_info.volume_step)
            if volume_float < symbol_info.volume_min:
                raise ValueError(f"Volume {volume_float} below minimum {symbol_info.volume_min}")
            if volume_float > symbol_info.volume_max:
                raise ValueError(f"Volume {volume_float} exceeds maximum {symbol_info.volume_max}")

            is_buy = side.lower() == "buy"

            if order_type.lower() == "market":
                order_mt5_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
                action = mt5.TRADE_ACTION_DEAL
                exec_price = tick.ask if is_buy else tick.bid
            elif order_type.lower() == "limit":
                if price is None:
                    raise ValueError("Limit order requires price")
                exec_price = float(price)
                if is_buy:
                    order_mt5_type = mt5.ORDER_TYPE_BUY_LIMIT if exec_price < tick.ask else mt5.ORDER_TYPE_BUY_STOP
                else:
                    order_mt5_type = mt5.ORDER_TYPE_SELL_LIMIT if exec_price > tick.bid else mt5.ORDER_TYPE_SELL_STOP
                action = mt5.TRADE_ACTION_PENDING
            else:
                raise ValueError(f"Unsupported order type: {order_type}")

            # Determine filling mode
            filling_mode = mt5.ORDER_FILLING_IOC
            if symbol_info.filling_mode & mt5.ORDER_FILLING_IOC:
                filling_mode = mt5.ORDER_FILLING_IOC
            elif symbol_info.filling_mode & mt5.ORDER_FILLING_FOK:
                filling_mode = mt5.ORDER_FILLING_FOK
            elif symbol_info.filling_mode & mt5.ORDER_FILLING_RETURN:
                filling_mode = mt5.ORDER_FILLING_RETURN

            request = {
                "action": action,
                "symbol": symbol,
                "volume": volume_float,
                "type": order_mt5_type,
                "price": exec_price,
                "deviation": 20,
                "magic": self._config.get("magic_number", 123456),
                "comment": "UF-Assistant",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }

            result = mt5.order_send(request)
            if result is None:
                error = mt5.last_error()
                raise RuntimeError(f"Order send failed: {error}")

            raw = result._asdict() if hasattr(result, "_asdict") else {}
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return OrderResult(
                    exchange_order_id=str(result.order) if hasattr(result, "order") else "0",
                    status="rejected",
                    raw={"retcode": result.retcode, "comment": result.comment, **raw},
                )

            return OrderResult(
                exchange_order_id=str(result.order),
                status="filled" if order_type.lower() == "market" else "submitted",
                filled_quantity=float(result.volume),
                filled_price=float(result.price),
                raw=raw,
            )

        return await asyncio.to_thread(_place)

    async def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        """Cancel a pending order by ticket."""
        mt5 = _ensure_mt5()
        self._ensure_connected()
        ticket = int(exchange_order_id)

        def _cancel():
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": ticket,
            }
            result = mt5.order_send(request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.warning("mt5_cancel_failed", ticket=ticket, comment=getattr(result, "comment", "unknown"))
                return False
            logger.info("mt5_cancelled", ticket=ticket)
            return True

        return await asyncio.to_thread(_cancel)

    async def get_order_status(self, exchange_order_id: str, symbol: str) -> OrderResult:
        """Query order status."""
        mt5 = _ensure_mt5()
        self._ensure_connected()
        ticket = int(exchange_order_id)

        def _query():
            orders = mt5.orders_get(ticket=ticket)
            if orders:
                order = orders[0]
                return OrderResult(
                    exchange_order_id=str(order.ticket),
                    status="submitted",
                    raw={"type": order.type, "volume_current": order.volume_current},
                )
            # Check if it became a deal/position
            history = mt5.history_deals_get(ticket=ticket)
            if history:
                deal = history[0]
                return OrderResult(
                    exchange_order_id=str(ticket),
                    status="filled",
                    filled_quantity=float(deal.volume),
                    filled_price=float(deal.price),
                    raw={"deal_ticket": deal.ticket},
                )
            return OrderResult(exchange_order_id=str(ticket), status="unknown")

        return await asyncio.to_thread(_query)

    async def get_positions(self) -> list[PositionResult]:
        """Get all open positions."""
        mt5 = _ensure_mt5()
        self._ensure_connected()

        def _query():
            positions = mt5.positions_get()
            if positions is None:
                return []
            results: list[PositionResult] = []
            for pos in positions:
                results.append(
                    PositionResult(
                        symbol=str(pos.symbol),
                        quantity=float(pos.volume) * (1 if pos.type == mt5.POSITION_TYPE_BUY else -1),
                        avg_cost=float(pos.price_open),
                    )
                )
            return results

        return await asyncio.to_thread(_query)

    async def get_balance(self) -> dict[str, float]:
        """Get account balance."""
        mt5 = _ensure_mt5()
        self._ensure_connected()

        def _query():
            info = mt5.account_info()
            if info is None:
                return {}
            return {
                "balance": float(info.balance),
                "equity": float(info.equity),
                "margin": float(info.margin),
                "margin_free": float(info.margin_free),
                "margin_level": float(info.margin_level) if info.margin_level else 0.0,
                "profit": float(info.profit),
            }

        return await asyncio.to_thread(_query)

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get latest quote."""
        mt5 = _ensure_mt5()
        self._ensure_connected()
        symbol = _normalize_symbol(symbol)

        def _query():
            self._select_symbol(symbol)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return {}
            return {
                "last": float(tick.last) if tick.last else None,
                "bid": float(tick.bid) if tick.bid else None,
                "ask": float(tick.ask) if tick.ask else None,
                "volume": float(tick.volume) if tick.volume else None,
                "time": tick.time,
            }

        return await asyncio.to_thread(_query)
