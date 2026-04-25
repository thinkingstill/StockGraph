import argparse
import logging

from stockgraph.application.services import NetworkAnalysisService
from stockgraph.core import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="构建龙虎榜关系图快照")
    parser.add_argument("--start-date", type=str, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--persist", action="store_true", help="将图快照写入数据库")
    args = parser.parse_args()

    configure_logging()
    service = NetworkAnalysisService()
    summaries = {
        "seat_stock": service.build_stock_seat_projection(
            start_date=args.start_date,
            end_date=args.end_date,
            persist=args.persist,
        ),
        "seat_projection": service.build_seat_projection(
            start_date=args.start_date,
            end_date=args.end_date,
            persist=args.persist,
        ),
        "stock_projection": service.build_stock_projection(
            start_date=args.start_date,
            end_date=args.end_date,
            persist=args.persist,
        ),
    }
    logging.info("图快照构建完成: %s", summaries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
