import argparse
import logging

from stockgraph.application.services.stock_locations import StockLocationService
from stockgraph.core import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 A 股上市公司所在地映射")
    parser.add_argument("--codes", type=str, default="", help="逗号分隔的股票代码；留空则读取 stock_basic_info.pkl 全量列表")
    parser.add_argument("--limit", type=int, default=100, help="本次最多新增抓取多少只股票；0 表示不限制")
    parser.add_argument("--sleep", type=float, default=1.2, help="每只股票请求后的等待秒数，避免频繁访问巨潮")
    parser.add_argument("--force", action="store_true", help="强制刷新已有映射和缓存")
    parser.add_argument("--rebuild-only", action="store_true", help="只用本地缓存重建 stock_location_mapping.json，不访问远端")
    args = parser.parse_args()

    configure_logging()
    codes = [item.strip() for item in args.codes.split(",") if item.strip()] if args.codes else None
    result = StockLocationService().sync(
        codes=codes,
        limit=args.limit,
        sleep_seconds=args.sleep,
        force=args.force,
        rebuild_only=args.rebuild_only,
    )
    logging.info("股票所在地同步完成: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
