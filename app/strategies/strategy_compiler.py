"""
UF Stock Assistant — Strategy Compiler

Compiles declarative strategy configuration (indicators + entry rules + risk management)
into executable Python backtest code that runs via BacktestService._run_script_strategy().
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger("app.strategies.strategy_compiler")


class StrategyCompiler:
    """Compile declarative strategy config into executable on_bar Python code."""

    def compile(self, config: dict[str, Any]) -> str:
        """
        Compiles the strategy configuration JSON into executable Python code.

        Config schema:
            name: str — strategy name
            entry_rules: list[dict] — each with indicator, params, operator/signal
            position_config: dict — initial_size_pct, leverage, max_pyramiding
            pyramiding_rules: dict — enabled, size_pct, value
            risk_management: dict — stop_loss, trailing_stop
        """
        name = config.get("name", "Generated Strategy")
        entry_rules = config.get("entry_rules", [])
        position_config = config.get("position_config", {})
        pyramiding_rules = config.get("pyramiding_rules", {})
        risk_management = config.get("risk_management", {})

        code = self._get_header(name)
        code += self._get_parameters(position_config, pyramiding_rules, risk_management)
        code += self._get_indicators_calculation(entry_rules)
        code += self._get_entry_logic(entry_rules)
        code += self._get_core_loop()
        code += self._get_output_section(name, entry_rules)

        logger.info("strategy_compiled", name=name, rules=len(entry_rules))
        return code

    # ── Header ──────────────────────────────────────────────────────────────

    def _get_header(self, name: str) -> str:
        return f'''# Generated Strategy: {name}
import numpy as np

def get_val(arr, i, default=0):
    if i < 0 or i >= len(arr): return default
    return arr[i]
'''

    # ── Parameters ──────────────────────────────────────────────────────────

    def _get_parameters(
        self,
        pos_config: dict[str, Any],
        pyr_rules: dict[str, Any],
        risk_mgmt: dict[str, Any],
    ) -> str:
        initial_size = pos_config.get("initial_size_pct", 10) / 100.0
        leverage = pos_config.get("leverage", 1)
        max_pyramiding = pos_config.get("max_pyramiding", 0)

        pyr_enabled = pyr_rules.get("enabled", False)
        add_size = pyr_rules.get("size_pct", 0) / 100.0 if pyr_enabled else 0
        add_threshold = pyr_rules.get("value", 0) / 100.0

        stop_loss = risk_mgmt.get("stop_loss", {})
        sl_enabled = stop_loss.get("enabled", False)
        sl_pct = stop_loss.get("value", 0) / 100.0 if sl_enabled else 0.0

        trailing = risk_mgmt.get("trailing_stop", {})
        ts_activation = trailing.get("activation_profit", 0) / 100.0
        ts_callback = trailing.get("callback_pct", 0) / 100.0

        return f'''
# ===========================
# 1. Parameters
# ===========================
initial_position_pct = {initial_size}
leverage = {leverage}
max_pyramiding = {max_pyramiding}

# Pyramiding
add_position_pct = {add_size}
add_threshold_pct = {add_threshold}

# Risk Management
stop_loss_pct = {sl_pct}
take_profit_activation = {ts_activation}
trailing_callback = {ts_callback}
'''

    # ── Indicators ──────────────────────────────────────────────────────────

    def _get_indicators_calculation(self, rules: list[dict[str, Any]]) -> str:
        code = """
# ===========================
# 2. Indicators Calculation
# ===========================
"""
        calculated: set[str] = set()

        for rule in rules:
            ind = rule.get("indicator")
            params = rule.get("params", {})

            if ind == "supertrend":
                key = f"st_{params.get('period')}_{params.get('multiplier')}"
                if key not in calculated:
                    code += self._code_supertrend(params)
                    calculated.add(key)

            elif ind == "ema":
                period = params.get("period", 20)
                key = f"ema_{period}"
                if key not in calculated:
                    code += f"\ndf['ema_{period}'] = df['close'].ewm(span={period}, adjust=False).mean()\n"
                    calculated.add(key)

            elif ind == "rsi":
                period = params.get("period", 14)
                key = f"rsi_{period}"
                if key not in calculated:
                    code += self._code_rsi(period)
                    calculated.add(key)

            elif ind == "macd":
                fast = params.get("fast_period", 12)
                slow = params.get("slow_period", 26)
                signal = params.get("signal_period", 9)
                key = f"macd_{fast}_{slow}_{signal}"
                if key not in calculated:
                    code += self._code_macd(fast, slow, signal)
                    calculated.add(key)

            elif ind == "bollinger":
                period = params.get("period", 20)
                std_dev = params.get("std_dev", 2.0)
                key = f"bb_{period}_{std_dev}"
                if key not in calculated:
                    code += self._code_bollinger(period, std_dev)
                    calculated.add(key)

            elif ind == "kdj":
                period = params.get("period", 9)
                signal_period = params.get("signal_period", 3)
                key = f"kdj_{period}_{signal_period}"
                if key not in calculated:
                    code += self._code_kdj(period, signal_period)
                    calculated.add(key)

            elif ind == "ma":
                period = params.get("period", 20)
                ma_type = params.get("ma_type", "sma")
                key = f"ma_{ma_type}_{period}"
                if key not in calculated:
                    if ma_type == "ema":
                        code += f"\ndf['ma_{ma_type}_{period}'] = df['close'].ewm(span={period}, adjust=False).mean()\n"
                    else:
                        code += f"\ndf['ma_{ma_type}_{period}'] = df['close'].rolling(window={period}).mean()\n"
                    calculated.add(key)

        return code

    @staticmethod
    def _code_supertrend(params: dict[str, Any]) -> str:
        period = params.get("period", 14)
        multiplier = params.get("multiplier", 3.0)
        return f"""
# SuperTrend ({period}, {multiplier})
period = {period}
multiplier = {multiplier}
df['hl2'] = (df['high'] + df['low']) / 2
df['tr'] = np.maximum(df['high'] - df['low'], np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))))
df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
df['basic_upper'] = df['hl2'] + (multiplier * df['atr'])
df['basic_lower'] = df['hl2'] - (multiplier * df['atr'])

final_upper = [0.0] * len(df)
final_lower = [0.0] * len(df)
trend = [1] * len(df)
close_arr = df['close'].values
basic_upper = np.nan_to_num(df['basic_upper'].values)
basic_lower = np.nan_to_num(df['basic_lower'].values)

for i in range(1, len(df)):
    if basic_upper[i] < final_upper[i-1] or close_arr[i-1] > final_upper[i-1]:
        final_upper[i] = basic_upper[i]
    else:
        final_upper[i] = final_upper[i-1]
    if basic_lower[i] > final_lower[i-1] or close_arr[i-1] < final_lower[i-1]:
        final_lower[i] = basic_lower[i]
    else:
        final_lower[i] = final_lower[i-1]
    prev_trend = trend[i-1]
    if prev_trend == -1 and close_arr[i] > final_upper[i-1]:
        trend[i] = 1
    elif prev_trend == 1 and close_arr[i] < final_lower[i-1]:
        trend[i] = -1
    else:
        trend[i] = prev_trend

df['st_trend'] = trend
df['st_upper'] = final_upper
df['st_lower'] = final_lower
"""

    @staticmethod
    def _code_rsi(period: int) -> str:
        return f"""
# RSI ({period})
delta = df['close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(window={period}).mean()
loss = (-delta.where(delta < 0, 0)).rolling(window={period}).mean()
rs = gain / loss
df['rsi_{period}'] = 100 - (100 / (1 + rs))
"""

    @staticmethod
    def _code_macd(fast: int, slow: int, signal: int) -> str:
        return f"""
# MACD ({fast}, {slow}, {signal})
exp1 = df['close'].ewm(span={fast}, adjust=False).mean()
exp2 = df['close'].ewm(span={slow}, adjust=False).mean()
df['macd_{fast}_{slow}_{signal}_line'] = exp1 - exp2
df['macd_{fast}_{slow}_{signal}_signal'] = df['macd_{fast}_{slow}_{signal}_line'].ewm(span={signal}, adjust=False).mean()
df['macd_{fast}_{slow}_{signal}_hist'] = df['macd_{fast}_{slow}_{signal}_line'] - df['macd_{fast}_{slow}_{signal}_signal']
"""

    @staticmethod
    def _code_bollinger(period: int, std_dev: float) -> str:
        return f"""
# Bollinger Bands ({period}, {std_dev})
sma = df['close'].rolling(window={period}).mean()
std = df['close'].rolling(window={period}).std()
df['bb_{period}_{std_dev}_upper'] = sma + ({std_dev} * std)
df['bb_{period}_{std_dev}_lower'] = sma - ({std_dev} * std)
df['bb_{period}_{std_dev}_mid'] = sma
"""

    @staticmethod
    def _code_kdj(period: int, signal_period: int) -> str:
        return f"""
# KDJ ({period}, {signal_period})
low_min = df['low'].rolling(window={period}).min()
high_max = df['high'].rolling(window={period}).max()
rsv = (df['close'] - low_min) / (high_max - low_min) * 100
df['kdj_{period}_{signal_period}_k'] = rsv.ewm(alpha=1/{signal_period}, adjust=False).mean()
df['kdj_{period}_{signal_period}_d'] = df['kdj_{period}_{signal_period}_k'].ewm(alpha=1/{signal_period}, adjust=False).mean()
df['kdj_{period}_{signal_period}_j'] = 3 * df['kdj_{period}_{signal_period}_k'] - 2 * df['kdj_{period}_{signal_period}_d']
"""

    # ── Entry Logic ─────────────────────────────────────────────────────────

    def _get_entry_logic(self, rules: list[dict[str, Any]]) -> str:
        code = """
# ===========================
# 3. Entry Signal Logic
# ===========================
df['raw_buy'] = False
df['raw_sell'] = False
"""
        conditions_buy: list[str] = []
        conditions_sell: list[str] = []

        for rule in rules:
            ind = rule.get("indicator")
            params = rule.get("params", {})
            operator = rule.get("operator", "")
            signal = rule.get("signal", "")

            if ind == "supertrend":
                if signal == "trend_bullish":
                    conditions_buy.append("(df['st_trend'] == 1) & (df['st_trend'].shift(1) == -1)")
                    conditions_sell.append("(df['st_trend'] == -1) & (df['st_trend'].shift(1) == 1)")
                elif signal == "is_uptrend":
                    conditions_buy.append("(df['st_trend'] == 1)")
                    conditions_sell.append("(df['st_trend'] == -1)")

            elif ind == "ema":
                period = params.get("period", 20)
                col = f"df['ema_{period}']"
                buy, sell = self._ema_conditions(col, operator)
                if buy:
                    conditions_buy.append(buy)
                if sell:
                    conditions_sell.append(sell)

            elif ind == "rsi":
                period = params.get("period", 14)
                thresh = params.get("threshold", 30)
                col = f"df['rsi_{period}']"
                buy, sell = self._rsi_conditions(col, operator, thresh)
                if buy:
                    conditions_buy.append(buy)
                if sell:
                    conditions_sell.append(sell)

            elif ind == "macd":
                fast = params.get("fast_period", 12)
                slow = params.get("slow_period", 26)
                sig = params.get("signal_period", 9)
                line_col = f"df['macd_{fast}_{slow}_{sig}_line']"
                sig_col = f"df['macd_{fast}_{slow}_{sig}_signal']"
                buy, sell = self._macd_conditions(line_col, sig_col, operator)
                if buy:
                    conditions_buy.append(buy)
                if sell:
                    conditions_sell.append(sell)

            elif ind == "bollinger":
                period = params.get("period", 20)
                std_dev = params.get("std_dev", 2.0)
                upper = f"df['bb_{period}_{std_dev}_upper']"
                lower = f"df['bb_{period}_{std_dev}_lower']"
                mid = f"df['bb_{period}_{std_dev}_mid']"
                buy, sell = self._bollinger_conditions(upper, lower, mid, operator)
                if buy:
                    conditions_buy.append(buy)
                if sell:
                    conditions_sell.append(sell)

            elif ind == "kdj":
                period = params.get("period", 9)
                sig = params.get("signal_period", 3)
                k_col = f"df['kdj_{period}_{sig}_k']"
                d_col = f"df['kdj_{period}_{sig}_d']"
                buy, sell = self._kdj_conditions(k_col, d_col, operator)
                if buy:
                    conditions_buy.append(buy)
                if sell:
                    conditions_sell.append(sell)

            elif ind == "ma":
                period = params.get("period", 20)
                ma_type = params.get("ma_type", "sma")
                col = f"df['ma_{ma_type}_{period}']"
                buy, sell = self._ema_conditions(col, operator)
                if buy:
                    conditions_buy.append(buy)
                if sell:
                    conditions_sell.append(sell)

        if conditions_buy:
            code += f"\ndf['raw_buy'] = {' & '.join(conditions_buy)}\n"
        if conditions_sell:
            code += f"\ndf['raw_sell'] = {' & '.join(conditions_sell)}\n"

        return code

    @staticmethod
    def _ema_conditions(col: str, operator: str) -> tuple[str, str]:
        """Return (buy_condition, sell_condition) for EMA/MA."""
        if operator == "price_above":
            return f"(df['close'] > {col})", f"(df['close'] < {col})"
        if operator == "price_below":
            return f"(df['close'] < {col})", f"(df['close'] > {col})"
        if operator == "cross_up":
            return (
                f"(df['close'] > {col}) & (df['close'].shift(1) <= {col}.shift(1))",
                f"(df['close'] < {col}) & (df['close'].shift(1) >= {col}.shift(1))",
            )
        if operator == "cross_down":
            return (
                f"(df['close'] < {col}) & (df['close'].shift(1) >= {col}.shift(1))",
                f"(df['close'] > {col}) & (df['close'].shift(1) <= {col}.shift(1))",
            )
        return "", ""

    @staticmethod
    def _rsi_conditions(col: str, operator: str, thresh: int) -> tuple[str, str]:
        """Return (buy_condition, sell_condition) for RSI."""
        inv = 100 - thresh
        if operator == "<":
            return f"({col} < {thresh})", f"({col} > {inv})"
        if operator == ">":
            return f"({col} > {thresh})", f"({col} < {inv})"
        if operator == "cross_up":
            return f"({col} > {thresh}) & ({col}.shift(1) <= {thresh})", f"({col} < {inv}) & ({col}.shift(1) >= {inv})"
        if operator == "cross_down":
            return f"({col} < {thresh}) & ({col}.shift(1) >= {thresh})", f"({col} > {inv}) & ({col}.shift(1) <= {inv})"
        return "", ""

    @staticmethod
    def _macd_conditions(line_col: str, sig_col: str, operator: str) -> tuple[str, str]:
        """Return (buy_condition, sell_condition) for MACD."""
        if operator == "diff_gt_dea":
            return f"({line_col} > {sig_col})", f"({line_col} < {sig_col})"
        if operator == "diff_lt_dea":
            return f"({line_col} < {sig_col})", f"({line_col} > {sig_col})"
        if operator == "cross_up":
            return (
                f"({line_col} > {sig_col}) & ({line_col}.shift(1) <= {sig_col}.shift(1))",
                f"({line_col} < {sig_col}) & ({line_col}.shift(1) >= {sig_col}.shift(1))",
            )
        if operator == "cross_down":
            return (
                f"({line_col} < {sig_col}) & ({line_col}.shift(1) >= {sig_col}.shift(1))",
                f"({line_col} > {sig_col}) & ({line_col}.shift(1) <= {sig_col}.shift(1))",
            )
        return "", ""

    @staticmethod
    def _bollinger_conditions(
        upper: str, lower: str, mid: str, operator: str
    ) -> tuple[str, str]:
        """Return (buy_condition, sell_condition) for Bollinger Bands."""
        if operator == "price_above_upper":
            return f"(df['close'] > {upper})", f"(df['close'] < {lower})"
        if operator == "price_below_lower":
            return f"(df['close'] < {lower})", f"(df['close'] > {upper})"
        if operator == "price_above_mid":
            return f"(df['close'] > {mid})", f"(df['close'] < {mid})"
        if operator == "price_below_mid":
            return f"(df['close'] < {mid})", f"(df['close'] > {mid})"
        if operator == "cross_up_lower":
            return (
                f"(df['close'] > {lower}) & (df['close'].shift(1) <= {lower}.shift(1))",
                f"(df['close'] < {upper}) & (df['close'].shift(1) >= {upper}.shift(1))",
            )
        if operator == "cross_down_upper":
            return (
                f"(df['close'] < {upper}) & (df['close'].shift(1) >= {upper}.shift(1))",
                f"(df['close'] > {lower}) & (df['close'].shift(1) <= {lower}.shift(1))",
            )
        return "", ""

    @staticmethod
    def _kdj_conditions(k_col: str, d_col: str, operator: str) -> tuple[str, str]:
        """Return (buy_condition, sell_condition) for KDJ."""
        if operator == "k_gt_d":
            return f"({k_col} > {d_col})", f"({k_col} < {d_col})"
        if operator == "k_lt_d":
            return f"({k_col} < {d_col})", f"({k_col} > {d_col})"
        if operator == "gold_cross":
            return (
                f"({k_col} > {d_col}) & ({k_col}.shift(1) <= {d_col}.shift(1))",
                f"({k_col} < {d_col}) & ({k_col}.shift(1) >= {d_col}.shift(1))",
            )
        if operator == "death_cross":
            return (
                f"({k_col} < {d_col}) & ({k_col}.shift(1) >= {d_col}.shift(1))",
                f"({k_col} > {d_col}) & ({k_col}.shift(1) <= {d_col}.shift(1))",
            )
        return "", ""

    # ── Core Loop ───────────────────────────────────────────────────────────

    @staticmethod
    def _get_core_loop() -> str:
        return """
# ===========================
# 4. Core Loop (Backtest)
# ===========================
open_long_signals = [False] * len(df)
add_long_signals = [False] * len(df)
close_long_signals = [False] * len(df)
open_long_text = [None] * len(df)
add_long_text = [None] * len(df)
open_long_price = [0.0] * len(df)
add_long_price = [0.0] * len(df)
close_long_price = [0.0] * len(df)
close_long_text = [None] * len(df)

open_short_signals = [False] * len(df)
add_short_signals = [False] * len(df)
close_short_signals = [False] * len(df)
open_short_price = [0.0] * len(df)
add_short_price = [0.0] * len(df)
close_short_price = [0.0] * len(df)
close_short_text = [None] * len(df)

position = 0
position_count = 0
avg_entry_price = 0.0
last_add_price = 0.0
highest_price = 0.0

close_arr = df['close'].values
high_arr = df['high'].values
low_arr = df['low'].values
raw_buy_arr = df['raw_buy'].values
raw_sell_arr = df['raw_sell'].values

for i in range(len(df)):
    current_close = close_arr[i]
    current_high = high_arr[i]
    current_low = low_arr[i]

    if position == 1:
        if current_high > highest_price:
            highest_price = current_high
        profit_pct = (highest_price - avg_entry_price) / avg_entry_price
        current_profit_pct = (current_close - avg_entry_price) / avg_entry_price

        if take_profit_activation > 0 and profit_pct >= take_profit_activation:
            drawdown = (highest_price - current_close) / avg_entry_price
            if drawdown >= trailing_callback:
                close_long_signals[i] = True
                close_long_price[i] = current_close
                close_long_text[i] = "Trailing Stop"
                position = 0
                position_count = 0
                continue

        if stop_loss_pct > 0:
            loss_pct = (avg_entry_price - current_low) / avg_entry_price
            if loss_pct >= stop_loss_pct:
                close_long_signals[i] = True
                close_long_price[i] = avg_entry_price * (1 - stop_loss_pct)
                close_long_text[i] = "Stop Loss"
                position = 0
                position_count = 0
                continue

        if raw_sell_arr[i]:
            close_long_signals[i] = True
            close_long_price[i] = current_close
            close_long_text[i] = "Signal Exit"
            position = 0
            position_count = 0
            continue

        if max_pyramiding > 0 and position_count < max_pyramiding + 1 and current_profit_pct > 0:
            if add_threshold_pct > 0:
                target_price = last_add_price * (1 + add_threshold_pct)
                if current_high >= target_price:
                    add_long_signals[i] = True
                    add_long_price[i] = target_price
                    add_long_text[i] = "Add Long"
                    position_count += 1
                    last_add_price = target_price

    elif position == -1:
        if highest_price == 0:
            highest_price = avg_entry_price
        if current_low < highest_price:
            highest_price = current_low
        profit_pct = (avg_entry_price - highest_price) / avg_entry_price
        current_profit_pct = (avg_entry_price - current_close) / avg_entry_price

        if take_profit_activation > 0 and profit_pct >= take_profit_activation:
            drawdown = (current_close - highest_price) / avg_entry_price
            if drawdown >= trailing_callback:
                close_short_signals[i] = True
                close_short_price[i] = current_close
                close_short_text[i] = "Trailing Stop"
                position = 0
                position_count = 0
                continue

        if stop_loss_pct > 0:
            loss_pct = (current_high - avg_entry_price) / avg_entry_price
            if loss_pct >= stop_loss_pct:
                close_short_signals[i] = True
                close_short_price[i] = avg_entry_price * (1 + stop_loss_pct)
                close_short_text[i] = "Stop Loss"
                position = 0
                position_count = 0
                continue

        if raw_buy_arr[i]:
            close_short_signals[i] = True
            close_short_price[i] = current_close
            close_short_text[i] = "Signal Exit"
            position = 0
            position_count = 0
            continue

        if max_pyramiding > 0 and position_count < max_pyramiding + 1 and current_profit_pct > 0:
            if add_threshold_pct > 0:
                target_price = last_add_price * (1 - add_threshold_pct)
                if current_low <= target_price:
                    add_short_signals[i] = True
                    add_short_price[i] = target_price
                    add_short_text[i] = "Add Short"
                    position_count += 1
                    last_add_price = target_price

    else:
        if raw_buy_arr[i]:
            open_long_signals[i] = True
            open_long_price[i] = current_close
            open_long_text[i] = "Open Long"
            position = 1
            position_count = 1
            avg_entry_price = current_close
            last_add_price = current_close
            highest_price = current_close
        elif raw_sell_arr[i]:
            open_short_signals[i] = True
            open_short_price[i] = current_close
            open_short_text[i] = "Open Short"
            position = -1
            position_count = 1
            avg_entry_price = current_close
            last_add_price = current_close
            highest_price = current_close

df['open_long'] = open_long_signals
df['add_long'] = add_long_signals
df['close_long'] = close_long_signals
df['open_long_price'] = [p if s else None for p, s in zip(open_long_price, open_long_signals)]
df['add_long_price'] = [p if s else None for p, s in zip(add_long_price, add_long_signals)]
df['close_long_price'] = [p if s else None for p, s in zip(close_long_price, close_long_signals)]
df['open_long_text'] = open_long_text
df['add_long_text'] = add_long_text
df['close_long_text'] = close_long_text
"""

    # ── Output Section ──────────────────────────────────────────────────────

    def _get_output_section(self, name: str, rules: list[dict[str, Any]]) -> str:
        plots: list[dict[str, Any]] = []
        for rule in rules:
            ind = rule.get("indicator")
            params = rule.get("params", {})
            plots.extend(self._indicator_plots(ind, params))

        plots_py = "[\n"
        for p in plots:
            plots_py += (
                f"    {{'name': '{p['name']}', 'type': '{p['type']}', "
                f"'data': {p['data']}, 'color': '{p['color']}', "
                f"'overlay': {p['overlay']}}},\n"
            )
        plots_py += "]"

        return f"""
# ===========================
# 5. Output
# ===========================
output = {{
    "name": "{name}",
    "plots": {plots_py},
    "signals": [
        {{"name": "Open Long", "type": "buy", "data": df['open_long_price'].tolist(), "color": "#00FF00", "text": "Open Long"}},
        {{"name": "Add Long", "type": "buy", "data": df['add_long_price'].tolist(), "color": "#00DD00", "text": "Add Long"}},
        {{"name": "Close Long", "type": "sell", "data": df['close_long_price'].tolist(), "color": "#FF6600", "text": "Close Long"}},
        {{"name": "Open Short", "type": "sell", "data": df['open_short_price'].tolist(), "color": "#FF0000", "text": "Open Short"}},
        {{"name": "Add Short", "type": "sell", "data": df['add_short_price'].tolist(), "color": "#DD0000", "text": "Add Short"}},
        {{"name": "Close Short", "type": "buy", "data": df['close_short_price'].tolist(), "color": "#00CCFF", "text": "Close Short"}},
    ]
}}
"""

    @staticmethod
    def _indicator_plots(ind: str | None, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Return plot config dicts for a given indicator."""
        plots: list[dict[str, Any]] = []
        if ind == "supertrend":
            plots.append({"name": "SuperTrend Up", "type": "line", "data": "df['st_lower'].tolist()", "color": "#00FF00", "overlay": True})
            plots.append({"name": "SuperTrend Down", "type": "line", "data": "df['st_upper'].tolist()", "color": "#FF0000", "overlay": True})
        elif ind == "ema":
            p = params.get("period", 20)
            plots.append({"name": f"EMA {p}", "type": "line", "data": f"df['ema_{p}'].tolist()", "color": "#FFA500", "overlay": True})
        elif ind == "ma":
            p = params.get("period", 20)
            t = params.get("ma_type", "sma")
            plots.append({"name": f"{t.upper()} {p}", "type": "line", "data": f"df['ma_{t}_{p}'].tolist()", "color": "#FFA500", "overlay": True})
        elif ind == "bollinger":
            p = params.get("period", 20)
            d = params.get("std_dev", 2.0)
            plots.append({"name": "BB Upper", "type": "line", "data": f"df['bb_{p}_{d}_upper'].tolist()", "color": "#0088FE", "overlay": True})
            plots.append({"name": "BB Lower", "type": "line", "data": f"df['bb_{p}_{d}_lower'].tolist()", "color": "#0088FE", "overlay": True})
        elif ind == "macd":
            f = params.get("fast_period", 12)
            s = params.get("slow_period", 26)
            si = params.get("signal_period", 9)
            plots.append({"name": "MACD", "type": "line", "data": f"df['macd_{f}_{s}_{si}_line'].tolist()", "color": "#0088FE", "overlay": False})
            plots.append({"name": "Signal", "type": "line", "data": f"df['macd_{f}_{s}_{si}_signal'].tolist()", "color": "#FF8042", "overlay": False})
        elif ind == "rsi":
            p = params.get("period", 14)
            plots.append({"name": f"RSI {p}", "type": "line", "data": f"df['rsi_{p}'].tolist()", "color": "#8884d8", "overlay": False})
        elif ind == "kdj":
            p = params.get("period", 9)
            si = params.get("signal_period", 3)
            plots.append({"name": "K", "type": "line", "data": f"df['kdj_{p}_{si}_k'].tolist()", "color": "#8884d8", "overlay": False})
            plots.append({"name": "D", "type": "line", "data": f"df['kdj_{p}_{si}_d'].tolist()", "color": "#82ca9d", "overlay": False})
            plots.append({"name": "J", "type": "line", "data": f"df['kdj_{p}_{si}_j'].tolist()", "color": "#ffc658", "overlay": False})
        return plots
