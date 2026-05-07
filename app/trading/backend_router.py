"""
UF Stock Assistant — 交易后端路由器
根据市场类型和交易模式路由到对应后端
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.constants import MarketType, TradingMode
from app.core.exceptions import CredentialError
from app.core.logging import get_logger

from .backends import ExchangeBackend
from .backends.mock_backend import MockBackend
from .credential_store import get_active_credential, get_credential_decrypted

logger = get_logger("app.trading.backend_router")


class BackendRouter:
    """根据市场和模式路由到对应交易后端"""

    def __init__(self, db: Session, mode: str = TradingMode.MOCK) -> None:
        self.db = db
        self.mode = mode
        self._backends: dict[str, ExchangeBackend] = {}

    async def get_backend(self, market: str) -> ExchangeBackend:
        """获取交易后端

        - mock 模式：返回 MockBackend（不需要凭证）
        - live 模式：从 DB 获取凭证，连接真实交易所
        """
        cache_key = f"{self.mode}:{market}"

        if cache_key in self._backends:
            return self._backends[cache_key]

        if self.mode == TradingMode.MOCK:
            backend = MockBackend()
            await backend.connect()
            self._backends[cache_key] = backend
            return backend

        # Live 模式 — 需要凭证
        cred = get_active_credential(self.db, market)
        if not cred:
            raise CredentialError(f"未找到 {market} 的交易凭证，请先添加凭证")

        decrypted = get_credential_decrypted(self.db, cred.id)
        if not decrypted:
            raise CredentialError("凭证解密失败")

        backend = self._create_backend(market)
        await backend.connect(decrypted)
        self._backends[cache_key] = backend

        logger.info("backend_connected", market=market, mode=self.mode)
        return backend

    def _create_backend(self, market: str) -> ExchangeBackend:
        """根据市场类型创建对应后端实例"""
        if market == MarketType.CRYPTO:
            from .backends.crypto_backend import CryptoBackend
            return CryptoBackend()
        elif market == MarketType.A_SHARE:
            from .backends.a_share_backend import AShareBackend
            return AShareBackend()
        elif market == MarketType.US_STOCK:
            from .backends.us_stock_backend import USStockBackend
            return USStockBackend()
        else:
            raise ValueError(f"不支持的市场类型: {market}")

    def get_mode(self) -> str:
        return self.mode

    def set_mode(self, mode: str) -> None:
        """切换交易模式（清空后端缓存）"""
        if mode != self.mode:
            self._backends.clear()
            self.mode = mode
            logger.info("trading_mode_changed", mode=mode)
