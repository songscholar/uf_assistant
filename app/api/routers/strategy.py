"""
UF Stock Assistant — 策略接口
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.services.market_analyzer import MarketAnalyzer
from app.services.stock_picker import StockPicker
from app.strategies.registry import create_strategy, list_all_strategies

logger = get_logger("app.api.strategy")

router = APIRouter()


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
        
        return {
            "strategy": strategy.name,
            "symbol": request.symbol,
            "signal": {
                "direction": result.signal.direction.value if result.signal else None,
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
