"""
ETF 价格采集器
优先腾讯财经 API，降级东方财富，兼容 GitHub Actions 网络环境
"""
import random
import requests
from typing import Dict, List

from .guba_collector import SECTORS

# 上证 ETF 代码前缀
_SH_PREFIX = {"513100", "518880", "515880", "512480", "513500", "512800", "512690", "510300"}

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


def _build_headers() -> Dict[str, str]:
    ua = random.choice(_USER_AGENTS)
    return {
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }


def _symbol(etf_code: str) -> str:
    """ETF 代码 → 行情符号（如 513100 → sh513100）"""
    prefix = "sh" if etf_code in _SH_PREFIX else "sz"
    return f"{prefix}{etf_code}"


def _fetch_tencent(symbol: str, lmt: int) -> List[Dict]:
    """腾讯财经日K线（对 GitHub Actions 友好）"""
    url = (
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={symbol},day,,,{lmt},qfq"
    )
    resp = requests.get(url, headers=_build_headers(), timeout=15)
    resp.encoding = "utf-8"
    data = resp.json()

    if data.get("code") != 0:
        raise ValueError(f"腾讯API返回code={data.get('code')}: {data.get('msg', '')}")

    stock_data = data.get("data", {}).get(symbol, {})
    klines = stock_data.get("qfqday") or stock_data.get("day", [])

    result = []
    for item in klines:
        if len(item) >= 3:
            result.append({"date": item[0], "close": float(item[2])})
    result.sort(key=lambda x: x["date"])
    return result


def _fetch_eastmoney(etf_code: str, lmt: int) -> List[Dict]:
    """东方财富日K线（本地环境使用，GitHub Actions 可能被拒）"""
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid=1.{etf_code}"
        f"&fields1=f1,f2,f3,f4"
        f"&fields2=f51,f52,f53,f54,f55,f56"
        f"&klt=101&fqt=1&end=20500101&lmt={lmt}"
    )
    headers = _build_headers()
    headers["Referer"] = "https://quote.eastmoney.com/"
    headers["Origin"] = "https://quote.eastmoney.com"

    resp = requests.get(url, headers=headers, timeout=15)
    resp.encoding = "utf-8"
    data = resp.json()

    klines = data.get("data", {}).get("klines", [])
    if not klines:
        return []

    result = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 3:
            result.append({"date": parts[0], "close": float(parts[2])})
    result.sort(key=lambda x: x["date"])
    return result


def fetch_etf_kline(etf_code: str, lmt: int = 60) -> List[Dict]:
    """获取 ETF 历史日K线，自动选择可用数据源

    Args:
        etf_code: ETF 代码（如 "513100"）
        lmt: 获取数据条数，默认 60 条

    Returns:
        [{"date": "2026-08-01", "close": 1.234}, ...] 按日期升序
    """
    sym = _symbol(etf_code)

    # 腾讯优先（GitHub Actions 可访问）
    try:
        return _fetch_tencent(sym, lmt)
    except Exception as e_tx:
        print(f"    腾讯API失败({e_tx})，尝试东方财富...")

    # 降级东方财富
    try:
        return _fetch_eastmoney(etf_code, lmt)
    except Exception as e_em:
        raise RuntimeError(f"腾讯API与东方财富均失败: {e_em}")


def collect_all() -> Dict[str, List[Dict]]:
    """采集所有板块对应 ETF 的历史价格

    Returns:
        {sector_key: [{"date": "2026-08-01", "close": 1.234}, ...]}
    """
    result = {}
    for sector_key, cfg in SECTORS.items():
        etf_code = cfg.get("etf")
        if not etf_code:
            print(f"  [{cfg['name']}] 无 ETF 代码，跳过")
            continue

        try:
            prices = fetch_etf_kline(etf_code)
            result[sector_key] = prices
            print(f"  [{cfg['name']}] ETF {etf_code} 获取 {len(prices)} 条历史价格")
        except Exception as e:
            print(f"  [{cfg['name']}] ETF {etf_code} 价格获取失败: {e}")
            result[sector_key] = []

    return result


if __name__ == "__main__":
    data = collect_all()
    for k, v in data.items():
        print(f"{k}: {len(v)} records, latest: {v[-1] if v else 'N/A'}")
