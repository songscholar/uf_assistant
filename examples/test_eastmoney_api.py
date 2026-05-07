"""
东方财富直连 API 调试脚本
测试实时行情、龙虎榜、A股涨跌幅统计
"""

import json
import time
import urllib.request
import urllib.parse


def fetch_json(url: str, timeout: float = 10, retries: int = 2) -> dict:
    """通用 JSON 请求，带重试"""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "keep-alive",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
            # 东财部分接口返回 JSONP 格式 callback({...})
            if text.startswith("jQuery") or text.startswith("callback"):
                text = text[text.index("(") + 1 : text.rindex(")")]
            return json.loads(text)
        except Exception:
            if attempt < retries:
                time.sleep(1)
            else:
                raise


# ============================================================
# 1. 单股实时行情 — 600570 恒生电子
# ============================================================
def test_stock_realtime(symbol: str = "600570"):
    """获取单股实时行情"""
    # secid: 沪市 1.代码, 深市 0.代码
    prefix = "1" if symbol.startswith("6") else "0"
    fields = ",".join([
        "f43",   # 最新价
        "f44",   # 最高
        "f45",   # 最低
        "f46",   # 今开
        "f47",   # 成交量（手）
        "f48",   # 成交额
        "f50",   # 量比
        "f51",   # 涨停价
        "f52",   # 跌停价
        "f55",   # 收益（每股）
        "f57",   # 代码
        "f58",   # 名称
        "f60",   # 昨收
        "f116",  # 总市值
        "f117",  # 流通市值
        "f162",  # 市盈率(动)
        "f167",  # 市净率
        "f170",  # 涨跌幅
        "f171",  # 振幅
        "f168",  # 换手率
    ])
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid={prefix}.{symbol}&fields={fields}&_={int(time.time() * 1000)}"
    )

    t0 = time.time()
    data = fetch_json(url)
    elapsed = time.time() - t0

    print("=" * 60)
    print(f"1. 单股实时行情 — {symbol}")
    print(f"   耗时: {elapsed * 1000:.0f}ms")
    print("=" * 60)

    if data.get("data"):
        d = data["data"]
        name = d.get("f58", "")
        price = d.get("f43", 0)
        if isinstance(price, (int, float)):
            price = price / 100  # 东财返回的是分
        change_pct = d.get("f170", 0)
        if isinstance(change_pct, (int, float)):
            change_pct = change_pct / 100

        print(f"   名称: {name}")
        print(f"   代码: {d.get('f57', '')}")
        print(f"   最新价: {price}")
        print(f"   涨跌幅: {change_pct}%")
        print(f"   今开: {d.get('f46', 0) / 100 if d.get('f46') else '-'}")
        print(f"   最高: {d.get('f44', 0) / 100 if d.get('f44') else '-'}")
        print(f"   最低: {d.get('f45', 0) / 100 if d.get('f45') else '-'}")
        print(f"   昨收: {d.get('f60', 0) / 100 if d.get('f60') else '-'}")
        print(f"   成交量: {d.get('f47', 0)} 手")
        vol = d.get("f48", 0)
        if isinstance(vol, (int, float)) and vol > 0:
            print(f"   成交额: {vol / 100000000:.2f} 亿")
        print(f"   市盈率(动): {d.get('f162', 0) / 100 if d.get('f162') else '-'}")
        print(f"   市净率: {d.get('f167', 0) / 100 if d.get('f167') else '-'}")
        total_cap = d.get("f116", 0)
        if isinstance(total_cap, (int, float)) and total_cap > 0:
            print(f"   总市值: {total_cap / 100000000:.2f} 亿")
        float_cap = d.get("f117", 0)
        if isinstance(float_cap, (int, float)) and float_cap > 0:
            print(f"   流通市值: {float_cap / 100000000:.2f} 亿")
        print(f"   振幅: {d.get('f171', 0) / 100 if d.get('f171') else '-'}%")
        print(f"   换手率: {d.get('f168', 0) / 100 if d.get('f168') else '-'}%")
    else:
        print("   无数据")
    print()


# ============================================================
# 2. A股涨跌统计（涨跌家数、涨停跌停）
# ============================================================
def test_market_overview():
    """获取A股整体涨跌统计"""
    # 东财涨跌分布统计接口
    url = (
        "https://push2ex.eastmoney.com/getTopicZDFenBu"
        "?ut=7eea3edcaed734bea9cb3a85377d3d86"
        "&dession=129.86.159.159"
        "&sort=fbt:asc"
        "&_=1"
    )

    t0 = time.time()
    try:
        data = fetch_json(url)
        elapsed = time.time() - t0

        print("=" * 60)
        print("2. A股涨跌统计")
        print(f"   耗时: {elapsed * 1000:.0f}ms")
        print("=" * 60)

        # 尝试解析
        if data.get("data"):
            print(f"   数据: {json.dumps(data['data'], ensure_ascii=False, indent=2)[:500]}")
        else:
            print(f"   原始响应: {json.dumps(data, ensure_ascii=False)[:300]}")
    except Exception as e:
        elapsed = time.time() - t0
        print("=" * 60)
        print("2. A股涨跌统计")
        print(f"   耗时: {elapsed * 1000:.0f}ms")
        print("=" * 60)
        print(f"   接口异常: {e}")

    # 备用方案：用板块涨跌排行间接统计
    print()
    print("   --- 备用：涨跌停统计 (东财人气榜接口) ---")
    url2 = (
        "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
        "?appId=appId01&globalId=786e4c21-70dc-435a-93bb-38"
        "&marketType=&pageNo=1&pageSize=1"
    )
    try:
        t0 = time.time()
        data2 = fetch_json(url2, timeout=5)
        elapsed2 = time.time() - t0
        print(f"   耗时: {elapsed2 * 1000:.0f}ms")
        total = data2.get("total", 0)
        print(f"   人气榜总数: {total}")
    except Exception as e:
        print(f"   异常: {e}")
    print()


# ============================================================
# 3. 龙虎榜
# ============================================================
def test_longhu_bang():
    """获取龙虎榜数据"""
    today = time.strftime("%Y-%m-%d")
    url = (
        f"https://datacenter-web.eastmoney.com/api/data/v1/get"
        f"?sortColumns=TURNOVERRATE&sortTypes=-1&pageSize=20&pageNumber=1"
        f"&reportName=RPT_DAILYBILLBOARD_DETAILSNEW"
        f"&columns=ALL&filter=(TRADE_DATE%3E%3D%27{today}%27)"
        f"&source=WEB&client=WEB&_={int(time.time() * 1000)}"
    )

    t0 = time.time()
    data = fetch_json(url, timeout=10)
    elapsed = time.time() - t0

    print("=" * 60)
    print(f"3. 龙虎榜 ({today})")
    print(f"   耗时: {elapsed * 1000:.0f}ms")
    print("=" * 60)

    result = data.get("result", {})
    records = result.get("data", [])
    total = result.get("count", 0)

    print(f"   总条数: {total}")

    if records:
        for i, r in enumerate(records[:10]):
            code = r.get("SECURITY_CODE", "")
            name = r.get("SECURITY_NAME_ABBR", "")
            change = r.get("CHANGE_RATE", 0)
            reason = r.get("EXPLANATION", "")
            close = r.get("CLOSE_PRICE", 0)
            print(f"   [{i+1}] {code} {name}  涨跌幅:{change}%  收盘:{close}  原因:{reason}")
        if len(records) > 10:
            print(f"   ... 还有 {len(records) - 10} 条")
    else:
        print("   今日暂无龙虎榜数据（可能非交易日或盘后才更新）")
    print()


# ============================================================
# 4. 大盘指数
# ============================================================
def test_index_quotes():
    """获取主要指数实时行情"""
    indices = [
        ("1.000001", "上证指数"),
        ("0.399001", "深证成指"),
        ("0.399006", "创业板指"),
        ("1.000688", "科创50"),
    ]

    secids = ",".join(i[0] for i in indices)
    fields = "f2,f3,f4,f12,f14"
    url = (
        f"https://push2.eastmoney.com/api/qt/ulist.np/get"
        f"?fltt=2&fields={fields}&secids={secids}"
        f"&_={int(time.time() * 1000)}"
    )

    t0 = time.time()
    data = fetch_json(url)
    elapsed = time.time() - t0

    print("=" * 60)
    print("4. 大盘指数")
    print(f"   耗时: {elapsed * 1000:.0f}ms")
    print("=" * 60)

    items = data.get("data", {}).get("diff", [])
    if items:
        for item in items:
            name = item.get("f14", "")
            price = item.get("f2", 0)
            change_pct = item.get("f3", 0)
            change = item.get("f4", 0)
            sign = "+" if change_pct >= 0 else ""
            print(f"   {name}: {price}  {sign}{change_pct}%  ({sign}{change})")
    else:
        print("   无数据")
    print()


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("东方财富直连 API 测试")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    for fn in [lambda: test_stock_realtime("600570"), test_index_quotes, test_market_overview, test_longhu_bang]:
        try:
            fn()
        except Exception as e:
            print(f"   [ERROR] {e}")
            print()
        time.sleep(1)

    print("测试完成。")
