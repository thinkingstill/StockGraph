import sqlite3
from pathlib import Path

from stockgraph.core.paths import SHARED_STATE_DIR, ensure_runtime_dirs


def database_path() -> Path:
    ensure_runtime_dirs()
    return SHARED_STATE_DIR / "dragon_tiger.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(database_path())
    conn.row_factory = sqlite3.Row
    return conn
