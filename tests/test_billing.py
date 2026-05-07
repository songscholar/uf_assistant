"""
UF Stock Assistant — 计费模块单元测试
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import reload_settings
from app.services.billing import BillingService, BillingStore, get_billing_service

client = TestClient(app)


def _random_user() -> str:
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _billing_env(monkeypatch):
    """为计费测试设置隔离环境，不影响其他测试模块"""
    import tempfile
    db_path = tempfile.mktemp(suffix=".db")
    monkeypatch.setenv("STOCK_ASSISTANT_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STOCK_ASSISTANT_BILLING_ENABLED", "true")
    monkeypatch.setenv("STOCK_ASSISTANT_BILLING_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("STOCK_ASSISTANT_BILLING_CREDITS_REGISTER_BONUS", "100")
    # 清除配置缓存，确保新环境变量生效
    reload_settings()
    # 重置单例和表
    BillingStore._engine = None
    BillingStore._session_factory = None
    BillingStore.ensure_tables()
    yield
    # 清理临时数据库文件
    import os
    try:
        os.unlink(db_path)
    except Exception:
        pass


@pytest.fixture
def billing_svc() -> BillingService:
    svc = BillingService()
    svc.clear_config_cache()
    return svc


class TestBillingConfig:
    def test_is_billing_enabled(self, billing_svc: BillingService) -> None:
        assert billing_svc.is_billing_enabled() is True

    def test_get_feature_cost(self, billing_svc: BillingService) -> None:
        assert billing_svc.get_feature_cost("ai_analysis") == 10
        assert billing_svc.get_feature_cost("unknown_feature") == 0


class TestCredits:
    def test_get_user_credits_new_user(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        credits = billing_svc.get_user_credits(user_id)
        # 默认注册赠送 100 积分
        assert credits == 100

    def test_add_credits(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        ok, msg = billing_svc.add_credits(user_id, 100, action="test", remark="init")
        assert ok is True
        assert billing_svc.get_user_credits(user_id) == 100

    def test_add_credits_negative_amount(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        ok, msg = billing_svc.add_credits(user_id, -10)
        assert ok is False
        assert "positive" in msg

    def test_set_credits(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        billing_svc.add_credits(user_id, 50)
        ok, msg = billing_svc.set_credits(user_id, 200)
        assert ok is True
        assert billing_svc.get_user_credits(user_id) == 200

    def test_consume_success(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        billing_svc.add_credits(user_id, 100)
        ok, msg = billing_svc.check_and_consume(user_id, "ai_analysis")
        assert ok is True
        assert msg == "consumed"
        assert billing_svc.get_user_credits(user_id) == 90

    def test_consume_insufficient(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        # 先将积分设为 0，测试不足场景
        billing_svc.set_credits(user_id, 0)
        ok, msg = billing_svc.check_and_consume(user_id, "ai_analysis")
        assert ok is False
        assert "insufficient_credits" in msg

    def test_consume_billing_disabled(self, billing_svc: BillingService) -> None:
        os.environ["STOCK_ASSISTANT_BILLING_ENABLED"] = "false"
        billing_svc.clear_config_cache()
        user_id = _random_user()
        ok, msg = billing_svc.check_and_consume(user_id, "ai_analysis")
        assert ok is True
        assert msg == "billing_disabled"
        os.environ["STOCK_ASSISTANT_BILLING_ENABLED"] = "true"
        billing_svc.clear_config_cache()


class TestVip:
    def test_purchase_monthly(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        ok, msg, data = billing_svc.purchase_membership(user_id, "monthly")
        assert ok is True
        assert data["plan"] == "monthly"
        assert "order_id" in data
        is_vip, expires = billing_svc.get_user_vip_status(user_id)
        assert is_vip is True
        assert expires is not None

    def test_purchase_lifetime(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        ok, msg, data = billing_svc.purchase_membership(user_id, "lifetime")
        assert ok is True
        is_vip, expires = billing_svc.get_user_vip_status(user_id)
        assert is_vip is True

    def test_purchase_lifetime_auto_grant_first_month(self, billing_svc: BillingService) -> None:
        """终身会员首次购买应立即发放首月积分"""
        user_id = _random_user()
        ok, msg, data = billing_svc.purchase_membership(user_id, "lifetime")
        assert ok is True
        info = billing_svc.get_user_billing_info(user_id)
        # 默认 lifetime_monthly_credits = 800
        assert info["credits"] == 800.0

    def test_lifetime_auto_grant_after_due(self, billing_svc: BillingService) -> None:
        """模拟 35 天后查询 VIP 状态，应自动补发月度积分"""
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal
        from app.services.billing import BillingStore
        from app.data.billing_models import UserCreditsModel

        user_id = _random_user()
        billing_svc.purchase_membership(user_id, "lifetime")
        initial_credits = billing_svc.get_user_credits(user_id)
        assert initial_credits == 800

        # 手动将 last_grant 回退 35 天

        session = BillingStore.get_session()
        row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
        assert row is not None
        row.vip_monthly_credits_last_grant = datetime.now(timezone.utc) - timedelta(days=35)
        session.commit()
        session.close()

        # 再次查询 VIP 状态，触发自动补发
        billing_svc.get_user_vip_status(user_id)
        new_credits = billing_svc.get_user_credits(user_id)
        # 补发 1 个周期 = 800
        assert new_credits == 1600

    def test_set_vip_revoke(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        billing_svc.purchase_membership(user_id, "monthly")
        ok, msg = billing_svc.set_vip(user_id, None)
        assert ok is True
        is_vip, _ = billing_svc.get_user_vip_status(user_id)
        assert is_vip is False

    def test_purchase_invalid_plan(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        ok, msg, data = billing_svc.purchase_membership(user_id, "invalid")
        assert ok is False
        assert "invalid_plan" in msg


class TestCreditsLog:
    def test_get_credits_log(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        billing_svc.add_credits(user_id, 100, remark="first")
        billing_svc.add_credits(user_id, 50, remark="second")
        logs = billing_svc.get_credits_log(user_id)
        assert logs["total"] == 2
        assert len(logs["items"]) == 2


class TestMembershipOrders:
    def test_get_membership_orders(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        billing_svc.purchase_membership(user_id, "monthly")
        billing_svc.purchase_membership(user_id, "yearly")
        orders = billing_svc.get_membership_orders(user_id)
        assert orders["total"] == 2
        assert len(orders["items"]) == 2
        plans = [o["plan"] for o in orders["items"]]
        assert "monthly" in plans
        assert "yearly" in plans


class TestBillingInfo:
    def test_get_user_billing_info(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        billing_svc.add_credits(user_id, 100)
        info = billing_svc.get_user_billing_info(user_id)
        assert info["credits"] == 100.0
        assert info["is_vip"] is False
        assert "feature_costs" in info


class TestAdminAuth:
    def test_add_credits_without_key(self, billing_svc: BillingService) -> None:
        """无 X-Admin-Key 应返回 503（admin_api_key 未配置时不应出现，但 fixture 已配置）"""
        # 临时清空 admin key
        import os
        old_key = os.environ.get("STOCK_ASSISTANT_BILLING_ADMIN_API_KEY")
        os.environ["STOCK_ASSISTANT_BILLING_ADMIN_API_KEY"] = ""
        reload_settings()

        response = client.post("/api/v1/billing/credits/add", json={
            "user_id": _random_user(),
            "amount": 100,
        })
        assert response.status_code == 503
        assert "admin_api_key_not_configured" in response.json()["detail"]

        if old_key:
            os.environ["STOCK_ASSISTANT_BILLING_ADMIN_API_KEY"] = old_key
        else:
            os.environ.pop("STOCK_ASSISTANT_BILLING_ADMIN_API_KEY", None)
        reload_settings()

    def test_add_credits_with_wrong_key(self, billing_svc: BillingService) -> None:
        """错误的 X-Admin-Key 应返回 401"""
        response = client.post("/api/v1/billing/credits/add", json={
            "user_id": _random_user(),
            "amount": 100,
        }, headers={"X-Admin-Key": "wrong-key"})
        assert response.status_code == 401
        assert "invalid_admin_key" in response.json()["detail"]

    def test_add_credits_with_correct_key(self, billing_svc: BillingService) -> None:
        """正确的 X-Admin-Key 应正常执行"""
        user_id = _random_user()
        response = client.post("/api/v1/billing/credits/add", json={
            "user_id": user_id,
            "amount": 100,
        }, headers={"X-Admin-Key": "test-admin-key"})
        assert response.status_code == 200
        assert response.json()["code"] == "success"
        assert billing_svc.get_user_credits(user_id) == 100

    def test_set_vip_with_correct_key(self, billing_svc: BillingService) -> None:
        """设置 VIP 管理接口认证通过"""
        user_id = _random_user()
        response = client.post("/api/v1/billing/vip/set", json={
            "user_id": user_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }, headers={"X-Admin-Key": "test-admin-key"})
        assert response.status_code == 200
        assert response.json()["code"] == "success"


class TestCreditsIdempotency:
    def test_consume_idempotent_with_reference_id(self, billing_svc: BillingService) -> None:
        """同一 reference_id 的扣费应只执行一次"""
        user_id = _random_user()
        billing_svc.add_credits(user_id, 100)

        ok1, msg1 = billing_svc.check_and_consume(
            user_id, "ai_analysis", reference_id="req-001"
        )
        assert ok1 is True
        assert msg1 == "consumed"
        assert billing_svc.get_user_credits(user_id) == 90

        ok2, msg2 = billing_svc.check_and_consume(
            user_id, "ai_analysis", reference_id="req-001"
        )
        assert ok2 is True
        assert msg2 == "already_consumed"
        # 积分不应再次扣减
        assert billing_svc.get_user_credits(user_id) == 90

    def test_consume_different_reference_ids(self, billing_svc: BillingService) -> None:
        """不同 reference_id 应分别扣费"""
        user_id = _random_user()
        billing_svc.add_credits(user_id, 100)

        ok1, _ = billing_svc.check_and_consume(
            user_id, "ai_analysis", reference_id="req-001"
        )
        assert ok1 is True

        ok2, _ = billing_svc.check_and_consume(
            user_id, "ai_analysis", reference_id="req-002"
        )
        assert ok2 is True
        assert billing_svc.get_user_credits(user_id) == 80

    def test_consume_empty_reference_id_no_idempotency(self, billing_svc: BillingService) -> None:
        """reference_id 为空时不做幂等检查"""
        user_id = _random_user()
        billing_svc.add_credits(user_id, 100)

        ok1, _ = billing_svc.check_and_consume(
            user_id, "ai_analysis", reference_id=""
        )
        assert ok1 is True

        ok2, _ = billing_svc.check_and_consume(
            user_id, "ai_analysis", reference_id=""
        )
        assert ok2 is True
        # 两次都扣费了
        assert billing_svc.get_user_credits(user_id) == 80


class TestLifetimeMembership:
    def test_purchase_lifetime_no_expiry(self, billing_svc: BillingService) -> None:
        """终身会员 vip_expires_at 应为 None"""
        user_id = _random_user()
        ok, msg, data = billing_svc.purchase_membership(user_id, "lifetime")
        assert ok is True
        is_vip, expires = billing_svc.get_user_vip_status(user_id)
        assert is_vip is True
        assert expires is None

    def test_set_vip_lifetime(self, billing_svc: BillingService) -> None:
        """set_vip 支持设置为终身会员"""
        user_id = _random_user()
        ok, msg = billing_svc.set_vip(user_id, None, is_lifetime=True)
        assert ok is True
        is_vip, expires = billing_svc.get_user_vip_status(user_id)
        assert is_vip is True
        assert expires is None

    def test_set_vip_revoke_clears_lifetime(self, billing_svc: BillingService) -> None:
        """取消 VIP 应同时清除终身会员标记"""
        user_id = _random_user()
        billing_svc.set_vip(user_id, None, is_lifetime=True)
        ok, msg = billing_svc.set_vip(user_id, None)
        assert ok is True
        is_vip, expires = billing_svc.get_user_vip_status(user_id)
        assert is_vip is False


class TestRegisterBonus:
    def test_new_user_gets_register_bonus(self, billing_svc: BillingService) -> None:
        """新用户首次查询积分应自动获得注册赠送积分"""
        user_id = _random_user()
        credits = billing_svc.get_user_credits(user_id)
        # 默认 credits_register_bonus = 100
        assert credits == 100

    def test_register_bonus_logged(self, billing_svc: BillingService) -> None:
        """注册赠送积分应记录到 credits_log"""
        user_id = _random_user()
        billing_svc.get_user_credits(user_id)
        logs = billing_svc.get_credits_log(user_id)
        assert logs["total"] == 1
        assert logs["items"][0]["action"] == "register_bonus"
        assert logs["items"][0]["amount"] == 100


class TestMembershipOrderDeduplication:
    def test_purchase_without_order_record(self, billing_svc: BillingService) -> None:
        """record_membership_order=False 时不写入 membership_orders"""
        user_id = _random_user()
        ok, msg, data = billing_svc.purchase_membership(
            user_id, "monthly", record_membership_order=False
        )
        assert ok is True
        orders = billing_svc.get_membership_orders(user_id)
        assert orders["total"] == 0

    def test_purchase_with_order_record(self, billing_svc: BillingService) -> None:
        """record_membership_order=True 时正常写入 membership_orders"""
        user_id = _random_user()
        ok, msg, data = billing_svc.purchase_membership(
            user_id, "monthly", record_membership_order=True
        )
        assert ok is True
        orders = billing_svc.get_membership_orders(user_id)
        assert orders["total"] == 1


class TestCreditsExpiry:
    def test_credits_expired_auto_zero(self, billing_svc: BillingService) -> None:
        """积分过期后自动清零"""
        from app.services.billing import BillingStore
        from app.data.billing_models import UserCreditsModel

        user_id = _random_user()
        billing_svc.add_credits(user_id, 100)
        assert billing_svc.get_user_credits(user_id) == 100

        # 手动将过期时间设为昨天
        session = BillingStore.get_session()
        row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
        assert row is not None
        row.credits_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()
        session.close()

        # 再次查询应触发过期清零
        credits = billing_svc.get_user_credits(user_id)
        assert credits == 0

        # 验证过期日志
        logs = billing_svc.get_credits_log(user_id)
        expired_logs = [l for l in logs["items"] if l["action"] == "expired"]
        assert len(expired_logs) == 1
        assert expired_logs[0]["amount"] == -100

    def test_credits_not_expired(self, billing_svc: BillingService) -> None:
        """积分未过期时保持正常"""
        user_id = _random_user()
        billing_svc.add_credits(user_id, 100)
        credits = billing_svc.get_user_credits(user_id)
        assert credits == 100

    def test_consume_after_expiry(self, billing_svc: BillingService) -> None:
        """积分过期后扣费应失败"""
        from app.services.billing import BillingStore
        from app.data.billing_models import UserCreditsModel

        user_id = _random_user()
        billing_svc.add_credits(user_id, 100)

        # 手动将过期时间设为昨天
        session = BillingStore.get_session()
        row = session.query(UserCreditsModel).filter_by(user_id=user_id).first()
        assert row is not None
        row.credits_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()
        session.close()

        ok, msg = billing_svc.check_and_consume(user_id, "ai_analysis")
        assert ok is False
        assert "insufficient_credits" in msg


class TestReconcileLogLevel:
    def test_log_level_none(self) -> None:
        from app.services.usdt_payment import UsdtPaymentService
        assert UsdtPaymentService._reconcile_log_allowed("none", "info") is False
        assert UsdtPaymentService._reconcile_log_allowed("none", "error") is False

    def test_log_level_info(self) -> None:
        from app.services.usdt_payment import UsdtPaymentService
        assert UsdtPaymentService._reconcile_log_allowed("info", "info") is True
        assert UsdtPaymentService._reconcile_log_allowed("info", "warn") is True
        assert UsdtPaymentService._reconcile_log_allowed("info", "debug") is False

    def test_log_level_debug(self) -> None:
        from app.services.usdt_payment import UsdtPaymentService
        assert UsdtPaymentService._reconcile_log_allowed("debug", "debug") is True
        assert UsdtPaymentService._reconcile_log_allowed("debug", "info") is True


class TestAdminMetrics:
    def test_metrics_endpoint(self, billing_svc: BillingService) -> None:
        """运营数据接口返回正确结构"""
        user_id = _random_user()
        billing_svc.purchase_membership(user_id, "monthly")
        billing_svc.check_and_consume(user_id, "ai_analysis", reference_id="r1")

        response = client.get("/api/v1/billing/admin/metrics", headers={"X-Admin-Key": "test-admin-key"})
        assert response.status_code == 200
        data = response.json()["data"]
        assert "users" in data
        assert "membership_orders" in data
        assert "usdt_orders" in data
        assert "top_consumed_features" in data
        assert data["users"]["total"] >= 1


class TestMembershipRevoke:
    def test_revoke_membership(self, billing_svc: BillingService) -> None:
        """撤销会员后 VIP 状态清除"""
        user_id = _random_user()
        billing_svc.purchase_membership(user_id, "monthly")
        is_vip, _ = billing_svc.get_user_vip_status(user_id)
        assert is_vip is True

        ok, msg = billing_svc.revoke_membership(user_id)
        assert ok is True
        is_vip, _ = billing_svc.get_user_vip_status(user_id)
        assert is_vip is False

    def test_revoke_non_vip(self, billing_svc: BillingService) -> None:
        """撤销非 VIP 用户应失败"""
        user_id = _random_user()
        ok, msg = billing_svc.revoke_membership(user_id)
        assert ok is False
        assert "not_vip" in msg

    def test_revoke_endpoint(self, billing_svc: BillingService) -> None:
        """管理接口撤销会员"""
        user_id = _random_user()
        billing_svc.purchase_membership(user_id, "monthly")

        response = client.post("/api/v1/billing/membership/revoke", json={
            "user_id": user_id,
            "remark": "test revoke",
        }, headers={"X-Admin-Key": "test-admin-key"})
        assert response.status_code == 200
        assert response.json()["data"]["revoked"] is True


class TestCreditsStream:
    def test_credits_stream_media_type(self) -> None:
        """SSE 端点路由配置正确（通过检查路由表而非实际请求）"""
        from app.api.main import app
        routes = [r.path for r in app.routes]
        assert "/api/v1/billing/credits/stream" in routes
