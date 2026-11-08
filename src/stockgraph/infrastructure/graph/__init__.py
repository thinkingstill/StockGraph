"""图存储层。

对外只暴露 `create_graph_store()` 与 `GraphStore` 协议，具体后端由配置决定：

- 默认：SQLite（零依赖，与历史数据兼容）
- 可选：FalkorDB（Cypher 多跳查询，适合资金链路挖掘）
- 切换：`python scripts/graph_backend.py switch falkordb`
"""

from stockgraph.infrastructure.graph.algorithms import (
    bfs_shortest_path,
    connected_components,
    degree_centrality,
    label_propagation_communities,
    pagerank,
)
from stockgraph.infrastructure.graph.analytics import GraphAnalyticsMixin
from stockgraph.infrastructure.graph.base import GraphStore, GraphStoreError, GraphStoreStats
from stockgraph.infrastructure.graph.config import (
    SUPPORTED_BACKENDS,
    GraphSettings,
    load_config,
    resolve_settings,
    save_config,
    switch_backend,
)
from stockgraph.infrastructure.graph.factory import (
    backend_status,
    build_falkordb_store,
    build_sqlite_store,
    create_graph_store,
    reset_cache,
)

__all__ = [
    "SUPPORTED_BACKENDS",
    "GraphAnalyticsMixin",
    "GraphSettings",
    "GraphStore",
    "GraphStoreError",
    "GraphStoreStats",
    "backend_status",
    "bfs_shortest_path",
    "build_falkordb_store",
    "build_sqlite_store",
    "connected_components",
    "create_graph_store",
    "degree_centrality",
    "label_propagation_communities",
    "load_config",
    "pagerank",
    "reset_cache",
    "resolve_settings",
    "save_config",
    "switch_backend",
]
