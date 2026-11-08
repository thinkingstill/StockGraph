"""图后端工厂：全项目唯一的图存储入口。"""

from __future__ import annotations

import logging
from typing import Any

from stockgraph.infrastructure.graph.base import GraphStore, GraphStoreError
from stockgraph.infrastructure.graph.config import GraphSettings, resolve_settings
from stockgraph.infrastructure.graph.falkordb_store import FalkorDBGraphStore
from stockgraph.infrastructure.graph.sqlite_store import SqliteGraphStore

logger = logging.getLogger(__name__)

_CACHE: dict[str, GraphStore] = {}


def build_sqlite_store(graph_name: str = "stockgraph") -> SqliteGraphStore:
    return SqliteGraphStore(graph_name=graph_name)


def build_falkordb_store(settings: GraphSettings) -> FalkorDBGraphStore:
    cfg = settings.falkordb
    return FalkorDBGraphStore(
        host=cfg.get("host", "127.0.0.1"),
        port=int(cfg.get("port", 6379)),
        graph_name=cfg.get("graph_name", "stockgraph"),
        username=cfg.get("username") or None,
        password=cfg.get("password") or None,
        timeout=float(cfg.get("timeout", 5)),
    )


def create_graph_store(
    backend: str | None = None,
    *,
    settings: GraphSettings | None = None,
    use_cache: bool = True,
) -> GraphStore:
    """按配置创建图存储。

    - backend 显式传入时覆盖配置；
    - `auto` 先试 FalkorDB，失败后回退 SQLite；
    - `falkordb` 在 `fallback_to_sqlite=True` 时同样会回退，避免整个数据链路被图库拖垮。
    """
    settings = settings or resolve_settings()
    target = (backend or settings.backend or "sqlite").strip().lower()

    if target in {"auto"}:
        target = "falkordb" if _falkordb_ready(settings) else "sqlite"

    if target == "sqlite":
        cache_key = f"sqlite:{settings.falkordb.get('graph_name', 'stockgraph')}"
        if use_cache and cache_key in _CACHE:
            return _CACHE[cache_key]
        store: GraphStore = build_sqlite_store(settings.falkordb.get("graph_name", "stockgraph"))
        if use_cache:
            _CACHE[cache_key] = store
        return store

    if target == "falkordb":
        cache_key = "falkordb:" + str(settings.falkordb)
        if use_cache and cache_key in _CACHE:
            return _CACHE[cache_key]
        store = build_falkordb_store(settings)
        try:
            store.initialize()
        except GraphStoreError as exc:
            if not settings.fallback_to_sqlite:
                raise
            logger.warning("FalkorDB 不可用（%s），已回退到 SQLite 图后端", exc)
            return create_graph_store("sqlite", settings=settings, use_cache=use_cache)
        if use_cache:
            _CACHE[cache_key] = store
        return store

    raise ValueError(f"未知图后端: {target}")


def _falkordb_ready(settings: GraphSettings) -> bool:
    try:
        store = build_falkordb_store(settings)
        return bool(store.health().get("ok"))
    except Exception:  # noqa: BLE001
        return False


def backend_status() -> dict[str, Any]:
    """给 CLI / API 用的整体状态。"""
    settings = resolve_settings()
    active = create_graph_store(settings=settings)
    status: dict[str, Any] = {
        "settings": settings.as_dict(),
        "active_backend": active.backend,
        "requested_backend": settings.backend,
        "fallback_triggered": settings.backend != active.backend,
        "active": _safe(lambda: active.health()),
        "candidates": {},
    }
    status["candidates"]["sqlite"] = _safe(lambda: build_sqlite_store().health())
    status["candidates"]["falkordb"] = _safe(lambda: build_falkordb_store(settings).health())
    return status


def reset_cache() -> None:
    _CACHE.clear()


def _safe(func) -> dict[str, Any]:
    try:
        return func()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
