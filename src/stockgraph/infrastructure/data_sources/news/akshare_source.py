"""基于 akshare 的个股近期新闻数据源。

优先使用 akshare 的 stock_news_em 接口获取东方财富个股新闻，
支持按股票代码批量拉取近期新闻。
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime

from stockgraph.domain.news.models import NewsArticle, NewsBatch
from stockgraph.infrastructure.data_sources.news.base import NewsSource

logger = logging.getLogger(__name__)


class AkShareStockNewsSource(NewsSource):
    """通过 akshare 获取个股近期新闻。"""

    name = "akshare个股新闻"

    def __init__(self, stock_codes: list[str] | None = None) -> None:
        self.stock_codes = stock_codes or []
        self.request_delay_seconds = self._env_float("STOCKGRAPH_REQUEST_DELAY_SECONDS", 0.8)

    def fetch(self, limit: int = 50) -> NewsBatch:
        if not self.stock_codes:
            logger.info("未指定股票代码，跳过个股新闻采集")
            return NewsBatch(source=self.name, articles=[])

        articles: list[NewsArticle] = []
        for code in self.stock_codes:
            try:
                if articles:
                    self._polite_sleep()
                batch = self._fetch_stock_news(code, limit)
                articles.extend(batch.articles)
            except Exception:
                logger.warning("个股新闻采集失败: %s", code, exc_info=True)
        return NewsBatch(source=self.name, articles=articles)

    def _fetch_stock_news(self, stock_code: str, limit: int) -> NewsBatch:
        import akshare as ak

        logger.info("正在采集个股新闻: %s", stock_code)
        df = ak.stock_news_em(symbol=stock_code)
        if df is None or df.empty:
            logger.info("个股 %s 无新闻数据", stock_code)
            return NewsBatch(source=self.name, articles=[])

        articles: list[NewsArticle] = []
        for _, row in df.head(limit).iterrows():
            title = str(row.get("新闻标题", "")).strip()
            content = str(row.get("新闻内容", "")).strip()
            published_at = str(row.get("发布时间", "")).strip()
            source_name = str(row.get("文章来源", "")).strip()
            url = str(row.get("新闻链接", "")).strip()
            keyword = str(row.get("关键词", stock_code)).strip()

            if not title:
                continue

            article = NewsArticle(
                source=f"{self.name}({source_name})",
                title=title,
                content=content,
                published_at=published_at,
                url=url,
                metadata={
                    "stock_code": stock_code,
                    "keyword": keyword,
                    "original_source": source_name,
                },
            )
            articles.append(article)

        logger.info("个股 %s 采集到 %d 条新闻", stock_code, len(articles))
        return NewsBatch(source=self.name, articles=articles)

    def _polite_sleep(self) -> None:
        if self.request_delay_seconds > 0:
            time.sleep(self.request_delay_seconds)

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, str(default)))
        except ValueError:
            return default


class AkShareMainNewsSource(NewsSource):
    """通过 akshare 获取财联社新闻快讯（全局新闻）。"""

    name = "akshare财联社快讯"

    def fetch(self, limit: int = 50) -> NewsBatch:
        import akshare as ak

        logger.info("正在采集财联社新闻快讯")
        try:
            delay_seconds = self._env_float("STOCKGRAPH_REQUEST_DELAY_SECONDS", 0.8)
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            df = ak.stock_news_main_cx()
            if df is None or df.empty:
                logger.info("财联社快讯无数据")
                return NewsBatch(source=self.name, articles=[])
        except Exception:
            logger.warning("财联社快讯采集失败", exc_info=True)
            return NewsBatch(source=self.name, articles=[])

        articles: list[NewsArticle] = []
        for _, row in df.head(limit).iterrows():
            # stock_news_main_cx 返回列: tag, summary, url
            title = str(row.get("tag", "")).strip()
            content = str(row.get("summary", "")).strip()
            url = str(row.get("url", "")).strip()

            if not title and not content:
                continue

            # 用 summary 作为标题（如果 tag 为空），content 作为正文
            article = NewsArticle(
                source=self.name,
                title=title or content[:60],
                content=content,
                published_at="",
                url=url,
                metadata={},
            )
            articles.append(article)

        logger.info("财联社快讯采集到 %d 条新闻", len(articles))
        return NewsBatch(source=self.name, articles=articles)

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, str(default)))
        except ValueError:
            return default
