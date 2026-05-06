"""
测试市场数据工具模块
"""

from unittest.mock import MagicMock, patch

from app.tools.market import get_market_index


class TestMarketTools:
    """测试市场工具"""

    def test_get_market_index(self):
        """测试获取大盘指数"""
        with patch("app.tools.market._get_ak") as mock_ak:
            mock_df = MagicMock()
            mock_df.iterrows.return_value = iter([
                (0, {"代码": "000001", "名称": "上证指数", "最新价": 3000, "涨跌幅": 0.5}),
                (1, {"代码": "399001", "名称": "深证成指", "最新价": 10000, "涨跌幅": 0.3}),
            ])
            mock_ak.return_value.stock_zh_index_spot.return_value = mock_df
            
            result = get_market_index()
            assert "上证指数" in result
            assert "深证成指" in result
