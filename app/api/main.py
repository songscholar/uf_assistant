"""
UF Stock Assistant — FastAPI 主应用
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.cache import start_background_refresh, stop_background_refresh
from app.core.config import get_settings
from app.core.exceptions import AssistantException
from app.core.logging import get_logger, setup_logging

from .routers import billing, chat, crypto, market, stock, strategy, trading, upload
from .agent import router as agent_router

logger = get_logger("app.api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    setup_logging()
    logger.info("api_server_starting", version=get_settings().version)

    # 启动后台数据预刷新任务（首次延迟后自动拉取 AKShare 全量数据到缓存）
    refresh_task = start_background_refresh()
    logger.info("background_refresh_task_started")

    # 启动 USDT 支付订单后台轮询（如启用）
    from app.services.usdt_payment import get_usdt_order_worker
    worker = get_usdt_order_worker()
    worker.start()
    logger.info("usdt_order_worker_started")

    yield

    # 关闭
    stop_background_refresh()
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass

    # 停止 USDT worker
    from app.services.usdt_payment import get_usdt_order_worker
    get_usdt_order_worker().stop()

    logger.info("api_server_shutting_down")


# 创建 FastAPI 应用
app = FastAPI(
    title="UF Stock Assistant API",
    description="智能股票助手 Agent API",
    version=get_settings().version,
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = int((time.perf_counter() - start) * 1000)
    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration,
    )
    return response


# Agent Gateway 错误码 → HTTP 状态码映射
_AGENT_ERROR_STATUS = {
    "INVALID_TOKEN": 401,
    "TOKEN_NOT_FOUND": 401,
    "TOKEN_REVOKED": 401,
    "TOKEN_INACTIVE": 401,
    "TOKEN_EXPIRED": 401,
    "INSUFFICIENT_SCOPE": 403,
    "RATE_LIMITED": 429,
    "PAPER_ONLY": 403,
    "LIVE_TRADING_DISABLED": 403,
}


# 全局异常处理
@app.exception_handler(AssistantException)
async def assistant_exception_handler(request: Request, exc: AssistantException):
    logger.error(
        "business_error",
        path=request.url.path,
        code=exc.code,
        message=exc.message,
    )
    status_code = _AGENT_ERROR_STATUS.get(exc.code, 400)
    # Rate limit 返回 Retry-After 头
    headers = {}
    if exc.code == "RATE_LIMITED":
        headers["Retry-After"] = "60"
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "retriable": exc.details.get("retriable", False) if exc.details else False,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unexpected_error",
        path=request.url.path,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
            }
        },
    )


# 注册路由
app.include_router(chat.router, prefix="/api/v1", tags=["对话"])
app.include_router(stock.router, prefix="/api/v1", tags=["股票数据"])
app.include_router(market.router, prefix="/api/v1", tags=["市场数据"])
app.include_router(crypto.router, prefix="/api/v1", tags=["虚拟货币"])
app.include_router(trading.router, prefix="/api/v1", tags=["交易"])
app.include_router(strategy.router, prefix="/api/v1", tags=["策略"])
app.include_router(upload.router, prefix="/api/v1", tags=["文件上传"])
app.include_router(billing.router, prefix="/api/v1", tags=["计费"])
app.include_router(agent_router, prefix="/api", tags=["Agent Gateway"])


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": get_settings().version,
        "timestamp": time.time(),
    }


@app.get("/")
async def root():
    """API 根路径"""
    return {
        "name": "UF Stock Assistant API",
        "version": get_settings().version,
        "docs": "/docs",
    }
