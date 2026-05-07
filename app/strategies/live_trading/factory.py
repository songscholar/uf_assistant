"""
Factory for direct exchange clients.

Supports:
- Crypto exchanges: Binance, OKX, Bitget, Bybit, Coinbase, Kraken, KuCoin, Gate, Deepcoin, HTX
- Traditional brokers: Interactive Brokers (IBKR) for US stocks
- Forex brokers: MetaTrader 5 (MT5)

All imports of exchange-specific clients are lazy (inside create_client) to avoid
ImportError when dependencies are not installed. The modules themselves are imported
at the top so type checkers / linters can see them.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

from .base import BaseRestClient, LiveTradingError

# Lazy import IBKR to avoid ImportError if ib_insync not installed
IBKRClient = None
IBKRConfig = None

# Lazy import MT5 to avoid ImportError if MetaTrader5 not installed
MT5Client = None
MT5Config = None


def _get(cfg: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = cfg.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


# Merged from HTTP JSON root into nested `exchange_config` for /strategies/test-connection
# when the UI sends demo/testnet toggles next to the nested object.
EXCHANGE_CONFIG_ROOT_OVERLAY_KEYS = (
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
    "network",
    "environment",
    "env",
    "base_url",
    "baseUrl",
    "futures_base_url",
    "futuresBaseUrl",
)


def merge_root_exchange_config_overlay(*, root: dict[str, Any], exchange_config: dict[str, Any]) -> dict[str, Any]:
    """Overlay selected keys from the request root onto exchange_config (copying the latter)."""
    out = dict(exchange_config or {})
    if not isinstance(root, dict):
        return out
    for k in EXCHANGE_CONFIG_ROOT_OVERLAY_KEYS:
        if k in root:
            out[k] = root[k]
    return out


def exchange_demo_mode_enabled(cfg: dict[str, Any]) -> bool:
    """
    Whether config indicates demo / testnet / simulated / paper mode for live-trading clients.

    Accepts common frontend / exchange naming variants so test-connection matches create_client.
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


def _demo_enabled(cfg: dict[str, Any]) -> bool:
    return exchange_demo_mode_enabled(cfg)


def create_client(exchange_config: dict[str, Any], *, market_type: str = "swap") -> BaseRestClient:
    """
    Create a native exchange client from config.

    Returns a subclass of BaseRestClient ready for live trading.
    Raises LiveTradingError if the exchange is unsupported or config is invalid.
    """
    if not isinstance(exchange_config, dict):
        raise LiveTradingError("Invalid exchange_config")

    exchange_id = _get(exchange_config, "exchange_id", "exchangeId").lower()
    api_key = _get(exchange_config, "api_key", "apiKey")
    secret_key = _get(exchange_config, "secret_key", "secret")
    passphrase = _get(exchange_config, "passphrase", "password")

    mt = (market_type or exchange_config.get("market_type") or exchange_config.get("defaultType") or "swap").strip().lower()
    if mt in ("futures", "future", "perp", "perpetual"):
        mt = "swap"

    is_demo = _demo_enabled(exchange_config)

    # ------------------------------------------------------------------
    # Binance (spot + USDT-M futures)
    # ------------------------------------------------------------------
    if exchange_id == "binance":
        spot_broker_id = _get(exchange_config, "spot_broker_id", "spotBrokerId", "broker_id", "brokerId") or "A2NAPZAC"
        futures_broker_id = _get(exchange_config, "futures_broker_id", "futuresBrokerId", "broker_id", "brokerId") or "HBpUbQjT"
        if mt == "spot":
            default_url = "https://demo-api.binance.com" if is_demo else "https://api.binance.com"
            base_url = _get(exchange_config, "base_url", "baseUrl") or default_url
            from .binance_spot import BinanceSpotClient
            return BinanceSpotClient(
                api_key=api_key,
                secret_key=secret_key,
                base_url=base_url,
                enable_demo_trading=is_demo,
                broker_id=spot_broker_id,
            )
        # Default to USDT-M futures
        default_url = "https://demo-fapi.binance.com" if is_demo else "https://fapi.binance.com"
        base_url = _get(exchange_config, "base_url", "baseUrl") or default_url
        from .binance import BinanceFuturesClient
        return BinanceFuturesClient(
            api_key=api_key,
            secret_key=secret_key,
            base_url=base_url,
            enable_demo_trading=is_demo,
            broker_id=futures_broker_id,
        )

    # ------------------------------------------------------------------
    # OKX
    # ------------------------------------------------------------------
    if exchange_id == "okx":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://www.okx.com"
        broker_code = "56fa80b0ce8cBCDE"
        from .okx import OkxClient
        return OkxClient(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            base_url=base_url,
            broker_code=broker_code,
            simulated_trading=is_demo,
        )

    # ------------------------------------------------------------------
    # Bitget (spot + USDT futures)
    # ------------------------------------------------------------------
    if exchange_id == "bitget":
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.bitget.com"
        channel_api_code = _get(exchange_config, "channel_api_code", "channelApiCode") or "qvz9x"
        if mt == "spot":
            from .bitget_spot import BitgetSpotClient
            return BitgetSpotClient(
                api_key=api_key,
                secret_key=secret_key,
                passphrase=passphrase,
                base_url=base_url,
                channel_api_code=channel_api_code,
                simulated_trading=is_demo,
            )
        from .bitget import BitgetMixClient
        return BitgetMixClient(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            base_url=base_url,
            channel_api_code=channel_api_code,
            simulated_trading=is_demo,
        )

    # ------------------------------------------------------------------
    # Bybit
    # ------------------------------------------------------------------
    if exchange_id == "bybit":
        default_bybit = "https://api-testnet.bybit.com" if is_demo else "https://api.bybit.com"
        base_url = _get(exchange_config, "base_url", "baseUrl") or default_bybit
        category = "spot" if mt == "spot" else "linear"
        recv_window_ms = int(exchange_config.get("recv_window_ms") or exchange_config.get("recvWindow") or 12000)
        broker_referer = _get(exchange_config, "bybit_referer", "broker_referer", "brokerReferer") or "Ri001020"
        hedge_mode_raw = exchange_config.get("hedge_mode")
        if hedge_mode_raw is None:
            hedge_mode_raw = exchange_config.get("hedgeMode")
        if hedge_mode_raw is None:
            hedge_mode_raw = exchange_config.get("position_mode") or exchange_config.get("positionMode")
        hedge_mode = False
        if isinstance(hedge_mode_raw, bool):
            hedge_mode = hedge_mode_raw
        else:
            hedge_mode = str(hedge_mode_raw or "").strip().lower() in ("true", "1", "yes", "hedge", "both_side")
        from .bybit import BybitClient
        return BybitClient(
            api_key=api_key,
            secret_key=secret_key,
            base_url=base_url,
            category=category,
            recv_window_ms=recv_window_ms,
            broker_referer=broker_referer,
            hedge_mode=hedge_mode,
        )

    # ------------------------------------------------------------------
    # Coinbase Exchange
    # ------------------------------------------------------------------
    if exchange_id in ("coinbaseexchange", "coinbase_exchange"):
        default_cb = "https://api-public.sandbox.exchange.coinbase.com" if is_demo else "https://api.exchange.coinbase.com"
        base_url = _get(exchange_config, "base_url", "baseUrl") or default_cb
        if mt != "spot":
            raise LiveTradingError("CoinbaseExchange only supports spot market_type in this project")
        from .coinbase_exchange import CoinbaseExchangeClient
        return CoinbaseExchangeClient(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            base_url=base_url,
        )

    # ------------------------------------------------------------------
    # Kraken (spot + futures)
    # ------------------------------------------------------------------
    if exchange_id == "kraken":
        if mt == "spot":
            base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.kraken.com"
            from .kraken import KrakenClient
            return KrakenClient(
                api_key=api_key,
                secret_key=secret_key,
                base_url=base_url,
            )
        fut_default = "https://demo-futures.kraken.com" if is_demo else "https://futures.kraken.com"
        fut_url = _get(exchange_config, "futures_base_url", "futuresBaseUrl") or fut_default
        from .kraken_futures import KrakenFuturesClient
        return KrakenFuturesClient(
            api_key=api_key,
            secret_key=secret_key,
            base_url=fut_url,
        )

    # ------------------------------------------------------------------
    # KuCoin (spot + futures)
    # ------------------------------------------------------------------
    if exchange_id == "kucoin":
        if mt == "spot":
            default_spot = "https://openapi-sandbox.kucoin.com" if is_demo else "https://api.kucoin.com"
            base_url = _get(exchange_config, "base_url", "baseUrl") or default_spot
            from .kucoin import KucoinSpotClient
            return KucoinSpotClient(
                api_key=api_key,
                secret_key=secret_key,
                passphrase=passphrase,
                base_url=base_url,
            )
        fut_default = "https://api-sandbox-futures.kucoin.com" if is_demo else "https://api-futures.kucoin.com"
        fut_url = _get(exchange_config, "futures_base_url", "futuresBaseUrl") or fut_default
        from .kucoin import KucoinFuturesClient
        return KucoinFuturesClient(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            base_url=fut_url,
        )

    # ------------------------------------------------------------------
    # Gate (spot + USDT futures)
    # ------------------------------------------------------------------
    if exchange_id == "gate":
        gate_channel_id = _get(exchange_config, "gate_channel_id", "gateChannelId") or "dinger"
        if mt == "spot":
            default_gate = "https://api-testnet.gateio.ws" if is_demo else "https://api.gateio.ws"
            base_url = _get(exchange_config, "base_url", "baseUrl") or default_gate
            from .gate import GateSpotClient
            return GateSpotClient(
                api_key=api_key,
                secret_key=secret_key,
                base_url=base_url,
                channel_id=gate_channel_id,
            )
        default_fut = "https://fx-api-testnet.gateio.ws" if is_demo else "https://fx-api.gateio.ws"
        base_url = _get(exchange_config, "base_url", "baseUrl") or default_fut
        from .gate import GateUsdtFuturesClient
        return GateUsdtFuturesClient(
            api_key=api_key,
            secret_key=secret_key,
            base_url=base_url,
            channel_id=gate_channel_id,
        )

    # ------------------------------------------------------------------
    # Deepcoin
    # ------------------------------------------------------------------
    if exchange_id == "deepcoin":
        if is_demo and not (_get(exchange_config, "base_url", "baseUrl")):
            raise LiveTradingError(
                "Deepcoin demo/testnet is not configured in this project yet. "
                "Please disable demo mode or provide an explicit testnet base_url."
            )
        base_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.deepcoin.com"
        from .deepcoin import DeepcoinClient
        return DeepcoinClient(
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            base_url=base_url,
            market_type=mt,
        )

    # ------------------------------------------------------------------
    # HTX
    # ------------------------------------------------------------------
    if exchange_id == "htx":
        if is_demo and not (
            _get(exchange_config, "base_url", "baseUrl") or _get(exchange_config, "futures_base_url", "futuresBaseUrl")
        ):
            raise LiveTradingError(
                "HTX demo/testnet is not configured in this project yet. "
                "Please disable demo mode or provide explicit testnet base_url/futures_base_url."
            )
        spot_url = _get(exchange_config, "base_url", "baseUrl") or "https://api.htx.com"
        futures_url = _get(exchange_config, "futures_base_url", "futuresBaseUrl") or "https://api.hbdm.com"
        broker_id = _get(exchange_config, "broker_id", "brokerId") or "AA7b890547"
        from .htx import HtxClient
        return HtxClient(
            api_key=api_key,
            secret_key=secret_key,
            base_url=spot_url,
            futures_base_url=futures_url,
            market_type=mt,
            broker_id=broker_id,
        )

    # ------------------------------------------------------------------
    # IBKR (US stocks)
    # ------------------------------------------------------------------
    if exchange_id == "ibkr":
        return create_ibkr_client(exchange_config)

    # ------------------------------------------------------------------
    # MT5 (Forex only)
    # ------------------------------------------------------------------
    if exchange_id == "mt5":
        return create_mt5_client(exchange_config)

    raise LiveTradingError(f"Unsupported exchange_id: {exchange_id}")


def create_ibkr_client(exchange_config: dict[str, Any]) -> Any:
    """
    Create IBKR client for US stock trading.

    exchange_config should contain:
    - ibkr_host: TWS/Gateway host (default: 127.0.0.1)
    - ibkr_port: TWS/Gateway port (default: 7497)
    - ibkr_client_id: Client ID (default: 1)
    - ibkr_account: Account ID (optional, auto-select if empty)
    """
    global IBKRClient, IBKRConfig

    if IBKRClient is None or IBKRConfig is None:
        try:
            from app.services.ibkr_trading import IBKRClient as _IBKRClient, IBKRConfig as _IBKRConfig
            IBKRClient = _IBKRClient
            IBKRConfig = _IBKRConfig
        except ImportError:
            raise LiveTradingError("IBKR trading requires ib_insync. Run: pip install ib_insync")

    host = str(exchange_config.get("ibkr_host") or "127.0.0.1").strip()
    port = int(exchange_config.get("ibkr_port") or 7497)
    client_id = int(exchange_config.get("ibkr_client_id") or 1)
    account = str(exchange_config.get("ibkr_account") or "").strip()

    config = IBKRConfig(
        host=host,
        port=port,
        client_id=client_id,
        account=account,
        readonly=False,
    )
    client = IBKRClient(config)
    if not client.connect():
        raise LiveTradingError("Failed to connect to IBKR TWS/Gateway. Please check if it's running.")
    return client


def create_mt5_client(exchange_config: dict[str, Any]) -> Any:
    """
    Create MT5 client for forex trading.

    exchange_config should contain:
    - mt5_login: MT5 account number
    - mt5_password: MT5 password
    - mt5_server: Broker server name (e.g., "ICMarkets-Demo")
    - mt5_terminal_path: Optional path to terminal64.exe
    """
    global MT5Client, MT5Config

    market_category = str(exchange_config.get("market_category") or "").strip()
    if market_category and market_category != "Forex":
        raise LiveTradingError(
            f"MT5 can only be used for Forex trading, but market_category is '{market_category}'. "
            f"MT5 does not support Crypto or Stock trading."
        )

    if MT5Client is None or MT5Config is None:
        try:
            from app.services.mt5_trading import MT5Client as _MT5Client, MT5Config as _MT5Config
            MT5Client = _MT5Client
            MT5Config = _MT5Config
        except ImportError:
            raise LiveTradingError(
                "MT5 trading requires MetaTrader5 library. Run: pip install MetaTrader5\n"
                "Note: This library only works on Windows."
            )

    login_raw = exchange_config.get("mt5_login") or 0
    try:
        login = int(login_raw) if login_raw else 0
    except (ValueError, TypeError):
        try:
            login = int(str(login_raw).strip())
        except (ValueError, TypeError):
            login = 0

    password = str(exchange_config.get("mt5_password") or "").strip()
    server = str(exchange_config.get("mt5_server") or "").strip()
    terminal_path = str(exchange_config.get("mt5_terminal_path") or "").strip()

    if not login or not password or not server:
        raise LiveTradingError("MT5 requires login, password, and server")

    config = MT5Config(
        login=login,
        password=password,
        server=server,
        terminal_path=terminal_path,
    )
    client = MT5Client(config)
    if not client.connect():
        raise LiveTradingError(
            "Failed to connect to MT5 terminal. Please check:\n"
            "1. MT5 terminal is running\n"
            "2. Credentials are correct\n"
            "3. You are on Windows"
        )
    return client


def query_fee_rate(
    exchange_config: dict[str, Any],
    symbol: str,
    market_type: str = "swap",
) -> dict[str, float] | None:
    """
    Best-effort: create a temporary client and query the account's fee tier
    for the given symbol.  Returns {"maker": 0.0002, "taker": 0.0005} or None.
    """
    try:
        client = create_client(exchange_config, market_type=market_type)
        return client.get_fee_rate(symbol, market_type=market_type)
    except Exception as exc:
        logger.debug(f"query_fee_rate failed for {symbol}: {exc}")
        return None
