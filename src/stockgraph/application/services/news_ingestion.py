"""新闻采集编排。

个股新闻优先走自研的东方财富搜索适配器：akshare 的 `stock_news_em`
在 pandas 3.0 / pyarrow 下会抛 `ArrowInvalid: invalid escape sequence`，
整条链路静默返回空。自研适配器直连同一底层接口，不依赖 pandas，
akshare 只作为兜底保留。
"""

from __future__ import annotations

import logging

from stockgraph.domain.news import link_article_entities, normalize_news_article
from stockgraph.infrastructure.data_sources.news import (
    AkShareMainNewsSource,
    AkShareStockNewsSource,
    CLSNewsSource,
    EastMoneyNewsSource,
    RSSNewsSource,
)
from stockgraph.infrastructure.data_sources.news.eastmoney_search import (
    EastMoneyStockNewsSource,
)
from stockgraph.infrastructure.db.repositories import NewsRepository

logger = logging.getLogger(__name__)


class NewsIngestionService:
    def __init__(self, repository: NewsRepository | None = None) -> None:
        self.repository = repository or NewsRepository()
        self.global_sources = [
            CLSNewsSource(),
            EastMoneyNewsSource(),
            AkShareMainNewsSource(),
            RSSNewsSource(),
        ]

    def _save(self, batch) -> int:
        batch.articles = [
            link_article_entities(normalize_news_article(article)) for article in batch.articles
        ]
        return self.repository.save_batch(batch)

    def sync(self, limit: int = 50) -> dict:
        """同步全局新闻源。

        单个源失败不影响其他源：财经站点经常单点返回空响应，
        整批中断会让例行任务每天都缺数据。
        """
        self.repository.initialize_database()
        result = {"sources": [], "inserted_articles": 0}
        for source in self.global_sources:
            try:
                batch = source.fetch(limit=limit)
            except Exception:  # noqa: BLE001
                logger.warning("新闻源采集失败: %s", source.name, exc_info=True)
                result["sources"].append({"source": source.name, "fetched": 0, "inserted": 0, "error": True})
                continue
            inserted = self._save(batch)
            logger.info("新闻源同步完成: %s, 新增 %s 条", source.name, inserted)
            result["sources"].append(
                {"source": source.name, "fetched": len(batch.articles), "inserted": inserted}
            )
            result["inserted_articles"] += inserted
        return result

    def sync_stock_news(self, stock_codes: list[str], limit: int = 20) -> dict:
        """同步指定股票的个股近期新闻。"""
        self.repository.initialize_database()
        pages = max(1, limit // 20)

        fetched = 0
        inserted = 0
        used_source = ""

        primary = EastMoneyStockNewsSource()
        for code in stock_codes:
            try:
                batch = primary.fetch_for_stock(code, pages=pages)
            except Exception:  # noqa: BLE001
                logger.warning("个股新闻主源失败: %s", code, exc_info=True)
                batch = None
            if batch and batch.articles:
                fetched += len(batch.articles)
                inserted += self._save(batch)
                used_source = primary.name

        if fetched:
            logger.info("个股新闻同步完成: %s, 新增 %s 条", stock_codes, inserted)
            return {
                "source": used_source,
                "stock_codes": stock_codes,
                "fetched": fetched,
                "inserted": inserted,
            }

        # 兜底：主源全空时才用 akshare（pandas 3.x 下大概率仍为空，但保持链路可用）
        logger.info("主源无数据，回退 akshare 个股新闻")
        fallback = AkShareStockNewsSource(stock_codes=stock_codes)
        batch = fallback.fetch(limit=limit)
        inserted = self._save(batch)
        return {
            "source": fallback.name,
            "stock_codes": stock_codes,
            "fetched": len(batch.articles),
            "inserted": inserted,
        }
