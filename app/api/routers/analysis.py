"""
UF Stock Assistant — AI 分析记忆与反思 API
历史查询、相似模式、反馈、性能统计
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.core.exceptions import AssistantException
from app.core.logging import get_logger
from app.services.analysis_memory import AnalysisMemoryService
from app.services.ai_calibration import AICalibrationService

logger = get_logger("app.api.routers.analysis")

router = APIRouter(prefix="/analysis", tags=["AI 分析记忆"], dependencies=[Depends(get_current_user)])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    memory_id: int = Field(..., description="分析记录 ID")
    feedback: str = Field(..., description="反馈类型: helpful / not_helpful / accurate / inaccurate")


class CalibrationQuery(BaseModel):
    market: str = Field(default="AStock", description="市场类型")


class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., description="股票代码")
    market_type: str = Field(default="stock", description="市场类型: stock / crypto")


# ------------------------------------------------------------------
# 执行分析
# ------------------------------------------------------------------

@router.post("/analyze")
async def analyze_stock(
    payload: AnalyzeRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """执行单股票快速 AI 分析并保存结果"""
    try:
        from app.strategies.fast_analysis import get_fast_analysis_service

        svc = get_fast_analysis_service()
        result = svc.analyze(
            symbol=payload.symbol,
            market_type=payload.market_type,
            user_id=str(user["user_id"]),
        )
        return {"code": "success", "data": result}
    except Exception as exc:
        logger.error("analyze_stock_error", symbol=payload.symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=f"分析失败: {exc}")


# ------------------------------------------------------------------
# 查询接口
# ------------------------------------------------------------------

@router.get("/history")
async def get_analysis_history(
    user: dict = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
    symbol: str | None = Query(None, description="股票代码过滤"),
) -> dict[str, Any]:
    """获取用户分析历史"""
    svc = AnalysisMemoryService()
    data = svc.get_history(user_id=str(user["user_id"]), symbol=symbol, page=page, page_size=page_size)
    return {"code": "success", "data": data}


@router.get("/history/{market}/{symbol}")
async def get_recent_analysis(
    market: str,
    symbol: str,
    days: int = 7,
    limit: int = 5,
) -> dict[str, Any]:
    """获取某标近期的分析历史"""
    svc = AnalysisMemoryService()
    items = svc.get_recent(market=market, symbol=symbol, days=days, limit=limit)
    return {"code": "success", "data": {"items": items, "market": market, "symbol": symbol}}


@router.get("/similar/{market}/{symbol}")
async def get_similar_patterns(
    market: str,
    symbol: str,
    indicators: str = "{}",
    limit: int = 3,
) -> dict[str, Any]:
    """获取历史相似技术指标模式"""
    import json
    try:
        current_indicators = json.loads(indicators) if indicators else {}
    except json.JSONDecodeError:
        raise AssistantException("invalid_indicators_json", "indicators 参数必须是合法 JSON")

    svc = AnalysisMemoryService()
    patterns = svc.get_similar_patterns(market=market, symbol=symbol, current_indicators=current_indicators, limit=limit)
    return {"code": "success", "data": {"patterns": patterns}}


@router.delete("/{memory_id}")
async def delete_analysis(
    memory_id: int,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """删除分析记录"""
    svc = AnalysisMemoryService()
    ok = svc.delete(memory_id=memory_id, user_id=str(user["user_id"]))
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在或无权限删除")
    return {"code": "success", "data": {"deleted": True}}


# ------------------------------------------------------------------
# 反馈与统计
# ------------------------------------------------------------------

@router.post("/feedback")
async def record_feedback(payload: FeedbackRequest) -> dict[str, Any]:
    """记录用户对分析的反馈"""
    svc = AnalysisMemoryService()
    ok = svc.record_feedback(payload.memory_id, payload.feedback)
    if not ok:
        raise AssistantException("feedback_failed", "反馈记录失败，memory_id 可能不存在")
    return {"code": "success", "data": {"recorded": True}}


@router.get("/stats")
async def get_performance_stats(
    market: str | None = None,
    symbol: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """获取 AI 性能统计"""
    svc = AnalysisMemoryService()
    stats = svc.get_performance_stats(market=market, symbol=symbol, days=days)
    return {"code": "success", "data": stats}


@router.get("/calibration/{market}")
async def get_calibration(market: str) -> dict[str, Any]:
    """获取市场最新校准配置"""
    svc = AICalibrationService()
    cfg = svc.get_latest(market)
    return {"code": "success", "data": {"market": market, "config": cfg}}
