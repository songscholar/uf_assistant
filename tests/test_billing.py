"""
UF Stock Assistant — 计费模块单元测试
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services.billing import BillingService, BillingStore, get_billing_service


def _random_user() -> str:
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _billing_env(monkeypatch):
    """为计费测试设置隔离环境，不影响其他测试模块"""
    monkeypatch.setenv("STOCK_ASSISTANT_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("STOCK_ASSISTANT_BILLING_ENABLED", "true")
    # 重置单例和表
    BillingStore._engine = None
    BillingStore._session_factory = None


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
        assert credits == 0

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
        is_vip, expires = billing_svc.get_user_vip_status(user_id)
        assert is_vip is True
        assert expires is not None

    def test_purchase_lifetime(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        ok, msg, data = billing_svc.purchase_membership(user_id, "lifetime")
        assert ok is True
        is_vip, expires = billing_svc.get_user_vip_status(user_id)
        assert is_vip is True

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


class TestBillingInfo:
    def test_get_user_billing_info(self, billing_svc: BillingService) -> None:
        user_id = _random_user()
        billing_svc.add_credits(user_id, 100)
        info = billing_svc.get_user_billing_info(user_id)
        assert info["credits"] == 100.0
        assert info["is_vip"] is False
        assert "feature_costs" in info
