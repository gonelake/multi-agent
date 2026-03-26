"""
search.py — DuckDuckGo 搜索工具封装

提供真实的网络新闻搜索能力，供 ResearcherAgent 使用。
无需 API Key，基于 ddgs 库（duckduckgo-search 的继任包）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from ddgs import DDGS
from config import SearchConfig

_logger = logging.getLogger(__name__)

# 模块级默认配置
_search_cfg = SearchConfig()


class DuckDuckGoSearchClient:
    """
    封装 DuckDuckGo News 搜索，返回真实的最新新闻结果。
    搜索参数默认值来自 SearchConfig，可通过参数覆盖。
    """

    def search(
        self,
        query: str,
        max_results: int = _search_cfg.max_results,
        days: int = _search_cfg.default_days,
    ) -> list[dict]:
        """
        搜索最新新闻，返回标准化结果列表。

        Returns:
            list[dict]，每项包含: title, url, content, published_date
        """
        timelimit = _search_cfg.timelimit(days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results = []
        with DDGS() as ddgs:
            for item in ddgs.news(query, max_results=max_results, timelimit=timelimit):
                published = item.get("date", "")
                # 客户端二次过滤：丢弃超出时间窗口的结果
                if published:
                    try:
                        pub_dt = datetime.fromisoformat(published)
                        if pub_dt < cutoff:
                            continue
                    except ValueError:
                        pass  # 日期格式无法解析时保留
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("body", ""),
                    "published_date": published,
                })
        return results

    def search_multi(
        self,
        queries: list[str],
        max_results_per_query: int = _search_cfg.results_per_query,
        days: int = _search_cfg.default_days,
    ) -> list[dict]:
        """对多个关键词分别搜索，合并去重后返回。"""
        seen_urls: set[str] = set()
        all_results: list[dict] = []

        for q in queries:
            try:
                for r in self.search(q, max_results=max_results_per_query, days=days):
                    if r["url"] not in seen_urls:
                        seen_urls.add(r["url"])
                        all_results.append(r)
            except Exception as e:
                # 单个关键词搜索失败不中断整体，但记录日志便于排查
                _logger.warning("搜索关键词 %r 失败: %s", q, e)
                continue

        return all_results
