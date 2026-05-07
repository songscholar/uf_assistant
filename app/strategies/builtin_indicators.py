"""
UF Stock Assistant — 内置指标示例
移植自 QuantDinger builtin_indicators.py

4 个示例指标，展示 IndicatorStrategy 的标准写法：
- 使用 # @strategy 注解声明风控配置
- 使用 # @param 声明可调参数
- 输出 df['buy'] / df['sell'] 布尔信号列
- 输出 output 字典用于图表渲染（plots + signals）
"""

from __future__ import annotations

from typing import Any


BUILTIN_INDICATORS: list[dict[str, str]] = [
    {
        "name": "[示例] RSI 边缘触发",
        "description": "经典 RSI 超卖反弹买入、超买回落卖出；信号为「当根刚触发」避免重复开仓。适合熟悉回测面板与 @strategy。",
        "code": r'''my_indicator_name = "[示例] RSI 边缘触发"
my_indicator_description = "RSI 超卖/超买 + 边缘触发；可在回测面板调杠杆、周期与标的。"

# @strategy stopLossPct 0.03
# @strategy takeProfitPct 0.06
# @strategy entryPct 1
# @strategy tradeDirection long

df = df.copy()
rsi_len = 14
delta = df['close'].diff()
gain = delta.clip(lower=0)
loss = (-delta).clip(lower=0)
avg_gain = gain.ewm(alpha=1 / rsi_len, adjust=False).mean()
avg_loss = loss.ewm(alpha=1 / rsi_len, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, np.nan)
rsi = 100 - (100 / (1 + rs))
rsi = rsi.fillna(50)

raw_buy = rsi < 30
raw_sell = rsi > 70
buy = raw_buy.fillna(False) & (~raw_buy.shift(1).fillna(False))
sell = raw_sell.fillna(False) & (~raw_sell.shift(1).fillna(False))
df['buy'] = buy.astype(bool)
df['sell'] = sell.astype(bool)

buy_marks = [df['low'].iloc[i] * 0.995 if bool(buy.iloc[i]) else None for i in range(len(df))]
sell_marks = [df['high'].iloc[i] * 1.005 if bool(sell.iloc[i]) else None for i in range(len(df))]

output = {
    'name': my_indicator_name,
    'plots': [
        {'name': 'RSI(14)', 'data': rsi.tolist(), 'color': '#faad14', 'overlay': False}
    ],
    'signals': [
        {'type': 'buy', 'text': 'B', 'data': buy_marks, 'color': '#00E676'},
        {'type': 'sell', 'text': 'S', 'data': sell_marks, 'color': '#FF5252'}
    ]
}
''',
    },
    {
        "name": "[示例] 双均线金叉死叉",
        "description": "快线上穿慢线做多，下穿做空；参数可直接在代码里改 fast/slow 周期。",
        "code": r'''my_indicator_name = "[示例] 双均线金叉死叉"
my_indicator_description = "快慢均线交叉；边缘触发。杠杆、手续费等在回测面板设置。"

# @strategy stopLossPct 0.025
# @strategy takeProfitPct 0.05
# @strategy entryPct 1
# @strategy tradeDirection both

df = df.copy()
fast_n = 12
slow_n = 26
ma_f = df['close'].rolling(fast_n, min_periods=1).mean()
ma_s = df['close'].rolling(slow_n, min_periods=1).mean()

golden = (ma_f > ma_s) & (ma_f.shift(1) <= ma_s.shift(1))
death = (ma_f < ma_s) & (ma_f.shift(1) >= ma_s.shift(1))
df['buy'] = golden.fillna(False).astype(bool)
df['sell'] = death.fillna(False).astype(bool)

buy_marks = [df['low'].iloc[i] * 0.995 if bool(df['buy'].iloc[i]) else None for i in range(len(df))]
sell_marks = [df['high'].iloc[i] * 1.005 if bool(df['sell'].iloc[i]) else None for i in range(len(df))]

output = {
    'name': my_indicator_name,
    'plots': [
        {'name': f'MA({fast_n})', 'data': ma_f.tolist(), 'color': '#1890ff', 'overlay': True},
        {'name': f'MA({slow_n})', 'data': ma_s.tolist(), 'color': '#ff7a45', 'overlay': True}
    ],
    'signals': [
        {'type': 'buy', 'text': 'B', 'data': buy_marks, 'color': '#00E676'},
        {'type': 'sell', 'text': 'S', 'data': sell_marks, 'color': '#FF5252'}
    ]
}
''',
    },
    {
        "name": "[示例] MACD 柱穿零轴",
        "description": "MACD 柱状线由负转正试多，由正转负试空；适合观察动量切换。",
        "code": r'''my_indicator_name = "[示例] MACD 柱穿零轴"
my_indicator_description = "DIF/DEA/柱；柱线穿越零轴边缘触发。可与 1H/4H 加密合约回测配合。"

# @strategy stopLossPct 0.03
# @strategy takeProfitPct 0.08
# @strategy entryPct 0.5
# @strategy tradeDirection both

df = df.copy()
exp12 = df['close'].ewm(span=12, adjust=False).mean()
exp26 = df['close'].ewm(span=26, adjust=False).mean()
dif = exp12 - exp26
dea = dif.ewm(span=9, adjust=False).mean()
hist = dif - dea

raw_buy = (hist > 0) & (hist.shift(1) <= 0)
raw_sell = (hist < 0) & (hist.shift(1) >= 0)
df['buy'] = raw_buy.fillna(False).astype(bool)
df['sell'] = raw_sell.fillna(False).astype(bool)

buy_marks = [df['low'].iloc[i] * 0.995 if bool(df['buy'].iloc[i]) else None for i in range(len(df))]
sell_marks = [df['high'].iloc[i] * 1.005 if bool(df['sell'].iloc[i]) else None for i in range(len(df))]

output = {
    'name': my_indicator_name,
    'plots': [
        {'name': 'MACD DIF', 'data': dif.tolist(), 'color': '#1890ff', 'overlay': False},
        {'name': 'MACD DEA', 'data': dea.tolist(), 'color': '#ff7a45', 'overlay': False},
        {'name': 'MACD Hist', 'data': hist.tolist(), 'color': '#888888', 'overlay': False}
    ],
    'signals': [
        {'type': 'buy', 'text': 'B', 'data': buy_marks, 'color': '#00E676'},
        {'type': 'sell', 'text': 'S', 'data': sell_marks, 'color': '#FF5252'}
    ]
}
''',
    },
    {
        "name": "[示例] 布林带触及",
        "description": "收盘价跌破下轨产生买入信号，突破上轨产生卖出信号（边缘触发）。",
        "code": r'''my_indicator_name = "[示例] 布林带触及"
my_indicator_description = "简单布林带反转思路示例；实盘请结合趋势过滤与风控。"

# @strategy stopLossPct 0.02
# @strategy takeProfitPct 0.04
# @strategy entryPct 0.3
# @strategy tradeDirection long

df = df.copy()
period = 20
mult = 2.0
mid = df['close'].rolling(period, min_periods=1).mean()
std = df['close'].rolling(period, min_periods=1).std()
upper = mid + mult * std
lower = mid - mult * std

raw_buy = df['close'] < lower
raw_sell = df['close'] > upper
buy = raw_buy.fillna(False) & (~raw_buy.shift(1).fillna(False))
sell = raw_sell.fillna(False) & (~raw_sell.shift(1).fillna(False))
df['buy'] = buy.astype(bool)
df['sell'] = sell.astype(bool)

buy_marks = [df['low'].iloc[i] * 0.995 if bool(buy.iloc[i]) else None for i in range(len(df))]
sell_marks = [df['high'].iloc[i] * 1.005 if bool(sell.iloc[i]) else None for i in range(len(df))]

output = {
    'name': my_indicator_name,
    'plots': [
        {'name': 'BOLL 上', 'data': upper.tolist(), 'color': '#69c0ff', 'overlay': True},
        {'name': 'BOLL 中', 'data': mid.tolist(), 'color': '#d9d9d9', 'overlay': True},
        {'name': 'BOLL 下', 'data': lower.tolist(), 'color': '#69c0ff', 'overlay': True}
    ],
    'signals': [
        {'type': 'buy', 'text': 'B', 'data': buy_marks, 'color': '#00E676'},
        {'type': 'sell', 'text': 'S', 'data': sell_marks, 'color': '#FF5252'}
    ]
}
''',
    },
]


def get_builtin_indicator_by_name(name: str) -> dict[str, str] | None:
    """按名称获取内置指标"""
    for indicator in BUILTIN_INDICATORS:
        if indicator["name"] == name:
            return indicator
    return None


def list_builtin_indicators() -> list[dict[str, Any]]:
    """列出所有内置指标（不含代码，仅元数据）"""
    return [
        {
            "name": ind["name"],
            "description": ind["description"],
            "is_builtin": True,
        }
        for ind in BUILTIN_INDICATORS
    ]
