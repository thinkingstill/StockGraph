"""把后端无关的分析能力挂到任意图存储实现上。

`GraphAnalyticsMixin` 只依赖实现类的 `fetch_edges()` 与 `node_names()`，
因此 SQLite 与 FalkorDB 得到完全一致的中心度、社区划分结果——切换后端不会改变分析结论。
"""

from __future__ import annotations

from typing import Any

from stockgraph.infrastructure.graph.algorithms import (
    connected_components,
    degree_centrality,
    label_propagation_communities,
    pagerank,
)


class GraphAnalyticsMixin:
    """实现类需提供 fetch_edges(snapshot_type, snapshot_date) 与 node_names(node_ids)。"""

    def degree_centrality(self, snapshot_type: str, snapshot_date: str) -> dict[str, float]:
        return degree_centrality(self.fetch_edges(snapshot_type, snapshot_date))  # type: ignore[attr-defined]

    def pagerank(
        self,
        snapshot_type: str,
        snapshot_date: str,
        *,
        damping: float = 0.85,
        iterations: int = 40,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        edges = self.fetch_edges(snapshot_type, snapshot_date)  # type: ignore[attr-defined]
        ranks = pagerank(edges, damping=damping, iterations=iterations)
        if not ranks:
            return []
        # 同分必须用 node_id 做次级键：SQLite 与 FalkorDB 的边返回顺序不同，
        # 只按 score 排序时，并列节点的名次会随后端漂移（实测第 40 名互换）。
        ordered = sorted(ranks.items(), key=lambda item: (-item[1], item[0]))[:limit]
        names = self.node_names([node_id for node_id, _ in ordered])  # type: ignore[attr-defined]
        return [
            {
                "node_id": node_id,
                "node_name": names.get(node_id, ""),
                "score": round(score, 8),
                "rank": index + 1,
            }
            for index, (node_id, score) in enumerate(ordered)
        ]

    def communities(
        self,
        snapshot_type: str,
        snapshot_date: str,
        *,
        max_iterations: int = 30,
        min_size: int = 2,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        edges = self.fetch_edges(snapshot_type, snapshot_date)  # type: ignore[attr-defined]
        labels = label_propagation_communities(edges, max_iterations=max_iterations, min_size=min_size)
        if not labels:
            return []
        names = self.node_names(list(labels))  # type: ignore[attr-defined]

        weights: dict[str, float] = {}
        for edge in edges:
            label = labels.get(str(edge["source"]))
            if label:
                weights[label] = weights.get(label, 0.0) + float(edge.get("weight") or 0.0)

        buckets: dict[str, list[str]] = {}
        for node_id, label in labels.items():
            buckets.setdefault(label, []).append(node_id)

        result: list[dict[str, Any]] = []
        for label, members in sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0]))[:limit]:
            members.sort(key=lambda node_id: names.get(node_id, node_id))
            result.append(
                {
                    "community_id": label,
                    "size": len(members),
                    "total_weight": round(weights.get(label, 0.0), 2),
                    "top_members": [
                        {"node_id": node_id, "node_name": names.get(node_id, "")} for node_id in members[:10]
                    ],
                }
            )
        return result

    def components(self, snapshot_type: str, snapshot_date: str, limit: int = 10) -> list[dict[str, Any]]:
        edges = self.fetch_edges(snapshot_type, snapshot_date)  # type: ignore[attr-defined]
        all_components = connected_components(edges)
        names = self.node_names([node for comp in all_components[:limit] for node in comp])  # type: ignore[attr-defined]
        return [
            {
                "component_id": index + 1,
                "size": len(component),
                "members": [{"node_id": n, "node_name": names.get(n, "")} for n in component[:10]],
            }
            for index, component in enumerate(all_components[:limit])
        ]
