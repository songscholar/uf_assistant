"""
UF Stock Assistant — 计费服务
积分余额、功能扣费、会员状态与套餐发放
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.exceptions import BillingError, InsufficientCreditsError
from app.core.logging import get_logger
from app.data.billing_models import (
    Base,
    CreditsLogModel,
    UserCreditsModel,
)

logger = get_logger("app.services.billing")

BILLING_CONFIG_PREFIX = "STOCK_ASSISTANT_BILLING_"

DEFAULT_BILLING_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "cost_ai_analysis": 10,
    "cost_ai_code_gen": 30,
}

FEATURE_NAMES: Dict[str, str] = {
    "ai_analysis": "AI 分析",
    "ai_code_gen": "AI 代码生成",
}


class BillingStore:
    """计费数据库连接管理（复用对话存储的数据库 URL）"""

    _engine = None
    _session_factory = None

    @classmethod
    def get_engine(cls):
        if cls._engine is None:
            cls._engine = create_engine(get_settings().database.url, echo=False, future=True)
        return cls._engine

    @classmethod
    def get_session(cls):
        if cls._session_factory is None:
            cls._session_factory = sessionmaker(bind=cls.get_engine())
        return cls._session_factory()

    @classmethod
    def ensure_tables(cls):
        Base.metadata.create_all(cls.get_engine())


class BillingService:
    """计费服务类"""

    def __init__(self) -> None:
        self._config_cache: Optional[Dict[str, Any]] = None
        self._config_cache_time: float = 0.0
        self._cache_ttl: int = 60
        BillingStore.ensure_tables()

    def get_billing_config(self) -> Dict[str, Any]:
        """获取计费配置（合并 .env 与默认值）"""
        now = time.time()
        if self._config_cache and (now - self._config_cache_time) < self._cache_ttl:
            return self._config_cache

        config: Dict[str, Any] = {}
        for key, default_value in DEFAULT_BILLING_CONFIG.items():
            env_key = f"{BILLING_CONFIG_PREFIX}{key.upper()}"
            value = os.getenv(env_key)

            if value is None or value == "":
                config[key] = default_value
            elif isinstance(default_value, bool):
                config[key] = str(value).lower() in ("true", "1", "yes")
            elif isinstance(default_value, int):
                try:
                    config[key] = int(value)
                except (ValueError, TypeError):
                    config[key] = default_value
            else:
                config[key] = value

        self._config_cache = config
        self._config_cache_time = now
        return config

    def clear_config_cache(self) -> None:
        """清除配置缓存"""
        self._config_cache = None
        self._config_cache_time = 0

    def is_billing_enabled(self) -> bool:
        """检查是否启用计费"""
        config = self.get_billing_config()
        return config.get("enabled", False)

    def get_feature_cost(self, feature: str) -> int:
        """获取指定功能的积分消耗，0 表示免费"""
        config = self.get_billing_config()
        cost_key = f"cost_{feature}"
        return config.get(cost_key, 0)

    # ------------------------------------------------------------------
    # 积分管理
    # ------------------------------------------------------------------

    def get_user_credits(self, user_id: str) -> Decimal:
        """获取用户积分余额"""
        try:
            session = BillingStore.get_session()
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            session.close()
            if row:
                return Decimal(str(row.credits or 0))
            return Decimal("0")
        except Exception as e:
            logger.error(f"get_user_credits failed: {e}")
            return Decimal("0")

    def add_credits(
        self,
        user_id: str,
        amount: int,
        action: str = "recharge",
        remark: str = "",
        reference_id: str = "",
    ) -> Tuple[bool, str]:
        """增加用户积分"""
        if amount <= 0:
            return False, "amount_must_be_positive"

        session = BillingStore.get_session()
        try:
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            if not row:
                row = UserCreditsModel(user_id=user_id, credits=Decimal("0"))
                session.add(row)
                session.flush()

            old_credits = Decimal(str(row.credits or 0))
            new_balance = old_credits + Decimal(str(amount))
            row.credits = new_balance
            row.updated_at = datetime.now(timezone.utc)

            log = CreditsLogModel(
                user_id=user_id,
                action=action,
                amount=amount,
                balance_after=new_balance,
                remark=remark,
                reference_id=reference_id,
            )
            session.add(log)
            session.commit()

            logger.info(f"User {user_id} added {amount} credits ({action}), balance: {new_balance}")
            return True, str(new_balance)
        except Exception as e:
            session.rollback()
            logger.error(f"add_credits failed: {e}")
            return False, str(e)
        finally:
            session.close()

    def check_and_consume(
        self,
        user_id: str,
        feature: str,
        reference_id: str = "",
    ) -> Tuple[bool, str]:
        """检查并消耗积分"""
        if not self.is_billing_enabled():
            return True, "billing_disabled"

        cost = self.get_feature_cost(feature)
        if cost <= 0:
            return True, "free_feature"

        credits = self.get_user_credits(user_id)
        if credits < cost:
            return False, f"insufficient_credits:{credits}:{cost}"

        session = BillingStore.get_session()
        try:
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            if not row:
                session.close()
                return False, f"insufficient_credits:0:{cost}"

            old_credits = Decimal(str(row.credits or 0))
            new_balance = old_credits - Decimal(str(cost))
            row.credits = new_balance
            row.updated_at = datetime.now(timezone.utc)

            feature_name = FEATURE_NAMES.get(feature, feature)
            log = CreditsLogModel(
                user_id=user_id,
                action="consume",
                amount=-cost,
                balance_after=new_balance,
                feature=feature,
                reference_id=reference_id,
                remark=f"Consume: {feature_name}",
            )
            session.add(log)
            session.commit()

            logger.info(f"User {user_id} consumed {cost} credits for {feature}, balance: {new_balance}")
            return True, "consumed"
        except Exception as e:
            session.rollback()
            logger.error(f"check_and_consume failed: {e}")
            return False, f"error:{str(e)}"
        finally:
            session.close()

    def set_credits(
        self,
        user_id: str,
        amount: int,
        remark: str = "",
    ) -> Tuple[bool, str]:
        """设置用户积分（管理员直接设置）"""
        if amount < 0:
            return False, "amount_cannot_be_negative"

        session = BillingStore.get_session()
        try:
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            if not row:
                old_credits = Decimal("0")
                row = UserCreditsModel(user_id=user_id, credits=Decimal(str(amount)))
                session.add(row)
            else:
                old_credits = Decimal(str(row.credits or 0))
                row.credits = Decimal(str(amount))
                row.updated_at = datetime.now(timezone.utc)

            diff = Decimal(str(amount)) - old_credits
            log = CreditsLogModel(
                user_id=user_id,
                action="admin_adjust",
                amount=float(diff),
                balance_after=Decimal(str(amount)),
                remark=remark or f"Admin adjust: {old_credits} -> {amount}",
            )
            session.add(log)
            session.commit()

            logger.info(f"User {user_id} credits set to {amount}")
            return True, str(amount)
        except Exception as e:
            session.rollback()
            logger.error(f"set_credits failed: {e}")
            return False, str(e)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # VIP / 会员
    # ------------------------------------------------------------------

    def get_user_vip_status(self, user_id: str) -> Tuple[bool, Optional[datetime]]:
        """获取用户 VIP 状态"""
        try:
            session = BillingStore.get_session()
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            session.close()

            if not row or not row.vip_expires_at:
                return False, None

            expires_at = row.vip_expires_at
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

            now = datetime.now(timezone.utc)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            return expires_at > now, expires_at
        except Exception as e:
            logger.error(f"get_user_vip_status failed: {e}")
            return False, None

    def get_membership_plans(self) -> Dict[str, Any]:
        """获取会员套餐配置"""
        settings = get_settings().membership
        return {
            "monthly": {
                "plan": "monthly",
                "price_usd": settings.monthly_price_usd,
                "credits_once": settings.monthly_credits,
                "duration_days": 30,
            },
            "yearly": {
                "plan": "yearly",
                "price_usd": settings.yearly_price_usd,
                "credits_once": settings.yearly_credits,
                "duration_days": 365,
            },
            "lifetime": {
                "plan": "lifetime",
                "price_usd": settings.lifetime_price_usd,
                "credits_monthly": settings.lifetime_monthly_credits,
            },
        }

    def purchase_membership(
        self,
        user_id: str,
        plan: str,
        *,
        fulfillment_ref: str = "",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """激活会员（VIP 日期 + 赠送积分）"""
        plan = (plan or "").strip().lower()
        plans = self.get_membership_plans()
        if plan not in plans:
            return False, "invalid_plan", {}

        session = BillingStore.get_session()
        try:
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            if not row:
                row = UserCreditsModel(user_id=user_id, credits=Decimal("0"))
                session.add(row)
                session.flush()

            now = datetime.now(timezone.utc)
            current_expires = row.vip_expires_at
            if isinstance(current_expires, str) and current_expires:
                try:
                    current_expires = datetime.fromisoformat(current_expires.replace("Z", "+00:00"))
                except Exception:
                    current_expires = None
            if current_expires and current_expires.tzinfo is None:
                current_expires = current_expires.replace(tzinfo=timezone.utc)

            base_time = current_expires if (current_expires and current_expires > now) else now

            vip_expires_at: Optional[datetime] = None
            vip_is_lifetime = False

            if plan in ("monthly", "yearly"):
                days = int(plans[plan].get("duration_days") or (30 if plan == "monthly" else 365))
                vip_expires_at = base_time + timedelta(days=days)
            else:
                vip_expires_at = now + timedelta(days=365 * 100)
                vip_is_lifetime = True

            row.vip_expires_at = vip_expires_at
            row.vip_plan = plan
            row.vip_is_lifetime = vip_is_lifetime
            row.updated_at = now

            order_ref = fulfillment_ref or f"billing:{user_id}:{int(now.timestamp())}"

            if plan in ("monthly", "yearly"):
                credits_once = int(plans[plan].get("credits_once") or 0)
                if credits_once > 0:
                    old_credits = Decimal(str(row.credits or 0))
                    new_balance = old_credits + Decimal(str(credits_once))
                    row.credits = new_balance

                    log = CreditsLogModel(
                        user_id=user_id,
                        action="membership_bonus",
                        amount=credits_once,
                        balance_after=new_balance,
                        remark=f"Membership bonus ({plan})",
                        reference_id=order_ref,
                    )
                    session.add(log)
            else:
                monthly_credits = int(plans["lifetime"].get("credits_monthly") or 0)
                if monthly_credits > 0:
                    old_credits = Decimal(str(row.credits or 0))
                    new_balance = old_credits + Decimal(str(monthly_credits))
                    row.credits = new_balance

                    log = CreditsLogModel(
                        user_id=user_id,
                        action="membership_monthly",
                        amount=monthly_credits,
                        balance_after=new_balance,
                        remark="Lifetime membership monthly credits",
                        reference_id=order_ref,
                    )
                    session.add(log)
                row.vip_monthly_credits_last_grant = now

            # VIP 日志
            audit_log = CreditsLogModel(
                user_id=user_id,
                action="membership_purchase",
                amount=0,
                balance_after=row.credits,
                remark=f"Membership purchased: {plan}",
                reference_id=order_ref,
            )
            session.add(audit_log)
            session.commit()

            return True, "success", {
                "plan": plan,
                "vip_expires_at": vip_expires_at.isoformat() if vip_expires_at else None,
            }
        except Exception as e:
            session.rollback()
            logger.error(f"purchase_membership failed: {e}", exc_info=True)
            return False, f"error:{str(e)}", {}
        finally:
            session.close()

    def set_vip(
        self,
        user_id: str,
        expires_at: Optional[datetime],
        remark: str = "",
    ) -> Tuple[bool, str]:
        """设置用户 VIP 状态"""
        session = BillingStore.get_session()
        try:
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            if not row:
                row = UserCreditsModel(user_id=user_id, credits=Decimal("0"))
                session.add(row)
                session.flush()

            row.vip_expires_at = expires_at
            row.updated_at = datetime.now(timezone.utc)

            action = "vip_grant" if expires_at else "vip_revoke"
            log_remark = remark or (f"VIP granted until {expires_at}" if expires_at else "VIP revoked")

            audit = CreditsLogModel(
                user_id=user_id,
                action=action,
                amount=0,
                balance_after=row.credits,
                remark=log_remark,
            )
            session.add(audit)
            session.commit()

            logger.info(f"User {user_id} VIP set to {expires_at}")
            return True, "success"
        except Exception as e:
            session.rollback()
            logger.error(f"set_vip failed: {e}")
            return False, str(e)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # 日志查询
    # ------------------------------------------------------------------

    def get_credits_log(self, user_id: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取用户积分变动日志"""
        offset = (page - 1) * page_size
        session = BillingStore.get_session()
        try:
            total = session.query(CreditsLogModel).filter_by(user_id=user_id).count()
            rows = (
                session.query(CreditsLogModel)
                .filter_by(user_id=user_id)
                .order_by(CreditsLogModel.created_at.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )

            logs = []
            for r in rows:
                dt = r.created_at
                created_at_str = None
                if dt:
                    if getattr(dt, "tzinfo", None) is not None:
                        created_at_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
                    else:
                        created_at_str = dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
                logs.append({
                    "id": r.id,
                    "action": r.action,
                    "amount": float(r.amount),
                    "balance_after": float(r.balance_after),
                    "feature": r.feature,
                    "reference_id": r.reference_id,
                    "remark": r.remark,
                    "created_at": created_at_str,
                })

            return {
                "items": logs,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            }
        except Exception as e:
            logger.error(f"get_credits_log failed: {e}")
            return {"items": [], "total": 0, "page": 1, "page_size": page_size, "total_pages": 0}
        finally:
            session.close()

    def get_user_billing_info(self, user_id: str) -> Dict[str, Any]:
        """获取用户计费与会员信息快照"""
        credits = self.get_user_credits(user_id)
        is_vip, vip_expires_at = self.get_user_vip_status(user_id)
        config = self.get_billing_config()

        return {
            "credits": float(credits),
            "is_vip": is_vip,
            "vip_expires_at": vip_expires_at.isoformat() if vip_expires_at else None,
            "billing_enabled": config.get("enabled", False),
            "feature_costs": {
                "ai_analysis": config.get("cost_ai_analysis", 0),
                "ai_code_gen": config.get("cost_ai_code_gen", 0),
            },
        }


# 全局单例
_billing_service: Optional[BillingService] = None


def get_billing_service() -> BillingService:
    """获取计费服务单例"""
    global _billing_service
    if _billing_service is None:
        _billing_service = BillingService()
    return _billing_service
