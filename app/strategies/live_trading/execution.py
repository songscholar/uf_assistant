"""
Signal-to-order execution dispatcher.

Translates strategy signals into exchange-specific order calls.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from .base import BaseRestClient, LiveTradingError

logger = get_logger("app.strategies.live_trading.execution")


def _signal_to_sides(signal_type: str) -> tuple[str, str, bool]:
    """
    Map 8-way signal to (side, pos_side, reduce_only).

    Returns:
        (side: str, pos_side: str, reduce_only: bool)
    """
    mapping = {
        "open_long": ("buy", "long", False),
        "add_long": ("buy", "long", False),
        "close_long": ("sell", "long", True),
        "reduce_long": ("sell", "long", True),
        "open_short": ("sell", "short", False),
        "add_short": ("sell", "short", False),
        "close_short": ("buy", "short", True),
        "reduce_short": ("buy", "short", True),
    }
    return mapping.get(signal_type, ("buy", "long", False))


def _normalize_symbol_for_order(symbol: str) -> str:
    """
    Normalize symbol for order placement.
    Handles bare symbols (e.g. 'PI', 'TRX') by appending '/USDT'.
    Strips ':USDT' suffixes.
    """
    if not symbol:
        return ""
    s = str(symbol).strip().upper()
    if ":" in s:
        s = s.split(":")[0]
    if "/" not in s and "_" not in s and "-" not in s:
        # Bare symbol → assume USDT pair
        s = f"{s}/USDT"
    return s


def place_order_from_signal(
    client: BaseRestClient,
    signal_type: str,
    symbol: str,
    amount: float,
    market_type: str = "swap",
    exchange_config: dict[str, Any] | None = None,
    client_order_id: str = "",
) -> dict[str, Any]:
    """
    Place an order based on a strategy signal.

    Args:
        client: Exchange client (subclass of BaseRestClient)
        signal_type: open_long, close_long, open_short, close_short, add_*, reduce_*
        symbol: Trading pair symbol
        amount: Order amount (base currency quantity)
        market_type: spot / swap / futures
        exchange_config: Additional exchange-specific config
        client_order_id: Optional client order ID

    Returns:
        {"success": bool, "order_id": str, "filled": float, "avg_price": float, "raw": dict}
    """
    exchange_config = exchange_config or {}
    side, pos_side, reduce_only = _signal_to_sides(signal_type)
    symbol = _normalize_symbol_for_order(symbol)

    # Import exchange-specific clients for isinstance checks
    # (lazy to avoid circular imports)
    try:
        from .binance import BinanceFuturesClient
        from .binance_spot import BinanceSpotClient
        from .bitget import BitgetMixClient
        from .bitget_spot import BitgetSpotClient
        from .bybit import BybitClient
        from .coinbase_exchange import CoinbaseExchangeClient
        from .deepcoin import DeepcoinClient
        from .gate import GateSpotClient, GateUsdtFuturesClient
        from .htx import HtxClient
        from .kraken import KrakenClient
        from .kraken_futures import KrakenFuturesClient
        from .kucoin import KucoinFuturesClient, KucoinSpotClient
        from .okx import OkxClient
    except ImportError:
        # Stage 3 exchange modules may not exist yet
        BinanceFuturesClient = BinanceSpotClient = BitgetMixClient = BitgetSpotClient = None
        BybitClient = CoinbaseExchangeClient = DeepcoinClient = None
        GateSpotClient = GateUsdtFuturesClient = HtxClient = None
        KrakenClient = KrakenFuturesClient = KucoinFuturesClient = KucoinSpotClient = None
        OkxClient = None

    result: dict[str, Any] = {"success": False, "order_id": "", "filled": 0.0, "avg_price": 0.0, "raw": {}}

    try:
        # ------------------------------------------------------------------
        # Binance Futures
        # ------------------------------------------------------------------
        if BinanceFuturesClient and isinstance(client, BinanceFuturesClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
                position_side=pos_side,
                reduce_only=reduce_only,
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Binance Spot
        # ------------------------------------------------------------------
        elif BinanceSpotClient and isinstance(client, BinanceSpotClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # OKX
        # ------------------------------------------------------------------
        elif OkxClient and isinstance(client, OkxClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
                pos_side=pos_side,
                reduce_only=reduce_only,
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Bitget Mix (USDT futures)
        # ------------------------------------------------------------------
        elif BitgetMixClient and isinstance(client, BitgetMixClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
                reduce_only=reduce_only,
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Bitget Spot
        # ------------------------------------------------------------------
        elif BitgetSpotClient and isinstance(client, BitgetSpotClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Bybit
        # ------------------------------------------------------------------
        elif BybitClient and isinstance(client, BybitClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
                pos_side=pos_side,
                reduce_only=reduce_only,
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Coinbase Exchange
        # ------------------------------------------------------------------
        elif CoinbaseExchangeClient and isinstance(client, CoinbaseExchangeClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Kraken Spot
        # ------------------------------------------------------------------
        elif KrakenClient and isinstance(client, KrakenClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Kraken Futures
        # ------------------------------------------------------------------
        elif KrakenFuturesClient and isinstance(client, KrakenFuturesClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
                reduce_only=reduce_only,
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # KuCoin Spot
        # ------------------------------------------------------------------
        elif KucoinSpotClient and isinstance(client, KucoinSpotClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # KuCoin Futures
        # ------------------------------------------------------------------
        elif KucoinFuturesClient and isinstance(client, KucoinFuturesClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
                reduce_only=reduce_only,
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Gate Spot
        # ------------------------------------------------------------------
        elif GateSpotClient and isinstance(client, GateSpotClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Gate USDT Futures
        # ------------------------------------------------------------------
        elif GateUsdtFuturesClient and isinstance(client, GateUsdtFuturesClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
                reduce_only=reduce_only,
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # Deepcoin
        # ------------------------------------------------------------------
        elif DeepcoinClient and isinstance(client, DeepcoinClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
                reduce_only=reduce_only,
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # HTX
        # ------------------------------------------------------------------
        elif HtxClient and isinstance(client, HtxClient):
            res = client.place_market_order(
                symbol=symbol,
                side=side,
                amount=float(amount),
                reduce_only=reduce_only,
            )
            result = {"success": True, "order_id": res.exchange_order_id, "filled": res.filled, "avg_price": res.avg_price, "raw": res.raw}

        # ------------------------------------------------------------------
        # IBKR / MT5 / Unknown
        # ------------------------------------------------------------------
        else:
            logger.warning("Unknown client type for order placement", client_type=type(client).__name__)
            result = {"success": False, "error": f"Unsupported client type: {type(client).__name__}"}

    except Exception as exc:
        logger.error("place_order_failed", signal=signal_type, symbol=symbol, error=str(exc))
        result = {"success": False, "error": str(exc)}

    return result
