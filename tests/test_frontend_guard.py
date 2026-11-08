"""前端聚合的两处静默失真回归测试。

回归点 1：`_limited_stock_files` 只取最近 N 天，本身是对的。
但它曾被当成"数据全集"用于回补，把 5500 行的日行情文件覆盖成 4 行，
而所有聚合模块（超图 / 城市气泡 / 行业强弱 / 行情日历）都不会报错，
只会安静地产出一个小得多的结果。这里为残缺文件加上告警闸门。

回归点 2：`market_calendar` 曾用"行业内涨跌幅累加和"当行业涨幅，
一个 100 只股票的行业能跑出 +65%、-894% 这种数字。
"""

from __future__ import annotations

import json
import logging

import pytest

import stockgraph.application.services.unified_frontend as frontend_module
from stockgraph.application.services.unified_frontend import UnifiedFrontendService


def _write_day(directory, date: str, count: int) -> None:
    rows = [{"代码": f"{i:06d}", "涨跌幅": 1.0} for i in range(count)]
    (directory / f"stock_daily_{date}.json").write_text(json.dumps(rows), encoding="utf-8")


@pytest.fixture()
def market_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(frontend_module, "MARKET_DATA_DIR", tmp_path)
    return tmp_path


def test_limited_stock_files_caps_days(market_dir):
    for i in range(5):
        _write_day(market_dir, f"2026110{i}", 5500)

    picked = UnifiedFrontendService._limited_stock_files("STOCKGRAPH_TEST_DAYS", 2)

    assert len(picked) == 2
    # 必须是最新的两天
    assert [p.name for p in picked] == ["stock_daily_20261104.json", "stock_daily_20261103.json"]


def test_zero_means_no_limit(market_dir, monkeypatch):
    for i in range(5):
        _write_day(market_dir, f"2026110{i}", 5500)
    monkeypatch.setenv("STOCKGRAPH_TEST_DAYS", "0")

    assert len(UnifiedFrontendService._limited_stock_files("STOCKGRAPH_TEST_DAYS", 2)) == 5


def test_truncated_file_raises_warning(market_dir, caplog):
    _write_day(market_dir, "20261101", 5500)
    _write_day(market_dir, "20261102", 4)  # 被覆盖成 4 行的残缺文件

    with caplog.at_level(logging.WARNING, logger=frontend_module.__name__):
        UnifiedFrontendService._limited_stock_files("STOCKGRAPH_TEST_DAYS", 2)

    assert any("疑似残缺" in record.message for record in caplog.records)


def test_complete_files_stay_silent(market_dir, caplog):
    for i in range(3):
        _write_day(market_dir, f"2026110{i}", 5500)

    with caplog.at_level(logging.WARNING, logger=frontend_module.__name__):
        UnifiedFrontendService._limited_stock_files("STOCKGRAPH_TEST_DAYS", 3)

    assert not caplog.records


def test_calendar_uses_average_not_sum(market_dir, tmp_path, monkeypatch):
    """100 只股票全部 +1% 的行业，涨幅应报 1%，而不是 100%。"""
    rows = [
        {"代码": f"{i:06d}", "名称": f"股{i}", "行业": "银行", "涨跌幅": 1.0}
        for i in range(100)
    ] + [
        {"代码": f"{9000 + i:06d}", "名称": f"跌{i}", "行业": "地产", "涨跌幅": -0.5}
        for i in range(10)
    ]
    (market_dir / "stock_daily_20261106.json").write_text(
        json.dumps(rows, ensure_ascii=False), encoding="utf-8"
    )

    service = UnifiedFrontendService.__new__(UnifiedFrontendService)
    written: dict = {}
    monkeypatch.setattr(
        service,
        "_write_section",
        lambda name, payload: written.update(payload) or {"available": True, "path": name},
    )

    service._build_market_calendar_data()

    entry = written["years"]["2026"][0]
    assert entry["top_industry"] == "银行"
    assert entry["top_change_pct"] == pytest.approx(1.0)
    assert entry["top_industry_stock_count"] == 100
    assert entry["bottom_industry"] == "地产"
    assert entry["bottom_change_pct"] == pytest.approx(-0.5)
    assert entry["bottom_industry_stock_count"] == 10
