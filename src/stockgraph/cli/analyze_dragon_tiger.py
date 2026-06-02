import argparse
import logging
from datetime import datetime
from pathlib import Path

from stockgraph.application.services import DragonTigerAnalysisService
from stockgraph.core import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="导出龙虎榜数据和网络图分析 JSON")
    parser.add_argument("--date", type=str, help="单个交易日，格式 YYYY-MM-DD")
    parser.add_argument("--start-date", type=str, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--output", type=Path, help="输出 JSON 文件路径，默认写入 outputs/dragon_tiger/")
    parser.add_argument("--top-limit", type=int, default=20, help="榜单保留条数，默认 20")
    parser.add_argument("--persist-graphs", action="store_true", help="同时将三类图快照写入 SQLite")
    args = parser.parse_args()

    configure_logging()
    start_date, end_date = _resolve_period(args)
    output_path = DragonTigerAnalysisService().export(
        start_date=start_date,
        end_date=end_date,
        output_path=args.output,
        top_limit=max(args.top_limit, 1),
        persist_graphs=args.persist_graphs,
    )
    logging.info("龙虎榜分析结果已导出: %s", output_path)
    return 0


def _resolve_period(args: argparse.Namespace) -> tuple[str | None, str | None]:
    if args.date and (args.start_date or args.end_date):
        raise SystemExit("--date 不能和 --start-date/--end-date 同时使用")
    for value in (args.date, args.start_date, args.end_date):
        if value:
            _validate_date(value)
    if args.date:
        return args.date, args.date
    if args.start_date and args.end_date and args.start_date > args.end_date:
        raise SystemExit("--start-date 不能晚于 --end-date")
    return args.start_date, args.end_date


def _validate_date(value: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"日期格式错误: {value}，应为 YYYY-MM-DD") from exc


if __name__ == "__main__":
    raise SystemExit(main())
