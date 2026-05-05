from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from stockgraph.core import APP_DATA_DIR, APP_OUTPUT_DIR, MARKET_DATA_DIR, ensure_runtime_dirs
from stockgraph.domain.dragon_tiger import FAMOUS_TRADERS
from stockgraph.domain.market_overview import get_exchange
from stockgraph.infrastructure.db import DragonTigerRepository
from stockgraph.infrastructure.db.repositories import NewsRepository
from stockgraph.presentation.templates import render_unified_app


class UnifiedFrontendService:
    def __init__(
        self,
        dragon_tiger_repository: DragonTigerRepository | None = None,
        news_repository: NewsRepository | None = None,
    ) -> None:
        self.dragon_tiger_repository = dragon_tiger_repository or DragonTigerRepository()
        self.news_repository = news_repository or NewsRepository()

    def generate(self) -> list[Path]:
        ensure_runtime_dirs()
        self.dragon_tiger_repository.initialize_database()
        self.news_repository.initialize_database()
        section_meta = {
            "dragon_query": self._build_dragon_query_data(),
            "dragon_graph": self._build_dragon_graph_data(),
            "market_hot": self._build_market_hot_data(),
            "market_calendar": self._build_market_calendar_data(),
            "market_industry": self._build_market_industry_data(),
            "stock_super_graph": self._build_stock_super_graph_data(),
            "stock_news": self._build_stock_news_data(),
            "ai_analysis": self._build_ai_analysis_data(),
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

    def _build_stock_news_data(self) -> dict:
        """构建个股新闻数据，供前端展示。"""
        stock_codes = self.news_repository.list_stock_codes_with_news()
        if not stock_codes:
            return self._missing("暂无个股新闻数据，请先运行新闻同步")

        # 获取所有新闻
        all_news = self.news_repository.query_all_news(limit=500)

        # 按股票代码分组
        stock_news_map: dict[str, list[dict]] = {}
        for article in all_news:
            code = article.get("stock_code", "")
            if code:
                stock_news_map.setdefault(code, []).append(article)

        # 也通过实体关联补充
        for code in stock_codes:
            if code not in stock_news_map:
                related = self.news_repository.query_news_by_stock(code, limit=30)
                if related:
                    stock_news_map[code] = related

        # 构建汇总数据
        stock_summaries = []
        for code in stock_codes:
            news_list = stock_news_map.get(code, [])
            if not news_list:
                continue
            # 统计情绪分布
            sentiment_counts = {"利好": 0, "利空": 0, "中性": 0}
            for n in news_list:
                s = n.get("sentiment", "中性")
                sentiment_counts[s] = sentiment_counts.get(s, 0) + 1
            stock_summaries.append({
                "stock_code": code,
                "news_count": len(news_list),
                "latest_news": news_list[0].get("title", "") if news_list else "",
                "latest_time": news_list[0].get("published_at", "") if news_list else "",
                "sentiment_summary": sentiment_counts,
            })

        # 按新闻数量排序
        stock_summaries.sort(key=lambda x: x["news_count"], reverse=True)

        payload = {
            "stock_codes": stock_codes,
            "stock_summaries": stock_summaries,
            "stock_news": stock_news_map,
            "total_articles": len(all_news),
        }
        return self._write_section("stock_news.json", payload)

    def _build_stock_super_graph_data(self) -> dict:
        """构建全 A 股可扩展图谱：股票全集 + 行业/交易/席位/新闻等关系。"""
        stock_files = sorted(MARKET_DATA_DIR.glob("stock_daily_*.json"), reverse=True)
        if not stock_files:
            return self._missing("全 A 图谱需要先生成 stock_daily 市场数据")

        hot_files = {
            self._format_trade_date(self._extract_trade_date(path.name)): path
            for path in MARKET_DATA_DIR.glob("hot_daily_*.json")
        }
        date_graphs: dict[str, dict] = {}
        date_list: list[str] = []
        categories = [
            {"key": "stock", "name": "股票", "color": "#2563eb"},
            {"key": "industry", "name": "行业", "color": "#0f766e"},
            {"key": "exchange", "name": "交易所", "color": "#7c3aed"},
            {"key": "trade_state", "name": "涨跌状态", "color": "#b45309"},
            {"key": "trade_bucket", "name": "交易分层", "color": "#0891b2"},
            {"key": "seat", "name": "席位", "color": "#dc2626"},
            {"key": "trader", "name": "游资别名", "color": "#be123c"},
            {"key": "news", "name": "新闻", "color": "#475569"},
            {"key": "event", "name": "事件", "color": "#9333ea"},
            {"key": "sentiment", "name": "情绪", "color": "#16a34a"},
        ]

        for stock_path in stock_files:
            trade_date = self._format_trade_date(self._extract_trade_date(stock_path.name))
            if not trade_date:
                continue
            stock_rows = self._read_json_list(stock_path)
            if not stock_rows:
                continue
            hot_rows = self._read_json_list(hot_files[trade_date]) if trade_date in hot_files else []
            graph = self._build_stock_super_graph_for_date(trade_date, stock_rows, hot_rows)
            if graph["nodes"]:
                date_graphs[trade_date] = graph
                date_list.append(trade_date)

        if not date_graphs:
            return self._missing("全 A 图谱有效数据为空")
        payload = {
            "schema_version": "stock_super_graph.v1",
            "latest_date": date_list[0],
            "date_list": date_list,
            "categories": categories,
            "graphs": date_graphs,
            "relation_types": {
                "stock_industry": "股票所属行业",
                "stock_exchange": "股票上市交易所",
                "stock_trade_state": "股票当日涨跌状态",
                "stock_trade_bucket": "股票当日交易活跃度分层",
                "seat_stock_trade": "龙虎榜席位买卖股票",
                "trader_seat_alias": "知名游资别名与席位",
                "news_stock": "新闻关联股票",
                "news_event": "新闻事件类型",
                "news_sentiment": "新闻情绪",
            },
        }
        return self._write_section("stock_super_graph.json", payload)

    def _build_stock_super_graph_for_date(self, trade_date: str, stock_rows: list[dict], hot_rows: list[dict]) -> dict:
        nodes: dict[str, dict] = {}
        links: dict[tuple[str, str, str], dict] = {}
        industries: dict[str, dict] = defaultdict(lambda: {"count": 0, "change_sum": 0.0, "amount_sum": 0.0})
        exchanges: dict[str, int] = defaultdict(int)

        hot_lookup: dict[str, dict] = {}
        for row in hot_rows:
            code = self._normalize_stock_code(row.get("股票代码"))
            if code and code not in hot_lookup:
                hot_lookup[code] = row

        def add_node(node_id: str, category: str, name: str, value: float = 1.0, **extra) -> None:
            existing = nodes.get(node_id)
            if existing:
                existing["value"] = max(float(existing.get("value") or 0), float(value or 0))
                existing["attributes"].update({k: v for k, v in extra.items() if v not in (None, "")})
                return
            nodes[node_id] = {
                "id": node_id,
                "name": name,
                "category": category,
                "value": round(float(value or 0), 4),
                "attributes": {k: v for k, v in extra.items() if v not in (None, "")},
            }

        def add_link(source: str, target: str, rel: str, weight: float = 1.0, **extra) -> None:
            key = (source, target, rel)
            if key not in links:
                links[key] = {
                    "source": source,
                    "target": target,
                    "type": rel,
                    "value": 0.0,
                    "attributes": {},
                }
            links[key]["value"] += float(weight or 0)
            links[key]["attributes"].update({k: v for k, v in extra.items() if v not in (None, "")})

        for row in stock_rows:
            code = self._normalize_stock_code(row.get("代码"))
            if not code:
                continue
            name = str(row.get("名称") or code)
            industry = self._clean_group_name(row.get("行业"))
            exchange = get_exchange(code)
            hot = hot_lookup.get(code, {})
            change_pct = self._as_float(row.get("涨跌幅")) or 0.0
            amount = self._as_float(row.get("成交额")) or 0.0
            volume = self._as_float(row.get("成交量")) or 0.0
            follow = self._as_float(hot.get("关注")) or 0.0
            tweet = self._as_float(hot.get("讨论")) or 0.0
            deal = self._as_float(hot.get("交易")) or 0.0
            node_value = math.log10(max(amount, 1.0)) + abs(change_pct) * 0.45 + follow + tweet + deal

            add_node(
                f"stock:{code}",
                "stock",
                f"{name}({code})",
                node_value,
                code=code,
                stock_name=name,
                industry=industry,
                exchange=exchange,
                latest_price=self._as_float(row.get("最新价")),
                change_pct=change_pct,
                amount=round(amount, 2),
                volume=round(volume, 2),
                follow=follow,
                tweet=tweet,
                deal=deal,
            )
            add_node(f"industry:{industry}", "industry", industry, 8)
            add_node(f"exchange:{exchange}", "exchange", exchange, 5)
            state_key, state_name = self._change_state(change_pct)
            amount_key, amount_name = self._amount_bucket(amount)
            add_node(f"trade_state:{state_key}", "trade_state", state_name, 4)
            add_node(f"trade_bucket:{amount_key}", "trade_bucket", amount_name, 4)

            add_link(f"stock:{code}", f"industry:{industry}", "stock_industry", 1)
            add_link(f"stock:{code}", f"exchange:{exchange}", "stock_exchange", 1)
            add_link(f"stock:{code}", f"trade_state:{state_key}", "stock_trade_state", abs(change_pct) + 1)
            add_link(f"stock:{code}", f"trade_bucket:{amount_key}", "stock_trade_bucket", max(math.log10(max(amount, 1.0)), 1))

            industries[industry]["count"] += 1
            industries[industry]["change_sum"] += change_pct
            industries[industry]["amount_sum"] += amount
            exchanges[exchange] += 1

        for industry, stat in industries.items():
            node = nodes.get(f"industry:{industry}")
            if node:
                node["value"] = stat["count"]
                node["attributes"].update({
                    "stock_count": stat["count"],
                    "avg_change_pct": round(stat["change_sum"] / stat["count"], 4) if stat["count"] else 0,
                    "amount": round(stat["amount_sum"], 2),
                })
        for exchange, count in exchanges.items():
            node = nodes.get(f"exchange:{exchange}")
            if node:
                node["value"] = count
                node["attributes"]["stock_count"] = count

        dragon_rows = self.dragon_tiger_repository.list_operations(trade_date, trade_date)
        for row in sorted(dragon_rows, key=lambda item: float(item.get("amount") or 0), reverse=True)[:1200]:
            code = self._normalize_stock_code(row.get("stock_code"))
            if not code or f"stock:{code}" not in nodes:
                continue
            seat_name = str(row.get("seat_name") or "").strip()
            if not seat_name:
                continue
            seat_id = f"seat:{seat_name}"
            amount = float(row.get("amount") or 0)
            add_node(seat_id, "seat", seat_name, math.log10(max(amount, 1.0)), seat_type=row.get("seat_type"), trader_alias=row.get("trader_alias"))
            add_link(
                seat_id,
                f"stock:{code}",
                "seat_stock_trade",
                max(amount / 1000, 1),
                direction=row.get("direction"),
                amount=round(amount, 2),
                seat_type=row.get("seat_type"),
            )
            if row.get("trader_alias"):
                trader_id = f"trader:{row['trader_alias']}"
                add_node(trader_id, "trader", row["trader_alias"], 8)
                add_link(trader_id, seat_id, "trader_seat_alias", 1)

        for row in self.news_repository.query_news_edges_by_date(trade_date, limit=800):
            code = self._normalize_stock_code(row.get("stock_code"))
            if not code or f"stock:{code}" not in nodes:
                continue
            news_id = f"news:{row['id']}"
            title = str(row.get("title") or f"新闻{row['id']}")
            event_type = self._clean_group_name(row.get("event_type"), fallback="其他")
            sentiment = self._clean_group_name(row.get("sentiment"), fallback="中性")
            add_node(news_id, "news", title[:34], 3, title=title, source=row.get("source"), published_at=row.get("published_at"), url=row.get("url"))
            add_node(f"event:{event_type}", "event", event_type, 4)
            add_node(f"sentiment:{sentiment}", "sentiment", sentiment, 3)
            add_link(news_id, f"stock:{code}", "news_stock", 3, published_at=row.get("published_at"))
            add_link(news_id, f"event:{event_type}", "news_event", 1)
            add_link(news_id, f"sentiment:{sentiment}", "news_sentiment", 1)

        stock_count = sum(1 for node in nodes.values() if node["category"] == "stock")
        return {
            "date": trade_date,
            "nodes": list(nodes.values()),
            "links": [
                {**link, "value": round(float(link["value"]), 4)}
                for link in links.values()
            ],
            "stats": {
                "stock_count": stock_count,
                "industry_count": len(industries),
                "exchange_count": len(exchanges),
                "seat_count": sum(1 for node in nodes.values() if node["category"] == "seat"),
                "news_count": sum(1 for node in nodes.values() if node["category"] == "news"),
                "edge_count": len(links),
            },
        }

    def _build_ai_analysis_data(self) -> dict:
        """构建 AI 分析所需的基础数据（股票列表 + 龙虎榜 + 新闻），供前端调用 LLM 时使用。"""
        # 合并两个来源的股票代码
        news_codes = self.news_repository.list_stock_codes_with_news()
        dates = self.dragon_tiger_repository.list_trade_dates()
        dt_codes: list[str] = []
        if dates:
            active = self.dragon_tiger_repository.aggregate_active_stocks(dates[0], limit=30)
            dt_codes = [s["code"] for s in active]

        # 新闻股票优先，再补充龙虎榜活跃股票
        seen: set[str] = set()
        stock_codes: list[str] = []
        for code in news_codes + dt_codes:
            if code not in seen:
                seen.add(code)
                stock_codes.append(code)

        if not stock_codes:
            return self._missing("暂无可分析的股票数据，请先同步龙虎榜或新闻")

        # 预加载龙虎榜数据集（避免重复加载）
        dragon_dataset = self.dragon_tiger_repository.export_query_dataset() if dates else {}

        # 构建每只股票的上下文数据
        stock_contexts: dict[str, dict] = {}
        for code in stock_codes[:50]:  # 最多50只
            ctx: dict = {"code": code}

            # 新闻数据
            news = self.news_repository.query_news_by_stock(code, limit=15)
            if news:
                ctx["news"] = [
                    {
                        "title": n.get("title", ""),
                        "source": n.get("source", ""),
                        "published_at": n.get("published_at", ""),
                        "sentiment": n.get("sentiment", "中性"),
                        "event_type": n.get("event_type", "其他"),
                        "content": (n.get("content", "") or "")[:300],
                    }
                    for n in news
                ]

            # 龙虎榜数据
            dragon_records: list[dict] = []
            for date in dates[:5]:
                ops = dragon_dataset.get(date, [])
                stock_ops = [op for op in ops if op.get("stockCode") == code]
                if stock_ops:
                    dragon_records.append({
                        "date": date,
                        "operations": stock_ops[:10],
                    })
            if dragon_records:
                ctx["dragon_tiger"] = dragon_records

            stock_contexts[code] = ctx

        payload = {
            "stock_codes": stock_codes[:50],
            "stock_contexts": stock_contexts,
        }
        return self._write_section("ai_analysis.json", payload)

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
    def _format_trade_date(value: str) -> str:
        if not value:
            return ""
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if len(digits) >= 8:
            return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
        return str(value)

    @staticmethod
    def _normalize_stock_code(value) -> str:
        text = str(value or "").strip()
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return ""
        return digits[-6:].zfill(6)

    @staticmethod
    def _clean_group_name(value, fallback: str = "未知") -> str:
        text = str(value or "").strip()
        return text if text and text not in {"缺失", "nan", "None"} else fallback

    @staticmethod
    def _change_state(change_pct: float) -> tuple[str, str]:
        if change_pct >= 9.8:
            return "limit_up", "涨停/强势"
        if change_pct <= -9.8:
            return "limit_down", "跌停/弱势"
        if change_pct >= 3:
            return "up_strong", "上涨3%+"
        if change_pct > 0:
            return "up", "上涨"
        if change_pct <= -3:
            return "down_strong", "下跌3%+"
        if change_pct < 0:
            return "down", "下跌"
        return "flat", "平盘"

    @staticmethod
    def _amount_bucket(amount: float) -> tuple[str, str]:
        if amount >= 10_000_000_000:
            return "amount_100y", "成交额100亿+"
        if amount >= 3_000_000_000:
            return "amount_30y", "成交额30亿+"
        if amount >= 1_000_000_000:
            return "amount_10y", "成交额10亿+"
        if amount >= 300_000_000:
            return "amount_3y", "成交额3亿+"
        if amount >= 100_000_000:
            return "amount_1y", "成交额1亿+"
        return "amount_low", "成交额1亿以下"

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
