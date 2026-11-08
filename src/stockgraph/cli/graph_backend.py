import argparse
import json
import logging

from stockgraph.core import configure_logging
from stockgraph.infrastructure.graph import (
    SUPPORTED_BACKENDS,
    backend_status,
    build_falkordb_store,
    build_sqlite_store,
    create_graph_store,
    reset_cache,
    resolve_settings,
    switch_backend,
)

logger = logging.getLogger(__name__)


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cmd_status(_args: argparse.Namespace) -> int:
    _print(backend_status())
    return 0


def _cmd_ping(args: argparse.Namespace) -> int:
    settings = resolve_settings()
    if args.backend == "sqlite":
        _print(build_sqlite_store().health())
    else:
        _print(build_falkordb_store(settings).health())
    return 0


def _cmd_switch(args: argparse.Namespace) -> int:
    config = switch_backend(
        args.backend,
        host=args.host,
        port=args.port,
        graph_name=args.graph_name,
        password=args.password,
        fallback_to_sqlite=False if args.no_fallback else None,
    )
    reset_cache()
    settings = resolve_settings()

    probe: dict
    if args.backend == "falkordb":
        probe = build_falkordb_store(settings).health()
    else:
        probe = build_sqlite_store().health()

    result = {
        "switched_to": args.backend,
        "config": config,
        "probe": probe,
    }

    if args.migrate:
        result["migration"] = _migrate(target=args.backend, settings=settings)
    elif probe.get("ok") and args.backend == "falkordb":
        result["hint"] = "如需把历史图快照复制到 FalkorDB，执行: python scripts/graph_backend.py migrate --to falkordb"

    _print(result)
    if not probe.get("ok") and not settings.fallback_to_sqlite:
        logger.error("后端已切换但不可用，且未开启自动回退")
        return 1
    return 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    _print(_migrate(target=args.to, settings=resolve_settings(), dry_run=args.dry_run))
    return 0


def _cmd_reset(args: argparse.Namespace) -> int:
    settings = resolve_settings()
    store = build_falkordb_store(settings) if args.backend == "falkordb" else build_sqlite_store()
    if args.backend == "falkordb":
        store.clear()
        _print({"backend": "falkordb", "cleared": True})
        return 0
    for snapshot in store.list_snapshots():
        store.delete_snapshot(snapshot["snapshot_type"], snapshot["snapshot_date"])
    _print({"backend": "sqlite", "cleared": True})
    return 0


def _migrate(target: str, settings, dry_run: bool = False) -> dict:
    """把 SQLite 中的全部快照复制到目标后端（或反向）。"""
    if target == "falkordb":
        source = build_sqlite_store()
        dest = build_falkordb_store(settings)
    elif target == "sqlite":
        source = build_falkordb_store(settings)
        dest = build_sqlite_store()
    else:
        raise SystemExit(f"不支持的目标后端: {target}")

    snapshots = source.list_snapshots()
    migrated = []
    for item in snapshots:
        snapshot = source.load_snapshot(item["snapshot_type"], item["snapshot_date"])
        if snapshot is None:
            continue
        if not dry_run:
            edges = dest.save_snapshot(snapshot)
        else:
            edges = len(snapshot.edges)
        migrated.append(
            {
                "snapshot_type": item["snapshot_type"],
                "snapshot_date": item["snapshot_date"],
                "nodes": len(snapshot.nodes),
                "edges": edges,
            }
        )
    return {
        "target": target,
        "dry_run": dry_run,
        "snapshot_total": len(snapshots),
        "migrated": migrated,
        "target_health": dest.health(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="StockGraph 图后端一键切换（sqlite <-> falkordb）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/graph_backend.py status
  python scripts/graph_backend.py switch falkordb --host 127.0.0.1 --port 6379
  python scripts/graph_backend.py switch falkordb --migrate
  python scripts/graph_backend.py switch sqlite
  python scripts/graph_backend.py migrate --to falkordb
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="查看当前后端与两边的健康状态")
    status.set_defaults(func=_cmd_status)

    ping = sub.add_parser("ping", help="探测指定后端连通性")
    ping.add_argument("--backend", choices=SUPPORTED_BACKENDS, default="falkordb")
    ping.set_defaults(func=_cmd_ping)

    switch = sub.add_parser("switch", help="切换默认图后端")
    switch.add_argument("backend", choices=SUPPORTED_BACKENDS)
    switch.add_argument("--host", help="FalkorDB 主机")
    switch.add_argument("--port", type=int, help="FalkorDB 端口")
    switch.add_argument("--graph-name", help="FalkorDB 图名")
    switch.add_argument("--password", help="FalkorDB 密码")
    switch.add_argument("--no-fallback", action="store_true", help="关闭不可用时自动回退 SQLite")
    switch.add_argument("--migrate", action="store_true", help="切换后把历史快照迁移过去")
    switch.set_defaults(func=_cmd_switch)

    migrate = sub.add_parser("migrate", help="在两个后端之间复制全部图快照")
    migrate.add_argument("--to", choices=SUPPORTED_BACKENDS, required=True)
    migrate.add_argument("--dry-run", action="store_true")
    migrate.set_defaults(func=_cmd_migrate)

    reset = sub.add_parser("reset", help="清空某个后端的图数据")
    reset.add_argument("--backend", choices=SUPPORTED_BACKENDS, default="falkordb")
    reset.set_defaults(func=_cmd_reset)

    return parser


def main() -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
