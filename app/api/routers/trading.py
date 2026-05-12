"""
UF Stock Assistant — 交易接口（支持模拟 + 实盘）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.core.constants import MarketType, TradingMode
from app.core.exceptions import CredentialError, TradingError
from app.core.logging import get_logger
from app.trading.fees import calculate_fees
from app.core.constants import TradeType
from app.tools.trading import (
    cancel_order,
    get_orders,
    get_portfolio,
    get_positions,
    submit_order,
)

logger = get_logger("app.api.trading")

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── 模拟交易接口（保持兼容） ─────────────────────────────────────────────────

class OrderRequest(BaseModel):
    """下单请求"""
    symbol: str = Field(..., description="股票代码")
    side: str = Field(..., description="buy 或 sell")
    quantity: float = Field(..., gt=0, description="数量")
    price: float | None = Field(None, description="价格（限价单必填）")
    order_type: str = Field("market", description="market/limit/stop/stop_limit")
    trade_type: str = Field("normal", description="normal/block/hk_sh/hk_sz/etf_create/etf_redeem")
    exchange_code: str = Field("SH", description="SH/SZ/HK")


@router.post("/trading/order")
async def place_order(request: OrderRequest, current_user: dict = Depends(get_current_user)):
    """提交模拟订单（支持多业务类型）"""
    try:
        return submit_order(
            user_id=current_user["user_id"],
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            order_type=request.order_type,
            trade_type=request.trade_type,
            exchange_code=request.exchange_code,
        )
    except TradingError as exc:
        logger.warning("place_order_business_error", user_id=current_user["user_id"], error=str(exc))
        raise HTTPException(status_code=400, detail="交易参数有误，请检查后重试")
    except Exception as exc:
        logger.error("place_order_error", user_id=current_user["user_id"], error=str(exc))
        raise HTTPException(status_code=500, detail="下单失败，请稍后重试")


class FeeEstimateRequest(BaseModel):
    """费用预估请求"""
    symbol: str = Field(..., description="股票代码")
    side: str = Field(..., description="buy 或 sell")
    quantity: float = Field(..., gt=0, description="数量")
    price: float = Field(..., gt=0, description="价格")
    trade_type: str = Field("normal", description="normal/block/hk_sh/hk_sz/etf_create/etf_redeem")
    exchange_code: str = Field("SH", description="SH/SZ/HK")


@router.post("/trading/fee-estimate")
async def fee_estimate(request: FeeEstimateRequest):
    """费用预估（买入/卖出费用明细）"""
    try:
        fee_result = calculate_fees(
            TradeType(request.trade_type),
            request.side,
            request.quantity,
            request.price,
            exchange_code=request.exchange_code,
        )
        return {
            "symbol": request.symbol,
            "side": request.side,
            "quantity": request.quantity,
            "price": request.price,
            "amount": round(request.quantity * request.price, 2),
            "fees": fee_result.to_dict(),
        }
    except Exception as exc:
        logger.error("fee_estimate_error", error=str(exc))
        raise HTTPException(status_code=500, detail="费用计算失败")


@router.get("/trading/positions")
async def positions(current_user: dict = Depends(get_current_user)):
    """获取模拟持仓"""
    try:
        return get_positions(user_id=current_user["user_id"])
    except Exception as exc:
        logger.error("positions_error", user_id=current_user["user_id"], error=str(exc))
        raise HTTPException(status_code=500, detail="获取持仓失败，请稍后重试")


@router.get("/trading/position/{symbol}")
async def position(symbol: str, current_user: dict = Depends(get_current_user)):
    """获取指定股票模拟持仓"""
    try:
        result = get_positions(user_id=current_user["user_id"])
        for pos in result.get("positions", []):
            if pos.get("symbol") == symbol.upper():
                return {"has_position": True, "position": pos}
        return {"symbol": symbol, "has_position": False}
    except Exception as exc:
        logger.error("position_error", user_id=current_user["user_id"], symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail="获取持仓失败，请稍后重试")


@router.get("/trading/orders")
async def orders(status: str | None = None, current_user: dict = Depends(get_current_user)):
    """获取模拟订单列表"""
    try:
        return get_orders(user_id=current_user["user_id"], status=status)
    except Exception as exc:
        logger.error("orders_error", user_id=current_user["user_id"], error=str(exc))
        raise HTTPException(status_code=500, detail="获取订单列表失败，请稍后重试")


@router.delete("/trading/orders/{order_id}")
async def cancel(order_id: str, current_user: dict = Depends(get_current_user)):
    """取消模拟订单"""
    try:
        return cancel_order(user_id=current_user["user_id"], order_id=order_id)
    except Exception as exc:
        logger.error("cancel_error", user_id=current_user["user_id"], order_id=order_id, error=str(exc))
        raise HTTPException(status_code=500, detail="取消订单失败，请稍后重试")


@router.get("/trading/portfolio")
async def portfolio(current_user: dict = Depends(get_current_user)):
    """获取模拟投资组合"""
    try:
        return get_portfolio(user_id=current_user["user_id"])
    except Exception as exc:
        logger.error("portfolio_error", user_id=current_user["user_id"], error=str(exc))
        raise HTTPException(status_code=500, detail="获取投资组合失败，请稍后重试")


# ── 实盘交易接口 ─────────────────────────────────────────────────────────────

class LiveOrderRequest(BaseModel):
    """实盘下单请求"""
    market: str = Field(..., description="市场: crypto, a_share, us_stock")
    symbol: str = Field(..., description="交易对/股票代码，如 BTC/USDT 或 600519")
    side: str = Field(..., description="buy 或 sell")
    order_type: str = Field("market", description="market/limit")
    quantity: float = Field(..., gt=0, description="数量")
    price: float | None = Field(None, description="价格（限价单必填）")
    strategy_id: str | None = Field(None, description="策略ID（自动交易时填写）")


def _get_trading_db():
    from app.trading.models import get_db_session
    return get_db_session()


@router.post("/trading/live/order")
async def live_order(request: LiveOrderRequest):
    """实盘下单"""
    try:
        from app.trading.backend_router import BackendRouter
        from app.trading.order_manager import OrderManager

        db = _get_trading_db()
        try:
            router_instance = BackendRouter(db, mode=TradingMode.LIVE)
            backend = await router_instance.get_backend(request.market)
            manager = OrderManager(db, backend, TradingMode.LIVE)

            order = await manager.submit_order(
                market=request.market,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                quantity=request.quantity,
                price=request.price,
                strategy_id=request.strategy_id,
            )

            return {
                "order_id": order.id,
                "status": order.status,
                "exchange_order_id": order.exchange_order_id,
                "filled_quantity": order.filled_quantity,
                "filled_price": order.filled_price,
                "fee": order.fee,
                "market": order.market,
                "symbol": order.symbol,
                "side": order.side,
                "mode": order.mode,
                "created_at": order.created_at.isoformat() if order.created_at else None,
            }
        finally:
            db.close()
    except CredentialError as exc:
        logger.warning("live_order_no_credential", error=str(exc))
        raise HTTPException(status_code=403, detail="未配置交易凭证或凭证无效，请先检查凭证设置")
    except Exception as exc:
        logger.error("live_order_error", error=str(exc))
        raise HTTPException(status_code=500, detail="实盘下单失败，请稍后重试")


@router.get("/trading/live/orders")
async def live_orders(
    market: str | None = Query(None, description="筛选市场"),
    status: str | None = Query(None, description="筛选状态"),
    limit: int = Query(50, ge=1, le=200),
):
    """实盘订单列表"""
    try:
        from app.trading.backend_router import BackendRouter
        from app.trading.order_manager import OrderManager

        db = _get_trading_db()
        try:
            router_instance = BackendRouter(db, mode=TradingMode.LIVE)
            # 使用 mock backend 只读 DB（不需要真实连接）
            from app.trading.backends.mock_backend import MockBackend
            backend = MockBackend()
            manager = OrderManager(db, backend, TradingMode.LIVE)

            orders_list = manager.list_orders(status=status, market=market, limit=limit)
            return {
                "orders": [
                    {
                        "id": o.id,
                        "market": o.market,
                        "symbol": o.symbol,
                        "side": o.side,
                        "order_type": o.order_type,
                        "quantity": o.quantity,
                        "price": o.price,
                        "status": o.status,
                        "filled_quantity": o.filled_quantity,
                        "filled_price": o.filled_price,
                        "fee": o.fee,
                        "strategy_id": o.strategy_id,
                        "mode": o.mode,
                        "created_at": o.created_at.isoformat() if o.created_at else None,
                    }
                    for o in orders_list
                ]
            }
        finally:
            db.close()
    except Exception as exc:
        logger.error("live_orders_error", error=str(exc))
        raise HTTPException(status_code=500, detail="获取订单列表失败，请稍后重试")


@router.post("/trading/live/cancel/{order_id}")
async def live_cancel(order_id: str, market: str = Query(...)):
    """取消实盘订单"""
    try:
        from app.trading.backend_router import BackendRouter
        from app.trading.order_manager import OrderManager

        db = _get_trading_db()
        try:
            router_instance = BackendRouter(db, mode=TradingMode.LIVE)
            backend = await router_instance.get_backend(market)
            manager = OrderManager(db, backend, TradingMode.LIVE)
            order = await manager.cancel_order(order_id)
            return {"order_id": order.id, "status": order.status}
        finally:
            db.close()
    except CredentialError as exc:
        logger.warning("live_cancel_no_credential", order_id=order_id, error=str(exc))
        raise HTTPException(status_code=403, detail="未配置交易凭证或凭证无效，请先检查凭证设置")
    except Exception as exc:
        logger.error("live_cancel_error", order_id=order_id, error=str(exc))
        raise HTTPException(status_code=500, detail="取消订单失败，请稍后重试")


@router.get("/trading/live/positions")
async def live_positions(market: str | None = Query(None)):
    """实盘持仓"""
    try:
        from app.trading.position_sync import PositionSyncer
        from app.trading.backends.mock_backend import MockBackend

        db = _get_trading_db()
        try:
            syncer = PositionSyncer(db, MockBackend(), TradingMode.LIVE)
            positions_list = syncer.get_positions(market=market)
            return {
                "positions": [
                    {
                        "id": p.id,
                        "market": p.market,
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "avg_cost": p.avg_cost,
                        "current_price": p.current_price,
                        "unrealized_pnl": p.unrealized_pnl,
                        "realized_pnl": p.realized_pnl,
                        "mode": p.mode,
                    }
                    for p in positions_list
                ]
            }
        finally:
            db.close()
    except Exception as exc:
        logger.error("live_positions_error", error=str(exc))
        raise HTTPException(status_code=500, detail="获取持仓失败，请稍后重试")


@router.post("/trading/live/sync")
async def live_sync(market: str = Query(...)):
    """从交易所同步持仓"""
    try:
        from app.trading.backend_router import BackendRouter
        from app.trading.position_sync import PositionSyncer

        db = _get_trading_db()
        try:
            router_instance = BackendRouter(db, mode=TradingMode.LIVE)
            backend = await router_instance.get_backend(market)
            syncer = PositionSyncer(db, backend, TradingMode.LIVE)
            positions_list = await syncer.sync_positions(market)
            return {
                "message": f"同步完成，共 {len(positions_list)} 个持仓",
                "positions": [
                    {
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "avg_cost": p.avg_cost,
                        "current_price": p.current_price,
                    }
                    for p in positions_list
                ],
            }
        finally:
            db.close()
    except CredentialError as exc:
        logger.warning("live_sync_no_credential", error=str(exc))
        raise HTTPException(status_code=403, detail="未配置交易凭证或凭证无效，请先检查凭证设置")
    except Exception as exc:
        logger.error("live_sync_error", error=str(exc))
        raise HTTPException(status_code=500, detail="同步持仓失败，请稍后重试")


@router.get("/trading/live/pnl")
async def live_pnl(market: str | None = Query(None)):
    """实盘盈亏统计"""
    try:
        from app.trading.pnl_tracker import PnLTracker

        db = _get_trading_db()
        try:
            tracker = PnLTracker(db, TradingMode.LIVE)
            return tracker.get_total_pnl(market=market)
        finally:
            db.close()
    except Exception as exc:
        logger.error("live_pnl_error", error=str(exc))
        raise HTTPException(status_code=500, detail="获取盈亏数据失败，请稍后重试")


@router.get("/trading/live/balance")
async def live_balance(market: str = Query(...)):
    """实盘账户余额"""
    try:
        from app.trading.backend_router import BackendRouter

        db = _get_trading_db()
        try:
            router_instance = BackendRouter(db, mode=TradingMode.LIVE)
            backend = await router_instance.get_backend(market)
            balance = await backend.get_balance()
            return {"market": market, "balance": balance}
        finally:
            db.close()
    except CredentialError as exc:
        logger.warning("live_balance_no_credential", error=str(exc))
        raise HTTPException(status_code=403, detail="未配置交易凭证或凭证无效，请先检查凭证设置")
    except Exception as exc:
        logger.error("live_balance_error", error=str(exc))
        raise HTTPException(status_code=500, detail="获取账户余额失败，请稍后重试")


@router.get("/trading/live/trades")
async def live_trades(
    market: str | None = Query(None),
    symbol: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """实盘交易历史"""
    try:
        from app.trading.pnl_tracker import PnLTracker

        db = _get_trading_db()
        try:
            tracker = PnLTracker(db, TradingMode.LIVE)
            trades = tracker.get_trade_history(symbol=symbol, market=market, limit=limit)
            return {"trades": trades}
        finally:
            db.close()
    except Exception as exc:
        logger.error("live_trades_error", error=str(exc))
        raise HTTPException(status_code=500, detail="获取交易历史失败，请稍后重试")
