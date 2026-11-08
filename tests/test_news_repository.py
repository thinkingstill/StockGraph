"""新闻仓储批量查询测试。

回归点：前端构建曾对每只有新闻的股票各调一次 `query_news_by_stock`，
该方法是「实体 JOIN + metadata_json LIKE 全表扫描」两次查询。
新闻从 246 条涨到 33 万条后，6000+ 只股票直接把构建拖到 30 分钟跑不完。
"""

from __future__ import annotations

import sqlite3

import pytest

from stockgraph.infrastructure.db.connection import get_connection
from stockgraph.infrastructure.db.repositories import NewsRepository
from stockgraph.infrastructure.db.schema import SCHEMA_SQL


@pytest.fixture()
def repo(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKGRAPH_DB_PATH", str(tmp_path / "news.db"))
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
    return NewsRepository()


def add_article(repo, title: str, published_at: str, codes: list[str]) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO news_articles (source, title, content, summary, published_at, url, hash, sentiment, event_type)
            VALUES (?, ?, '', '', ?, '', ?, '中性', '其他')
            """,
            ("test", title, published_at, f"h-{title}-{published_at}"),
        )
        article_id = cur.lastrowid
        for code in codes:
            cur.execute(
                "INSERT INTO news_entities (article_id, entity_type, entity_code, entity_name, confidence) "
                "VALUES (?, 'stock', ?, ?, 1.0)",
                (article_id, code, code),
            )
        conn.commit()
        return article_id


def test_grouped_query_limits_per_stock(repo):
    for i in range(5):
        add_article(repo, f"茅台新闻{i}", f"2026-01-0{i + 1} 10:00:00", ["600519"])
    for i in range(3):
        add_article(repo, f"平安新闻{i}", f"2026-02-0{i + 1} 10:00:00", ["000001"])

    grouped = repo.query_news_grouped_by_stock(limit_per_stock=2)
    assert set(grouped) == {"600519", "000001"}
    assert len(grouped["600519"]) == 2
    assert len(grouped["000001"]) == 2


def test_grouped_query_orders_by_published_desc(repo):
    add_article(repo, "旧闻", "2026-01-01 09:00:00", ["600519"])
    add_article(repo, "新闻", "2026-06-01 09:00:00", ["600519"])
    add_article(repo, "中间", "2026-03-01 09:00:00", ["600519"])

    grouped = repo.query_news_grouped_by_stock(limit_per_stock=2)
    titles = [item["title"] for item in grouped["600519"]]
    assert titles == ["新闻", "中间"]  # 只取最近两条，且倒序


def test_grouped_query_respects_max_stocks(repo):
    for code in ["600519", "000001", "300750", "600000"]:
        for i in range(code.count("0") + 1):
            add_article(repo, f"{code}-{i}", f"2026-01-0{i + 1} 10:00:00", [code])

    grouped = repo.query_news_grouped_by_stock(limit_per_stock=5, max_stocks=2)
    assert len(grouped) == 2
    # 新闻多的股票优先保留
    assert all(len(v) >= 2 for v in grouped.values())


def test_grouped_query_returns_article_fields(repo):
    add_article(repo, "贵州茅台发布三季报", "2026-10-30 18:36:28", ["600519"])
    article = repo.query_news_grouped_by_stock(limit_per_stock=1)["600519"][0]
    for field in ("stock_code", "title", "published_at", "sentiment", "event_type"):
        assert field in article
    assert article["stock_code"] == "600519"


def test_grouped_query_empty_database(repo):
    assert repo.query_news_grouped_by_stock() == {}


def test_grouped_query_is_one_roundtrip(repo):
    """必须只用一次 SQL —— 这是性能修复的核心。"""
    for i in range(50):
        add_article(repo, f"n{i}", f"2026-01-01 10:{i:02d}:00", [f"60000{i % 10}"])

    calls: list[str] = []
    import stockgraph.infrastructure.db.repositories as module

    original = module.get_connection

    def counting_connection():
        calls.append("x")
        return original()

    module.get_connection = counting_connection
    try:
        repo.query_news_grouped_by_stock(limit_per_stock=5)
    finally:
        module.get_connection = original

    assert len(calls) == 1, f"期望 1 次连接/查询，实际 {len(calls)} 次（N+1 回归）"
