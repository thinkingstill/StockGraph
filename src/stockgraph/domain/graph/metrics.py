from __future__ import annotations

from collections import Counter

from stockgraph.domain.graph.models import GraphSnapshot


def compute_cooccurrence_strength(weight: float, count: int) -> float:
    if count <= 0:
        return 0.0
    return round(weight / count, 4)


def compute_centrality_proxy(snapshot: GraphSnapshot) -> dict[str, int]:
    degree = Counter()
    for edge in snapshot.edges:
        degree[edge.source_node_id] += 1
        degree[edge.target_node_id] += 1
    return dict(degree)


def summarize_graph(snapshot: GraphSnapshot) -> dict:
    centrality = compute_centrality_proxy(snapshot)
    top_nodes = sorted(centrality.items(), key=lambda item: item[1], reverse=True)[:10]
    return {
        "snapshot_type": snapshot.snapshot_type,
        "snapshot_date": snapshot.snapshot_date,
        "node_count": len(snapshot.nodes),
        "edge_count": len(snapshot.edges),
        "top_degree_nodes": top_nodes,
    }
