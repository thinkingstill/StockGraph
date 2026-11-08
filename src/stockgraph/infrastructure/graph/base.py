"""图存储抽象层。

设计目标：
1. 上层（application / cli / api）只依赖 `GraphStore` 协议，不关心底层是 SQLite 还是 FalkorDB；
2. 图分析算法（PageRank、社区发现、最短路径）在两种后端上行为一致；
3. 后端可通过 `STOCKGRAPH_GRAPH_BACKEND` 环境变量或 `config/graph_backend.json` 一键切换。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from stockgraph.domain.graph.models import GraphSnapshot


@dataclass(slots=True)
class SnapshotKey:
    """快照唯一标识：同一 snapshot_type 在同一天只有一份。"""

    snapshot_type: str
    snapshot_date: str

    @property
    def key(self) -> str:
        return f"{self.snapshot_type}|{self.snapshot_date}"


@dataclass(slots=True)
class GraphStoreStats:
    backend: str
    graph_name: str
    node_count: int = 0
    edge_count: int = 0
    snapshot_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "graph_name": self.graph_name,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "snapshot_count": self.snapshot_count,
            **self.extra,
        }


class GraphStoreError(RuntimeError):
    """图存储层统一异常。"""


@runtime_checkable
class GraphStore(Protocol):
    """图存储统一接口。"""

    backend: str

    def initialize(self) -> None:
        """建表/建索引，幂等。"""

    def health(self) -> dict[str, Any]:
        """连通性与统计信息。"""

    def save_snapshot(self, snapshot: GraphSnapshot) -> int:
        """写入快照，返回写入的边数量；同 key 幂等覆盖。"""

    def load_snapshot(self, snapshot_type: str, snapshot_date: str) -> GraphSnapshot | None:
        """读取快照。"""

    def list_snapshots(self) -> list[dict[str, Any]]:
        """列出全部快照元信息。"""

    def delete_snapshot(self, snapshot_type: str, snapshot_date: str) -> int:
        """删除快照及其孤立节点，返回删除的边数量。"""

    def snapshot_stats(self, snapshot_type: str, snapshot_date: str) -> dict[str, Any]:
        """单快照统计。"""

    def fetch_edges(self, snapshot_type: str, snapshot_date: str) -> list[dict[str, Any]]:
        """返回 [{source, target, edge_type, weight, attributes}]，供后端无关的算法层使用。"""

    def top_nodes(
        self,
        snapshot_type: str,
        snapshot_date: str,
        limit: int = 20,
        node_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """按度中心性排序的节点。"""

    def neighbors(self, node_id: str, limit: int = 50, snapshot_type: str | None = None) -> dict[str, Any]:
        """一跳邻居。"""

    def shortest_path(
        self,
        source_node_id: str,
        target_node_id: str,
        max_depth: int = 4,
        snapshot_type: str | None = None,
    ) -> dict[str, Any]:
        """无权最短路径（BFS），用于资金关联链路挖掘。"""

    def node_names(self, node_ids: list[str]) -> dict[str, str]:
        """批量取节点名，供分析结果回填可读名称。"""

    def pagerank(
        self,
        snapshot_type: str,
        snapshot_date: str,
        *,
        damping: float = 0.85,
        iterations: int = 40,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """加权 PageRank 排序。"""

    def communities(
        self,
        snapshot_type: str,
        snapshot_date: str,
        *,
        max_iterations: int = 30,
        min_size: int = 2,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """社区发现。"""
