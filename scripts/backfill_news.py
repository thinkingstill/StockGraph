#!/usr/bin/env python3
"""回补 2026 年新闻数据。

三个来源互补，都是真实接口（不含任何编造数据）：

1. `cls`       财联社电报，可沿 `last_time` 游标一直往前翻，适合大面积覆盖全年；
2. `eastmoney` 东方财富 7×24 快讯，沿 `sortEnd` 游标回翻；
3. `stock`     东方财富个股新闻搜索，按「2026 年上过龙虎榜的股票」逐只补齐。

断点续传：`cls` / `eastmoney` 会从库里该来源最早一篇的发布时间继续往前翻，
中断后重跑不会从头开始。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core import configure_logging  # noqa: E402
from stockgraph.core.paths import SHARED_STATE_DIR  # noqa: E402
from stockgraph.domain.news import link_article_entities, normalize_news_article  # noqa: E402
from stockgraph.infrastructure.data_sources.news.cls import CLSNewsSource  # noqa: E402
from stockgraph.infrastructure.data_sources.news.eastmoney import EastMoneyNewsSource  # noqa: E402
from stockgraph.infrastructure.data_sources.news.eastmoney_search import (  # noqa: E402
    EastMoneyStockNewsSource,
)
from stockgraph.infrastructure.db.connection import get_connection  # noqa: E402
from stockgraph.infrastructure.db.repositories import NewsRepository  # noqa: E402

logger = logging.getLogger("backfill.news")


def parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"无法解析日期: {value}")


def earliest_published_at(source: str) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MIN(published_at) FROM news_articles WHERE source = ? AND published_at != ''",
            (source,),
        ).fetchone()
    return str(row[0] or "") if row else ""


# 两个源的游标单位不同：财联社 `last_time` 是秒，东财 `sortEnd` 是微秒。
# 这里统一「把库里最早一篇的发布时间反推成游标」，实现真正的断点续传。
CURSOR_SCALE = {"cls": 1, "eastmoney": 1_000_000}


def resume_cursor(source_name: str) -> str:
    """从库里该来源最早一篇的发布时间反推出游标。

    没有游标续传时，每次中断重启都要从最新一口气翻几千页才能回到断点，
    实测白跑约 12 分钟/960 页；`inserted == 0` 的早退逻辑还会让重跑直接
    在第 4 页判定「已覆盖」而退出，等于永远补不完历史。
    """
    earliest = earliest_published_at(
        "财联社电报" if source_name == "cls" else "东方财富快讯"
    )
    if not earliest:
        return ""
    try:
        stamp = int(datetime.strptime(earliest, "%Y-%m-%d %H:%M:%S").timestamp())
    except ValueError:
        logger.warning("%s 最早时间无法解析: %s，从头开始翻", source_name, earliest)
        return ""
    # 加 1 个单位：游标语义是「取该时刻之前的数据」，加一点确保不漏掉同一秒的其它文章
    return str(stamp * CURSOR_SCALE[source_name] + 1)


def count_news() -> dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
        by_year = conn.execute(
            "SELECT substr(published_at, 1, 4) AS y, COUNT(*) FROM news_articles "
            "WHERE published_at != '' GROUP BY y ORDER BY y"
        ).fetchall()
        linked = conn.execute("SELECT COUNT(*) FROM news_entities").fetchone()[0]
    return {
        "total": int(total or 0),
        "entities": int(linked or 0),
        "by_year": {row[0]: int(row[1]) for row in by_year},
    }


def save(batch, repository: NewsRepository) -> int:
    normalized = []
    for article in batch.articles:
        normalised = normalize_news_article(article)
        normalized.append(link_article_entities(normalised))
    batch.articles = normalized
    return repository.save_batch(batch)


def run_stream(
    source_name: str, start: date, sleep: float, max_pages: int, page_limit: int = 0
) -> dict:
    repository = NewsRepository()
    repository.initialize_database()
    source = CLSNewsSource() if source_name == "cls" else EastMoneyNewsSource()

    # 单次请求条数：东财实测上限 200 条（再大也只返回 200），财联社上限 50 条。
    # 默认 0 表示用各源自带页大小，调大能显著减少往返次数。
    if page_limit <= 0:
        page_limit = 200 if source_name == "eastmoney" else 50
    if source_name == "eastmoney":
        source.page_size = page_limit
    else:
        source.page_size = min(page_limit, 50)

    cursor = resume_cursor(source_name)
    if cursor:
        source.set_cursor(cursor)
        logger.info("%s 断点续传: 游标 %s（从库里最早一篇继续往前翻）", source_name, cursor)
    else:
        logger.info("%s 无历史数据，从最新开始翻", source_name)

    insert_total = 0
    pages = 0
    reached = False
    stale_pages = 0
    while pages < max_pages and not reached:
        pages += 1
        batch = source.fetch(limit=page_limit)
        if not batch.articles:
            logger.warning("%s 第 %d 页无数据，结束", source_name, pages)
            break
        earliest = min((a.published_at for a in batch.articles if a.published_at), default="")
        inserted = save(batch, repository)
        insert_total += inserted
        logger.info(
            "%s 第 %d 页: 拿到 %d 条（新增 %d），最早 %s",
            source_name,
            pages,
            len(batch.articles),
            inserted,
            earliest,
        )
        if earliest and earliest[:10] < start.isoformat():
            reached = True
        time.sleep(max(0.0, sleep))
        # 有游标续传后，「本页无新增」只说明这一页重复，不代表已覆盖历史，
        # 必须连续多页都无新增才认为真的到头了（阈值放大到 30 页）
        stale_pages = stale_pages + 1 if inserted == 0 else 0
        if stale_pages >= 30:
            logger.info("%s 连续 %d 页无新增，判定已覆盖，结束", source_name, stale_pages)
            break
    return {"source": source_name, "pages": pages, "inserted": insert_total, "reached_start": reached}


def run_stock(start: date, sleep: float, pages_per_stock: int, limit_stocks: int) -> dict:
    repository = NewsRepository()
    repository.initialize_database()

    codes: list[str] = []
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT stock_code, COUNT(*) AS cnt FROM stock_seat_operations
            WHERE date BETWEEN ? AND ? GROUP BY stock_code ORDER BY cnt DESC
            """,
            (start.isoformat(), date.today().isoformat()),
        ).fetchall()
        codes = [row[0] for row in rows]
    if limit_stocks:
        codes = codes[:limit_stocks]
    logger.info("个股新闻回补: %d 只股票", len(codes))

    source = EastMoneyStockNewsSource()
    insert_total = 0
    for index, code in enumerate(codes, 1):
        try:
            batch = source.fetch_for_stock(code, pages=pages_per_stock)
        except Exception:  # noqa: BLE001
            logger.warning("个股新闻失败: %s", code, exc_info=True)
            continue
        if not batch.articles:
            continue
        aged = [a for a in batch.articles if a.published_at and a.published_at[:10] >= start.isoformat()]
        batch.articles = aged or batch.articles
        insert_total += save(batch, repository)
        if index % 50 == 0:
            logger.info("个股新闻进度 %d/%d，累计新增 %d", index, len(codes), insert_total)
        time.sleep(max(0.0, sleep))
    return {"source": "stock", "stocks": len(codes), "inserted": insert_total}


def main() -> int:
    parser = argparse.ArgumentParser(description="回补 2026 年新闻")
    parser.add_argument("--source", choices=["cls", "eastmoney", "stock", "all"], default="all")
    parser.add_argument("--start", type=parse_date, default=date(2026, 1, 1))
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--max-pages", type=int, default=4000)
    parser.add_argument(
        "--page-limit",
        type=int,
        default=0,
        help="单次请求条数；0=用各源上限（东财 200、财联社 50）。调大能减少往返次数",
    )
    parser.add_argument("--pages-per-stock", type=int, default=3)
    parser.add_argument("--limit-stocks", type=int, default=0)
    args = parser.parse_args()

    configure_logging()
    result: dict = {"start": args.start.isoformat(), "results": []}

    if args.source in {"cls", "all"}:
        result["results"].append(
            run_stream("cls", args.start, args.sleep, args.max_pages, args.page_limit)
        )
    if args.source in {"eastmoney", "all"}:
        result["results"].append(
            run_stream("eastmoney", args.start, args.sleep, args.max_pages, args.page_limit)
        )
    if args.source in {"stock", "all"}:
        result["results"].append(run_stock(args.start, args.sleep, args.pages_per_stock, args.limit_stocks))

    result["stats"] = count_news()
    result["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report_path = SHARED_STATE_DIR / f"backfill_news_{args.start.isoformat()}.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("新闻回补完成: %s", result["stats"])
    logger.info("报告: %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
