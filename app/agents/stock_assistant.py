"""
UF Stock Assistant — 股票助手 Agent
基于 LangGraph 构建的状态机 Agent
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.core.llm_adapter import LangChainLlmAdapter
from app.core.logging import get_logger
from app.memory.manager import MemoryManager

from .prompts import build_system_prompt

logger = get_logger("app.agents.stock_assistant")


# =============================================================================
# Agent State
# =============================================================================

class AgentState(TypedDict):
    """
    Agent 状态定义
    
    字段：
        messages: 消息列表（会自动累加）
        context: 附加上下文数据
        tools_called: 已调用的工具记录
        final_answer: 最终回答
        should_end: 是否结束会话
    """
    messages: Annotated[list[BaseMessage], add_messages]
    context: dict[str, Any]
    tools_called: list[dict[str, Any]]
    final_answer: str | None
    should_end: bool


# =============================================================================
# 节点函数
# =============================================================================

def agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Agent 推理节点
    调用 LLM 进行推理，可能产生工具调用请求
    """
    llm: LangChainLlmAdapter = config["configurable"]["llm"]
    tools = config["configurable"].get("tools", [])
    
    # 绑定工具到 LLM
    llm_with_tools = llm.bind_tools(tools) if tools else llm
    
    # 调用 LLM
    response = llm_with_tools.invoke(state["messages"])
    
    return {"messages": [response]}


def tool_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    工具执行节点
    执行 LLM 请求的工具调用
    """
    tools_by_name = config["configurable"].get("tools_by_name", {})
    last_message = state["messages"][-1]
    
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}
    
    tool_messages = []
    tools_called = []
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_call_id = tool_call["id"]
        
        logger.info(
            "tool_invocation",
            tool_name=tool_name,
            tool_args=tool_args,
            tool_call_id=tool_call_id,
        )
        
        try:
            if tool_name in tools_by_name:
                tool_result = tools_by_name[tool_name].invoke(tool_args)
            else:
                tool_result = f"错误：未找到工具 '{tool_name}'"
                logger.warning("tool_not_found", tool_name=tool_name)
        except Exception as exc:
            tool_result = f"工具执行失败: {exc}"
            logger.error("tool_execution_failed", tool_name=tool_name, error=str(exc))
        
        tool_messages.append(
            ToolMessage(content=str(tool_result), tool_call_id=tool_call_id)
        )
        tools_called.append({
            "name": tool_name,
            "args": tool_args,
            "result": tool_result,
        })
    
    return {
        "messages": tool_messages,
        "tools_called": tools_called,
    }


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """
    判断是否需要继续执行
    如果最后一条消息包含工具调用，则路由到工具节点
    """
    last_message = state["messages"][-1]
    
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    return "end"


def finalize_node(state: AgentState) -> dict[str, Any]:
    """
    结束节点
    提取最终回答
    """
    last_message = state["messages"][-1]
    
    if isinstance(last_message, AIMessage):
        final_answer = last_message.content or ""
    else:
        final_answer = str(last_message.content) if hasattr(last_message, "content") else ""
    
    return {
        "final_answer": final_answer,
        "should_end": True,
    }


# =============================================================================
# 构建 Graph
# =============================================================================

def create_stock_assistant_graph() -> StateGraph:
    """
    创建股票助手 Agent 状态图
    
    工作流：
        START -> agent -> [有工具调用?] -> tools -> agent -> ...
                              |
                              v
                            END
    """
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("finalize", finalize_node)
    
    # 添加边
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": "finalize",
        },
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("finalize", END)
    
    return workflow.compile()


# =============================================================================
# Agent 包装类
# =============================================================================

class StockAssistantAgent:
    """
    股票助手 Agent
    
    封装 LangGraph 工作流，提供高层接口：
    - chat: 对话接口
    - analyze: 分析接口
    - pick_stocks: 选股接口
    """
    
    def __init__(
        self,
        llm: LangChainLlmAdapter | None = None,
        memory: MemoryManager | None = None,
        tools: list[Any] | None = None,
    ) -> None:
        self._llm = llm or LangChainLlmAdapter.from_env()
        self._memory = memory
        self._tools = tools or []
        self._tools_by_name = {t.name: t for t in self._tools} if self._tools else {}
        self._graph = create_stock_assistant_graph()
        self._system_prompt = build_system_prompt()
    
    @property
    def llm(self) -> LangChainLlmAdapter:
        return self._llm
    
    @property
    def memory(self) -> MemoryManager | None:
        return self._memory
    
    def _build_config(self) -> dict[str, Any]:
        """构建 RunnableConfig"""
        return {
            "configurable": {
                "llm": self._llm,
                "tools": self._tools,
                "tools_by_name": self._tools_by_name,
            }
        }
    
    def chat(
        self,
        user_input: str,
        conversation_id: str | None = None,
        user_id: str = "default",
    ) -> dict[str, Any]:
        """
        对话接口
        
        Args:
            user_input: 用户输入
            conversation_id: 会话 ID（None 则创建新会话）
            user_id: 用户标识
            
        Returns:
            {
                "conversation_id": str,
                "answer": str,
                "tools_used": list[dict],
            }
        """
        # 初始化/获取会话
        if self._memory:
            if not conversation_id:
                conversation_id = self._memory.create_conversation(
                    user_id=user_id,
                    system_prompt=self._system_prompt,
                )
            
            # 添加用户消息
            self._memory.add_user_message(conversation_id, user_input)
            
            # 获取上下文
            messages = self._memory.get_context(conversation_id)
        else:
            # 无记忆模式：直接构造消息
            conversation_id = conversation_id or "no-memory"
            messages = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_input},
            ]
        
        # 转换为 LangChain Message 对象
        lc_messages = self._convert_to_lc_messages(messages)
        
        # 运行 Agent
        initial_state: AgentState = {
            "messages": lc_messages,
            "context": {},
            "tools_called": [],
            "final_answer": None,
            "should_end": False,
        }
        
        result = self._graph.invoke(initial_state, self._build_config())
        
        # 提取结果
        final_answer = result.get("final_answer", "")
        tools_called = result.get("tools_called", [])
        
        # 保存助手回复到记忆
        if self._memory and conversation_id != "no-memory":
            self._memory.add_assistant_message(
                conversation_id=conversation_id,
                content=final_answer,
                tool_calls=tools_called,
            )
        
        logger.info(
            "chat_completed",
            conversation_id=conversation_id,
            answer_length=len(final_answer),
            tools_used=len(tools_called),
        )
        
        return {
            "conversation_id": conversation_id,
            "answer": final_answer,
            "tools_used": tools_called,
        }
    
    def analyze(self, symbol: str, context: str = "") -> str:
        """
        分析指定股票
        
        Args:
            symbol: 股票代码
            context: 附加上下文
            
        Returns:
            分析报告
        """
        from .prompts import build_analysis_prompt
        
        prompt = build_analysis_prompt(symbol=symbol, data=context)
        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=prompt),
        ]
        
        result = self._graph.invoke(
            {
                "messages": messages,
                "context": {"analysis_target": symbol},
                "tools_called": [],
                "final_answer": None,
                "should_end": False,
            },
            self._build_config(),
        )
        
        return result.get("final_answer", "")
    
    def _convert_to_lc_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[BaseMessage]:
        """将字典消息转换为 LangChain Message 对象"""
        result = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                result.append(SystemMessage(content=content))
            elif role == "assistant":
                result.append(AIMessage(content=content))
            elif role == "tool":
                result.append(ToolMessage(content=content, tool_call_id=msg.get("tool_call_id", "")))
            else:
                result.append(HumanMessage(content=content))
        
        return result
    
    def get_conversation_stats(self, conversation_id: str) -> dict[str, Any] | None:
        """获取会话统计"""
        if self._memory:
            return self._memory.get_stats(conversation_id)
        return None
