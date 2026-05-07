"""
Symbol normalization helpers.

Convert canonical "BASE/QUOTE" or "BASE/QUOTE:SETTLE" symbols into
exchange-specific identifiers.
"""

from __future__ import annotations


def to_binance_futures_symbol(canonical: str) -> str:
    """BTC/USDT:USDT -> BTCUSDT"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1].split(":")[0] if "/" in canonical else "USDT"
    return f"{base}{quote}"


def to_binance_spot_symbol(canonical: str) -> str:
    """BTC/USDT -> BTCUSDT"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1] if "/" in canonical else "USDT"
    return f"{base}{quote}"


def to_okx_swap_inst_id(canonical: str) -> str:
    """BTC/USDT:USDT -> BTC-USDT-SWAP"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    return f"{base}-USDT-SWAP"


def to_okx_spot_inst_id(canonical: str) -> str:
    """BTC/USDT -> BTC-USDT"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1] if "/" in canonical else "USDT"
    return f"{base}-{quote}"


def to_bitget_um_symbol(canonical: str) -> str:
    """BTC/USDT:USDT -> BTCUSDT"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1].split(":")[0] if "/" in canonical else "USDT"
    return f"{base}{quote}"


def to_bybit_symbol(canonical: str) -> str:
    """BTC/USDT:USDT -> BTCUSDT"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1].split(":")[0] if "/" in canonical else "USDT"
    return f"{base}{quote}"


def to_coinbase_product_id(canonical: str) -> str:
    """BTC/USDT -> BTC-USDT"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1] if "/" in canonical else "USDT"
    return f"{base}-{quote}"


def to_kraken_pair(canonical: str) -> str:
    """
    BTC/USDT -> XBTUSDT (Kraken uses XBT for BTC).
    """
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1] if "/" in canonical else "USDT"
    if base.upper() == "BTC":
        base = "XBT"
    return f"{base}{quote}"


def to_kucoin_symbol(canonical: str) -> str:
    """BTC/USDT -> BTC-USDT"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1] if "/" in canonical else "USDT"
    return f"{base}-{quote}"


def to_kucoin_futures_symbol(canonical: str) -> str:
    """
    BTC/USDT:USDT -> XBTUSDTM (KuCoin futures uses XBT for BTC and USDTM suffix).
    """
    base = canonical.split("/")[0] if "/" in canonical else canonical
    if base.upper() == "BTC":
        base = "XBT"
    return f"{base}USDTM"


def to_kraken_futures_symbol(canonical: str) -> str:
    """
    BTC/USDT:USDT -> PF_XBTUSD (best-effort).
    """
    base = canonical.split("/")[0] if "/" in canonical else canonical
    if base.upper() == "BTC":
        base = "XBT"
    return f"PF_{base}USD"


def to_gate_currency_pair(canonical: str) -> str:
    """BTC/USDT -> BTC_USDT"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1] if "/" in canonical else "USDT"
    return f"{base}_{quote}"


def to_deepcoin_symbol(canonical: str) -> str:
    """BTC/USDT -> BTC-USDT (perp: BTC-USDT-SWAP)"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote_part = canonical.split("/")[1] if "/" in canonical else "USDT"
    # Strip :SETTLE suffix (e.g. :USDT)
    quote = quote_part.split(":")[0] if ":" in quote_part else quote_part
    if ":" in canonical:
        return f"{base}-{quote}-SWAP"
    return f"{base}-{quote}"


def to_htx_spot_symbol(canonical: str) -> str:
    """BTC/USDT -> btcusdt (lowercase)"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1] if "/" in canonical else "USDT"
    return f"{base.lower()}{quote.lower()}"


def to_htx_contract_code(canonical: str) -> str:
    """BTC/USDT:USDT -> BTC-USDT"""
    base = canonical.split("/")[0] if "/" in canonical else canonical
    quote = canonical.split("/")[1].split(":")[0] if "/" in canonical else "USDT"
    return f"{base}-{quote}"
