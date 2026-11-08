"""东方财富龙虎榜数据源。

历史版本这里存在两个严重问题，已在本轮修复：

1. `_build_mock_operations` / `_mock_from_change`：抓不到席位明细时**凭空编造**
   「知名游资席位」「机构专用」「深股通专用」及其金额，这些假数据会直接进库，
   进而进入关系图与页面。现在改为：拿不到就留空并记录数据质量告警，绝不伪造。
2. `StockApiFallbackSource` 依赖第三方付费接口且同样造假，已移除；
   替换为基于东方财富数据中心真实报表的降级源。

席位明细改为**按日批量**拉取（`RPT_BILLBOARD_DAILYDETAILSBUY/SELL`），
一个交易日只需 2 次请求即可拿到全市场席位，比原来的「每只股票 2 次」快两个数量级，
这也是 2026 全年数据能在合理时间内补齐的前提。
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

import requests

from stockgraph.domain.dragon_tiger import DailySummary, DragonTigerBatch, SeatOperation
from stockgraph.infrastructure.data_sources.dragon_tiger.base import DragonTigerSource

logger = logging.getLogger(__name__)

DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://data.eastmoney.com/stock/lhb.html",
    "Connection": "keep-alive",
}
AMOUNT_UNIT = 10000.0  # 接口返回元，库内统一存万元


def _datacenter_get(
    report_name: str,
    *,
    filter_expr: str = "",
    page_size: int = 500,
    sort_columns: str = "",
    sort_types: int = -1,
    max_pages: int = 20,
) -> list[dict]:
    """拉取数据中心报表（自动翻页）。"""
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        params = {
            "reportName": report_name,
            "columns": "ALL",
            "pageNumber": page,
            "pageSize": page_size,
            "source": "WEB",
            "client": "WEB",
        }
        if filter_expr:
            params["filter"] = filter_expr
        if sort_columns:
            params["sortColumns"] = sort_columns
            params["sortTypes"] = sort_types
        try:
            response = requests.get(DATACENTER_URL, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.error("东方财富数据中心请求失败 %s: %s", report_name, exc)
            break

        if not payload.get("success"):
            logger.warning("数据中心报表 %s 返回失败: %s", report_name, payload.get("message"))
            break

        result = payload.get("result") or {}
        data = result.get("data") or []
        rows.extend(data)
        pages = int(result.get("pages") or 1)
        if page >= pages or not data:
            break
        time.sleep(0.2)
    return rows


def fetch_seat_details_bulk(trade_date: str) -> dict[str, list[SeatOperation]]:
    """一次拉取某交易日全市场席位明细，返回 {股票代码: [席位操作]}。"""
    grouped: dict[str, list[SeatOperation]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()

    for report_name, direction in (
        ("RPT_BILLBOARD_DAILYDETAILSBUY", "买"),
        ("RPT_BILLBOARD_DAILYDETAILSSELL", "卖"),
    ):
        rows = _datacenter_get(
            report_name,
            filter_expr=f"(TRADE_DATE='{trade_date}')",
            page_size=500,
        )
        for row in rows:
            code = str(row.get("SECURITY_CODE") or "").strip()
            seat_name = str(row.get("OPERATEDEPT_NAME") or "").strip()
            if not code or not seat_name:
                continue
            amount = float(row.get("BUY" if direction == "买" else "SELL") or 0.0)
            if amount <= 0:
                continue
            key = (code, seat_name, direction)
            if key in seen:
                continue
            seen.add(key)
            grouped[code].append(
                SeatOperation(seat_name=seat_name, direction=direction, amount=amount / AMOUNT_UNIT)
            )
    return dict(grouped)


def fetch_seat_details(trade_date: str, stock_code: str) -> list[SeatOperation]:
    """单只股票的席位明细（akshare 实现），保留给单日增量和排障使用。"""
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 未安装，跳过席位明细抓取")
        return []

    operations: list[SeatOperation] = []
    compact_date = trade_date.replace("-", "")
    for flag, direction, amount_key in (("买入", "买", "买入金额"), ("卖出", "卖", "卖出金额")):
        try:
            frame = ak.stock_lhb_stock_detail_em(symbol=stock_code, date=compact_date, flag=flag)
        except Exception as exc:  # noqa: BLE001
            logger.debug("AKShare 席位抓取失败 %s %s: %s", stock_code, flag, exc)
            continue
        if frame is None or frame.empty:
            continue
        for _, row in frame.iterrows():
            seat_name = str(row.get("交易营业部名称") or "").strip()
            amount = row.get(amount_key, 0)
            try:
                amount_value = float(amount or 0)
            except (TypeError, ValueError):
                amount_value = 0.0
            if seat_name and amount_value > 0:
                operations.append(
                    SeatOperation(seat_name=seat_name, direction=direction, amount=amount_value / AMOUNT_UNIT)
                )
    return operations


class EastMoneyApiSource(DragonTigerSource):
    name = "东方财富API"

    def __init__(self, use_bulk_seats: bool = True) -> None:
        self.use_bulk_seats = use_bulk_seats

    def fetch(self, trade_date: str) -> DragonTigerBatch | None:
        items = _datacenter_get(
            "RPT_ORGANIZATION_TRADE_DETAILS",
            filter_expr=f"(TRADE_DATE='{trade_date}')",
            page_size=500,
            sort_columns="TRADE_DATE",
        )
        if not items:
            logger.warning("东方财富 API 无数据: %s", trade_date)
            return None

        seat_map: dict[str, list[SeatOperation]] = {}
        if self.use_bulk_seats:
            seat_map = fetch_seat_details_bulk(trade_date)
            logger.info("批量席位明细: %s 共 %d 只股票", trade_date, len(seat_map))

        stocks: list[DailySummary] = []
        missing_seats: list[str] = []
        for item in items:
            stock_code = str(item.get("SECURITY_CODE") or "").strip()
            operations = seat_map.get(stock_code) or []
            if not operations:
                operations = fetch_seat_details(trade_date, stock_code)
            if not operations:
                missing_seats.append(stock_code)
            stocks.append(
                DailySummary(
                    stock_code=stock_code,
                    stock_name=str(item.get("SECURITY_NAME_ABBR") or ""),
                    listing_reason=str(item.get("EXPLANATION") or ""),
                    total_buy=float(item.get("BUY_AMT") or 0.0) / AMOUNT_UNIT,
                    total_sell=float(item.get("SELL_AMT") or 0.0) / AMOUNT_UNIT,
                    net_amount=float(item.get("NET_BUY_AMT") or 0.0) / AMOUNT_UNIT,
                    buy_seat_count=int(item.get("BUY_TIMES") or 0),
                    sell_seat_count=int(item.get("SELL_TIMES") or 0),
                    seat_operations=operations,
                )
            )

        if missing_seats:
            logger.warning(
                "%s 有 %d/%d 只股票未取到席位明细（已留空，不做任何补造）: %s",
                trade_date,
                len(missing_seats),
                len(stocks),
                ",".join(missing_seats[:10]),
            )
        return DragonTigerBatch(trade_date=trade_date, stocks=stocks)


class EastMoneyDatacenterFallbackSource(DragonTigerSource):
    """降级源：只取上榜汇总，不取席位明细。

    用于 `RPT_ORGANIZATION_TRADE_DETAILS` 异常但榜单报表仍可用的场景。
    数据全部来自真实报表，缺失的席位信息保持为空。
    """

    name = "东方财富数据中心(仅汇总)"

    def fetch(self, trade_date: str) -> DragonTigerBatch | None:
        rows = _datacenter_get(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_expr=f"(TRADE_DATE='{trade_date}')",
            page_size=500,
            sort_columns="BILLBOARD_NET_AMT",
        )
        if not rows:
            return None

        stocks = [
            DailySummary(
                stock_code=str(row.get("SECURITY_CODE") or ""),
                stock_name=str(row.get("SECURITY_NAME_ABBR") or ""),
                listing_reason=str(row.get("EXPLANATION") or ""),
                total_buy=float(row.get("BILLBOARD_BUY_AMT") or 0.0) / AMOUNT_UNIT,
                total_sell=float(row.get("BILLBOARD_SELL_AMT") or 0.0) / AMOUNT_UNIT,
                net_amount=float(row.get("BILLBOARD_NET_AMT") or 0.0) / AMOUNT_UNIT,
                buy_seat_count=_as_int(row.get("BUY_SEAT")),
                sell_seat_count=_as_int(row.get("SELL_SEAT")),
            )
            for row in rows
        ]
        return DragonTigerBatch(trade_date=trade_date, stocks=stocks)


def _as_int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0
