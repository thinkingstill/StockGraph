from __future__ import annotations

import json
import math
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from stockgraph.core import (
    APP_DATA_DIR,
    APP_OUTPUT_DIR,
    DRAGON_TIGER_OUTPUT_DIR,
    MARKET_DATA_DIR,
    REFERENCE_DATA_DIR,
    ensure_runtime_dirs,
)
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
            "china_city_bubble": self._build_china_city_bubble_data(),
            "stock_news": self._build_stock_news_data(),
            "ai_analysis": self._build_ai_analysis_data(),
        }
        manifest = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sections": section_meta,
        }
        manifest_path = APP_DATA_DIR / "app_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, default=str), encoding="utf-8")
        self._copy_static_assets()
        app_path = APP_OUTPUT_DIR / "index.html"
        app_path.write_text(render_unified_app(), encoding="utf-8")
        return [app_path, manifest_path]

    def _build_dragon_query_data(self) -> dict:
        operations = self._load_dragon_tiger_operations()
        dates = sorted({row["date"] for row in operations}, reverse=True)
        if not dates:
            return self._missing("龙虎榜查询暂无数据")
        query_dataset: dict[str, list[dict]] = {}
        for row in operations:
            record = {
                "date": row["date"],
                "stockCode": row["stock_code"],
                "stockName": row["stock_name"],
                "seatName": row["seat_name"],
                "direction": row["direction"],
                "amount": row["amount"],
                "netAmount": row["net_amount"],
                "seatType": row.get("seat_type"),
                "alias": row.get("trader_alias"),
            }
            query_dataset.setdefault(row["date"], []).append(record)
        payload = {
            "latest_date": dates[0],
            "date_list": dates,
            "all_operations": query_dataset,
            "all_active_stocks": {date: self._aggregate_dragon_active_stocks(query_dataset.get(date, [])) for date in dates},
            "all_active_seats": {date: self._aggregate_dragon_active_seats(query_dataset.get(date, [])) for date in dates},
            "all_famous_traders": {date: self.dragon_tiger_repository.aggregate_famous_traders(date) for date in dates},
        }
        return self._write_section("dragon_tiger_query.json", payload)

    def _build_dragon_graph_data(self) -> dict:
        records = [
            row
            for row in self._load_dragon_tiger_operations()
            if row["seat_name"] not in {"自然人", "中小投资者", "其他自然人", "机构专用"}
        ]
        if not records:
            return self._missing("龙虎榜关系网暂无数据")
        return self._write_section("dragon_tiger_graph.json", {"records": records, "famous_traders": FAMOUS_TRADERS})

    def _build_market_hot_data(self) -> dict:
        hot_files = sorted(MARKET_DATA_DIR.glob("hot_daily_*.json"), reverse=True)
        if not hot_files:
            return self._missing("市场热度数据未生成")
        date_payloads = {}
        date_list = []
        for hot_path in hot_files:
            trade_date = self._extract_trade_date(hot_path.name)
            daily_path = MARKET_DATA_DIR / f"stock_daily_{trade_date}.json"
            records = self._read_json_list(hot_path)
            daily_records = self._read_json_list(daily_path) if daily_path.exists() else []
            daily_lookup = {}
            for row in daily_records:
                code = self._normalize_stock_code(row.get("代码"))
                if code:
                    daily_lookup[code] = row
            deduped = {}
            for row in records:
                industry = str(row.get("行业", "未知")).strip()
                if industry in {"未知", "缺失", ""}:
                    continue
                code = self._normalize_stock_code(row.get("股票代码"))
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
            if deduped:
                formatted_date = self._format_trade_date(trade_date)
                date_payloads[formatted_date] = list(deduped.values())
                date_list.append(formatted_date)
        payload = {
            "trade_date": date_list[0] if date_list else "",
            "latest_date": date_list[0] if date_list else "",
            "date_list": date_list,
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
            "records": date_payloads.get(date_list[0], []) if date_list else [],
            "records_by_date": date_payloads,
        }
        if not date_payloads:
            return self._missing("市场热度有效数据为空")
        return self._write_section("market_hot.json", payload)

    def _build_market_industry_data(self) -> dict:
        stock_files = sorted(MARKET_DATA_DIR.glob("stock_daily_*.json"), reverse=True)
        if not stock_files:
            return self._missing("行业强弱数据未生成")
        records_by_date = {}
        date_list = []
        for stock_path in stock_files:
            records = self._read_json_list(stock_path)
            if not records:
                continue
            aggregate: dict[str, dict] = {}
            for row in records:
                industry = str(row.get("行业", "未知"))
                if industry == "未知":
                    continue
                item = aggregate.setdefault(industry, {"industry": industry, "stock_count": 0, "total_change_pct": 0.0})
                item["stock_count"] += 1
                item["total_change_pct"] += float(row.get("涨跌幅", 0) or 0)
            if not aggregate:
                continue
            grouped = []
            for item in aggregate.values():
                grouped.append({
                    "industry": item["industry"],
                    "stock_count": item["stock_count"],
                    "total_change_pct": round(item["total_change_pct"], 4),
                    "avg_change_pct": round(item["total_change_pct"] / item["stock_count"], 4) if item["stock_count"] else 0.0,
                })
            grouped.sort(key=lambda x: x["total_change_pct"], reverse=True)
            trade_date = self._format_trade_date(self._extract_trade_date(stock_path.name))
            records_by_date[trade_date] = grouped
            date_list.append(trade_date)
        if not records_by_date:
            return self._missing("行业强弱有效数据为空")
        payload = {
            "trade_date": date_list[0],
            "latest_date": date_list[0],
            "date_list": date_list,
            "records": records_by_date[date_list[0]],
            "records_by_date": records_by_date,
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

    def _build_china_city_bubble_data(self) -> dict:
        """构建按城市聚合的中国地图气泡数据，复用全市场日行情和基础股本数据。"""
        stock_files = sorted(MARKET_DATA_DIR.glob("stock_daily_*.json"), reverse=True)
        if not stock_files:
            return self._missing("城市气泡图需要先生成 stock_daily 市场数据")

        basic_lookup = self._load_stock_basic_info()
        location_mapping = self._load_stock_location_mapping()
        date_payloads: dict[str, dict] = {}
        date_list: list[str] = []
        latest_industry_by_code: dict[str, str] = {}
        location_quality_total: dict[str, int] = defaultdict(int)

        for stock_path in stock_files:
            trade_date = self._format_trade_date(self._extract_trade_date(stock_path.name))
            if not trade_date:
                continue
            stock_rows = self._read_json_list(stock_path)
            if not stock_rows:
                continue

            city_groups: dict[str, dict] = {}
            quality_counts: dict[str, int] = defaultdict(int)
            missing_market_cap_count = 0
            total_stock_count = 0
            located_stock_count = 0

            for row in stock_rows:
                code = self._normalize_stock_code(row.get("代码"))
                if not code:
                    continue
                total_stock_count += 1
                basic = basic_lookup.get(code, {})
                stock_name = str(row.get("名称") or basic.get("stock_name") or code)
                daily_industry = self._clean_group_name(row.get("行业"))
                basic_industry = self._clean_group_name(basic.get("industry"))
                industry = daily_industry if daily_industry != "未知" else basic_industry
                if industry != "未知":
                    latest_industry_by_code[code] = industry
                exchange = self._clean_group_name(basic.get("exchange") or get_exchange(code), fallback=get_exchange(code))
                latest_price = self._as_float(row.get("最新价")) or 0.0
                change_pct = self._as_float(row.get("涨跌幅")) or 0.0
                amount = self._as_float(row.get("成交额")) or 0.0
                volume = self._as_float(row.get("成交量")) or 0.0
                total_shares = self._as_float(basic.get("total_shares"))
                float_shares = self._as_float(basic.get("float_shares"))
                share_base = total_shares or float_shares
                market_cap = latest_price * share_base if latest_price and share_base else None
                if not market_cap:
                    missing_market_cap_count += 1

                location = self._resolve_stock_location(code, exchange, basic, location_mapping)
                quality = location.get("quality", "missing")
                quality_counts[quality] += 1
                location_quality_total[quality] += 1
                lng = self._as_float(location.get("lng"))
                lat = self._as_float(location.get("lat"))
                if lng is None or lat is None:
                    continue
                located_stock_count += 1

                province = str(location.get("province") or "未知")
                city = self._normalize_city_name(location.get("city") or "未知")
                city_key = f"{province}|{city}"
                group = city_groups.setdefault(
                    city_key,
                    {
                        "province": province,
                        "city": city,
                        "lng": lng,
                        "lat": lat,
                        "stock_count": 0,
                        "up_count": 0,
                        "down_count": 0,
                        "flat_count": 0,
                        "total_market_cap": 0.0,
                        "known_market_cap_count": 0,
                        "weighted_change_sum": 0.0,
                        "simple_change_sum": 0.0,
                        "amount": 0.0,
                        "volume": 0.0,
                        "industries": defaultdict(lambda: {"stock_count": 0, "market_cap": 0.0, "change_sum": 0.0}),
                        "location_quality": defaultdict(int),
                        "stocks": [],
                    },
                )
                group["stock_count"] += 1
                group["simple_change_sum"] += change_pct
                group["amount"] += amount
                group["volume"] += volume
                group["location_quality"][quality] += 1
                if change_pct > 0:
                    group["up_count"] += 1
                elif change_pct < 0:
                    group["down_count"] += 1
                else:
                    group["flat_count"] += 1
                if market_cap:
                    group["total_market_cap"] += market_cap
                    group["known_market_cap_count"] += 1
                    group["weighted_change_sum"] += change_pct * market_cap
                industry_group = group["industries"][industry]
                industry_group["stock_count"] += 1
                industry_group["market_cap"] += market_cap or 0.0
                industry_group["change_sum"] += change_pct
                group["stocks"].append(
                    {
                        "code": code,
                        "name": stock_name,
                        "industry": industry,
                        "exchange": exchange,
                        "latest_price": round(latest_price, 4),
                        "change_pct": round(change_pct, 4),
                        "market_cap": round(market_cap, 2) if market_cap else None,
                        "market_cap_source": "total_shares" if total_shares else "float_shares" if float_shares else "missing",
                        "amount": round(amount, 2),
                    }
                )

            cities: list[dict] = []
            province_set: set[str] = set()
            industry_set: set[str] = set()
            total_market_cap = 0.0
            weighted_change_sum = 0.0
            weighted_market_cap = 0.0
            up_count = down_count = flat_count = 0

            for group in city_groups.values():
                industries = []
                for name, item in group["industries"].items():
                    industry_set.add(name)
                    count = int(item["stock_count"])
                    industries.append(
                        {
                            "industry": name,
                            "stock_count": count,
                            "market_cap": round(float(item["market_cap"]), 2),
                            "avg_change_pct": round(float(item["change_sum"]) / count, 4) if count else 0.0,
                        }
                    )
                industries.sort(key=lambda item: (item["market_cap"], item["stock_count"]), reverse=True)
                stocks = sorted(
                    group["stocks"],
                    key=lambda item: (item["market_cap"] is not None, item["market_cap"] or 0.0),
                    reverse=True,
                )[:80]
                avg_change_pct = (
                    group["weighted_change_sum"] / group["total_market_cap"]
                    if group["total_market_cap"]
                    else group["simple_change_sum"] / group["stock_count"]
                    if group["stock_count"]
                    else 0.0
                )
                city_total_market_cap = float(group["total_market_cap"])
                total_market_cap += city_total_market_cap
                weighted_change_sum += float(group["weighted_change_sum"])
                weighted_market_cap += city_total_market_cap
                up_count += int(group["up_count"])
                down_count += int(group["down_count"])
                flat_count += int(group["flat_count"])
                province_set.add(group["province"])
                cities.append(
                    {
                        "province": group["province"],
                        "city": group["city"],
                        "lng": round(float(group["lng"]), 6),
                        "lat": round(float(group["lat"]), 6),
                        "value": [
                            round(float(group["lng"]), 6),
                            round(float(group["lat"]), 6),
                            round(city_total_market_cap, 2),
                            round(avg_change_pct, 4),
                            int(group["stock_count"]),
                        ],
                        "stock_count": int(group["stock_count"]),
                        "known_market_cap_count": int(group["known_market_cap_count"]),
                        "total_market_cap": round(city_total_market_cap, 2),
                        "avg_change_pct": round(avg_change_pct, 4),
                        "amount": round(float(group["amount"]), 2),
                        "volume": round(float(group["volume"]), 2),
                        "up_count": int(group["up_count"]),
                        "down_count": int(group["down_count"]),
                        "flat_count": int(group["flat_count"]),
                        "top_industries": industries[:12],
                        "location_quality": dict(group["location_quality"]),
                        "stocks": stocks,
                        "market_cap_bucket": self._market_cap_bucket(city_total_market_cap),
                    }
                )
            cities.sort(key=lambda item: item["total_market_cap"], reverse=True)
            date_payloads[trade_date] = {
                "date": trade_date,
                "cities": cities,
                "stats": {
                    "stock_count": total_stock_count,
                    "located_stock_count": located_stock_count,
                    "city_count": len(cities),
                    "province_count": len(province_set),
                    "industry_count": len(industry_set),
                    "total_market_cap": round(total_market_cap, 2),
                    "weighted_avg_change_pct": round(weighted_change_sum / weighted_market_cap, 4) if weighted_market_cap else 0.0,
                    "up_count": up_count,
                    "down_count": down_count,
                    "flat_count": flat_count,
                    "missing_market_cap_count": missing_market_cap_count,
                    "location_quality": dict(quality_counts),
                },
                "filters": {
                    "provinces": sorted(province_set),
                    "cities": sorted({city["city"] for city in cities}),
                    "industries": sorted(industry_set),
                    "market_cap_buckets": [
                        {"key": "all", "name": "全部市值"},
                        {"key": "lt_500y", "name": "500亿以下"},
                        {"key": "500y_1000y", "name": "500-1000亿"},
                        {"key": "1000y_3000y", "name": "1000-3000亿"},
                        {"key": "3000y_10000y", "name": "3000亿-1万亿"},
                        {"key": "gte_10000y", "name": "1万亿以上"},
                    ],
                },
            }
            date_list.append(trade_date)

        if not date_payloads:
            return self._missing("城市气泡图有效数据为空")

        news_by_industry = self._build_news_by_industry(latest_industry_by_code)
        payload = {
            "schema_version": "china_city_bubble.v1",
            "latest_date": date_list[0],
            "date_list": date_list,
            "dates": date_payloads,
            "news_by_industry": news_by_industry,
            "market_cap_unit": "yuan",
            "location_mapping": {
                "path": str(REFERENCE_DATA_DIR / "stock_location_mapping.json"),
                "available": bool(location_mapping),
                "schema": {
                    "000001": {
                        "province": "广东省",
                        "city": "深圳",
                        "lng": 114.0579,
                        "lat": 22.5431,
                    }
                },
                "note": "当前基础股本文件不含注册地/办公地。提供 stock_location_mapping.json 后会优先使用精确城市定位，缺失股票按交易所所在地降级聚合。",
            },
            "location_quality": dict(location_quality_total),
        }
        return self._write_section("china_city_bubble.json", payload)

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

    def _load_stock_basic_info(self) -> dict[str, dict]:
        path = REFERENCE_DATA_DIR / "stock_basic_info.pkl"
        if not path.exists():
            return {}
        try:
            import pandas as pd

            df = pd.read_pickle(path)
        except Exception:
            return {}

        lookup: dict[str, dict] = {}
        for row in df.to_dict("records"):
            code = self._normalize_stock_code(row.get("股票代码") or row.get("代码") or row.get("stock_code"))
            if not code:
                continue
            lookup[code] = {
                "stock_name": row.get("股票简称") or row.get("名称") or row.get("stock_name"),
                "industry": self._clean_group_name(row.get("行业") or row.get("industry")),
                "exchange": self._clean_group_name(row.get("交易所") or row.get("exchange"), fallback=get_exchange(code)),
                "total_shares": self._as_float(row.get("总股本") or row.get("total_shares")),
                "float_shares": self._as_float(row.get("流通股") or row.get("float_shares")),
                "province": row.get("省份") or row.get("province") or row.get("注册省份"),
                "city": row.get("城市") or row.get("city") or row.get("注册城市"),
                "lng": self._as_float(row.get("lng") or row.get("经度")),
                "lat": self._as_float(row.get("lat") or row.get("纬度")),
            }
        return lookup

    def _load_stock_location_mapping(self) -> dict[str, dict]:
        path = REFERENCE_DATA_DIR / "stock_location_mapping.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            if isinstance(payload.get("stocks"), list):
                rows = payload["stocks"]
            else:
                rows = [{**value, "code": key} for key, value in payload.items() if isinstance(value, dict)]
        else:
            return {}
        mapping: dict[str, dict] = {}
        for row in rows:
            code = self._normalize_stock_code(row.get("code") or row.get("stock_code") or row.get("股票代码"))
            if not code:
                continue
            mapping[code] = {
                "province": row.get("province") or row.get("省份"),
                "city": row.get("city") or row.get("城市"),
                "lng": self._as_float(row.get("lng") or row.get("longitude") or row.get("经度")),
                "lat": self._as_float(row.get("lat") or row.get("latitude") or row.get("纬度")),
                "source": row.get("source") or row.get("来源") or "stock_location_mapping",
                "quality": row.get("quality") or row.get("定位质量") or "mapped",
            }
        return mapping

    def _resolve_stock_location(self, code: str, exchange: str, basic: dict, location_mapping: dict[str, dict]) -> dict:
        mapped = location_mapping.get(code)
        if mapped and mapped.get("province") and mapped.get("city"):
            lng = self._as_float(mapped.get("lng"))
            lat = self._as_float(mapped.get("lat"))
            if lng is None or lat is None:
                lng, lat = self._resolve_city_coordinate(str(mapped.get("city")))
            return {
                "province": mapped.get("province"),
                "city": mapped.get("city"),
                "lng": lng,
                "lat": lat,
                "quality": mapped.get("quality") or "mapped",
                "source": mapped.get("source") or "stock_location_mapping",
            }

        if basic.get("province") and basic.get("city"):
            lng = self._as_float(basic.get("lng"))
            lat = self._as_float(basic.get("lat"))
            if lng is None or lat is None:
                lng, lat = self._resolve_city_coordinate(str(basic.get("city")))
            if lng is not None and lat is not None:
                return {
                    "province": basic.get("province"),
                    "city": basic.get("city"),
                    "lng": lng,
                    "lat": lat,
                    "quality": "basic_info",
                    "source": "stock_basic_info",
                }

        exchange_locations = {
            "上海": {"province": "上海市", "city": "上海", "lng": 121.4737, "lat": 31.2304},
            "深圳": {"province": "广东省", "city": "深圳", "lng": 114.0579, "lat": 22.5431},
            "北京": {"province": "北京市", "city": "北京", "lng": 116.4074, "lat": 39.9042},
        }
        exchange_text = str(exchange or "")
        if "上海" in exchange_text:
            location = exchange_locations["上海"]
        elif "深圳" in exchange_text:
            location = exchange_locations["深圳"]
        elif "北京" in exchange_text or code.startswith(("8", "9")):
            location = exchange_locations["北京"]
        else:
            return {"province": "未知", "city": "未知", "lng": None, "lat": None, "quality": "missing"}
        return {**location, "quality": "exchange_fallback", "source": "exchange"}

    @staticmethod
    def _resolve_city_coordinate(city: str) -> tuple[float | None, float | None]:
        normalized = city.replace("市", "").replace("地区", "").strip()
        coords = {
            "北京": (116.4074, 39.9042),
            "上海": (121.4737, 31.2304),
            "深圳": (114.0579, 22.5431),
            "广州": (113.2644, 23.1291),
            "杭州": (120.1551, 30.2741),
            "南京": (118.7969, 32.0603),
            "苏州": (120.5853, 31.2989),
            "宁波": (121.5504, 29.8746),
            "无锡": (120.3124, 31.4909),
            "常州": (119.9741, 31.8113),
            "绍兴": (120.5821, 29.9971),
            "嘉兴": (120.7555, 30.7461),
            "台州": (121.4208, 28.6564),
            "温州": (120.6994, 27.9949),
            "合肥": (117.2272, 31.8206),
            "芜湖": (118.4331, 31.3529),
            "济南": (117.1201, 36.6512),
            "青岛": (120.3826, 36.0671),
            "烟台": (121.4479, 37.4638),
            "潍坊": (119.1618, 36.7069),
            "郑州": (113.6254, 34.7466),
            "武汉": (114.3054, 30.5928),
            "长沙": (112.9388, 28.2282),
            "南昌": (115.8582, 28.6829),
            "福州": (119.2965, 26.0745),
            "厦门": (118.0894, 24.4798),
            "泉州": (118.6759, 24.8741),
            "成都": (104.0665, 30.5728),
            "重庆": (106.5516, 29.5630),
            "西安": (108.9398, 34.3416),
            "天津": (117.2000, 39.1333),
            "石家庄": (114.5149, 38.0428),
            "唐山": (118.1802, 39.6309),
            "太原": (112.5492, 37.8706),
            "呼和浩特": (111.7492, 40.8426),
            "沈阳": (123.4315, 41.8057),
            "大连": (121.6147, 38.9140),
            "长春": (125.3235, 43.8171),
            "哈尔滨": (126.6424, 45.7567),
            "南宁": (108.3669, 22.8170),
            "桂林": (110.2900, 25.2736),
            "海口": (110.1983, 20.0440),
            "三亚": (109.5083, 18.2479),
            "贵阳": (106.6302, 26.6470),
            "昆明": (102.8329, 24.8801),
            "拉萨": (91.1175, 29.6475),
            "兰州": (103.8343, 36.0611),
            "西宁": (101.7782, 36.6171),
            "银川": (106.2309, 38.4872),
            "乌鲁木齐": (87.6168, 43.8256),
        }
        return coords.get(normalized, (None, None))

    @staticmethod
    def _normalize_city_name(city: str) -> str:
        text = str(city or "").strip()
        suffixes = ["特别行政区", "自治州", "地区", "盟", "市"]
        for suffix in suffixes:
            if text.endswith(suffix) and len(text) > len(suffix):
                return text[: -len(suffix)]
        return text

    def _build_news_by_industry(self, industry_by_code: dict[str, str]) -> dict[str, list[dict]]:
        grouped: dict[str, dict[int, dict]] = defaultdict(dict)
        stock_codes = self.news_repository.list_stock_codes_with_news()
        for code in stock_codes[:160]:
            normalized = self._normalize_stock_code(code)
            industry = industry_by_code.get(normalized)
            if not industry or industry == "未知":
                continue
            for article in self.news_repository.query_news_by_stock(normalized, limit=8):
                article_id = article.get("id")
                if not article_id:
                    continue
                grouped[industry][int(article_id)] = {
                    "id": article_id,
                    "stock_code": normalized,
                    "title": article.get("title", ""),
                    "source": article.get("source", ""),
                    "published_at": article.get("published_at", ""),
                    "sentiment": article.get("sentiment") or "中性",
                    "event_type": article.get("event_type") or "其他",
                    "content": (article.get("content") or article.get("summary") or "")[:240],
                    "url": article.get("url", ""),
                }
        if not grouped:
            for article in self.news_repository.query_all_news(limit=240):
                code = self._normalize_stock_code(article.get("stock_code"))
                industry = industry_by_code.get(code)
                if not code or not industry or industry == "未知":
                    continue
                article_id = article.get("id")
                grouped[industry][int(article_id)] = {
                    "id": article_id,
                    "stock_code": code,
                    "title": article.get("title", ""),
                    "source": article.get("source", ""),
                    "published_at": article.get("published_at", ""),
                    "sentiment": article.get("sentiment") or "中性",
                    "event_type": article.get("event_type") or "其他",
                    "content": (article.get("content") or article.get("summary") or "")[:240],
                    "url": article.get("url", ""),
                }
        result: dict[str, list[dict]] = {}
        for industry, articles in grouped.items():
            result[industry] = sorted(
                articles.values(),
                key=lambda item: str(item.get("published_at") or ""),
                reverse=True,
            )[:24]
        return result

    @staticmethod
    def _market_cap_bucket(value: float) -> str:
        if value >= 1_000_000_000_000:
            return "gte_10000y"
        if value >= 300_000_000_000:
            return "3000y_10000y"
        if value >= 100_000_000_000:
            return "1000y_3000y"
        if value >= 50_000_000_000:
            return "500y_1000y"
        return "lt_500y"

    def _load_dragon_tiger_operations(self) -> list[dict]:
        rows = self.dragon_tiger_repository.list_operations()
        merged: dict[tuple, dict] = {}

        def add(row: dict) -> None:
            date = str(row.get("date") or "")
            stock_code = self._normalize_stock_code(row.get("stock_code") or row.get("stockCode"))
            stock_name = str(row.get("stock_name") or row.get("stockName") or "")
            seat_name = str(row.get("seat_name") or row.get("seatName") or "")
            direction = str(row.get("direction") or "")
            amount = self._as_float(row.get("amount")) or 0.0
            if not date or not stock_code or not seat_name or not direction:
                return
            normalized = {
                "date": date,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "seat_name": seat_name,
                "direction": direction,
                "amount": amount,
                "net_amount": amount if direction == "买" else -amount,
                "seat_type": row.get("seat_type") or row.get("seatType"),
                "trader_alias": row.get("trader_alias") or row.get("traderAlias"),
            }
            key = (date, stock_code, stock_name, seat_name, direction, round(amount, 4))
            merged[key] = normalized

        for row in rows:
            add(row)

        for path in sorted(DRAGON_TIGER_OUTPUT_DIR.glob("dragon_tiger_analysis_*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict) or payload.get("schemaVersion") != "dragon_tiger_analysis.v1":
                continue
            for row in payload.get("operations") or []:
                if isinstance(row, dict):
                    add(row)

        return sorted(merged.values(), key=lambda item: (item["date"], item["amount"]), reverse=True)

    @staticmethod
    def _aggregate_dragon_active_stocks(records: list[dict], limit: int = 20) -> list[dict]:
        grouped: dict[str, dict] = {}
        for row in records:
            key = row["stockCode"]
            item = grouped.setdefault(
                key,
                {"code": key, "name": row["stockName"], "seat_names": set(), "buy": 0.0, "sell": 0.0},
            )
            item["seat_names"].add(row["seatName"])
            if row["direction"] == "买":
                item["buy"] += float(row.get("amount") or 0)
            elif row["direction"] == "卖":
                item["sell"] += float(row.get("amount") or 0)
        result = []
        for item in grouped.values():
            result.append({
                "code": item["code"],
                "name": item["name"],
                "seatCount": len(item["seat_names"]),
                "buy": round(item["buy"], 2),
                "sell": round(item["sell"], 2),
                "net": round(item["buy"] - item["sell"], 2),
            })
        return sorted(result, key=lambda item: (item["seatCount"], item["buy"]), reverse=True)[:limit]

    @staticmethod
    def _aggregate_dragon_active_seats(records: list[dict], limit: int = 20) -> list[dict]:
        grouped: dict[str, dict] = {}
        for row in records:
            key = row["seatName"]
            item = grouped.setdefault(
                key,
                {
                    "name": key,
                    "type": row.get("seatType"),
                    "alias": row.get("alias"),
                    "count": 0,
                    "buy": 0.0,
                    "sell": 0.0,
                },
            )
            item["count"] += 1
            if row.get("alias"):
                item["alias"] = row.get("alias")
            if row["direction"] == "买":
                item["buy"] += float(row.get("amount") or 0)
            elif row["direction"] == "卖":
                item["sell"] += float(row.get("amount") or 0)
        result = []
        for item in grouped.values():
            result.append({
                "name": item["name"],
                "type": item["type"],
                "alias": item["alias"],
                "count": item["count"],
                "buy": round(item["buy"], 2),
                "sell": round(item["sell"], 2),
                "net": round(item["buy"] - item["sell"], 2),
            })
        return sorted(result, key=lambda item: (item["count"], item["buy"]), reverse=True)[:limit]

    @staticmethod
    def _write_section(filename: str, payload: dict) -> dict:
        path = APP_DATA_DIR / filename
        path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        return {"available": True, "path": f"./data/{filename}", "message": ""}

    @staticmethod
    def _copy_static_assets() -> None:
        china_map = REFERENCE_DATA_DIR / "china_echarts_map.js"
        if china_map.exists():
            shutil.copyfile(china_map, APP_DATA_DIR / "china_echarts_map.js")

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
            result = float(value)
            if math.isnan(result) or math.isinf(result):
                return None
            return result
        except Exception:
            return None
