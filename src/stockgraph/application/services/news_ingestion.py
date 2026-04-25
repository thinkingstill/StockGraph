import logging

from stockgraph.domain.news import link_article_entities, normalize_news_article
from stockgraph.infrastructure.data_sources.news import CLSNewsSource, EastMoneyNewsSource, RSSNewsSource
from stockgraph.infrastructure.db.repositories import NewsRepository

logger = logging.getLogger(__name__)


class NewsIngestionService:
    def __init__(self, repository: NewsRepository | None = None) -> None:
        self.repository = repository or NewsRepository()
        self.sources = [
            EastMoneyNewsSource(),
            CLSNewsSource(),
            RSSNewsSource(),
        ]

    def sync(self, limit: int = 50) -> dict:
        self.repository.initialize_database()
        result = {"sources": [], "inserted_articles": 0}
        for source in self.sources:
            batch = source.fetch(limit=limit)
            normalized = []
            for article in batch.articles:
                normalized.append(link_article_entities(normalize_news_article(article)))
            batch.articles = normalized
            inserted = self.repository.save_batch(batch)
            logger.info("新闻源同步完成: %s, 新增 %s 条", source.name, inserted)
            result["sources"].append({"source": source.name, "fetched": len(batch.articles), "inserted": inserted})
            result["inserted_articles"] += inserted
        return result
