"""
UF Stock Assistant — Agent Gateway HTTP 客户端
MCP Server 通过此客户端调用后端 API
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class AgentGatewayClient:
    """Agent Gateway HTTP 客户端"""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("UF_ASSISTANT_BASE_URL", "http://localhost:8000")).rstrip("/")
        self.token = token or os.getenv("UF_ASSISTANT_AGENT_TOKEN", "")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout, headers=self._headers())

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/agent/v1{path}"

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET 请求"""
        resp = self._client.get(self._url(path), params=params)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST 请求"""
        resp = self._client.post(self._url(path), json=json)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "AgentGatewayClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
