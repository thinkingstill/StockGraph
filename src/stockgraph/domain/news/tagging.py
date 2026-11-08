from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from stockgraph.core.paths import REFERENCE_DATA_DIR
from stockgraph.domain.news.models import NewsArticle, NewsEntity, NewsLink

logger = logging.getLogger(__name__)

POSITIVE_KEYWORDS = ("涨停", "中标", "业绩增长", "回购", "增持", "突破", "签约", "预增", "扭亏", "新高")
NEGATIVE_KEYWORDS = ("跌停", "减持", "处罚", "问询", "亏损", "终止", "下修", "预亏", "立案", "退市")
EVENT_PATTERNS = {
    "业绩": ("业绩", "预增", "预亏", "快报", "财报", "季报", "年报"),
    "并购重组": ("收购", "重组", "并购", "股权转让", "要约"),
    "监管": ("问询", "处罚", "立案", "监管", "警示函"),
    "投融资": ("定增", "融资", "回购", "增持", "减持", "可转债"),
    "产业政策": ("政策", "规划", "指引", "试点", "补贴"),
}

# 关键修复：原来用 \b 做边界，但中文属于单词字符，导致「600000股」这类写法匹配不到。
STOCK_CODE_PATTERN = re.compile(r"(?<!\d)((?:00|30|60|68|43|83|87|92)\d{4})(?!\d)")

MIN_NAME_LENGTH = 3
FULLWIDTH_MAP = str.maketrans({"Ａ": "A", "Ｂ": "B", "Ｃ": "C", "\u3000": " "})


def infer_sentiment(text: str) -> str:
    positive = sum(1 for keyword in POSITIVE_KEYWORDS if keyword in text)
    negative = sum(1 for keyword in NEGATIVE_KEYWORDS if keyword in text)
    if positive > negative:
        return "利好"
    if negative > positive:
        return "利空"
    return "中性"


def infer_event_type(text: str) -> str:
    for event_type, keywords in EVENT_PATTERNS.items():
        if any(keyword in text for keyword in keywords):
            return event_type
    return "其他"


@lru_cache(maxsize=1)
def stock_name_index() -> dict[str, str]:
    """载入代码 -> 简称字典，供新闻实体识别使用。

    文件缺失时返回空字典，实体识别退化为纯代码匹配，不影响主流程。
    """
    path = REFERENCE_DATA_DIR / "all_stock_codes.json"
    if not path.exists():
        logger.warning("未找到股票代码字典: %s，新闻实体识别将只匹配代码", path)
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("股票代码字典解析失败: %s", path, exc_info=True)
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(code): str(name).replace(" ", "").translate(FULLWIDTH_MAP) for code, name in payload.items()}


@lru_cache(maxsize=1)
def _name_to_code() -> dict[str, str]:
    return {name: code for code, name in stock_name_index().items()}


@lru_cache(maxsize=1)
def _matchable_names() -> frozenset[str]:
    return frozenset(name for name in stock_name_index().values() if len(name) >= MIN_NAME_LENGTH)


def find_stock_codes(text: str) -> list[str]:
    return list(dict.fromkeys(STOCK_CODE_PATTERN.findall(text)))


def find_stock_names(text: str) -> list[str]:
    """扫描文本中的上市公司简称。

    用滑动窗口 + 集合查询，避免为 5000+ 简称构建巨型正则。
    只接受长度 >= 3 的简称，2 字简称误报率过高。
    """
    names = _matchable_names()
    if not names or not text:
        return []
    max_len = max(len(name) for name in names)
    compact = text.translate(FULLWIDTH_MAP).replace(" ", "")
    found: list[str] = []
    i = 0
    while i < len(compact):
        matched = False
        for length in range(min(max_len, len(compact) - i), MIN_NAME_LENGTH - 1, -1):
            candidate = compact[i : i + length]
            if candidate in names:
                found.append(candidate)
                i += length
                matched = True
                break
        if not matched:
            i += 1
    return list(dict.fromkeys(found))


def code_for_name(name: str) -> str:
    return _name_to_code().get(name, "")


def link_article_entities(article: NewsArticle) -> NewsArticle:
    full_text = f"{article.title} {article.content}"
    explicit_codes = [
        str(code) for code in (article.metadata or {}).get("stock_codes", []) if str(code).isdigit()
    ]
    code_hits = find_stock_codes(full_text)
    name_hits = find_stock_names(full_text)

    index = stock_name_index()
    entities: dict[tuple[str, str], NewsEntity] = {}

    for code in explicit_codes:
        entities[("stock", code)] = NewsEntity(
            entity_type="stock",
            entity_code=code,
            entity_name=index.get(code, code),
            confidence=1.0,
        )
    for code in code_hits:
        entities.setdefault(
            ("stock", code),
            NewsEntity(entity_type="stock", entity_code=code, entity_name=index.get(code, code), confidence=0.9),
        )
    for name in name_hits:
        code = code_for_name(name)
        if not code:
            continue
        entities.setdefault(
            ("stock", code),
            NewsEntity(entity_type="stock", entity_code=code, entity_name=name, confidence=0.75),
        )

    article.entities = list(entities.values())
    article.links = [
        NewsLink(
            target_type="stock",
            target_code=entity.entity_code,
            target_name=entity.entity_name,
            link_reason=(
                "数据源标注"
                if entity.confidence >= 1.0
                else ("文本命中代码" if entity.confidence >= 0.9 else "文本命中简称")
            ),
        )
        for entity in article.entities
    ]
    article.sentiment = infer_sentiment(full_text)
    article.event_type = infer_event_type(full_text)
    return article
