"""
测试记忆模块
"""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.core.constants import CONTEXT_COMPRESS_TARGET, CONTEXT_COMPRESS_THRESHOLD
from app.memory.compressor import ContextCompressor
from app.memory.conversation import ConversationStore
from app.memory.manager import MemoryManager


class TestConversationStore:
    """测试对话存储"""

    @pytest.fixture
    def store(self):
        """创建临时存储"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_url = f"sqlite:///{tmp.name}"
            store = ConversationStore(database_url=db_url)
            yield store

    def test_create_conversation(self, store):
        """测试创建会话"""
        conv_id = store.create_conversation(user_id="test_user", title="测试会话")
        assert conv_id is not None
        assert len(conv_id) == 36  # UUID 长度

    def test_add_and_get_messages(self, store):
        """测试添加和获取消息"""
        conv_id = store.create_conversation()
        
        # 添加消息
        store.add_message(conv_id, "user", "你好")
        store.add_message(conv_id, "assistant", "你好！有什么可以帮你的？")
        
        # 获取消息
        messages = store.get_messages(conv_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_get_messages_exclude_system(self, store):
        """测试排除系统消息"""
        conv_id = store.create_conversation()
        store.add_message(conv_id, "system", "系统提示")
        store.add_message(conv_id, "user", "用户消息")
        
        messages = store.get_messages(conv_id, include_system=False)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_get_conversation(self, store):
        """测试获取会话信息"""
        conv_id = store.create_conversation(user_id="test", title="标题")
        conv = store.get_conversation(conv_id)
        assert conv is not None
        assert conv["user_id"] == "test"
        assert conv["title"] == "标题"

    def test_list_conversations(self, store):
        """测试列会话"""
        store.create_conversation(user_id="u1", title="c1")
        store.create_conversation(user_id="u1", title="c2")
        
        convs = store.list_conversations(user_id="u1")
        assert len(convs) == 2

    def test_update_summary(self, store):
        """测试更新摘要"""
        conv_id = store.create_conversation()
        store.update_summary(conv_id, "摘要内容", is_compressed=True)
        
        conv = store.get_conversation(conv_id)
        assert conv["summary"] == "摘要内容"
        assert conv["is_compressed"] is True

    def test_delete_conversation(self, store):
        """测试删除会话"""
        conv_id = store.create_conversation()
        store.add_message(conv_id, "user", "test")
        
        assert store.delete_conversation(conv_id) is True
        assert store.get_conversation(conv_id) is None

    def test_get_message_count(self, store):
        """测试消息计数"""
        conv_id = store.create_conversation()
        store.add_message(conv_id, "system", "sys")
        store.add_message(conv_id, "user", "u1")
        store.add_message(conv_id, "user", "u2")
        
        assert store.get_message_count(conv_id, include_system=True) == 3
        assert store.get_message_count(conv_id, include_system=False) == 2

    def test_clear_messages(self, store):
        """测试清空消息"""
        conv_id = store.create_conversation()
        store.add_message(conv_id, "user", "test")
        store.clear_messages(conv_id)
        
        messages = store.get_messages(conv_id)
        assert len(messages) == 0


class TestContextCompressor:
    """测试上下文压缩器"""

    def test_should_compress_threshold(self):
        """测试压缩阈值判断"""
        compressor = ContextCompressor(threshold=10)
        assert compressor.should_compress(10) is True
        assert compressor.should_compress(9) is False
        assert compressor.should_compress(15) is True

    def test_fallback_compress(self):
        """测试 fallback 压缩"""
        compressor = ContextCompressor(threshold=5, keep_recent=2)
        messages = [
            {"role": "user", "content": "消息1"},
            {"role": "assistant", "content": "回复1"},
            {"role": "user", "content": "消息2"},
            {"role": "assistant", "content": "回复2"},
            {"role": "user", "content": "消息3"},
        ]
        
        summary, keep = compressor.compress(messages)
        assert summary != ""
        assert len(keep) == 2

    def test_no_compress_below_threshold(self):
        """测试低于阈值不压缩"""
        compressor = ContextCompressor(threshold=10, keep_recent=3)
        messages = [
            {"role": "user", "content": "消息1"},
            {"role": "assistant", "content": "回复1"},
        ]
        
        # 消息数少于 keep_recent，不压缩
        summary, keep = compressor._fallback_compress(messages)
        assert summary == ""
        assert len(keep) == 2

    def test_format_history(self):
        """测试历史格式化"""
        compressor = ContextCompressor()
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "您好"},
        ]
        text = compressor._format_history(messages)
        assert "用户: 你好" in text
        assert "助手: 您好" in text


class TestMemoryManager:
    """测试记忆管理器"""

    @pytest.fixture
    def manager(self):
        """创建临时管理器"""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_url = f"sqlite:///{tmp.name}"
            store = ConversationStore(database_url=db_url)
            compressor = ContextCompressor(threshold=5, keep_recent=2)
            manager = MemoryManager(store=store, compressor=compressor)
            yield manager

    def test_create_conversation(self, manager):
        """测试创建会话"""
        conv_id = manager.create_conversation(
            user_id="test",
            title="测试",
            system_prompt="你是助手",
        )
        assert conv_id is not None
        
        # 验证 system prompt 已存入
        messages = manager._store.get_messages(conv_id)
        assert any(m["role"] == "system" and m["content"] == "你是助手" for m in messages)

    def test_add_messages(self, manager):
        """测试添加消息"""
        conv_id = manager.create_conversation()
        
        manager.add_user_message(conv_id, "用户问题")
        manager.add_assistant_message(conv_id, "助手回答")
        manager.add_tool_message(conv_id, "call_1", "工具结果")
        
        messages = manager._store.get_messages(conv_id, include_system=False)
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "tool"

    def test_get_context(self, manager):
        """测试获取上下文"""
        conv_id = manager.create_conversation(system_prompt="系统提示")
        manager.add_user_message(conv_id, "你好")
        manager.add_assistant_message(conv_id, "您好")
        
        context = manager.get_context(conv_id)
        assert len(context) >= 2
        assert context[0]["role"] == "system"

    def test_get_stats(self, manager):
        """测试获取统计"""
        conv_id = manager.create_conversation()
        manager.add_user_message(conv_id, "test")
        
        stats = manager.get_stats(conv_id)
        assert stats["message_count"] == 1
        assert stats["is_compressed"] is False
        assert stats["needs_compression"] is False

    def test_list_and_delete(self, manager):
        """测试列会话和删除"""
        manager.create_conversation(user_id="u1", title="c1")
        manager.create_conversation(user_id="u1", title="c2")
        
        convs = manager.list_conversations(user_id="u1")
        assert len(convs) == 2
        
        manager.delete_conversation(convs[0]["id"])
        convs = manager.list_conversations(user_id="u1")
        assert len(convs) == 1
