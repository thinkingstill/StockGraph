"""数据源适配器的纯函数级测试（不联网）。

覆盖三个曾经出过错、且不依赖网络就能验证的点：
1. 财联社 `sign` 的签名算法（顺序敏感 + 双层哈希）；
2. 东方财富 `stockList` 的市场前缀清洗（港股/板块必须丢掉）；
3. 龙虎榜金额单位换算（接口给万元，入库要元）。
"""

from __future__ import annotations

import hashlib

import pytest

from stockgraph.infrastructure.data_sources.news._common import (
    PoliteSession,
    normalize_em_stock_list,
)


class TestCLSSign:
    def test_sign_matches_md5_of_sha1_of_sorted_query(self):
        from stockgraph.infrastructure.data_sources.news.cls import build_sign

        params = {"app": "CailianpressWeb", "os": "web", "sv": "7.7.5"}
        query = "app=CailianpressWeb&os=web&sv=7.7.5"
        expected = hashlib.md5(
            hashlib.sha1(query.encode("utf-8")).hexdigest().encode("utf-8")
        ).hexdigest()
        assert build_sign(params) == expected

    def test_sign_is_order_independent(self):
        from stockgraph.infrastructure.data_sources.news.cls import build_sign

        first = build_sign({"b": "2", "a": "1"})
        second = build_sign({"a": "1", "b": "2"})
        assert first == second

    def test_sign_changes_with_value(self):
        from stockgraph.infrastructure.data_sources.news.cls import build_sign

        assert build_sign({"a": "1"}) != build_sign({"a": "2"})


class TestNormalizeEMStockList:
    def test_keeps_a_share_markets_only(self):
        raw = ["1.600519", "0.000001", "0.300750", "1.688981"]
        codes = [item["stock_code"] for item in normalize_em_stock_list(raw)]
        assert codes == ["600519", "000001", "300750", "688981"]

    def test_drops_hk_board_and_malformed(self):
        raw = ["150.014238", "90.BK0704", "1.60051", "abc", "", "1.600519"]
        codes = [item["stock_code"] for item in normalize_em_stock_list(raw)]
        assert codes == ["600519"]

    def test_deduplicates(self):
        raw = ["1.600519", "1.600519", "0.000001"]
        codes = [item["stock_code"] for item in normalize_em_stock_list(raw)]
        assert codes == ["600519", "000001"]

    def test_none_input(self):
        assert normalize_em_stock_list(None) == []


class TestPoliteSession:
    def test_min_interval_configurable_via_env(self, monkeypatch):
        monkeypatch.setenv("STOCKGRAPH_REQUEST_DELAY_SECONDS", "0.5")
        session = PoliteSession()
        assert session.delay_seconds == pytest.approx(0.5)

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("STOCKGRAPH_REQUEST_DELAY_SECONDS", "abc")
        session = PoliteSession()
        assert session.delay_seconds == pytest.approx(0.8)

    def test_throttle_sleeps_between_calls(self, monkeypatch):
        """连续两次请求之间必须真的等待，避免把数据源打挂。"""
        session = PoliteSession(delay_seconds=0.05)
        slept: list[float] = []
        monkeypatch.setattr(
            "stockgraph.infrastructure.data_sources.news._common.time.sleep",
            lambda seconds: slept.append(seconds),
        )
        session._throttle()
        session._throttle()
        assert slept, "第一次调用后应记录时间戳，第二次应触发 sleep"


class TestDragonTigerAmountUnit:
    def test_amount_unit_is_ten_thousand(self):
        """东财龙虎榜接口金额单位是万元，入库统一换算成元。"""
        from stockgraph.infrastructure.data_sources.dragon_tiger.eastmoney import AMOUNT_UNIT

        assert AMOUNT_UNIT == 10000.0

    def test_no_mock_source_remains_exported(self):
        """回归：原实现导出的造假数据源必须已从包里删除。"""
        import stockgraph.infrastructure.data_sources.dragon_tiger as pkg

        for name in ("StockApiFallbackSource", "EastMoneyWebFallbackSource", "SinaFallbackSource"):
            assert not hasattr(pkg, name), f"{name} 应已删除（历史上会伪造席位数据）"
