"""东方财富 7×24 快讯数据源。

接口：`https://np-weblist.eastmoney.com/comm/web/getFastNewsList`
- 无需登录，返回 `fastNewsList`，字段含 title / summary / showTime / code / stockList
- 通过 `sortEnd` 游标向前翻页，天然适合增量补齐历史快讯
"""

from __future__ import annotations

import logging
from datetime import datetime

from stockgraph.domain.news import NewsArticle, NewsBatch
from stockgraph.infrastructure.data_sources.news._common import (
    PoliteSession,
    env_int,
    normalize_em_stock_list,
)
from stockgraph.infrastructure.data_sources.news.base import NewsSource

logger = logging.getLogger(__name__)

FAST_NEWS_URL = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"


class EastMoneyNewsSource(NewsSource):
    name = "东方财富快讯"

    def __init__(self, page_size: int | None = None, session: PoliteSession | None = None) -> None:
        self.page_size = page_size or env_int("STOCKGRAPH_EM_NEWS_PAGE_SIZE", 50)
        self.session = session or PoliteSession()
        # sortEnd 游标，连续 fetch 会持续向前翻页，便于大批量回补
        self.cursor = ""

    def set_cursor(self, cursor: str) -> None:
        self.cursor = str(cursor or "")

    def fetch(self, limit: int = 50, *, reset: bool = False) -> NewsBatch:
        articles: list[NewsArticle] = []
        cursor = "" if reset else self.cursor
        seen: set[str] = set()
        pages = 0
        page_size = max(1, min(self.page_size, limit))
        max_pages = max(1, (limit // page_size) + 2)

        while len(articles) < limit and pages < max_pages:
            pages += 1
            params = {
                "client": "web",
                "biz": "web_724",
                "fastColumn": "102",
                "sortEnd": cursor,
                "pageSize": str(min(page_size, max(1, limit - len(articles)))),
                "req_trace": str(int(datetime.now().timestamp() * 1000)),
            }
            try:
                payload = self.session.get_json(FAST_NEWS_URL, params=params)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s 请求失败: %s", self.name, exc)
                break

            data = payload.get("data") or {}
            items = data.get("fastNewsList") or []
            if not items:
                break

            for item in items:
                code = str(item.get("code") or "")
                title = (item.get("title") or "").strip()
                if not title or code in seen:
                    continue
                seen.add(code)
                stocks = normalize_em_stock_list(item.get("stockList"))
                articles.append(
                    NewsArticle(
                        source=self.name,
                        title=title,
                        content=(item.get("summary") or "").strip(),
                        published_at=(item.get("showTime") or "").strip(),
                        url=f"https://finance.eastmoney.com/a/{code}.html" if code else "",
                        metadata={
                            "em_code": code,
                            "channel": "7x24",
                            "stock_codes": [s["stock_code"] for s in stocks],
                        },
                    )
                )
                if len(articles) >= limit:
                    break

            next_cursor = str(data.get("sortEnd") or "")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        self.cursor = cursor
        logger.info("%s 采集到 %d 条快讯（游标 %s）", self.name, len(articles), self.cursor)
        return NewsBatch(source=self.name, articles=articles)
