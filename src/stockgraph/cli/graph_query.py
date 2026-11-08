"""图查询 CLI：中心度、社区、邻居、链路。

所有命令都走 `create_graph_store()`，因此 SQLite 与 FalkorDB 下用法完全一致。
"""

from __future__ import annotations

import argparse
import json

from stockgraph.core import configure_logging
from stockgraph.infrastructure.graph import backend_status, create_graph_store, resolve_settings


def _dump(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _resolve_snapshot(store, snapshot_type: str | None, snapshot_date: str | None):
    snapshots = store.list_snapshots()
    if not snapshots:
        raise SystemExit("图库里还没有快照，先执行: python scripts/build_graph_snapshots.py --persist")
    if snapshot_type and snapshot_date:
        return snapshot_type, snapshot_date
    for item in snapshots:
        if snapshot_type and item["snapshot_type"] != snapshot_type:
            continue
        if snapshot_date and item["snapshot_date"] != snapshot_date:
            continue
        return item["snapshot_type"], item["snapshot_date"]
    raise SystemExit(f"未找到匹配快照: type={snapshot_type} date={snapshot_date}")


def _cmd_stats(args) -> int:
    store = create_graph_store()
    _dump(
        {
            "backend": store.backend,
            "settings": resolve_settings().as_dict(),
            "health": store.health(),
            "snapshots": store.list_snapshots()[:20],
        }
    )
    return 0


def _cmd_top(args) -> int:
    store = create_graph_store()
    snapshot_type, snapshot_date = _resolve_snapshot(store, args.snapshot_type, args.snapshot_date)
    _dump(
        {
            "backend": store.backend,
            "snapshot_type": snapshot_type,
            "snapshot_date": snapshot_date,
            "top_nodes": store.top_nodes(snapshot_type, snapshot_date, limit=args.limit, node_type=args.node_type),
        }
    )
    return 0


def _cmd_pagerank(args) -> int:
    store = create_graph_store()
    snapshot_type, snapshot_date = _resolve_snapshot(store, args.snapshot_type, args.snapshot_date)
    _dump(
        {
            "backend": store.backend,
            "snapshot_type": snapshot_type,
            "snapshot_date": snapshot_date,
            "damping": args.damping,
            "ranking": store.pagerank(
                snapshot_type, snapshot_date, damping=args.damping, iterations=args.iterations, limit=args.limit
            ),
        }
    )
    return 0


def _cmd_communities(args) -> int:
    store = create_graph_store()
    snapshot_type, snapshot_date = _resolve_snapshot(store, args.snapshot_type, args.snapshot_date)
    _dump(
        {
            "backend": store.backend,
            "snapshot_type": snapshot_type,
            "snapshot_date": snapshot_date,
            "communities": store.communities(
                snapshot_type, snapshot_date, max_iterations=args.iterations, min_size=args.min_size, limit=args.limit
            ),
        }
    )
    return 0


def _cmd_neighbors(args) -> int:
    store = create_graph_store()
    _dump(store.neighbors(args.node_id, limit=args.limit, snapshot_type=args.snapshot_type))
    return 0


def _cmd_path(args) -> int:
    store = create_graph_store()
    _dump(store.shortest_path(args.source, args.target, max_depth=args.max_depth, snapshot_type=args.snapshot_type))
    return 0


def _cmd_status(_args) -> int:
    _dump(backend_status())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="StockGraph 图分析查询")
    sub = parser.add_subparsers(dest="command", required=True)

    stats = sub.add_parser("stats", help="后端与快照概览")
    stats.set_defaults(func=_cmd_stats)

    status = sub.add_parser("status", help="后端健康状态")
    status.set_defaults(func=_cmd_status)

    top = sub.add_parser("top", help="按加权度取核心节点")
    top.add_argument("--snapshot-type", "--type", dest="snapshot_type")
    top.add_argument("--snapshot-date", "--date", dest="snapshot_date")
    top.add_argument("--node-type")
    top.add_argument("--limit", type=int, default=20)
    top.set_defaults(func=_cmd_top)

    pr = sub.add_parser("pagerank", help="加权 PageRank 重要性排序")
    pr.add_argument("--snapshot-type", "--type", dest="snapshot_type")
    pr.add_argument("--snapshot-date", "--date", dest="snapshot_date")
    pr.add_argument("--damping", type=float, default=0.85)
    pr.add_argument("--iterations", type=int, default=40)
    pr.add_argument("--limit", type=int, default=20)
    pr.set_defaults(func=_cmd_pagerank)

    comm = sub.add_parser("communities", help="标签传播社区发现")
    comm.add_argument("--snapshot-type", "--type", dest="snapshot_type")
    comm.add_argument("--snapshot-date", "--date", dest="snapshot_date")
    comm.add_argument("--iterations", type=int, default=30)
    comm.add_argument("--min-size", type=int, default=2)
    comm.add_argument("--limit", type=int, default=20)
    comm.set_defaults(func=_cmd_communities)

    nb = sub.add_parser("neighbors", help="一跳邻居")
    nb.add_argument("node_id")
    nb.add_argument("--snapshot-type", "--type", dest="snapshot_type")
    nb.add_argument("--limit", type=int, default=50)
    nb.set_defaults(func=_cmd_neighbors)

    path = sub.add_parser("path", help="最短关联链路")
    path.add_argument("source")
    path.add_argument("target")
    path.add_argument("--snapshot-type", "--type", dest="snapshot_type")
    path.add_argument("--max-depth", type=int, default=4)
    path.set_defaults(func=_cmd_path)

    return parser


def main() -> int:
    configure_logging()
    args = build_parser().parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
