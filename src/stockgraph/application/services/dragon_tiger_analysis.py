from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from stockgraph.application.services.network_analysis import NetworkAnalysisService
from stockgraph.core.paths import DRAGON_TIGER_OUTPUT_DIR, ensure_runtime_dirs
from stockgraph.domain.graph import GraphSnapshot, summarize_graph
from stockgraph.infrastructure.db.connection import database_path
from stockgraph.infrastructure.db.repositories import DragonTigerRepository, GraphRepository


class DragonTigerAnalysisService:
    def __init__(
        self,
        dragon_tiger_repository: DragonTigerRepository | None = None,
        graph_repository: GraphRepository | None = None,
    ) -> None:
        self.dragon_tiger_repository = dragon_tiger_repository or DragonTigerRepository()
        self.network_analysis_service = NetworkAnalysisService(
            dragon_tiger_repository=self.dragon_tiger_repository,
            graph_repository=graph_repository or GraphRepository(),
        )

    def export(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        output_path: Path | None = None,
        top_limit: int = 20,
        persist_graphs: bool = False,
    ) -> Path:
        ensure_runtime_dirs()
        self.dragon_tiger_repository.initialize_database()
        records = self.dragon_tiger_repository.list_operations(start_date=start_date, end_date=end_date)
        snapshots = self.network_analysis_service.build_snapshots(
            start_date=start_date,
            end_date=end_date,
            persist=persist_graphs,
        )
        payload = self.build_payload(
            records=records,
            snapshots=snapshots,
            start_date=start_date,
            end_date=end_date,
            top_limit=top_limit,
        )
        target = output_path or self.default_output_path(start_date=start_date, end_date=end_date)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def build_payload(
        self,
        records: list[dict],
        snapshots: dict[str, GraphSnapshot],
        start_date: str | None,
        end_date: str | None,
        top_limit: int,
    ) -> dict:
        trade_dates = sorted({row["date"] for row in records}, reverse=True)
        period = {
            "startDate": start_date,
            "endDate": end_date,
            "tradeDates": trade_dates,
            "tradeDateCount": len(trade_dates),
        }
        if start_date and end_date and start_date == end_date:
            period["mode"] = "single_date"
        elif start_date or end_date:
            period["mode"] = "date_range"
        else:
            period["mode"] = "all"

        return {
            "schemaVersion": "dragon_tiger_analysis.v1",
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "source": {
                "database": str(database_path()),
                "amountUnit": "万元",
            },
            "period": period,
            "stats": self._stats(records),
            "rankings": self._rankings(records=records, limit=top_limit),
            "daily": self._daily(records=records, limit=top_limit),
            "operations": [self._operation(row) for row in records],
            "graphs": {name: self._snapshot(snapshot) for name, snapshot in snapshots.items()},
        }

    @staticmethod
    def default_output_path(start_date: str | None, end_date: str | None) -> Path:
        if start_date and end_date and start_date == end_date:
            suffix = start_date
        elif start_date or end_date:
            suffix = f"{start_date or 'begin'}_{end_date or 'end'}"
        else:
            suffix = "all"
        return DRAGON_TIGER_OUTPUT_DIR / f"dragon_tiger_analysis_{suffix}.json"

    def _daily(self, records: list[dict], limit: int) -> dict[str, dict]:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in records:
            grouped[row["date"]].append(row)
        return {
            date: {
                "stats": self._stats(rows),
                "rankings": self._rankings(records=rows, limit=limit),
            }
            for date, rows in sorted(grouped.items(), reverse=True)
        }

    @staticmethod
    def _stats(records: list[dict]) -> dict:
        buy_amount = sum(float(row.get("amount") or 0) for row in records if row.get("direction") == "买")
        sell_amount = sum(float(row.get("amount") or 0) for row in records if row.get("direction") == "卖")
        return {
            "operationCount": len(records),
            "stockCount": len({row["stock_code"] for row in records}),
            "seatCount": len({row["seat_name"] for row in records}),
            "buyAmount": round(buy_amount, 4),
            "sellAmount": round(sell_amount, 4),
            "netAmount": round(buy_amount - sell_amount, 4),
        }

    def _rankings(self, records: list[dict], limit: int) -> dict:
        return {
            "topStocksByNetBuy": self._aggregate_by_stock(records, limit, "net", reverse=True),
            "topStocksByNetSell": self._aggregate_by_stock(records, limit, "net", reverse=False),
            "topStocksByActivity": self._aggregate_by_stock(records, limit, "operationCount", reverse=True),
            "topSeatsByNetBuy": self._aggregate_by_seat(records, limit, "net", reverse=True),
            "topSeatsByNetSell": self._aggregate_by_seat(records, limit, "net", reverse=False),
            "topSeatsByActivity": self._aggregate_by_seat(records, limit, "operationCount", reverse=True),
        }

    @staticmethod
    def _aggregate_by_stock(records: list[dict], limit: int, sort_key: str, reverse: bool) -> list[dict]:
        grouped: dict[str, dict] = {}
        for row in records:
            key = row["stock_code"]
            item = grouped.setdefault(
                key,
                {
                    "stockCode": row["stock_code"],
                    "stockName": row["stock_name"],
                    "operationCount": 0,
                    "seatCount": set(),
                    "buy": 0.0,
                    "sell": 0.0,
                    "net": 0.0,
                },
            )
            DragonTigerAnalysisService._accumulate_amounts(item, row)
            item["seatCount"].add(row["seat_name"])
        return DragonTigerAnalysisService._finalize_aggregates(grouped.values(), sort_key, reverse, limit)

    @staticmethod
    def _aggregate_by_seat(records: list[dict], limit: int, sort_key: str, reverse: bool) -> list[dict]:
        grouped: dict[str, dict] = {}
        for row in records:
            key = row["seat_name"]
            item = grouped.setdefault(
                key,
                {
                    "seatName": row["seat_name"],
                    "seatType": row.get("seat_type"),
                    "traderAlias": row.get("trader_alias"),
                    "operationCount": 0,
                    "stockCount": set(),
                    "buy": 0.0,
                    "sell": 0.0,
                    "net": 0.0,
                },
            )
            if row.get("trader_alias"):
                item["traderAlias"] = row.get("trader_alias")
            DragonTigerAnalysisService._accumulate_amounts(item, row)
            item["stockCount"].add(row["stock_code"])
        return DragonTigerAnalysisService._finalize_aggregates(grouped.values(), sort_key, reverse, limit)

    @staticmethod
    def _accumulate_amounts(item: dict, row: dict) -> None:
        amount = float(row.get("amount") or 0)
        item["operationCount"] += 1
        if row.get("direction") == "买":
            item["buy"] += amount
            item["net"] += amount
        elif row.get("direction") == "卖":
            item["sell"] += amount
            item["net"] -= amount

    @staticmethod
    def _finalize_aggregates(items, sort_key: str, reverse: bool, limit: int) -> list[dict]:
        result = []
        for item in items:
            normalized = dict(item)
            for key, value in list(normalized.items()):
                if isinstance(value, set):
                    normalized[key] = len(value)
            for key in ("buy", "sell", "net"):
                normalized[key] = round(float(normalized.get(key) or 0), 4)
            result.append(normalized)
        return sorted(result, key=lambda item: item.get(sort_key) or 0, reverse=reverse)[:limit]

    @staticmethod
    def _operation(row: dict) -> dict:
        return {
            "date": row["date"],
            "stockCode": row["stock_code"],
            "stockName": row["stock_name"],
            "seatName": row["seat_name"],
            "direction": row["direction"],
            "amount": row["amount"],
            "seatType": row.get("seat_type"),
            "traderAlias": row.get("trader_alias"),
        }

    @staticmethod
    def _snapshot(snapshot: GraphSnapshot) -> dict:
        return {
            "summary": summarize_graph(snapshot),
            "snapshot": asdict(snapshot),
        }
