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

from .routers import chat, crypto, market, stock, strategy, trading, upload

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

    yield

    # 关闭
    stop_background_refresh()
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass
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


# 全局异常处理
@app.exception_handler(AssistantException)
async def assistant_exception_handler(request: Request, exc: AssistantException):
    logger.error(
        "business_error",
        path=request.url.path,
        code=exc.code,
        message=exc.message,
    )
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
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
