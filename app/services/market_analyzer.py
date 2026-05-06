"""
UF Stock Assistant — 市场分析服务
整合市场数据生成分析报告
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.tools.market import get_market_index, get_market_overview, get_sector_hot

logger = get_logger("app.services.market_analyzer")


class MarketAnalyzer:
    """
    市场分析器
    
    整合多项市场数据，生成综合分析报告
    """
    
    def __init__(self) -> None:
        pass
    
    def generate_daily_report(self) -> str:
        """
        生成每日市场分析报告
        
        Returns:
            JSON 格式的分析报告
        """
        try:
            # 获取市场概况
            overview = json.loads(get_market_overview())
            
            # 获取大盘指数
            indices = json.loads(get_market_index())
            
            # 获取板块热点
            sectors = json.loads(get_sector_hot())
            
            # 分析涨跌分布
            summary = overview.get("summary", {})
            up = summary.get("up", 0)
            down = summary.get("down", 0)
            flat = summary.get("flat", 0)
            total = up + down + flat
            
            if total > 0:
                up_ratio = round(up / total * 100, 2)
                down_ratio = round(down / total * 100, 2)
            else:
                up_ratio = down_ratio = 0
            
            # 判断市场情绪
            if up_ratio > 60:
                sentiment = "强势"
                sentiment_level = 3
            elif up_ratio > 50:
                sentiment = "偏强"
                sentiment_level = 2
            elif up_ratio > 40:
                sentiment = "中性"
                sentiment_level = 1
            else:
                sentiment = "偏弱"
                sentiment_level = 0
            
            # 判断主要指数趋势
            index_trends = []
            for idx in indices.get("indices", []):
                change = idx.get("change_pct", 0) or 0
                if change > 1:
                    trend = "大涨"
                elif change > 0:
                    trend = "上涨"
                elif change > -1:
                    trend = "微跌"
                else:
                    trend = "大跌"
                
                index_trends.append({
                    "name": idx.get("name"),
                    "price": idx.get("price"),
                    "change_pct": change,
                    "trend": trend,
                })
            
            report = {
                "type": "daily_market_report",
                "timestamp": overview.get("timestamp"),
                "market_summary": {
                    "total_stocks": total,
                    "up": up,
                    "down": down,
                    "flat": flat,
                    "up_ratio": up_ratio,
                    "down_ratio": down_ratio,
                    "limit_up": summary.get("limit_up", 0),
                    "limit_down": summary.get("limit_down", 0),
                    "sentiment": sentiment,
                    "sentiment_level": sentiment_level,
                },
                "indices": index_trends,
                "hot_sectors": {
                    "industries": sectors.get("industries", [])[:5],
                    "concepts": sectors.get("concepts", [])[:5],
                },
                "analysis": {
                    "overall": f"今日市场{sentiment}，上涨家数占比 {up_ratio}%",
                    "risk_level": self._calculate_risk_level(sentiment_level, down_ratio),
                },
            }
            
            logger.info("daily_report_generated")
            return json.dumps(report, ensure_ascii=False, default=str)
            
        except Exception as exc:
            logger.error("daily_report_failed", error=str(exc))
            return json.dumps({"error": f"生成报告失败: {exc}"}, ensure_ascii=False)
    
    def _calculate_risk_level(self, sentiment_level: int, down_ratio: float) -> dict[str, Any]:
        """计算风险等级"""
        if sentiment_level >= 2 and down_ratio < 30:
            level = 1
            desc = "低风险"
        elif sentiment_level >= 1 and down_ratio < 40:
            level = 2
            desc = "中低风险"
        elif sentiment_level >= 0 and down_ratio < 50:
            level = 3
            desc = "中等风险"
        elif down_ratio < 60:
            level = 4
            desc = "中高风险"
        else:
            level = 5
            desc = "高风险"
        
        return {
            "level": level,
            "description": desc,
            "suggestion": self._risk_suggestion(level),
        }
    
    def _risk_suggestion(self, level: int) -> str:
        """根据风险等级给出建议"""
        suggestions = {
            1: "市场情绪积极，可适当增加仓位",
            2: "市场情绪良好，可维持现有仓位",
            3: "市场情绪中性，建议控制仓位",
            4: "市场情绪偏弱，建议减仓观望",
            5: "市场情绪悲观，建议降低仓位或空仓观望",
        }
        return suggestions.get(level, "建议观望")
    
    def analyze_sector_rotation(self) -> str:
        """
        分析板块轮动
        
        Returns:
            JSON 格式的板块分析
        """
        try:
            sectors = json.loads(get_sector_hot())
            
            industries = sectors.get("industries", [])
            concepts = sectors.get("concepts", [])
            
            # 计算板块热度
            hot_industries = [s for s in industries if s.get("change_pct", 0) > 2]
            cold_industries = [s for s in industries if s.get("change_pct", 0) < -2]
            
            analysis = {
                "hot_industries": hot_industries[:5],
                "cold_industries": cold_industries[:5],
                "hot_concepts": concepts[:5],
                "rotation_analysis": {
                    "leading": [s["name"] for s in hot_industries[:3]],
                    "lagging": [s["name"] for s in cold_industries[:3]],
                },
            }
            
            return json.dumps(analysis, ensure_ascii=False, default=str)
            
        except Exception as exc:
            logger.error("sector_analysis_failed", error=str(exc))
            return json.dumps({"error": f"板块分析失败: {exc}"}, ensure_ascii=False)
