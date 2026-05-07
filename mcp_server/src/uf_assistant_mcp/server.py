"""
UF Stock Assistant — MCP Server 主程序

支持两种传输方式：
  1. stdio（默认）— 用于 Cursor / Claude Code / Codex 桌面版
  2. streamable-http — 用于云端 Agent / 浏览器 IDE

环境变量：
  UF_ASSISTANT_BASE_URL         — Agent Gateway 地址
  UF_ASSISTANT_AGENT_TOKEN      — Agent Token
  UF_ASSISTANT_MCP_TRANSPORT    — stdio（默认）或 streamable-http
  UF_ASSISTANT_MCP_HOST         — HTTP 模式监听地址
  UF_ASSISTANT_MCP_PORT         — HTTP 模式监听端口
"""

from __future__ import annotations

import os
import sys

from .client import AgentGatewayClient
from .tools import ALL_TOOLS, set_client


def _create_mcp_server():
    """创建 FastMCP Server 实例"""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        print(
            "ERROR: mcp package not installed.\n"
            "Run:  uv pip install mcp>=1.0.0\n"
            "Or:  pip install mcp>=1.0.0",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    server = FastMCP(
        "uf-assistant",
        instructions=(
            "Tools for the UF Stock Assistant self-hosted quant platform. "
            "All tools are scoped via the configured agent token. "
            "Trading is intentionally NOT exposed via MCP; use the REST API for that."
        ),
    )

    # 注册所有 tools
    for tool in ALL_TOOLS:
        server.add_tool(tool)

    return server


def main() -> None:
    """MCP Server 入口"""
    base_url = os.getenv("UF_ASSISTANT_BASE_URL", "http://localhost:8000")
    token = os.getenv("UF_ASSISTANT_AGENT_TOKEN", "")
    transport = os.getenv("UF_ASSISTANT_MCP_TRANSPORT", "stdio")
    host = os.getenv("UF_ASSISTANT_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("UF_ASSISTANT_MCP_PORT", "7800"))

    if not token:
        print(
            "WARNING: UF_ASSISTANT_AGENT_TOKEN is not set.\n"
            "Agent Gateway calls will fail with 401.\n"
            "Issue a token from the UF Assistant web UI: Sidebar -> Agent Tokens",
            file=sys.stderr,
        )

    # 初始化客户端
    client = AgentGatewayClient(base_url=base_url, token=token)
    set_client(client)

    server = _create_mcp_server()

    if transport == "stdio":
        # stdio 模式（默认）
        server.run(transport="stdio")
    elif transport in ("streamable-http", "http"):
        # HTTP 模式
        print(f"Starting MCP HTTP server on {host}:{port}", file=sys.stderr)
        # FastMCP 1.0+ 支持 streamable-http
        server.run(transport="streamable-http", host=host, port=port)
    elif transport == "sse":
        # 旧版 SSE 模式（兼容老客户端）
        print(f"Starting MCP SSE server on {host}:{port}", file=sys.stderr)
        server.run(transport="sse", host=host, port=port)
    else:
        print(f"Unknown transport: {transport}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
