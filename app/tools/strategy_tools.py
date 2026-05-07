from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from langchain.tools import tool
from app.core.logging import get_logger

logger = get_logger("app.tools.strategy_tools")


@tool
def run_backtest(
    code: str,
    symbol: str,
    strategy_type: str = "indicator",
    timeframe: str = "1D",
    initial_capital: float = 100000,
    commission: float = 0.001,
    leverage: int = 1,
    trade_direction: str = "long",
    days: int = 365,
    market: str = "stock",
    params_json: str = "{}",
    risk_config_json: str = "{}",
) -> str:
    """运行策略回测。code 是指标代码或脚本代码，symbol 是交易标的。
    strategy_type: indicator 或 script。返回回测结果 JSON。"""
    try:
        from app.strategies.backtest import BacktestService
        import json as _json

        params = _json.loads(params_json)
        risk_config = _json.loads(risk_config_json)

        service = BacktestService()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        strategy_config = {}
        if risk_config:
            strategy_config["risk"] = risk_config

        if strategy_type == "script":
            result = service._run_script_strategy(
                code=code, market=market, symbol=symbol, timeframe=timeframe,
                start_date=start_date, end_date=end_date,
                initial_capital=initial_capital, commission=commission,
                slippage=0.0, leverage=leverage, trade_direction=trade_direction,
                strategy_config=strategy_config,
            )
        else:
            result = service.run(
                indicator_code=code, market=market, symbol=symbol, timeframe=timeframe,
                start_date=start_date, end_date=end_date,
                initial_capital=initial_capital, commission=commission,
                leverage=leverage, trade_direction=trade_direction,
                strategy_config=strategy_config, indicator_params=params,
            )

        return _json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("run_backtest_tool_error", error=str(e))
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def verify_strategy_code(code: str, strategy_type: str = "indicator") -> str:
    """验证策略代码语法是否正确。返回 {valid: bool, error: str|null}"""
    try:
        from app.core.safe_exec import validate_code_safety

        is_safe, error = validate_code_safety(code)
        if not is_safe:
            return json.dumps({"valid": False, "error": error}, ensure_ascii=False)

        if strategy_type == "script":
            from app.strategies.script_runtime import compile_strategy_script_handlers
            compile_strategy_script_handlers(code)
        else:
            compile(code, "<indicator>", "exec")

        return json.dumps({"valid": True, "error": None}, ensure_ascii=False)
    except SyntaxError as e:
        return json.dumps(
            {"valid": False, "error": f"语法错误: {e.msg} (行 {e.lineno})"},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"valid": False, "error": str(e)}, ensure_ascii=False)


@tool
def analyze_code_quality(code: str) -> str:
    """分析指标代码质量，返回问题列表和建议。"""
    try:
        from app.strategies.code_quality import analyze_indicator_code_quality
        result = analyze_indicator_code_quality(code)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("analyze_code_quality_tool_error", error=str(e))
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def execute_indicator(
    code: str,
    symbol: str,
    params_json: str = "{}",
    timeframe: str = "1D",
    days: int = 120,
    market: str = "stock",
) -> str:
    """执行指标代码获取最新信号。返回买入/卖出信号数量。"""
    try:
        from app.strategies.backtest import BacktestService
        import json as _json

        params = _json.loads(params_json)
        service = BacktestService()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        df = service._fetch_kline_data(market, symbol, timeframe, start_date, end_date)
        if df.empty:
            return json.dumps({"error": "无法获取K线数据"}, ensure_ascii=False)

        backtest_params = {
            "leverage": 1, "initial_capital": 100000,
            "commission": 0.001, "trade_direction": "both",
            "indicator_params": params,
        }
        signals = service._execute_indicator(code, df, backtest_params)

        if isinstance(signals, dict):
            buy_count = int(signals.get("buy", []).sum()) if "buy" in signals else 0
            sell_count = int(signals.get("sell", []).sum()) if "sell" in signals else 0
        else:
            buy_count = sell_count = 0

        return json.dumps({
            "buy_signals": buy_count, "sell_signals": sell_count,
            "total_bars": len(df),
            "signal_columns": list(signals.keys()) if isinstance(signals, dict) else [],
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("execute_indicator_tool_error", error=str(e))
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def start_strategy(strategy_id: int) -> str:
    """启动策略实盘运行。返回 {success: bool, strategy_id: int, status: str}"""
    try:
        from app.strategies.trading_executor import TradingExecutor
        executor = TradingExecutor()
        ok = executor.start_strategy(strategy_id)
        if ok:
            return json.dumps(
                {"success": True, "strategy_id": strategy_id, "status": "running"},
                ensure_ascii=False,
            )
        else:
            error_msg = getattr(executor, "_last_start_failure", "启动失败")
            return json.dumps({"success": False, "error": error_msg}, ensure_ascii=False)
    except Exception as e:
        logger.error("start_strategy_tool_error", error=str(e))
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def stop_strategy(strategy_id: int) -> str:
    """停止策略。返回 {success: bool, strategy_id: int, status: str}"""
    try:
        from app.strategies.trading_executor import TradingExecutor
        executor = TradingExecutor()
        ok = executor.stop_strategy(strategy_id)
        return json.dumps({
            "success": ok, "strategy_id": strategy_id,
            "status": "stopped" if ok else "not_running",
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("stop_strategy_tool_error", error=str(e))
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool
def list_strategy_indicators() -> str:
    """列出所有可用的内置指标和自定义指标。"""
    try:
        from app.strategies.registry import get_indicator_registry
        from app.strategies.builtin_indicators import list_builtin_indicators

        registry = get_indicator_registry()
        builtin = list_builtin_indicators()
        custom = registry.list_indicators()

        return json.dumps({"builtin": builtin, "custom": custom}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("list_indicators_tool_error", error=str(e))
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# Export list for registration in app/tools/__init__.py
STRATEGY_TOOLS = [
    run_backtest,
    verify_strategy_code,
    analyze_code_quality,
    execute_indicator,
    start_strategy,
    stop_strategy,
    list_strategy_indicators,
]
