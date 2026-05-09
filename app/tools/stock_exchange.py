"""
A 股代码交易所识别工具
覆盖主板、科创板、创业板、基金/ETF、B股、北交所等全量场景
"""

from __future__ import annotations

# 上海交易所（sh / secid=1）
_SH_PREFIXES = frozenset({
    # 主板
    "600", "601", "603", "605",
    # 科创板
    "688", "689",
    # 基金/ETF/封闭式基金
    "500", "501", "502", "505", "510", "511", "512", "513", "515", "518", "519",
    "521", "522", "523", "525", "526", "527", "528", "529",
    "560", "561", "563", "564", "565", "568", "569",
    "570", "571", "572", "573", "578", "579",
    "580", "582", "583", "585", "586", "588",
    # B股
    "900",
    # 存托凭证
    "689",
    # 国债/逆回购（部分场景需要）
    "009", "010", "018", "019", "020",
})

# 深圳交易所（sz / secid=0）
_SZ_PREFIXES = frozenset({
    # 主板
    "000", "001",
    # 中小板
    "002", "003",
    # 创业板
    "300", "301",
    # 基金/LOF/ETF
    "150", "159", "160", "161", "162", "163", "164", "165", "166", "167", "168", "169",
    "184",
    # B股
    "200",
    # 配股/转债等
    "080", "031", "038",
    # 国债/逆回购
    "100", "101", "102", "103", "104", "105", "106", "107", "108", "109",
    "111", "112", "115",
})

# 北京交易所（bj）— 注意：东财和腾讯对北交所支持有限
_BJ_PREFIXES = frozenset({
    "430", "830", "870", "889", "88",
})


def get_exchange(symbol: str) -> str:
    """
    根据股票代码判断所属交易所。

    Returns:
        "sh" | "sz" | "bj" | "unknown"
    """
    if not symbol or len(symbol) < 3:
        return "unknown"

    prefix3 = symbol[:3]
    if prefix3 in _SH_PREFIXES:
        return "sh"
    if prefix3 in _SZ_PREFIXES:
        return "sz"

    # 北交所以 88 开头是 4 位前缀
    prefix2 = symbol[:2]
    if prefix2 in ("88", "43", "83", "87"):
        # 进一步确认
        if prefix3 in _BJ_PREFIXES or prefix2 == "88":
            return "bj"

    return "unknown"


def get_eastmoney_secid(symbol: str) -> str:
    """
    东财 API 的 secid 前缀：1=上海，0=深圳
    北交所在东财中通常走上海通道或不被支持
    """
    exchange = get_exchange(symbol)
    if exchange == "sh":
        return "1"
    if exchange == "sz":
        return "0"
    # 北交所 fallback 到上海
    return "1"


def get_tencent_prefix(symbol: str) -> str:
    """
    腾讯财经 API 的前缀：sh=上海，sz=深圳
    北交所在腾讯财经中通常不被支持
    """
    exchange = get_exchange(symbol)
    if exchange == "sz":
        return "sz"
    # sh / bj / unknown 都 fallback 到 sh
    return "sh"
