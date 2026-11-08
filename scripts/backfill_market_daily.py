#!/usr/bin/env python3
"""回补 2026 年全 A 日行情快照。

背景：项目原始实现只依赖东方财富 `push2` 实时快照，一旦该接口被限流/封禁
（本机实测即为空响应），历史行情完全无法回补，且没有备用源。
这里改用新浪历史 K 线接口 `getKLineData` 逐股拉取日线，再按交易日聚合。

口径说明（会同时写进报告）：
- 开高低收、成交量来自新浪日线；
- 新浪日线不含成交额，`成交额` 用 `成交量 × (最高+最低+收盘)/3` 估算，字段 `成交额估算=true`；
- 雪球热度接口按 IP 封锁（403），历史热度无法回补，`hot_daily_*` 不做伪造。

用法：
    python scripts/backfill_market_daily.py --start 20260101 --end 20261107
    python scripts/backfill_market_daily.py --emit-json          # 从库导出每日 JSON
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core import configure_logging  # noqa: E402
from stockgraph.core.paths import MARKET_DATA_DIR, REFERENCE_DATA_DIR, SHARED_STATE_DIR  # noqa: E402
from stockgraph.infrastructure.db.connection import database_path, get_connection  # noqa: E402
from stockgraph.infrastructure.db.schema import SCHEMA_SQL  # noqa: E402

logger = logging.getLogger("backfill.market")

SINA_KLINE = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.sina.com.cn/",
}


def parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"无法解析日期: {value}")


def sina_symbol(code: str) -> str:
    if code.startswith(("60", "68", "51", "58")):
        return f"sh{code}"
    if code.startswith(("00", "30", "12", "15")):
        return f"sz{code}"
    return f"bj{code}"


def fetch_kline(symbol: str, datalen: int, session) -> list[dict]:
    response = session.get(
        SINA_KLINE,
        params={"symbol": symbol, "scale": 240, "ma": "no", "datalen": datalen},
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    text = response.text.strip()
    if not text or text in {"null", "[]"}:
        return []
    try:
        return json.loads(text)
    except ValueError:
        return []


def load_industry() -> dict[str, str]:
    path = REFERENCE_DATA_DIR / "industry_mapping.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="回补 2026 年全 A 日行情")
    parser.add_argument("--start", type=parse_date, default=date(2026, 1, 1))
    parser.add_argument("--end", type=parse_date, default=date.today())
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.15, help="每个请求前的间隔（线程内）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 只股票，调试用")
    parser.add_argument("--emit-json", action="store_true", help="只从数据库导出每日 JSON，不联网")
    args = parser.parse_args()

    configure_logging()
    if args.emit_json:
        return emit_json(args.start, args.end)

    codes_path = REFERENCE_DATA_DIR / "all_stock_codes.json"
    codes: dict[str, str] = json.loads(codes_path.read_text(encoding="utf-8"))
    if args.limit:
        codes = dict(list(codes.items())[: args.limit])

    industry = load_industry()
    start, end = args.start, args.end
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        done = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT stock_code FROM market_daily_snapshots WHERE trade_date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            )
        }
    pending = [(code, name) for code, name in codes.items() if code not in done]
    logger.info("待回补股票 %d 只（已完成 %d 只）", len(pending), len(done))

    import requests

    session = requests.Session()
    rows_buffer: list[tuple] = []
    total_rows = 0
    failed: list[str] = []
    datalen = 300

    def work(item):
        code, name = item
        if args.sleep:
            time.sleep(args.sleep)
        try:
            series = fetch_kline(sina_symbol(code), datalen, session)
        except Exception as exc:  # noqa: BLE001
            return code, name, [], str(exc)

        records = []
        prev_close = None
        for bar in series:
            day = str(bar.get("day") or "")[:10]
            try:
                close = float(bar.get("close") or 0)
                high = float(bar.get("high") or close)
                low = float(bar.get("low") or close)
                open_price = float(bar.get("open") or close)
                volume = float(bar.get("volume") or 0)
            except (TypeError, ValueError):
                continue
            if not (start.isoformat() <= day <= end.isoformat()):
                prev_close = close or prev_close
                continue
            change_pct = round((close / prev_close - 1) * 100, 2) if prev_close else None
            amount = round(volume * ((high + low + close) / 3), 2) if volume else None
            records.append(
                (
                    day,
                    code,
                    name,
                    close,
                    change_pct,
                    industry.get(code, ""),
                    json.dumps(
                        {
                            "代码": code,
                            "名称": name,
                            "最新价": close,
                            "涨跌额": round(close - prev_close, 3) if prev_close else None,
                            "涨跌幅": change_pct,
                            "今开": open_price,
                            "最高": high,
                            "最低": low,
                            "昨收": prev_close,
                            "成交量": volume,
                            "成交额": amount,
                            "成交额估算": True,
                            "date": day.replace("-", ""),
                            "行业": industry.get(code, ""),
                            "数据源": "sina_kline",
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            prev_close = close
        return code, name, records, ""

    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(work, item): item for item in pending}
        for index, future in enumerate(as_completed(futures), 1):
            code, name, records, error = future.result()
            if error:
                failed.append(f"{code}:{error[:80]}")
            if records:
                rows_buffer.extend(records)
                total_rows += len(records)
            if index % 200 == 0 or index == len(pending):
                flush(rows_buffer)
                rows_buffer.clear()
                logger.info(
                    "进度 %d/%d 股票，累计写入 %d 行，失败 %d 只",
                    index,
                    len(pending),
                    total_rows,
                    len(failed),
                )

    flush(rows_buffer)
    report = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "stocks_total": len(codes),
        "stocks_done_before": len(done),
        "stocks_processed": len(pending),
        "rows_written": total_rows,
        "failed": failed[:200],
        "failed_count": len(failed),
        "amount_estimated": True,
        "hot_data_available": False,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    report_path = SHARED_STATE_DIR / f"backfill_market_{start.isoformat()}_{end.isoformat()}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("行情回补完成: %s", report_path)
    return emit_json(start, end)


def flush(rows: list[tuple]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO market_daily_snapshots
            (trade_date, stock_code, stock_name, latest_price, change_pct, industry, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def emit_json(start: date, end: date) -> int:
    """把库里的日行情导出成前端直接消费的 stock_daily_YYYYMMDD.json。"""
    with get_connection() as conn:
        days = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT trade_date FROM market_daily_snapshots WHERE trade_date BETWEEN ? AND ? ORDER BY trade_date",
                (start.isoformat(), end.isoformat()),
            )
        ]
    logger.info("导出 %d 个交易日的行情 JSON", len(days))
    for day in days:
        compact = day.replace("-", "")
        target = MARKET_DATA_DIR / f"stock_daily_{compact}.json"
        if target.exists() and target.stat().st_size > 1024:
            continue
        with get_connection() as conn:
            payload = [json.loads(row[0]) for row in conn.execute(
                "SELECT raw_json FROM market_daily_snapshots WHERE trade_date = ? ORDER BY stock_code",
                (day,),
            )]
        if not payload:
            continue
        MARKET_DATA_DIR.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
