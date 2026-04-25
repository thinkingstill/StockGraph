import argparse
import logging

from stockgraph.application.services import NewsIngestionService
from stockgraph.core import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="同步新闻资讯并写入数据库")
    parser.add_argument("--limit", type=int, default=50, help="每个新闻源最多抓取多少条")
    args = parser.parse_args()

    configure_logging()
    result = NewsIngestionService().sync(limit=args.limit)
    logging.info("新闻同步完成: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
