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
    deployment_mode: str = Field(default="self", description="部署模式: self / saas / hosted / multitenant")


class BillingSettings(BaseSettings):
    """计费与商业化配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_BILLING_", extra="ignore")
    
    enabled: bool = Field(default=False, description="是否启用计费系统")
    cost_ai_analysis: int = Field(default=10, description="AI 分析单次消耗积分")
    cost_ai_code_gen: int = Field(default=30, description="AI 代码生成单次消耗积分")
    credits_register_bonus: int = Field(default=100, description="注册赠送积分")
    credits_referral_bonus: int = Field(default=50, description="邀请赠送积分")
    credits_expiry_days: int = Field(default=0, description="积分有效期（天），0 表示永不过期")
    admin_api_key: str = Field(default="", description="管理接口 API Key（X-Admin-Key 校验用）")


class MembershipSettings(BaseSettings):
    """会员套餐配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_MEMBERSHIP_", extra="ignore")
    
    monthly_price_usd: float = Field(default=19.9, description="月付价格(USD)")
    monthly_credits: int = Field(default=500, description="月付赠送积分")
    yearly_price_usd: float = Field(default=199.0, description="年付价格(USD)")
    yearly_credits: int = Field(default=8000, description="年付赠送积分")
    lifetime_price_usd: float = Field(default=499.0, description="终身价格(USD)")
    lifetime_monthly_credits: int = Field(default=800, description="终身会员每月积分")


class ReflectionSettings(BaseSettings):
    """AI 反射与校准配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_REFLECTION_", extra="ignore")
    
    enabled: bool = Field(default=True, description="是否启用反射 Worker")
    interval_seconds: int = Field(default=86400, description="反射 Worker 执行间隔(秒)")
    min_age_days: int = Field(default=7, description="验证最小历史天数")
    validate_limit: int = Field(default=200, description="单次验证最大条数")
    calibration_enabled: bool = Field(default=True, description="是否启用离线 AI 校准")
    calibration_markets: str = Field(default="Crypto", description="需要校准的市场，逗号分隔")
    calibration_lookback_days: int = Field(default=30, description="校准回溯天数")
    calibration_min_samples: int = Field(default=80, description="校准最小样本数")


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
    debug_reconcile_log: str = Field(default="info", description="USDT 对账日志级别: none/error/warn/info/debug")


class CnPaymentSettings(BaseSettings):
    """人民币支付配置（支付宝 / 微信 / 模拟支付）"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_CN_PAY_", extra="ignore")

    mock_enabled: bool = Field(default=False, description="是否启用模拟支付（开发测试用）")
    order_expire_minutes: int = Field(default=30, description="订单过期时间(分钟)")
    # 支付宝
    alipay_enabled: bool = Field(default=False, description="是否启用支付宝")
    alipay_app_id: str = Field(default="", description="支付宝 App ID")
    alipay_app_private_key: str = Field(default="", description="支付宝应用私钥")
    alipay_public_key: str = Field(default="", description="支付宝公钥")
    alipay_sign_type: str = Field(default="RSA2", description="签名类型: RSA2")
    alipay_gateway: str = Field(default="https://openapi.alipay.com/gateway.do", description="支付宝网关")
    alipay_sandbox: bool = Field(default=True, description="是否使用支付宝沙箱环境")
    # 微信支付
    wechat_enabled: bool = Field(default=False, description="是否启用微信支付")
    wechat_mch_id: str = Field(default="", description="微信支付商户号")
    wechat_app_id: str = Field(default="", description="微信支付 App ID")
    wechat_api_key: str = Field(default="", description="微信支付 API v3 密钥")
    wechat_api_key_serial: str = Field(default="", description="微信支付 API 证书序列号")
    wechat_api_cert_path: str = Field(default="", description="微信支付 API 证书路径")
    wechat_api_key_path: str = Field(default="", description="微信支付 API 私钥路径")
    wechat_notify_url: str = Field(default="", description="微信支付回调地址")


class LocalBrokerSettings(BaseSettings):
    """本地桌面券商配置（IBKR / MT5）"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_LOCAL_BROKER_", extra="ignore")

    allowed: bool = Field(default=False, description="是否允许使用本地桌面券商（TWS/MT5）")
    ibkr_default_host: str = Field(default="127.0.0.1", description="IBKR TWS 默认主机")
    ibkr_default_port: int = Field(default=7497, description="IBKR TWS 默认端口")
    ibkr_default_client_id: int = Field(default=1, description="IBKR TWS 默认 Client ID")
    ibkr_readonly: bool = Field(default=False, description="IBKR 只读模式")


class AuthSettings(BaseSettings):
    """用户认证配置"""
    model_config = SettingsConfigDict(env_prefix="STOCK_ASSISTANT_AUTH_", extra="ignore")

    secret_key: str = Field(default="uf-assistant-secret-change-me", description="JWT 签名密钥")
    jwt_algorithm: str = Field(default="HS256", description="JWT 算法")
    jwt_expire_days: int = Field(default=7, description="JWT 有效期(天)")
    single_user_mode: bool = Field(default=False, description="单用户模式（跳过数据库认证）")
    admin_user: str = Field(default="admin", description="单用户模式 / 默认管理员用户名")
    admin_password: str = Field(default="123456", description="单用户模式 / 默认管理员密码")
    registration_enabled: bool = Field(default=True, description="是否开放注册")
    turnstile_site_key: str = Field(default="", description="Cloudflare Turnstile 站点密钥")
    turnstile_secret_key: str = Field(default="", description="Cloudflare Turnstile 密钥")
    # OAuth
    google_client_id: str = Field(default="", description="Google OAuth Client ID")
    google_client_secret: str = Field(default="", description="Google OAuth Client Secret")
    github_client_id: str = Field(default="", description="GitHub OAuth Client ID")
    github_client_secret: str = Field(default="", description="GitHub OAuth Client Secret")
    oauth_state_ttl_minutes: int = Field(default=20, description="OAuth state 有效期(分钟)")
    # Email
    smtp_host: str = Field(default="", description="SMTP 服务器地址")
    smtp_port: int = Field(default=587, description="SMTP 端口")
    smtp_user: str = Field(default="", description="SMTP 用户名")
    smtp_password: str = Field(default="", description="SMTP 密码")
    smtp_from: str = Field(default="", description="发件人地址")
    smtp_use_tls: bool = Field(default=True, description="SMTP 是否使用 TLS")
    email_code_expire_minutes: int = Field(default=10, description="邮箱验证码有效期(分钟)")
    # Resend (第三方邮件服务，优先于 SMTP)
    resend_api_key: str = Field(default="", description="Resend API Key")
    resend_from: str = Field(default="noreply@uf-assistant.dev", description="Resend 发件人地址")
    # Credits
    credits_register_bonus: float = Field(default=100, description="注册赠送积分")
    credits_referral_bonus: float = Field(default=50, description="邀请赠送积分")


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
    
    # 数据源配置
    tushare_token: str = Field(default="", description="Tushare Pro API Token")
    
    # 子配置
    log: LogSettings = Field(default_factory=LogSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    billing: BillingSettings = Field(default_factory=BillingSettings)
    membership: MembershipSettings = Field(default_factory=MembershipSettings)
    usdt: UsdtPaymentSettings = Field(default_factory=UsdtPaymentSettings)
    reflection: ReflectionSettings = Field(default_factory=ReflectionSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    cn_pay: CnPaymentSettings = Field(default_factory=CnPaymentSettings)
    local_broker: LocalBrokerSettings = Field(default_factory=LocalBrokerSettings)
    
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
