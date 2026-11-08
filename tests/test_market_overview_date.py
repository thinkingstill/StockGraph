"""市场概览日期格式一致性回归测试。

真实踩过的坑：`AkshareMarketOverviewSource.get_exchange_date()` 返回"报告时间"
是 `20261106`（无横线），而历史回补 `backfill_market_daily.py` 写库用的是
`2026-11-06`（带横线）。不统一的结果是同一天在 `market_daily_snapshots` 里
分裂成两批——实测 111 万行带横线 vs 5578 行无横线，任何按日期聚合的查询
都会静默漏掉一半，且 `INSERT OR REPLACE` 主键不冲突所以两边都活着。
"""

from __future__ import annotations

import pytest

from stockgraph.application.services.market_overview import MarketOverviewService


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20261106", "2026-11-06"),
        ("2026-11-06", "2026-11-06"),
        ("20261106 ", "2026-11-06"),
        (" 2026-11-06", "2026-11-06"),
        ("20260105", "2026-01-05"),
    ],
)
def test_normalize_trade_date(raw, expected):
    service = MarketOverviewService.__new__(MarketOverviewService)
    assert service._normalize_trade_date(raw) == expected


def test_normalize_preserves_non_date_input():
    service = MarketOverviewService.__new__(MarketOverviewService)
    assert service._normalize_trade_date("") == ""
    assert service._normalize_trade_date("abc") == "abc"


def test_compact_filename_separate_from_db_key():
    """文件名用 YYYYMMDD，数据库键用 YYYY-MM-DD，二者必须分离。"""
    service = MarketOverviewService.__new__(MarketOverviewService)
    db_key = service._normalize_trade_date("20261106")
    assert db_key == "2026-11-06"
    # 文件名的紧凑格式由 replace 生成，不是直接复用 db_key
    compact = db_key.replace("-", "")
    assert compact == "20261106"
