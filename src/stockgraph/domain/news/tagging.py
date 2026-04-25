from __future__ import annotations

import re

from stockgraph.domain.news.models import NewsArticle, NewsEntity, NewsLink

POSITIVE_KEYWORDS = ("涨停", "中标", "业绩增长", "回购", "增持", "突破", "签约")
NEGATIVE_KEYWORDS = ("跌停", "减持", "处罚", "问询", "亏损", "终止", "下修")
EVENT_PATTERNS = {
    "业绩": ("业绩", "预增", "预亏", "快报", "财报"),
    "并购重组": ("收购", "重组", "并购", "股权转让"),
    "监管": ("问询", "处罚", "立案", "监管"),
    "投融资": ("定增", "融资", "回购", "增持", "减持"),
    "产业政策": ("政策", "规划", "指引", "试点"),
}
STOCK_CODE_PATTERN = re.compile(r"\b(00\d{4}|30\d{4}|60\d{4}|68\d{4})\b")


def infer_sentiment(text: str) -> str:
    if any(keyword in text for keyword in POSITIVE_KEYWORDS):
        return "利好"
    if any(keyword in text for keyword in NEGATIVE_KEYWORDS):
        return "利空"
    return "中性"


def infer_event_type(text: str) -> str:
    for event_type, keywords in EVENT_PATTERNS.items():
        if any(keyword in text for keyword in keywords):
            return event_type
    return "其他"


def link_article_entities(article: NewsArticle) -> NewsArticle:
    full_text = f"{article.title} {article.content}"
    found_codes = list(dict.fromkeys(STOCK_CODE_PATTERN.findall(full_text)))
    article.entities = [
        NewsEntity(entity_type="stock", entity_code=code, entity_name=code, confidence=0.9)
        for code in found_codes
    ]
    article.links = [
        NewsLink(target_type="stock", target_code=code, target_name=code, link_reason="文本命中股票代码")
        for code in found_codes
    ]
    article.sentiment = infer_sentiment(full_text)
    article.event_type = infer_event_type(full_text)
    return article
