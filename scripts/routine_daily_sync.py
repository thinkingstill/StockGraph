#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _parse_date(value: str) -> date:
    normalized = value.strip().replace("/", "-")
    if normalized == "yesterday":
        china_tz = timezone(timedelta(hours=8))
        return datetime.now(china_tz).date() - timedelta(days=1)
    if len(normalized) == 8 and normalized.isdigit():
        return datetime.strptime(normalized, "%Y%m%d").date()
    return datetime.strptime(normalized, "%Y-%m-%d").date()


def _default_target_date() -> date:
    china_tz = timezone(timedelta(hours=8))
    return datetime.now(china_tz).date() - timedelta(days=1)


def _load_trade_dates(start: date, end: date) -> set[date]:
    import akshare as ak

    frame = ak.tool_trade_date_hist_sina()
    if frame.empty or "trade_date" not in frame.columns:
        raise RuntimeError("akshare did not return a usable A-share trade calendar")
    values = set()
    for item in frame["trade_date"].tolist():
        if isinstance(item, datetime):
            parsed = item.date()
        elif isinstance(item, date):
            parsed = item
        else:
            text = str(item).strip()
            parsed = datetime.strptime(text[:10], "%Y-%m-%d").date()
        if start <= parsed <= end:
            values.add(parsed)
    return values


def is_trade_date(target: date) -> bool:
    return target in _load_trade_dates(target, target)


def _write_github_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run routine non-LLM StockGraph data jobs for one A-share trading date.")
    parser.add_argument("--target-date", help="Target date, YYYY-MM-DD/YYYYMMDD, default: yesterday in Asia/Shanghai")
    parser.add_argument("--force", action="store_true", help="Run even when the target date is not in the A-share trade calendar")
    args = parser.parse_args()

    target = _parse_date(args.target_date) if args.target_date else _default_target_date()
    target_text = target.strftime("%Y-%m-%d")
    compact_target = target.strftime("%Y%m%d")
    _write_github_output("target_date", target_text)

    if not args.force and not is_trade_date(target):
        print(f"[stockgraph] {target_text} is not an A-share trading date; routine jobs skipped")
        _write_github_output("should_commit", "false")
        _write_github_output("should_deploy", "false")
        return 0

    env = os.environ.copy()
    env.update(
        {
            "TARGET_DATE": target_text,
            "SYNC_DRAGON_TIGER": env.get("SYNC_DRAGON_TIGER", "1"),
            "SYNC_MARKET_OVERVIEW": env.get("SYNC_MARKET_OVERVIEW", "1"),
            "SYNC_NEWS": "0",
            "BUILD_GRAPHS": env.get("BUILD_GRAPHS", "1"),
            "ANALYZE_DRAGON_TIGER": env.get("ANALYZE_DRAGON_TIGER", "1"),
            "DRAGON_TIGER_ANALYSIS_START_DATE": target_text,
            "DRAGON_TIGER_ANALYSIS_END_DATE": target_text,
            "ROUTINE_TRADE_DATE": compact_target,
        }
    )
    print(f"[stockgraph] running routine jobs for {target_text}")
    subprocess.run(["bash", str(ROOT_DIR / "run_daily_sync.sh")], cwd=ROOT_DIR, env=env, check=True)
    _write_github_output("should_commit", "true")
    _write_github_output("should_deploy", "true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
