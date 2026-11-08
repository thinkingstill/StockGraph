"""FalkorDB 图后端。

FalkorDB 是基于 Redis 模块的稀疏矩阵图数据库，用 Cypher 查询，适合做多跳资金链路挖掘。
这里把 `GraphSnapshot` 映射为：

- 节点：`(:Entity {node_id, node_type, node_key, node_name, attrs_json})`
- 边：关系类型取 `edge_type` 的大写净化形式，属性 `{snapshot_key, snapshot_type, trade_date, weight, attrs_json}`
- 快照元信息：`(:GraphSnapshot {snapshot_key, snapshot_type, snapshot_date, version, meta_json})`

`snapshot_key = "{snapshot_type}|{snapshot_date}"` 保证同一快照重复写入是幂等的。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from stockgraph.domain.graph.models import GraphEdge, GraphNode, GraphSnapshot
from stockgraph.infrastructure.graph.algorithms import bfs_shortest_path, edge_types_on_path
from stockgraph.infrastructure.graph.analytics import GraphAnalyticsMixin
from stockgraph.infrastructure.graph.base import GraphStoreError, GraphStoreStats

logger = logging.getLogger(__name__)

_REL_SANITIZER = re.compile(r"[^A-Za-z0-9_]")


def snapshot_key(snapshot_type: str, snapshot_date: str) -> str:
    return f"{snapshot_type}|{snapshot_date}"


def sanitize_rel_type(edge_type: str) -> str:
    """把任意 edge_type 转成合法的 Cypher 关系类型标识符。

    Cypher 的关系类型只接受 `[A-Za-z_][A-Za-z0-9_]*`，但业务里的 edge_type
    带中文（`seat_stock_买` / `seat_stock_卖`）。如果只是简单地把非法字符删掉，
    两者都会变成 `SEAT_STOCK`，于是同一对节点的买入/卖出两条边在 `MERGE` 时
    撞成一条——实测 609 张快照里少了 16075 条边。

    做法：先做可读的规范化；一旦清洗过程中丢了信息（出现非法字符），
    追加原始值的短哈希后缀，保证不同类型之间永不碰撞。原始值仍然完整保留在
    边的 `edge_type` 属性里，业务查询按属性过滤而不是按 `type(r)`。
    """
    raw = (edge_type or "related").strip()
    cleaned = _REL_SANITIZER.sub("_", raw).upper().strip("_")
    # 只要发生了字符替换，就说明有信息损失，必须补哈希以保持区分度
    lost_info = _REL_SANITIZER.search(raw) is not None or cleaned.upper() != raw.upper()
    if lost_info:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        cleaned = f"{cleaned}_{digest}" if cleaned else f"R_{digest}"
    if not cleaned:
        cleaned = "RELATED"
    if not cleaned[0].isalpha():
        cleaned = f"R_{cleaned}"
    return cleaned[:64]


class FalkorDBGraphStore(GraphAnalyticsMixin):
    backend = "falkordb"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        graph_name: str = "stockgraph",
        username: str | None = None,
        password: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.graph_name = graph_name
        self.username = username or None
        self.password = password or None
        self.timeout = timeout
        self._db = None
        self._graph = None
        self._initialized = False

    # ---------------------------------------------------------------- 连接

    def _connect(self):
        if self._graph is not None:
            return self._graph
        try:
            from falkordb import FalkorDB  # 延迟导入：未安装 falkordb 时不影响 SQLite 后端
        except ImportError as exc:  # pragma: no cover - 取决于运行环境
            raise GraphStoreError(
                "缺少 falkordb 客户端，请先安装：pip install falkordb"
            ) from exc

        kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "socket_timeout": self.timeout,
        }
        if self.password:
            kwargs["password"] = self.password
            kwargs["username"] = self.username or "falkordb"
        try:
            self._db = FalkorDB(**kwargs)
            self._graph = self._db.select_graph(self.graph_name)
            self._graph.query("RETURN 1")
        except Exception as exc:  # noqa: BLE001
            self._graph = None
            self._db = None
            raise GraphStoreError(f"FalkorDB 连接失败 {self.host}:{self.port} - {exc}") from exc
        return self._graph

    @property
    def graph(self):
        return self._connect()

    # FalkorDB 单次查询默认最多返回 10000 行（GRAPH.CONFIG RESULTSET_SIZE）。
    # 超过就**静默截断**——不报错、不告警。seat_stock 一类实际有 75960 条边，
    # 截断后 shortest_path / _edges_of_type 只在头 1 万条里找路，
    # 结论与 SQLite 不一致，而两边都不会报任何错。
    MAX_ROWS_PER_QUERY = 10000
    PAGE_SIZE = 5000

    def _query(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        try:
            result = self.graph.query(cypher, params or {})
        except GraphStoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GraphStoreError(f"FalkorDB 查询失败: {exc}\nCypher: {cypher[:300]}") from exc
        return result.result_set or []

    def _query_all(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        """自动分页取全量结果，绕开 RESULTSET_SIZE 静默截断。

        只在可能超过 1 万行的场景使用（全类型边扫描等）；
        带 LIMIT 的小查询仍走 `_query`，避免无谓的多次往返。
        调用方的 Cypher **不要自带 SKIP/LIMIT**，本方法会追加。
        """
        params = params or {}
        collected: list[list[Any]] = []
        offset = 0
        while True:
            paged = f"{cypher.rstrip().rstrip(';')} SKIP {offset} LIMIT {self.PAGE_SIZE}"
            rows = self._query(paged, params)
            collected.extend(rows)
            if len(rows) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE
            if offset > 5_000_000:  # 防御：避免异常数据把循环卡死
                logger.warning("FalkorDB 分页超过 500 万行，提前终止: %s", cypher[:120])
                break
        return collected

    # ---------------------------------------------------------------- 基础

    def initialize(self) -> None:
        if self._initialized:
            return
        # 全图几十万条边时，没有索引的邻居展开会直接超时。
        # 注意 FalkorDB 的索引语法要求关系必须带类型（`FOR ()-[r]-()` 不合法），
        # 所以关系侧只对已知的固定类型建索引；动态哈希类型的边靠模式匹配剪枝。
        statements = [
            "CREATE INDEX FOR (n:Entity) ON (n.node_id)",
            "CREATE INDEX FOR (n:Entity) ON (n.node_type)",
            "CREATE INDEX FOR (s:GraphSnapshot) ON (s.snapshot_key)",
        ]
        for rel_type in ("SEAT_STOCK", "SEAT_SEAT_COOCCURRENCE", "STOCK_STOCK_COOCCURRENCE"):
            statements.append(f"CREATE INDEX FOR ()-[r:{rel_type}]-() ON (r.snapshot_type)")
        for statement in statements:
            try:
                self._query(statement)
            except GraphStoreError as exc:
                # 索引已存在不是错误，重复执行必须幂等
                if "already indexed" not in str(exc):
                    logger.debug("创建索引跳过: %s -> %s", statement, str(exc)[:120])
        self._initialized = True

    def health(self) -> dict[str, Any]:
        info = {"backend": self.backend, "host": self.host, "port": self.port, "graph_name": self.graph_name}
        try:
            self._query("RETURN 1")
            stats = self.stats()
            return {"ok": True, **info, **stats.as_dict()}
        except GraphStoreError as exc:
            return {"ok": False, **info, "error": str(exc)}

    def stats(self) -> GraphStoreStats:
        self.initialize()
        nodes = self._query("MATCH (n:Entity) RETURN count(n)")
        edges = self._query("MATCH ()-[r]->() RETURN count(r)")
        snapshots = self._query("MATCH (s:GraphSnapshot) RETURN count(s)")
        return GraphStoreStats(
            backend=self.backend,
            graph_name=self.graph_name,
            node_count=int(nodes[0][0]) if nodes else 0,
            edge_count=int(edges[0][0]) if edges else 0,
            snapshot_count=int(snapshots[0][0]) if snapshots else 0,
        )

    # ---------------------------------------------------------------- 写入

    def save_snapshot(self, snapshot: GraphSnapshot) -> int:
        self.initialize()
        key = snapshot_key(snapshot.snapshot_type, snapshot.snapshot_date)

        self._query(
            """
            MERGE (s:GraphSnapshot {snapshot_key: $key})
            SET s.snapshot_type = $snapshot_type,
                s.snapshot_date = $snapshot_date,
                s.version = $version,
                s.meta_json = $meta_json
            """,
            {
                "key": key,
                "snapshot_type": snapshot.snapshot_type,
                "snapshot_date": snapshot.snapshot_date,
                "version": snapshot.version,
                "meta_json": json.dumps(snapshot.metadata, ensure_ascii=False),
            },
        )

        node_rows = [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "node_key": node.node_key,
                "node_name": node.node_name,
                "attrs_json": json.dumps(node.attributes, ensure_ascii=False),
            }
            for node in snapshot.nodes
        ]
        for chunk in _chunks(node_rows, 1000):
            self._query(
                """
                UNWIND $rows AS row
                MERGE (n:Entity {node_id: row.node_id})
                SET n.node_type = row.node_type,
                    n.node_key = row.node_key,
                    n.node_name = CASE WHEN row.node_name = '' THEN n.node_name ELSE row.node_name END,
                    n.attrs_json = CASE
                        WHEN row.attrs_json IN ['{}', ''] THEN n.attrs_json
                        ELSE row.attrs_json
                    END
                """,
                {"rows": chunk},
            )

        # 幂等：先清掉同一快照的旧边，再写入
        self._query(
            "MATCH ()-[r {snapshot_key: $key}]->() DELETE r",
            {"key": key},
        )

        grouped: dict[str, list[dict[str, Any]]] = {}
        for edge in snapshot.edges:
            # 自环在 Cypher 里是零长度路径，MERGE 无法建边，统计也会漏算，
            # 与 SQLite 侧保持一致：直接丢弃
            if edge.source_node_id == edge.target_node_id:
                continue
            rel = sanitize_rel_type(edge.edge_type)
            grouped.setdefault(rel, []).append(
                {
                    "source": edge.source_node_id,
                    "target": edge.target_node_id,
                    "edge_type": edge.edge_type,
                    "weight": float(edge.weight or 0.0),
                    "trade_date": edge.trade_date or snapshot.snapshot_date,
                    "attrs_json": json.dumps(edge.attributes, ensure_ascii=False),
                }
            )

        written = 0
        for rel_type, rows in grouped.items():
            for chunk in _chunks(rows, 500):
                self._query(
                    f"""
                    UNWIND $rows AS row
                    MATCH (a:Entity {{node_id: row.source}})
                    MATCH (b:Entity {{node_id: row.target}})
                    MERGE (a)-[r:{rel_type} {{snapshot_key: $key}}]->(b)
                    SET r.edge_type = row.edge_type,
                        r.snapshot_type = $snapshot_type,
                        r.trade_date = row.trade_date,
                        r.weight = row.weight,
                        r.attrs_json = row.attrs_json
                    """,
                    {"rows": chunk, "key": key, "snapshot_type": snapshot.snapshot_type},
                )
                written += len(chunk)
        return written

    def _edges_of_type(self, snapshot_type: str) -> list[dict[str, Any]]:
        """取某类图在所有快照下的边，结构与 `fetch_edges` 一致。

        必须用 `_query_all`：单类型边可达数万条，超过 FalkorDB 的 1 万行上限后
        会被静默截断，导致最短路等分析只在部分数据上做。
        """
        self.initialize()
        rows = self._query_all(
            """
            MATCH (a:Entity)-[r {snapshot_type: $st}]->(b:Entity)
            RETURN a.node_id, b.node_id, r.edge_type, r.weight, r.trade_date, r.snapshot_type
            ORDER BY a.node_id, b.node_id
            """,
            {"st": snapshot_type},
        )
        return [
            {
                "source": row[0],
                "target": row[1],
                "edge_type": row[2],
                "weight": float(row[3] or 0.0),
                "trade_date": row[4],
                "snapshot_type": row[5],
            }
            for row in rows
        ]

    def delete_snapshot(self, snapshot_type: str, snapshot_date: str) -> int:
        self.initialize()
        key = snapshot_key(snapshot_type, snapshot_date)
        counted = self._query("MATCH ()-[r {snapshot_key: $key}]->() RETURN count(r)", {"key": key})
        removed = int(counted[0][0]) if counted else 0
        self._query("MATCH ()-[r {snapshot_key: $key}]->() DELETE r", {"key": key})
        self._query("MATCH (s:GraphSnapshot {snapshot_key: $key}) DELETE s", {"key": key})
        self._query("MATCH (n:Entity) WHERE NOT (n)--() DELETE n")
        return removed

    # ---------------------------------------------------------------- 读取

    def load_snapshot(self, snapshot_type: str, snapshot_date: str) -> GraphSnapshot | None:
        self.initialize()
        key = snapshot_key(snapshot_type, snapshot_date)
        meta_rows = self._query(
            "MATCH (s:GraphSnapshot {snapshot_key: $key}) RETURN s.version, s.meta_json",
            {"key": key},
        )
        edge_rows = self.fetch_edges(snapshot_type, snapshot_date)
        if not meta_rows and not edge_rows:
            return None

        node_ids: set[str] = set()
        edges: list[GraphEdge] = []
        for row in edge_rows:
            node_ids.add(row["source"])
            node_ids.add(row["target"])
            edges.append(
                GraphEdge(
                    source_node_id=row["source"],
                    target_node_id=row["target"],
                    edge_type=row["edge_type"],
                    weight=float(row["weight"] or 0.0),
                    trade_date=row.get("trade_date") or "",
                    attributes=row.get("attributes") or {},
                )
            )

        nodes = self._fetch_nodes(list(node_ids))
        version = "v1"
        metadata: dict[str, Any] = {}
        if meta_rows:
            version = meta_rows[0][0] or "v1"
            metadata = _loads(meta_rows[0][1])
        return GraphSnapshot(
            snapshot_date=snapshot_date,
            snapshot_type=snapshot_type,
            version=version,
            nodes=nodes,
            edges=edges,
            metadata=metadata,
        )

    def _fetch_nodes(self, node_ids: list[str]) -> list[GraphNode]:
        if not node_ids:
            return []
        nodes: list[GraphNode] = []
        for chunk in _chunks(node_ids, 2000):
            rows = self._query(
                """
                MATCH (n:Entity) WHERE n.node_id IN $ids
                RETURN n.node_id, n.node_type, n.node_key, n.node_name, n.attrs_json
                """,
                {"ids": chunk},
            )
            for row in rows:
                nodes.append(
                    GraphNode(
                        node_id=row[0],
                        node_type=row[1],
                        node_key=row[2],
                        node_name=row[3],
                        attributes=_loads(row[4]),
                    )
                )
        return nodes

    def list_snapshots(self) -> list[dict[str, Any]]:
        self.initialize()
        # 不能用 OPTIONAL MATCH ()-[r {snapshot_key: s.snapshot_key}]->()：
        # FalkorDB 不支持无类型关系索引（`FOR ()-[r]-()` 语法直接报错），
        # 那个写法会对每个快照全扫一遍边，609 张快照 × 44 万条边要几分钟。
        # 改成一次全边聚合拿到 snapshot_key -> 边数，再和快照节点做左连接，实测 0.4 秒。
        meta_rows = self._query(
            """
            MATCH (s:GraphSnapshot)
            RETURN s.snapshot_type, s.snapshot_date, s.version, s.meta_json, s.snapshot_key
            ORDER BY s.snapshot_date DESC
            """
        )
        counts = {
            str(row[0]): int(row[1] or 0)
            for row in self._query(
                "MATCH ()-[r]->() WITH r.snapshot_key AS k, count(r) AS c RETURN k, c"
            )
            if row[0]
        }
        return [
            {
                "snapshot_type": row[0],
                "snapshot_date": row[1],
                "version": row[2],
                "metadata": _loads(row[3]),
                "edge_count": counts.get(str(row[4]), 0),
            }
            for row in meta_rows
        ]

    def snapshot_stats(self, snapshot_type: str, snapshot_date: str) -> dict[str, Any]:
        key = snapshot_key(snapshot_type, snapshot_date)
        rows = self._query(
            """
            MATCH (a:Entity)-[r {snapshot_key: $key}]->(b:Entity)
            WITH collect(a.node_id) + collect(b.node_id) AS ids, count(r) AS ec
            UNWIND ids AS nid
            RETURN ec, count(DISTINCT nid)
            """,
            {"key": key},
        )
        edge_count = int(rows[0][0]) if rows else 0
        node_count = int(rows[0][1]) if rows else 0
        return {
            "snapshot_type": snapshot_type,
            "snapshot_date": snapshot_date,
            "node_count": node_count,
            "edge_count": edge_count,
        }

    def fetch_edges(self, snapshot_type: str, snapshot_date: str) -> list[dict[str, Any]]:
        self.initialize()
        key = snapshot_key(snapshot_type, snapshot_date)
        rows = self._query(
            """
            MATCH (a:Entity)-[r {snapshot_key: $key}]->(b:Entity)
            RETURN a.node_id, b.node_id, r.edge_type, r.weight, r.trade_date, r.attrs_json
            """,
            {"key": key},
        )
        return [
            {
                "source": row[0],
                "target": row[1],
                "edge_type": row[2],
                "weight": float(row[3] or 0.0),
                "trade_date": row[4],
                "attributes": _loads(row[5]),
            }
            for row in rows
        ]

    def node_names(self, node_ids: list[str]) -> dict[str, str]:
        if not node_ids:
            return {}
        result: dict[str, str] = {}
        for chunk in _chunks(node_ids, 2000):
            rows = self._query(
                "MATCH (n:Entity) WHERE n.node_id IN $ids RETURN n.node_id, n.node_name",
                {"ids": chunk},
            )
            result.update({row[0]: row[1] for row in rows})
        return result

    def top_nodes(
        self,
        snapshot_type: str,
        snapshot_date: str,
        limit: int = 20,
        node_type: str | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        key = snapshot_key(snapshot_type, snapshot_date)
        type_filter = "AND n.node_type = $node_type" if node_type else ""
        params: dict[str, Any] = {"key": key, "limit": limit}
        if node_type:
            params["node_type"] = node_type
        rows = self._query(
            f"""
            MATCH (n:Entity)-[r {{snapshot_key: $key}}]-(m:Entity)
            WHERE 1 = 1 {type_filter}
            RETURN n.node_id, n.node_type, n.node_name, sum(r.weight), count(r)
            ORDER BY sum(r.weight) DESC, count(r) DESC, n.node_id ASC
            LIMIT $limit
            """,
            params,
        )
        return [
            {
                "node_id": row[0],
                "node_type": row[1],
                "node_name": row[2],
                "weighted_degree": round(float(row[3] or 0.0), 2),
                "degree": int(row[4] or 0),
            }
            for row in rows
        ]

    def neighbors(self, node_id: str, limit: int = 50, snapshot_type: str | None = None) -> dict[str, Any]:
        self.initialize()
        params: dict[str, Any] = {"node_id": node_id, "limit": max(1, int(limit))}
        if snapshot_type:
            # 把类型条件下推进关系模式，让引擎在展开时就能剪枝；
            # 放到 WHERE 里会先展开全部关系再过滤，全图 44 万条边时会超时
            pattern = "(n:Entity {node_id: $node_id})-[r {snapshot_type: $snapshot_type}]-(m:Entity)"
            params["snapshot_type"] = snapshot_type
        else:
            pattern = "(n:Entity {node_id: $node_id})-[r]-(m:Entity)"

        rows = self._query(
            f"""
            MATCH {pattern}
            RETURN m.node_id, m.node_name, m.node_type, r.edge_type, r.weight, r.snapshot_type, r.trade_date
            ORDER BY r.weight DESC, m.node_id ASC
            LIMIT $limit
            """,
            params,
        )
        neighbors = [
            {
                "node_id": row[0],
                "node_name": row[1],
                "node_type": row[2],
                "edge_type": row[3],
                "weight": round(float(row[4] or 0.0), 2),
                "snapshot_type": row[5],
                "trade_date": row[6],
            }
            for row in rows
        ]
        return {"node_id": node_id, "neighbor_count": len(neighbors), "neighbors": neighbors}

    def shortest_path(
        self,
        source_node_id: str,
        target_node_id: str,
        max_depth: int = 4,
        snapshot_type: str | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        depth = max(1, min(int(max_depth), 8))
        empty = {
            "source": source_node_id,
            "target": target_node_id,
            "found": False,
            "path": [],
            "edge_types": [],
            "hops": 0,
            "length": 0,
            "max_depth": depth,
        }

        # 指定类型时的语义与 SQLite 对齐：在**该类型下所有快照的边**里找路。
        # FalkorDB 的 RETURN shortestPath 无法附加边过滤条件，所以走同口径的本地 BFS。
        # 之前只取 list_snapshots()[0]（最新一天），导致「昨天连过的两只股票」查不到路径。
        if snapshot_type:
            edges = self._edges_of_type(snapshot_type)
            if not edges:
                return empty
            path = bfs_shortest_path(edges, source_node_id, target_node_id, max_depth=depth)
            return {
                **empty,
                "found": bool(path),
                "path": path,
                "edge_types": edge_types_on_path(edges, path),
                "hops": max(0, len(path) - 1),
                "length": max(0, len(path) - 1),
            }

        cypher = f"""
        MATCH (a:Entity {{node_id: $source}}), (b:Entity {{node_id: $target}})
        RETURN shortestPath((a)-[*1..{depth}]-(b)) AS p
        LIMIT 1
        """
        try:
            rows = self._query(
                cypher, {"source": source_node_id, "target": target_node_id}
            )
        except GraphStoreError as exc:
            logger.warning("FalkorDB 最短路径查询失败: %s", exc)
            return empty
        if not rows or rows[0][0] is None:
            return empty

        path_obj = rows[0][0]
        try:
            node_ids = [node.properties.get("node_id") for node in path_obj.nodes()]
            edge_types = [edge.properties.get("edge_type") for edge in path_obj.edges()]
        except AttributeError:  # pragma: no cover - 客户端返回格式变化时兜底
            return empty

        return {
            "source": source_node_id,
            "target": target_node_id,
            "found": True,
            "path": node_ids,
            "edge_types": edge_types,
            "hops": max(0, len(node_ids) - 1),
            "length": max(0, len(node_ids) - 1),
            "max_depth": depth,
        }

    # ---------------------------------------------------------------- 维护

    def clear(self) -> None:
        self.initialize()
        self._query("MATCH (n) DETACH DELETE n")


def _chunks(items: list[Any], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}
