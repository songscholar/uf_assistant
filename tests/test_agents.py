"""
测试 Agent 模块
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.prompts import (
    STOCK_ASSISTANT_ROLE,
    build_analysis_prompt,
    build_crypto_prompt,
    build_market_prompt,
    build_picking_prompt,
    build_strategy_prompt,
    build_system_prompt,
    build_trading_prompt,
)
from app.agents.stock_assistant import AgentState, StockAssistantAgent, create_stock_assistant_graph


class TestPrompts:
    """测试提示词构建"""

    def test_build_system_prompt_default(self):
        """测试默认系统提示词"""
        prompt = build_system_prompt()
        assert STOCK_ASSISTANT_ROLE in prompt
        assert "工具调用规范" in prompt

    def test_build_system_prompt_custom(self):
        """测试自定义系统提示词"""
        prompt = build_system_prompt(
            role="自定义角色",
            include_tool_guide=False,
            custom_instructions="自定义指令",
        )
        assert "自定义角色" in prompt
        assert "工具调用规范" not in prompt
        assert "自定义指令" in prompt

    def test_build_analysis_prompt(self):
        """测试分析提示词"""
        prompt = build_analysis_prompt("000001", "平安银行", "股价: 10.5")
        assert "000001" in prompt
        assert "平安银行" in prompt
        assert "股价: 10.5" in prompt
        assert "基本面" in prompt

    def test_build_strategy_prompt(self):
        """测试策略提示词"""
        prompt = build_strategy_prompt("均线交叉")
        assert "均线交叉" in prompt
        assert "策略原理" in prompt

    def test_build_picking_prompt(self):
        """测试选股提示词"""
        prompt = build_picking_prompt("MACD", "金叉条件")
        assert "MACD" in prompt
        assert "金叉条件" in prompt

    def test_build_market_prompt(self):
        """测试市场分析提示词"""
        prompt = build_market_prompt("大盘数据")
        assert "大盘数据" in prompt
        assert "主要指数" in prompt

    def test_build_trading_prompt(self):
        """测试交易提示词"""
        prompt = build_trading_prompt("000001", "buy", 100, 10.5, "limit")
        assert "000001" in prompt
        assert "buy" in prompt
        assert "10.5" in str(prompt)

    def test_build_crypto_prompt(self):
        """测试虚拟货币提示词"""
        prompt = build_crypto_prompt("BTC", "价格: 60000")
        assert "BTC" in prompt
        assert "60000" in prompt


class TestStockAssistantAgent:
    """测试股票助手 Agent"""

    def test_agent_init(self):
        """测试 Agent 初始化"""
        with patch("app.agents.stock_assistant.LangChainLlmAdapter.from_env") as mock_llm:
            mock_llm.return_value = MagicMock()
            agent = StockAssistantAgent()
            assert agent is not None

    def test_convert_to_lc_messages(self):
        """测试消息转换"""
        with patch("app.agents.stock_assistant.LangChainLlmAdapter.from_env") as mock_llm:
            mock_llm.return_value = MagicMock()
            agent = StockAssistantAgent()
            
            messages = [
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "用户消息"},
                {"role": "assistant", "content": "助手回复"},
            ]
            result = agent._convert_to_lc_messages(messages)
            
            assert len(result) == 3
            assert isinstance(result[0], SystemMessage)
            assert isinstance(result[1], HumanMessage)
            assert isinstance(result[2], AIMessage)

    def test_chat_without_memory(self):
        """测试无记忆模式对话"""
        with patch("app.agents.stock_assistant.LangChainLlmAdapter.from_env") as mock_llm_class:
            mock_llm = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "测试回答"
            mock_response.tool_calls = []
            mock_llm.bind_tools.return_value = mock_llm
            mock_llm.invoke.return_value = mock_response
            mock_llm_class.return_value = mock_llm
            
            agent = StockAssistantAgent()
            
            # Mock graph execution
            with patch.object(agent, "_graph") as mock_graph:
                mock_graph.invoke.return_value = {
                    "final_answer": "测试回答",
                    "tools_called": [],
                }
                result = agent.chat("你好")
            
            assert result["answer"] == "测试回答"
            assert result["conversation_id"] == "no-memory"


class TestAgentGraph:
    """测试 Agent Graph"""

    def test_graph_creation(self):
        """测试图创建"""
        graph = create_stock_assistant_graph()
        assert graph is not None

    def test_should_continue_with_tool_calls(self):
        """测试有工具调用时继续"""
        from app.agents.stock_assistant import should_continue
        
        state = {
            "messages": [AIMessage(content="", tool_calls=[{"id": "1", "name": "test", "args": {}}])],
            "context": {},
            "tools_called": [],
            "final_answer": None,
            "should_end": False,
        }
        result = should_continue(state)
        assert result == "tools"

    def test_should_continue_without_tool_calls(self):
        """测试无工具调用时结束"""
        from app.agents.stock_assistant import should_continue
        
        state = {
            "messages": [AIMessage(content="回答完毕")],
            "context": {},
            "tools_called": [],
            "final_answer": None,
            "should_end": False,
        }
        result = should_continue(state)
        assert result == "end"
