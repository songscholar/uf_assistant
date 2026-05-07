"""
测试 IndicatorCaller — 指标间互相调用（递归深度、环形检测、DB查询）
"""

from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.strategies.indicator_caller import IndicatorCaller
from app.strategies.models import Base, IndicatorModel


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_df():
    """创建一个简单的 OHLCV DataFrame"""
    return pd.DataFrame({
        "open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "high": [101.0, 102.0, 103.0, 104.0, 105.0],
        "low": [99.0, 100.0, 101.0, 102.0, 103.0],
        "close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "volume": [1000, 2000, 1500, 3000, 2500],
    })


class TestIndicatorCallerDepthLimit:
    def test_max_depth_exceeded(self, sample_df):
        """递归深度超过 MAX_CALL_DEPTH=5 时应被截断"""
        caller = IndicatorCaller(user_id="u1")
        # 手动设置深度为 5，第 6 层调用应被截断
        result = caller.call_indicator("nonexistent", sample_df, _depth=5)
        assert "error" in result
        assert "depth exceeded" in result["error"]

    def test_depth_increments_on_nested_call(self, db_session, sample_df):
        """嵌套调用时深度应递增，第6层被截断返回 error dict"""
        # 创建一个自调用指标
        self_call_code = """
# 自调用指标：无限递归
result = call_indicator('SelfCall', df)
df['buy'] = True
df['sell'] = False
"""
        ind = IndicatorModel(
            user_id="u1",
            name="SelfCall",
            code=self_call_code,
        )
        db_session.add(ind)
        db_session.commit()

        caller = IndicatorCaller(user_id="u1", session=db_session)
        result = caller.call_indicator("SelfCall", sample_df)
        # 第 5 层自调用时深度达到 MAX_CALL_DEPTH=5，返回 error
        # 但外层指标继续执行并设置 buy/sell
        assert "error" not in result
        assert result["buy"].all()


class TestIndicatorCallerCircularDetection:
    def test_circular_dependency_a_to_b_to_a(self, db_session, sample_df):
        """A→B→A 环形依赖应被检测，error dict 返回给调用方，外层继续执行"""
        code_a = """
result_b = call_indicator('IndicatorB', df)
df['buy'] = True
df['sell'] = False
"""
        code_b = """
result_a = call_indicator('IndicatorA', df)
df['buy'] = False
df['sell'] = True
"""
        ind_a = IndicatorModel(user_id="u1", name="IndicatorA", code=code_a)
        ind_b = IndicatorModel(user_id="u1", name="IndicatorB", code=code_b)
        db_session.add_all([ind_a, ind_b])
        db_session.commit()

        caller = IndicatorCaller(user_id="u1", session=db_session)
        result = caller.call_indicator("IndicatorA", sample_df)
        # 环形检测触发时返回 error dict 给 B，B 继续执行设置 buy/sell
        # A 获得 B 的结果（含 buy=True）
        assert "error" not in result
        assert result["buy"].all()  # B 设置了 buy=True


class TestIndicatorCallerDbLookup:
    def test_lookup_by_name_builtin(self, db_session, sample_df):
        """按名称查询内置指标"""
        code = """
df['buy'] = df['close'] > df['open']
df['sell'] = df['close'] < df['open']
"""
        ind = IndicatorModel(
            user_id="u1",
            name="SimpleCross",
            code=code,
            is_builtin=True,
        )
        db_session.add(ind)
        db_session.commit()

        caller = IndicatorCaller(user_id="u1", session=db_session)
        result = caller.call_indicator("SimpleCross", sample_df)
        assert "error" not in result
        assert "buy" in result
        assert "sell" in result
        assert result["buy"].dtype == bool

    def test_lookup_by_id(self, db_session, sample_df):
        """按 UUID ID 查询指标"""
        code = """
df['buy'] = [True, False, True, False, True]
df['sell'] = [False, True, False, True, False]
"""
        ind = IndicatorModel(
            user_id="u1",
            name="ByIdTest",
            code=code,
        )
        db_session.add(ind)
        db_session.commit()

        caller = IndicatorCaller(user_id="u1", session=db_session)
        result = caller.call_indicator(ind.id, sample_df)
        assert "error" not in result
        assert result["buy"].sum() == 3
        assert result["sell"].sum() == 2

    def test_lookup_not_found(self, sample_df):
        """查询不存在的指标应返回错误"""
        caller = IndicatorCaller(user_id="u1", session=None)
        result = caller.call_indicator("NonExistent", sample_df)
        assert "error" in result
        assert "not found" in result["error"]


class TestIndicatorCallerParams:
    def test_params_passed_to_indicator(self, db_session, sample_df):
        """参数应正确传递给被调用指标"""
        code = """
threshold = params.get('threshold', 100)
df['buy'] = df['close'] > threshold
df['sell'] = df['close'] <= threshold
"""
        ind = IndicatorModel(
            user_id="u1",
            name="ParamTest",
            code=code,
        )
        db_session.add(ind)
        db_session.commit()

        caller = IndicatorCaller(user_id="u1", session=db_session)
        result = caller.call_indicator("ParamTest", sample_df, {"threshold": 102})
        assert "error" not in result
        # close = [100.5, 101.5, 102.5, 103.5, 104.5], threshold=102
        # buy = [F, F, T, T, T]
        assert result["buy"].sum() == 3
        assert result["sell"].sum() == 2

    def test_user_scoping(self, db_session, sample_df):
        """用户只能访问自己的指标和内置指标"""
        private_code = "df['buy'] = True; df['sell'] = False"
        ind = IndicatorModel(
            user_id="u1",
            name="Private",
            code=private_code,
        )
        db_session.add(ind)
        db_session.commit()

        # u2 不能访问 u1 的 Private 指标
        caller_u2 = IndicatorCaller(user_id="u2", session=db_session)
        result = caller_u2.call_indicator("Private", sample_df)
        assert "error" in result
        assert "not found" in result["error"]

        # u1 可以访问自己的 Private 指标
        caller_u1 = IndicatorCaller(user_id="u1", session=db_session)
        result = caller_u1.call_indicator("Private", sample_df)
        assert "error" not in result
