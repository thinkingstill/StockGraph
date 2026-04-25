from __future__ import annotations

from stockgraph.domain.graph import (
    build_stock_seat_bipartite_graph,
    build_stock_stock_projection,
    build_trader_seat_projection,
    summarize_graph,
)
from stockgraph.infrastructure.db.repositories import DragonTigerRepository, GraphRepository


class NetworkAnalysisService:
    def __init__(
        self,
        dragon_tiger_repository: DragonTigerRepository | None = None,
        graph_repository: GraphRepository | None = None,
    ) -> None:
        self.dragon_tiger_repository = dragon_tiger_repository or DragonTigerRepository()
        self.graph_repository = graph_repository or GraphRepository()

    def build_stock_seat_projection(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        persist: bool = False,
    ) -> dict:
        records = self.dragon_tiger_repository.list_operations(start_date=start_date, end_date=end_date)
        snapshot_date = end_date or start_date or "all"
        snapshot = build_stock_seat_bipartite_graph(records=records, snapshot_date=snapshot_date)
        if persist:
            self.graph_repository.save_snapshot(snapshot)
        return summarize_graph(snapshot)

    def build_seat_projection(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        persist: bool = False,
    ) -> dict:
        records = self.dragon_tiger_repository.list_operations(start_date=start_date, end_date=end_date)
        snapshot_date = end_date or start_date or "all"
        snapshot = build_trader_seat_projection(records=records, snapshot_date=snapshot_date)
        if persist:
            self.graph_repository.save_snapshot(snapshot)
        return summarize_graph(snapshot)

    def build_stock_projection(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        persist: bool = False,
    ) -> dict:
        records = self.dragon_tiger_repository.list_operations(start_date=start_date, end_date=end_date)
        snapshot_date = end_date or start_date or "all"
        snapshot = build_stock_stock_projection(records=records, snapshot_date=snapshot_date)
        if persist:
            self.graph_repository.save_snapshot(snapshot)
        return summarize_graph(snapshot)
