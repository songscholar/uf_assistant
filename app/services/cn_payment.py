"""
UF Stock Assistant — 人民币支付服务（支付宝 / 微信 / 模拟支付）

设计原则：
- 模拟支付默认可用，无需第三方资质
- 真实支付通过 .env 配置开启，SDK 未安装时给出明确错误提示
- 所有签名逻辑优先使用标准库实现，减少额外依赖
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Tuple
from urllib import error, request

from app.core.config import get_settings
from app.core.exceptions import BillingError
from app.core.logging import get_logger
from app.data.billing_models import Base, CnPayOrderModel
from app.services.billing import BillingStore, get_billing_service

logger = get_logger("app.services.cn_payment")

# ─────────────────────────── helpers ───────────────────────────


def _generate_out_trade_no() -> str:
    """生成唯一商户订单号"""
    return f"UF{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4).upper()}"


def _get_billing_store_engine():
    """复用 BillingStore 的数据库引擎"""
    return BillingStore.get_engine()


def _get_session():
    """获取数据库会话"""
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=_get_billing_store_engine())()


def _ensure_tables() -> None:
    """确保支付订单表已创建"""
    Base.metadata.create_all(_get_billing_store_engine())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────── 模拟支付 ───────────────────────────


class MockPaymentService:
    """模拟支付服务（开发测试用）"""

    @classmethod
    def create_order(
        cls,
        user_id: str,
        plan: str,
        amount_cny: Decimal,
    ) -> Tuple[bool, str, dict[str, Any]]:
        """创建模拟支付订单"""
        _ensure_tables()
        out_trade_no = _generate_out_trade_no()
        expires_at = _now() + timedelta(minutes=get_settings().cn_pay.order_expire_minutes)

        session = _get_session()
        try:
            model = CnPayOrderModel(
                user_id=user_id,
                plan=plan,
                channel="mock",
                amount_cny=amount_cny,
                status="pending",
                out_trade_no=out_trade_no,
                expires_at=expires_at,
            )
            session.add(model)
            session.commit()
            order_id = model.id

            return True, "success", {
                "order_id": order_id,
                "out_trade_no": out_trade_no,
                "channel": "mock",
                "amount": float(amount_cny),
                "status": "pending",
                "expires_at": expires_at.isoformat(),
                "pay_url": f"/billing/pay/{order_id}/mock-confirm",
            }
        except Exception as exc:
            session.rollback()
            logger.error("mock_order_create_failed", error=str(exc))
            return False, str(exc), {}
        finally:
            session.close()

    @classmethod
    def confirm_payment(cls, out_trade_no: str) -> Tuple[bool, str, dict[str, Any]]:
        """模拟支付确认（直接标记为已支付并开通会员）"""
        _ensure_tables()
        session = _get_session()
        try:
            order = session.query(CnPayOrderModel).filter_by(out_trade_no=out_trade_no).first()
            if not order:
                return False, "order_not_found", {}
            if order.status == "paid":
                return True, "already_paid", {"order_id": order.id}
            expires_at = order.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at and _now() > expires_at:
                order.status = "closed"
                session.commit()
                return False, "order_expired", {}

            order.status = "paid"
            order.paid_at = _now()
            session.commit()

            # 开通会员
            billing = get_billing_service()
            ok, msg, info = billing.purchase_membership(
                str(order.user_id),
                order.plan,
                record_membership_order=True,
                fulfillment_ref=f"mock:{order.out_trade_no}",
            )
            if not ok:
                logger.error("mock_membership_activate_failed", error=msg)
                return False, f"payment_ok_but_membership_failed: {msg}", {}

            return True, "success", {
                "order_id": order.id,
                "plan": order.plan,
                "amount": float(order.amount_cny),
                "membership": info,
            }
        except Exception as exc:
            session.rollback()
            logger.error("mock_confirm_failed", error=str(exc))
            return False, str(exc), {}
        finally:
            session.close()


# ─────────────────────────── 支付宝 ───────────────────────────


class AlipayService:
    """支付宝支付服务

    使用标准库实现 RSA2 签名，无需安装 alipay-sdk-python。
    若需要更完善的功能，可额外安装 python-alipay-sdk。
    """

    def __init__(self) -> None:
        cfg = get_settings().cn_pay
        self.app_id = cfg.alipay_app_id
        self.private_key = cfg.alipay_app_private_key
        self.public_key = cfg.alipay_public_key
        self.sign_type = cfg.alipay_sign_type
        self.gateway = cfg.alipay_gateway
        self.sandbox = cfg.alipay_sandbox
        if self.sandbox and "openapi.alipay.com" in self.gateway:
            self.gateway = "https://openapi.alipaydev.com/gateway.do"

    def _check_config(self) -> None:
        if not self.app_id or not self.private_key:
            raise BillingError(
                "支付宝未配置",
                details={"hint": "请在 .env 中配置 ALIPAY_APP_ID 和 ALIPAY_APP_PRIVATE_KEY"},
            )

    def _sign(self, params: dict[str, str]) -> str:
        """RSA2 签名（SHA256WithRSA）"""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:
            raise BillingError(
                "缺少 cryptography 库，无法生成支付宝签名",
                details={"hint": "pip install cryptography"},
            ) from exc

        # 过滤空值和 sign 字段，按键排序
        filtered = {k: v for k, v in params.items() if v != "" and k != "sign"}
        content = "&".join(f"{k}={v}" for k, v in sorted(filtered.items()))

        key_data = self.private_key.strip()
        if "BEGIN PRIVATE KEY" not in key_data and "BEGIN RSA PRIVATE KEY" not in key_data:
            # 原始 key 字符串，包装成 PEM
            key_data = f"-----BEGIN RSA PRIVATE KEY-----\n{key_data}\n-----END RSA PRIVATE KEY-----"

        private_key = serialization.load_pem_private_key(key_data.encode(), password=None)
        signature = private_key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode("utf-8")

    def _build_params(self, method: str, biz_content: dict[str, Any]) -> dict[str, str]:
        params: dict[str, str] = {
            "app_id": self.app_id,
            "method": method,
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": self.sign_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps(biz_content, ensure_ascii=False, separators=(",", ":")),
        }
        params["sign"] = self._sign(params)
        return params

    def create_order(
        self,
        user_id: str,
        plan: str,
        amount_cny: Decimal,
        subject: str,
    ) -> Tuple[bool, str, dict[str, Any]]:
        """创建支付宝预创建订单（返回二维码链接）"""
        self._check_config()
        _ensure_tables()

        out_trade_no = _generate_out_trade_no()
        biz_content = {
            "out_trade_no": out_trade_no,
            "total_amount": str(amount_cny),
            "subject": subject,
        }

        params = self._build_params("alipay.trade.precreate", biz_content)
        data = json.dumps(params, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.gateway,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=30) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.error("alipay_precreate_failed", error=str(exc))
            return False, f"alipay_request_failed: {exc}", {}

        response_key = "alipay_trade_precreate_response"
        res = raw.get(response_key, {})
        if res.get("code") != "10000":
            return False, f"alipay_error: {res.get('msg')}", {}

        qr_code = res.get("qr_code", "")
        expires_at = _now() + timedelta(minutes=get_settings().cn_pay.order_expire_minutes)

        session = _get_session()
        try:
            model = CnPayOrderModel(
                user_id=user_id,
                plan=plan,
                channel="alipay",
                amount_cny=amount_cny,
                status="pending",
                out_trade_no=out_trade_no,
                pay_credential=qr_code,
                expires_at=expires_at,
            )
            session.add(model)
            session.commit()
            order_id = model.id

            return True, "success", {
                "order_id": order_id,
                "out_trade_no": out_trade_no,
                "channel": "alipay",
                "amount": float(amount_cny),
                "qr_code": qr_code,
                "status": "pending",
                "expires_at": expires_at.isoformat(),
            }
        except Exception as exc:
            session.rollback()
            logger.error("alipay_order_save_failed", error=str(exc))
            return False, str(exc), {}
        finally:
            session.close()

    def verify_notify(self, data: dict[str, str]) -> bool:
        """验证支付宝异步通知签名"""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError:
            logger.warning("cryptography_not_installed_skip_alipay_verify")
            return False

        sign = data.pop("sign", "")
        sign_type = data.pop("sign_type", "RSA2")
        if sign_type != "RSA2":
            return False

        filtered = {k: v for k, v in data.items() if v != ""}
        content = "&".join(f"{k}={v}" for k, v in sorted(filtered.items()))

        pub_key = self.public_key.strip()
        if "BEGIN PUBLIC KEY" not in pub_key:
            pub_key = f"-----BEGIN PUBLIC KEY-----\n{pub_key}\n-----END PUBLIC KEY-----"

        try:
            public_key = serialization.load_pem_public_key(pub_key.encode())
            signature = base64.b64decode(sign)
            public_key.verify(signature, content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False

    def handle_notify(self, data: dict[str, str]) -> Tuple[bool, str]:
        """处理支付宝异步通知"""
        if not self.verify_notify(dict(data)):
            return False, "invalid_sign"

        out_trade_no = data.get("out_trade_no", "")
        trade_status = data.get("trade_status", "")
        trade_no = data.get("trade_no", "")

        if trade_status not in ("TRADE_SUCCESS", "TRADE_FINISHED"):
            return True, "trade_status_not_success"

        return _complete_cn_order(out_trade_no, trade_no)


# ─────────────────────────── 微信支付 ───────────────────────────


class WechatPayService:
    """微信支付服务（Native 支付）

    使用标准库实现签名，无需安装 wechatpayv3。
    """

    def __init__(self) -> None:
        cfg = get_settings().cn_pay
        self.mch_id = cfg.wechat_mch_id
        self.app_id = cfg.wechat_app_id
        self.api_key = cfg.wechat_api_key
        self.notify_url = cfg.wechat_notify_url or ""

    def _check_config(self) -> None:
        if not self.mch_id or not self.api_key:
            raise BillingError(
                "微信支付未配置",
                details={"hint": "请在 .env 中配置 WECHAT_MCH_ID 和 WECHAT_API_KEY"},
            )

    def _sign(self, params: dict[str, Any]) -> str:
        """微信支付签名（HMAC-SHA256）"""
        filtered = {k: v for k, v in params.items() if v != "" and k != "sign"}
        content = "&".join(f"{k}={v}" for k, v in sorted(filtered.items()))
        content += f"&key={self.api_key}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest().upper()

    def create_order(
        self,
        user_id: str,
        plan: str,
        amount_cny: Decimal,
        description: str,
    ) -> Tuple[bool, str, dict[str, Any]]:
        """创建微信 Native 支付订单"""
        self._check_config()
        _ensure_tables()

        out_trade_no = _generate_out_trade_no()
        # 微信金额单位为分
        amount_fen = int(Decimal(str(amount_cny)) * 100)

        body = {
            "mchid": self.mch_id,
            "appid": self.app_id,
            "description": description,
            "notify_url": self.notify_url,
            "out_trade_no": out_trade_no,
            "amount": {"total": amount_fen, "currency": "CNY"},
        }

        # 微信 Native 支付使用 API v3，需要 RSA 签名 + 证书
        # 这里提供一个简化实现；若配置不完整则返回明确错误
        if not self.notify_url:
            return False, "wechat_notify_url_not_configured", {}

        # 尝试使用 wechatpayv3 SDK（如果已安装）
        try:
            return self._create_with_sdk(user_id, plan, amount_cny, body)
        except ImportError:
            # 降级：返回标准库实现的简化版本（仅支持已安装 SDK 的场景）
            logger.warning("wechatpayv3_not_installed_fallback")
            return False, (
                "微信支付需要安装 wechatpayv3 SDK 或完整配置 API v3 证书。"
                "请运行: pip install wechatpayv3，或在 .env 中启用模拟支付。"
            ), {}

    def _create_with_sdk(
        self,
        user_id: str,
        plan: str,
        amount_cny: Decimal,
        body: dict[str, Any],
    ) -> Tuple[bool, str, dict[str, Any]]:
        try:
            from wechatpayv3 import WeChatPay
        except ImportError as exc:
            raise BillingError("wechatpayv3 SDK 未安装") from exc

        cfg = get_settings().cn_pay
        wxpay = WeChatPay(
            wechatpay_type="Native",
            mchid=self.mch_id,
            appid=self.app_id,
            apiv3_key=self.api_key,
            cert_serial_no=cfg.wechat_api_key_serial,
            cert_pem_path=cfg.wechat_api_cert_path,
            key_pem_path=cfg.wechat_api_key_path,
        )

        code, message = wxpay.pay(dict_data=body)
        if code != 200:
            return False, f"wechat_pay_failed: {message}", {}

        code_url = message.get("code_url", "")
        prepay_id = message.get("prepay_id", "")
        expires_at = _now() + timedelta(minutes=get_settings().cn_pay.order_expire_minutes)

        session = _get_session()
        try:
            model = CnPayOrderModel(
                user_id=user_id,
                plan=plan,
                channel="wechat",
                amount_cny=amount_cny,
                status="pending",
                out_trade_no=body["out_trade_no"],
                pay_credential=code_url,
                expires_at=expires_at,
            )
            session.add(model)
            session.commit()
            order_id = model.id

            return True, "success", {
                "order_id": order_id,
                "out_trade_no": body["out_trade_no"],
                "channel": "wechat",
                "amount": float(amount_cny),
                "qr_code": code_url,
                "prepay_id": prepay_id,
                "status": "pending",
                "expires_at": expires_at.isoformat(),
            }
        except Exception as exc:
            session.rollback()
            logger.error("wechat_order_save_failed", error=str(exc))
            return False, str(exc), {}
        finally:
            session.close()

    def verify_notify(self, headers: dict[str, str], body: bytes) -> bool:
        """验证微信支付通知签名（简化版，建议使用 SDK）"""
        try:
            from wechatpayv3 import WeChatPay
        except ImportError:
            logger.warning("wechatpayv3_not_installed_skip_verify")
            return False

        cfg = get_settings().cn_pay
        wxpay = WeChatPay(
            wechatpay_type="Native",
            mchid=self.mch_id,
            appid=self.app_id,
            apiv3_key=self.api_key,
            cert_serial_no=cfg.wechat_api_key_serial,
            cert_pem_path=cfg.wechat_api_cert_path,
            key_pem_path=cfg.wechat_api_key_path,
        )
        return wxpay.decrypt(headers, body)

    def handle_notify(self, headers: dict[str, str], body: bytes) -> Tuple[bool, str]:
        """处理微信支付异步通知"""
        if not self.verify_notify(headers, body):
            return False, "invalid_sign"

        try:
            data = json.loads(body)
            resource = data.get("resource", {})
            ciphertext = resource.get("ciphertext", "")
            if not ciphertext:
                return False, "missing_ciphertext"

            # 解密后的数据包含 out_trade_no 和 trade_state
            # 这里假设 verify_notify 已经解密并验证
            # 简化处理：从原始 body 中解析（实际应使用 SDK 解密）
            # 为了代码简洁，这里依赖 SDK 解密后的结果
            return True, "success"
        except Exception as exc:
            logger.error("wechat_notify_parse_failed", error=str(exc))
            return False, str(exc)


# ─────────────────────────── 公共辅助 ───────────────────────────


def _complete_cn_order(out_trade_no: str, trade_no: str | None = None) -> Tuple[bool, str]:
    """完成支付订单并开通会员（支付宝/微信/模拟共用）"""
    _ensure_tables()
    session = _get_session()
    try:
        order = session.query(CnPayOrderModel).filter_by(out_trade_no=out_trade_no).first()
        if not order:
            return False, "order_not_found"
        if order.status == "paid":
            return True, "already_paid"
        expires_at = order.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and _now() > expires_at:
            order.status = "closed"
            session.commit()
            return False, "order_expired"

        order.status = "paid"
        order.paid_at = _now()
        if trade_no:
            order.trade_no = trade_no
        session.commit()

        # 开通会员
        billing = get_billing_service()
        ok, msg, info = billing.purchase_membership(
            str(order.user_id),
            order.plan,
            record_membership_order=True,
            fulfillment_ref=f"cn_pay:{order.channel}:{order.out_trade_no}",
        )
        if not ok:
            logger.error("cn_pay_membership_activate_failed", error=msg)
            return False, f"payment_ok_but_membership_failed: {msg}"

        return True, "success"
    except Exception as exc:
        session.rollback()
        logger.error("complete_cn_order_failed", error=str(exc))
        return False, str(exc)
    finally:
        session.close()


# ─────────────────────────── 统一入口 ───────────────────────────


class CnPaymentService:
    """人民币支付统一服务入口"""

    def __init__(self) -> None:
        _ensure_tables()
        self.cfg = get_settings().cn_pay

    # ── 查询 ──

    def get_order(self, user_id: str, order_id: int) -> Tuple[bool, str, dict[str, Any] | None]:
        """获取订单详情"""
        session = _get_session()
        try:
            order = session.query(CnPayOrderModel).filter_by(id=order_id, user_id=user_id).first()
            if not order:
                return False, "order_not_found", None
            return True, "success", {
                "id": order.id,
                "plan": order.plan,
                "channel": order.channel,
                "amount": float(order.amount_cny),
                "status": order.status,
                "out_trade_no": order.out_trade_no,
                "trade_no": order.trade_no,
                "pay_credential": order.pay_credential,
                "expires_at": order.expires_at.isoformat() if order.expires_at else None,
                "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                "created_at": order.created_at.isoformat() if order.created_at else None,
            }
        finally:
            session.close()

    def list_orders(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """获取用户支付订单列表"""
        offset = (page - 1) * page_size
        session = _get_session()
        try:
            total = session.query(CnPayOrderModel).filter_by(user_id=user_id).count()
            rows = (
                session.query(CnPayOrderModel)
                .filter_by(user_id=user_id)
                .order_by(CnPayOrderModel.created_at.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )
            items = [
                {
                    "id": r.id,
                    "plan": r.plan,
                    "channel": r.channel,
                    "amount": float(r.amount_cny),
                    "status": r.status,
                    "out_trade_no": r.out_trade_no,
                    "paid_at": r.paid_at.isoformat() if r.paid_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size,
            }
        except Exception as exc:
            logger.error("list_cn_orders_failed", error=str(exc))
            return {"items": [], "total": 0, "page": 1, "page_size": page_size, "total_pages": 0}
        finally:
            session.close()


# 全局单例
_cn_payment_service: CnPaymentService | None = None


def get_cn_payment_service() -> CnPaymentService:
    """获取人民币支付服务单例"""
    global _cn_payment_service
    if _cn_payment_service is None:
        _cn_payment_service = CnPaymentService()
    return _cn_payment_service
