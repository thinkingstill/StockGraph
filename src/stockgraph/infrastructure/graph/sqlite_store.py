"""SQLite 图后端（默认实现，零外部依赖）。

复用既有的 `graph_nodes / graph_edges / graph_snapshots` 三张表，
因此不需要迁移历史数据即可直接使用。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from stockgraph.domain.graph.models import GraphEdge, GraphNode, GraphSnapshot
from stockgraph.infrastructure.db.connection import database_path, get_connection
from stockgraph.infrastructure.db.schema import SCHEMA_SQL
from stockgraph.infrastructure.graph.algorithms import bfs_shortest_path, edge_types_on_path
from stockgraph.infrastructure.graph.analytics import GraphAnalyticsMixin
from stockgraph.infrastructure.graph.base import GraphStoreStats

logger = logging.getLogger(__name__)


class SqliteGraphStore(GraphAnalyticsMixin):
    backend = "sqlite"

    def __init__(self, graph_name: str = "stockgraph") -> None:
        self.graph_name = graph_name

    # ---------------------------------------------------------------- 基础

    def initialize(self) -> None:
        with get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    def health(self) -> dict[str, Any]:
        self.initialize()
        stats = self.stats()
        return {
            "backend": self.backend,
            "ok": True,
            "graph_name": self.graph_name,
            "location": str(database_path()),
            **stats.as_dict(),
        }

    def stats(self) -> GraphStoreStats:
        with get_connection() as conn:
            nodes = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
            snapshots = conn.execute("SELECT COUNT(*) FROM graph_snapshots").fetchone()[0]
        return GraphStoreStats(
            backend=self.backend,
            graph_name=self.graph_name,
            node_count=int(nodes or 0),
            edge_count=int(edges or 0),
            snapshot_count=int(snapshots or 0),
        )

    # ---------------------------------------------------------------- 写入

    def save_snapshot(self, snapshot: GraphSnapshot) -> int:
        self.initialize()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO graph_snapshots
                (snapshot_date, snapshot_type, version, metadata_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(snapshot_date, snapshot_type, version) DO UPDATE SET
                    metadata_json = excluded.metadata_json,
                    created_at = CURRENT_TIMESTAMP
                """,
                (
                    snapshot.snapshot_date,
                    snapshot.snapshot_type,
                    snapshot.version,
                    json.dumps(snapshot.metadata, ensure_ascii=False),
                ),
            )
            cursor.execute(
                "DELETE FROM graph_edges WHERE snapshot_type = ? AND trade_date = ?",
                (snapshot.snapshot_type, snapshot.snapshot_date),
            )
            for node in snapshot.nodes:
                # 关键修复：同一 node_id 会被多种快照复用，
                # 旧实现用 INSERT OR REPLACE 会把其他快照写入的属性整行覆盖成空。
                cursor.execute(
                    """
                    INSERT INTO graph_nodes (node_id, node_type, node_key, node_name, attributes_json)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(node_id) DO UPDATE SET
                        node_type = excluded.node_type,
                        node_key = excluded.node_key,
                        node_name = CASE
                            WHEN excluded.node_name IS NULL OR excluded.node_name = ''
                            THEN graph_nodes.node_name
                            ELSE excluded.node_name
                        END,
                        attributes_json = CASE
                            WHEN excluded.attributes_json IN ('{}', '', 'null', '{}')
                            THEN graph_nodes.attributes_json
                            ELSE excluded.attributes_json
                        END
                    """,
                    (
                        node.node_id,
                        node.node_type,
                        node.node_key,
                        node.node_name,
                        json.dumps(node.attributes, ensure_ascii=False),
                    ),
                )
            rows = [
                (
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.edge_type,
                    float(edge.weight or 0.0),
                    edge.trade_date or snapshot.snapshot_date,
                    snapshot.snapshot_type,
                    json.dumps(edge.attributes, ensure_ascii=False),
                )
                for edge in snapshot.edges
                # 自环边在 Cypher 里是零长度路径，不是真正的边；两种后端都不应存
                if edge.source_node_id != edge.target_node_id
            ]
            if rows:
                cursor.executemany(
                    """
                    INSERT INTO graph_edges
                    (source_node_id, target_node_id, edge_type, weight, trade_date, snapshot_type, attributes_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
            conn.commit()
        # 返回真正写入的边数（已排除自环），与 FalkorDB 后端口径一致
        return len(rows)

    def delete_snapshot(self, snapshot_type: str, snapshot_date: str) -> int:
        self.initialize()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM graph_edges WHERE snapshot_type = ? AND trade_date = ?",
                (snapshot_type, snapshot_date),
            )
            removed = cursor.rowcount or 0
            cursor.execute(
                "DELETE FROM graph_snapshots WHERE snapshot_type = ? AND snapshot_date = ?",
                (snapshot_type, snapshot_date),
            )
            # 清理孤立节点，避免 graph_nodes 无限膨胀
            cursor.execute(
                """
                DELETE FROM graph_nodes
                WHERE node_id NOT IN (SELECT source_node_id FROM graph_edges)
                  AND node_id NOT IN (SELECT target_node_id FROM graph_edges)
                """
            )
            conn.commit()
        return int(removed)

    # ---------------------------------------------------------------- 读取

    def load_snapshot(self, snapshot_type: str, snapshot_date: str) -> GraphSnapshot | None:
        self.initialize()
        with get_connection() as conn:
            meta_row = conn.execute(
                """
                SELECT version, metadata_json FROM graph_snapshots
                WHERE snapshot_type = ? AND snapshot_date = ?
                ORDER BY id DESC LIMIT 1
                """,
                (snapshot_type, snapshot_date),
            ).fetchone()
            edge_rows = conn.execute(
                """
                SELECT source_node_id, target_node_id, edge_type, weight, trade_date, attributes_json
                FROM graph_edges
                WHERE snapshot_type = ? AND trade_date = ?
                """,
                (snapshot_type, snapshot_date),
            ).fetchall()
            if not meta_row and not edge_rows:
                return None

            node_ids: set[str] = set()
            edges: list[GraphEdge] = []
            for row in edge_rows:
                node_ids.add(row["source_node_id"])
                node_ids.add(row["target_node_id"])
                edges.append(
                    GraphEdge(
                        source_node_id=row["source_node_id"],
                        target_node_id=row["target_node_id"],
                        edge_type=row["edge_type"],
                        weight=float(row["weight"] or 0.0),
                        trade_date=row["trade_date"] or "",
                        attributes=_loads(row["attributes_json"]),
                    )
                )

            nodes: list[GraphNode] = []
            if node_ids:
                placeholders = ",".join("?" for _ in node_ids)
                node_rows = conn.execute(
                    f"""
                    SELECT node_id, node_type, node_key, node_name, attributes_json
                    FROM graph_nodes WHERE node_id IN ({placeholders})
                    """,
                    tuple(node_ids),
                ).fetchall()
                nodes = [
                    GraphNode(
                        node_id=row["node_id"],
                        node_type=row["node_type"],
                        node_key=row["node_key"],
                        node_name=row["node_name"],
                        attributes=_loads(row["attributes_json"]),
                    )
                    for row in node_rows
                ]

        return GraphSnapshot(
            snapshot_date=snapshot_date,
            snapshot_type=snapshot_type,
            version=(meta_row["version"] if meta_row else "v1"),
            nodes=nodes,
            edges=edges,
            metadata=_loads(meta_row["metadata_json"]) if meta_row else {},
        )

    def list_snapshots(self) -> list[dict[str, Any]]:
        self.initialize()
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT s.snapshot_type, s.snapshot_date, s.version, s.metadata_json, s.created_at,
                       (SELECT COUNT(*) FROM graph_edges e
                         WHERE e.snapshot_type = s.snapshot_type AND e.trade_date = s.snapshot_date) AS edge_count
                FROM graph_snapshots s
                ORDER BY s.snapshot_date DESC, s.snapshot_type
                """
            ).fetchall()
        return [
            {
                "snapshot_type": row["snapshot_type"],
                "snapshot_date": row["snapshot_date"],
                "version": row["version"],
                "edge_count": int(row["edge_count"] or 0),
                "created_at": row["created_at"],
                "metadata": _loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def snapshot_stats(self, snapshot_type: str, snapshot_date: str) -> dict[str, Any]:
        self.initialize()
        with get_connection() as conn:
            edge_count = conn.execute(
                "SELECT COUNT(*) FROM graph_edges WHERE snapshot_type = ? AND trade_date = ?",
                (snapshot_type, snapshot_date),
            ).fetchone()[0]
            node_count = conn.execute(
                """
                SELECT COUNT(DISTINCT node_id) FROM (
                    SELECT source_node_id AS node_id FROM graph_edges
                     WHERE snapshot_type = ? AND trade_date = ?
                    UNION
                    SELECT target_node_id AS node_id FROM graph_edges
                     WHERE snapshot_type = ? AND trade_date = ?
                )
                """,
                (snapshot_type, snapshot_date, snapshot_type, snapshot_date),
            ).fetchone()[0]
        return {
            "snapshot_type": snapshot_type,
            "snapshot_date": snapshot_date,
            "node_count": int(node_count or 0),
            "edge_count": int(edge_count or 0),
        }

    def fetch_edges(self, snapshot_type: str, snapshot_date: str) -> list[dict[str, Any]]:
        self.initialize()
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT source_node_id, target_node_id, edge_type, weight, trade_date, attributes_json
                FROM graph_edges
                WHERE snapshot_type = ? AND trade_date = ?
                """,
                (snapshot_type, snapshot_date),
            ).fetchall()
        return [
            {
                "source": row["source_node_id"],
                "target": row["target_node_id"],
                "edge_type": row["edge_type"],
                "weight": float(row["weight"] or 0.0),
                "trade_date": row["trade_date"],
                "attributes": _loads(row["attributes_json"]),
            }
            for row in rows
        ]

    def top_nodes(
        self,
        snapshot_type: str,
        snapshot_date: str,
        limit: int = 20,
        node_type: str | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        type_filter = "AND n.node_type = ?" if node_type else ""
        params: list[Any] = [snapshot_type, snapshot_date, snapshot_type, snapshot_date]
        if node_type:
            params.append(node_type)
        params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT n.node_id, n.node_type, n.node_name,
                       SUM(d.weight) AS weighted_degree, COUNT(*) AS degree
                FROM (
                    SELECT source_node_id AS node_id, weight FROM graph_edges
                     WHERE snapshot_type = ? AND trade_date = ?
                    UNION ALL
                    SELECT target_node_id AS node_id, weight FROM graph_edges
                     WHERE snapshot_type = ? AND trade_date = ?
                ) d
                JOIN graph_nodes n ON n.node_id = d.node_id
                WHERE 1 = 1 {type_filter}
                GROUP BY n.node_id
                ORDER BY weighted_degree DESC, degree DESC, n.node_id ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            {
                "node_id": row["node_id"],
                "node_type": row["node_type"],
                "node_name": row["node_name"],
                "weighted_degree": round(float(row["weighted_degree"] or 0.0), 2),
                "degree": int(row["degree"] or 0),
            }
            for row in rows
        ]

    def neighbors(self, node_id: str, limit: int = 50, snapshot_type: str | None = None) -> dict[str, Any]:
        self.initialize()
        type_filter = "AND e.snapshot_type = ?" if snapshot_type else ""
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT e.source_node_id, e.target_node_id, e.edge_type, e.weight, e.snapshot_type, e.trade_date,
                       n.node_name, n.node_type
                FROM graph_edges e
                LEFT JOIN graph_nodes n
                       ON n.node_id = CASE WHEN e.source_node_id = ? THEN e.target_node_id ELSE e.source_node_id END
                WHERE (e.source_node_id = ? OR e.target_node_id = ?) {type_filter}
                ORDER BY e.weight DESC,
                         CASE WHEN e.source_node_id = ? THEN e.target_node_id ELSE e.source_node_id END ASC
                LIMIT ?
                """,
                [node_id, node_id, node_id, *([snapshot_type] if snapshot_type else []), node_id, limit],
            ).fetchall()
        neighbors = []
        for row in rows:
            other = row["target_node_id"] if row["source_node_id"] == node_id else row["source_node_id"]
            neighbors.append(
                {
                    "node_id": other,
                    "node_name": row["node_name"],
                    "node_type": row["node_type"],
                    "edge_type": row["edge_type"],
                    "weight": round(float(row["weight"] or 0.0), 2),
                    "snapshot_type": row["snapshot_type"],
                    "trade_date": row["trade_date"],
                }
            )
        return {"node_id": node_id, "neighbor_count": len(neighbors), "neighbors": neighbors}

    def shortest_path(
        self,
        source_node_id: str,
        target_node_id: str,
        max_depth: int = 4,
        snapshot_type: str | None = None,
    ) -> dict[str, Any]:
        edges = self._all_edges(snapshot_type)
        path = bfs_shortest_path(edges, source_node_id, target_node_id, max_depth=max_depth)
        return {
            "source": source_node_id,
            "target": target_node_id,
            "found": bool(path),
            "path": path,
            "edge_types": edge_types_on_path(edges, path),
            "hops": max(0, len(path) - 1),
            "length": max(0, len(path) - 1),
            "max_depth": max_depth,
        }

    def node_names(self, node_ids: list[str]) -> dict[str, str]:
        if not node_ids:
            return {}
        self.initialize()
        placeholders = ",".join("?" for _ in node_ids)
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT node_id, node_name FROM graph_nodes WHERE node_id IN ({placeholders})",
                tuple(node_ids),
            ).fetchall()
        return {row["node_id"]: row["node_name"] for row in rows}

    def _all_edges(self, snapshot_type: str | None) -> list[dict[str, Any]]:
        self.initialize()
        sql = "SELECT source_node_id, target_node_id, edge_type, weight FROM graph_edges"
        params: tuple[Any, ...] = ()
        if snapshot_type:
            sql += " WHERE snapshot_type = ?"
            params = (snapshot_type,)
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "source": row["source_node_id"],
                "target": row["target_node_id"],
                "edge_type": row["edge_type"],
                "weight": float(row["weight"] or 0.0),
            }
            for row in rows
        ]


def _loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}
