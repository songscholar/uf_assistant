"""
UF Stock Assistant — 费用计算引擎
支持普通委托、大宗交易、港股通、ETF 等多业务类型的费用计算
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.core.constants import TradeType
from app.core.logging import get_logger

logger = get_logger("app.trading.fees")


# ── 默认费率表 ───────────────────────────────────────────────────────────────

FEE_RATES = {
    # 普通委托（A股）
    TradeType.NORMAL: {
        "commission_rate": Decimal("0.0003"),      # 佣金 0.03%（双向）
        "stamp_tax_rate": Decimal("0.001"),        # 印花税 0.1%（卖出单向）
        "transfer_fee_rate": Decimal("0.00002"),   # 过户费 0.002%（双向）
        "exchange_fee_rate": Decimal("0.0000487"), # 证管费 0.00487%（双向）
        "min_commission": Decimal("5"),            # 最低佣金 5元
    },
    # 大宗交易
    TradeType.BLOCK_TRADE: {
        "commission_rate": Decimal("0.0003"),      # 佣金可协商
        "stamp_tax_rate": Decimal("0.001"),        # 印花税 0.1%（卖出单向）
        "transfer_fee_rate": Decimal("0.00002"),   # 过户费
        "exchange_fee_rate": Decimal("0.00003409"),# 经手费下浮30%后
        "min_commission": Decimal("5"),
    },
    # 港股通
    TradeType.STOCK_CONNECT_SH: {
        "commission_rate": Decimal("0.0003"),      # 佣金 0.03%（双向）
        "stamp_tax_rate": Decimal("0.001"),        # 印花税 0.1%（双向）
        "exchange_fee_rate": Decimal("0.00005"),   # 交收费 0.005%（最低2元，最高100元）
        "system_fee_rate": Decimal("0.5"),         # 交易系统使用费 0.5港币/笔
        "portfolio_fee_rate": Decimal("0.00008"),  # 组合费 年化0.08%（按日）
        "min_commission": Decimal("5"),
    },
    TradeType.STOCK_CONNECT_SZ: {
        "commission_rate": Decimal("0.0003"),
        "stamp_tax_rate": Decimal("0.001"),
        "exchange_fee_rate": Decimal("0.00005"),
        "system_fee_rate": Decimal("0.5"),
        "portfolio_fee_rate": Decimal("0.00008"),
        "min_commission": Decimal("5"),
    },
    # ETF 交易
    TradeType.ETF_CREATION: {
        "commission_rate": Decimal("0.0003"),
        "stamp_tax_rate": Decimal("0"),            # ETF 免印花税
        "transfer_fee_rate": Decimal("0"),         # ETF 免过户费
        "exchange_fee_rate": Decimal("0.0000487"),
        "min_commission": Decimal("5"),
    },
    TradeType.ETF_REDEMPTION: {
        "commission_rate": Decimal("0.0003"),
        "stamp_tax_rate": Decimal("0"),
        "transfer_fee_rate": Decimal("0"),
        "exchange_fee_rate": Decimal("0.0000487"),
        "min_commission": Decimal("5"),
    },
}


# ── 费用结果数据结构 ─────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class FeeResult:
    """费用计算结果"""
    commission: Decimal      # 佣金
    stamp_tax: Decimal       # 印花税
    exchange_fee: Decimal    # 交易所费用（经手费/交收费等）
    transfer_fee: Decimal    # 过户费
    system_fee: Decimal      # 交易系统使用费（港股通）
    portfolio_fee: Decimal   # 组合费（港股通）
    other_fees: Decimal      # 其他费用
    total: Decimal           # 总费用

    def to_dict(self) -> dict[str, float]:
        return {
            "commission": float(self.commission),
            "stamp_tax": float(self.stamp_tax),
            "exchange_fee": float(self.exchange_fee),
            "transfer_fee": float(self.transfer_fee),
            "system_fee": float(self.system_fee),
            "portfolio_fee": float(self.portfolio_fee),
            "other_fees": float(self.other_fees),
            "total": float(self.total),
        }


# ── 费用计算函数 ─────────────────────────────────────────────────────────────

def calculate_fees(
    trade_type: TradeType,
    side: str,
    quantity: float,
    price: float,
    *,
    exchange_code: str = "SH",
    reference_rate: float | None = None,
) -> FeeResult:
    """
    计算交易费用

    Args:
        trade_type: 业务类型
        side: buy / sell
        quantity: 数量
        price: 价格
        exchange_code: 交易所代码（SH/SZ/HK）
        reference_rate: 参考汇率（港股通用）

    Returns:
        FeeResult
    """
    rates = FEE_RATES.get(trade_type, FEE_RATES[TradeType.NORMAL])
    amount = Decimal(str(quantity)) * Decimal(str(price))

    # 佣金（双向或按规则）
    commission = amount * rates.get("commission_rate", Decimal("0"))
    min_commission = rates.get("min_commission", Decimal("0"))
    if commission < min_commission and commission > 0:
        commission = min_commission

    # 印花税
    stamp_tax_rate = rates.get("stamp_tax_rate", Decimal("0"))
    if trade_type in (TradeType.NORMAL, TradeType.BLOCK_TRADE, TradeType.ETF_CREATION, TradeType.ETF_REDEMPTION):
        # A股/ETF：卖出单向
        stamp_tax = amount * stamp_tax_rate if side == "sell" else Decimal("0")
    elif trade_type in (TradeType.STOCK_CONNECT_SH, TradeType.STOCK_CONNECT_SZ):
        # 港股通：双向
        stamp_tax = amount * stamp_tax_rate
    else:
        stamp_tax = Decimal("0")

    # 过户费
    transfer_fee = amount * rates.get("transfer_fee_rate", Decimal("0"))

    # 交易所费用（经手费/交收费）
    exchange_fee = amount * rates.get("exchange_fee_rate", Decimal("0"))

    # 港股通特有费用
    system_fee = Decimal("0")
    portfolio_fee = Decimal("0")
    if trade_type in (TradeType.STOCK_CONNECT_SH, TradeType.STOCK_CONNECT_SZ):
        # 交易系统使用费：0.5港币/笔
        system_fee = rates.get("system_fee_rate", Decimal("0"))
        # 组合费：年化0.08%，按日计算（简化：按成交金额一次性计算）
        portfolio_fee = amount * rates.get("portfolio_fee_rate", Decimal("0"))

    # 其他费用
    other_fees = Decimal("0")

    total = commission + stamp_tax + transfer_fee + exchange_fee + system_fee + portfolio_fee + other_fees

    logger.info(
        "fees_calculated",
        trade_type=trade_type,
        side=side,
        amount=float(amount),
        commission=float(commission),
        stamp_tax=float(stamp_tax),
        total=float(total),
    )

    return FeeResult(
        commission=quantize(commission),
        stamp_tax=quantize(stamp_tax),
        exchange_fee=quantize(exchange_fee),
        transfer_fee=quantize(transfer_fee),
        system_fee=quantize(system_fee),
        portfolio_fee=quantize(portfolio_fee),
        other_fees=quantize(other_fees),
        total=quantize(total),
    )


def quantize(value: Decimal, places: int = 2) -> Decimal:
    """四舍五入到指定小数位"""
    return value.quantize(Decimal("0.01") ** (places // 2) if places <= 2 else Decimal("0.0001"), rounding=ROUND_HALF_UP)


def get_settlement_mode(trade_type: TradeType, exchange_code: str = "SH") -> str:
    """
    根据业务类型和交易所返回交收模式

    Returns:
        "T+0" / "T+1" / "T+2"
    """
    from app.core.constants import SettlementMode

    mapping = {
        TradeType.NORMAL: SettlementMode.T1,
        TradeType.BLOCK_TRADE: SettlementMode.T1,  # 默认担保交收 T+1
        TradeType.STOCK_CONNECT_SH: SettlementMode.T2,
        TradeType.STOCK_CONNECT_SZ: SettlementMode.T2,
        TradeType.ETF_CREATION: SettlementMode.T1,
        TradeType.ETF_REDEMPTION: SettlementMode.T1,
    }

    # 大宗交易非担保交收例外
    if trade_type == TradeType.BLOCK_TRADE:
        if exchange_code == "SZ":
            return SettlementMode.T0  # 深圳非担保 T+0
        # 上海非担保为 T+1，担保为 T+1

    return mapping.get(trade_type, SettlementMode.T1)


def check_block_trade_limits(
    trade_type: TradeType,
    symbol: str,
    quantity: float,
    price: float,
    exchange_code: str,
) -> tuple[bool, str]:
    """
    检查大宗交易最低限额

    Returns:
        (是否通过, 错误信息)
    """
    if trade_type != TradeType.BLOCK_TRADE:
        return True, ""

    amount = quantity * price

    # 简化：根据交易所和代码前缀判断品种
    # A股：60/68/00/30 开头
    # 基金：50/51/15/16 开头
    # 债券：11/12/13 开头
    prefix = symbol[:2] if len(symbol) >= 2 else ""

    limits = {
        "SH": {
            "A": {"min_qty": 300_000, "min_amount": 2_000_000},
            "B": {"min_qty": 300_000, "min_amount": 200_000},
            "F": {"min_qty": 2_000_000, "min_amount": 2_000_000},
        },
        "SZ": {
            "A": {"min_qty": 300_000, "min_amount": 2_000_000},
            "B": {"min_qty": 30_000, "min_amount": 200_000},
            "F": {"min_qty": 2_000_000, "min_amount": 2_000_000},
        },
    }

    exchange = limits.get(exchange_code, limits["SH"])

    # 简单分类
    if prefix in ("60", "68", "00", "30"):
        category = "A"
    elif prefix in ("90", "20"):
        category = "B"
    elif prefix in ("50", "51", "15", "16", "18"):
        category = "F"
    else:
        category = "A"

    limit = exchange.get(category, exchange["A"])
    min_qty = limit["min_qty"]
    min_amount = limit["min_amount"]

    if quantity < min_qty and amount < min_amount:
        return False, f"大宗交易限额不足：数量需≥{min_qty}股或金额需≥{min_amount}元，当前{quantity}股/{amount:.2f}元"

    return True, ""
