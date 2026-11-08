"""新闻实体识别测试。

原实现的两个硬伤：
1. 用 `\\b(\\d{6})\\b` 匹配股票代码 —— 中文是单词字符，`600519股` 这种写法直接匹配失败；
2. 完全不做公司简称识别，导致「贵州茅台发布三季报」这类纯文字新闻一条实体都提不出来。
"""

from __future__ import annotations

import json

import pytest

from stockgraph.domain.news import tagging
from stockgraph.domain.news.models import NewsArticle


@pytest.fixture(autouse=True)
def fake_stock_index(monkeypatch, tmp_path):
    """用小型字典替代 5000+ 真实字典，让测试不依赖 data/reference。"""
    payload = {
        "600519": "贵州茅台",
        "000001": "平安银行",
        "300750": "宁德时代",
        "600000": "浦发银行",
    }
    path = tmp_path / "all_stock_codes.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(tagging, "REFERENCE_DATA_DIR", tmp_path)
    tagging.stock_name_index.cache_clear()
    tagging._name_to_code.cache_clear()
    tagging._matchable_names.cache_clear()
    yield
    tagging.stock_name_index.cache_clear()
    tagging._name_to_code.cache_clear()
    tagging._matchable_names.cache_clear()


def make_article(title: str, content: str = "", metadata: dict | None = None) -> NewsArticle:
    return NewsArticle(
        source="test",
        title=title,
        content=content,
        url="https://example.com/a",
        published_at="2026-01-05 09:30:00",
        metadata=metadata or {},
    )


def test_finds_codes_embedded_in_chinese_text():
    """回归：中文字符紧贴代码时也要能识别。"""
    assert tagging.find_stock_codes("600519股今日涨停") == ["600519"]
    assert tagging.find_stock_codes("关注300750。") == ["300750"]


def test_ignores_invalid_prefix_and_partial_numbers():
    assert tagging.find_stock_codes("编号12345678 和 512345") == []
    assert tagging.find_stock_codes("金额 6005190000 元") == []


def test_deduplicates_codes_preserving_order():
    assert tagging.find_stock_codes("600519 涨了，600519 又涨了，000001") == ["600519", "000001"]


def test_finds_company_short_names():
    names = tagging.find_stock_names("贵州茅台发布三季报，平安银行同步披露")
    assert "贵州茅台" in names
    assert "平安银行" in names


def test_short_names_below_min_length_are_ignored():
    """2 字简称误报率过高，明确不作为实体。"""
    assert "浦发" not in tagging.find_stock_names("浦发银行发布公告")


def test_link_article_entities_merges_source_and_text_hits():
    article = make_article(
        "贵州茅台：第三季度净利润同比增长",
        "公司代码 600519，同日 000001 也披露了数据",
        metadata={"stock_codes": ["600519"]},
    )
    tagged = tagging.link_article_entities(article)
    codes = {entity.entity_code for entity in tagged.entities}
    assert codes == {"600519", "000001"}

    confidence = {entity.entity_code: entity.confidence for entity in tagged.entities}
    # 数据源标注优先于文本命中
    assert confidence["600519"] == 1.0
    assert confidence["000001"] >= 0.9
    reasons = {link.target_code: link.link_reason for link in tagged.links}
    assert reasons["600519"] == "数据源标注"


def test_link_article_entities_matches_by_name_when_code_absent():
    article = make_article("宁德时代宣布扩产", "公司拟新建电池产线")
    tagged = tagging.link_article_entities(article)
    assert [entity.entity_code for entity in tagged.entities] == ["300750"]
    assert tagged.links[0].link_reason == "文本命中简称"


def test_sentiment_and_event_type_inferred():
    good = tagging.link_article_entities(make_article("某公司中标大单并回购股份"))
    assert good.sentiment == "利好"
    bad = tagging.link_article_entities(make_article("某公司被立案调查，股东减持"))
    assert bad.sentiment == "利空"
    neutral = tagging.link_article_entities(make_article("某公司召开股东大会"))
    assert neutral.sentiment == "中性"
    assert neutral.event_type == "其他"

    deal = tagging.link_article_entities(make_article("某公司宣布重大资产重组"))
    assert deal.event_type == "并购重组"


def test_missing_reference_file_degrades_gracefully(monkeypatch, tmp_path):
    """字典缺失时不能崩，退化为只有代码匹配。"""
    monkeypatch.setattr(tagging, "REFERENCE_DATA_DIR", tmp_path / "nope")
    tagging.stock_name_index.cache_clear()
    tagging._matchable_names.cache_clear()
    assert tagging.stock_name_index() == {}
    assert tagging.find_stock_names("贵州茅台") == []

    tagged = tagging.link_article_entities(make_article("贵州茅台 600519"))
    assert [entity.entity_code for entity in tagged.entities] == ["600519"]
