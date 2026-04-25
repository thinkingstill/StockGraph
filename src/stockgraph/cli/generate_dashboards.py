import logging

from stockgraph.application.services import DashboardGenerationService
from stockgraph.core import configure_logging


def main() -> int:
    configure_logging()
    outputs = DashboardGenerationService().generate()
    if not outputs:
        logging.warning("数据库中没有龙虎榜数据，未生成页面")
        return 1
    for path in outputs:
        logging.info("已生成页面: %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
