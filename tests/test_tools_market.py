"""
测试市场数据工具模块
"""

from unittest.mock import MagicMock, patch

import pandas as pd

from app.tools.market import get_market_index


def _names_in_indices(result: dict, names: list[str]) -> bool:
    """检查结果中是否包含指定指数名称"""
    result_names = {item["name"] for item in result.get("indices", [])}
    return all(n in result_names for n in names)


class TestMarketTools:
    """测试市场工具"""

    def test_get_market_index_from_cache(self):
        """测试获取大盘指数（命中缓存路径）"""
        mock_df = pd.DataFrame({
            "代码": ["000001", "399001"],
            "名称": ["上证指数", "深证成指"],
            "最新价": [3000, 10000],
            "涨跌额": [12.0, -5.0],
            "涨跌幅": [0.5, 0.3],
        })

        with patch("app.tools.market.ensure_cache", return_value=mock_df):
            result = get_market_index()
            assert _names_in_indices(result, ["上证指数", "深证成指"])
            assert result["source"] == "live"

    def test_get_market_index_fallback(self):
        """测试缓存 miss 时的 fallback 路径"""
        mock_df = MagicMock()
        mock_df.iterrows.return_value = iter([
            (0, {"代码": "000001", "名称": "上证指数", "最新价": 3000, "涨跌额": 12.0, "涨跌幅": 0.5}),
            (1, {"代码": "399001", "名称": "深证成指", "最新价": 10000, "涨跌额": -5.0, "涨跌幅": 0.3}),
        ])

        with patch("app.tools.market.ensure_cache", return_value=None):
            with patch("app.tools.market._get_ak") as mock_ak:
                mock_ak.return_value.stock_zh_index_spot_em.return_value = mock_df
                result = get_market_index()
                assert _names_in_indices(result, ["上证指数", "深证成指"])
                assert result["source"] == "live"
