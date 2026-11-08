"""数据库连接与并发配置测试。

回归点：原实现用默认 `delete` 日志模式，写事务独占整库。
在跑 609 张图快照回补的同时采集新闻，直接抛 `database is locked` 中断。
"""

from __future__ import annotations

import pytest

from stockgraph.infrastructure.db.connection import DEFAULT_BUSY_TIMEOUT, database_path, get_connection


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKGRAPH_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("STOCKGRAPH_SQLITE_WAL", raising=False)
    yield tmp_path


def test_database_path_honours_env_override(isolated_db):
    assert database_path() == isolated_db / "t.db"


def test_creates_parent_directory(monkeypatch, tmp_path):
    nested = tmp_path / "a" / "b" / "x.db"
    monkeypatch.setenv("STOCKGRAPH_DB_PATH", str(nested))
    assert database_path().parent.is_dir()


def test_wal_mode_enabled_by_default():
    with get_connection() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_busy_timeout_configured():
    with get_connection() as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == int(DEFAULT_BUSY_TIMEOUT * 1000)


def test_wal_can_be_disabled_via_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKGRAPH_DB_PATH", str(tmp_path / "nowal.db"))
    monkeypatch.setenv("STOCKGRAPH_SQLITE_WAL", "0")
    with get_connection() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal"


def test_read_works_while_write_transaction_open():
    """WAL 的核心收益：写事务未提交时，另一个连接仍能读。"""
    with get_connection() as writer:
        writer.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        writer.execute("INSERT INTO t (v) VALUES ('x')")
        writer.commit()
        writer.execute("BEGIN")
        writer.execute("INSERT INTO t (v) VALUES ('y')")

        with get_connection() as reader:
            count = reader.execute("SELECT COUNT(*) FROM t").fetchone()[0]
            assert count == 1  # 看得到已提交的那条，不被写锁挡住

        writer.rollback()
