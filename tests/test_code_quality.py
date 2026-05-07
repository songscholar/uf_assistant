"""Tests for indicator code quality analysis heuristics."""

from __future__ import annotations

from app.strategies.code_quality import analyze_indicator_code_quality


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _codes(hints: list[dict]) -> set[str]:
    """Extract the set of hint codes from a hints list."""
    return {h["code"] for h in hints}


def _has_code(hints: list[dict], code: str) -> bool:
    return any(h["code"] == code for h in hints)


def _severity_for(hints: list[dict], code: str) -> str | None:
    for h in hints:
        if h["code"] == code:
            return h["severity"]
    return None


# ---------------------------------------------------------------------------
# Fixtures: reusable code snippets
# ---------------------------------------------------------------------------

MINIMAL_VALID = """\
my_indicator_name = "MA Crossover"
my_indicator_description = "Moving average crossover strategy"

df = df.copy()
output = {}

# @strategy stopLossPct 0.02
# @strategy takeProfitPct 0.05

df['buy'] = (df['ma_fast'] > df['ma_slow'])
df['sell'] = (df['ma_fast'] < df['ma_slow'])

output['plots'] = [{'name': 'ma_fast'}]
output['signals'] = [{'type': 'buy'}]
"""


# ---------------------------------------------------------------------------
# 1. Empty code
# ---------------------------------------------------------------------------

class TestEmptyCode:
    def test_empty_string_returns_empty_code_hint(self) -> None:
        hints = analyze_indicator_code_quality("")
        assert _has_code(hints, "EMPTY_CODE")

    def test_whitespace_only_returns_empty_code_hint(self) -> None:
        hints = analyze_indicator_code_quality("   \n  \t  ")
        assert _has_code(hints, "EMPTY_CODE")

    def test_empty_code_has_error_severity(self) -> None:
        hints = analyze_indicator_code_quality("")
        assert _severity_for(hints, "EMPTY_CODE") == "error"

    def test_empty_code_returns_single_hint(self) -> None:
        hints = analyze_indicator_code_quality("")
        assert len(hints) == 1


# ---------------------------------------------------------------------------
# 2. Minimal valid code -- few or no issues
# ---------------------------------------------------------------------------

class TestMinimalValidCode:
    def test_no_error_hints(self) -> None:
        hints = analyze_indicator_code_quality(MINIMAL_VALID)
        error_codes = {h["code"] for h in hints if h["severity"] == "error"}
        assert error_codes == set()

    def test_no_missing_indicator_name(self) -> None:
        hints = analyze_indicator_code_quality(MINIMAL_VALID)
        assert not _has_code(hints, "MISSING_INDICATOR_NAME")

    def test_no_missing_df_copy(self) -> None:
        hints = analyze_indicator_code_quality(MINIMAL_VALID)
        assert not _has_code(hints, "MISSING_DF_COPY")

    def test_no_missing_output(self) -> None:
        hints = analyze_indicator_code_quality(MINIMAL_VALID)
        assert not _has_code(hints, "MISSING_OUTPUT")

    def test_no_missing_buy_sell(self) -> None:
        hints = analyze_indicator_code_quality(MINIMAL_VALID)
        assert not _has_code(hints, "MISSING_BUY_SELL_COLUMNS")

    def test_no_stop_loss_take_profit_issues(self) -> None:
        hints = analyze_indicator_code_quality(MINIMAL_VALID)
        assert not _has_code(hints, "NO_STOP_LOSS")
        assert not _has_code(hints, "NO_TAKE_PROFIT")
        assert not _has_code(hints, "NO_STOP_AND_TAKE_PROFIT")


# ---------------------------------------------------------------------------
# 3. Missing @indicator name
# ---------------------------------------------------------------------------

class TestMissingIndicatorName:
    CODE = """\
my_indicator_description = "desc"
df = df.copy()
output = {}
df['buy'] = True
"""

    def test_has_missing_indicator_name_hint(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        assert _has_code(hints, "MISSING_INDICATOR_NAME")

    def test_severity_is_warn(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        assert _severity_for(hints, "MISSING_INDICATOR_NAME") == "warn"


# ---------------------------------------------------------------------------
# 4. Missing df.copy()
# ---------------------------------------------------------------------------

class TestMissingDfCopy:
    CODE = """\
# @indicator Test
my_indicator_description = "desc"
output = {}
df['buy'] = True
"""

    def test_has_missing_df_copy_hint(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        assert _has_code(hints, "MISSING_DF_COPY")

    def test_severity_is_info(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        assert _severity_for(hints, "MISSING_DF_COPY") == "info"


# ---------------------------------------------------------------------------
# 5. No stop loss (but has take profit)
# ---------------------------------------------------------------------------

class TestNoStopLoss:
    CODE = """\
# @indicator Test
my_indicator_description = "desc"
df = df.copy()
output = {}
df['buy'] = True
df['sell'] = False
# @strategy takeProfitPct 0.05
"""

    def test_has_no_stop_loss_hint(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        assert _has_code(hints, "NO_STOP_LOSS")

    def test_no_take_profit_not_present(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        assert not _has_code(hints, "NO_TAKE_PROFIT")


# ---------------------------------------------------------------------------
# 6. No take profit (but has stop loss)
# ---------------------------------------------------------------------------

class TestNoTakeProfit:
    CODE = """\
# @indicator Test
my_indicator_description = "desc"
df = df.copy()
output = {}
df['buy'] = True
df['sell'] = False
# @strategy stopLossPct 0.02
"""

    def test_has_no_take_profit_hint(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        assert _has_code(hints, "NO_TAKE_PROFIT")

    def test_no_stop_loss_not_present(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        assert not _has_code(hints, "NO_STOP_LOSS")


# ---------------------------------------------------------------------------
# 7. Good code with all checks passing -- no error-severity issues
# ---------------------------------------------------------------------------

class TestGoodCodeNoErrors:
    """Comprehensive good code that should pass all structural checks."""

    CODE = """\
my_indicator_name = "RSI Mean Reversion"
my_indicator_description = "RSI-based mean reversion with volume filter"

# @param rsi_period int 14 RSI 计算周期
# @param oversold float 30 超卖阈值

# @strategy stopLossPct 0.03
# @strategy takeProfitPct 0.06
# @strategy entryPct 0.5

df = df.copy()
output = {}

rsi = df['close'].rolling(rsi_period).mean()
df['buy'] = (rsi < oversold) & (df['volume'] > df['volume'].rolling(20).mean())
df['sell'] = (rsi > 70)

output['plots'] = [{'name': 'rsi'}]
output['signals'] = [{'type': 'buy'}]
"""

    def test_no_error_severity_hints(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        error_codes = {h["code"] for h in hints if h["severity"] == "error"}
        assert error_codes == set()

    def test_no_structural_warnings(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        structural = {"MISSING_INDICATOR_NAME", "MISSING_DF_COPY", "MISSING_OUTPUT",
                      "MISSING_BUY_SELL_COLUMNS", "NO_STOP_AND_TAKE_PROFIT"}
        assert _codes(hints).isdisjoint(structural)

    def test_params_get_used_for_declared_params(self) -> None:
        """Declared @param should be read via params.get(), otherwise a warning fires."""
        hints = analyze_indicator_code_quality(self.CODE)
        # The snippet uses bare `rsi_period` / `oversold` -- no params.get()
        # so we expect the DECLARED_PARAMS_NOT_READ_VIA_PARAMS_GET warning.
        assert _has_code(hints, "DECLARED_PARAMS_NOT_READ_VIA_PARAMS_GET")

    def test_hint_structure_has_required_keys(self) -> None:
        hints = analyze_indicator_code_quality(self.CODE)
        for h in hints:
            assert "severity" in h
            assert "code" in h
            assert "params" in h
            assert h["severity"] in ("info", "warn", "error")
