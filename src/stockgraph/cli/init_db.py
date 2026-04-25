import argparse
import logging

from stockgraph.core import configure_logging
from stockgraph.infrastructure.db import DragonTigerRepository, database_path


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 StockGraph SQLite 数据库")
    parser.add_argument("--import-legacy", action="store_true", help="从 source/dragon_tiger.db 导入历史数据库")
    parser.add_argument("--overwrite", action="store_true", help="导入 legacy 数据时覆盖当前数据库")
    args = parser.parse_args()

    configure_logging()
    repository = DragonTigerRepository()
    if args.import_legacy:
        imported = repository.import_legacy_database(overwrite=args.overwrite)
        if imported:
            logging.info("数据库初始化完成: %s", database_path())
            return 0
    repository.initialize_database()
    logging.info("数据库初始化完成: %s", database_path())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
