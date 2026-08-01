"""
ETF 价格采集器
调用东方财富 K 线 API 获取历史日K收盘价
"""
import requests
from typing import Dict, List

from .anti_detection import get_anti_detection
from .guba_collector import SECTORS, PROXY

_ad = get_anti_detection()


def _should_use_proxy() -> bool:
    import os
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return False
    if os.environ.get("USE_PROXY") == "false":
        return False
    return True


def fetch_etf_kline(etf_code: str, lmt: int = 60) -> List[Dict]:
    """获取 ETF 历史日K线数据

    Args:
        etf_code: ETF 代码（如 "513100"）
        lmt: 获取数据条数，默认 60 条（约 3 个月交易日）

    Returns:
        [{"date": "2026-08-01", "close": 1.234}, ...] 按日期升序
    """
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid=1.{etf_code}"
        f"&fields1=f1,f2,f3,f4"
        f"&fields2=f51,f52,f53,f54,f55,f56"
        f"&klt=101"
        f"&fqt=1"
        f"&end=20500101"
        f"&lmt={lmt}"
    )

    headers = _ad.get_common_headers(referer="https://quote.eastmoney.com")
    proxies = PROXY if _should_use_proxy() else None

    resp = requests.get(url, headers=headers, proxies=proxies, timeout=15)
    resp.encoding = 'utf-8'
    data = resp.json()

    klines = data.get("data", {}).get("klines", [])
    if not klines:
        return []

    result = []
    for line in klines:
        # 格式: 日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
        parts = line.split(",")
        if len(parts) >= 3:
            result.append({
                "date": parts[0],
                "close": float(parts[2]),
            })

    result.sort(key=lambda x: x["date"])
    return result


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
