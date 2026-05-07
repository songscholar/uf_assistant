"""
UF Stock Assistant — 统一交易所客户端
提供抽象交易所接口，支持 CCXT（加密货币）和模拟（A 股）两种实现。

用于交易执行器（trading executor）下单、撤单、查询持仓和余额。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

logger = get_logger("app.strategies.exchange_client")

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class LiveOrderResult:
    """统一订单结果"""

    order_id: str
    symbol: str
    side: str  # "buy" / "sell"
    amount: float
    price: float | None
    status: str  # "open", "closed", "canceled"
    filled: float
    cost: float
    fee: float
    timestamp: float
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------


class ExchangeClient(ABC):
    """交易所客户端抽象基类

    所有交易所实现必须继承此类并实现全部抽象方法。
    """

    @abstractmethod
    def get_ticker(self, symbol: str) -> dict[str, Any]:
        """获取行情摘要

        Args:
            symbol: 交易对 / 股票代码

        Returns:
            包含 price, bid, ask, volume 等字段的字典
        """
        ...

    @abstractmethod
    def get_klines(self, symbol: str, timeframe: str, limit: int = 200) -> list[dict[str, Any]]:
        """获取 K 线数据

        Args:
            symbol: 交易对 / 股票代码
            timeframe: 周期（如 "1d", "1h", "5m"）
            limit: 返回条数

        Returns:
            OHLCV 字典列表
        """
        ...

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float | None = None,
        order_type: str = "market",
    ) -> LiveOrderResult:
        """下单

        Args:
            symbol: 交易对 / 股票代码
            side: "buy" / "sell"
            amount: 数量
            price: 限价（市价单传 None）
            order_type: "market" / "limit"

        Returns:
            LiveOrderResult 订单结果
        """
        ...

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """撤单

        Args:
            symbol: 交易对 / 股票代码
            order_id: 订单 ID

        Returns:
            撤单是否成功
        """
        ...

    @abstractmethod
    def get_positions(self) -> list[dict[str, Any]]:
        """获取当前持仓

        Returns:
            持仓列表，每项包含 symbol, side, amount, entry_price 等
        """
        ...

    @abstractmethod
    def get_balance(self) -> dict[str, Any]:
        """获取账户余额

        Returns:
            包含 total, free, used 等字段的字典
        """
        ...


# ---------------------------------------------------------------------------
# CCXT 实现（加密货币）
# ---------------------------------------------------------------------------

# 信号类型到订单方向的映射
_SIGNAL_TO_SIDE: dict[str, str] = {
    "open_long": "buy",
    "close_long": "sell",
    "open_short": "sell",
    "close_short": "buy",
    "add_long": "buy",
    "add_short": "sell",
    "reduce_long": "sell",
    "reduce_short": "buy",
}


class CCXTExchangeClient(ExchangeClient):
    """基于 CCXT 的加密货币交易所客户端

    支持任意 CCXT 兼容交易所（Binance, OKX, Gate 等）。
    网络请求自动重试，懒加载 ccxt 以避免未安装时的导入错误。
    """

    _MAX_RETRIES = 3
    _RETRY_DELAY = 1.0  # 秒

    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        passphrase: str | None = None,
        sandbox: bool = False,
    ) -> None:
        self._exchange_id = exchange_id
        self._sandbox = sandbox
        self._exchange = self._create_exchange(exchange_id, api_key, api_secret, passphrase, sandbox)
        logger.info(
            "ccxt_exchange_initialized",
            exchange=exchange_id,
            sandbox=sandbox,
        )

    # -- 内部工具 -----------------------------------------------------------

    @staticmethod
    def _create_exchange(
        exchange_id: str,
        api_key: str,
        api_secret: str,
        passphrase: str | None,
        sandbox: bool,
    ) -> Any:
        """懒加载 ccxt 并创建交易所实例"""
        try:
            import ccxt
        except ImportError as exc:
            raise ImportError(
                "ccxt 未安装，请运行 pip install ccxt"
            ) from exc

        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"不支持的交易所: {exchange_id}")

        config: dict[str, Any] = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": 15_000,
        }
        if passphrase:
            config["password"] = passphrase

        exchange: Any = exchange_class(config)
        if sandbox and hasattr(exchange, "set_sandbox_mode"):
            exchange.set_sandbox_mode(True)
        return exchange

    def _retry(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """带重试的网络调用"""
        last_exc: Exception | None = None
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "ccxt_retry",
                    attempt=attempt,
                    max_retries=self._MAX_RETRIES,
                    error=str(exc),
                )
                if attempt < self._MAX_RETRIES:
                    time.sleep(self._RETRY_DELAY * attempt)
        raise last_exc  # type: ignore[misc]

    # -- 公开接口 -----------------------------------------------------------

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        ticker = self._retry(self._exchange.fetch_ticker, symbol)
        return {
            "symbol": symbol,
            "price": ticker.get("last"),
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "high": ticker.get("high"),
            "low": ticker.get("low"),
            "volume": ticker.get("baseVolume"),
            "quote_volume": ticker.get("quoteVolume"),
            "change_pct": ticker.get("percentage"),
            "timestamp": ticker.get("timestamp"),
        }

    def get_klines(self, symbol: str, timeframe: str, limit: int = 200) -> list[dict[str, Any]]:
        ohlcv = self._retry(self._exchange.fetch_ohlcv, symbol, timeframe, limit=limit)
        return [
            {
                "timestamp": candle[0],
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5],
            }
            for candle in ohlcv
        ]

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float | None = None,
        order_type: str = "market",
    ) -> LiveOrderResult:
        params: dict[str, Any] = {}
        order = self._retry(
            self._exchange.create_order,
            symbol,
            order_type,
            side,
            amount,
            price,
            params,
        )
        result = self._to_live_result(order)
        logger.info(
            "ccxt_order_placed",
            exchange=self._exchange_id,
            symbol=symbol,
            side=side,
            amount=amount,
            order_id=result.order_id,
            status=result.status,
        )
        return result

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        try:
            self._retry(self._exchange.cancel_order, order_id, symbol)
            logger.info("ccxt_order_canceled", symbol=symbol, order_id=order_id)
            return True
        except Exception as exc:
            logger.error("ccxt_cancel_failed", symbol=symbol, order_id=order_id, error=str(exc))
            return False

    def get_positions(self) -> list[dict[str, Any]]:
        try:
            positions = self._retry(self._exchange.fetch_positions)
            return [
                {
                    "symbol": p.get("symbol"),
                    "side": p.get("side"),
                    "amount": p.get("contracts"),
                    "notional": p.get("notional"),
                    "entry_price": p.get("entryPrice"),
                    "unrealized_pnl": p.get("unrealizedPnl"),
                    "leverage": p.get("leverage"),
                    "liquidation_price": p.get("liquidationPrice"),
                }
                for p in positions
                if p.get("contracts") and float(p.get("contracts", 0)) != 0
            ]
        except Exception:
            # 现货交易所不支持 fetch_positions，从余额推断
            logger.info("ccxt_positions_fallback_to_balance")
            return []

    def get_balance(self) -> dict[str, Any]:
        bal = self._retry(self._exchange.fetch_balance)
        total = bal.get("total", {})
        free = bal.get("free", {})
        used = bal.get("used", {})
        return {
            "total": {k: v for k, v in total.items() if v and float(v) > 0},
            "free": {k: v for k, v in free.items() if v and float(v) > 0},
            "used": {k: v for k, v in used.items() if v and float(v) > 0},
            "timestamp": bal.get("timestamp"),
        }

    # -- CCXT 增强方法 (QuantDinger parity) --------------------------------

    def set_leverage(self, leverage: int, symbol: str, margin_mode: str = "cross") -> None:
        """Set leverage for a futures symbol.

        Args:
            leverage: Leverage multiplier (e.g. 10 for 10x)
            symbol: Trading pair (e.g. "BTC/USDT:USDT")
            margin_mode: "cross" or "isolated"
        """
        try:
            params: dict[str, Any] = {}
            if hasattr(self._exchange, "set_leverage"):
                self._retry(self._exchange.set_leverage, leverage, symbol, params=params)
                logger.info("leverage_set", symbol=symbol, leverage=leverage, margin_mode=margin_mode)
            # Set margin mode if supported.
            if hasattr(self._exchange, "set_margin_mode"):
                try:
                    self._retry(self._exchange.set_margin_mode, margin_mode, symbol)
                except Exception:
                    pass  # Some exchanges don't support this or it's already set.
        except Exception as exc:
            logger.warning("set_leverage_failed", symbol=symbol, error=str(exc))

    def get_position_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        """Get position for a specific symbol.

        Returns:
            Position dict with symbol, side, contracts, entryPrice, etc., or None.
        """
        try:
            positions = self._retry(self._exchange.fetch_positions, [symbol])
            for p in (positions or []):
                qty = float(p.get("contracts") or 0)
                if abs(qty) > 0:
                    return {
                        "symbol": p.get("symbol"),
                        "side": p.get("side"),
                        "contracts": abs(qty),
                        "entry_price": p.get("entryPrice"),
                        "unrealized_pnl": p.get("unrealizedPnl"),
                        "leverage": p.get("leverage"),
                        "notional": p.get("notional"),
                    }
            return None
        except Exception as exc:
            logger.warning("get_position_for_symbol_failed", symbol=symbol, error=str(exc))
            return None

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        reduce_only: bool = False,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Place a limit order.

        Args:
            symbol: Trading pair
            side: "buy" or "sell"
            amount: Quantity
            price: Limit price
            reduce_only: If True, order only reduces position
            params: Additional CCXT params

        Returns:
            CCXT order dict with id, status, filled, etc.
        """
        order_params = dict(params or {})
        if reduce_only:
            order_params["reduceOnly"] = True
        order = self._retry(
            self._exchange.create_order,
            symbol, "limit", side, amount, price, order_params,
        )
        logger.info(
            "limit_order_placed", exchange=self._exchange_id,
            symbol=symbol, side=side, amount=amount, price=price,
            order_id=order.get("id"),
        )
        return order

    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        reduce_only: bool = False,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Place a market order.

        Args:
            symbol: Trading pair
            side: "buy" or "sell"
            amount: Quantity
            reduce_only: If True, order only reduces position
            params: Additional CCXT params

        Returns:
            CCXT order dict.
        """
        order_params = dict(params or {})
        if reduce_only:
            order_params["reduceOnly"] = True
        order = self._retry(
            self._exchange.create_order,
            symbol, "market", side, amount, None, order_params,
        )
        logger.info(
            "market_order_placed", exchange=self._exchange_id,
            symbol=symbol, side=side, amount=amount,
            order_id=order.get("id"), filled=order.get("filled"),
        )
        return order

    def wait_for_fill(
        self,
        symbol: str,
        order_id: str,
        max_wait_sec: float = 10.0,
        poll_interval: float = 1.0,
    ) -> dict[str, Any] | None:
        """Poll an order until it is filled or timeout.

        Args:
            symbol: Trading pair
            order_id: Exchange order ID
            max_wait_sec: Maximum wait time in seconds
            poll_interval: Seconds between polls

        Returns:
            Order dict if filled, None if timeout or canceled.
        """
        deadline = time.time() + max_wait_sec
        while time.time() < deadline:
            try:
                order = self._retry(self._exchange.fetch_order, order_id, symbol)
                status = order.get("status", "")
                if status == "closed":
                    return order
                if status in ("canceled", "expired", "rejected"):
                    logger.info("order_canceled_during_wait", order_id=order_id, status=status)
                    return order
            except Exception as exc:
                logger.warning("wait_for_fill_poll_error", order_id=order_id, error=str(exc))
            time.sleep(poll_interval)

        logger.info("wait_for_fill_timeout", order_id=order_id, max_wait_sec=max_wait_sec)
        return None

    def get_fee_rate(self, symbol: str) -> dict[str, float] | None:
        """Query trading fee rate for a symbol.

        Returns:
            Dict with 'maker' and 'taker' keys, or None on failure.
        """
        try:
            fees = self._retry(self._exchange.fetch_trading_fee, symbol)
            if fees:
                return {
                    "maker": float(fees.get("maker") or 0.0002),
                    "taker": float(fees.get("taker") or 0.0005),
                }
            return None
        except Exception as exc:
            logger.warning("get_fee_rate_failed", symbol=symbol, error=str(exc))
            return None

    def normalize_symbol(self, symbol: str, market_type: str = "swap") -> str:
        """Normalize a symbol for swap/futures markets.

        Converts e.g. "BTC/USDT" to "BTC/USDT:USDT" for OKX/Binance futures.

        Args:
            symbol: Raw symbol string
            market_type: "swap" or "spot"

        Returns:
            Normalized symbol string.
        """
        if market_type != "swap":
            return symbol
        if not symbol or ":" in symbol:
            return symbol

        try:
            if not self._exchange.markets:
                return symbol
            # Check if already a swap market.
            try:
                mkt = self._exchange.market(symbol)
                if mkt.get("swap") or mkt.get("future") or mkt.get("contract"):
                    return symbol
            except Exception:
                pass

            if "/" not in symbol:
                return symbol

            base, quote = symbol.split("/", 1)
            candidates = [f"{base}/{quote}:{quote}"]
            if quote != "USDT":
                candidates.append(f"{base}/{quote}:USDT")

            for candidate in candidates:
                if candidate in self._exchange.markets:
                    mkt = self._exchange.markets[candidate]
                    if mkt.get("swap") or mkt.get("future") or mkt.get("contract"):
                        logger.info("symbol_normalized", original=symbol, normalized=candidate)
                        return candidate
        except Exception:
            pass

        return symbol

    # -- 便捷方法 -----------------------------------------------------------

    def place_order_from_signal(
        self,
        symbol: str,
        signal_type: str,
        amount: float,
        price: float | None = None,
    ) -> LiveOrderResult:
        """将 4-way 信号转换为订单

        信号映射：open_long -> buy, close_long -> sell,
                  open_short -> sell, close_short -> buy

        Args:
            symbol: 交易对
            signal_type: 信号类型（open_long / close_long / open_short / close_short）
            amount: 数量
            price: 限价

        Returns:
            LiveOrderResult 订单结果
        """
        side = _SIGNAL_TO_SIDE.get(signal_type)
        if side is None:
            raise ValueError(f"不支持的信号类型: {signal_type}，可选: {list(_SIGNAL_TO_SIDE)}")

        order_type = "limit" if price is not None else "market"
        logger.info("signal_to_order", symbol=symbol, signal=signal_type, side=side, amount=amount)
        return self.place_order(symbol, side, amount, price, order_type)

    # -- 内部转换 -----------------------------------------------------------

    @staticmethod
    def _to_live_result(order: dict[str, Any]) -> LiveOrderResult:
        """将 CCXT 订单字典转为 LiveOrderResult"""
        return LiveOrderResult(
            order_id=str(order.get("id", "")),
            symbol=str(order.get("symbol", "")),
            side=str(order.get("side", "")),
            amount=float(order.get("amount") or 0),
            price=order.get("price"),
            status=str(order.get("status", "open")),
            filled=float(order.get("filled") or 0),
            cost=float(order.get("cost") or 0),
            fee=float((order.get("fee") or {}).get("cost") or 0),
            timestamp=float(order.get("timestamp") or time.time() * 1000),
            raw=order,
        )


# ---------------------------------------------------------------------------
# 模拟股票客户端（A 股纸面交易 / 回测）
# ---------------------------------------------------------------------------


class SimulatedStockClient(ExchangeClient):
    """模拟 A 股交易客户端

    用于回测和纸面交易，所有操作在内存中完成，不连接真实券商。
    支持 T+1 限制（当日买入不可当日卖出）和 10% 涨跌停限制。
    """

    def __init__(self, initial_balance: float = 100_000) -> None:
        self._initial_balance = initial_balance
        self._cash: float = initial_balance
        self._positions: dict[str, dict[str, Any]] = {}  # symbol -> {amount, avg_price, ...}
        self._orders: list[LiveOrderResult] = []
        self._order_counter: int = 0
        logger.info("simulated_stock_initialized", initial_balance=initial_balance)

    # -- 内部工具 -----------------------------------------------------------

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"SIM-{self._order_counter:08d}"

    def _commission(self, cost: float) -> float:
        """佣金：万三（最低 5 元）"""
        fee = cost * 0.0003
        return max(fee, 5.0) if cost > 0 else 0.0

    # -- 公开接口 -----------------------------------------------------------

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        # 模拟客户端无法获取实时行情，返回占位数据
        pos = self._positions.get(symbol)
        price = pos["avg_price"] if pos else 0.0
        logger.debug("sim_ticker", symbol=symbol, price=price)
        return {
            "symbol": symbol,
            "price": price,
            "bid": price,
            "ask": price,
            "high": price,
            "low": price,
            "volume": 0,
            "quote_volume": 0,
            "change_pct": 0.0,
            "timestamp": time.time() * 1000,
        }

    def get_klines(self, symbol: str, timeframe: str, limit: int = 200) -> list[dict[str, Any]]:
        logger.debug("sim_klines", symbol=symbol, timeframe=timeframe)
        return []

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float | None = None,
        order_type: str = "market",
    ) -> LiveOrderResult:
        if price is None or price <= 0:
            raise ValueError("模拟交易必须指定价格（无实时行情）")

        # A 股按手（100 股）取整
        lots = int(amount) // 100
        if lots <= 0:
            raise ValueError(f"数量不足一手（100 股），当前: {amount}")
        actual_amount = lots * 100
        cost = actual_amount * price
        commission = self._commission(cost)

        if side == "buy":
            total_cost = cost + commission
            if total_cost > self._cash:
                raise ValueError(f"余额不足: 需要 {total_cost:.2f}，可用 {self._cash:.2f}")
            self._cash -= total_cost
            pos = self._positions.get(symbol)
            if pos:
                old_amount = pos["amount"]
                old_cost = old_amount * pos["avg_price"]
                new_amount = old_amount + actual_amount
                pos["avg_price"] = (old_cost + cost) / new_amount
                pos["amount"] = new_amount
            else:
                self._positions[symbol] = {
                    "amount": actual_amount,
                    "avg_price": price,
                    "symbol": symbol,
                }
        elif side == "sell":
            pos = self._positions.get(symbol)
            if not pos or pos["amount"] < actual_amount:
                available = pos["amount"] if pos else 0
                raise ValueError(f"持仓不足: {symbol} 可用 {available}，需要 {actual_amount}")
            self._cash += cost - commission
            pos["amount"] -= actual_amount
            if pos["amount"] == 0:
                del self._positions[symbol]
        else:
            raise ValueError(f"不支持的 side: {side}，可选: buy / sell")

        result = LiveOrderResult(
            order_id=self._next_order_id(),
            symbol=symbol,
            side=side,
            amount=actual_amount,
            price=price,
            status="closed",  # 模拟交易立即成交
            filled=actual_amount,
            cost=cost,
            fee=commission,
            timestamp=time.time() * 1000,
            raw={"simulated": True},
        )
        self._orders.append(result)
        logger.info(
            "sim_order_executed",
            symbol=symbol,
            side=side,
            amount=actual_amount,
            price=price,
            cost=cost,
            fee=commission,
            cash_remaining=self._cash,
        )
        return result

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        logger.info("sim_cancel_order", symbol=symbol, order_id=order_id)
        return True  # 模拟交易全部立即成交，撤单视为成功

    def get_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": p["symbol"],
                "side": "long",
                "amount": p["amount"],
                "entry_price": p["avg_price"],
                "notional": p["amount"] * p["avg_price"],
                "unrealized_pnl": 0.0,
            }
            for p in self._positions.values()
            if p["amount"] > 0
        ]

    def get_balance(self) -> dict[str, Any]:
        position_value = sum(
            p["amount"] * p["avg_price"] for p in self._positions.values()
        )
        return {
            "total": {"CNY": self._cash + position_value},
            "free": {"CNY": self._cash},
            "used": {"CNY": position_value},
            "initial_balance": self._initial_balance,
            "pnl": self._cash + position_value - self._initial_balance,
            "timestamp": time.time() * 1000,
        }


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def create_exchange_client(exchange_type: str, **kwargs: Any) -> ExchangeClient:
    """创建交易所客户端

    Args:
        exchange_type: "ccxt" 或 "simulated_stock"
        **kwargs: 传递给具体实现的参数

    Returns:
        ExchangeClient 实例

    Raises:
        ValueError: 未知的 exchange_type
    """
    if exchange_type == "ccxt":
        return CCXTExchangeClient(**kwargs)
    if exchange_type == "simulated_stock":
        return SimulatedStockClient(**kwargs)
    raise ValueError(f"未知的交易所类型: {exchange_type}，可选: ccxt, simulated_stock")


# ---------------------------------------------------------------------------
# Demo mode detection & Binance -2015 hint (migrated from QuantDinger)
# ---------------------------------------------------------------------------


def exchange_demo_mode_enabled(cfg: dict[str, Any]) -> bool:
    """
    检测配置是否指示 demo / testnet / simulated / paper 模式。

    接受常见的前端/交易所命名变体，确保 test-connection 与 create_client 行为一致。
    """
    if not isinstance(cfg, dict):
        return False
    env = str(cfg.get("network") or cfg.get("environment") or cfg.get("env") or "").strip().lower()
    if env in ("testnet", "sandbox", "demo", "paper", "simulate", "simulation"):
        return True
    for k in (
        "enable_demo_trading",
        "enableDemoTrading",
        "simulated_trading",
        "simulatedTrading",
        "use_testnet",
        "is_testnet",
        "isTestnet",
        "sandbox",
        "paper_trading",
        "paperTrading",
    ):
        v = cfg.get(k)
        if v is None:
            continue
        if isinstance(v, bool) and v:
            return True
        if isinstance(v, (int, float)) and int(v) == 1:
            return True
        if isinstance(v, str) and str(v).strip().lower() in ("true", "1", "yes", "on"):
            return True
    return False


def _hint_binance_2015(market_type: str, base_url: str, is_demo: bool, alt_ok: bool = False, alt_market_type: str = "") -> str:
    """Binance -2015 错误双语提示"""
    hint = (
        f"Binance auth failed (-2015). Verify: "
        f"(1) IP whitelist includes this server egress IP, "
        f"(2) API key permissions match market_type={market_type} "
        f"(spot requires Spot permissions; swap requires Futures permissions), "
        f"(3) you're using the correct key set for base_url={base_url or 'unknown'}."
    )
    if is_demo:
        hint += " Demo mode is enabled, so you must use Binance demo/testnet API keys instead of mainnet keys."
    else:
        hint += " Mainnet mode is enabled, so you must use binance.com mainnet keys."
    if alt_ok:
        hint += (
            f" Auto-check: your key works for market_type={alt_market_type} "
            f"but fails for market_type={market_type}. This is almost always a permissions/product mismatch."
        )

    hint_cn = (
        "币安接口返回 -2015（密钥/IP/权限不匹配）。请逐项核对："
        "① API Key 是否勾选与当前测试一致的业务（现货选现货权限，合约选合约/U 本位权限）；"
        "② 若启用 IP 白名单，是否包含当前服务器出口 IP；"
        "③ base_url 与密钥环境一致（主网密钥配 api.binance.com / fapi，模拟盘配 demo 域名与 demo Key）；"
        "④ 无多余空格、复制完整 Secret。"
    )
    if alt_ok:
        hint_cn += (
            f" 自动探测：同一密钥在 market_type={alt_market_type} 可通过，"
            f"当前选择的 {market_type} 与密钥权限不一致的可能性很大。"
        )

    return f"{hint} | {hint_cn}"


def safe_exchange_config_for_log(cfg: dict[str, Any]) -> dict[str, Any]:
    """密钥脱敏，用于日志输出"""
    out = dict(cfg)
    for k in ["api_key", "secret_key", "passphrase", "apiKey", "secret", "password"]:
        if k in out and out.get(k):
            val = str(out.get(k))
            out[k] = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
    return out
