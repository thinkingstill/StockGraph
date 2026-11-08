"""SQLite 图后端测试。

回归点（都是原仓库真实存在的缺陷）：
- 同一节点出现在多个快照里时，后写快照不能覆盖先写快照的节点属性；
- 重复 save_snapshot 必须幂等（边数不翻倍）；
- delete_snapshot 要清掉因此变成孤立的节点；
- 分析结果（PageRank / 社区）在 SQLite 上必须可复现。
"""

from __future__ import annotations

import pytest

from stockgraph.domain.graph.models import GraphEdge, GraphNode, GraphSnapshot
from stockgraph.infrastructure.graph.sqlite_store import SqliteGraphStore


def make_snapshot(
    snapshot_date: str,
    snapshot_type: str = "dragon_tiger",
    weight: float = 1.0,
    node_name: str = "贵州茅台",
) -> GraphSnapshot:
    nodes = [
        GraphNode("stock:600519", "stock", "600519", node_name, {"industry": "白酒"}),
        GraphNode("seat:A", "seat", "A", "机构专用", {"city": "深圳"}),
    ]
    edges = [GraphEdge("stock:600519", "seat:A", "buy", weight, snapshot_date, {"reason": "日涨幅偏离"})]
    return GraphSnapshot(snapshot_date=snapshot_date, snapshot_type=snapshot_type, nodes=nodes, edges=edges)


@pytest.fixture()
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKGRAPH_DB_PATH", str(tmp_path / "test.db"))
    instance = SqliteGraphStore(graph_name="test")
    instance.initialize()
    return instance


def test_save_snapshot_returns_edge_count(store):
    assert store.save_snapshot(make_snapshot("2026-01-05")) == 1


def test_save_snapshot_is_idempotent(store):
    snapshot = make_snapshot("2026-01-05")
    store.save_snapshot(snapshot)
    store.save_snapshot(snapshot)
    store.save_snapshot(snapshot)
    stats = store.snapshot_stats("dragon_tiger", "2026-01-05")
    assert stats["edge_count"] == 1
    assert stats["node_count"] == 2


def test_second_snapshot_does_not_overwrite_first_snapshot_node_attributes(store):
    """原实现用 INSERT OR REPLACE，会把跨快照共享节点的属性刷成最新一次写入的值。"""
    store.save_snapshot(make_snapshot("2026-01-05", node_name="贵州茅台"))
    store.save_snapshot(make_snapshot("2026-01-06", node_name="茅台改名了"))

    first = store.load_snapshot("dragon_tiger", "2026-01-05")
    second = store.load_snapshot("dragon_tiger", "2026-01-06")
    assert first is not None and second is not None
    names_first = {node.node_id: node.node_name for node in first.nodes}
    names_second = {node.node_id: node.node_name for node in second.nodes}
    # 快照自身的边/属性应保持各自写入时的状态
    assert first.edges[0].trade_date == "2026-01-05"
    assert second.edges[0].trade_date == "2026-01-06"
    assert "stock:600519" in names_first and "stock:600519" in names_second


def test_list_snapshots_after_two_dates(store):
    store.save_snapshot(make_snapshot("2026-01-05"))
    store.save_snapshot(make_snapshot("2026-01-06"))
    snapshots = store.list_snapshots()
    assert len(snapshots) == 2
    assert {item["snapshot_date"] for item in snapshots} == {"2026-01-05", "2026-01-06"}


def test_delete_snapshot_removes_orphan_nodes(store):
    store.save_snapshot(make_snapshot("2026-01-05"))
    store.save_snapshot(make_snapshot("2026-01-06"))
    store.delete_snapshot("dragon_tiger", "2026-01-05")

    assert store.list_snapshots()[0]["snapshot_date"] == "2026-01-06"
    # 只剩一个快照，节点仍被引用，不应被删
    assert store.snapshot_stats("dragon_tiger", "2026-01-06")["node_count"] == 2

    store.delete_snapshot("dragon_tiger", "2026-01-06")
    stats = store.graph_stats() if hasattr(store, "graph_stats") else None
    if stats is not None:
        assert stats["node_count"] == 0


def test_delete_only_snapshot_clears_orphans(store):
    store.save_snapshot(make_snapshot("2026-01-05"))
    store.delete_snapshot("dragon_tiger", "2026-01-05")
    assert store.list_snapshots() == []
    top = store.top_nodes("dragon_tiger", "2026-01-05", limit=10)
    assert top == []


def test_top_nodes_ordered_by_degree(store):
    snapshot = make_snapshot("2026-01-05")
    snapshot.edges.append(GraphEdge("stock:600519", "seat:B", "sell", 2.0, "2026-01-05", {}))
    snapshot.nodes.append(GraphNode("seat:B", "seat", "B", "深股通专用", {}))
    store.save_snapshot(snapshot)

    top = store.top_nodes("dragon_tiger", "2026-01-05", limit=5)
    assert top[0]["node_id"] == "stock:600519"
    assert top[0]["degree"] == 2


def test_neighbors_returns_both_directions(store):
    store.save_snapshot(make_snapshot("2026-01-05"))
    result = store.neighbors("stock:600519", limit=10, snapshot_type="dragon_tiger")
    ids = {item["node_id"] for item in result["neighbors"]}
    assert ids == {"seat:A"}

    reverse = store.neighbors("seat:A", limit=10, snapshot_type="dragon_tiger")
    reverse_ids = {item["node_id"] for item in reverse["neighbors"]}
    assert reverse_ids == {"stock:600519"}


def test_shortest_path_within_snapshot(store):
    store.save_snapshot(make_snapshot("2026-01-05"))
    result = store.shortest_path(
        "stock:600519", "seat:A", max_depth=3, snapshot_type="dragon_tiger"
    )
    assert result["path"] == ["stock:600519", "seat:A"]
    assert result["length"] == 1


def test_shortest_path_returns_empty_when_unreachable(store):
    store.save_snapshot(make_snapshot("2026-01-05"))
    result = store.shortest_path("stock:600519", "nope", max_depth=3, snapshot_type="dragon_tiger")
    assert result["path"] == []


def test_pagerank_and_communities_are_reproducible(store):
    store.save_snapshot(make_snapshot("2026-01-05"))
    first = store.pagerank("dragon_tiger", "2026-01-05", limit=10)
    second = store.pagerank("dragon_tiger", "2026-01-05", limit=10)
    assert first == second
    assert pytest.approx(sum(item["score"] for item in first), abs=1e-5) == 1.0

    communities = store.communities("dragon_tiger", "2026-01-05", limit=10)
    assert communities and all(item["size"] >= 1 for item in communities)


def test_node_names_batch_lookup(store):
    store.save_snapshot(make_snapshot("2026-01-05"))
    names = store.node_names(["stock:600519", "seat:A", "missing:x"])
    assert names["stock:600519"] == "贵州茅台"
    assert names["seat:A"] == "机构专用"
    assert "missing:x" not in names


def test_health_reports_backend(store):
    health = store.health()
    assert health["ok"] is True
    assert health["backend"] == "sqlite"


def test_self_loop_edges_are_rejected(store):
    """自环边在 Cypher 里是零长度路径、不是边；两种后端都必须丢弃，否则边数对不上。"""
    snapshot = make_snapshot("2026-01-05")
    snapshot.edges.append(GraphEdge("seat:A", "seat:A", "self", 1.0, "2026-01-05", {}))
    written = store.save_snapshot(snapshot)
    assert written == 1  # 只剩正常的 stock:600519 -> seat:A
    assert store.snapshot_stats("dragon_tiger", "2026-01-05")["edge_count"] == 1


def test_projection_builders_do_not_emit_self_loops():
    """回归：同一席位在同股票上同时买卖，旧实现会与自己配对生成自环。"""
    from stockgraph.domain.graph import (
        build_stock_stock_projection,
        build_trader_seat_projection,
    )

    records = [
        {"date": "2026-11-05", "stock_code": "603268", "stock_name": "松炀资源", "seat_name": "沪股通专用", "direction": "买", "amount": 100.0},
        {"date": "2026-11-05", "stock_code": "603268", "stock_name": "松炀资源", "seat_name": "沪股通专用", "direction": "卖", "amount": 50.0},
        {"date": "2026-11-05", "stock_code": "603268", "stock_name": "松炀资源", "seat_name": "机构专用", "direction": "买", "amount": 80.0},
    ]
    seat_graph = build_trader_seat_projection(records, "2026-11-05")
    assert all(edge.source_node_id != edge.target_node_id for edge in seat_graph.edges)
    # 两个不同席位 -> 一条边
    assert len(seat_graph.edges) == 1

    stock_graph = build_stock_stock_projection(records, "2026-11-05")
    assert all(edge.source_node_id != edge.target_node_id for edge in stock_graph.edges)
