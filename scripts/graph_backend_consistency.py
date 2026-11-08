#!/usr/bin/env python3
"""SQLite / FalkorDB 双后端一致性比对。

同一份图数据分别落到 SQLite 与 FalkorDB，两边的查询结果必须逐项相同——
否则"一键切换"就是假的：切过去之后分析结论会变。

用法：
    python scripts/graph_backend_consistency.py
    python scripts/graph_backend_consistency.py --decimals 8 --json

退出码 0 表示全部一致，1 表示存在差异（并打印差异明细）。

注意：FalkorDB 侧为空时先执行
    python scripts/graph_backend.py migrate --to falkordb
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.infrastructure.graph.sqlite_store import SqliteGraphStore  # noqa: E402

try:
    from stockgraph.infrastructure.graph.falkordb_store import FalkorDBGraphStore
except ImportError:  # pragma: no cover - falkordb 为可选依赖
    FalkorDBGraphStore = None  # type: ignore[assignment]


# 比对时忽略的字段：它们描述"存在哪/何时写入"，不是图语义。
# - backend：后端名本来就不同
# - created_at：SQLite 的入库时间戳，FalkorDB 没有对应概念
# 数据本身（节点、边、权重、分析结果）一律不忽略。
IGNORED_KEYS = {"backend", "created_at"}


def _strip_ignored(value):
    if isinstance(value, dict):
        return {k: _strip_ignored(v) for k, v in value.items() if k not in IGNORED_KEYS}
    if isinstance(value, list):
        return [_strip_ignored(v) for v in value]
    return value


def _norm(value, decimals: int):
    """浮点按精度归一，避免尾差造成假差异。"""
    value = _strip_ignored(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return str(value)
        return round(value, decimals)
    if isinstance(value, dict):
        return {k: _norm(v, decimals) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_norm(v, decimals) for v in value]
    return value


def _diff(label: str, left, right, decimals: int) -> dict:
    a, b = _norm(left, decimals), _norm(right, decimals)
    if a == b:
        return {"check": label, "ok": True, "detail": ""}
    sa = json.dumps(a, ensure_ascii=False, sort_keys=True)[:400]
    sb = json.dumps(b, ensure_ascii=False, sort_keys=True)[:400]
    return {"check": label, "ok": False, "detail": f"sqlite={sa}\n  falkordb={sb}"}


def _partition_signature(groups) -> list[list[str]]:
    """把社区结果归一成"分组结构"，消除标签命名差异的影响。"""
    if isinstance(groups, dict):
        buckets: dict[str, list[str]] = {}
        for node, label in groups.items():
            buckets.setdefault(str(label), []).append(str(node))
        return sorted((sorted(v) for v in buckets.values()), key=lambda g: (-len(g), g[0] if g else ""))
    if isinstance(groups, list):
        out = []
        for item in groups:
            members = item.get("members") if isinstance(item, dict) else item
            out.append(sorted(str(m) for m in (members or [])))
        return sorted(out, key=lambda g: (-len(g), g[0] if g else ""))
    return []


def run(decimals: int) -> list[dict]:
    if FalkorDBGraphStore is None:
        raise SystemExit("未安装 falkordb 依赖，无法比对。pip install falkordb")

    sqlite_store = SqliteGraphStore()
    falkor_store = FalkorDBGraphStore()
    results: list[dict] = []

    # 1) 全局规模
    results.append(_diff("stats", _stats_dict(sqlite_store.stats()), _stats_dict(falkor_store.stats()), decimals))

    # 2) 快照清单
    s_snaps = sqlite_store.list_snapshots()
    f_snaps = falkor_store.list_snapshots()
    results.append(_diff("list_snapshots", s_snaps, f_snaps, decimals))
    if not f_snaps:
        results.append({"check": "FalkorDB 数据", "ok": False, "detail": "FalkorDB 为空，请先 migrate --to falkordb"})
        return results

    # 采样：每种类型取最新一张，再补最早期的一张
    by_type: dict[str, dict] = {}
    for snap in sorted(s_snaps, key=lambda s: str(s.get("snapshot_date")), reverse=True):
        by_type.setdefault(str(snap.get("snapshot_type")), snap)
    picks = list(by_type.values())
    if s_snaps:
        picks.append(sorted(s_snaps, key=lambda s: str(s.get("snapshot_date")))[0])
    seen, uniq = set(), []
    for snap in picks:
        key = (snap.get("snapshot_type"), snap.get("snapshot_date"))
        if key not in seen:
            seen.add(key)
            uniq.append(snap)

    for snap in uniq:
        stype = str(snap.get("snapshot_type"))
        sdate = str(snap.get("snapshot_date"))
        tag = f"{stype}@{sdate}"

        results.append(_diff(f"snapshot_stats[{tag}]",
                             sqlite_store.snapshot_stats(stype, sdate),
                             falkor_store.snapshot_stats(stype, sdate), decimals))

        s_edges = _edge_tuples(sqlite_store.fetch_edges(stype, sdate))
        f_edges = _edge_tuples(falkor_store.fetch_edges(stype, sdate))
        results.append(_diff(f"fetch_edges[{tag}]", s_edges, f_edges, decimals))

        node_ids = sorted({e[0] for e in s_edges} | {e[1] for e in s_edges})
        results.append(_diff(f"node_names[{tag}]",
                             sqlite_store.node_names(node_ids),
                             falkor_store.node_names(node_ids), decimals))

        results.append(_diff(f"top_nodes[{tag}]",
                             sqlite_store.top_nodes(stype, sdate, limit=20),
                             falkor_store.top_nodes(stype, sdate, limit=20), decimals))

        results.append(_diff(f"degree_centrality[{tag}]",
                             sqlite_store.degree_centrality(stype, sdate),
                             falkor_store.degree_centrality(stype, sdate), decimals))

        results.append(_diff(f"pagerank[{tag}]",
                             sqlite_store.pagerank(stype, sdate, limit=50),
                             falkor_store.pagerank(stype, sdate, limit=50), decimals))

        results.append(_diff(f"communities[{tag}]",
                             _partition_signature(sqlite_store.communities(stype, sdate)),
                             _partition_signature(falkor_store.communities(stype, sdate)), decimals))

        results.append(_diff(f"components[{tag}]",
                             sqlite_store.components(stype, sdate),
                             falkor_store.components(stype, sdate), decimals))

        # 邻居与最短路：取度数最高的节点做端点
        degrees = sqlite_store.degree_centrality(stype, sdate)
        ranked = sorted(degrees.items(), key=lambda kv: (-float(kv[1] or 0), kv[0]))
        if ranked:
            hub = ranked[0][0]
            results.append(_diff(f"neighbors[{tag}:{hub}]",
                                 sqlite_store.neighbors(hub, limit=50, snapshot_type=stype),
                                 falkor_store.neighbors(hub, limit=50, snapshot_type=stype), decimals))
            if len(ranked) > 5:
                other = ranked[5][0]
                results.append(_diff(f"shortest_path[{tag}:{hub}->{other}]",
                                     sqlite_store.shortest_path(hub, other, max_depth=4, snapshot_type=stype),
                                     falkor_store.shortest_path(hub, other, max_depth=4, snapshot_type=stype),
                                     decimals))

    return results


def _stats_dict(stats) -> dict:
    if hasattr(stats, "as_dict"):
        return stats.as_dict()
    if hasattr(stats, "to_dict"):
        return stats.to_dict()
    if hasattr(stats, "__dict__") and stats.__dict__:
        return dict(stats.__dict__)
    # __slots__ 数据类
    return {k: getattr(stats, k) for k in getattr(stats, "__slots__", [])}


def _edge_tuples(edges) -> list[tuple]:
    rows = [
        (
            str(e.get("source") or e.get("source_node_id")),
            str(e.get("target") or e.get("target_node_id")),
            str(e.get("edge_type")),
            round(float(e.get("weight") or 0.0), 4),
        )
        for e in edges
    ]
    return sorted(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite / FalkorDB 一致性比对")
    parser.add_argument("--decimals", type=int, default=8, help="浮点比较精度，默认 8 位小数")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    results = run(args.decimals)
    failed = [r for r in results if not r["ok"]]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['check']}")
            if not r["ok"]:
                print(f"       {r['detail']}")
        print()
        print(f"{len(results) - len(failed)}/{len(results)} 项一致")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
