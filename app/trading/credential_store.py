"""
UF Stock Assistant — 凭证加密存储
使用 Fernet 对称加密保护交易所 API Key/Secret
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.core.constants import MarketType
from app.core.exceptions import CredentialError
from app.core.logging import get_logger

from .models import TradingCredential, _uuid, _utcnow

logger = get_logger("app.trading.credential_store")

# 持久化密钥文件路径
_KEY_FILE = os.path.join(os.path.dirname(__file__), ".trading_key")

# 项目根目录（app/ 的父目录）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_key() -> str:
    """加载加密密钥（优先 .env，回退密钥文件，最后自动生成）"""
    key = ""

    # 1. 从项目根目录 .env 文件读取
    try:
        from dotenv import dotenv_values
        env_path = os.path.join(_PROJECT_ROOT, ".env")
        if os.path.exists(env_path):
            env_values = dotenv_values(env_path)
            key = env_values.get("TRADING_CREDENTIALS_KEY", "")
    except ImportError:
        pass

    # 2. 回退到环境变量
    if not key:
        key = os.environ.get("TRADING_CREDENTIALS_KEY", "")

    # 3. 从密钥文件读取
    if not key and os.path.exists(_KEY_FILE):
        with open(_KEY_FILE) as f:
            key = f.read().strip()

    # 4. 自动生成并持久化
    if not key:
        key = Fernet.generate_key().decode()
        with open(_KEY_FILE, "w") as f:
            f.write(key)
        logger.warning("auto_generated_encryption_key", key_file=_KEY_FILE)

    return key


def _get_fernet() -> Fernet:
    """获取 Fernet 实例（每次创建，确保一致性）"""
    key = _load_key()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_credential(plaintext: str) -> str:
    """加密凭证"""
    f = _get_fernet()
    result = f.encrypt(plaintext.encode()).decode()
    logger.debug("credential_encrypted", key_id=id(f))
    return result


def decrypt_credential(ciphertext: str) -> str:
    """解密凭证"""
    f = _get_fernet()
    try:
        result = f.decrypt(ciphertext.encode()).decode()
        logger.debug("credential_decrypted", key_id=id(f))
        return result
    except Exception as exc:
        logger.error("decrypt_failed", error=str(exc), error_type=type(exc).__name__, key_id=id(f), key_preview=_load_key()[:20])
        raise CredentialError(f"凭证解密失败: {exc}") from exc


def save_credential(
    db: Session,
    market: str,
    name: str,
    api_key: str,
    api_secret: str,
    passphrase: str | None = None,
    extra_config: dict | None = None,
) -> TradingCredential:
    """保存凭证（加密后存储）"""
    cred = TradingCredential(
        id=_uuid(),
        market=market,
        name=name,
        api_key_encrypted=encrypt_credential(api_key),
        api_secret_encrypted=encrypt_credential(api_secret),
        passphrase_encrypted=encrypt_credential(passphrase) if passphrase else None,
        extra_config=extra_config,
        is_active=True,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    logger.info("credential_saved", market=market, name=name, id=cred.id)
    return cred


def get_active_credential(db: Session, market: str) -> TradingCredential | None:
    """获取指定市场的活跃凭证"""
    return (
        db.query(TradingCredential)
        .filter(TradingCredential.market == market, TradingCredential.is_active == True)
        .first()
    )


def get_credential_decrypted(db: Session, credential_id: str) -> dict | None:
    """获取凭证并解密返回"""
    cred = db.query(TradingCredential).filter(TradingCredential.id == credential_id).first()
    if not cred:
        return None
    return {
        "id": cred.id,
        "market": cred.market,
        "name": cred.name,
        "api_key": decrypt_credential(cred.api_key_encrypted),
        "api_secret": decrypt_credential(cred.api_secret_encrypted),
        "passphrase": decrypt_credential(cred.passphrase_encrypted) if cred.passphrase_encrypted else None,
        "extra_config": cred.extra_config or {},
    }


def list_credentials(db: Session) -> list[dict]:
    """列出所有凭证（脱敏）"""
    creds = db.query(TradingCredential).order_by(TradingCredential.created_at.desc()).all()
    results = []
    for c in creds:
        api_key = decrypt_credential(c.api_key_encrypted)
        masked_key = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else "****"
        results.append({
            "id": c.id,
            "market": c.market,
            "name": c.name,
            "api_key_masked": masked_key,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return results


def update_credential(
    db: Session,
    credential_id: str,
    name: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    passphrase: str | None = None,
    extra_config: dict | None = None,
    is_active: bool | None = None,
) -> TradingCredential | None:
    """更新凭证"""
    cred = db.query(TradingCredential).filter(TradingCredential.id == credential_id).first()
    if not cred:
        return None

    if name is not None:
        cred.name = name
    if api_key is not None:
        cred.api_key_encrypted = encrypt_credential(api_key)
    if api_secret is not None:
        cred.api_secret_encrypted = encrypt_credential(api_secret)
    if passphrase is not None:
        cred.passphrase_encrypted = encrypt_credential(passphrase)
    if extra_config is not None:
        cred.extra_config = extra_config
    if is_active is not None:
        cred.is_active = is_active
    cred.updated_at = _utcnow()

    db.commit()
    db.refresh(cred)
    logger.info("credential_updated", id=credential_id)
    return cred


def delete_credential(db: Session, credential_id: str) -> bool:
    """删除凭证"""
    cred = db.query(TradingCredential).filter(TradingCredential.id == credential_id).first()
    if not cred:
        return False
    db.delete(cred)
    db.commit()
    logger.info("credential_deleted", id=credential_id)
    return True
