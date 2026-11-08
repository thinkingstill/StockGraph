#!/usr/bin/env python3
"""按交易日区间回补龙虎榜（含席位明细）。

特点：
- 跳过周末与非交易日（无数据即视为非交易日，自动记录，不重试）
- 断点续传：已入库的日期直接跳过，中断后重跑不会重复劳动
- 限速：默认每个交易日之间间隔 0.6s，可通过 --sleep 调整
- 结果落盘到 data/shared_state/backfill_dragon_tiger_<start>_<end>.json，便于核对覆盖率
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core import configure_logging  # noqa: E402
from stockgraph.core.paths import SHARED_STATE_DIR  # noqa: E402
from stockgraph.infrastructure.db.connection import get_connection  # noqa: E402
from stockgraph.infrastructure.db.repositories import DragonTigerRepository  # noqa: E402

logger = logging.getLogger("backfill.dragon_tiger")


def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"无法解析日期: {value}")


def iter_days(start: date, end: date):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def date_stats(conn, trade_date: str) -> tuple[int, int]:
    stocks = conn.execute(
        "SELECT COUNT(*) FROM daily_summaries WHERE date = ?", (trade_date,)
    ).fetchone()[0]
    seats = conn.execute(
        "SELECT COUNT(*) FROM stock_seat_operations WHERE date = ?", (trade_date,)
    ).fetchone()[0]
    return int(stocks or 0), int(seats or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="回补 2026 龙虎榜数据")
    parser.add_argument("--start", type=parse_date, default=date(2026, 1, 1))
    parser.add_argument("--end", type=parse_date, default=date.today())
    parser.add_argument("--sleep", type=float, default=0.6, help="每个交易日之间的间隔秒数")
    parser.add_argument("--force", action="store_true", help="即使已入库也重新抓取")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    configure_logging()
    repository = DragonTigerRepository()
    repository.initialize_database()

    from stockgraph.application.services.dragon_tiger_ingestion import DragonTigerIngestionService

    service = DragonTigerIngestionService(repository=repository)

    report_path = args.report or (
        SHARED_STATE_DIR
        / f"backfill_dragon_tiger_{args.start.isoformat()}_{args.end.isoformat()}.json"
    )
    report: dict = {
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "days": {},
        "ok": [],
        "empty": [],
        "failed": [],
        "skipped": [],
    }

    total = 0
    for day in iter_days(args.start, args.end):
        total += 1
        trade_date = day.isoformat()
        with get_connection() as conn:
            stocks, seats = date_stats(conn, trade_date)

        if stocks > 0 and not args.force:
            report["skipped"].append(trade_date)
            report["days"][trade_date] = {"stocks": stocks, "seats": seats, "status": "cached"}
            logger.info("[%s] 已存在 %d 只 / %d 席位，跳过", trade_date, stocks, seats)
            continue

        ok = False
        for attempt in range(1, args.retries + 1):
            try:
                ok = service.sync(trade_date=trade_date, purge_existing=True)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] 第 %d 次抓取异常: %s", trade_date, attempt, exc)
                time.sleep(2.0 * attempt)

        with get_connection() as conn:
            stocks, seats = date_stats(conn, trade_date)
        record = {"stocks": stocks, "seats": seats, "status": "ok" if ok else "empty"}
        if ok and stocks > 0:
            report["ok"].append(trade_date)
        elif ok:
            report["empty"].append(trade_date)
        else:
            report["failed"].append(trade_date)
            record["status"] = "failed"
        report["days"][trade_date] = record
        logger.info("[%s] %s 股票=%d 席位=%d", trade_date, record["status"], stocks, seats)

        time.sleep(max(0.0, args.sleep))

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["summary"] = {
        "trading_days_with_data": len(report["ok"]) + len(report["skipped"]),
        "fetched": len(report["ok"]),
        "cached": len(report["skipped"]),
        "empty": len(report["empty"]),
        "failed": len(report["failed"]),
        "weekday_total": total,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("回补完成: %s", report["summary"])
    logger.info("报告: %s", report_path)
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
