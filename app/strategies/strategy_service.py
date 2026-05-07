"""
UF Stock Assistant — Strategy Service Layer

High-level CRUD and batch operations for strategies.
移植自 QuantDinger，适配 SQLAlchemy + SQLite
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.strategies.models import StrategyModel, StrategyPosition, StrategyTrade
from app.strategies.trading_executor import get_strategy_db_session, get_trading_executor

logger = get_logger("app.strategies.strategy_service")


def create_strategy(payload: dict[str, Any]) -> str:
    """Create a new strategy. Returns the strategy ID."""
    session = get_strategy_db_session()
    try:
        strategy = StrategyModel(
            strategy_name=payload.get("strategy_name", "Untitled"),
            strategy_type=payload.get("strategy_type", "indicator"),
            status="stopped",
            symbol=payload.get("symbol", ""),
            timeframe=payload.get("timeframe", "1D"),
            strategy_code=payload.get("strategy_code", ""),
            indicator_config=payload.get("indicator_config"),
            trading_config=payload.get("trading_config"),
            initial_capital=float(payload.get("initial_capital", 100000.0)),
            leverage=int(payload.get("leverage", 1)),
            market_type=payload.get("market_type", "stock"),
            trade_direction=payload.get("trade_direction", "long"),
            commission=float(payload.get("commission", 0.001)),
            slippage=float(payload.get("slippage", 0.0)),
            execution_mode=payload.get("execution_mode", "signal"),
            market_category=payload.get("market_category", "Crypto"),
            strategy_mode=payload.get("strategy_mode", "signal"),
            notification_config=payload.get("notification_config"),
            ai_model_config=payload.get("ai_model_config"),
            strategy_group_id=payload.get("strategy_group_id", ""),
            group_base_name=payload.get("group_base_name", ""),
        )
        session.add(strategy)
        session.commit()
        strategy_id = str(strategy.id)
        logger.info("strategy_created", strategy_id=strategy_id, name=strategy.strategy_name)
        return strategy_id
    except Exception as exc:
        session.rollback()
        logger.error("create_strategy_failed", error=str(exc))
        raise
    finally:
        session.close()


def batch_create_strategies(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Batch create strategies (multi-symbol)

    Returns:
        {
            'success': True/False,
            'strategy_group_id': '...',
            'created_ids': ['id1', 'id2'],
            'failed_symbols': []
        }
    """
    symbols = payload.get("symbols") or []
    if not symbols or not isinstance(symbols, list):
        raise ValueError("symbols array is required")

    base_name = (payload.get("strategy_name") or "").strip()
    if not base_name:
        raise ValueError("strategy_name is required")

    market_category = payload.get("market_category") or "Crypto"
    exchange_config = payload.get("exchange_config") or {}

    from app.strategies.exchange_execution import resolve_exchange_config

    uid = str(payload.get("user_id") or "default")
    _resolved = resolve_exchange_config(exchange_config if isinstance(exchange_config, dict) else {}, user_id=uid)
    exchange_id = (_resolved.get("exchange_id") or "").strip().lower() if isinstance(_resolved, dict) else ""

    # Validate exchange-market compatibility
    if exchange_id == "mt5" and market_category != "Forex":
        raise ValueError(
            f"MT5 can only be used for Forex trading, but market_category is '{market_category}'. "
            f"MT5 does not support Crypto or Stock trading."
        )
    if exchange_id == "ibkr" and market_category != "USStock":
        raise ValueError(
            f"IBKR can only be used for US stock trading, but market_category is '{market_category}'."
        )

    # Generate strategy group ID
    strategy_group_id = str(uuid.uuid4())[:8]

    created_ids = []
    failed_symbols = []

    for symbol in symbols:
        try:
            single_payload = dict(payload)

            # Parse symbol (may be "Market:SYMBOL" format)
            if isinstance(symbol, str) and ":" in symbol:
                parts = symbol.split(":", 1)
                market_category = parts[0]
                symbol_name = parts[1]
            else:
                market_category = payload.get("market_category") or "Crypto"
                symbol_name = symbol

            single_payload["strategy_name"] = f"{base_name}-{symbol_name}"
            single_payload["strategy_group_id"] = strategy_group_id
            single_payload["group_base_name"] = base_name
            single_payload["market_category"] = market_category

            # Update symbol in trading_config
            trading_config = dict(single_payload.get("trading_config") or {})
            trading_config["symbol"] = symbol_name
            single_payload["trading_config"] = trading_config

            new_id = create_strategy(single_payload)
            created_ids.append(new_id)

        except Exception as exc:
            logger.error(f"Failed to create strategy for symbol {symbol}: {exc}")
            failed_symbols.append({"symbol": symbol, "error": str(exc)})

    return {
        "success": len(created_ids) > 0,
        "strategy_group_id": strategy_group_id,
        "group_base_name": base_name,
        "created_ids": created_ids,
        "failed_symbols": failed_symbols,
        "total_created": len(created_ids),
        "total_failed": len(failed_symbols),
    }


def get_exchange_symbols(exchange_config: dict[str, Any], user_id: str = "default") -> dict[str, Any]:
    """
    Get exchange trading pairs (no API Key required for public endpoints)
    """
    try:
        from app.strategies.exchange_execution import resolve_exchange_config

        resolved = resolve_exchange_config(exchange_config or {}, user_id=str(user_id or "default"))
        exchange_id = (resolved.get("exchange_id") or exchange_config.get("exchange_id") or "")
        proxies = resolved.get("proxies") or exchange_config.get("proxies")

        if not str(exchange_id).strip():
            return {"success": False, "message": "Please select an exchange", "symbols": []}

        ex = str(exchange_id or "").strip().lower()

        # IBKR / MT5 are not CCXT exchanges
        if ex in ("ibkr", "mt5"):
            from app.utils.local_brokers import desktop_broker_cloud_reject_message, local_desktop_brokers_allowed

            if not local_desktop_brokers_allowed():
                return {"success": False, "message": desktop_broker_cloud_reject_message(), "symbols": []}

            if ex == "ibkr":
                common = [
                    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "NFLX", "INTC",
                    "SPY", "QQQ", "IWM", "DIA", "VOO", "BABA", "JD", "PDD", "COIN", "MSTR",
                ]
                return {
                    "success": True,
                    "message": "IBKR: 以下为常用美股代码示例，也可手动输入其他在 TWS 中可交易的代码。",
                    "symbols": common,
                }

            if ex == "mt5":
                try:
                    from app.strategies.live_trading.factory import create_mt5_client

                    mt5_client = create_mt5_client(resolved)
                    if mt5_client and mt5_client.connected:
                        infos = mt5_client.get_symbols(group="*") or []
                        names = []
                        for info in infos:
                            if isinstance(info, dict):
                                n = str(info.get("name") or "").strip()
                                if n:
                                    names.append(n)
                        names = sorted(set(names))[:2000]
                        return {
                            "success": True,
                            "message": f"MT5: {len(names)} symbols from terminal",
                            "symbols": names,
                        }
                    return {
                        "success": False,
                        "message": "MT5 未连接：请确认本机已启动 MT5 终端且账号配置正确。",
                        "symbols": [],
                    }
                except Exception as exc:
                    logger.error(f"MT5 get_symbols failed: {exc}")
                    return {
                        "success": False,
                        "message": f"MT5 品种列表失败: {exc}",
                        "symbols": [],
                    }

        # For these exchanges, prefer direct REST (no ccxt)
        if ex in ("bybit", "coinbaseexchange", "coinbase_exchange", "kraken", "kucoin", "gate"):
            import requests

            def _req_json(url: str) -> Any:
                r = requests.get(url, timeout=15, proxies=proxies)
                r.raise_for_status()
                return r.json()

            symbols = []
            market_type = str(exchange_config.get("market_type") or exchange_config.get("defaultType") or "spot").strip().lower()
            if market_type in ("futures", "future", "perp", "perpetual"):
                market_type = "swap"

            if ex == "bybit":
                base = str(exchange_config.get("base_url") or exchange_config.get("baseUrl") or "https://api.bybit.com").rstrip("/")
                cat = "spot" if market_type == "spot" else "linear"
                j = _req_json(f"{base}/v5/market/instruments-info?category={cat}")
                lst = (((j.get("result") or {}).get("list")) if isinstance(j, dict) else None) or []
                if isinstance(lst, list):
                    for it in lst:
                        if not isinstance(it, dict):
                            continue
                        sym = str(it.get("symbol") or "")
                        status = str(it.get("status") or "").lower()
                        if not sym or (status and status not in ("trading", "tradable", "online")):
                            continue
                        if sym.endswith("USDT") and len(sym) > 4:
                            symbols.append(f"{sym[:-4]}/USDT")
                symbols = sorted(list(set(symbols)))
                return {"success": True, "message": f"Success, {len(symbols)} trading pairs", "symbols": symbols}

            if ex in ("coinbaseexchange", "coinbase_exchange"):
                base = str(exchange_config.get("base_url") or exchange_config.get("baseUrl") or "https://api.exchange.coinbase.com").rstrip("/")
                j = _req_json(f"{base}/products")
                if isinstance(j, list):
                    for it in j:
                        if not isinstance(it, dict):
                            continue
                        if str(it.get("status") or "").lower() not in ("online", ""):
                            continue
                        base_ccy = str(it.get("base_currency") or "").upper()
                        quote_ccy = str(it.get("quote_currency") or "").upper()
                        if quote_ccy == "USDT" and base_ccy:
                            symbols.append(f"{base_ccy}/USDT")
                symbols = sorted(list(set(symbols)))
                return {"success": True, "message": f"Success, {len(symbols)} trading pairs", "symbols": symbols}

            if ex == "kraken":
                if market_type == "spot":
                    j = _req_json("https://api.kraken.com/0/public/AssetPairs")
                    res = (j.get("result") if isinstance(j, dict) else None) or {}
                    if isinstance(res, dict):
                        for _k, v in res.items():
                            if not isinstance(v, dict):
                                continue
                            wsname = str(v.get("wsname") or "")
                            if not wsname or "/" not in wsname:
                                continue
                            base_ccy, quote_ccy = wsname.split("/", 1)
                            if str(quote_ccy).upper() == "USDT":
                                symbols.append(f"{str(base_ccy).upper()}/USDT")
                else:
                    base = str(exchange_config.get("futures_base_url") or exchange_config.get("futuresBaseUrl") or "https://futures.kraken.com").rstrip("/")
                    j = _req_json(f"{base}/derivatives/api/v3/instruments")
                    instruments = j.get("instruments") if isinstance(j, dict) else None
                    if isinstance(instruments, list):
                        for it in instruments:
                            if not isinstance(it, dict):
                                continue
                            sym = str(it.get("symbol") or "")
                            typ = str(it.get("type") or "").lower()
                            if sym and ("perpetual" in typ or typ.startswith("pf") or sym.startswith("PF_")):
                                symbols.append(sym)
                symbols = sorted(list(set(symbols)))
                return {"success": True, "message": f"Success, {len(symbols)} trading pairs", "symbols": symbols}

            if ex == "kucoin":
                if market_type == "spot":
                    base = str(exchange_config.get("base_url") or exchange_config.get("baseUrl") or "https://api.kucoin.com").rstrip("/")
                    j = _req_json(f"{base}/api/v1/symbols")
                    data = (j.get("data") if isinstance(j, dict) else None) or []
                    if isinstance(data, list):
                        for it in data:
                            if not isinstance(it, dict):
                                continue
                            if not bool(it.get("enableTrading", True)):
                                continue
                            if str(it.get("quoteCurrency") or "").upper() != "USDT":
                                continue
                            b = str(it.get("baseCurrency") or "").upper()
                            if b:
                                symbols.append(f"{b}/USDT")
                else:
                    base = str(exchange_config.get("futures_base_url") or exchange_config.get("futuresBaseUrl") or "https://api-futures.kucoin.com").rstrip("/")
                    j = _req_json(f"{base}/api/v1/contracts/active")
                    data = (j.get("data") if isinstance(j, dict) else None) or []
                    if isinstance(data, list):
                        for it in data:
                            if not isinstance(it, dict):
                                continue
                            sym = str(it.get("symbol") or "")
                            if not sym or not sym.upper().endswith("USDTM"):
                                continue
                            base_ccy = sym[:-5].upper()
                            if base_ccy == "XBT":
                                base_ccy = "BTC"
                            if base_ccy:
                                symbols.append(f"{base_ccy}/USDT")
                symbols = sorted(list(set(symbols)))
                return {"success": True, "message": f"Success, {len(symbols)} trading pairs", "symbols": symbols}

            if ex == "gate":
                base = str(exchange_config.get("base_url") or exchange_config.get("baseUrl") or "https://api.gateio.ws").rstrip("/")
                if market_type == "spot":
                    j = _req_json(f"{base}/api/v4/spot/currency_pairs")
                    if isinstance(j, list):
                        for it in j:
                            if not isinstance(it, dict):
                                continue
                            if str(it.get("trade_status") or "").lower() not in ("tradable", "trading", ""):
                                continue
                            base_ccy = str(it.get("base") or "").upper()
                            quote_ccy = str(it.get("quote") or "").upper()
                            if quote_ccy == "USDT" and base_ccy:
                                symbols.append(f"{base_ccy}/USDT")
                else:
                    j = _req_json(f"{base}/api/v4/futures/usdt/contracts")
                    if isinstance(j, list):
                        for it in j:
                            if not isinstance(it, dict):
                                continue
                            name = str(it.get("name") or it.get("contract") or "")
                            if name and name.upper().endswith("_USDT"):
                                symbols.append(name.replace("_", "/"))
                symbols = sorted(list(set(symbols)))
                return {"success": True, "message": f"Success, {len(symbols)} trading pairs", "symbols": symbols}

        # Fallback to CCXT
        import ccxt

        exchange_class = getattr(ccxt, exchange_id, None)
        if not exchange_class:
            return {"success": False, "message": f"Unsupported exchange: {exchange_id}", "symbols": []}

        exchange_config_dict = {
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if proxies:
            exchange_config_dict["proxies"] = proxies

        exchange = exchange_class(exchange_config_dict)
        markets = exchange.load_markets()

        symbols = []
        for symbol, market in markets.items():
            if market.get("active", False) and market.get("quote") == "USDT":
                symbols.append(symbol)

        symbols.sort()
        return {"success": True, "message": f"Success, {len(symbols)} trading pairs", "symbols": symbols}

    except Exception as exc:
        logger.error(f"Failed to fetch symbols: {exc}")
        return {"success": False, "message": f"Failed to get trading pairs: {exc}", "symbols": []}


def _compute_runtime_metrics(strategy_ids: list[str]) -> dict[str, dict[str, float]]:
    """批量计算策略的已实现盈亏 / 未实现盈亏 / 当前权益。"""
    result: dict[str, dict[str, float]] = {}
    if not strategy_ids:
        return result
    try:
        session = get_strategy_db_session()
        try:
            # Realized PnL from trades
            rows = (
                session.query(
                    StrategyTrade.strategy_id,
                    session.query.func.coalesce(
                        session.query.func.sum(
                            session.query.func.coalesce(StrategyTrade.profit, 0)
                            - session.query.func.coalesce(StrategyTrade.commission, 0)
                        ),
                        0,
                    ).label("realized_pnl"),
                )
                .filter(StrategyTrade.strategy_id.in_(strategy_ids))
                .group_by(StrategyTrade.strategy_id)
                .all()
            )
            # SQLite doesn't support coalesce in func.sum directly the same way,
            # so use a simpler approach
            for sid in strategy_ids:
                result.setdefault(sid, {"realized_pnl": 0.0, "unrealized_pnl": 0.0})

            for row in rows:
                sid = str(row[0])
                result.setdefault(sid, {"realized_pnl": 0.0, "unrealized_pnl": 0.0})
                result[sid]["realized_pnl"] = float(row[1] or 0.0)

            # Unrealized PnL from positions
            pos_rows = (
                session.query(
                    StrategyPosition.strategy_id,
                    session.query.func.coalesce(
                        session.query.func.sum(session.query.func.coalesce(StrategyPosition.unrealized_pnl, 0)),
                        0,
                    ).label("unrealized_pnl"),
                )
                .filter(StrategyPosition.strategy_id.in_(strategy_ids))
                .group_by(StrategyPosition.strategy_id)
                .all()
            )
            for row in pos_rows:
                sid = str(row[0])
                result.setdefault(sid, {"realized_pnl": 0.0, "unrealized_pnl": 0.0})
                result[sid]["unrealized_pnl"] = float(row[1] or 0.0)
        finally:
            session.close()
    except Exception as exc:
        logger.warning(f"compute runtime metrics failed: {exc}")
    return result


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default or 0.0)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default or 0)


def _display_item(
    key: str,
    label_key: str,
    value: Any,
    value_type: str = "text",
    value_key: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "label_key": label_key,
        "value": value,
        "value_type": value_type,
        "value_key": value_key or "",
    }


def _build_bot_display(trading_config: dict[str, Any]) -> dict[str, Any]:
    """Build bot display config for grid/martingale/trend/DCA bots."""
    tc = trading_config if isinstance(trading_config, dict) else {}
    bot_type = str(tc.get("bot_type") or "").strip().lower()
    if not bot_type:
        return {}

    params = tc.get("bot_params") if isinstance(tc.get("bot_params"), dict) else {}
    initial_capital = _to_float(tc.get("initial_capital"), 0.0)

    display = {
        "bot_type": bot_type,
        "capital_label_key": "trading-bot.wizard.initialCapital",
        "capital_value": initial_capital,
        "capital_value_type": "usdt",
        "strategy_params": [],
        "risk_params": [],
    }

    if bot_type == "martingale":
        display["capital_label_key"] = "trading-bot.martingale.totalBudget"
        multiplier = _to_float(params.get("multiplier"), 2.0)
        max_layers = max(1, _to_int(params.get("maxLayers"), 5))
        geo_sum = 0.0
        for i in range(max_layers):
            geo_sum += pow(multiplier, i)
        first_order = max(0.0, (initial_capital / geo_sum) if geo_sum > 0 else 0.0)

        display["strategy_params"] = [
            _display_item("initialAmount", "trading-bot.martingale.initialAmountAuto", first_order, "usdt"),
            _display_item("multiplier", "trading-bot.martingale.multiplier", _to_float(params.get("multiplier"), 2.0), "number"),
            _display_item("maxLayers", "trading-bot.martingale.maxLayers", max_layers, "number"),
            _display_item("priceDropPct", "trading-bot.martingale.priceDropTrigger", _to_float(params.get("priceDropPct"), 0.0), "percent"),
            _display_item("takeProfitPct", "trading-bot.martingale.avgEntryTakeProfit", _to_float(params.get("takeProfitPct"), 0.0), "percent"),
            _display_item("stopLossPct", "trading-bot.martingale.avgEntryStopLoss", _to_float(params.get("stopLossPct"), 0.0), "percent"),
            _display_item("direction", "trading-bot.martingale.direction", params.get("direction") or "long", "enum", f"trading-bot.martingale.{params.get('direction') or 'long'}"),
        ]
        if _to_float(tc.get("max_daily_loss"), 0.0) > 0:
            display["risk_params"].append(
                _display_item("maxDailyLoss", "trading-bot.martingale.maxDailyLossAdvanced", _to_float(tc.get("max_daily_loss"), 0.0), "usdt")
            )
        return display

    if bot_type == "grid":
        display["strategy_params"] = [
            _display_item("upperPrice", "trading-bot.grid.upperPrice", _to_float(params.get("upperPrice"), 0.0), "usdt"),
            _display_item("lowerPrice", "trading-bot.grid.lowerPrice", _to_float(params.get("lowerPrice"), 0.0), "usdt"),
            _display_item("gridCount", "trading-bot.grid.gridCount", _to_int(params.get("gridCount"), 0), "number"),
            _display_item("amountPerGrid", "trading-bot.grid.amountPerGrid", _to_float(params.get("amountPerGrid"), 0.0), "usdt"),
            _display_item("gridMode", "trading-bot.grid.mode", params.get("gridMode") or "arithmetic", "enum", f"trading-bot.grid.{params.get('gridMode') or 'arithmetic'}"),
            _display_item("gridDirection", "trading-bot.grid.direction", params.get("gridDirection") or "neutral", "enum", f"trading-bot.grid.{params.get('gridDirection') or 'neutral'}"),
            _display_item("orderMode", "trading-bot.grid.orderType", params.get("orderMode") or "maker", "enum", "trading-bot.grid.limitOrder" if (params.get("orderMode") or "maker") == "maker" else "trading-bot.grid.marketOrder"),
        ]
    elif bot_type == "trend":
        direction = params.get("direction") or "long"
        direction_key = {
            "long": "trading-bot.trend.longOnly",
            "short": "trading-bot.trend.shortOnly",
            "both": "trading-bot.trend.bothSides",
        }.get(direction, "trading-bot.trend.longOnly")
        display["strategy_params"] = [
            _display_item("maPeriod", "trading-bot.trend.maPeriod", _to_int(params.get("maPeriod"), 0), "number"),
            _display_item("maType", "trading-bot.trend.maType", params.get("maType") or "EMA", "text"),
            _display_item("confirmBars", "trading-bot.trend.confirmBars", _to_int(params.get("confirmBars"), 0), "number"),
            _display_item("positionPct", "trading-bot.trend.positionPct", _to_float(params.get("positionPct"), 0.0), "percent"),
            _display_item("direction", "trading-bot.trend.direction", direction, "enum", direction_key),
        ]
    elif bot_type == "dca":
        frequency = params.get("frequency") or "daily"
        frequency_key = {
            "every_bar": "trading-bot.dca.everyBar",
            "hourly": "trading-bot.dca.hourly",
            "4h": "",
            "daily": "trading-bot.dca.daily",
            "weekly": "trading-bot.dca.weekly",
            "biweekly": "trading-bot.dca.biweekly",
            "monthly": "trading-bot.dca.monthly",
        }.get(frequency, "")
        display["strategy_params"] = [
            _display_item("amountEach", "trading-bot.dca.amountEach", _to_float(params.get("amountEach"), 0.0), "usdt"),
            _display_item("frequency", "trading-bot.dca.frequency", frequency, "enum", frequency_key),
            _display_item("totalBudget", "trading-bot.dca.totalBudget", _to_float(params.get("totalBudget"), 0.0), "usdt"),
            _display_item("dipBuyEnabled", "trading-bot.dca.dipBuy", bool(params.get("dipBuyEnabled")), "bool"),
            _display_item("dipThreshold", "trading-bot.dca.dipThreshold", _to_float(params.get("dipThreshold"), 0.0), "percent"),
        ]

    if _to_float(tc.get("stop_loss_pct"), 0.0) > 0:
        display["risk_params"].append(
            _display_item("stopLossPct", "trading-bot.risk.stopLossPct", _to_float(tc.get("stop_loss_pct"), 0.0), "percent")
        )
    if _to_float(tc.get("take_profit_pct"), 0.0) > 0:
        display["risk_params"].append(
            _display_item("takeProfitPct", "trading-bot.risk.takeProfitPct", _to_float(tc.get("take_profit_pct"), 0.0), "percent")
        )
    if _to_float(tc.get("max_position"), 0.0) > 0:
        display["risk_params"].append(
            _display_item("maxPosition", "trading-bot.risk.maxPosition", _to_float(tc.get("max_position"), 0.0), "usdt")
        )
    if _to_float(tc.get("max_daily_loss"), 0.0) > 0:
        display["risk_params"].append(
            _display_item("maxDailyLoss", "trading-bot.risk.maxDailyLoss", _to_float(tc.get("max_daily_loss"), 0.0), "usdt")
        )
    return display


def update_strategy(strategy_id: str, payload: dict[str, Any], session=None) -> None:
    """Update an existing strategy's fields."""
    _session = session or get_strategy_db_session()
    _owns_session = session is None
    try:
        strategy = _session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Merge trading_config 而不是整体替换，避免覆盖后端写入的运行时状态字段
        _RUNTIME_PROTECTED_KEYS = (
            "script_runtime_state",
            "last_signal_time",
            "last_execution_time",
            "bot_runtime_stats",
        )

        updatable_fields = [
            "strategy_name", "strategy_type", "symbol", "timeframe",
            "strategy_code", "indicator_config",
            "initial_capital", "leverage", "market_type", "trade_direction",
            "commission", "slippage", "execution_mode", "market_category",
            "strategy_mode", "notification_config", "ai_model_config",
            "strategy_group_id", "group_base_name",
        ]
        for field in updatable_fields:
            if field in payload:
                value = payload[field]
                if field in ("initial_capital", "commission", "slippage"):
                    value = float(value)
                elif field in ("leverage",):
                    value = int(value)
                setattr(strategy, field, value)

        # trading_config 使用 merge 逻辑，保护运行时字段
        if "trading_config" in payload:
            existing_tc = strategy.trading_config or {}
            if not isinstance(existing_tc, dict):
                existing_tc = {}
            incoming_tc = payload["trading_config"] or {}
            if not isinstance(incoming_tc, dict):
                incoming_tc = {}
            merged_tc = dict(existing_tc)
            merged_tc.update(incoming_tc)
            for key in _RUNTIME_PROTECTED_KEYS:
                if key not in incoming_tc and key in existing_tc:
                    merged_tc[key] = existing_tc[key]
            strategy.trading_config = merged_tc

        strategy.updated_at = datetime.now(timezone.utc)
        _session.commit()
        logger.info("strategy_updated", strategy_id=strategy_id)
    except Exception as exc:
        _session.rollback()
        logger.error("update_strategy_failed", strategy_id=strategy_id, error=str(exc))
        raise
    finally:
        if _owns_session:
            _session.close()


def delete_strategy(strategy_id: str) -> None:
    """Delete a strategy. Stops it first if running."""
    executor = get_trading_executor()
    if strategy_id in executor.running_strategies:
        executor.stop_strategy(strategy_id)

    session = get_strategy_db_session()
    try:
        strategy = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        session.delete(strategy)
        session.commit()
        logger.info("strategy_deleted", strategy_id=strategy_id)
    except Exception as exc:
        session.rollback()
        logger.error("delete_strategy_failed", strategy_id=strategy_id, error=str(exc))
        raise
    finally:
        session.close()


def get_strategy(strategy_id: str) -> dict[str, Any] | None:
    """Get a strategy by ID. Returns dict or None."""
    session = get_strategy_db_session()
    try:
        strategy = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
        if strategy is None:
            return None
        return _strategy_to_dict(strategy)
    finally:
        session.close()


def list_strategies() -> list[dict[str, Any]]:
    """List all strategies."""
    session = get_strategy_db_session()
    try:
        strategies = session.query(StrategyModel).order_by(StrategyModel.created_at.desc()).all()
        return [_strategy_to_dict(s) for s in strategies]
    finally:
        session.close()


def update_strategy_status(strategy_id: str, status: str) -> None:
    """Update just the status field of a strategy."""
    session = get_strategy_db_session()
    try:
        strategy = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
        if strategy is not None:
            strategy.status = status
            strategy.updated_at = datetime.now(timezone.utc)
            session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("update_status_failed", strategy_id=strategy_id, error=str(exc))
    finally:
        session.close()


def batch_start_strategies(strategy_ids: list[str]) -> dict[str, bool]:
    """Start multiple strategies. Returns {strategy_id: success}."""
    executor = get_trading_executor()
    results: dict[str, bool] = {}
    for sid in strategy_ids:
        try:
            results[sid] = executor.start_strategy(sid)
        except Exception as exc:
            logger.error("batch_start_failed", strategy_id=sid, error=str(exc))
            results[sid] = False
    return results


def batch_stop_strategies(strategy_ids: list[str]) -> dict[str, bool]:
    """Stop multiple strategies. Returns {strategy_id: success}."""
    executor = get_trading_executor()
    results: dict[str, bool] = {}
    for sid in strategy_ids:
        try:
            results[sid] = executor.stop_strategy(sid)
        except Exception as exc:
            logger.error("batch_stop_failed", strategy_id=sid, error=str(exc))
            results[sid] = False
    return results


import threading

_TEST_CONN_SEMAPHORE = threading.Semaphore(5)


def test_exchange_connection(exchange_config: dict[str, Any]) -> dict[str, Any]:
    """
    Test exchange connectivity with enhanced diagnostics.

    Migrated from QuantDinger:
    - Egress IP detection (for Binance IP whitelist debugging)
    - Demo mode detection
    - Binance -2015 cross-market diagnosis
    - Market type probing (spot/swap candidates)
    - Secret masking in logs
    - Concurrency limit (threading.Semaphore(5))

    Returns:
        {"success": bool, "message": str, "data": dict}
    """
    with _TEST_CONN_SEMAPHORE:
        try:
            from app.strategies.exchange_client import (
                CCXTExchangeClient,
                _hint_binance_2015,
                exchange_demo_mode_enabled,
                safe_exchange_config_for_log,
            )

            cfg = exchange_config or {}
            safe_cfg = safe_exchange_config_for_log(cfg)
            exchange_id = (cfg.get("exchange_id") or "").strip().lower()
            if not exchange_id:
                return {"success": False, "message": "Missing exchange_id", "data": None}

            # Egress IP detection (best-effort)
            egress_ip = ""
            try:
                import urllib.request
                with urllib.request.urlopen("https://ifconfig.me/ip", timeout=5) as resp:
                    egress_ip = resp.read().decode("utf-8").strip()
            except Exception:
                pass

            # Resolve market type candidates
            raw_market_type = str(
                cfg.get("market_type") or cfg.get("defaultType") or ""
            ).strip().lower()
            if raw_market_type in ("futures", "future", "perp", "perpetual"):
                raw_market_type = "swap"
            explicit_market_type = raw_market_type in ("spot", "swap")
            if exchange_id in ("coinbase", "coinbaseexchange"):
                market_candidates = ["spot"]
            else:
                market_candidates = [raw_market_type] if explicit_market_type else ["spot", "swap"]

            def _probe(market_type: str) -> dict[str, Any]:
                """Probe a single market type."""
                try:
                    client = CCXTExchangeClient(
                        exchange_id=exchange_id,
                        api_key=cfg.get("api_key", ""),
                        api_secret=cfg.get("api_secret", ""),
                        passphrase=cfg.get("passphrase"),
                        sandbox=cfg.get("sandbox", False),
                    )
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"Create client failed: {e}",
                        "data": {
                            "exchange": safe_cfg,
                            "market_type": market_type,
                            "egress_ip": egress_ip,
                        },
                    }

                client_kind = type(client).__name__

                # Public ping
                ok_public = False
                try:
                    ok_public = bool(client._exchange.fetch_time())
                except Exception:
                    try:
                        client._exchange.load_markets()
                        ok_public = True
                    except Exception:
                        ok_public = False

                if not ok_public:
                    return {
                        "success": False,
                        "message": f"Public ping failed: {exchange_id}",
                        "data": {
                            "exchange": safe_cfg,
                            "client": client_kind,
                            "market_type": market_type,
                            "egress_ip": egress_ip,
                        },
                    }

                # Private validation
                try:
                    balance = client.get_balance()
                except Exception as e:
                    msg = str(e)
                    # Binance -2015 diagnosis
                    if exchange_id == "binance" and ("-2015" in msg or "Invalid API-key, IP, or permissions" in msg):
                        alt_market_type = "spot" if market_type != "spot" else "swap"
                        alt_ok = False
                        try:
                            alt_client = CCXTExchangeClient(
                                exchange_id=exchange_id,
                                api_key=cfg.get("api_key", ""),
                                api_secret=cfg.get("api_secret", ""),
                                passphrase=cfg.get("passphrase"),
                                sandbox=cfg.get("sandbox", False),
                            )
                            alt_client._exchange.fetch_balance()
                            alt_ok = True
                        except Exception:
                            alt_ok = False

                        is_demo = exchange_demo_mode_enabled(cfg)
                        base_url = getattr(client._exchange, "urls", {}).get("api", "")
                        hint = _hint_binance_2015(market_type, base_url, is_demo, alt_ok, alt_market_type)
                        msg = f"{msg} | {hint}"

                    return {
                        "success": False,
                        "message": f"Auth failed: {msg}",
                        "data": {
                            "exchange": safe_cfg,
                            "client": client_kind,
                            "market_type": market_type,
                            "egress_ip": egress_ip,
                        },
                    }

                return {
                    "success": True,
                    "message": "Connection OK",
                    "data": {
                        "exchange": safe_cfg,
                        "client": client_kind,
                        "market_type": market_type,
                        "egress_ip": egress_ip,
                        "balance": balance,
                    },
                }

            last_failure = None
            for market_type in market_candidates:
                result = _probe(market_type)
                if result.get("success"):
                    if not explicit_market_type and len(market_candidates) > 1:
                        result["message"] = f"Connection OK ({market_type})"
                    return result
                last_failure = result

            if last_failure and not explicit_market_type and len(market_candidates) > 1:
                tried = "/".join(market_candidates)
                last_failure["message"] = f"{last_failure.get('message')}. Tried market_type={tried}"
            return last_failure or {"success": False, "message": "Connection failed", "data": None}

        except Exception as e:
            logger.error("test_exchange_connection_failed", error=str(e))
            return {"success": False, "message": f"Connection failed: {e}", "data": None}


def _strategy_to_dict(strategy: StrategyModel) -> dict[str, Any]:
    """Convert a StrategyModel to a serializable dict."""
    result = {
        "id": str(strategy.id),
        "strategy_name": strategy.strategy_name,
        "strategy_type": strategy.strategy_type,
        "status": strategy.status,
        "symbol": strategy.symbol,
        "timeframe": strategy.timeframe,
        "initial_capital": strategy.initial_capital,
        "leverage": strategy.leverage,
        "market_type": strategy.market_type,
        "trade_direction": strategy.trade_direction,
        "commission": strategy.commission,
        "slippage": strategy.slippage,
        "execution_mode": getattr(strategy, "execution_mode", "signal"),
        "market_category": getattr(strategy, "market_category", "Crypto"),
        "strategy_mode": getattr(strategy, "strategy_mode", "signal"),
        "strategy_group_id": getattr(strategy, "strategy_group_id", ""),
        "group_base_name": getattr(strategy, "group_base_name", ""),
        "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
        "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
    }
    # Attach bot_display if trading_config contains bot_type
    tc = strategy.trading_config or {}
    if isinstance(tc, dict) and tc.get("bot_type"):
        result["bot_display"] = _build_bot_display(tc)
    return result
