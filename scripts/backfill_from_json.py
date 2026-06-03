#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from stockgraph.core.paths import DRAGON_TIGER_OUTPUT_DIR, MARKET_DATA_DIR, ensure_runtime_dirs
from stockgraph.domain.dragon_tiger import detect_seat_type, match_trader
from stockgraph.infrastructure.db.connection import get_connection
from stockgraph.infrastructure.db.schema import SCHEMA_SQL


VALID_AREAS = {"dragon_tiger", "market_overview", "graphs"}


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().replace("/", "-")
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").strftime("%Y-%m-%d")
    return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")


def _compact_date(value: str | None) -> str | None:
    parsed = _parse_date(value)
    return parsed.replace("-", "") if parsed else None


def _date_in_range(value: str, start: str | None, end: str | None) -> bool:
    parsed = _parse_date(value)
    if not parsed:
        return False
    return (not start or parsed >= start) and (not end or parsed <= end)


def _parse_areas(value: str) -> set[str]:
    if value == "all":
        return set(VALID_AREAS)
    areas = {item.strip() for item in value.split(",") if item.strip()}
    invalid = areas - VALID_AREAS
    if invalid:
        raise ValueError(f"unsupported areas: {', '.join(sorted(invalid))}")
    return areas


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[stockgraph] skip unreadable json: {path} ({exc})")
        return None


def _extract_digits_date(filename: str) -> str:
    digits = "".join(ch for ch in filename if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ""


def _normalize_stock_code(value) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def _as_float(value) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _load_market_rows(prefix: str, start_compact: str | None, end_compact: str | None) -> list[tuple[str, Path, list[dict]]]:
    rows = []
    for path in sorted(MARKET_DATA_DIR.glob(f"{prefix}_*.json")):
        trade_date = _extract_digits_date(path.name)
        if not trade_date:
            continue
        if start_compact and trade_date < start_compact:
            continue
        if end_compact and trade_date > end_compact:
            continue
        payload = _read_json(path)
        if isinstance(payload, list):
            rows.append((trade_date, path, payload))
    return rows


def backfill_market_overview(start: str | None, end: str | None, dry_run: bool) -> dict[str, int]:
    start_compact = start.replace("-", "") if start else None
    end_compact = end.replace("-", "") if end else None
    stock_files = _load_market_rows("stock_daily", start_compact, end_compact)
    hot_files = _load_market_rows("hot_daily", start_compact, end_compact)
    stats = {"stock_rows": 0, "hot_rows": 0, "industry_rows": 0}

    if dry_run:
        stats["stock_rows"] = sum(len(rows) for _, _, rows in stock_files)
        stats["hot_rows"] = sum(len(rows) for _, _, rows in hot_files)
        stats["industry_rows"] = len(stock_files) * 2
        return stats

    with get_connection() as conn:
        cursor = conn.cursor()
        for trade_date, _, records in stock_files:
            industry_change: dict[str, float] = defaultdict(float)
            for row in records:
                code = _normalize_stock_code(row.get("代码") or row.get("stock_code"))
                if not code:
                    continue
                stock_name = str(row.get("名称") or row.get("stock_name") or "")
                industry = str(row.get("行业") or "未知")
                change_pct = _as_float(row.get("涨跌幅") or row.get("change_pct"))
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO market_daily_snapshots
                    (trade_date, stock_code, stock_name, latest_price, change_pct, industry, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trade_date,
                        code,
                        stock_name,
                        _as_float(row.get("最新价") or row.get("latest_price")),
                        change_pct,
                        industry,
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )
                stats["stock_rows"] += 1
                if industry and industry not in {"未知", "缺失"} and change_pct is not None:
                    industry_change[industry] += change_pct
            if industry_change:
                top_industry = max(industry_change.items(), key=lambda item: item[1])[0]
                bottom_industry = min(industry_change.items(), key=lambda item: item[1])[0]
                for direction, industry in (("top", top_industry), ("bottom", bottom_industry)):
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO market_industry_rankings
                        (trade_date, industry, direction)
                        VALUES (?, ?, ?)
                        """,
                        (trade_date, industry, direction),
                    )
                    stats["industry_rows"] += 1

        for trade_date, _, records in hot_files:
            for row in records:
                code = _normalize_stock_code(row.get("股票代码") or row.get("stock_code"))
                if not code:
                    continue
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO market_hot_rankings
                    (trade_date, stock_code, stock_name, latest_price, follow_rank, tweet_rank, deal_rank, change_pct, industry, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trade_date,
                        code,
                        str(row.get("股票简称") or row.get("stock_name") or ""),
                        _as_float(row.get("最新价") or row.get("latest_price")),
                        _as_float(row.get("关注") or row.get("follow_rank")),
                        _as_float(row.get("讨论") or row.get("tweet_rank")),
                        _as_float(row.get("交易") or row.get("deal_rank")),
                        _as_float(row.get("涨跌幅") or row.get("change_pct")),
                        str(row.get("行业") or row.get("industry") or "未知"),
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )
                stats["hot_rows"] += 1
        conn.commit()
    return stats


def _dragon_paths(start: str | None, end: str | None) -> list[Path]:
    paths = []
    for path in sorted(DRAGON_TIGER_OUTPUT_DIR.glob("dragon_tiger_analysis_*.json")):
        payload = _read_json(path)
        if not isinstance(payload, dict) or payload.get("schemaVersion") != "dragon_tiger_analysis.v1":
            continue
        trade_dates = payload.get("period", {}).get("tradeDates") or []
        operations = payload.get("operations") or []
        candidate_dates = trade_dates or [row.get("date") for row in operations if isinstance(row, dict)]
        if any(_date_in_range(str(item), start, end) for item in candidate_dates):
            paths.append(path)
    return paths


def backfill_dragon_tiger(start: str | None, end: str | None, dry_run: bool) -> dict[str, int]:
    operations_by_date: dict[str, dict[tuple[str, str, str], dict]] = defaultdict(dict)
    for path in _dragon_paths(start, end):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        for row in payload.get("operations") or []:
            if not isinstance(row, dict):
                continue
            date = _parse_date(str(row.get("date") or ""))
            if not date or not _date_in_range(date, start, end):
                continue
            code = _normalize_stock_code(row.get("stock_code") or row.get("stockCode"))
            seat_name = str(row.get("seat_name") or row.get("seatName") or "").strip()
            direction = str(row.get("direction") or "").strip()
            amount = _as_float(row.get("amount"))
            if not code or not seat_name or direction not in {"买", "卖"} or amount is None:
                continue
            normalized = {
                "date": date,
                "stock_code": code,
                "stock_name": str(row.get("stock_name") or row.get("stockName") or ""),
                "seat_name": seat_name,
                "direction": direction,
                "amount": amount,
                "net_amount": amount if direction == "买" else -amount,
                "seat_type": row.get("seat_type") or row.get("seatType") or detect_seat_type(seat_name),
                "trader_alias": row.get("trader_alias") or row.get("traderAlias") or match_trader(seat_name),
            }
            key = (code, seat_name, direction)
            operations_by_date[date][key] = normalized

    stats = {"operations": sum(len(items) for items in operations_by_date.values()), "summaries": 0, "seat_details": 0}
    if dry_run:
        stats["summaries"] = sum(len({row["stock_code"] for row in items.values()}) for items in operations_by_date.values())
        stats["seat_details"] = len({row["seat_name"] for items in operations_by_date.values() for row in items.values()})
        return stats

    with get_connection() as conn:
        cursor = conn.cursor()
        for trade_date, operations in sorted(operations_by_date.items()):
            cursor.execute("DELETE FROM daily_summaries WHERE date = ?", (trade_date,))
            cursor.execute("DELETE FROM stock_seat_operations WHERE date = ?", (trade_date,))
            grouped: dict[str, list[dict]] = defaultdict(list)
            for row in operations.values():
                grouped[row["stock_code"]].append(row)
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO stock_seat_operations
                    (date, stock_code, stock_name, seat_name, direction, amount, net_amount, seat_type, trader_alias)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["date"],
                        row["stock_code"],
                        row["stock_name"],
                        row["seat_name"],
                        row["direction"],
                        row["amount"],
                        row["net_amount"],
                        row["seat_type"],
                        row["trader_alias"],
                    ),
                )
                existing = cursor.execute("SELECT seat_name FROM seat_details WHERE seat_name = ?", (row["seat_name"],)).fetchone()
                if existing:
                    cursor.execute(
                        """
                        UPDATE seat_details
                        SET last_seen_date = ?, total_operations = total_operations + 1, total_amount = total_amount + ?
                        WHERE seat_name = ?
                        """,
                        (trade_date, row["amount"], row["seat_name"]),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO seat_details
                        (seat_name, seat_type, first_seen_date, last_seen_date, total_operations, total_amount)
                        VALUES (?, ?, ?, ?, 1, ?)
                        """,
                        (row["seat_name"], row["seat_type"], trade_date, trade_date, row["amount"]),
                    )
                    stats["seat_details"] += 1

            for code, rows in grouped.items():
                buy_amount = sum(row["amount"] for row in rows if row["direction"] == "买")
                sell_amount = sum(row["amount"] for row in rows if row["direction"] == "卖")
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO daily_summaries
                    (date, stock_code, stock_name, listing_reason, total_buy, total_sell, net_amount, buy_seat_count, sell_seat_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trade_date,
                        code,
                        rows[0]["stock_name"],
                        "",
                        buy_amount,
                        sell_amount,
                        buy_amount - sell_amount,
                        len({row["seat_name"] for row in rows if row["direction"] == "买"}),
                        len({row["seat_name"] for row in rows if row["direction"] == "卖"}),
                    ),
                )
                stats["summaries"] += 1
        conn.commit()
    return stats


def _graph_snapshots(start: str | None, end: str | None) -> dict[tuple[str, str], dict]:
    snapshots: dict[tuple[str, str], dict] = {}
    for path in _dragon_paths(start, end):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        graphs = payload.get("graphs") or {}
        if not isinstance(graphs, dict):
            continue
        for fallback_type, section in graphs.items():
            if not isinstance(section, dict):
                continue
            snapshot = section.get("snapshot")
            if not isinstance(snapshot, dict):
                continue
            snapshot_date = _parse_date(str(snapshot.get("snapshot_date") or section.get("summary", {}).get("snapshot_date") or ""))
            snapshot_type = str(snapshot.get("snapshot_type") or fallback_type or "").strip()
            if not snapshot_date or not snapshot_type or not _date_in_range(snapshot_date, start, end):
                continue
            snapshots[(snapshot_date, snapshot_type)] = snapshot
    return snapshots


def backfill_graphs(start: str | None, end: str | None, dry_run: bool) -> dict[str, int]:
    snapshots = _graph_snapshots(start, end)
    stats = {
        "snapshots": len(snapshots),
        "nodes": sum(len(snapshot.get("nodes") or []) for snapshot in snapshots.values()),
        "edges": sum(len(snapshot.get("edges") or []) for snapshot in snapshots.values()),
    }
    if dry_run:
        return stats

    with get_connection() as conn:
        cursor = conn.cursor()
        for (snapshot_date, snapshot_type), snapshot in sorted(snapshots.items()):
            version = str(snapshot.get("version") or "v1")
            metadata = snapshot.get("metadata") or {}
            cursor.execute(
                """
                INSERT OR REPLACE INTO graph_snapshots
                (snapshot_date, snapshot_type, version, metadata_json)
                VALUES (?, ?, ?, ?)
                """,
                (snapshot_date, snapshot_type, version, json.dumps(metadata, ensure_ascii=False, default=str)),
            )
            cursor.execute(
                "DELETE FROM graph_edges WHERE snapshot_type = ? AND trade_date = ?",
                (snapshot_type, snapshot_date),
            )
            for node in snapshot.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("node_id") or "")
                if not node_id:
                    continue
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO graph_nodes
                    (node_id, node_type, node_key, node_name, attributes_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        node_id,
                        str(node.get("node_type") or ""),
                        str(node.get("node_key") or ""),
                        str(node.get("node_name") or ""),
                        json.dumps(node.get("attributes") or {}, ensure_ascii=False, default=str),
                    ),
                )
            for edge in snapshot.get("edges") or []:
                if not isinstance(edge, dict):
                    continue
                source = str(edge.get("source_node_id") or "")
                target = str(edge.get("target_node_id") or "")
                edge_type = str(edge.get("edge_type") or "")
                if not source or not target or not edge_type:
                    continue
                cursor.execute(
                    """
                    INSERT INTO graph_edges
                    (source_node_id, target_node_id, edge_type, weight, trade_date, snapshot_type, attributes_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source,
                        target,
                        edge_type,
                        _as_float(edge.get("weight")) or 0.0,
                        _parse_date(str(edge.get("trade_date") or snapshot_date)) or snapshot_date,
                        snapshot_type,
                        json.dumps(edge.get("attributes") or {}, ensure_ascii=False, default=str),
                    ),
                )
        conn.commit()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline backfill database from existing StockGraph JSON files.")
    parser.add_argument("--start-date", help="Start date, YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--end-date", help="End date, YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--areas", default="all", help="Comma-separated areas: dragon_tiger,market_overview,graphs; or all")
    parser.add_argument("--dry-run", action="store_true", help="Only report rows that would be imported")
    args = parser.parse_args()

    start = _parse_date(args.start_date)
    end = _parse_date(args.end_date)
    if start and end and start > end:
        raise ValueError("start date must be earlier than or equal to end date")
    areas = _parse_areas(args.areas)

    ensure_runtime_dirs()
    if not args.dry_run:
        with get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    if "market_overview" in areas:
        stats = backfill_market_overview(start, end, args.dry_run)
        print(
            "[stockgraph] market_overview json backfill: "
            f"stock_rows={stats['stock_rows']} hot_rows={stats['hot_rows']} industry_rows={stats['industry_rows']}"
        )
    if "dragon_tiger" in areas:
        stats = backfill_dragon_tiger(start, end, args.dry_run)
        print(
            "[stockgraph] dragon_tiger json backfill: "
            f"operations={stats['operations']} summaries={stats['summaries']} seat_details={stats['seat_details']}"
        )
    if "graphs" in areas:
        stats = backfill_graphs(start, end, args.dry_run)
        print(
            "[stockgraph] graph json backfill: "
            f"snapshots={stats['snapshots']} nodes={stats['nodes']} edges={stats['edges']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
