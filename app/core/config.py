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


class AgentSettings(BaseSettings):
    """Agent Gateway 配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_AGENT_", extra="ignore")
    
    live_trading_enabled: bool = Field(default=False, description="是否允许 Agent 实盘交易")
    token_ttl_hours: int = Field(default=720, description="Agent Token 有效期(小时)，默认30天")
    audit_log_retention_days: int = Field(default=90, description="审计日志保留天数")
    sse_heartbeat_interval: int = Field(default=5, description="SSE 心跳间隔(秒)")


class BillingSettings(BaseSettings):
    """计费与商业化配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_BILLING_", extra="ignore")
    
    enabled: bool = Field(default=False, description="是否启用计费系统")
    cost_ai_analysis: int = Field(default=10, description="AI 分析单次消耗积分")
    cost_ai_code_gen: int = Field(default=30, description="AI 代码生成单次消耗积分")
    credits_register_bonus: int = Field(default=100, description="注册赠送积分")
    credits_referral_bonus: int = Field(default=50, description="邀请赠送积分")


class MembershipSettings(BaseSettings):
    """会员套餐配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_MEMBERSHIP_", extra="ignore")
    
    monthly_price_usd: float = Field(default=19.9, description="月付价格(USD)")
    monthly_credits: int = Field(default=500, description="月付赠送积分")
    yearly_price_usd: float = Field(default=199.0, description="年付价格(USD)")
    yearly_credits: int = Field(default=8000, description="年付赠送积分")
    lifetime_price_usd: float = Field(default=499.0, description="终身价格(USD)")
    lifetime_monthly_credits: int = Field(default=800, description="终身会员每月积分")


class UsdtPaymentSettings(BaseSettings):
    """USDT-TRC20 支付配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_USDT_", extra="ignore")
    
    pay_enabled: bool = Field(default=False, description="是否启用 USDT 支付")
    chain: str = Field(default="TRC20", description="链类型")
    trc20_xpub: str = Field(default="", description="TRC20 观察钱包 xpub")
    trc20_contract: str = Field(default="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", description="USDT TRC20 合约地址")
    trongrid_base_url: str = Field(default="https://api.trongrid.io", description="TronGrid API 地址")
    trongrid_api_key: str = Field(default="", description="TronGrid API Key")
    confirm_seconds: int = Field(default=30, description="链上确认等待秒数")
    order_expire_minutes: int = Field(default=30, description="订单过期时间(分钟)")
    worker_poll_interval: int = Field(default=30, description="后台轮询间隔(秒)")


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
    billing: BillingSettings = Field(default_factory=BillingSettings)
    membership: MembershipSettings = Field(default_factory=MembershipSettings)
    usdt: UsdtPaymentSettings = Field(default_factory=UsdtPaymentSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    
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
