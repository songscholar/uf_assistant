"""
测试服务层
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.market_analyzer import MarketAnalyzer
from app.services.stock_picker import StockPicker


class TestStockPicker:
    """测试选股服务"""

    @pytest.fixture
    def picker(self):
        return StockPicker()

    def test_quick_screen(self, picker):
        """测试快速筛选"""
        with patch("app.services.stock_picker.ak.stock_zh_a_spot_em") as mock_spot:
            import pandas as pd
            mock_df = pd.DataFrame([
                {"代码": "000001", "名称": "平安银行", "最新价": 10.5, "涨跌幅": 1.2, "成交量": 10000, "成交额": 100000, "市盈率-动态": 5, "市净率": 0.8},
            ])
            mock_spot.return_value = mock_df
            
            result = picker.quick_screen({"min_price": 5, "limit": 10})
            data = json.loads(result)
            assert "stocks" in data

    def test_quick_screen_error(self, picker):
        """测试筛选异常"""
        with patch("app.services.stock_picker.ak.stock_zh_a_spot_em", side_effect=Exception("test error")):
            result = picker.quick_screen({})
            data = json.loads(result)
            assert "error" in data


class TestMarketAnalyzer:
    """测试市场分析服务"""

    @pytest.fixture
    def analyzer(self):
        return MarketAnalyzer()

    def test_calculate_risk_level_low(self, analyzer):
        """测试低风险"""
        risk = analyzer._calculate_risk_level(3, 20)
        assert risk["level"] == 1
        assert "低" in risk["description"]

    def test_calculate_risk_level_high(self, analyzer):
        """测试高风险"""
        risk = analyzer._calculate_risk_level(0, 70)
        assert risk["level"] == 5
        assert "高" in risk["description"]

    def test_risk_suggestion(self, analyzer):
        """测试风险建议"""
        assert "增加" in analyzer._risk_suggestion(1)
        assert "观望" in analyzer._risk_suggestion(5)

    def test_generate_daily_report_mock(self, analyzer):
        """测试生成日报（mock）"""
        with patch("app.services.market_analyzer.get_market_overview") as mock_overview, \
             patch("app.services.market_analyzer.get_market_index") as mock_index, \
             patch("app.services.market_analyzer.get_sector_hot") as mock_sector:
            
            mock_overview.return_value = json.dumps({
                "timestamp": "2024-01-01",
                "summary": {"up": 3000, "down": 1000, "flat": 500, "limit_up": 50, "limit_down": 10},
            })
            mock_index.return_value = json.dumps({
                "indices": [{"name": "上证指数", "price": 3000, "change_pct": 0.5}],
            })
            mock_sector.return_value = json.dumps({
                "industries": [{"name": "银行", "change_pct": 2.5}],
                "concepts": [{"name": "人工智能", "change_pct": 3.0}],
            })
            
            result = analyzer.generate_daily_report()
            data = json.loads(result)
            assert "market_summary" in data
            assert "indices" in data
            assert "sentiment" in data["market_summary"]
