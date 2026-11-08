"""生成 2026 年数据回补核验报告。

输出 `data/shared_state/data_completeness_<date>.json`，可直接用于回答
「2026 年的数据到底全不全」这类问题，而不是靠肉眼看日志。

用法：
    python scripts/report_completeness.py
    python scripts/report_completeness.py --start 2026-01-01 --end 2026-11-06
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core import configure_logging  # noqa: E402
from stockgraph.core.paths import SHARED_STATE_DIR  # noqa: E402
from stockgraph.infrastructure.db.connection import get_connection  # noqa: E402


def parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"无法解析日期: {value}")


def scalar(conn, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def build_report(start: date, end: date) -> dict:
    s, e = start.isoformat(), end.isoformat()
    with get_connection() as conn:
        # ---- 行情：以 market_daily_snapshots 的交易日作为「应有交易日」基准
        market_days = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT trade_date FROM market_daily_snapshots "
                "WHERE trade_date BETWEEN ? AND ? ORDER BY trade_date",
                (s, e),
            )
        ]
        market_rows = scalar(
            conn,
            "SELECT COUNT(*) FROM market_daily_snapshots WHERE trade_date BETWEEN ? AND ?",
            (s, e),
        )
        market_stocks = scalar(
            conn,
            "SELECT COUNT(DISTINCT stock_code) FROM market_daily_snapshots WHERE trade_date BETWEEN ? AND ?",
            (s, e),
        )
        per_day = dict(
            conn.execute(
                "SELECT trade_date, COUNT(*) FROM market_daily_snapshots "
                "WHERE trade_date BETWEEN ? AND ? GROUP BY trade_date ORDER BY trade_date",
                (s, e),
            ).fetchall()
        )

        # ---- 龙虎榜
        dt_days = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT date FROM daily_summaries WHERE date BETWEEN ? AND ?", (s, e)
            )
        }
        dt_rows = scalar(
            conn, "SELECT COUNT(*) FROM daily_summaries WHERE date BETWEEN ? AND ?", (s, e)
        )
        seat_rows = scalar(
            conn,
            "SELECT COUNT(*) FROM stock_seat_operations WHERE date BETWEEN ? AND ?",
            (s, e),
        )
        dt_stocks = scalar(
            conn,
            "SELECT COUNT(DISTINCT stock_code) FROM daily_summaries WHERE date BETWEEN ? AND ?",
            (s, e),
        )

        # ---- 图快照
        graph_snapshots = scalar(
            conn,
            "SELECT COUNT(*) FROM graph_snapshots WHERE snapshot_date BETWEEN ? AND ?",
            (s, e),
        )
        graph_by_type = dict(
            conn.execute(
                "SELECT snapshot_type, COUNT(*) FROM graph_snapshots "
                "WHERE snapshot_date BETWEEN ? AND ? GROUP BY snapshot_type",
                (s, e),
            ).fetchall()
        )
        graph_nodes = scalar(conn, "SELECT COUNT(*) FROM graph_nodes")
        graph_edges = scalar(conn, "SELECT COUNT(*) FROM graph_edges")
        self_loops = scalar(
            conn, "SELECT COUNT(*) FROM graph_edges WHERE source_node_id = target_node_id"
        )

        # ---- 新闻
        news_total = scalar(conn, "SELECT COUNT(*) FROM news_articles")
        news_in_range = scalar(
            conn,
            "SELECT COUNT(*) FROM news_articles WHERE substr(published_at,1,10) BETWEEN ? AND ?",
            (s, e),
        )
        news_by_source = dict(
            conn.execute(
                "SELECT source, COUNT(*) FROM news_articles GROUP BY source ORDER BY 2 DESC"
            ).fetchall()
        )
        news_by_month = dict(
            conn.execute(
                "SELECT substr(published_at,1,7) AS m, COUNT(*) FROM news_articles "
                "WHERE published_at != '' GROUP BY m ORDER BY m"
            ).fetchall()
        )
        news_entities = scalar(conn, "SELECT COUNT(*) FROM news_entities")
        news_range = conn.execute(
            "SELECT MIN(published_at), MAX(published_at) FROM news_articles WHERE published_at != ''"
        ).fetchone()

        # 新闻回补是否完成：最早一篇已经早于目标起始日，说明该区间已翻到底
        news_earliest = str(news_range[0] or "") if news_range else ""
        news_complete = bool(news_earliest) and news_earliest[:10] <= s

    missing_dt = sorted(set(market_days) - dt_days)
    coverage = {
        "market_trading_days": len(market_days),
        "dragon_tiger_days": len(dt_days),
        "dragon_tiger_missing_days": missing_dt,
        "dragon_tiger_coverage_pct": round(len(dt_days & set(market_days)) / len(market_days) * 100, 2)
        if market_days
        else 0.0,
        "graph_snapshot_coverage_pct": round(
            graph_by_type.get("seat_stock", 0) / len(market_days) * 100, 2
        )
        if market_days
        else 0.0,
    }

    return {
        "range": {"start": s, "end": e},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "market": {
            "trading_days": len(market_days),
            "rows": market_rows,
            "stocks": market_stocks,
            "first_day": market_days[0] if market_days else None,
            "last_day": market_days[-1] if market_days else None,
            "stocks_per_day_min": min(per_day.values()) if per_day else 0,
            "stocks_per_day_max": max(per_day.values()) if per_day else 0,
            "source": "sina_kline",
            "amount_estimated": True,
            "hot_data_available": False,
        },
        "dragon_tiger": {
            "days": len(dt_days),
            "summaries": dt_rows,
            "seat_operations": seat_rows,
            "stocks": dt_stocks,
        },
        "graph": {
            "snapshots": graph_snapshots,
            "by_type": graph_by_type,
            "nodes": graph_nodes,
            "edges": graph_edges,
            "self_loop_edges": self_loops,
        },
        "news": {
            "total": news_total,
            "in_range": news_in_range,
            "by_source": news_by_source,
            "by_month": news_by_month,
            "entities": news_entities,
            "earliest": news_range[0] if news_range else None,
            "latest": news_range[1] if news_range else None,
            "backfill_complete": news_complete,
            "coverage_note": f"最早一篇 {news_earliest[:10]}，目标起始 {s}，已{'覆盖' if news_complete else '未覆盖'}目标区间",
        },
        "coverage": coverage,
        "notes": [
            "行情成交额由 成交量×(最高+最低+收盘)/3 估算，字段 amount_estimated=true 已标注",
            "雪球热度接口按 IP 封锁，历史热度无法回补，未做任何伪造",
            "dragon_tiger_missing_days 为空表示龙虎榜已覆盖全部行情交易日",
            "self_loop_edges 必须为 0：自环在 Cypher 中是零长度路径，会让两个图后端边数不一致",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成数据完整性报告")
    parser.add_argument("--start", type=parse_date, default=date(2026, 1, 1))
    parser.add_argument("--end", type=parse_date, default=date.today())
    args = parser.parse_args()

    configure_logging()
    report = build_report(args.start, args.end)
    target = SHARED_STATE_DIR / f"data_completeness_{date.today().isoformat()}.json"
    SHARED_STATE_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告已写入: {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
