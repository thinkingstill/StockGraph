import argparse
import logging

from stockgraph.application.services import MarketOverviewService
from stockgraph.core import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="同步市场概览、雪球热度和行业榜单")
    parser.add_argument("--date", type=str, help="指定交易日 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--year", type=str, help="额外构建年度行业榜单，例如 2025")
    args = parser.parse_args()

    configure_logging()
    service = MarketOverviewService()
    if args.date:
        target_date = args.date.replace("-", "")
        result = service.sync_daily(trade_date=target_date)
        logging.info("市场概览同步完成: %s", result)
    else:
        result = service.sync_daily()
        logging.info("市场概览同步完成: %s", result)

    if args.year:
        yearly = service.build_yearly_industry_rankings(args.year)
        logging.info("年度行业榜单生成完成: %s", yearly)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
