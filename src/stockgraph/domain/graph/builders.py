from __future__ import annotations

from collections import defaultdict

from stockgraph.domain.graph.models import GraphEdge, GraphNode, GraphSnapshot


def build_stock_seat_bipartite_graph(records: list[dict], snapshot_date: str, snapshot_type: str = "seat_stock") -> GraphSnapshot:
    node_map: dict[str, GraphNode] = {}
    edge_map: dict[tuple[str, str, str, str], GraphEdge] = {}

    for row in records:
        seat_id = f"seat:{row['seat_name']}"
        stock_id = f"stock:{row['stock_code']}"
        node_map.setdefault(
            seat_id,
            GraphNode(
                node_id=seat_id,
                node_type="seat",
                node_key=row["seat_name"],
                node_name=row["seat_name"],
                attributes={"seat_type": row.get("seat_type"), "trader_alias": row.get("trader_alias")},
            ),
        )
        node_map.setdefault(
            stock_id,
            GraphNode(
                node_id=stock_id,
                node_type="stock",
                node_key=row["stock_code"],
                node_name=row["stock_name"],
                attributes={"stock_code": row["stock_code"]},
            ),
        )

        key = (seat_id, stock_id, row["direction"], row["date"])
        if key not in edge_map:
            edge_map[key] = GraphEdge(
                source_node_id=seat_id,
                target_node_id=stock_id,
                edge_type=f"seat_stock_{row['direction']}",
                weight=0.0,
                trade_date=row["date"],
                attributes={"direction": row["direction"], "count": 0},
            )
        edge_map[key].weight += float(row.get("amount") or 0)
        edge_map[key].attributes["count"] += 1

    return GraphSnapshot(
        snapshot_date=snapshot_date,
        snapshot_type=snapshot_type,
        nodes=list(node_map.values()),
        edges=list(edge_map.values()),
        metadata={"record_count": len(records)},
    )


def build_trader_seat_projection(records: list[dict], snapshot_date: str) -> GraphSnapshot:
    """席位共现图：同一交易日参与同一只股票的席位两两连边。

    必须按席位名去重再配对。同一席位在同一只股票上经常同时有买入和卖出两条记录，
    不去重就会生成 `seat:X -> seat:X` 的自环边——这种边没有任何分析意义，
    还会在 Cypher 里变成零长度路径，导致 SQLite 与 FalkorDB 的边数对不上。
    """
    cooccurrence: dict[tuple[str, str], dict] = defaultdict(lambda: {"weight": 0.0, "stocks": set(), "dates": set()})
    grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in records:
        key = (row["date"], row["stock_code"])
        seat = row["seat_name"]
        # 同一席位在多条记录里出现时，取该席位在该股票上的最大金额作为配对权重
        grouped[key][seat] = max(
            grouped[key].get(seat, 0.0), float(row.get("amount") or 0.0)
        )

    nodes: dict[str, GraphNode] = {}
    for (day, _stock), seat_amounts in grouped.items():
        seats = list(seat_amounts)
        for seat in seats:
            nodes.setdefault(
                f"seat:{seat}",
                GraphNode(node_id=f"seat:{seat}", node_type="seat", node_key=seat, node_name=seat),
            )
        for idx, left in enumerate(seats):
            for right in seats[idx + 1:]:
                if left == right:
                    continue
                pair = tuple(sorted((left, right)))
                cooccurrence[pair]["weight"] += min(seat_amounts[left], seat_amounts[right])
                cooccurrence[pair]["stocks"].add(_stock)
                cooccurrence[pair]["dates"].add(day)

    edges = [
        GraphEdge(
            source_node_id=f"seat:{left}",
            target_node_id=f"seat:{right}",
            edge_type="seat_seat_cooccurrence",
            weight=payload["weight"],
            trade_date=snapshot_date,
            attributes={"stock_count": len(payload["stocks"]), "date_count": len(payload["dates"])},
        )
        for (left, right), payload in cooccurrence.items()
        if left != right
    ]
    return GraphSnapshot(snapshot_date=snapshot_date, snapshot_type="seat_projection", nodes=list(nodes.values()), edges=edges)


def build_stock_stock_projection(records: list[dict], snapshot_date: str) -> GraphSnapshot:
    """股票共现图：同一交易日被同一席位操作的股票两两连边。

    同样按股票代码去重，避免 `stock:X -> stock:X` 自环。
    """
    cooccurrence: dict[tuple[str, str], dict] = defaultdict(lambda: {"weight": 0.0, "seats": set(), "dates": set()})
    grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in records:
        key = (row["date"], row["seat_name"])
        code = row["stock_code"]
        grouped[key][code] = max(grouped[key].get(code, 0.0), float(row.get("amount") or 0.0))

    nodes: dict[str, GraphNode] = {}
    name_by_code: dict[str, str] = {}
    for row in records:
        name_by_code.setdefault(row["stock_code"], row["stock_name"])

    for (_day, _seat), stock_amounts in grouped.items():
        codes = list(stock_amounts)
        for row in records:
            if row["stock_code"] in stock_amounts:
                nodes.setdefault(
                    f"stock:{row['stock_code']}",
                    GraphNode(
                        node_id=f"stock:{row['stock_code']}",
                        node_type="stock",
                        node_key=row["stock_code"],
                        node_name=row["stock_name"],
                    ),
                )
        for idx, left in enumerate(codes):
            for right in codes[idx + 1:]:
                if left == right:
                    continue
                pair = tuple(sorted((left, right)))
                cooccurrence[pair]["weight"] += min(stock_amounts[left], stock_amounts[right])
                cooccurrence[pair]["seats"].add(_seat)
                cooccurrence[pair]["dates"].add(_day)

    edges = [
        GraphEdge(
            source_node_id=f"stock:{left}",
            target_node_id=f"stock:{right}",
            edge_type="stock_stock_cooccurrence",
            weight=payload["weight"],
            trade_date=snapshot_date,
            attributes={"seat_count": len(payload["seats"]), "date_count": len(payload["dates"])},
        )
        for (left, right), payload in cooccurrence.items()
        if left != right
    ]
    return GraphSnapshot(snapshot_date=snapshot_date, snapshot_type="stock_projection", nodes=list(nodes.values()), edges=edges)
