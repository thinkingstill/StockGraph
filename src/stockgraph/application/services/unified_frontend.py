from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from stockgraph.core import APP_DATA_DIR, APP_OUTPUT_DIR, MARKET_DATA_DIR, ensure_runtime_dirs
from stockgraph.domain.dragon_tiger import FAMOUS_TRADERS
from stockgraph.domain.market_overview import get_exchange
from stockgraph.infrastructure.db import DragonTigerRepository
from stockgraph.presentation.templates import render_unified_app


class UnifiedFrontendService:
    def __init__(self, dragon_tiger_repository: DragonTigerRepository | None = None) -> None:
        self.dragon_tiger_repository = dragon_tiger_repository or DragonTigerRepository()

    def generate(self) -> list[Path]:
        ensure_runtime_dirs()
        self.dragon_tiger_repository.initialize_database()
        section_meta = {
            "dragon_query": self._build_dragon_query_data(),
            "dragon_graph": self._build_dragon_graph_data(),
            "market_hot": self._build_market_hot_data(),
            "market_calendar": self._build_market_calendar_data(),
            "market_industry": self._build_market_industry_data(),
        }
        manifest = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sections": section_meta,
        }
        manifest_path = APP_DATA_DIR / "app_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, default=str), encoding="utf-8")
        app_path = APP_OUTPUT_DIR / "index.html"
        app_path.write_text(render_unified_app(), encoding="utf-8")
        return [app_path, manifest_path]

    def _build_dragon_query_data(self) -> dict:
        dates = self.dragon_tiger_repository.list_trade_dates()
        if not dates:
            return self._missing("龙虎榜查询暂无数据")
        payload = {
            "latest_date": dates[0],
            "date_list": dates,
            "all_operations": self.dragon_tiger_repository.export_query_dataset(),
            "all_active_stocks": {date: self.dragon_tiger_repository.aggregate_active_stocks(date) for date in dates},
            "all_active_seats": {date: self.dragon_tiger_repository.aggregate_active_seats(date) for date in dates},
            "all_famous_traders": {date: self.dragon_tiger_repository.aggregate_famous_traders(date) for date in dates},
        }
        return self._write_section("dragon_tiger_query.json", payload)

    def _build_dragon_graph_data(self) -> dict:
        records = self.dragon_tiger_repository.export_operations()
        if not records:
            return self._missing("龙虎榜关系网暂无数据")
        return self._write_section("dragon_tiger_graph.json", {"records": records, "famous_traders": FAMOUS_TRADERS})

    def _build_market_hot_data(self) -> dict:
        latest = self._latest_json("hot_daily_*.json")
        if latest is None:
            return self._missing("市场热度数据未生成")
        records = self._read_json_list(latest)
        if not records:
            return self._missing("市场热度数据为空")
        daily_latest = self._latest_json("stock_daily_*.json")
        daily_records = self._read_json_list(daily_latest) if daily_latest else []
        daily_lookup = {}
        for row in daily_records:
            code = str(row.get("代码", ""))[-6:].zfill(6)
            if code:
                daily_lookup[code] = row
        deduped = {}
        for row in records:
            industry = str(row.get("行业", "未知")).strip()
            if industry in {"未知", "缺失", ""}:
                continue
            code = str(row.get("股票代码", ""))[-6:].zfill(6)
            if not code:
                continue
            daily = daily_lookup.get(code, {})
            deduped[code] = {
                "stock_code": code,
                "stock_name": row.get("股票简称", ""),
                "industry": industry,
                "exchange": get_exchange(code),
                "latest_price": self._as_float(daily.get("最新价", row.get("最新价"))),
                "change_pct": self._as_float(daily.get("涨跌幅", row.get("涨跌幅"))),
                "change_amount": self._as_float(daily.get("涨跌额")),
                "buy_price": self._as_float(daily.get("买入")),
                "sell_price": self._as_float(daily.get("卖出")),
                "prev_close": self._as_float(daily.get("昨收")),
                "open_price": self._as_float(daily.get("今开")),
                "high_price": self._as_float(daily.get("最高")),
                "low_price": self._as_float(daily.get("最低")),
                "volume": self._as_float(daily.get("成交量")),
                "amount": self._as_float(daily.get("成交额")),
                "follow_rank": self._as_float(row.get("关注")),
                "tweet_rank": self._as_float(row.get("讨论")),
                "deal_rank": self._as_float(row.get("交易")),
            }
        payload = {
            "trade_date": self._extract_trade_date(latest.name),
            "numeric_fields": {
                "follow_rank": "关注热度",
                "tweet_rank": "讨论热度",
                "deal_rank": "交易热度",
                "change_pct": "涨跌幅",
                "latest_price": "最新价",
                "amount": "成交额",
                "volume": "成交量",
                "open_price": "开盘价",
                "high_price": "最高价",
                "low_price": "最低价",
            },
            "records": list(deduped.values()),
        }
        if not payload["records"]:
            return self._missing("市场热度有效数据为空")
        return self._write_section("market_hot.json", payload)

    def _build_market_industry_data(self) -> dict:
        latest = self._latest_json("stock_daily_*.json")
        if latest is None:
            return self._missing("行业强弱数据未生成")
        records = self._read_json_list(latest)
        if not records:
            return self._missing("行业强弱数据为空")
        aggregate: dict[str, dict] = {}
        for row in records:
            industry = str(row.get("行业", "未知"))
            if industry == "未知":
                continue
            item = aggregate.setdefault(industry, {"industry": industry, "stock_count": 0, "total_change_pct": 0.0})
            item["stock_count"] += 1
            item["total_change_pct"] += float(row.get("涨跌幅", 0) or 0)
        if not aggregate:
            return self._missing("行业强弱有效数据为空")
        grouped = []
        for item in aggregate.values():
            grouped.append({
                "industry": item["industry"],
                "stock_count": item["stock_count"],
                "total_change_pct": round(item["total_change_pct"], 4),
                "avg_change_pct": round(item["total_change_pct"] / item["stock_count"], 4) if item["stock_count"] else 0.0,
            })
        grouped.sort(key=lambda x: x["total_change_pct"], reverse=True)
        payload = {
            "trade_date": self._extract_trade_date(latest.name),
            "records": grouped,
        }
        return self._write_section("market_industry.json", payload)

    def _build_market_calendar_data(self) -> dict:
        files = sorted(MARKET_DATA_DIR.glob("stock_daily_*.json"))
        if not files:
            return self._missing("行业日历数据未生成")
        years: dict[str, list[dict]] = {}
        for path in files:
            trade_date = self._extract_trade_date(path.name)
            if len(trade_date) != 8:
                continue
            records = self._read_json_list(path)
            if not records:
                continue
            aggregate: dict[str, float] = {}
            for row in records:
                industry = str(row.get("行业", "未知"))
                if industry == "未知":
                    continue
                aggregate[industry] = aggregate.get(industry, 0.0) + float(row.get("涨跌幅", 0) or 0)
            if not aggregate:
                continue
            sorted_items = sorted(aggregate.items(), key=lambda item: item[1], reverse=True)
            years.setdefault(trade_date[:4], []).append({
                "date": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                "top_industry": sorted_items[0][0],
                "top_change_pct": round(sorted_items[0][1], 4),
                "bottom_industry": sorted_items[-1][0],
                "bottom_change_pct": round(sorted_items[-1][1], 4),
            })
        if not years:
            return self._missing("行业日历数据为空")
        for year in years:
            years[year] = sorted(years[year], key=lambda item: item["date"])
        return self._write_section("market_calendar.json", {"years": years})

    @staticmethod
    def _write_section(filename: str, payload: dict) -> dict:
        path = APP_DATA_DIR / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        return {"available": True, "path": f"./data/{filename}", "message": ""}

    @staticmethod
    def _missing(message: str) -> dict:
        return {"available": False, "path": "", "message": message}

    @staticmethod
    def _latest_json(pattern: str) -> Path | None:
        candidates = sorted(MARKET_DATA_DIR.glob(pattern), reverse=True)
        return candidates[0] if candidates else None

    @staticmethod
    def _extract_trade_date(filename: str) -> str:
        digits = "".join(ch for ch in filename if ch.isdigit())
        if len(digits) >= 8:
            return digits[:8]
        return ""

    @staticmethod
    def _read_json_list(path: Path) -> list[dict]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except Exception:
            return []

    @staticmethod
    def _as_float(value):
        try:
            if value in ("", None):
                return None
            return float(value)
        except Exception:
            return None
