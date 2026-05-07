"""
测试股票数据工具模块
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import StockDataError
from app.tools.stock_data import get_stock_info, get_stock_realtime, search_stocks


class TestSearchStocks:
    """测试股票搜索"""

    def test_search_returns_json(self):
        """测试搜索返回 JSON"""
        with patch("app.tools.stock_data._get_ak") as mock_ak:
            # 简化 mock，直接返回空 DataFrame
            mock_df = MagicMock()
            mock_df.__iter__ = MagicMock(return_value=iter([]))
            mock_df.iterrows.return_value = iter([])
            mock_ak.return_value.stock_zh_a_spot_em.return_value = mock_df
            
            result = search_stocks("平安")
            data = json.loads(result)
            assert "keyword" in data
            assert "stocks" in data


class TestGetStockInfo:
    """测试股票信息"""

    def test_get_info_returns_json(self):
        """测试获取信息返回 JSON"""
        with patch("app.tools.stock_data._get_ak") as mock_ak:
            mock_df = MagicMock()
            mock_df.iterrows.return_value = iter([
                (0, {"item": "股票代码", "value": "000001"}),
                (1, {"item": "股票名称", "value": "平安银行"}),
            ])
            mock_ak.return_value.stock_individual_info_em.return_value = mock_df
            
            result = get_stock_info("000001")
            assert "000001" in result
            assert "平安银行" in result


class TestGetStockRealtime:
    """测试实时行情"""

    def test_get_realtime_returns_json(self):
        """测试获取实时行情返回 JSON（兼容 dict 或 str 返回）"""
        with patch("app.tools.stock_data.eastmoney_api") as mock_em:
            mock_em.get_stock_realtime.return_value = {"error": "未找到股票 000001"}
            
            result = get_stock_realtime("000001")
            # 兼容 dict 直接返回或 JSON 字符串
            data = result if isinstance(result, dict) else json.loads(result)
            assert "error" in data
