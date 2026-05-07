"""
测试 AI 分析记忆与反射校准模块
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.analysis_models import AICalibrationModel, AnalysisMemoryModel, Base
from app.services.ai_calibration import AICalibrationService
from app.services.analysis_memory import AnalysisMemoryService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ------------------------------------------------------------------
# AnalysisMemoryService
# ------------------------------------------------------------------

class TestAnalysisMemoryService:
    def test_store_and_get(self, db_session):
        svc = AnalysisMemoryService(session=db_session)
        result = {
            "market": "AStock",
            "symbol": "000001.SZ",
            "decision": "BUY",
            "confidence": 75,
            "summary": "上升趋势",
            "reasons": ["RSI 超卖", "MACD 金叉"],
            "scores": {"rsi": 30, "macd": 1.5},
            "indicators_snapshot": {"rsi_14": 30, "macd_signal": 1.5},
            "raw_result": {"model": "kimi"},
            "consensus_score": 22.5,
            "consensus_abs": 22.5,
            "agreement_ratio": 0.85,
            "quality_multiplier": 0.9,
        }
        mid = svc.store(result, user_id="u1")
        assert mid > 0
        recent = svc.get_recent("AStock", "000001.SZ", days=7, limit=5)
        assert len(recent) == 1
        assert recent[0]["decision"] == "BUY"
        assert recent[0]["confidence"] == 75

    def test_get_history_pagination(self, db_session):
        svc = AnalysisMemoryService(session=db_session)
        for i in range(5):
            svc.store({
                "market": "AStock",
                "symbol": "000001.SZ",
                "decision": "BUY",
                "confidence": 50 + i,
                "summary": f"分析{i}",
                "reasons": [],
                "scores": {},
                "indicators_snapshot": {},
                "raw_result": {},
            }, user_id="u1")
        data = svc.get_history("u1", page=1, page_size=2)
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1

    def test_record_feedback(self, db_session):
        svc = AnalysisMemoryService(session=db_session)
        mid = svc.store({
            "market": "AStock",
            "symbol": "000001.SZ",
            "decision": "SELL",
            "confidence": 60,
            "summary": "测试",
            "reasons": [],
            "scores": {},
            "indicators_snapshot": {},
            "raw_result": {},
        }, user_id="u2")
        ok = svc.record_feedback(mid, "helpful")
        assert ok is True
        row = db_session.query(AnalysisMemoryModel).get(mid)
        assert row.user_feedback == "helpful"
        assert row.feedback_at is not None

    def test_get_similar_patterns_empty(self, db_session):
        svc = AnalysisMemoryService(session=db_session)
        patterns = svc.get_similar_patterns("AStock", "000001.SZ", {}, limit=3)
        assert patterns == []

    def test_store_with_price_and_indicators(self, db_session):
        svc = AnalysisMemoryService(session=db_session)
        mid = svc.store({
            "market": "AStock",
            "symbol": "000001.SZ",
            "decision": "HOLD",
            "confidence": 55,
            "summary": "震荡",
            "reasons": ["无明显信号"],
            "scores": {"rsi": 50},
            "indicators_snapshot": {"rsi_14": 50, "macd": 0},
            "raw_result": {},
            "market_data": {"current_price": 100.5},
        }, user_id="u3")
        row = db_session.query(AnalysisMemoryModel).get(mid)
        assert float(row.price_at_analysis) == pytest.approx(100.5)


# ------------------------------------------------------------------
# AICalibrationService
# ------------------------------------------------------------------

class TestAICalibrationService:
    def test_get_latest_defaults(self, db_session):
        svc = AICalibrationService(session=db_session)
        cfg = svc.get_latest("Crypto")
        assert cfg["buy_threshold"] == 20.0
        assert cfg["sell_threshold"] == -20.0
        assert cfg["min_consensus_abs_override"] == 15.0
        assert cfg["quality_hold_threshold"] == 0.7

    def test_calibrate_market_no_samples(self, db_session):
        svc = AICalibrationService(session=db_session)
        result = svc.calibrate_market("AStock", lookback_days=30, min_samples=10)
        assert result is None

    def test_calibrate_market_with_samples(self, db_session):
        svc = AICalibrationService(session=db_session)
        # 创建足够样本：BUY 正确、SELL 正确、HOLD 正确
        now = datetime.now(timezone.utc)
        for i in range(30):
            decision = ["BUY", "SELL", "HOLD"][i % 3]
            ret = 5.0 if i % 3 == 0 else (-5.0 if i % 3 == 1 else 2.0)
            m = AnalysisMemoryModel(
                user_id="u1",
                market="Crypto",
                symbol="BTC/USDT",
                decision=decision,
                confidence=60,
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
                validated_at=now,
                actual_return_pct=ret,
                consensus_score=22.5 if decision == "BUY" else (-22.5 if decision == "SELL" else 5.0),
                was_correct=True,
            )
            db_session.add(m)
        db_session.commit()
        result = svc.calibrate_market("Crypto", lookback_days=30, min_samples=10)
        assert result is not None
        assert result.buy_threshold is not None
        assert result.sell_threshold is not None
        # 校准结果应存入数据库
        latest = db_session.query(AICalibrationModel).filter_by(market="Crypto").order_by(AICalibrationModel.id.desc()).first()
        assert latest is not None

    def test_predict_decision_from_score(self, db_session):
        from app.services.ai_calibration import _predict_from_score
        assert _predict_from_score(25, 15) == "BUY"
        assert _predict_from_score(-25, 15) == "SELL"
        assert _predict_from_score(10, 15) == "HOLD"
        assert _predict_from_score(-10, 15) == "HOLD"


# ------------------------------------------------------------------
# AnalysisModels
# ------------------------------------------------------------------

class TestAnalysisModels:
    def test_json_columns(self, db_session):
        m = AnalysisMemoryModel(
            user_id="u1",
            market="AStock",
            symbol="000001.SZ",
            decision="BUY",
            reasons=["reason1"],
            scores={"rsi": 30},
            indicators_snapshot={"ma5": 10.0},
            raw_result={"model": "test"},
        )
        db_session.add(m)
        db_session.commit()
        row = db_session.query(AnalysisMemoryModel).first()
        assert row.reasons == ["reason1"]
        assert row.scores == {"rsi": 30}
        assert row.indicators_snapshot == {"ma5": 10.0}
        assert row.raw_result == {"model": "test"}
