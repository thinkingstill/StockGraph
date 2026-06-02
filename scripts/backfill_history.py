#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from routine_daily_sync import _load_trade_dates


ROOT_DIR = Path(__file__).resolve().parents[1]
VALID_AREAS = {"dragon_tiger", "market_overview", "graphs", "stock_locations"}


def _parse_date(value: str) -> date:
    text = value.strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    return datetime.strptime(text, "%Y-%m-%d").date()


def _date_range(start: date, end: date) -> list[date]:
    if start > end:
        raise ValueError("start date must be earlier than or equal to end date")
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _parse_areas(value: str) -> set[str]:
    if value == "all":
        return set(VALID_AREAS)
    areas = {item.strip() for item in value.split(",") if item.strip()}
    invalid = areas - VALID_AREAS
    if invalid:
        raise ValueError(f"unsupported areas: {', '.join(sorted(invalid))}")
    return areas


def _write_github_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill StockGraph historical non-LLM data by date range.")
    parser.add_argument("--start-date", required=True, help="Start date, YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--end-date", required=True, help="End date, YYYY-MM-DD or YYYYMMDD")
    parser.add_argument(
        "--areas",
        default="all",
        help="Comma-separated areas: dragon_tiger,market_overview,graphs,stock_locations; or all",
    )
    parser.add_argument("--force", action="store_true", help="Run every calendar day without A-share calendar filtering")
    args = parser.parse_args()

    start = _parse_date(args.start_date)
    end = _parse_date(args.end_date)
    areas = _parse_areas(args.areas)
    candidates = _date_range(start, end)

    if args.force:
        targets = candidates
    else:
        trade_dates = _load_trade_dates(start, end)
        targets = [item for item in candidates if item in trade_dates]

    if not targets:
        print(f"[stockgraph] no trading dates to backfill in {start:%Y-%m-%d}..{end:%Y-%m-%d}")
        _write_github_output("should_commit", "false")
        _write_github_output("should_deploy", "false")
        return 0

    print(
        "[stockgraph] backfill selected dates: "
        + ", ".join(item.strftime("%Y-%m-%d") for item in targets)
    )
    env_base = os.environ.copy()
    for target in targets:
        target_text = target.strftime("%Y-%m-%d")
        env = env_base.copy()
        env.update(
            {
                "TARGET_DATE": target_text,
                "SYNC_DRAGON_TIGER": "1" if "dragon_tiger" in areas else "0",
                "SYNC_MARKET_OVERVIEW": "1" if "market_overview" in areas else "0",
                "BUILD_GRAPHS": "1" if "graphs" in areas else "0",
                "SYNC_STOCK_LOCATIONS": "1" if "stock_locations" in areas else "0",
                "SYNC_NEWS": "0",
                "ANALYZE_DRAGON_TIGER": "1" if "dragon_tiger" in areas else "0",
                "DRAGON_TIGER_ANALYSIS_START_DATE": target_text,
                "DRAGON_TIGER_ANALYSIS_END_DATE": target_text,
            }
        )
        print(f"[stockgraph] backfilling {target_text}: {','.join(sorted(areas))}")
        subprocess.run(["bash", str(ROOT_DIR / "run_daily_sync.sh")], cwd=ROOT_DIR, env=env, check=True)

    _write_github_output("should_commit", "true")
    _write_github_output("should_deploy", "true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
