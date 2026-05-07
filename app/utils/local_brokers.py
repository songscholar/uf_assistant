"""
Local desktop brokers (IBKR TWS/Gateway, MetaTrader 5).

These require software running on the same machine as the API process
(or reachable private network). SaaS / single-container cloud installs
cannot reach the user's home PC by default — gate with env.
"""

from __future__ import annotations

from app.core.config import settings


def local_desktop_brokers_allowed() -> bool:
    """When False, IBKR/MT5 credential creation and related flows are rejected."""
    return settings.local_broker.allowed


def desktop_broker_cloud_reject_message() -> str:
    return (
        "当前部署环境已关闭 IBKR / MT5（需本机 TWS、IB Gateway 或 MT5 终端）。"
        "请在个人电脑或私有服务器上本地部署，并安装 Interactive Brokers TWS/Gateway 或 MetaTrader 5。"
        " | This server has disabled IBKR/MT5 (requires local TWS/Gateway or MT5). "
        "Deploy on your own machine and install IBKR or MetaTrader 5."
    )
