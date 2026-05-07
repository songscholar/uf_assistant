"""
UF Stock Assistant — 对话接口
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.stock_assistant import StockAssistantAgent
from app.auth.dependencies import get_current_user
from app.core.logging import get_logger
from app.memory.manager import MemoryManager

logger = get_logger("app.api.chat")

router = APIRouter(dependencies=[Depends(get_current_user)])

# 全局实例
_agent: StockAssistantAgent | None = None
_memory: MemoryManager | None = None


def _get_agent() -> StockAssistantAgent:
    """获取或创建 Agent 实例"""
    global _agent
    if _agent is None:
        _agent = StockAssistantAgent()
    return _agent


def _get_memory() -> MemoryManager:
    """获取或创建 Memory 实例"""
    global _memory
    if _memory is None:
        _memory = MemoryManager.from_env()
    return _memory


# =============================================================================
# 请求/响应模型
# =============================================================================

class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., description="用户消息", min_length=1, max_length=4000)
    conversation_id: str | None = Field(None, description="会话 ID（新会话留空）")
    user_id: str = Field("default", description="用户标识")
    provider: str | None = Field(None, description="LLM 提供商名称")


class ChatResponse(BaseModel):
    """对话响应"""
    conversation_id: str
    answer: str
    tools_used: list[dict[str, Any]] = []


class ConversationListResponse(BaseModel):
    """会话列表响应"""
    conversations: list[dict[str, Any]]


class ConversationDetailResponse(BaseModel):
    """会话详情响应"""
    id: str
    title: str
    messages: list[dict[str, Any]]
    stats: dict[str, Any]


# =============================================================================
# 接口
# =============================================================================

@router.get("/providers")
async def list_providers():
    """获取可用的 LLM 提供商列表"""
    agent = _get_agent()
    providers = agent.llm.llm_service.list_providers()
    return {"providers": providers}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    发送消息与助手对话
    
    - 如果提供了 conversation_id，则继续现有会话
    - 如果没有提供，则创建新会话
    """
    try:
        agent = _get_agent()
        result = agent.chat(
            user_input=request.message,
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            provider=request.provider,
        )
        return ChatResponse(**result)
    except Exception as exc:
        logger.error("chat_error", error=str(exc))
        raise HTTPException(status_code=500, detail=f"对话处理失败: {exc}")


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(user: dict = Depends(get_current_user), limit: int = 20):
    """获取用户会话列表"""
    try:
        memory = _get_memory()
        conversations = memory.list_conversations(user_id=str(user["user_id"]), limit=limit)
        return ConversationListResponse(conversations=conversations)
    except Exception as exc:
        logger.error("list_conversations_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(conversation_id: str):
    """获取会话详情"""
    try:
        memory = _get_memory()
        conv = memory.get_conversation_info(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        messages = memory._store.get_messages(conversation_id, limit=100)
        stats = memory.get_stats(conversation_id)
        
        return ConversationDetailResponse(
            id=conv["id"],
            title=conv.get("title", ""),
            messages=messages,
            stats=stats,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_conversation_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """删除会话"""
    try:
        memory = _get_memory()
        success = memory.delete_conversation(conversation_id)
        if not success:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"success": True, "message": "会话已删除"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("delete_conversation_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/conversations")
async def create_conversation(user: dict = Depends(get_current_user), title: str | None = None):
    """创建新会话"""
    try:
        memory = _get_memory()
        conversation_id = memory.create_conversation(user_id=str(user["user_id"]), title=title)
        return {
            "conversation_id": conversation_id,
            "message": "会话创建成功",
        }
    except Exception as exc:
        logger.error("create_conversation_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
