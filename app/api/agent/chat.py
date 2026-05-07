"""
UF Stock Assistant — Agent Gateway 对话端点
支持普通对话和 SSE 流式返回
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.stock_assistant import StockAssistantAgent
from app.core.agent_auth import AgentAuthManager, AgentTokenRecord
from app.core.constants import AgentScope
from app.core.logging import get_logger

from . import require_scope

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
    request: ChatRequest,
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """
    Agent 对话接口
    
    AI 代理可以通过此接口与股票助手进行对话，获取分析结果。
    """
    try:
        agent = _get_agent()
        result = agent.chat(
            user_input=request.message,
            conversation_id=request.conversation_id,
            user_id=request.user_id,
        )
        return ChatResponse(**result)
    except Exception as exc:
        logger.error("agent_chat_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"对话处理失败: {exc}")


@router.post("/stream")
async def agent_chat_stream(
    request: ChatRequest,
    _record: AgentTokenRecord = Depends(require_scope(AgentScope.READ)),
):
    """
    Agent 对话接口（SSE 流式）
    
    返回 Server-Sent Events，适合长分析任务。
    事件类型：
    - `thinking`: Agent 正在思考
    - `tool_call`: 正在调用工具
    - `tool_result`: 工具返回结果
    - `answer`: 最终回答
    - `done`: 流结束
    """
    async def event_generator() -> AsyncIterator[str]:
        try:
            agent = _get_agent()
            
            # 发送开始事件
            yield f"data: {json.dumps({'event': 'start', 'message': request.message}, ensure_ascii=False)}\n\n"
            
            # 由于当前 Agent 不支持原生流式，这里模拟流式效果
            # 先发送 thinking 事件
            yield f"data: {json.dumps({'event': 'thinking', 'content': '正在分析...'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.5)
            
            # 执行对话
            result = agent.chat(
                user_input=request.message,
                conversation_id=request.conversation_id,
                user_id=request.user_id,
            )
            
            # 发送工具调用事件
            if result.get("tools_used"):
                for tool in result["tools_used"]:
                    yield f"data: {json.dumps({'event': 'tool_call', 'tool': tool}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.2)
            
            # 发送最终回答（分段）
            answer = result.get("answer", "")
            chunk_size = 50
            for i in range(0, len(answer), chunk_size):
                chunk = answer[i:i + chunk_size]
                yield f"data: {json.dumps({'event': 'answer', 'chunk': chunk, 'index': i // chunk_size}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.1)
            
            # 发送完成事件
            yield f"data: {json.dumps({'event': 'done', 'conversation_id': result.get('conversation_id')}, ensure_ascii=False)}\n\n"
            
        except Exception as exc:
            logger.error("agent_chat_stream_error", error=str(exc))
            yield f"data: {json.dumps({'event': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
