import argparse
import logging

from stockgraph.application.services import NewsIngestionService
from stockgraph.core import configure_logging
from stockgraph.infrastructure.db.repositories import DragonTigerRepository


def _get_recent_stock_codes(limit: int = 20) -> list[str]:
    """从龙虎榜数据中获取近期活跃股票代码，用于个股新闻采集。"""
    try:
        repo = DragonTigerRepository()
        repo.initialize_database()
        dates = repo.list_trade_dates()
        if not dates:
            return []
        codes: list[str] = []
        for date in dates[:3]:  # 取最近3个交易日
            stocks = repo.aggregate_active_stocks(date, limit=limit)
            for s in stocks:
                code = s.get("code", "")
                if code and code not in codes:
                    codes.append(code)
        return codes[:limit]
    except Exception:
        logging.warning("获取龙虎榜股票代码失败", exc_info=True)
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="同步新闻资讯并写入数据库")
    parser.add_argument("--limit", type=int, default=50, help="每个新闻源最多抓取多少条")
    parser.add_argument(
        "--stock-codes",
        type=str,
        default="",
        help="逗号分隔的股票代码列表，用于个股新闻采集。留空则自动从龙虎榜获取",
    )
    parser.add_argument(
        "--stock-limit",
        type=int,
        default=20,
        help="每个股票最多采集多少条新闻",
    )
    parser.add_argument(
        "--skip-stock-news",
        action="store_true",
        help="跳过个股新闻采集，仅同步全局新闻",
    )
    args = parser.parse_args()

    configure_logging()
    service = NewsIngestionService()

    # 同步全局新闻
    result = service.sync(limit=args.limit)
    logging.info("全局新闻同步完成: %s", result)

    # 同步个股新闻
    if not args.skip_stock_news:
        if args.stock_codes:
            stock_codes = [c.strip() for c in args.stock_codes.split(",") if c.strip()]
        else:
            stock_codes = _get_recent_stock_codes()
            logging.info("自动获取龙虎榜活跃股票: %s", stock_codes)

        if stock_codes:
            stock_result = service.sync_stock_news(stock_codes, limit=args.stock_limit)
            logging.info("个股新闻同步完成: %s", stock_result)
            result["stock_news"] = stock_result
        else:
            logging.info("无股票代码可采集个股新闻")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
