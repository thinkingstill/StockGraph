"""后端无关的图算法。

刻意只用标准库实现，避免为一个可选能力（FalkorDB）引入 networkx 这类重依赖。
算法输入统一是 `fetch_edges` 返回的边列表，因此 SQLite 与 FalkorDB 共用同一套数值结果。
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Iterable


def degree_centrality(edges: Iterable[dict[str, Any]]) -> dict[str, float]:
    degree: dict[str, float] = defaultdict(float)
    for edge in edges:
        weight = float(edge.get("weight") or 1.0)
        degree[str(edge["source"])] += weight
        degree[str(edge["target"])] += weight
    return dict(degree)


def pagerank(
    edges: Iterable[dict[str, Any]],
    *,
    damping: float = 0.85,
    iterations: int = 40,
    tolerance: float = 1e-8,
    weight_field: str = "weight",
) -> dict[str, float]:
    """加权 PageRank。

    权重必须为正，否则退化为无权图；迭代到 L1 收敛或达到上限。
    """
    edge_list = list(edges)
    nodes: set[str] = set()
    out_weight: dict[str, float] = defaultdict(float)
    out_links: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for edge in edge_list:
        source = str(edge["source"])
        target = str(edge["target"])
        weight = float(edge.get(weight_field) or 0.0)
        if weight <= 0:
            weight = 1.0
        nodes.add(source)
        nodes.add(target)
        out_links[source].append((target, weight))
        out_weight[source] += weight

    if not nodes:
        return {}

    total = float(len(nodes))
    ranks = {node: 1.0 / total for node in nodes}
    # 悬挂节点（无出边）的权重按全图均分，避免权重泄漏
    dangling = [node for node in nodes if out_weight.get(node, 0.0) <= 0]

    for _ in range(max(1, iterations)):
        new_ranks = {node: (1.0 - damping) / total for node in nodes}
        dangling_share = damping * sum(ranks[node] for node in dangling) / total
        if dangling_share:
            for node in nodes:
                new_ranks[node] += dangling_share
        for source, links in out_links.items():
            source_weight = ranks[source]
            if source_weight <= 0:
                continue
            denom = out_weight[source]
            for target, weight in links:
                new_ranks[target] += damping * source_weight * (weight / denom)
        delta = sum(abs(new_ranks[node] - ranks[node]) for node in nodes)
        ranks = new_ranks
        if delta < tolerance:
            break

    return {node: round(value, 8) for node, value in ranks.items()}


def label_propagation_communities(
    edges: Iterable[dict[str, Any]],
    *,
    max_iterations: int = 30,
    min_size: int = 2,
) -> dict[str, str]:
    """标签传播社区发现（LPA）。

    返回 node_id -> community_id。同步更新 + 稳定顺序，保证同一输入结果可复现；
    这比随机顺序版本更适合入库存档与前后端对齐。
    """
    adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for edge in edges:
        source = str(edge["source"])
        target = str(edge["target"])
        weight = float(edge.get("weight") or 1.0)
        if weight <= 0:
            weight = 1.0
        adjacency[source].append((target, weight))
        adjacency[target].append((source, weight))

    labels = {node: node for node in adjacency}
    if not labels:
        return {}

    for _ in range(max(1, max_iterations)):
        changed = False
        for node in sorted(labels):
            scores: dict[str, float] = defaultdict(float)
            for neighbor, weight in adjacency[node]:
                scores[labels[neighbor]] += weight
            if not scores:
                continue
            # 同分时取字典序最小的标签，保证确定性
            best_label, best_score = min(
                scores.items(), key=lambda item: (-item[1], item[0])
            )
            if best_score > scores.get(labels[node], 0.0) or (
                best_score == scores.get(labels[node], 0.0) and best_label < labels[node]
            ):
                if labels[node] != best_label:
                    labels[node] = best_label
                    changed = True
        if not changed:
            break

    # 收敛后按社区规模重新编号，小的并入噪声社区 0
    sizes: dict[str, int] = defaultdict(int)
    for label in labels.values():
        sizes[label] += 1
    order = sorted(sizes.items(), key=lambda item: (-item[1], item[0]))
    mapping: dict[str, str] = {}
    next_id = 1
    for label, size in order:
        if size < min_size:
            mapping[label] = "0"
            continue
        mapping[label] = f"c{next_id}"
        next_id += 1
    return {node: mapping[label] for node, label in labels.items()}


def bfs_shortest_path(edges: Iterable[dict[str, Any]], source: str, target: str, max_depth: int = 4) -> list[str]:
    """无权最短路径；返回节点序列，找不到返回空列表。"""
    if source == target:
        return [source]
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        a = str(edge["source"])
        b = str(edge["target"])
        adjacency[a].append(b)
        adjacency[b].append(a)

    queue: deque[tuple[str, list[str]]] = deque([(source, [source])])
    visited = {source}
    while queue:
        node, path = queue.popleft()
        # path 长度即起点到该节点的跳数；已用满 max_depth 的节点不再扩展
        if len(path) - 1 >= max_depth:
            continue
        for neighbor in sorted(adjacency.get(node, [])):
            if neighbor in visited:
                continue
            if neighbor == target:
                return [*path, neighbor]
            visited.add(neighbor)
            queue.append((neighbor, [*path, neighbor]))
    return []


def connected_components(edges: Iterable[dict[str, Any]]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        a = str(edge["source"])
        b = str(edge["target"])
        adjacency[a].add(b)
        adjacency[b].add(a)

    seen: set[str] = set()
    components: list[list[str]] = []
    for node in sorted(adjacency):
        if node in seen:
            continue
        stack = [node]
        component: list[str] = []
        seen.add(node)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    components.sort(key=len, reverse=True)
    return components


def edge_types_on_path(edges: Iterable[dict[str, Any]], path: list[str]) -> list[str]:
    """按路径顺序取出每一跳的 edge_type。

    两种后端共用：保证 `shortest_path()` 返回结构完全一致。
    """
    if len(path) < 2:
        return []
    # 同一对节点可能同时存在买入/卖出等多条边，取权重最大的那条，
    # 否则结果会依赖遍历顺序 —— SQLite 与 FalkorDB 就会给出不同的 edge_types。
    lookup: dict[tuple[str, str], tuple[float, str]] = {}
    for edge in edges:
        source = str(edge["source"])
        target = str(edge["target"])
        edge_type = str(edge.get("edge_type") or "")
        weight = float(edge.get("weight") or 0.0)
        for key in ((source, target), (target, source)):
            current = lookup.get(key)
            if current is None or weight > current[0]:
                lookup[key] = (weight, edge_type)
    return [lookup.get((path[i], path[i + 1]), (0.0, ""))[1] for i in range(len(path) - 1)]
