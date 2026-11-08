"""SQLite 连接管理。

并发策略：默认开启 WAL（`journal_mode=WAL`）+ 5 秒 busy timeout。
原实现用默认的 `delete` 日志模式，写事务会独占整库，回补行情/图快照时
新闻采集必然撞上 `database is locked`（实测在跑满 609 张图快照时直接中断）。
WAL 允许「一写多读」，busy timeout 让偶发的写-写冲突自己等待而不是立刻抛错。
"""

import os
import sqlite3
from pathlib import Path

from stockgraph.core.paths import SHARED_STATE_DIR, ensure_runtime_dirs

DEFAULT_BUSY_TIMEOUT = 10.0


def database_path() -> Path:
    """数据库路径。

    默认 `data/shared_state/dragon_tiger.db`；设置 `STOCKGRAPH_DB_PATH` 可覆盖，
    便于测试与多实例部署（原实现写死路径，测试之间会互相污染）。
    """
    override = os.environ.get("STOCKGRAPH_DB_PATH", "").strip()
    if override:
        path = Path(override).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    ensure_runtime_dirs()
    return SHARED_STATE_DIR / "dragon_tiger.db"


def get_connection() -> sqlite3.Connection:
    path = database_path()
    conn = sqlite3.connect(path, timeout=DEFAULT_BUSY_TIMEOUT)
    conn.row_factory = sqlite3.Row
    # WAL 是持久化到数据库文件头的，设置一次即可；但只读库上可能失败，忽略即可
    if os.environ.get("STOCKGRAPH_SQLITE_WAL", "1") not in {"0", "false", "False"}:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            pass
    conn.execute(f"PRAGMA busy_timeout={int(DEFAULT_BUSY_TIMEOUT * 1000)}")
    return conn
