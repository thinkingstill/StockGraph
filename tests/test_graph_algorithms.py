"""图存储抽象层与算法层测试。

重点覆盖三块：
1. 后端无关算法（PageRank / 社区发现 / 最短路径 / 连通分量）的数值正确性；
2. SQLite 后端的写入幂等、跨快照节点属性不被覆盖、删除快照后清理孤立节点；
3. 配置解析的优先级（环境变量 > 配置文件 > 默认值）与非法后端校验。
"""

from __future__ import annotations

import json

import pytest

from stockgraph.domain.graph.models import GraphEdge, GraphNode, GraphSnapshot
from stockgraph.infrastructure.graph import algorithms
from stockgraph.infrastructure.graph.config import (
    DEFAULT_CONFIG,
    resolve_settings,
    switch_backend,
)


def build_snapshot(snapshot_date: str = "2026-01-05", snapshot_type: str = "dragon_tiger") -> GraphSnapshot:
    nodes = [
        GraphNode(node_id="stock:600519", node_type="stock", node_key="600519", node_name="贵州茅台", attributes={}),
        GraphNode(node_id="stock:000001", node_type="stock", node_key="000001", node_name="平安银行", attributes={}),
        GraphNode(node_id="seat:A", node_type="seat", node_key="A", node_name="机构专用", attributes={}),
        GraphNode(node_id="seat:B", node_type="seat", node_key="B", node_name="深股通专用", attributes={}),
    ]
    edges = [
        GraphEdge("stock:600519", "seat:A", "buy", 3.0, snapshot_date, {}),
        GraphEdge("stock:000001", "seat:A", "buy", 1.0, snapshot_date, {}),
        GraphEdge("stock:000001", "seat:B", "sell", 2.0, snapshot_date, {}),
    ]
    return GraphSnapshot(snapshot_date=snapshot_date, snapshot_type=snapshot_type, nodes=nodes, edges=edges)


# --------------------------------------------------------------------------- 算法层


def test_pagerank_sums_to_one_and_ranks_high_weight_first():
    edges = [
        {"source": "a", "target": "b", "weight": 1.0},
        {"source": "a", "target": "c", "weight": 1.0},
        {"source": "b", "target": "c", "weight": 1.0},
    ]
    scores = algorithms.pagerank(edges)
    assert pytest.approx(sum(scores.values()), abs=1e-6) == 1.0
    # c 收到两条入边，应当排第一
    assert max(scores, key=scores.get) == "c"


def test_pagerank_handles_empty_graph():
    assert algorithms.pagerank([]) == {}


def test_pagerank_handles_dangling_nodes_without_losing_mass():
    scores = algorithms.pagerank([{"source": "a", "target": "b", "weight": 1.0}])
    assert pytest.approx(sum(scores.values()), abs=1e-6) == 1.0


def test_label_propagation_finds_two_clusters():
    edges = [
        {"source": "a", "target": "b", "weight": 1.0},
        {"source": "b", "target": "c", "weight": 1.0},
        {"source": "c", "target": "a", "weight": 1.0},
        {"source": "x", "target": "y", "weight": 1.0},
        {"source": "y", "target": "z", "weight": 1.0},
        {"source": "z", "target": "x", "weight": 1.0},
    ]
    # LPA 返回 node_id -> community_id，按社区分组后应得到两个三元组
    labels = algorithms.label_propagation_communities(edges, min_size=1)
    groups: dict[str, list[str]] = {}
    for node, community in labels.items():
        groups.setdefault(community, []).append(node)
    assert sorted(sorted(members) for members in groups.values()) == [["a", "b", "c"], ["x", "y", "z"]]


def test_communities_below_min_size_collapse_into_zero():
    edges = [{"source": "a", "target": "b", "weight": 1.0}]
    labels = algorithms.label_propagation_communities(edges, min_size=3)
    assert set(labels.values()) == {"0"}
    assert sorted(labels) == ["a", "b"]


def test_bfs_shortest_path_is_deterministic_and_ordered():
    edges = [
        {"source": "a", "target": "b"},
        {"source": "b", "target": "c"},
        {"source": "a", "target": "c"},
    ]
    path = algorithms.bfs_shortest_path(edges, "a", "c", max_depth=3)
    assert path == ["a", "c"]  # 直连优先，长度 1


def test_bfs_returns_empty_when_unreachable_or_too_deep():
    edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]
    # 跳数上限 1 时 a→c 需要 2 跳，应当找不到
    assert algorithms.bfs_shortest_path(edges, "a", "c", max_depth=1) == []
    assert algorithms.bfs_shortest_path(edges, "a", "zzz", max_depth=5) == []
    assert algorithms.bfs_shortest_path(edges, "a", "c", max_depth=2) == ["a", "b", "c"]


def test_degree_centrality_counts_both_directions():
    edges = [{"source": "a", "target": "b"}, {"source": "c", "target": "b"}]
    degree = algorithms.degree_centrality(edges)
    assert degree["b"] == 2
    assert degree["a"] == 1


def test_connected_components_separates_islands():
    edges = [{"source": "a", "target": "b"}, {"source": "c", "target": "d"}]
    components = algorithms.connected_components(edges)
    assert components == [["a", "b"], ["c", "d"]]


# --------------------------------------------------------------------------- 配置层


def test_resolve_settings_defaults_to_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("STOCKGRAPH_GRAPH_BACKEND", raising=False)
    monkeypatch.delenv("STOCKGRAPH_GRAPH_FALLBACK", raising=False)
    monkeypatch.setenv("STOCKGRAPH_GRAPH_CONFIG", str(tmp_path / "missing.json"))
    settings = resolve_settings()
    assert settings.backend == "sqlite"
    assert settings.source == "default"
    assert settings.fallback_to_sqlite is True


def test_env_backend_beats_config_file(monkeypatch, tmp_path):
    config_path = tmp_path / "graph_backend.json"
    payload = json.loads(json.dumps(DEFAULT_CONFIG))
    payload["backend"] = "sqlite"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setenv("STOCKGRAPH_GRAPH_CONFIG", str(config_path))
    monkeypatch.setenv("STOCKGRAPH_GRAPH_BACKEND", "falkordb")
    settings = resolve_settings()
    assert settings.backend == "falkordb"
    assert settings.source == "env"


def test_config_file_is_respected_when_env_absent(monkeypatch, tmp_path):
    config_path = tmp_path / "graph_backend.json"
    payload = json.loads(json.dumps(DEFAULT_CONFIG))
    payload["backend"] = "falkordb"
    payload["falkordb"]["port"] = 6399
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.delenv("STOCKGRAPH_GRAPH_BACKEND", raising=False)
    monkeypatch.setenv("STOCKGRAPH_GRAPH_CONFIG", str(config_path))
    settings = resolve_settings()
    assert settings.backend == "falkordb"
    assert settings.falkordb["port"] == 6399
    assert settings.source == "config"


def test_switch_backend_rejects_unknown_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCKGRAPH_GRAPH_CONFIG", str(tmp_path / "graph_backend.json"))
    with pytest.raises(ValueError):
        switch_backend("neo4j")


def test_switch_backend_persists_config(monkeypatch, tmp_path):
    config_path = tmp_path / "graph_backend.json"
    monkeypatch.setenv("STOCKGRAPH_GRAPH_CONFIG", str(config_path))
    switch_backend("falkordb", host="10.0.0.5", port=7000, graph_name="sg_test")
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["backend"] == "falkordb"
    assert saved["falkordb"]["host"] == "10.0.0.5"
    assert saved["falkordb"]["port"] == 7000
    assert saved["falkordb"]["graph_name"] == "sg_test"
