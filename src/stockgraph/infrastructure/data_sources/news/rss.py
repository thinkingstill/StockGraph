"""通用 RSS / Atom 新闻源。

不引入 feedparser，用标准库 xml.etree 解析，兼容 RSS 2.0 与 Atom 1.0。
订阅地址通过环境变量配置，默认给几个稳定的财经资讯源：

    export STOCKGRAPH_RSS_FEEDS="https://example.com/rss,https://example.org/atom.xml"
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from stockgraph.domain.news import NewsArticle, NewsBatch
from stockgraph.infrastructure.data_sources.news._common import PoliteSession, env_int
from stockgraph.infrastructure.data_sources.news.base import NewsSource

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = (
    "https://rsshub.app/cls/telegraph",
    "https://www.chinanews.com.cn/rss/finance.xml",
)

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


class RSSNewsSource(NewsSource):
    name = "RSS"

    def __init__(self, feeds: list[str] | None = None, session: PoliteSession | None = None) -> None:
        raw = os.environ.get("STOCKGRAPH_RSS_FEEDS", "")
        configured = [item.strip() for item in raw.split(",") if item.strip()]
        self.feeds = feeds or configured or list(DEFAULT_FEEDS)
        self.session = session or PoliteSession()
        self.timeout_seconds = env_int("STOCKGRAPH_RSS_TIMEOUT", 20)

    def fetch(self, limit: int = 50) -> NewsBatch:
        articles: list[NewsArticle] = []
        for feed in self.feeds:
            if len(articles) >= limit:
                break
            try:
                text = self.session.get_text(feed)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s 订阅抓取失败 %s: %s", self.name, feed, exc)
                continue
            try:
                items = parse_feed(text)
            except ET.ParseError as exc:
                logger.warning("%s 解析失败 %s: %s", self.name, feed, exc)
                continue
            for item in items:
                if len(articles) >= limit:
                    break
                item.metadata.setdefault("feed", feed)
                articles.append(item)

        logger.info("%s 采集到 %d 条", self.name, len(articles))
        return NewsBatch(source=self.name, articles=articles)


def parse_feed(text: str) -> list[NewsArticle]:
    root = ET.fromstring(text)
    articles: list[NewsArticle] = []

    # RSS 2.0
    for item in root.iter("item"):
        title = _text(item, "title")
        description = _text(item, "description")
        articles.append(
            NewsArticle(
                source="RSS",
                title=title or description[:60],
                content=description,
                summary=description[:200],
                published_at=_normalize_date(_text(item, "pubDate")),
                url=_text(item, "link"),
                metadata={"feed": _text(item, "guid")},
            )
        )

    # Atom 1.0
    if not articles:
        for entry in root.iter(f"{{{NS['atom']}}}entry"):
            title = _text(entry, "atom:title")
            summary = _text(entry, "atom:summary") or _text(entry, "atom:content")
            link = ""
            for node in entry.findall(f"{{{NS['atom']}}}link"):
                if node.get("rel") in (None, "alternate"):
                    link = node.get("href") or ""
                    break
            articles.append(
                NewsArticle(
                    source="RSS",
                    title=title or summary[:60],
                    content=summary,
                    summary=summary[:200],
                    published_at=_normalize_date(
                        _text(entry, "atom:updated") or _text(entry, "atom:published")
                    ),
                    url=link,
                )
            )

    return [article for article in articles if article.title]


def _text(node: ET.Element, path: str) -> str:
    if path.startswith("atom:"):
        child = node.find(path, NS)
    else:
        child = node.find(path)
    if child is None:
        return ""
    return (child.text or "").strip()


def _normalize_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        parsed = parsedate_to_datetime(raw)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.replace("Z", "+0000") if fmt.endswith("%z") else raw, fmt).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            continue
    return raw
