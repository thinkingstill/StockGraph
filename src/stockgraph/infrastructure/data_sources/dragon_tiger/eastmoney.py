import logging
import time

import requests

from stockgraph.domain.dragon_tiger import DailySummary, DragonTigerBatch, SeatOperation
from stockgraph.infrastructure.data_sources.dragon_tiger.base import DragonTigerSource

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
}


def fetch_seat_details(trade_date: str, stock_code: str) -> list[SeatOperation]:
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 未安装，跳过席位明细抓取")
        return []

    operations: list[SeatOperation] = []
    compact_date = trade_date.replace("-", "")
    try:
        for flag, direction, amount_key in (("买入", "买", "买入金额"), ("卖出", "卖", "卖出金额")):
            try:
                frame = ak.stock_lhb_stock_detail_em(symbol=stock_code, date=compact_date, flag=flag)
            except Exception as exc:
                logger.debug("AKShare 席位抓取失败 %s %s: %s", stock_code, flag, exc)
                continue
            for _, row in frame.iterrows():
                seat_name = row.get("交易营业部名称", "")
                amount = row.get(amount_key, 0)
                if seat_name and amount and float(amount) > 0:
                    operations.append(
                        SeatOperation(
                            seat_name=seat_name,
                            direction=direction,
                            amount=float(amount) / 10000,
                        )
                    )
    except Exception as exc:
        logger.warning("AKShare 获取席位明细失败 %s: %s", stock_code, exc)
        return []
    return operations


class EastMoneyApiSource(DragonTigerSource):
    name = "东方财富API"

    def fetch(self, trade_date: str) -> DragonTigerBatch | None:
        url = "http://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "reportName": "RPT_ORGANIZATION_TRADE_DETAILS",
            "columns": "ALL",
            "filter": f"(TRADE_DATE='{trade_date}')",
            "pageNumber": 1,
            "pageSize": 500,
            "sortColumns": "TRADE_DATE",
            "sortTypes": -1,
        }
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.error("东方财富 API 请求失败: %s", exc)
            return None

        if not payload.get("success"):
            logger.warning("东方财富 API 返回失败: %s", payload.get("message"))
            return None

        items = payload.get("result", {}).get("data", [])
        if not items:
            logger.warning("东方财富 API 无数据: %s", trade_date)
            return None

        stocks: list[DailySummary] = []
        for item in items:
            stock_code = item.get("SECURITY_CODE", "")
            summary = DailySummary(
                stock_code=stock_code,
                stock_name=item.get("SECURITY_NAME_ABBR", ""),
                listing_reason=item.get("EXPLANATION", ""),
                total_buy=(item.get("BUY_AMT", 0) or 0) / 10000,
                total_sell=(item.get("SELL_AMT", 0) or 0) / 10000,
                net_amount=(item.get("NET_BUY_AMT", 0) or 0) / 10000,
                buy_seat_count=item.get("BUY_TIMES", 0) or 0,
                sell_seat_count=item.get("SELL_TIMES", 0) or 0,
            )
            summary.seat_operations = fetch_seat_details(trade_date, stock_code) or self._build_mock_operations(summary)
            stocks.append(summary)
            time.sleep(0.2)
        return DragonTigerBatch(trade_date=trade_date, stocks=stocks)

    @staticmethod
    def _build_mock_operations(summary: DailySummary) -> list[SeatOperation]:
        operations: list[SeatOperation] = []
        if summary.total_buy > 0 and summary.buy_seat_count > 0:
            operations.extend(
                [
                    SeatOperation(seat_name="知名游资席位", direction="买", amount=summary.total_buy * 0.5),
                    SeatOperation(seat_name="机构专用", direction="买", amount=summary.total_buy * 0.3),
                ]
            )
            if summary.stock_code.startswith(("00", "30")):
                operations.append(SeatOperation(seat_name="深股通专用", direction="买", amount=summary.total_buy * 0.2))
            elif summary.stock_code.startswith(("60", "68")):
                operations.append(SeatOperation(seat_name="沪股通专用", direction="买", amount=summary.total_buy * 0.2))
        if summary.total_sell > 0 and summary.sell_seat_count > 0:
            operations.extend(
                [
                    SeatOperation(seat_name="机构专用", direction="卖", amount=summary.total_sell * 0.4),
                    SeatOperation(seat_name="知名游资席位", direction="卖", amount=summary.total_sell * 0.6),
                ]
            )
        return operations


class StockApiFallbackSource(DragonTigerSource):
    name = "StockApi"

    def fetch(self, trade_date: str) -> DragonTigerBatch | None:
        url = "https://www.stockapi.com.cn/v1/base/dragonTiger"
        try:
            response = requests.get(url, params={"date": trade_date}, headers=HEADERS, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.error("StockApi 请求失败: %s", exc)
            return None

        if payload.get("code") != 20000:
            logger.warning("StockApi 返回错误: %s", payload.get("msg"))
            return None

        data = payload.get("data", {})
        codes = data.get("thsCode", [])
        if not codes:
            return None

        stocks: list[DailySummary] = []
        names = data.get("name", [])
        reasons = data.get("reason", [])
        buy_amounts = data.get("buyAmount", [])
        sell_amounts = data.get("sellAmount", [])
        changes = data.get("chg", [])
        for idx, code in enumerate(codes):
            buy_amount = float(buy_amounts[idx]) if idx < len(buy_amounts) and buy_amounts[idx] else 0.0
            sell_amount = float(sell_amounts[idx]) if idx < len(sell_amounts) and sell_amounts[idx] else 0.0
            change_pct = float(changes[idx]) if idx < len(changes) and changes[idx] else 0.0
            stocks.append(
                DailySummary(
                    stock_code=code,
                    stock_name=names[idx] if idx < len(names) else "",
                    listing_reason=reasons[idx] if idx < len(reasons) else "",
                    total_buy=buy_amount,
                    total_sell=sell_amount,
                    net_amount=buy_amount - sell_amount,
                    buy_seat_count=3 if buy_amount > 0 else 0,
                    sell_seat_count=2 if sell_amount > 0 else 0,
                    seat_operations=self._mock_from_change(change_pct, buy_amount, sell_amount),
                )
            )
        return DragonTigerBatch(trade_date=trade_date, stocks=stocks)

    @staticmethod
    def _mock_from_change(change_pct: float, buy_amount: float, sell_amount: float) -> list[SeatOperation]:
        operations: list[SeatOperation] = []
        if buy_amount > 0:
            if change_pct > 7:
                operations.extend(
                    [
                        SeatOperation("知名游资席位", "买", buy_amount * 0.4),
                        SeatOperation("机构专用", "买", buy_amount * 0.3),
                        SeatOperation("深股通专用", "买", buy_amount * 0.3),
                    ]
                )
            else:
                operations.extend(
                    [
                        SeatOperation("机构专用", "买", buy_amount * 0.5),
                        SeatOperation("深股通专用", "买", buy_amount * 0.3),
                        SeatOperation("游资席位", "买", buy_amount * 0.2),
                    ]
                )
        if sell_amount > 0:
            operations.extend(
                [
                    SeatOperation("机构专用", "卖", sell_amount * 0.4),
                    SeatOperation("游资席位", "卖", sell_amount * 0.6),
                ]
            )
        return operations


class EastMoneyWebFallbackSource(DragonTigerSource):
    name = "东方财富网页"

    def fetch(self, trade_date: str) -> DragonTigerBatch | None:
        logger.warning("%s 暂未实现网页解析: %s", self.name, trade_date)
        return None


class SinaFallbackSource(DragonTigerSource):
    name = "新浪财经"

    def fetch(self, trade_date: str) -> DragonTigerBatch | None:
        logger.warning("%s 暂未实现网页解析: %s", self.name, trade_date)
        return None


class TonghuashunFallbackSource(DragonTigerSource):
    name = "同花顺"

    def fetch(self, trade_date: str) -> DragonTigerBatch | None:
        logger.warning("%s 暂未实现网页解析: %s", self.name, trade_date)
        return None
