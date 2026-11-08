"""东方财富个股新闻搜索源。

为什么不直接用 akshare 的 `stock_news_em`：
1. 该接口需要 TLS 指纹伪装（curl_cffi impersonate），普通 requests 会被返回空结果；
2. akshare 内部用 pandas 的 `.str.replace(r"\\u3000", ...)`，在 pandas 3.x 的
   pyarrow 字符串后端上会抛 `ArrowInvalid: invalid escape sequence`，
   导致 `stock_news_em` 在新环境直接不可用。

这里直接访问底层接口，只依赖 requests / curl_cffi 与标准库，稳定得多。
"""

from __future__ import annotations

import json
import logging
import re

from stockgraph.domain.news import NewsArticle, NewsBatch
from stockgraph.infrastructure.data_sources.news._common import PoliteSession, env_int
from stockgraph.infrastructure.data_sources.news.base import NewsSource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://search-api-web.eastmoney.com/search/jsonp"
EM_TAG = re.compile(r"</?em>")


class EastMoneyStockNewsSource(NewsSource):
    name = "东方财富个股新闻"

    def __init__(self, stock_codes: list[str] | None = None, session: PoliteSession | None = None) -> None:
        self.stock_codes = stock_codes or []
        self.session = session or PoliteSession()
        self.page_size = env_int("STOCKGRAPH_EM_STOCK_NEWS_PAGE_SIZE", 20)

    # ------------------------------------------------------------------ 抓取

    def fetch(self, limit: int = 50) -> NewsBatch:
        if not self.stock_codes:
            logger.info("未指定股票代码，跳过个股新闻采集")
            return NewsBatch(source=self.name, articles=[])
        pages = max(1, limit // max(1, self.page_size))
        articles: list[NewsArticle] = []
        for code in self.stock_codes:
            try:
                batch = self.fetch_for_stock(code, pages=pages)
            except Exception:  # noqa: BLE001
                logger.warning("个股新闻采集失败: %s", code, exc_info=True)
                continue
            articles.extend(batch.articles)
        return NewsBatch(source=self.name, articles=articles)

    def fetch_for_stock(self, stock_code: str, pages: int = 3) -> NewsBatch:
        articles: list[NewsArticle] = []
        seen: set[str] = set()
        for page in range(1, max(1, pages) + 1):
            items = self._request(stock_code, page)
            if not items:
                break
            for item in items:
                code = str(item.get("code") or "")
                title = _clean(item.get("title") or "")
                if not title or code in seen:
                    continue
                seen.add(code)
                articles.append(
                    NewsArticle(
                        source=self.name,
                        title=title,
                        content=_clean(item.get("content") or ""),
                        summary=_clean(item.get("content") or "")[:200],
                        published_at=str(item.get("date") or ""),
                        url=f"https://finance.eastmoney.com/a/{code}.html" if code else "",
                        metadata={
                            "stock_codes": [stock_code],
                            "media": item.get("mediaName") or "",
                            "em_code": code,
                            "keyword": stock_code,
                        },
                    )
                )
            if len(items) < self.page_size:
                break
        return NewsBatch(source=self.name, articles=articles)

    def _request(self, keyword: str, page: int) -> list[dict]:
        inner = {
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": page,
                    "pageSize": self.page_size,
                    "preTag": "<em>",
                    "postTag": "</em>",
                }
            },
        }
        params = {"cb": "jQuery", "param": json.dumps(inner, ensure_ascii=False), "_": "1"}
        headers = {"referer": f"https://so.eastmoney.com/news/s?keyword={keyword}"}
        text = self._get_text(params, headers)
        if not text:
            return []
        start, end = text.find("("), text.rfind(")")
        if start < 0 or end <= start:
            return []
        try:
            payload = json.loads(text[start + 1 : end])
        except ValueError:
            logger.warning("%s 响应解析失败: %s", self.name, keyword)
            return []
        return (payload.get("result") or {}).get("cmsArticleWebOld") or []

    def _get_text(self, params: dict, headers: dict) -> str:
        """优先用 curl_cffi（需要 TLS 指纹），不可用时退回 requests。"""
        self.session._throttle()
        try:
            from curl_cffi import requests as curl_requests

            response = curl_requests.get(
                SEARCH_URL, params=params, headers=headers, impersonate="chrome", timeout=20
            )
            return response.text
        except ImportError:
            pass
        try:
            response = self.session.session.get(SEARCH_URL, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s 请求失败 %s: %s", self.name, params.get("param", "")[:60], exc)
            return ""


def _clean(text: str) -> str:
    return EM_TAG.sub("", str(text)).replace("\u3000", " ").strip()
