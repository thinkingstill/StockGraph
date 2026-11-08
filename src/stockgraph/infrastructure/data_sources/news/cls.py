"""财联社电报数据源。

接口：`https://www.cls.cn/v1/roll/get_roll_list`
- 必须带 `sign`：把参数按 key 排序拼成 query，先 sha1 再 md5
- `last_time` 作为翻页游标（上一页最后一条的 ctime）
- 返回的 `stock_list` 里有财联社标注的关联个股，可直接作为实体关联依据
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from stockgraph.domain.news import NewsArticle, NewsBatch
from stockgraph.infrastructure.data_sources.news._common import PoliteSession, env_int
from stockgraph.infrastructure.data_sources.news.base import NewsSource

logger = logging.getLogger(__name__)

ROLL_URL = "https://www.cls.cn/v1/roll/get_roll_list"
REFERER = "https://www.cls.cn/telegraph"


def build_sign(params: dict[str, str]) -> str:
    """财联社签名：md5(sha1(sorted_query))。"""
    query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.md5(hashlib.sha1(query.encode("utf-8")).hexdigest().encode("utf-8")).hexdigest()


class CLSNewsSource(NewsSource):
    name = "财联社电报"

    def __init__(self, page_size: int | None = None, session: PoliteSession | None = None) -> None:
        self.page_size = page_size or env_int("STOCKGRAPH_CLS_PAGE_SIZE", 30)
        self.session = session or PoliteSession()
        # 游标持久化在实例上，连续调用 fetch() 会持续向前翻页，便于大批量回补
        self.cursor = ""

    def set_cursor(self, ctime: str) -> None:
        self.cursor = str(ctime or "")

    def fetch(self, limit: int = 50, *, reset: bool = False) -> NewsBatch:
        articles: list[NewsArticle] = []
        seen: set[str] = set()
        last_time = "" if reset else self.cursor
        pages = 0
        page_size = max(1, min(self.page_size, limit))
        max_pages = max(1, (limit // page_size) + 2)

        while len(articles) < limit and pages < max_pages:
            pages += 1
            params = {
                "app": "CailianpressWeb",
                "category": "",
                "last_time": last_time,
                "os": "web",
                "refresh_type": "1",
                "rn": str(min(page_size, max(1, limit - len(articles)))),
                "sv": "8.4.6",
            }
            params["sign"] = build_sign(params)
            try:
                payload = self.session.get_json(ROLL_URL, params=params, referer=REFERER)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s 请求失败: %s", self.name, exc)
                break

            if payload.get("errno") not in (0, None):
                logger.warning("%s 返回错误: %s", self.name, payload.get("msg"))
                break

            items = (payload.get("data") or {}).get("roll_data") or []
            if not items:
                break

            for item in items:
                article_id = str(item.get("id") or "")
                title = (item.get("title") or "").strip()
                brief = (item.get("brief") or "").strip()
                if not title and not brief:
                    continue
                if article_id in seen:
                    continue
                seen.add(article_id)
                stocks = _extract_stock_codes(item.get("stock_list"))
                ctime = item.get("ctime")
                published_at = (
                    datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(ctime, (int, float)) or (isinstance(ctime, str) and ctime.isdigit())
                    else ""
                )
                articles.append(
                    NewsArticle(
                        source=self.name,
                        title=title or brief[:60],
                        content=item.get("content") or brief,
                        summary=brief,
                        published_at=published_at,
                        url=item.get("shareurl") or f"https://www.cls.cn/detail/{article_id}",
                        metadata={
                            "cls_id": article_id,
                            "level": item.get("level"),
                            "subjects": [s.get("subject_name") for s in (item.get("subjects") or [])],
                            "stock_codes": stocks,
                        },
                    )
                )
                if len(articles) >= limit:
                    break
                if ctime:
                    last_time = str(ctime)

            if len(items) < page_size:
                break

        self.cursor = last_time
        logger.info("%s 采集到 %d 条电报（游标 %s）", self.name, len(articles), self.cursor)
        return NewsBatch(source=self.name, articles=articles)


def _extract_stock_codes(raw: list | None) -> list[str]:
    codes: list[str] = []
    for item in raw or []:
        if isinstance(item, dict):
            candidate = (
                item.get("StockID")
                or item.get("secu_code")
                or item.get("code")
                or item.get("stock_id")
                or ""
            )
        else:
            candidate = item
        code = str(candidate).split(".")[-1].strip()
        if len(code) == 6 and code.isdigit() and code not in codes:
            codes.append(code)
    return codes
