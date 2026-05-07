"""
UF Stock Assistant — Exchange execution helpers
完全复刻 QuantDinger 设计，适配 UF 凭据系统

提供：
  - resolve_exchange_config(): 凭据解析（支持 credential_id 引用 + 覆盖）
  - load_strategy_configs(): 从 DB 加载策略执行所需配置
  - safe_exchange_config_for_log(): 安全日志脱敏
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.strategies.trading_executor import get_strategy_db_session

logger = get_logger("app.strategies.exchange_execution")


def _safe_json_loads(value: Any, default: Any) -> Any:
    """安全 JSON 解析"""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return default
    s = value.strip()
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def mask_secret(s: str, keep: int = 4) -> str:
    """Return a masked representation of a secret for safe logs."""
    if not s:
        return ""
    s = str(s)
    if len(s) <= keep * 2:
        return s[: max(1, keep)] + "***"
    return f"{s[:keep]}...{s[-keep:]}"


def safe_exchange_config_for_log(cfg: dict[str, Any]) -> dict[str, Any]:
    """脱敏 exchange_config，用于日志输出"""
    if not isinstance(cfg, dict):
        return {}
    out = dict(cfg)
    for k in ("api_key", "secret_key", "passphrase", "apiKey", "secret", "password", "api_secret"):
        if k in out and out.get(k):
            out[k] = mask_secret(str(out.get(k)))
    return out


def load_strategy_configs(strategy_id: str) -> dict[str, Any]:
    """Load strategy config fields needed for live execution."""
    from app.strategies.models import StrategyModel

    session = get_strategy_db_session()
    try:
        row = session.query(StrategyModel).filter_by(id=str(strategy_id)).first()
        if row is None:
            return {}

        exchange_config = _safe_json_loads(row.exchange_config, {})
        trading_config = _safe_json_loads(row.trading_config, {})

        market_type = (row.market_type or exchange_config.get("market_type") or "swap").strip()
        leverage = float(
            row.leverage or trading_config.get("leverage") or exchange_config.get("leverage") or 1.0
        )
        execution_mode = (row.execution_mode or "signal").strip().lower()
        market_category = (row.market_category or "Crypto").strip()
        user_id = str(row.user_id or "default")

        return {
            "strategy_id": str(strategy_id),
            "user_id": user_id,
            "exchange_config": exchange_config if isinstance(exchange_config, dict) else {},
            "trading_config": trading_config if isinstance(trading_config, dict) else {},
            "market_type": market_type,
            "leverage": leverage,
            "execution_mode": execution_mode,
            "market_category": market_category,
        }
    finally:
        session.close()


def _load_credential_config(credential_id: str, user_id: str = "default") -> dict[str, Any]:
    """Load credential from UF credential store (decrypted)."""
    try:
        from app.trading.models import get_db_session
        from app.trading.credential_store import get_credential_decrypted

        db = get_db_session()
        try:
            cred = get_credential_decrypted(db, credential_id)
            if not cred:
                logger.warning(f"credential_not_found", credential_id=credential_id)
                return {}
            return {
                "api_key": cred.get("api_key", ""),
                "secret_key": cred.get("api_secret", ""),
                "passphrase": cred.get("passphrase", ""),
                "exchange_id": (cred.get("extra_config") or {}).get("exchange", ""),
            }
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to load credential_id={credential_id}: {exc}")
        return {}


def resolve_exchange_config(exchange_config: dict[str, Any], user_id: str = "default") -> dict[str, Any]:
    """
    Resolve exchange config.

    Supports:
    - direct inline config: {exchange_id, api_key, secret_key, passphrase?}
    - credential reference: {credential_id: "uuid", ...overrides}
    """
    if not isinstance(exchange_config, dict):
        return {}

    merged: dict[str, Any] = {}
    credential_id = exchange_config.get("credential_id") or exchange_config.get("credentials_id")
    try:
        if credential_id:
            base = _load_credential_config(str(credential_id), user_id=user_id)
            if isinstance(base, dict):
                merged.update(base)
    except Exception as exc:
        logger.warning(f"Failed to load credential_id={credential_id}: {exc}")

    # Overlay strategy-level settings (non-empty wins)
    for k, v in exchange_config.items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        merged[k] = v

    return merged
