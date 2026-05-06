"""
UF Stock Assistant — 企业级日志系统
支持 JSON 结构化输出、文件轮转、彩色控制台、分级日志
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from pathlib import Path
from typing import Any

import structlog

from .config import get_settings


def _add_exc_info(
    logger: logging.Logger | structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """如果 exc_info=True 存在但值为布尔值，替换为真实的异常信息"""
    exc_info = event_dict.get("exc_info")
    if exc_info is True:
        exc_info = sys.exc_info()
        if exc_info[0] is not None:
            event_dict["exc_info"] = traceback.format_exception(*exc_info)
        else:
            del event_dict["exc_info"]
    return event_dict


def _json_serializer(
    logger: logging.Logger | structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> str:
    """JSON 序列化处理器"""
    import json
    return json.dumps(event_dict, ensure_ascii=False, default=str)


def _console_renderer(
    logger: logging.Logger | structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> str:
    """控制台渲染器（彩色友好格式）"""
    timestamp = event_dict.pop("timestamp", "")
    level = event_dict.pop("level", "INFO")
    event = event_dict.pop("event", "")
    
    # 构建字段字符串
    fields = " ".join(f"{k}={v!r}" for k, v in event_dict.items())
    
    # 颜色映射
    color_map = {
        "debug": "\033[36m",      # cyan
        "info": "\033[32m",       # green
        "warning": "\033[33m",    # yellow
        "error": "\033[31m",      # red
        "critical": "\033[35m",   # magenta
    }
    reset = "\033[0m"
    
    level_lower = level.lower() if isinstance(level, str) else "info"
    color = color_map.get(level_lower, "")
    
    return f"{timestamp} [{color}{level}{reset}] {event}{' ' + fields if fields else ''}"


def setup_logging() -> None:
    """
    配置企业级日志系统
    - 控制台输出：彩色（开发）或纯文本（生产）
    - 文件输出：JSON 结构化，按大小轮转
    """
    app_settings = get_settings()
    log_settings = app_settings.log
    log_dir = app_settings.log_dir_path
    
    # 确保日志目录存在
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 标准库日志处理器 -----------------------------------------------------------
    
    # 文件处理器（JSON 格式，轮转）
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "assistant.log",
        maxBytes=log_settings.max_bytes,
        backupCount=log_settings.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, log_settings.level.upper(), logging.INFO))
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_settings.level.upper(), logging.INFO))
    
    # 格式化器
    if log_settings.json_format:
        file_formatter = logging.Formatter("%(message)s")
    else:
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
    
    file_handler.setFormatter(file_formatter)
    
    if log_settings.console_color:
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
    
    console_handler.setFormatter(console_formatter)
    
    # 根日志配置
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers = []
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 降低第三方库日志级别
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    # structlog 配置 ------------------------------------------------------------
    
    shared_processors: list[Any] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
        _add_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    if log_settings.json:
        # JSON 模式：文件 + 控制台都输出 JSON
        structlog.configure(
            processors=shared_processors + [_json_serializer],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    else:
        # 非 JSON 模式：控制台彩色，文件纯文本
        structlog.configure(
            processors=shared_processors + [structlog.dev.ConsoleRenderer(colors=log_settings.console_color)],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    # 记录日志系统启动事件
    logger = structlog.get_logger("app.core.logging")
    logger.info(
        "logging_system_initialized",
        log_level=log_settings.level,
        log_dir=str(log_dir),
        json_format=log_settings.json_format,
        max_bytes=log_settings.max_bytes,
        backup_count=log_settings.backup_count,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """获取结构化日志记录器"""
    return structlog.get_logger(name)


# 业务日志快捷方法
def log_business(event: str, **kwargs: Any) -> None:
    """记录业务事件"""
    logger = structlog.get_logger("app.business")
    logger.info(event, **kwargs)


def log_error(event: str, message: str, exc: Exception | None = None, **kwargs: Any) -> None:
    """记录错误事件"""
    logger = structlog.get_logger("app.error")
    extra = {"error_message": message, **kwargs}
    if exc:
        extra["exc_type"] = type(exc).__name__
        extra["exc_str"] = str(exc)
    logger.error(event, **extra)


def log_trading(
    action: str,
    symbol: str,
    side: str | None = None,
    quantity: float | None = None,
    price: float | None = None,
    status: str | None = None,
    **kwargs: Any,
) -> None:
    """记录交易事件"""
    logger = structlog.get_logger("app.trading")
    logger.info(
        action,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        status=status,
        **kwargs,
    )
