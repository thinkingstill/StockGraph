import logging
from datetime import datetime, timedelta

from stockgraph.infrastructure.data_sources.dragon_tiger import (
    EastMoneyApiSource,
    EastMoneyWebFallbackSource,
    SinaFallbackSource,
    StockApiFallbackSource,
    TonghuashunFallbackSource,
)
from stockgraph.infrastructure.db import DragonTigerRepository

logger = logging.getLogger(__name__)


class DragonTigerIngestionService:
    def __init__(self, repository: DragonTigerRepository | None = None) -> None:
        self.repository = repository or DragonTigerRepository()
        self.sources = [
            EastMoneyApiSource(),
            EastMoneyWebFallbackSource(),
            SinaFallbackSource(),
            TonghuashunFallbackSource(),
            StockApiFallbackSource(),
        ]

    @staticmethod
    def get_previous_trading_date(base_time: datetime | None = None) -> str:
        now = base_time or datetime.now()
        if now.weekday() == 0:
            target = now - timedelta(days=3)
        elif now.weekday() >= 5:
            target = now - timedelta(days=now.weekday() - 4)
        else:
            target = now - timedelta(days=1)
        return target.strftime("%Y-%m-%d")

    def sync(self, trade_date: str | None = None, purge_existing: bool = False) -> bool:
        self.repository.initialize_database()
        target_date = trade_date or self.get_previous_trading_date()
        if purge_existing:
            self.repository.purge_by_date(target_date)
            logger.info("已清理历史数据: %s", target_date)

        for source in self.sources:
            logger.info("尝试抓取数据源: %s", source.name)
            batch = source.fetch(target_date)
            if batch:
                logger.info("抓取成功: %s", source.name)
                return self.repository.save_batch(batch)
        logger.error("所有龙虎榜数据源均失败: %s", target_date)
        return False
