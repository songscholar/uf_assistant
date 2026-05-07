"""
测试 API 接口
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.auth.dependencies import get_current_user

# Override auth dependency so tests don't need real JWT tokens
def _mock_user():
    return {"user_id": 1, "username": "testuser", "role": "admin"}

app.dependency_overrides[get_current_user] = _mock_user

client = TestClient(app)


class TestHealth:
    """测试健康检查"""

    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_root(self):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data


class TestChatAPI:
    """测试对话接口"""

    def test_chat_new_conversation(self):
        """测试发送消息"""
        with patch("app.api.routers.chat._get_agent") as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.chat.return_value = {
                "conversation_id": "test-123",
                "answer": "这是回答",
                "tools_used": [],
            }
            mock_get_agent.return_value = mock_agent
            
            response = client.post("/api/v1/chat", json={
                "message": "你好",
                "user_id": "test",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["answer"] == "这是回答"
            assert data["conversation_id"] == "test-123"

    def test_chat_empty_message(self):
        """测试空消息"""
        response = client.post("/api/v1/chat", json={"message": ""})
        assert response.status_code == 422  # 验证错误


class TestStockAPI:
    """测试股票接口"""

    def test_search_stock(self):
        """测试搜索股票"""
        with patch("app.api.routers.stock.search_stocks") as mock_search:
            mock_search.return_value = json.dumps({"keyword": "平安", "stocks": []})
            response = client.get("/api/v1/stock/search?keyword=平安&limit=10")
            assert response.status_code == 200

    def test_stock_info(self):
        """测试获取股票信息"""
        with patch("app.api.routers.stock.get_stock_info") as mock_info:
            mock_info.return_value = json.dumps({"代码": "000001", "名称": "平安银行"})
            response = client.get("/api/v1/stock/000001/info")
            assert response.status_code == 200

    def test_stock_realtime(self):
        """测试实时行情"""
        with patch("app.api.routers.stock.get_stock_realtime") as mock_rt:
            mock_rt.return_value = json.dumps({"symbol": "000001", "price": 10.5})
            response = client.get("/api/v1/stock/000001/realtime")
            assert response.status_code == 200

    def test_stock_history(self):
        """测试历史数据"""
        with patch("app.api.routers.stock.get_stock_history") as mock_hist:
            mock_hist.return_value = json.dumps({"symbol": "000001", "data": []})
            response = client.get("/api/v1/stock/000001/history?period=daily&limit=10")
            assert response.status_code == 200


class TestMarketAPI:
    """测试市场接口"""

    def test_market_overview(self):
        """测试市场概况"""
        with patch("app.api.routers.market.get_market_overview") as mock_overview:
            mock_overview.return_value = json.dumps({"summary": {}})
            response = client.get("/api/v1/market/overview")
            assert response.status_code == 200

    def test_market_indices(self):
        """测试大盘指数"""
        with patch("app.api.routers.market.get_market_index") as mock_index:
            mock_index.return_value = json.dumps({"indices": []})
            response = client.get("/api/v1/market/indices")
            assert response.status_code == 200

    def test_market_sectors(self):
        """测试板块热点"""
        with patch("app.api.routers.market.get_sector_hot") as mock_sectors:
            mock_sectors.return_value = json.dumps({"industries": [], "concepts": []})
            response = client.get("/api/v1/market/sectors")
            assert response.status_code == 200

    def test_market_longhu(self):
        """测试龙虎榜"""
        with patch("app.api.routers.market.get_longhu_bang") as mock_longhu:
            mock_longhu.return_value = json.dumps({"date": "2024-01-01", "data": []})
            response = client.get("/api/v1/market/longhu")
            assert response.status_code == 200


class TestTradingAPI:
    """测试交易接口"""

    def test_place_order(self):
        """测试下单"""
        with patch("app.api.routers.trading.submit_order") as mock_order:
            mock_order.return_value = json.dumps({"success": True, "order": {"id": "123"}})
            response = client.post("/api/v1/trading/order", json={
                "symbol": "000001",
                "side": "buy",
                "quantity": 100,
                "price": 10.5,
                "order_type": "limit",
            })
            assert response.status_code == 200

    def test_get_positions(self):
        """测试获取持仓"""
        with patch("app.api.routers.trading.get_positions") as mock_pos:
            mock_pos.return_value = json.dumps({"positions": []})
            response = client.get("/api/v1/trading/positions")
            assert response.status_code == 200

    def test_get_orders(self):
        """测试获取订单"""
        with patch("app.api.routers.trading.get_orders") as mock_orders:
            mock_orders.return_value = json.dumps({"orders": []})
            response = client.get("/api/v1/trading/orders")
            assert response.status_code == 200

    def test_cancel_order(self):
        """测试取消订单"""
        with patch("app.api.routers.trading.cancel_order") as mock_cancel:
            mock_cancel.return_value = json.dumps({"success": True})
            response = client.delete("/api/v1/trading/orders/123")
            assert response.status_code == 200


class TestStrategyAPI:
    """测试策略接口"""

    def test_list_strategies(self):
        """测试列出策略"""
        with patch("app.api.routers.strategy.list_all_strategies") as mock_list:
            mock_list.return_value = [{"name": "测试策略", "key": "test"}]
            response = client.get("/api/v1/strategies")
            assert response.status_code == 200
            assert len(response.json()) == 1

    def test_quick_screen(self):
        """测试快速筛选"""
        with patch("app.api.routers.strategy.StockPicker") as mock_picker_class:
            mock_picker = MagicMock()
            mock_picker.quick_screen.return_value = json.dumps({"stocks": []})
            mock_picker_class.return_value = mock_picker
            
            response = client.post("/api/v1/strategies/screen", json={
                "min_price": 5,
                "limit": 10,
            })
            assert response.status_code == 200


class TestUploadAPI:
    """测试上传接口"""

    def test_upload_txt(self):
        """测试上传文本文件"""
        from io import BytesIO
        
        with patch("app.api.routers.upload.parse_file") as mock_parse:
            mock_parse.return_value = "测试内容"
            
            response = client.post(
                "/api/v1/upload",
                files={"file": ("test.txt", BytesIO("测试内容".encode('utf-8')), "text/plain")},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "parsed_content" in data

    def test_upload_batch(self):
        """测试批量上传"""
        from io import BytesIO
        
        with patch("app.api.routers.upload.parse_file") as mock_parse:
            mock_parse.return_value = "测试内容"
            
            response = client.post(
                "/api/v1/upload/batch",
                files=[
                    ("files", ("test1.txt", BytesIO("内容1".encode('utf-8')), "text/plain")),
                    ("files", ("test2.txt", BytesIO("内容2".encode('utf-8')), "text/plain")),
                ],
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success_count"] == 2
