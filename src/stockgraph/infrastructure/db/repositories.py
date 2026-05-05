import logging
import json
import shutil
from dataclasses import asdict
from datetime import datetime

from stockgraph.core.paths import SOURCE_DIR
from stockgraph.domain.dragon_tiger import DragonTigerBatch, detect_seat_type, match_trader
from stockgraph.domain.graph import GraphSnapshot
from stockgraph.domain.market_overview import IndustryRanking, MarketOverviewBundle, StockHotRecord
from stockgraph.domain.news import NewsBatch
from stockgraph.infrastructure.db.connection import database_path, get_connection
from stockgraph.infrastructure.db.schema import SCHEMA_SQL

logger = logging.getLogger(__name__)


class DragonTigerRepository:
    def initialize_database(self) -> None:
        with get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    def import_legacy_database(self, overwrite: bool = False) -> bool:
        legacy_path = SOURCE_DIR / "dragon_tiger.db"
        target = database_path()
        if not legacy_path.exists():
            logger.warning("未找到 legacy 数据库: %s", legacy_path)
            return False
        if target.exists() and not overwrite:
            logger.info("目标数据库已存在，跳过 legacy 数据导入: %s", target)
            return False
        shutil.copy2(legacy_path, target)
        logger.info("已导入 legacy 数据库: %s -> %s", legacy_path, target)
        return True

    def purge_by_date(self, trade_date: str) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM daily_summaries WHERE date = ?", (trade_date,))
            conn.execute("DELETE FROM stock_seat_operations WHERE date = ?", (trade_date,))

    def save_batch(self, batch: DragonTigerBatch) -> bool:
        if not batch.stocks:
            logger.error("没有可入库的龙虎榜数据")
            return False

        saved = 0
        with get_connection() as conn:
            cursor = conn.cursor()
            for stock in batch.stocks:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO daily_summaries
                    (date, stock_code, stock_name, listing_reason, total_buy, total_sell,
                     net_amount, buy_seat_count, sell_seat_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch.trade_date,
                        stock.stock_code,
                        stock.stock_name,
                        stock.listing_reason,
                        stock.total_buy,
                        stock.total_sell,
                        stock.net_amount,
                        stock.buy_seat_count,
                        stock.sell_seat_count,
                    ),
                )

                for op in stock.seat_operations:
                    seat_type = op.seat_type or detect_seat_type(op.seat_name)
                    trader_alias = op.trader_alias or match_trader(op.seat_name)
                    self._upsert_seat_detail(
                        cursor=cursor,
                        seat_name=op.seat_name,
                        seat_type=seat_type,
                        amount=op.amount,
                    )
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO stock_seat_operations
                        (date, stock_code, stock_name, seat_name, direction, amount, net_amount, seat_type, trader_alias)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            batch.trade_date,
                            stock.stock_code,
                            stock.stock_name,
                            op.seat_name,
                            op.direction,
                            op.amount,
                            op.amount if op.direction == "买" else -op.amount,
                            seat_type,
                            trader_alias,
                        ),
                    )

                saved += 1
            conn.commit()
        logger.info("已保存龙虎榜股票记录: %s", saved)
        return saved > 0

    def export_operations(self) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT date, stock_code, stock_name, seat_name, direction, amount, seat_type, trader_alias
                FROM stock_seat_operations
                WHERE seat_name NOT IN ('自然人', '中小投资者', '其他自然人', '机构专用')
                ORDER BY date DESC, amount DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def export_query_dataset(self) -> dict:
        result: dict[str, list[dict]] = {}
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT date, stock_code, stock_name, seat_name, direction, amount, net_amount, seat_type, trader_alias
                FROM stock_seat_operations
                ORDER BY date DESC, amount DESC
                """
            ).fetchall()
        for row in rows:
            record = {
                "date": row["date"],
                "stockCode": row["stock_code"],
                "stockName": row["stock_name"],
                "seatName": row["seat_name"],
                "direction": row["direction"],
                "amount": row["amount"],
                "netAmount": row["net_amount"],
                "seatType": row["seat_type"],
                "alias": row["trader_alias"],
            }
            result.setdefault(row["date"], []).append(record)
        return result

    def list_trade_dates(self) -> list[str]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT date FROM stock_seat_operations ORDER BY date DESC"
            ).fetchall()
        return [row[0] for row in rows]

    def aggregate_active_stocks(self, trade_date: str, limit: int = 20) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT stock_code, stock_name, COUNT(DISTINCT seat_name) AS seat_cnt,
                       SUM(CASE WHEN direction='买' THEN amount ELSE 0 END) AS buy_amt,
                       SUM(CASE WHEN direction='卖' THEN amount ELSE 0 END) AS sell_amt
                FROM stock_seat_operations
                WHERE date = ?
                GROUP BY stock_code
                ORDER BY seat_cnt DESC, buy_amt DESC
                LIMIT ?
                """,
                (trade_date, limit),
            ).fetchall()
        return [
            {
                "code": row["stock_code"],
                "name": row["stock_name"],
                "seatCount": row["seat_cnt"],
                "buy": round(row["buy_amt"] or 0, 2),
                "sell": round(row["sell_amt"] or 0, 2),
                "net": round((row["buy_amt"] or 0) - (row["sell_amt"] or 0), 2),
            }
            for row in rows
        ]

    def aggregate_active_seats(self, trade_date: str, limit: int = 20) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT seat_name, seat_type, COUNT(*) AS cnt, MAX(trader_alias) AS trader_alias,
                       SUM(CASE WHEN direction='买' THEN amount ELSE 0 END) AS buy_amt,
                       SUM(CASE WHEN direction='卖' THEN amount ELSE 0 END) AS sell_amt
                FROM stock_seat_operations
                WHERE date = ?
                GROUP BY seat_name
                ORDER BY cnt DESC, buy_amt DESC
                LIMIT ?
                """,
                (trade_date, limit),
            ).fetchall()
        return [
            {
                "name": row["seat_name"],
                "type": row["seat_type"],
                "count": row["cnt"],
                "alias": row["trader_alias"],
                "buy": round(row["buy_amt"] or 0, 2),
                "sell": round(row["sell_amt"] or 0, 2),
                "net": round((row["buy_amt"] or 0) - (row["sell_amt"] or 0), 2),
            }
            for row in rows
        ]

    def list_operations(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        conditions = []
        params: list = []
        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT date, stock_code, stock_name, seat_name, direction, amount, seat_type, trader_alias
            FROM stock_seat_operations
            {where_clause}
            ORDER BY date DESC, amount DESC
        """
        with get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def aggregate_famous_traders(self, trade_date: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT seat_name, seat_type, COUNT(*) AS cnt, MAX(trader_alias) AS trader_alias,
                       SUM(CASE WHEN direction='买' THEN amount ELSE 0 END) AS buy_amt,
                       SUM(CASE WHEN direction='卖' THEN amount ELSE 0 END) AS sell_amt
                FROM stock_seat_operations
                WHERE date = ? AND trader_alias IS NOT NULL AND trader_alias != ''
                GROUP BY seat_name
                ORDER BY buy_amt DESC
                """,
                (trade_date,),
            ).fetchall()
        return [
            {
                "name": row["seat_name"],
                "type": row["seat_type"],
                "count": row["cnt"],
                "alias": row["trader_alias"],
                "buy": round(row["buy_amt"] or 0, 2),
                "sell": round(row["sell_amt"] or 0, 2),
                "net": round((row["buy_amt"] or 0) - (row["sell_amt"] or 0), 2),
            }
            for row in rows
        ]

    @staticmethod
    def _upsert_seat_detail(cursor, seat_name: str, seat_type: str, amount: float) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        existing = cursor.execute(
            "SELECT seat_name FROM seat_details WHERE seat_name = ?",
            (seat_name,),
        ).fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE seat_details
                SET last_seen_date = ?, total_operations = total_operations + 1, total_amount = total_amount + ?
                WHERE seat_name = ?
                """,
                (today, amount, seat_name),
            )
            return
        cursor.execute(
            """
            INSERT INTO seat_details
            (seat_name, seat_type, first_seen_date, last_seen_date, total_operations, total_amount)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (seat_name, seat_type, today, today, amount),
        )


class NewsRepository:
    def initialize_database(self) -> None:
        with get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    def save_batch(self, batch: NewsBatch) -> int:
        if not batch.articles:
            return 0
        inserted = 0
        with get_connection() as conn:
            cursor = conn.cursor()
            for article in batch.articles:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO news_articles
                    (source, title, content, summary, published_at, url, hash, sentiment, event_type, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article.source,
                        article.title,
                        article.content,
                        article.summary,
                        article.published_at,
                        article.url,
                        article.article_hash,
                        article.sentiment,
                        article.event_type,
                        json.dumps(article.metadata, ensure_ascii=False),
                    ),
                )
                if cursor.rowcount <= 0:
                    existing = cursor.execute(
                        "SELECT id FROM news_articles WHERE hash = ?",
                        (article.article_hash,),
                    ).fetchone()
                    article_id = existing["id"] if existing else None
                else:
                    article_id = cursor.lastrowid
                    inserted += 1

                if not article_id:
                    continue
                for entity in article.entities:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO news_entities
                        (article_id, entity_type, entity_code, entity_name, confidence)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (article_id, entity.entity_type, entity.entity_code, entity.entity_name, entity.confidence),
                    )
                for link in article.links:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO news_article_links
                        (article_id, target_type, target_code, target_name, link_reason)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (article_id, link.target_type, link.target_code, link.target_name, link.link_reason),
                    )
            conn.commit()
        return inserted

    def query_news_by_stock(self, stock_code: str, limit: int = 30) -> list[dict]:
        """查询与指定股票相关的新闻，优先通过实体关联，其次通过 metadata 中的 stock_code。"""
        with get_connection() as conn:
            # 方式1: 通过 news_entities 关联
            rows = conn.execute(
                """
                SELECT DISTINCT na.id, na.source, na.title, na.content, na.summary,
                       na.published_at, na.url, na.sentiment, na.event_type, na.metadata_json
                FROM news_articles na
                INNER JOIN news_entities ne ON ne.article_id = na.id
                WHERE ne.entity_code = ? AND ne.entity_type = 'stock'
                ORDER BY na.published_at DESC
                LIMIT ?
                """,
                (stock_code, limit),
            ).fetchall()

            # 方式2: 通过 metadata_json 中的 stock_code 字段补充
            extra_rows = conn.execute(
                """
                SELECT id, source, title, content, summary, published_at, url, sentiment, event_type, metadata_json
                FROM news_articles
                WHERE metadata_json LIKE ?
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (f'%"stock_code": "{stock_code}"%', limit),
            ).fetchall()

        # 合并去重
        seen_ids: set[int] = set()
        results: list[dict] = []
        for row in rows:
            rid = row["id"]
            if rid not in seen_ids:
                seen_ids.add(rid)
                results.append(self._row_to_news_dict(row))
        for row in extra_rows:
            rid = row["id"]
            if rid not in seen_ids:
                seen_ids.add(rid)
                results.append(self._row_to_news_dict(row))

        # 按发布时间降序排序
        results.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        return results[:limit]

    def query_all_news(self, limit: int = 100) -> list[dict]:
        """查询所有最新新闻。"""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, source, title, content, summary, published_at, url, sentiment, event_type, metadata_json
                FROM news_articles
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_news_dict(row) for row in rows]

    def list_stock_codes_with_news(self) -> list[str]:
        """列出所有有新闻关联的股票代码。"""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT entity_code
                FROM news_entities
                WHERE entity_type = 'stock'
                ORDER BY entity_code
                """
            ).fetchall()
            codes_from_entities = {row["entity_code"] for row in rows}

            # 也从 metadata 中提取
            meta_rows = conn.execute(
                """
                SELECT DISTINCT metadata_json FROM news_articles
                WHERE metadata_json LIKE '%"stock_code"%'
                """
            ).fetchall()
        codes_from_meta: set[str] = set()
        for row in meta_rows:
            try:
                meta = json.loads(row["metadata_json"])
                code = meta.get("stock_code")
                if code:
                    codes_from_meta.add(str(code))
            except Exception:
                pass

        all_codes = sorted(codes_from_entities | codes_from_meta)
        return all_codes

    def query_news_edges_by_date(self, trade_date: str, limit: int = 500) -> list[dict]:
        """查询某天新闻与股票实体的关联，用于图谱边构建。"""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT na.id, na.source, na.title, na.published_at, na.url,
                       na.sentiment, na.event_type, ne.entity_code, ne.entity_name
                FROM news_articles na
                INNER JOIN news_entities ne ON ne.article_id = na.id
                WHERE ne.entity_type = 'stock' AND substr(na.published_at, 1, 10) = ?
                ORDER BY na.published_at DESC
                LIMIT ?
                """,
                (trade_date, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "source": row["source"],
                "title": row["title"],
                "published_at": row["published_at"],
                "url": row["url"],
                "sentiment": row["sentiment"] or "中性",
                "event_type": row["event_type"] or "其他",
                "stock_code": row["entity_code"],
                "stock_name": row["entity_name"],
            }
            for row in rows
        ]

    @staticmethod
    def _row_to_news_dict(row) -> dict:
        meta = {}
        try:
            meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        except Exception:
            pass
        return {
            "id": row["id"],
            "source": row["source"],
            "title": row["title"],
            "content": row["content"],
            "summary": row["summary"],
            "published_at": row["published_at"],
            "url": row["url"],
            "sentiment": row["sentiment"],
            "event_type": row["event_type"],
            "stock_code": meta.get("stock_code", ""),
            "original_source": meta.get("original_source", ""),
        }


class GraphRepository:
    def initialize_database(self) -> None:
        with get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    def save_snapshot(self, snapshot: GraphSnapshot) -> int:
        self.initialize_database()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO graph_snapshots
                (snapshot_date, snapshot_type, version, metadata_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_date,
                    snapshot.snapshot_type,
                    snapshot.version,
                    json.dumps(snapshot.metadata, ensure_ascii=False),
                ),
            )
            cursor.execute(
                "DELETE FROM graph_edges WHERE snapshot_type = ? AND trade_date = ?",
                (snapshot.snapshot_type, snapshot.snapshot_date),
            )
            for node in snapshot.nodes:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO graph_nodes
                    (node_id, node_type, node_key, node_name, attributes_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        node.node_id,
                        node.node_type,
                        node.node_key,
                        node.node_name,
                        json.dumps(node.attributes, ensure_ascii=False),
                    ),
                )
            for edge in snapshot.edges:
                cursor.execute(
                    """
                    INSERT INTO graph_edges
                    (source_node_id, target_node_id, edge_type, weight, trade_date, snapshot_type, attributes_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge.source_node_id,
                        edge.target_node_id,
                        edge.edge_type,
                        edge.weight,
                        edge.trade_date,
                        snapshot.snapshot_type,
                        json.dumps(edge.attributes, ensure_ascii=False),
                    ),
                )
            conn.commit()
        return len(snapshot.edges)


class MarketOverviewRepository:
    def initialize_database(self) -> None:
        with get_connection() as conn:
            conn.executescript(SCHEMA_SQL)

    def save_bundle(self, bundle: MarketOverviewBundle) -> None:
        self.initialize_database()
        with get_connection() as conn:
            cursor = conn.cursor()
            for row in bundle.daily_snapshot.records:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO market_daily_snapshots
                    (trade_date, stock_code, stock_name, latest_price, change_pct, industry, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bundle.trade_date,
                        str(row.get("代码") or row.get("stock_code") or ""),
                        str(row.get("名称") or row.get("stock_name") or ""),
                        row.get("最新价"),
                        row.get("涨跌幅"),
                        row.get("行业"),
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )
            for record in bundle.hot_records:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO market_hot_rankings
                    (trade_date, stock_code, stock_name, latest_price, follow_rank, tweet_rank, deal_rank, change_pct, industry, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.trade_date,
                        record.stock_code,
                        record.stock_name,
                        record.latest_price,
                        record.follow_rank,
                        record.tweet_rank,
                        record.deal_rank,
                        record.change_pct,
                        record.industry,
                        json.dumps(asdict(record), ensure_ascii=False, default=str),
                    ),
                )
            for ranking in [*bundle.top_industries, *bundle.bottom_industries]:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO market_industry_rankings
                    (trade_date, industry, direction)
                    VALUES (?, ?, ?)
                    """,
                    (ranking.trade_date, ranking.industry, ranking.direction),
                )
            conn.commit()
