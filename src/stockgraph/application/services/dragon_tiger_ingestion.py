import logging
from datetime import datetime, timedelta

from stockgraph.infrastructure.data_sources.dragon_tiger import (
    EastMoneyApiSource,
    EastMoneyDatacenterFallbackSource,
)
from stockgraph.infrastructure.db import DragonTigerRepository

logger = logging.getLogger(__name__)


class DragonTigerIngestionService:
    """龙虎榜抓取编排。

    数据源链只保留真实来源：主源拿「上榜汇总 + 全市场席位明细」，
    降级源只拿汇总。任何一级失败都不会伪造席位数据。
    """

    def __init__(self, repository: DragonTigerRepository | None = None) -> None:
        self.repository = repository or DragonTigerRepository()
        self.sources = [
            EastMoneyApiSource(),
            EastMoneyDatacenterFallbackSource(),
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
            try:
                batch = source.fetch(target_date)
            except Exception:  # noqa: BLE001
                logger.warning("数据源异常，继续尝试下一个: %s", source.name, exc_info=True)
                continue
            if batch:
                logger.info("抓取成功: %s", source.name)
                return self.repository.save_batch(batch)
        logger.error("所有龙虎榜数据源均失败: %s", target_date)
        return False
