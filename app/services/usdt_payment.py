"""
UF Stock Assistant — USDT-TRC20 支付服务
每单独立地址 + 自动对账（TronGrid）
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

import requests

from app.core.config import get_settings
from app.core.logging import get_logger
from app.data.billing_models import UsdtOrderModel
from app.services.billing import BillingStore, get_billing_service

logger = get_logger("app.services.usdt_payment")


class UsdtPaymentService:
    """USDT-TRC20 支付服务"""

    _schema_ensured: bool = False

    def __init__(self) -> None:
        self.billing = get_billing_service()
        BillingStore.ensure_tables()

    def _get_cfg(self) -> Dict[str, Any]:
        s = get_settings().usdt
        return {
            "enabled": s.pay_enabled,
            "chain": (s.chain or "TRC20").upper(),
            "xpub_trc20": (s.trc20_xpub or "").strip(),
            "trongrid_base": (s.trongrid_base_url or "https://api.trongrid.io").strip().rstrip("/"),
            "trongrid_key": (s.trongrid_api_key or "").strip(),
            "usdt_trc20_contract": (s.trc20_contract or "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t").strip(),
            "confirm_seconds": s.confirm_seconds,
            "order_expire_minutes": s.order_expire_minutes,
            "debug_reconcile_log": True,
            "trongrid_page_limit": min(200, max(1, 200)),
            "trongrid_max_pages": max(1, min(20, 5)),
        }

    # -------------------- Address derivation --------------------

    def _derive_trc20_address_from_xpub(self, xpub: str, index: int) -> str:
        """从 xpub 派生 TRC20 地址（需要 bip_utils）"""
        try:
            from bip_utils import Bip44, Bip44Coins, Bip44Changes
        except Exception as e:
            raise RuntimeError(f"bip_utils_missing:{e}")

        if not xpub:
            raise RuntimeError("missing_xpub")
        if index < 0:
            raise RuntimeError("invalid_index")

        ctx = Bip44.FromExtendedKey(xpub, Bip44Coins.TRON)
        lvl = int(ctx.Level())
        if lvl == 3:
            ctx = ctx.Change(Bip44Changes.CHAIN_EXT)
        elif lvl == 4:
            pass
        elif lvl == 5:
            if index != 0:
                raise RuntimeError("xpub_is_address_level")
            return ctx.PublicKey().ToAddress()
        else:
            raise RuntimeError(f"unsupported_xpub_level:{lvl}")

        addr = ctx.AddressIndex(index).PublicKey().ToAddress()
        return addr

    # -------------------- Orders --------------------

    def create_order(self, user_id: str, plan: str) -> Tuple[bool, str, Dict[str, Any]]:
        """创建 USDT 支付订单"""
        cfg = self._get_cfg()
        if not cfg["enabled"]:
            return False, "usdt_pay_disabled", {}
        if cfg["chain"] != "TRC20":
            return False, "unsupported_chain", {}

        plan = (plan or "").strip().lower()
        if plan not in ("monthly", "yearly", "lifetime"):
            return False, "invalid_plan", {}

        plans = self.billing.get_membership_plans()
        amount = Decimal(str(plans.get(plan, {}).get("price_usdt") or plans.get(plan, {}).get("price_usd") or 0))
        if amount <= 0:
            return False, "invalid_amount", {}

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=cfg["order_expire_minutes"])

        session = BillingStore.get_session()
        try:
            max_idx = session.query(UsdtOrderModel).filter_by(chain="TRC20").count() - 1
            if max_idx < 0:
                max_idx = -1
            # 精确计数获取下一个索引
            all_orders = session.query(UsdtOrderModel).filter_by(chain="TRC20").order_by(UsdtOrderModel.address_index.desc()).first()
            next_idx = (all_orders.address_index + 1) if all_orders else 0

            address = self._derive_trc20_address_from_xpub(cfg["xpub_trc20"], next_idx)

            order = UsdtOrderModel(
                user_id=user_id,
                plan=plan,
                chain="TRC20",
                amount_usdt=amount,
                address_index=next_idx,
                address=address,
                status="pending",
                expires_at=expires_at,
            )
            session.add(order)
            session.commit()
            order_id = order.id
            session.close()

            return True, "success", {
                "order_id": order_id,
                "plan": plan,
                "chain": "TRC20",
                "amount_usdt": str(amount),
                "address": address,
                "expires_at": expires_at.isoformat(),
            }
        except Exception as e:
            session.rollback()
            session.close()
            logger.error(f"create_order failed: {e}", exc_info=True)
            return False, f"error:{str(e)}", {}

    def get_order(self, user_id: str, order_id: int, refresh: bool = True) -> Tuple[bool, str, Dict[str, Any]]:
        """获取订单详情，可选刷新链上状态"""
        session = BillingStore.get_session()
        try:
            row = session.query(UsdtOrderModel).filter_by(id=order_id, user_id=user_id).first()
            session.close()

            if not row:
                return False, "order_not_found", {}

            if refresh:
                try:
                    self._refresh_one_order_out_of_tx(row)
                except Exception as e:
                    logger.warning(f"get_order refresh failed order_id={order_id}: {e}")

                # 重新读取
                session = BillingStore.get_session()
                row = session.query(UsdtOrderModel).filter_by(id=order_id, user_id=user_id).first()
                session.close()

            return True, "success", self._row_to_dict(row)
        except Exception as e:
            session.close()
            logger.error(f"get_order failed: {e}", exc_info=True)
            return False, f"error:{str(e)}", {}

    @staticmethod
    def _coerce_utc_datetime(val: Any) -> Optional[datetime]:
        if val is None:
            return None
        if isinstance(val, datetime):
            dt = val
        elif isinstance(val, str):
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            except Exception:
                return None
        else:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _row_to_dict(self, row: UsdtOrderModel) -> Dict[str, Any]:
        return {
            "order_id": row.id,
            "plan": row.plan,
            "chain": row.chain,
            "amount_usdt": str(row.amount_usdt or 0),
            "address": row.address or "",
            "status": row.status or "",
            "tx_hash": row.tx_hash or "",
            "paid_at": row.paid_at.isoformat() if row.paid_at else None,
            "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # -------------------- Chain check --------------------

    def _find_trc20_usdt_incoming(
        self, address: str, amount_usdt: Decimal, created_at: Optional[Any]
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """查询 TronGrid 匹配转账记录"""
        cfg = self._get_cfg()
        base = cfg["trongrid_base"]
        contract = cfg["usdt_trc20_contract"]
        address = (address or "").strip()
        page_limit = int(cfg.get("trongrid_page_limit", 200))
        max_pages = int(cfg.get("trongrid_max_pages", 5))

        url = f"{base}/v1/accounts/{address}/transactions/trc20"
        headers: Dict[str, str] = {}
        if cfg["trongrid_key"]:
            headers["TRON-PRO-API-KEY"] = cfg["trongrid_key"]

        target = int((amount_usdt * Decimal("1000000")).to_integral_value())

        min_ts = None
        ct_parsed = self._coerce_utc_datetime(created_at)
        if ct_parsed:
            min_ts = int(ct_parsed.timestamp() * 1000) - 60_000

        fingerprint: Optional[str] = None
        total_scanned = 0
        pages_fetched = 0
        wrong_to = before_order = underpaid = parse_err = 0

        try:
            for _ in range(max_pages):
                params: Dict[str, Any] = {
                    "only_to": "true",
                    "limit": page_limit,
                    "contract_address": contract,
                    "only_confirmed": "true",
                }
                if fingerprint:
                    params["fingerprint"] = fingerprint

                resp = requests.get(url, params=params, headers=headers, timeout=15)
                if resp.status_code != 200:
                    body_head = (resp.text or "")[:200].replace("\n", " ")
                    return None, f"trongrid_http={resp.status_code} body_head={body_head!r}"

                data = resp.json() or {}
                items = data.get("data") or []
                pages_fetched += 1
                total_scanned += len(items)

                for it in items:
                    try:
                        if (it.get("to") or "").strip() != address:
                            wrong_to += 1
                            continue
                        bts = int(it.get("block_timestamp") or 0)
                        if min_ts and bts < min_ts:
                            before_order += 1
                            continue
                        val = int(it.get("value") or 0)
                        if val < target:
                            underpaid += 1
                            continue
                        return it, f"ok pages={pages_fetched} scanned={total_scanned}"
                    except Exception:
                        parse_err += 1
                        continue

                meta = data.get("meta") or {}
                fingerprint = meta.get("fingerprint") if isinstance(meta.get("fingerprint"), str) else None
                if not fingerprint or len(items) < page_limit:
                    break

            parts = [
                f"scanned_items={total_scanned}",
                f"pages={pages_fetched}",
                f"wrong_to={wrong_to}",
                f"before_order={before_order}",
                f"underpaid={underpaid}",
                f"parse_err={parse_err}",
            ]
            return None, "no_match " + " ".join(parts)
        except Exception as e:
            return None, f"trongrid_request_error:{type(e).__name__}:{e}"

    # -------------------- Out-of-transaction refresh --------------------

    def _refresh_one_order_out_of_tx(self, row: UsdtOrderModel) -> None:
        """刷新单个订单链上状态。HTTP 在事务外执行，DB 写入用短事务。"""
        cfg = self._get_cfg()
        status = (row.status or "").lower()
        chain = (row.chain or "").upper()
        order_id = row.id
        now = datetime.now(timezone.utc)

        if chain != "TRC20":
            return
        if status not in ("pending", "paid", "expired"):
            return

        address = row.address or ""
        amount = Decimal(str(row.amount_usdt or 0))
        if not address or amount <= 0:
            return

        if status == "paid":
            confirm_sec = int(cfg.get("confirm_seconds", 30))
            paid_at = self._coerce_utc_datetime(row.paid_at)
            ready = False
            if paid_at and (now - paid_at).total_seconds() >= confirm_sec:
                ready = True
            elif not paid_at and confirm_sec <= 0:
                ready = True
            if ready:
                self._confirm_and_activate_short_tx(order_id, row.user_id, row.plan, row.tx_hash or "")
            return

        tx, chain_note = self._find_trc20_usdt_incoming(address, amount, row.created_at)
        if not tx and chain_note and (
            chain_note.startswith("trongrid_http=") or chain_note.startswith("trongrid_request_error:")
        ):
            logger.warning("USDT reconcile TronGrid error order_id=%s %s", order_id, chain_note)

        if cfg.get("debug_reconcile_log"):
            logger.info(
                "USDT reconcile scan order_id=%s status=%s amount=%s addr=%s note=%s",
                order_id,
                status,
                amount,
                address,
                chain_note if not tx else f"matched_tx={tx.get('transaction_id')}",
            )

        if tx:
            tx_hash = tx.get("transaction_id") or ""
            paid_at = datetime.now(timezone.utc)
            try:
                session = BillingStore.get_session()
                session.query(UsdtOrderModel).filter_by(id=order_id).update({
                    "status": "paid",
                    "tx_hash": tx_hash,
                    "paid_at": paid_at,
                    "updated_at": paid_at,
                })
                session.commit()
                session.close()
            except Exception as e:
                logger.error(f"USDT mark_paid UPDATE failed order_id={order_id}: {e}")
                return

            confirm_sec = int(cfg.get("confirm_seconds", 30))
            try:
                tx_ts = tx.get("block_timestamp")
                if tx_ts:
                    tx_time = datetime.fromtimestamp(int(tx_ts) / 1000.0, tz=timezone.utc)
                    if (now - tx_time).total_seconds() >= confirm_sec:
                        self._confirm_and_activate_short_tx(order_id, row.user_id, row.plan, tx_hash)
                elif confirm_sec <= 0:
                    self._confirm_and_activate_short_tx(order_id, row.user_id, row.plan, tx_hash)
            except Exception:
                pass
            return

        if status == "pending":
            exp = self._coerce_utc_datetime(row.expires_at)
            if exp is not None and exp <= now:
                try:
                    session = BillingStore.get_session()
                    session.query(UsdtOrderModel).filter_by(id=order_id).update({
                        "status": "expired",
                        "updated_at": now,
                    })
                    session.commit()
                    session.close()
                except Exception as e:
                    logger.warning(f"USDT mark_expired UPDATE failed order_id={order_id}: {e}")

    def _confirm_and_activate_short_tx(self, order_id: int, user_id: str, plan: str, tx_hash: str) -> None:
        """幂等确认订单并激活会员"""
        try:
            session = BillingStore.get_session()
            current = session.query(UsdtOrderModel).filter_by(id=order_id).first()
            if current and (current.status or "").lower() == "confirmed":
                session.close()
                return

            session.query(UsdtOrderModel).filter_by(id=order_id).update({
                "status": "confirmed",
                "confirmed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            })
            session.commit()
            session.close()
        except Exception as e:
            logger.error(f"USDT confirm UPDATE failed order_id={order_id}: {e}")
            return

        try:
            ok, msg, _ = self.billing.purchase_membership(
                user_id,
                plan,
                fulfillment_ref=f"usdt_order:{order_id}",
            )
            logger.info(f"USDT activate membership: order={order_id} user={user_id} plan={plan} ok={ok} msg={msg}")
        except Exception as e:
            logger.error(f"USDT activate membership failed: order={order_id} err={e}", exc_info=True)

    # -------------------- Batch refresh --------------------

    def refresh_all_active_orders(self) -> int:
        """批量刷新所有 pending/paid 订单。返回状态变更数。"""
        updated = 0
        try:
            session = BillingStore.get_session()
            rows = (
                session.query(UsdtOrderModel)
                .filter(UsdtOrderModel.status.in_(("pending", "paid")))
                .order_by(UsdtOrderModel.created_at.asc())
                .limit(100)
                .all()
            )
            session.close()

            for row in rows:
                order_id = row.id
                old_status = (row.status or "").lower()
                try:
                    self._refresh_one_order_out_of_tx(row)
                except Exception as e:
                    logger.debug(f"refresh_all: order {order_id} error: {e}")
                    continue

                try:
                    session = BillingStore.get_session()
                    new_row = session.query(UsdtOrderModel).filter_by(id=order_id).first()
                    session.close()
                    new_status = (new_row.status or "").lower() if new_row else old_status
                    if new_status != old_status:
                        updated += 1
                        logger.info(f"USDT order {order_id}: {old_status} -> {new_status}")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"refresh_all_active_orders error: {e}", exc_info=True)
        return updated


# ==================== Background Worker ====================

class UsdtOrderWorker:
    """后台线程：定期扫描 USDT 订单链上状态"""

    def __init__(self, poll_interval_sec: float = 30.0):
        self.poll_interval_sec = float(poll_interval_sec)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pay_disabled_logged = False

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="UsdtOrderWorker", daemon=True)
            self._thread.start()
            logger.info("UsdtOrderWorker started (interval=%ss)", self.poll_interval_sec)
            return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("UsdtOrderWorker stopped")

    def _run_loop(self) -> None:
        self._stop_event.wait(timeout=10)
        while not self._stop_event.is_set():
            try:
                svc = get_usdt_payment_service()
                cfg = svc._get_cfg()
                if cfg["enabled"]:
                    updated = svc.refresh_all_active_orders()
                    if updated > 0:
                        logger.info(f"UsdtOrderWorker: refreshed {updated} orders")
                else:
                    if not self._pay_disabled_logged:
                        logger.info("UsdtOrderWorker: USDT pay disabled — worker runs but skips reconcile")
                        self._pay_disabled_logged = True
            except Exception as e:
                logger.error(f"UsdtOrderWorker loop error: {e}", exc_info=True)

            self._stop_event.wait(timeout=self.poll_interval_sec)


# ==================== Singletons ====================

_svc: Optional[UsdtPaymentService] = None
_worker: Optional[UsdtOrderWorker] = None


def get_usdt_payment_service() -> UsdtPaymentService:
    global _svc
    if _svc is None:
        _svc = UsdtPaymentService()
    return _svc


def get_usdt_order_worker() -> UsdtOrderWorker:
    global _worker
    if _worker is None:
        interval = float(os.getenv("STOCK_ASSISTANT_USDT_WORKER_POLL_INTERVAL", "30"))
        _worker = UsdtOrderWorker(poll_interval_sec=interval)
    return _worker
