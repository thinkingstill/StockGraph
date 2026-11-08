"""构建龙虎榜关系图快照。

    # 单个交易日（三类图：席位-股票二部图、席位共现、股票共现）
    python scripts/build_graph_snapshots.py --date 2026-11-05 --persist

    # 区间：逐交易日各生成一张快照（推荐用法）
    python scripts/build_graph_snapshots.py --start-date 2026-01-01 --end-date 2026-11-06 --persist

    # 只建某一类图
    python scripts/build_graph_snapshots.py --start-date 2026-01-01 --end-date 2026-11-06 \
        --types seat_stock --persist

原实现会把整个区间的记录塞进一个以 end-date 命名的快照，导致快照日期与边日期不一致；
现在每个交易日一张快照，二者严格对应。
"""

from __future__ import annotations

import argparse
import json
import logging

from stockgraph.application.services import NetworkAnalysisService
from stockgraph.core import configure_logging

logger = logging.getLogger(__name__)

ALL_TYPES = ("seat_stock", "seat_projection", "stock_projection")


def main() -> int:
    parser = argparse.ArgumentParser(description="构建龙虎榜关系图快照")
    parser.add_argument("--date", type=str, help="构建单个交易日，如 2026-11-05")
    parser.add_argument("--start-date", type=str, help="区间开始 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, help="区间结束 YYYY-MM-DD")
    parser.add_argument(
        "--types", nargs="+", choices=ALL_TYPES, default=list(ALL_TYPES), help="只构建指定类型的图"
    )
    parser.add_argument("--persist", action="store_true", help="写入图数据库")
    parser.add_argument("--rebuild", action="store_true", help="忽略已有快照，强制重建")
    args = parser.parse_args()

    configure_logging()
    service = NetworkAnalysisService()

    if args.date:
        result: dict = {}
        for name in args.types:
            result[name] = service.build_snapshot(name, args.date, persist=args.persist)
    else:
        result = service.build_range(
            start_date=args.start_date,
            end_date=args.end_date,
            persist=args.persist,
            builders=tuple(args.types),
            skip_existing=not args.rebuild,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
