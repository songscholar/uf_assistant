"""
UF Stock Assistant — 策略接口

支持双范式策略引擎：
- evaluate 模式：传统内置策略
- IndicatorStrategy：指标代码回测/实盘
- ScriptStrategy：事件驱动脚本回测/实盘
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.core.logging import get_logger
from app.services.market_analyzer import MarketAnalyzer
from app.services.stock_picker import StockPicker
from app.strategies.registry import (
    create_strategy,
    get_indicator_registry,
    list_all_strategies,
)
from app.strategies.strategy_service import (
    batch_create_strategies,
    get_exchange_symbols,
    _compute_runtime_metrics,
)

logger = get_logger("app.api.strategy")

router = APIRouter(dependencies=[Depends(get_current_user)])


class StrategyEvaluateRequest(BaseModel):
    """策略执行请求"""
    symbol: str = Field(..., description="股票代码")
    params: dict[str, Any] = Field(default_factory=dict, description="策略参数")


class StrategyPickRequest(BaseModel):
    """选股请求"""
    strategy_key: str = Field(..., description="策略标识")
    symbols: list[str] = Field(..., description="股票代码列表")
    params: dict[str, Any] = Field(default_factory=dict, description="策略参数")
    min_confidence: float = Field(0.3, ge=0, le=1, description="最小置信度")


class QuickScreenRequest(BaseModel):
    """快速筛选请求"""
    min_price: float | None = Field(None, description="最低价格")
    max_price: float | None = Field(None, description="最高价格")
    min_change_pct: float | None = Field(None, description="最小涨跌幅")
    max_change_pct: float | None = Field(None, description="最大涨跌幅")
    limit: int = Field(20, ge=1, le=100, description="返回数量")


class CustomStrategyRequest(BaseModel):
    """自定义策略请求"""
    description: str = Field(..., description="策略描述", min_length=10, max_length=2000)


# =============================================================================
# 接口
# =============================================================================

@router.get("/strategies")
async def list_strategies():
    """列出所有策略"""
    try:
        return list_all_strategies()
    except Exception as exc:
        logger.error("list_strategies_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/{strategy_key}/evaluate")
async def evaluate_strategy(strategy_key: str, request: StrategyEvaluateRequest):
    """执行策略分析"""
    try:
        import json
        from app.tools.stock_data import get_stock_history
        
        strategy = create_strategy(strategy_key, **request.params)
        if not strategy:
            raise HTTPException(status_code=404, detail=f"策略 '{strategy_key}' 不存在")
        
        # 获取历史数据
        history_json = get_stock_history(request.symbol, period="daily", limit=120)
        history_data = json.loads(history_json)
        
        if "error" in history_data or not history_data.get("data"):
            raise HTTPException(status_code=400, detail="获取历史数据失败")
        
        # 执行策略
        result = strategy.evaluate(request.symbol, history_data["data"])

        # 映射 direction: up→buy, down→sell, flat→hold
        direction_map = {"up": "buy", "down": "sell", "flat": "hold"}
        raw_direction = result.signal.direction.value if result.signal else None
        mapped_direction = direction_map.get(raw_direction, raw_direction) if raw_direction else None

        return {
            "strategy": strategy.name,
            "symbol": request.symbol,
            "signal": {
                "direction": mapped_direction,
                "confidence": result.signal.confidence if result.signal else None,
                "reason": result.signal.reason if result.signal else None,
            } if result.signal else None,
            "data": result.data,
            "error": result.error,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("evaluate_strategy_error", strategy=strategy_key, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/pick")
async def pick_stocks(request: StrategyPickRequest):
    """根据策略选股"""
    try:
        picker = StockPicker()
        return picker.pick_by_strategy(
            strategy_key=request.strategy_key,
            symbols=request.symbols,
            strategy_params=request.params,
            min_confidence=request.min_confidence,
        )
    except Exception as exc:
        logger.error("pick_stocks_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/screen")
async def quick_screen(request: QuickScreenRequest):
    """快速筛选股票"""
    try:
        picker = StockPicker()
        conditions = {}
        if request.min_price is not None:
            conditions["min_price"] = request.min_price
        if request.max_price is not None:
            conditions["max_price"] = request.max_price
        if request.min_change_pct is not None:
            conditions["min_change_pct"] = request.min_change_pct
        if request.max_change_pct is not None:
            conditions["max_change_pct"] = request.max_change_pct
        conditions["limit"] = request.limit
        
        return picker.quick_screen(conditions)
    except Exception as exc:
        logger.error("quick_screen_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/custom")
async def create_custom_strategy(request: CustomStrategyRequest):
    """创建自定义策略（通过 LLM 生成）"""
    try:
        from app.strategies.custom import CustomStrategyManager
        
        manager = CustomStrategyManager.from_env()
        result = manager.generate_strategy(request.description)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
        
        return {
            "success": True,
            "strategy_key": result["strategy_key"],
            "code": result["code"],
            "message": "策略代码已生成，请审核后编译",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("custom_strategy_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/market/daily-report")
async def daily_report():
    """获取每日市场报告"""
    try:
        analyzer = MarketAnalyzer()
        return analyzer.generate_daily_report()
    except Exception as exc:
        logger.error("daily_report_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# QuantDinger 风格策略引擎接口
# =============================================================================


class BacktestRequest(BaseModel):
    """回测请求"""
    code: str = Field(..., description="指标/脚本代码")
    symbol: str = Field(..., description="交易标的")
    strategy_type: str = Field("indicator", description="策略类型: indicator / script")
    timeframe: str = Field("1D", description="K线周期")
    initial_capital: float = Field(100000, description="初始资金")
    commission: float = Field(0.001, description="手续费率")
    leverage: int = Field(1, description="杠杆倍数")
    trade_direction: str = Field("long", description="交易方向: long / short / both")
    params: dict[str, Any] = Field(default_factory=dict, description="指标参数")
    risk_config: dict[str, Any] = Field(default_factory=dict, description="风控配置")
    strategy_config: dict[str, Any] = Field(default_factory=dict, description="策略配置")
    days: int = Field(365, description="回测天数")
    market: str = Field("stock", description="市场类型: stock / crypto")
    enable_mtf: bool = Field(False, description="是否启用多时间框架回测")


class CodeVerifyRequest(BaseModel):
    """代码验证请求"""
    code: str = Field(..., description="策略代码")
    strategy_type: str = Field("indicator", description="策略类型")


class CodeQualityRequest(BaseModel):
    """代码质量检测请求"""
    code: str = Field(..., description="指标代码")


class ParseParamsRequest(BaseModel):
    """参数解析请求"""
    code: str = Field(..., description="指标代码")


class IndicatorExecuteRequest(BaseModel):
    """指标执行请求"""
    code: str = Field(..., description="指标代码")
    symbol: str = Field(..., description="交易标的")
    params: dict[str, Any] = Field(default_factory=dict, description="指标参数")
    timeframe: str = Field("1D", description="K线周期")
    days: int = Field(120, description="数据天数")
    market: str = Field("stock", description="市场类型")


class StrategyStartRequest(BaseModel):
    """策略启动请求"""
    strategy_id: int = Field(..., description="策略ID")


class StrategyStopRequest(BaseModel):
    """策略停止请求"""
    strategy_id: int = Field(..., description="策略ID")


@router.post("/strategies/backtest")
async def run_backtest(request: BacktestRequest):
    """运行回测"""
    try:
        from app.strategies.backtest import BacktestService

        service = BacktestService()

        end_date = datetime.now()
        start_date = datetime.now().replace(year=end_date.year - 1) if request.days >= 365 else \
            datetime.fromtimestamp(end_date.timestamp() - request.days * 86400)

        strategy_config = request.strategy_config or {}
        if request.risk_config:
            strategy_config.setdefault("risk", {}).update(request.risk_config)

        if request.strategy_type == "script":
            result = service._run_script_strategy(
                code=request.code,
                market=request.market,
                symbol=request.symbol,
                timeframe=request.timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_capital=request.initial_capital,
                commission=request.commission,
                slippage=0.0,
                leverage=request.leverage,
                trade_direction=request.trade_direction,
                strategy_config=strategy_config,
            )
        elif request.enable_mtf:
            result = service.run_multi_timeframe(
                indicator_code=request.code,
                market=request.market,
                symbol=request.symbol,
                timeframe=request.timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_capital=request.initial_capital,
                commission=request.commission,
                leverage=request.leverage,
                trade_direction=request.trade_direction,
                strategy_config=strategy_config,
                enable_mtf=True,
                indicator_params=request.params,
            )
        else:
            result = service.run(
                indicator_code=request.code,
                market=request.market,
                symbol=request.symbol,
                timeframe=request.timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_capital=request.initial_capital,
                commission=request.commission,
                leverage=request.leverage,
                trade_direction=request.trade_direction,
                strategy_config=strategy_config,
                indicator_params=request.params,
            )

        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("backtest_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/verify-code")
async def verify_code(request: CodeVerifyRequest):
    """验证策略代码语法"""
    try:
        from app.core.safe_exec import validate_code_safety

        is_safe, error = validate_code_safety(request.code)
        if not is_safe:
            return {"valid": False, "error": error}

        if request.strategy_type == "script":
            from app.strategies.script_runtime import compile_strategy_script_handlers
            try:
                compile_strategy_script_handlers(request.code)
                return {"valid": True, "error": None}
            except Exception as e:
                return {"valid": False, "error": str(e)}
        else:
            try:
                compile(request.code, "<indicator>", "exec")
                return {"valid": True, "error": None}
            except SyntaxError as e:
                return {"valid": False, "error": f"语法错误: {e.msg} (行 {e.lineno})"}
    except Exception as exc:
        logger.error("verify_code_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/code-quality")
async def code_quality(request: CodeQualityRequest):
    """代码质量检测"""
    try:
        from app.strategies.code_quality import analyze_indicator_code_quality

        result = analyze_indicator_code_quality(request.code)
        return result
    except Exception as exc:
        logger.error("code_quality_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/parse-params")
async def parse_params(request: ParseParamsRequest):
    """解析指标参数声明"""
    try:
        from app.strategies.indicator_params import IndicatorParamsParser, StrategyConfigParser

        params = IndicatorParamsParser.parse_params(request.code)
        config = StrategyConfigParser.parse(request.code)

        return {
            "params": params,
            "strategy_config": config,
        }
    except Exception as exc:
        logger.error("parse_params_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/indicator/execute")
async def execute_indicator(request: IndicatorExecuteRequest):
    """执行指标获取信号"""
    try:
        from app.strategies.backtest import BacktestService
        from app.strategies.indicator_params import IndicatorParamsParser

        service = BacktestService()
        end_date = datetime.now()
        start_date = datetime.fromtimestamp(end_date.timestamp() - request.days * 86400)

        df = service._fetch_kline_data(request.market, request.symbol, request.timeframe, start_date, end_date)
        if df.empty:
            raise HTTPException(status_code=400, detail="无法获取K线数据")

        backtest_params = {
            "leverage": 1,
            "initial_capital": 100000,
            "commission": 0.001,
            "trade_direction": "both",
            "indicator_params": request.params,
        }

        signals = service._execute_indicator(request.code, df, backtest_params)

        if isinstance(signals, dict):
            buy_count = int(signals.get("buy", []).sum()) if "buy" in signals else 0
            sell_count = int(signals.get("sell", []).sum()) if "sell" in signals else 0
        else:
            buy_count = sell_count = 0

        return {
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "total_bars": len(df),
            "signal_columns": list(signals.keys()) if isinstance(signals, dict) else [],
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("execute_indicator_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/strategies/indicators")
async def list_indicators():
    """列出所有内置指标"""
    try:
        from app.strategies.builtin_indicators import list_builtin_indicators

        registry = get_indicator_registry()
        builtin = list_builtin_indicators()
        custom = registry.list_indicators()

        return {
            "builtin": builtin,
            "custom": custom,
        }
    except Exception as exc:
        logger.error("list_indicators_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/strategies/indicators/{name}")
async def get_indicator(name: str):
    """获取指标详情（含代码）"""
    try:
        from app.strategies.builtin_indicators import get_builtin_indicator_by_name

        indicator = get_builtin_indicator_by_name(name)
        if not indicator:
            registry = get_indicator_registry()
            indicator = registry.get(name)

        if not indicator:
            raise HTTPException(status_code=404, detail=f"指标 '{name}' 不存在")

        return indicator
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_indicator_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/start")
async def start_strategy(request: StrategyStartRequest):
    """启动策略实盘运行"""
    try:
        from app.strategies.trading_executor import TradingExecutor

        executor = TradingExecutor()
        ok = executor.start_strategy(request.strategy_id)
        if not ok:
            error_msg = getattr(executor, "_last_start_failure", "启动失败")
            raise HTTPException(status_code=400, detail=error_msg)

        return {"success": True, "strategy_id": request.strategy_id, "status": "running"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("start_strategy_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/stop")
async def stop_strategy(request: StrategyStopRequest):
    """停止策略"""
    try:
        from app.strategies.trading_executor import TradingExecutor

        executor = TradingExecutor()
        ok = executor.stop_strategy(request.strategy_id)
        if not ok:
            raise HTTPException(status_code=400, detail="策略未在运行或停止失败")

        return {"success": True, "strategy_id": request.strategy_id, "status": "stopped"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("stop_strategy_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/strategies/positions")
async def get_strategy_positions(strategy_id: str | None = None):
    """获取策略持仓"""
    try:
        from app.strategies.models import StrategyPosition
        from app.strategies.trading_executor import get_strategy_db_session

        session = get_strategy_db_session()
        try:
            query = session.query(StrategyPosition)
            if strategy_id is not None:
                query = query.filter(StrategyPosition.strategy_id == strategy_id)
            positions = query.all()
            return [
                {
                    "id": p.id,
                    "strategy_id": p.strategy_id,
                    "symbol": p.symbol,
                    "side": p.side,
                    "size": p.size,
                    "entry_price": p.entry_price,
                    "amount": p.amount,
                    "unrealized_pnl": p.unrealized_pnl,
                    "highest_price": p.highest_price,
                    "lowest_price": p.lowest_price,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in positions
            ]
        finally:
            session.close()
    except Exception as exc:
        logger.error("get_positions_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/strategies/trades")
async def get_strategy_trades(strategy_id: str | None = None, limit: int = 50):
    """获取策略交易记录"""
    try:
        from app.strategies.models import StrategyTrade
        from app.strategies.trading_executor import get_strategy_db_session

        session = get_strategy_db_session()
        try:
            query = session.query(StrategyTrade)
            if strategy_id is not None:
                query = query.filter(StrategyTrade.strategy_id == strategy_id)
            trades = query.order_by(StrategyTrade.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": t.id,
                    "strategy_id": t.strategy_id,
                    "symbol": t.symbol,
                    "side": t.trade_type,
                    "price": t.price,
                    "amount": t.amount,
                    "commission": t.commission,
                    "pnl": t.profit,
                    "timestamp": t.created_at.isoformat() if t.created_at else None,
                }
                for t in trades
            ]
        finally:
            session.close()
    except Exception as exc:
        logger.error("get_trades_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/strategies/equity-curve")
async def get_equity_curve(run_id: int):
    """获取回测权益曲线"""
    try:
        from app.strategies.models import BacktestEquityPoint
        from app.strategies.trading_executor import get_strategy_db_session

        session = get_strategy_db_session()
        try:
            points = (
                session.query(BacktestEquityPoint)
                .filter(BacktestEquityPoint.run_id == run_id)
                .order_by(BacktestEquityPoint.timestamp)
                .all()
            )
            return [
                {"timestamp": p.timestamp.isoformat() if p.timestamp else None, "equity": p.equity}
                for p in points
            ]
        finally:
            session.close()
    except Exception as exc:
        logger.error("get_equity_curve_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/strategies/logs")
async def get_strategy_logs(strategy_id: int, limit: int = 100):
    """获取策略运行日志"""
    try:
        from app.strategies.models import StrategyLog
        from app.strategies.trading_executor import get_strategy_db_session

        session = get_strategy_db_session()
        try:
            logs = (
                session.query(StrategyLog)
                .filter(StrategyLog.strategy_id == strategy_id)
                .order_by(StrategyLog.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": l.id,
                    "strategy_id": l.strategy_id,
                    "level": l.level,
                    "message": l.message,
                    "created_at": l.created_at.isoformat() if l.created_at else None,
                }
                for l in logs
            ]
        finally:
            session.close()
    except Exception as exc:
        logger.error("get_logs_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# Batch + Exchange Symbols + Runtime Metrics ( ported from QuantDinger )
# =============================================================================

class BatchCreateRequest(BaseModel):
    """批量创建策略请求"""
    strategy_name: str = Field(..., description="策略基础名称")
    symbols: list[str] = Field(..., description="交易对列表，支持 Market:SYMBOL 格式")
    strategy_type: str = Field("indicator", description="策略类型")
    market_category: str = Field("Crypto", description="市场类别")
    exchange_config: dict[str, Any] = Field(default_factory=dict, description="交易所配置")
    trading_config: dict[str, Any] = Field(default_factory=dict, description="交易配置")
    indicator_config: dict[str, Any] = Field(default_factory=dict, description="指标配置")
    initial_capital: float = Field(100000.0, description="初始资金")
    leverage: int = Field(1, description="杠杆")
    trade_direction: str = Field("long", description="交易方向")
    execution_mode: str = Field("signal", description="执行模式")
    strategy_mode: str = Field("signal", description="策略模式")
    notification_config: dict[str, Any] | None = None
    ai_model_config: dict[str, Any] | None = None
    user_id: str = Field("default", description="用户ID")


class ExchangeSymbolsRequest(BaseModel):
    """获取交易所交易对请求"""
    exchange_id: str = Field(..., description="交易所ID")
    market_type: str = Field("spot", description="市场类型: spot, swap, futures")
    base_url: str | None = Field(None, description="自定义基础URL")
    proxies: dict[str, Any] | None = None
    credential_id: str | None = Field(None, description="凭据ID（如有）")


@router.post("/strategies/batch")
async def create_strategies_batch(request: BatchCreateRequest):
    """批量创建策略（多交易对）"""
    try:
        payload = request.model_dump()
        result = batch_create_strategies(payload)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("batch_create_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/strategies/exchange-symbols")
async def get_symbols_by_exchange(request: ExchangeSymbolsRequest):
    """按交易所获取交易对列表"""
    try:
        exchange_config = request.model_dump(exclude_none=True)
        result = get_exchange_symbols(exchange_config, user_id="default")
        return result
    except Exception as exc:
        logger.error("get_exchange_symbols_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/strategies/{strategy_id}/runtime-metrics")
async def get_runtime_metrics(strategy_id: str):
    """获取策略运行时指标（已实现盈亏 / 未实现盈亏）"""
    try:
        metrics = _compute_runtime_metrics([strategy_id])
        return metrics.get(strategy_id, {"realized_pnl": 0.0, "unrealized_pnl": 0.0})
    except Exception as exc:
        logger.error("runtime_metrics_error", strategy_id=strategy_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
