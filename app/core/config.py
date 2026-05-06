"""
UF Stock Assistant — 配置管理
基于 Pydantic Settings，支持 .env 文件加载
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogSettings(BaseSettings):
    """日志配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_LOG_", extra="ignore")
    
    level: str = Field(default="INFO", description="日志级别: DEBUG, INFO, WARNING, ERROR")
    dir: str = Field(default="logs", description="日志目录")
    json_format: bool = Field(default=True, description="是否使用 JSON 格式输出")
    max_bytes: int = Field(default=10 * 1024 * 1024, description="单个日志文件最大字节数")
    backup_count: int = Field(default=10, description="保留的日志文件数量")
    console_color: bool = Field(default=True, description="控制台是否彩色输出")


class DatabaseSettings(BaseSettings):
    """数据库配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_DATABASE_", extra="ignore")
    
    url: str = Field(default="sqlite:///data/assistant.db", description="数据库连接URL")
    echo: bool = Field(default=False, description="是否打印SQL语句")
    pool_size: int = Field(default=5, description="连接池大小")
    max_overflow: int = Field(default=10, description="连接池溢出大小")


class CacheSettings(BaseSettings):
    """缓存配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_CACHE_", extra="ignore")
    
    ttl: int = Field(default=300, description="缓存过期时间(秒)")
    max_size: int = Field(default=1000, description="缓存最大条目数")


class AppSettings(BaseSettings):
    """应用主配置"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="STOCK_ASSISTANT_",
        env_nested_delimiter="__",
    )
    
    # 项目基础
    project_name: str = Field(default="UF Stock Assistant", description="项目名称")
    version: str = Field(default="0.1.0", description="版本号")
    debug: bool = Field(default=False, description="调试模式")
    
    # LLM Provider 选择
    llm_provider: str = Field(default="kimi", description="默认LLM提供商")
    
    # 子配置
    log: LogSettings = Field(default_factory=LogSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    
    @property
    def log_dir_path(self) -> Path:
        """获取日志目录路径"""
        path = Path(self.log.dir)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def data_dir_path(self) -> Path:
        """获取数据目录路径"""
        path = Path("data")
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """获取配置单例（缓存）"""
    return AppSettings()


def reload_settings() -> AppSettings:
    """重新加载配置（用于热更新）"""
    get_settings.cache_clear()
    return get_settings()


# 便捷导出
settings = get_settings()
