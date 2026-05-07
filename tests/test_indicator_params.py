"""Tests for indicator parameter parsing and strategy config parsing."""

from __future__ import annotations

from app.strategies.indicator_params import IndicatorParamsParser, StrategyConfigParser


# ---------------------------------------------------------------------------
# StrategyConfigParser.parse
# ---------------------------------------------------------------------------


class TestStrategyConfigParserParse:
    def test_parse_single_float_key(self) -> None:
        code = "# @strategy stopLossPct 0.03"
        result = StrategyConfigParser.parse(code)
        assert result == {"stopLossPct": 0.03}

    def test_parse_multiple_keys(self) -> None:
        code = "# @strategy takeProfitPct 0.06\n# @strategy tradeDirection both"
        result = StrategyConfigParser.parse(code)
        assert result["takeProfitPct"] == 0.06
        assert result["tradeDirection"] == "both"

    def test_parse_empty_string(self) -> None:
        assert StrategyConfigParser.parse("") == {}

    def test_parse_no_annotations(self) -> None:
        code = "x = 1\ny = 2\nprint(x + y)"
        assert StrategyConfigParser.parse(code) == {}

    def test_unknown_keys_ignored(self) -> None:
        code = "# @strategy unknownKey 42\n# @strategy stopLossPct 0.05"
        result = StrategyConfigParser.parse(code)
        assert "unknownKey" not in result
        assert result == {"stopLossPct": 0.05}

    def test_bool_value_parsed(self) -> None:
        code = "# @strategy trailingEnabled true"
        result = StrategyConfigParser.parse(code)
        assert result["trailingEnabled"] is True

    def test_enum_fallback_for_invalid_value(self) -> None:
        code = "# @strategy tradeDirection invalid"
        result = StrategyConfigParser.parse(code)
        # invalid enum value falls back to first valid option
        assert result["tradeDirection"] == "long"

    def test_optional_colon_separator(self) -> None:
        code = "# @strategy stopLossPct: 0.02"
        result = StrategyConfigParser.parse(code)
        assert result == {"stopLossPct": 0.02}

    def test_none_input(self) -> None:
        assert StrategyConfigParser.parse(None) == {}  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# StrategyConfigParser.generate_annotations
# ---------------------------------------------------------------------------


class TestStrategyConfigParserGenerateAnnotations:
    def test_single_key(self) -> None:
        result = StrategyConfigParser.generate_annotations({"stopLossPct": 0.03})
        assert "# @strategy stopLossPct 0.03" in result

    def test_multiple_keys(self) -> None:
        config = {"stopLossPct": 0.03, "takeProfitPct": 0.06}
        result = StrategyConfigParser.generate_annotations(config)
        assert "# @strategy stopLossPct 0.03" in result
        assert "# @strategy takeProfitPct 0.06" in result

    def test_bool_formatted_as_lowercase(self) -> None:
        result = StrategyConfigParser.generate_annotations({"trailingEnabled": True})
        assert "# @strategy trailingEnabled true" in result

    def test_empty_config(self) -> None:
        assert StrategyConfigParser.generate_annotations({}) == ""


# ---------------------------------------------------------------------------
# IndicatorParamsParser.parse_params
# ---------------------------------------------------------------------------


class TestIndicatorParamsParserParseParams:
    def test_parse_int_param(self) -> None:
        code = "# @param fast_period int 12 short MA period"
        params = IndicatorParamsParser.parse_params(code)
        assert len(params) == 1
        assert params[0]["name"] == "fast_period"
        assert params[0]["type"] == "int"
        assert params[0]["default"] == 12
        assert params[0]["description"] == "short MA period"

    def test_parse_float_param(self) -> None:
        code = "# @param threshold float 0.5"
        params = IndicatorParamsParser.parse_params(code)
        assert len(params) == 1
        assert params[0]["type"] == "float"
        assert params[0]["default"] == 0.5

    def test_parse_bool_param(self) -> None:
        code = "# @param use_filter bool true"
        params = IndicatorParamsParser.parse_params(code)
        assert len(params) == 1
        assert params[0]["type"] == "bool"
        assert params[0]["default"] is True

    def test_parse_str_param(self) -> None:
        code = "# @param name str hello world"
        params = IndicatorParamsParser.parse_params(code)
        assert len(params) == 1
        assert params[0]["type"] == "str"
        assert params[0]["default"] == "hello"

    def test_parse_string_type_normalized_to_str(self) -> None:
        code = "# @param label string default_label"
        params = IndicatorParamsParser.parse_params(code)
        assert params[0]["type"] == "str"

    def test_no_params_returns_empty_list(self) -> None:
        code = "x = 1\n# just a comment\nprint(x)"
        assert IndicatorParamsParser.parse_params(code) == []

    def test_empty_string_returns_empty_list(self) -> None:
        assert IndicatorParamsParser.parse_params("") == []

    def test_multiple_params(self) -> None:
        code = (
            "# @param fast int 5 fast period\n"
            "# @param slow int 20 slow period\n"
            "# @param threshold float 0.5 threshold value"
        )
        params = IndicatorParamsParser.parse_params(code)
        assert len(params) == 3
        assert [p["name"] for p in params] == ["fast", "slow", "threshold"]


# ---------------------------------------------------------------------------
# IndicatorParamsParser.merge_params
# ---------------------------------------------------------------------------


class TestIndicatorParamsParserMergeParams:
    def test_user_override_replaces_default(self) -> None:
        declared = [{"name": "fast", "type": "int", "default": 12, "description": ""}]
        result = IndicatorParamsParser.merge_params(declared, {"fast": 20})
        assert result["fast"] == 20

    def test_default_used_when_user_empty(self) -> None:
        declared = [{"name": "fast", "type": "int", "default": 12, "description": ""}]
        result = IndicatorParamsParser.merge_params(declared, {})
        assert result["fast"] == 12

    def test_extra_user_params_ignored(self) -> None:
        declared = [{"name": "fast", "type": "int", "default": 12, "description": ""}]
        result = IndicatorParamsParser.merge_params(declared, {"fast": 20, "extra": 99})
        assert "extra" not in result
        assert result["fast"] == 20

    def test_type_coercion_on_user_value(self) -> None:
        declared = [{"name": "threshold", "type": "float", "default": 0.5, "description": ""}]
        result = IndicatorParamsParser.merge_params(declared, {"threshold": "1.5"})
        assert result["threshold"] == 1.5
        assert isinstance(result["threshold"], float)

    def test_multiple_params_partial_override(self) -> None:
        declared = [
            {"name": "fast", "type": "int", "default": 5, "description": ""},
            {"name": "slow", "type": "int", "default": 20, "description": ""},
        ]
        result = IndicatorParamsParser.merge_params(declared, {"slow": 30})
        assert result["fast"] == 5
        assert result["slow"] == 30
