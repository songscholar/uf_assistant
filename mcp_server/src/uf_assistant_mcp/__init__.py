"""
UF Stock Assistant MCP Server

将 UF Stock Assistant 的 Agent Gateway 能力包装为 MCP Tools，
支持 Cursor / Claude Code / Codex 等 AI 客户端直接调用。

环境变量：
  UF_ASSISTANT_BASE_URL    — Agent Gateway 地址（默认 http://localhost:8000）
  UF_ASSISTANT_AGENT_TOKEN — Agent Token（必填）
  UF_ASSISTANT_MCP_TRANSPORT — 传输方式：stdio（默认）或 streamable-http
  UF_ASSISTANT_MCP_HOST    — HTTP 模式监听地址（默认 0.0.0.0）
  UF_ASSISTANT_MCP_PORT    — HTTP 模式监听端口（默认 7800）

用法：
  # stdio 模式（Cursor / Claude Code）
  uvx uf-assistant-mcp

  # HTTP 模式
  UF_ASSISTANT_MCP_TRANSPORT=streamable-http uf-assistant-mcp
"""

__version__ = "0.1.0"
