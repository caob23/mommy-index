"""
ETF 价格采集器
调用东方财富 K 线 API 获取历史日K收盘价
"""
import os
import random
import time
import requests
from typing import Dict, List

from .guba_collector import SECTORS, PROXY

# 模拟移动端/轻量请求头，避免网页导航头被风控拦截
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]


def _should_use_proxy() -> bool:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return False
    if os.environ.get("USE_PROXY") == "false":
        return False
    return True


def _build_headers(referer: str = "https://quote.eastmoney.com/") -> Dict[str, str]:
    """构造轻量 API 请求头，避免 Sec-Fetch-Dest:document 触发风控"""
    ua = random.choice(_USER_AGENTS)
    version = ua.split("Chrome/")[1].split(".")[0]
    return {
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Origin": "https://quote.eastmoney.com",
        "Connection": "keep-alive",
        "sec-ch-ua": f'"Not_A Brand";v="8", "Chromium";v="{version}", "Google Chrome";v="{version}"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }


def fetch_etf_kline(etf_code: str, lmt: int = 60, retries: int = 3) -> List[Dict]:
    """获取 ETF 历史日K线数据

    Args:
        etf_code: ETF 代码（如 "513100"）
        lmt: 获取数据条数，默认 60 条（约 3 个月交易日）
        retries: 重试次数，默认 3 次

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

    proxies = PROXY if _should_use_proxy() else None
    last_error = None

    for attempt in range(retries):
        try:
            headers = _build_headers()
            resp = requests.get(url, headers=headers, proxies=proxies, timeout=15)
            resp.encoding = 'utf-8'
            data = resp.json()

            klines = data.get("data", {}).get("klines", [])
            if not klines:
                return []

            result = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 3:
                    result.append({
                        "date": parts[0],
                        "close": float(parts[2]),
                    })

            result.sort(key=lambda x: x["date"])
            return result

        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                wait = 2 ** attempt + random.uniform(0, 1)
                time.sleep(wait)

    raise last_error


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
