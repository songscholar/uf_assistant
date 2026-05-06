"""
测试配置管理模块
"""

import os
from unittest.mock import patch

import pytest

from app.core.config import AppSettings, get_settings, reload_settings


class TestAppSettings:
    """测试应用配置"""

    def test_default_values(self):
        """测试默认值"""
        settings = AppSettings()
        assert settings.project_name == "UF Stock Assistant"
        assert settings.version == "0.1.0"
        assert settings.debug is False
        assert settings.llm_provider == "kimi"

    def test_log_settings_defaults(self):
        """测试日志配置默认值"""
        settings = AppSettings()
        assert settings.log.level == "INFO"
        assert settings.log.dir == "logs"
        assert settings.log.json_format is True
        assert settings.log.max_bytes == 10 * 1024 * 1024
        assert settings.log.backup_count == 10

    def test_database_settings_defaults(self):
        """测试数据库配置默认值"""
        settings = AppSettings()
        assert settings.database.url == "sqlite:///data/assistant.db"
        assert settings.database.echo is False

    def test_cache_settings_defaults(self):
        """测试缓存配置默认值"""
        settings = AppSettings()
        assert settings.cache.ttl == 300
        assert settings.cache.max_size == 1000

    def test_log_dir_path(self):
        """测试日志目录路径"""
        settings = AppSettings()
        path = settings.log_dir_path
        assert path.exists()
        assert path.name == "logs"

    def test_data_dir_path(self):
        """测试数据目录路径"""
        settings = AppSettings()
        path = settings.data_dir_path
        assert path.exists()
        assert path.name == "data"


class TestSettingsSingleton:
    """测试配置单例"""

    def test_singleton(self):
        """测试单例模式"""
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reload(self):
        """测试重新加载"""
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = reload_settings()
        assert s1 is not s2
        # 清理缓存避免影响其他测试
        get_settings.cache_clear()

    def test_env_override(self):
        """测试环境变量覆盖"""
        get_settings.cache_clear()
        with patch.dict(os.environ, {
            "STOCK_ASSISTANT_LLM_PROVIDER": "openai",
            "STOCK_ASSISTANT_DEBUG": "true",
        }, clear=False):
            settings = AppSettings()
            assert settings.llm_provider == "openai"
            assert settings.debug is True
        # 清理
        get_settings.cache_clear()
