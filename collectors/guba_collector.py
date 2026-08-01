"""
东方财富股吧采集器 — 反检测升级版
支持板块: 纳斯达克ETF, 黄金ETF, 通信ETF(CPO), 半导体ETF
"""
import re
import html as html_mod
import requests
import time
from datetime import datetime
from typing import List, Dict, Optional

from .anti_detection import get_anti_detection

SECTORS = {
    "nasdaq":     {"name": "纳斯达克", "code": "of159941", "etf": "513100"},
    "gold":       {"name": "黄金",     "code": "of518880", "etf": "518880"},
    "cpo":        {"name": "CPO通信",  "code": "of515880", "etf": "515880"},
    "semiconductor": {"name": "半导体", "code": "of512480", "etf": "512480"},
    "sp500":      {"name": "标普500",  "code": "of513500", "etf": "513500"},
    "bank":       {"name": "银行",     "code": "of512800", "etf": "512800"},
    "baijiu":     {"name": "白酒",     "code": "of512690", "etf": "512690"},
    "hs300":      {"name": "沪深300",  "code": "of510300", "etf": "510300"},
}

PROXY = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}

_ad = get_anti_detection()


def _should_use_proxy() -> bool:
    """判断是否使用本地代理：GitHub Actions 环境不走代理"""
    import os
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return False
    if os.environ.get("USE_PROXY") == "false":
        return False
    return True


def fetch_board_page(code: str, page: int = 1) -> str:
    """获取股吧指定页HTML — 使用反检测请求头
    第1页: list,{code}.html
    第2页起: list,{code}_{page}.html
    """
    if page <= 1:
        url = f"https://guba.eastmoney.com/list,{code}.html"
    else:
        url = f"https://guba.eastmoney.com/list,{code}_{page}.html"
    headers = _ad.get_common_headers(referer="https://guba.eastmoney.com")
    proxies = PROXY if _should_use_proxy() else None
    resp = requests.get(url, headers=headers, proxies=proxies, timeout=15)
    resp.encoding = 'utf-8'
    return resp.text


def fetch_board(code: str) -> str:
    """获取股吧首页HTML（兼容旧接口）"""
    return fetch_board_page(code, page=1)


def parse_posts(html_content: str) -> List[Dict]:
    """解析帖子列表"""
    title_pattern = re.compile(
        r'<a[^>]*href="(/news,[^"]*)"[^>]*title="([^"]*)"[^>]*>',
        re.DOTALL
    )
    # 匹配 <cite> 和 <span>（股吧可能切换标签）
    tag = r'(?:cite|span)'
    read_pattern = re.compile(rf'<{tag}[^>]*class="[^"]*l1[^"]*"[^>]*>(.*?)</{tag}>', re.DOTALL)
    reply_pattern = re.compile(rf'<{tag}[^>]*class="[^"]*l2[^"]*"[^>]*>(.*?)</{tag}>', re.DOTALL)
    author_pattern = re.compile(rf'<{tag}[^>]*class="[^"]*l4[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', re.DOTALL)
    date_pattern = re.compile(rf'<{tag}[^>]*class="[^"]*l5[^"]*"[^>]*>(.*?)</{tag}>', re.DOTALL)

    titles = title_pattern.findall(html_content)
    reads = read_pattern.findall(html_content)
    replies = reply_pattern.findall(html_content)
    authors = author_pattern.findall(html_content)
    dates = date_pattern.findall(html_content)

    # 跳过表头行（第一行是 "阅读/评论/标题/作者/最后更新"）
    reads = reads[1:]
    replies = replies[1:]
    authors = authors[1:]
    dates = dates[1:]

    posts = []
    for i, (url, title) in enumerate(titles):
        title = html_mod.unescape(title.strip())
        if not title or title == '点击开始搜索':
            continue
        author = authors[i].strip() if i < len(authors) else "未知"
        # 清理 HTML 标签（如 <font>xxx</font>）
        author = re.sub(r'<[^>]+>', '', author)
        posts.append({
            "id": f"guba_{url.split(',')[-1].replace('.html','')}",
            "title": title,
            "url": f"https://guba.eastmoney.com{url}",
            "platform": "guba",
            "author": authors[i].strip() if i < len(authors) else "未知",
            "reads": reads[i].strip() if i < len(reads) else "0",
            "replies": replies[i].strip() if i < len(replies) else "0",
            "date": dates[i].strip() if i < len(dates) else "未知",
            "collected_at": datetime.now().isoformat(),
        })
    return posts


def collect_all(pages: int = 5) -> Dict[str, List[Dict]]:
    """采集所有板块 — 支持翻页 + 人类延迟防触发风控
    
    Args:
        pages: 每个板块翻页数，默认 5 页（约覆盖一个月的历史帖子）
    """
    result = {}
    for sector_key, cfg in SECTORS.items():
        all_posts = []
        for page in range(1, pages + 1):
            try:
                html = fetch_board_page(cfg["code"], page)
                posts = parse_posts(html)
                if not posts:
                    # 空页说明已到末尾，停止翻页
                    print(f"  [{cfg['name']}] 第{page}页为空，停止翻页")
                    break
                all_posts.extend(posts)
                print(f"  [{cfg['name']}] 第{page}页 采集到 {len(posts)} 条帖子")
                # 页之间加延迟
                if page < pages:
                    _ad.sleep_like_human("scroll")
            except Exception as e:
                print(f"  [{cfg['name']}] 第{page}页 采集失败: {e}")
                # 单页失败不中断，继续翻下一页
        result[sector_key] = all_posts
        print(f"  [{cfg['name']}] 翻页{min(page, pages)}页，共采集 {len(all_posts)} 条帖子")
        # 板块之间加延迟
        _ad.sleep_like_human("scroll")
    return result


if __name__ == "__main__":
    data = collect_all()
    for k, v in data.items():
        print(f"{k}: {len(v)} posts")
