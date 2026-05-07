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

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.exceptions import BillingError, InsufficientCreditsError
from app.core.logging import get_logger
from app.data.billing_models import (
    Base,
    CreditsLogModel,
    MembershipOrderModel,
    UserCreditsModel,
    UsdtOrderModel,
)

logger = get_logger("app.services.billing")

BILLING_CONFIG_PREFIX = "STOCK_ASSISTANT_BILLING_"

DEFAULT_BILLING_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "cost_ai_analysis": 10,
    "cost_ai_code_gen": 30,
    "credits_register_bonus": 0,
    "credits_referral_bonus": 0,
    "credits_expiry_days": 0,
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
        """获取用户积分余额（新用户自动创建记录并赠送注册积分；过期积分自动清零）"""
        try:
            session = BillingStore.get_session()
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            if row:
                # 检查积分是否过期
                self._expire_credits_if_due(session, row)
                session.close()
                return Decimal(str(row.credits or 0))

            # 新用户：创建记录并赠送注册积分
            bonus = self.get_billing_config().get("credits_register_bonus", 0)
            new_row = UserCreditsModel(user_id=user_id, credits=Decimal(str(bonus)))
            session.add(new_row)
            session.commit()

            if bonus > 0:
                log = CreditsLogModel(
                    user_id=user_id,
                    action="register_bonus",
                    amount=bonus,
                    balance_after=bonus,
                    remark="Register bonus",
                )
                session.add(log)
                session.commit()
                logger.info(f"User {user_id} registered with {bonus} bonus credits")

            session.close()
            return Decimal(str(bonus))
        except Exception as e:
            logger.error(f"get_user_credits failed: {e}")
            return Decimal("0")

    def _expire_credits_if_due(self, session, row: UserCreditsModel) -> None:
        """检查并处理积分过期（内部方法，需在 session 内调用）"""
        expiry = row.credits_expires_at
        if expiry is None:
            return
        if isinstance(expiry, str):
            try:
                expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            except Exception:
                return
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        if expiry > now:
            return

        old_credits = Decimal(str(row.credits or 0))
        if old_credits <= 0:
            return

        row.credits = Decimal("0")
        row.updated_at = now
        log = CreditsLogModel(
            user_id=row.user_id,
            action="expired",
            amount=-float(old_credits),
            balance_after=Decimal("0"),
            remark=f"Credits expired (expiry={expiry.isoformat()})",
        )
        session.add(log)
        session.commit()
        logger.info(f"User {row.user_id} credits expired: {old_credits} -> 0")

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

            # 更新积分过期时间
            expiry_days = self.get_billing_config().get("credits_expiry_days", 0)
            if expiry_days > 0:
                row.credits_expires_at = datetime.now(timezone.utc) + timedelta(days=expiry_days)

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
        """检查并消耗积分（reference_id 非空时幂等去重）"""
        if not self.is_billing_enabled():
            return True, "billing_disabled"

        cost = self.get_feature_cost(feature)
        if cost <= 0:
            return True, "free_feature"

        # 幂等去重：同一 reference_id 的扣费只执行一次
        if reference_id:
            session_check = BillingStore.get_session()
            try:
                existing = (
                    session_check.query(CreditsLogModel)
                    .filter_by(user_id=user_id, action="consume", reference_id=reference_id)
                    .first()
                )
                if existing:
                    return True, "already_consumed"
            finally:
                session_check.close()

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
        """获取用户 VIP 状态（终身会员会自动检查并补发月度积分）
        
        返回:
            (is_vip, expires_at): expires_at 为 None 表示终身会员永不过期
        """
        try:
            session = BillingStore.get_session()
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            if not row:
                session.close()
                return False, None

            # 终身会员永不过期
            if row.vip_is_lifetime:
                now = datetime.now(timezone.utc)
                self._grant_lifetime_monthly_credits_if_due(session, row, now)
                session.close()
                return True, None

            if not row.vip_expires_at:
                session.close()
                return False, None

            expires_at = row.vip_expires_at
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

            now = datetime.now(timezone.utc)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            is_vip = expires_at > now
            session.close()
            return is_vip, expires_at
        except Exception as e:
            logger.error(f"get_user_vip_status failed: {e}")
            return False, None

    def _grant_lifetime_monthly_credits_if_due(
        self,
        session,
        row: UserCreditsModel,
        now: datetime,
    ) -> None:
        """检查终身会员是否到月度积分发放时间，若到则补发（最多 6 个月）。"""
        try:
            plans = self.get_membership_plans()
            monthly_credits = int(plans.get("lifetime", {}).get("credits_monthly") or 0)
            if monthly_credits <= 0:
                return

            last_grant = row.vip_monthly_credits_last_grant
            if isinstance(last_grant, str) and last_grant:
                try:
                    last_grant = datetime.fromisoformat(last_grant.replace("Z", "+00:00"))
                except Exception:
                    last_grant = None
            if last_grant and last_grant.tzinfo is None:
                last_grant = last_grant.replace(tzinfo=timezone.utc)

            # 首次不补发（购买时已发放），但需设置 last_grant
            if not last_grant:
                row.vip_monthly_credits_last_grant = now
                row.updated_at = now
                session.commit()
                return

            delta_days = int((now - last_grant).total_seconds() // 86400)
            periods = delta_days // 30
            if periods <= 0:
                return
            if periods > 6:
                periods = 6

            total = monthly_credits * periods
            old_credits = Decimal(str(row.credits or 0))
            new_balance = old_credits + Decimal(str(total))
            row.credits = new_balance
            row.vip_monthly_credits_last_grant = now
            row.updated_at = now

            log = CreditsLogModel(
                user_id=row.user_id,
                action="membership_monthly",
                amount=total,
                balance_after=new_balance,
                remark=f"Lifetime membership monthly credits x{periods} (auto-grant)",
                reference_id="",
            )
            session.add(log)
            session.commit()
            logger.info(
                f"User {row.user_id} lifetime auto-granted {total} credits x{periods}, "
                f"balance: {new_balance}"
            )
        except Exception:
            # Best-effort; never break caller
            session.rollback()
            logger.warning(f"Auto-grant lifetime credits failed for {row.user_id}", exc_info=True)

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
        record_membership_order: bool = True,
        fulfillment_ref: str = "",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """激活会员（VIP 日期 + 赠送积分）
        
        Args:
            record_membership_order: 是否写入 membership_orders 表。
                USDT 支付确认时应设为 False（usdt_orders 已代表实际订单）。
        """
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
                vip_expires_at = None  # 终身会员无过期时间
                vip_is_lifetime = True

            row.vip_expires_at = vip_expires_at
            row.vip_plan = plan
            row.vip_is_lifetime = vip_is_lifetime
            row.updated_at = now

            order_ref = fulfillment_ref or f"billing:{user_id}:{int(now.timestamp())}"
            order_id: int | None = None

            if record_membership_order:
                # 创建会员订单记录（内部调用/赠送场景）
                plan_info = plans[plan]
                credits_granted = 0
                if plan in ("monthly", "yearly"):
                    credits_granted = int(plan_info.get("credits_once") or 0)
                else:
                    credits_granted = int(plan_info.get("credits_monthly") or 0)

                order = MembershipOrderModel(
                    user_id=user_id,
                    plan=plan,
                    price_usd=Decimal(str(plan_info.get("price_usd") or 0)),
                    credits_granted=credits_granted,
                    status="paid",
                    fulfillment_ref=order_ref,
                    paid_at=now,
                )
                session.add(order)
                session.flush()
                order_id = order.id
            else:
                # USDT 支付场景：usdt_orders 已代表实际订单，不重复记录
                ref = (fulfillment_ref or "").strip()
                order_ref = ref if ref else f"usdt:{user_id}:{int(now.timestamp())}"

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
                "order_id": order_id,
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
        is_lifetime: bool = False,
    ) -> Tuple[bool, str]:
        """设置用户 VIP 状态
        
        Args:
            expires_at: VIP 过期时间，None 表示取消 VIP（终身会员除外）
            is_lifetime: 是否为终身会员，为 True 时 expires_at 应为 None
        """
        session = BillingStore.get_session()
        try:
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            if not row:
                row = UserCreditsModel(user_id=user_id, credits=Decimal("0"))
                session.add(row)
                session.flush()

            row.vip_expires_at = expires_at
            row.vip_is_lifetime = is_lifetime
            row.updated_at = datetime.now(timezone.utc)

            if is_lifetime:
                action = "vip_grant_lifetime"
                log_remark = remark or "VIP granted (lifetime)"
            elif expires_at:
                action = "vip_grant"
                log_remark = remark or f"VIP granted until {expires_at}"
            else:
                action = "vip_revoke"
                log_remark = remark or "VIP revoked"

            audit = CreditsLogModel(
                user_id=user_id,
                action=action,
                amount=0,
                balance_after=row.credits,
                remark=log_remark,
            )
            session.add(audit)
            session.commit()

            logger.info(f"User {user_id} VIP set to {expires_at} (lifetime={is_lifetime})")
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

    def get_membership_orders(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """获取用户会员购买订单"""
        offset = (page - 1) * page_size
        session = BillingStore.get_session()
        try:
            total = session.query(MembershipOrderModel).filter_by(user_id=user_id).count()
            rows = (
                session.query(MembershipOrderModel)
                .filter_by(user_id=user_id)
                .order_by(MembershipOrderModel.created_at.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )

            items = []
            for r in rows:
                dt = r.created_at
                created_at_str = None
                if dt:
                    if getattr(dt, "tzinfo", None) is not None:
                        created_at_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
                    else:
                        created_at_str = dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
                items.append({
                    "id": r.id,
                    "plan": r.plan,
                    "price_usd": float(r.price_usd),
                    "credits_granted": r.credits_granted,
                    "status": r.status,
                    "fulfillment_ref": r.fulfillment_ref,
                    "created_at": created_at_str,
                })

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            }
        except Exception as e:
            logger.error(f"get_membership_orders failed: {e}")
            return {"items": [], "total": 0, "page": 1, "page_size": page_size, "total_pages": 0}
        finally:
            session.close()

    def revoke_membership(self, user_id: str, remark: str = "") -> Tuple[bool, str]:
        """撤销用户 VIP 会员身份（不清除积分，仅撤销会员状态）"""
        session = BillingStore.get_session()
        try:
            row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
            if not row:
                session.close()
                return False, "not_vip"

            was_vip = row.vip_is_lifetime
            if not was_vip and row.vip_expires_at:
                expires_at = row.vip_expires_at
                if isinstance(expires_at, str):
                    try:
                        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    except Exception:
                        expires_at = None
                if expires_at and expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at and expires_at > datetime.now(timezone.utc):
                    was_vip = True
            if not was_vip:
                session.close()
                return False, "user_not_vip"

            row.vip_expires_at = None
            row.vip_is_lifetime = False
            row.vip_plan = ""
            row.updated_at = datetime.now(timezone.utc)

            log = CreditsLogModel(
                user_id=user_id,
                action="membership_revoke",
                amount=0,
                balance_after=row.credits,
                remark=remark or "Membership revoked by admin",
            )
            session.add(log)
            session.commit()

            logger.info(f"User {user_id} membership revoked")
            return True, "success"
        except Exception as e:
            session.rollback()
            logger.error(f"revoke_membership failed: {e}")
            return False, str(e)
        finally:
            session.close()

    def get_admin_metrics(self) -> Dict[str, Any]:
        """获取运营数据指标（管理员）"""
        session = BillingStore.get_session()
        try:
            # 用户统计
            total_users = session.query(UserCreditsModel).count()
            vip_users = session.query(UserCreditsModel).filter(
                UserCreditsModel.vip_is_lifetime == True
            ).count()
            vip_users += session.query(UserCreditsModel).filter(
                UserCreditsModel.vip_is_lifetime == False,
                UserCreditsModel.vip_expires_at > datetime.now(timezone.utc)
            ).count()

            # 套餐购买统计
            plan_counts = {}
            for plan in ("monthly", "yearly", "lifetime"):
                plan_counts[plan] = session.query(MembershipOrderModel).filter_by(plan=plan).count()

            # USDT 订单统计
            usdt_status_counts = {}
            for status in ("pending", "paid", "confirmed", "expired"):
                usdt_status_counts[status] = session.query(UsdtOrderModel).filter_by(status=status).count()

            # 积分消耗 Top 功能
            top_features = (
                session.query(
                    CreditsLogModel.feature,
                    func.count(CreditsLogModel.id).label("count"),
                    func.sum(CreditsLogModel.amount).label("total_amount"),
                )
                .filter(CreditsLogModel.action == "consume")
                .filter(CreditsLogModel.feature.isnot(None))
                .group_by(CreditsLogModel.feature)
                .order_by(func.count(CreditsLogModel.id).desc())
                .limit(5)
                .all()
            )

            return {
                "users": {
                    "total": total_users,
                    "vip": vip_users,
                },
                "membership_orders": plan_counts,
                "usdt_orders": usdt_status_counts,
                "top_consumed_features": [
                    {"feature": f[0], "count": f[1], "total_credits": float(f[2] or 0)}
                    for f in top_features
                ],
            }
        except Exception as e:
            logger.error(f"get_admin_metrics failed: {e}")
            return {
                "users": {"total": 0, "vip": 0},
                "membership_orders": {},
                "usdt_orders": {},
                "top_consumed_features": [],
            }
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
