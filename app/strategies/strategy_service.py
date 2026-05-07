"""
UF Stock Assistant — Strategy Service Layer

High-level CRUD and batch operations for strategies.
Simplified from QuantDinger: no user_id scoping, no bot_display.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.strategies.models import StrategyModel
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


def update_strategy(strategy_id: str, payload: dict[str, Any], session=None) -> None:
    """Update an existing strategy's fields."""
    _session = session or get_strategy_db_session()
    _owns_session = session is None
    try:
        strategy = _session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Merge trading_config 而不是整体替换，避免覆盖后端写入的运行时状态字段
        # (如 script_runtime_state、马丁 layer/total_cost、网格 bp/sp/prev_price、DCA total_qty 等)
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
        ]
        for field in updatable_fields:
            if field in payload:
                value = payload[field]
                # Type coercion for numeric fields.
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


def test_exchange_connection(exchange_config: dict[str, Any]) -> dict[str, Any]:
    """
    Test exchange connectivity using the provided config.

    Returns:
        {"success": bool, "error": str_or_empty, "balance": dict_or_none}
    """
    try:
        from app.strategies.exchange_client import CCXTExchangeClient

        exchange_id = exchange_config.get("exchange_id", "binance")
        api_key = exchange_config.get("api_key", "")
        api_secret = exchange_config.get("api_secret", "")
        passphrase = exchange_config.get("passphrase")
        sandbox = exchange_config.get("sandbox", False)

        if not api_key or not api_secret:
            return {"success": False, "error": "Missing api_key or api_secret", "balance": None}

        client = CCXTExchangeClient(
            exchange_id=exchange_id,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            sandbox=sandbox,
        )

        balance = client.get_balance()
        return {"success": True, "error": "", "balance": balance}

    except Exception as exc:
        logger.error("test_exchange_connection_failed", error=str(exc))
        return {"success": False, "error": str(exc), "balance": None}


def _strategy_to_dict(strategy: StrategyModel) -> dict[str, Any]:
    """Convert a StrategyModel to a serializable dict."""
    return {
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
        "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
        "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
    }
