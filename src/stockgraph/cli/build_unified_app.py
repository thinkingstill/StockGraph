import logging

from stockgraph.application.services.unified_frontend import UnifiedFrontendService
from stockgraph.core import configure_logging


def main() -> int:
    configure_logging()
    outputs = UnifiedFrontendService().generate()
    for path in outputs:
        logging.info("已生成统一前端产物: %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
