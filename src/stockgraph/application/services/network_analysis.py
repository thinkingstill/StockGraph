"""关系图构建编排。

**按交易日切分快照**是关键：原实现把 `start_date..end_date` 整个区间的记录
塞进一个以 `end_date` 命名的快照里。传一整年就会得到一张「名叫 2026-11-06、
但边上带着 2026-01-05 到 2026-11-06 全部交易」的图——快照日期和边日期对不上，
`fetch_edges(snapshot_type, date)` 的语义完全失效，跨快照路径分析也就失去意义。

现在每个交易日一张快照，`snapshot_date` 与 `edge.trade_date` 严格一致。
`build_range()` 负责按日遍历，供回补脚本使用。
"""

from __future__ import annotations

import logging
from collections import defaultdict

from stockgraph.domain.graph import (
    GraphSnapshot,
    build_stock_seat_bipartite_graph,
    build_stock_stock_projection,
    build_trader_seat_projection,
    summarize_graph,
)
from stockgraph.infrastructure.db.repositories import DragonTigerRepository, GraphRepository

logger = logging.getLogger(__name__)

BUILDERS = {
    "seat_stock": build_stock_seat_bipartite_graph,
    "seat_projection": build_trader_seat_projection,
    "stock_projection": build_stock_stock_projection,
}


class NetworkAnalysisService:
    def __init__(
        self,
        dragon_tiger_repository: DragonTigerRepository | None = None,
        graph_repository: GraphRepository | None = None,
    ) -> None:
        self.dragon_tiger_repository = dragon_tiger_repository or DragonTigerRepository()
        self.graph_repository = graph_repository or GraphRepository()

    # ------------------------------------------------------------------ 内部

    def _records(self, start_date: str | None, end_date: str | None) -> list[dict]:
        return self.dragon_tiger_repository.list_operations(start_date=start_date, end_date=end_date)

    def _group_by_date(self, records: list[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            grouped[str(record.get("date") or "")].append(record)
        return {day: rows for day, rows in grouped.items() if day}

    def _build_one(self, builder_name: str, records: list[dict], snapshot_date: str) -> GraphSnapshot:
        return BUILDERS[builder_name](records=records, snapshot_date=snapshot_date)

    # ------------------------------------------------------------------ 单快照

    def build_snapshot(
        self,
        builder_name: str,
        snapshot_date: str,
        persist: bool = False,
    ) -> dict:
        """构建单个交易日的某类图快照。"""
        if builder_name not in BUILDERS:
            raise ValueError(f"未知的图类型: {builder_name}，可选: {', '.join(BUILDERS)}")
        records = self._records(snapshot_date, snapshot_date)
        snapshot = self._build_one(builder_name, records, snapshot_date)
        if persist and snapshot.edges:
            self.graph_repository.save_snapshot(snapshot)
        return summarize_graph(snapshot)

    def build_stock_seat_projection(
        self, start_date: str | None = None, end_date: str | None = None, persist: bool = False
    ) -> dict:
        return self.build_snapshot("seat_stock", self._single_date(start_date, end_date), persist)

    def build_seat_projection(
        self, start_date: str | None = None, end_date: str | None = None, persist: bool = False
    ) -> dict:
        return self.build_snapshot("seat_projection", self._single_date(start_date, end_date), persist)

    def build_stock_projection(
        self, start_date: str | None = None, end_date: str | None = None, persist: bool = False
    ) -> dict:
        return self.build_snapshot("stock_projection", self._single_date(start_date, end_date), persist)

    @staticmethod
    def _single_date(start_date: str | None, end_date: str | None) -> str:
        """单快照构建只接受单个交易日。

        传入区间会被拒绝，而不是静默地把整段数据混进一个快照。
        """
        if start_date and end_date and start_date != end_date:
            raise ValueError(
                f"单快照构建只接受一个交易日，收到 {start_date} ~ {end_date}；"
                "区间构建请用 build_range()"
            )
        day = end_date or start_date
        if not day:
            raise ValueError("必须指定 snapshot_date")
        return day

    # ------------------------------------------------------------------ 区间

    def build_range(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        persist: bool = False,
        builders: tuple[str, ...] = ("seat_stock", "seat_projection", "stock_projection"),
        skip_existing: bool = True,
    ) -> dict:
        """按交易日逐日构建并落库。

        `skip_existing=True` 时跳过库里已有的 (类型, 日期)，方便断点续跑。
        """
        records = self._records(start_date, end_date)
        grouped = self._group_by_date(records)

        existing: set[tuple[str, str]] = set()
        if skip_existing and persist:
            for item in self.graph_repository.list_snapshots():
                existing.add((item["snapshot_type"], item["snapshot_date"]))

        written = 0
        skipped = 0
        per_type: dict[str, int] = defaultdict(int)
        totals: dict[str, dict] = {}

        for day in sorted(grouped):
            rows = grouped[day]
            for builder_name in builders:
                if (builder_name, day) in existing:
                    skipped += 1
                    continue
                snapshot = self._build_one(builder_name, rows, day)
                if not snapshot.edges:
                    continue
                if persist:
                    self.graph_repository.save_snapshot(snapshot)
                written += 1
                per_type[builder_name] += 1
                summary = summarize_graph(snapshot)
                totals[builder_name] = {
                    "nodes": summary["node_count"],
                    "edges": summary["edge_count"],
                }

        logger.info(
            "图快照构建完成: %d 天, 写入 %d 张, 跳过 %d 张, 明细 %s",
            len(grouped),
            written,
            skipped,
            dict(per_type),
        )
        return {
            "trading_days": len(grouped),
            "snapshots_written": written,
            "snapshots_skipped": skipped,
            "per_type": dict(per_type),
            "last_snapshot_size": totals,
        }

    def build_snapshots(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        persist: bool = False,
    ) -> dict[str, GraphSnapshot]:
        """构建单日三类快照（内存对象），保持旧接口兼容。"""
        day = self._single_date(start_date, end_date)
        records = self._records(day, day)
        snapshots = {
            name: self._build_one(name, records, day) for name in BUILDERS
        }
        if persist:
            for snapshot in snapshots.values():
                if snapshot.edges:
                    self.graph_repository.save_snapshot(snapshot)
        return snapshots
