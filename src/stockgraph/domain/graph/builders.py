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
    cooccurrence: dict[tuple[str, str], dict] = defaultdict(lambda: {"weight": 0.0, "stocks": set(), "dates": set()})
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in records:
        grouped[(row["date"], row["stock_code"])].append(row)

    nodes: dict[str, GraphNode] = {}
    for rows in grouped.values():
        seats = [row["seat_name"] for row in rows]
        for seat in seats:
            nodes.setdefault(
                f"seat:{seat}",
                GraphNode(node_id=f"seat:{seat}", node_type="seat", node_key=seat, node_name=seat),
            )
        for idx, left in enumerate(rows):
            for right in rows[idx + 1:]:
                pair = tuple(sorted((left["seat_name"], right["seat_name"])))
                cooccurrence[pair]["weight"] += min(float(left.get("amount") or 0), float(right.get("amount") or 0))
                cooccurrence[pair]["stocks"].add(left["stock_code"])
                cooccurrence[pair]["dates"].add(left["date"])

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
    ]
    return GraphSnapshot(snapshot_date=snapshot_date, snapshot_type="seat_projection", nodes=list(nodes.values()), edges=edges)


def build_stock_stock_projection(records: list[dict], snapshot_date: str) -> GraphSnapshot:
    cooccurrence: dict[tuple[str, str], dict] = defaultdict(lambda: {"weight": 0.0, "seats": set(), "dates": set()})
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in records:
        grouped[(row["date"], row["seat_name"])].append(row)

    nodes: dict[str, GraphNode] = {}
    for rows in grouped.values():
        stocks = [row["stock_code"] for row in rows]
        for row in rows:
            nodes.setdefault(
                f"stock:{row['stock_code']}",
                GraphNode(
                    node_id=f"stock:{row['stock_code']}",
                    node_type="stock",
                    node_key=row["stock_code"],
                    node_name=row["stock_name"],
                ),
            )
        for idx, left in enumerate(rows):
            for right in rows[idx + 1:]:
                pair = tuple(sorted((left["stock_code"], right["stock_code"])))
                cooccurrence[pair]["weight"] += min(float(left.get("amount") or 0), float(right.get("amount") or 0))
                cooccurrence[pair]["seats"].add(left["seat_name"])
                cooccurrence[pair]["dates"].add(left["date"])

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
    ]
    return GraphSnapshot(snapshot_date=snapshot_date, snapshot_type="stock_projection", nodes=list(nodes.values()), edges=edges)
