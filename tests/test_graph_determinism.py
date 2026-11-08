"""图分析结果的确定性回归测试。

两个真实踩过的坑，共同特点是**不报错、只是结果悄悄变了**：

1. FalkorDB 单次查询默认最多返回 10000 行，超过静默截断。
   seat_stock 类型实际 75960 条边，`_edges_of_type` 只拿到 1 万条，
   最短路只在 13% 的数据里找路，返回 found=false 而 SQLite 明明有直接边。

2. PageRank / top_nodes 只按分数排序。同分节点（营业部重名很常见，
   权重精确相等到小数点后 8 位）名次随后端返回顺序漂移，
   实测第 40 名两张报表互换。

这些用例不依赖真实 FalkorDB 连接，只验证排序与分页逻辑本身。
"""

from __future__ import annotations

from stockgraph.infrastructure.graph.algorithms import pagerank


def test_pagerank_ties_are_ordered_by_node_id():
    """构造完全对称的图，所有节点分数相同，顺序必须按 node_id 稳定。"""
    # 一个环形：每个节点入度出度权重都一致 -> PageRank 必然同分
    ring = ["n:05", "n:03", "n:01", "n:04", "n:02"]
    edges = [
        {"source": ring[i], "target": ring[(i + 1) % len(ring)], "edge_type": "e", "weight": 1.0}
        for i in range(len(ring))
    ]
    ranks = pagerank(edges)
    scores = {round(v, 10) for v in ranks.values()}
    assert len(scores) == 1, "环形图应当所有节点同分"

    # 复现 analytics.pagerank 的排序键：-score, node_id
    ordered = sorted(ranks.items(), key=lambda item: (-item[1], item[0]))
    assert [n for n, _ in ordered] == sorted(ring), "同分时必须回退到 node_id 升序"


def test_pagerank_order_is_input_order_independent():
    """打乱边输入顺序，排序结果必须完全一致。"""
    edges = []
    for i in range(6):
        edges.append({"source": f"s:{i}", "target": "s:0", "edge_type": "e", "weight": 1.0})
    forward = sorted(pagerank(edges).items(), key=lambda kv: (-kv[1], kv[0]))
    backward = sorted(pagerank(list(reversed(edges))).items(), key=lambda kv: (-kv[1], kv[0]))
    assert [n for n, _ in forward] == [n for n, _ in backward]


def test_falkordb_paged_query_appends_skip_limit():
    """_query_all 必须在原 Cypher 后追加 SKIP/LIMIT，且不破坏已有语义。"""
    from stockgraph.infrastructure.graph.falkordb_store import FalkorDBGraphStore

    calls: list[str] = []

    class FakeStore(FalkorDBGraphStore):
        def __init__(self):  # noqa: D107 - 跳过真实连接
            self.PAGE_SIZE = 3
            self._initialized = True

        def _query(self, cypher, params=None):  # noqa: D102
            calls.append(cypher)
            # 第一页满 3 条触发翻页，第二页只回 1 条结束
            return [[1], [2], [3]] if len(calls) == 1 else [[4]]

    store = FakeStore()
    rows = store._query_all("MATCH (n) RETURN n")
    assert len(rows) == 4
    assert "SKIP 0 LIMIT 3" in calls[0]
    assert "SKIP 3 LIMIT 3" in calls[1]


def test_falkordb_paged_query_stops_on_short_page():
    """返回行数不足一页就应停止，不能多打一次空查询。"""
    from stockgraph.infrastructure.graph.falkordb_store import FalkorDBGraphStore

    calls: list[str] = []

    class FakeStore(FalkorDBGraphStore):
        def __init__(self):  # noqa: D107
            self.PAGE_SIZE = 10
            self._initialized = True

        def _query(self, cypher, params=None):  # noqa: D102
            calls.append(cypher)
            return [[1], [2]]

    store = FakeStore()
    rows = store._query_all("MATCH (n) RETURN n")
    assert len(rows) == 2
    assert len(calls) == 1, "短页后不应继续请求"
