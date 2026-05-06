"""
测试日志系统模块
"""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import structlog

from app.core.config import AppSettings
from app.core.logging import (
    get_logger,
    log_business,
    log_error,
    log_trading,
    setup_logging,
)


class TestSetupLogging:
    """测试日志配置"""

    def test_setup_creates_log_dir(self, tmp_path):
        """测试 setup_logging 创建日志目录"""
        log_dir = tmp_path / "test_logs"
        # 创建临时配置
        settings = AppSettings()
        with patch.object(settings.log, "dir", str(log_dir)):
            with patch("app.core.logging.get_settings", return_value=settings):
                setup_logging()
                assert log_dir.exists()

    def test_get_logger(self):
        """测试 get_logger 返回日志记录器"""
        setup_logging()
        logger = get_logger("test")
        # structlog.get_logger 返回的是 BoundLoggerLazyProxy，调用后才是 BoundLogger
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")

    def test_log_business(self, capsys):
        """测试业务日志记录"""
        setup_logging()
        log_business("test_event", symbol="000001", action="query")
        captured = capsys.readouterr()
        assert "test_event" in captured.out or "test_event" in captured.err

    def test_log_error(self, capsys):
        """测试错误日志记录"""
        setup_logging()
        log_error("test_error", message="something went wrong")
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "test_error" in output
        assert "something went wrong" in output

    def test_log_trading(self, capsys):
        """测试交易日志记录"""
        setup_logging()
        log_trading(
            "order_submitted",
            symbol="000001.SZ",
            side="buy",
            quantity=100,
            price=10.5,
        )
        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "order_submitted" in output
        assert "000001.SZ" in output
