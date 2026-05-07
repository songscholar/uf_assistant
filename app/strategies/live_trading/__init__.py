"""
UF Stock Assistant — Live Trading (native exchange clients)

Infrastructure ported from QuantDinger:
  - base.py        : BaseRestClient, LiveOrderResult, LiveTradingError
  - factory.py     : Exchange client factory + IBKR/MT5 support
  - symbols.py     : Symbol normalization per exchange
  - records.py     : Trade/position local DB snapshot
  - execution.py   : Signal-to-order dispatch
"""

from .base import BaseRestClient, LiveOrderResult, LiveTradingError
from .factory import create_client, exchange_demo_mode_enabled, query_fee_rate

__all__ = [
    "BaseRestClient",
    "LiveOrderResult",
    "LiveTradingError",
    "create_client",
    "exchange_demo_mode_enabled",
    "query_fee_rate",
]
