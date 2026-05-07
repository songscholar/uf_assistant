"""
UF Stock Assistant — Agent Gateway 对话端点
支持普通对话和 SSE 流式返回

参考 QuantDinger 设计：
  - SSE 支持 Last-Event-ID 断点续传
  - 长对话可转为异步 Job
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.stock_assistant import StockAssistantAgent
from app.core.agent_auth import AgentAuthManager, AgentTokenRecord
from app.core.constants import AgentScope
from app.core.logging import get_logger

from . import require_scope, _inject_rate_limit

logger = get_logger("app.api.agent.chat")

router = APIRouter()

_agent: StockAssistantAgent | None = None


def _get_agent() -> StockAssistantAgent:
    global _agent
    if _agent is None:
        _agent = StockAssistantAgent()
    return _agent


class ChatRequest(BaseModel):
    """Agent 对话请求"""
    message: str = Field(..., description="用户消息", min_length=1, max_length=4000)
    conversation_id: str | None = Field(None, description="会话 ID")
    user_id: str = Field("agent_default", description="用户标识")


class ChatResponse(BaseModel):
    """Agent 对话响应"""
    conversation_id: str
    answer: str
    tools_used: list[dict[str, Any]] = []


@router.post("", response_model=ChatResponse)
async def agent_chat(
    request: Request,
    body: ChatRequest,
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """
    Agent 对话接口

    AI 代理可以通过此接口与股票助手进行对话，获取分析结果。
    """
    _inject_rate_limit(request, record)
    try:
        agent = _get_agent()
        result = agent.chat(
            user_input=body.message,
            conversation_id=body.conversation_id,
            user_id=body.user_id,
        )
        return ChatResponse(**result)
    except Exception as exc:
        logger.error("agent_chat_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"对话处理失败: {exc}")


@router.post("/stream")
async def agent_chat_stream(
    request: Request,
    body: ChatRequest,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    since: int | None = Query(None, description="从第 N 个事件开始（断点续传）"),
    record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """
    Agent 对话接口（SSE 流式）

    返回 Server-Sent Events，支持 Last-Event-ID 和 ?since 断点续传。
    事件类型：
    - `start`: 开始处理
    - `thinking`: Agent 正在思考
    - `tool_call`: 正在调用工具
    - `answer`: 最终回答（分段）
    - `done`: 流结束
    - `error`: 错误
    """
    _inject_rate_limit(request, record)

    # 计算起始索引（断点续传）
    start_index = 0
    if since is not None:
        start_index = max(0, since)
    if last_event_id and last_event_id.startswith("evt_"):
        try:
            start_index = max(start_index, int(last_event_id.split("_")[1]) + 1)
        except (IndexError, ValueError):
            pass

    async def event_generator() -> AsyncIterator[str]:
        event_counter = 0

        def _event(data: dict) -> str:
            nonlocal event_counter
            event_counter += 1
            data["_seq"] = event_counter
            return f"id: evt_{event_counter}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            # 跳过已发送的事件
            if start_index == 0:
                yield _event({"event": "start", "message": body.message})

            if start_index <= 1:
                yield _event({"event": "thinking", "content": "正在分析..."})
                await asyncio.sleep(0.5)

            agent = _get_agent()
            result = agent.chat(
                user_input=body.message,
                conversation_id=body.conversation_id,
                user_id=body.user_id,
            )

            # 工具调用事件
            tools = result.get("tools_used", [])
            if tools and start_index <= 2:
                for tool in tools:
                    yield _event({"event": "tool_call", "tool": tool})
                    await asyncio.sleep(0.2)

            # 最终回答（分段）
            answer = result.get("answer", "")
            chunk_size = 50
            base_seq = 3 + len(tools)
            for i in range(0, len(answer), chunk_size):
                seq = base_seq + i // chunk_size
                if seq < start_index:
                    continue
                chunk = answer[i:i + chunk_size]
                yield _event({"event": "answer", "chunk": chunk, "index": i // chunk_size})
                await asyncio.sleep(0.1)

            yield _event({"event": "done", "conversation_id": result.get("conversation_id")})

        except Exception as exc:
            logger.error("agent_chat_stream_error", error=str(exc))
            yield _event({"event": "error", "message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
