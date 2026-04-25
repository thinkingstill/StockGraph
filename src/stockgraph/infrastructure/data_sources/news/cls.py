import logging

from stockgraph.domain.news import NewsBatch
from stockgraph.infrastructure.data_sources.news.base import NewsSource

logger = logging.getLogger(__name__)


class CLSNewsSource(NewsSource):
    name = "财联社"

    def fetch(self, limit: int = 50) -> NewsBatch:
        logger.warning("%s 抓取逻辑尚未接入，当前返回空批次", self.name)
        return NewsBatch(source=self.name, articles=[])
