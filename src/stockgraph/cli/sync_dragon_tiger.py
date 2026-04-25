import argparse
import logging

from stockgraph.application.services import DashboardGenerationService, DragonTigerIngestionService
from stockgraph.core import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取龙虎榜数据并刷新页面")
    parser.add_argument("--date", type=str, help="指定抓取日期，格式 YYYY-MM-DD")
    parser.add_argument("--purge-existing", action="store_true", help="抓取前删除目标日期的历史数据")
    parser.add_argument("--skip-dashboard", action="store_true", help="仅抓取入库，不生成 HTML")
    args = parser.parse_args()

    configure_logging()
    success = DragonTigerIngestionService().sync(
        trade_date=args.date,
        purge_existing=args.purge_existing or bool(args.date),
    )
    if not success:
        logging.error("龙虎榜同步失败")
        return 1

    if not args.skip_dashboard:
        outputs = DashboardGenerationService().generate()
        for path in outputs:
            logging.info("已生成页面: %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
