from __future__ import annotations

import hashlib
import re

from stockgraph.domain.news.models import NewsArticle


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_url(url: str) -> str:
    normalized = (url or "").strip()
    return normalized.split("#", 1)[0]


def build_dedup_hash(title: str, content: str) -> str:
    payload = f"{normalize_text(title)}|{normalize_text(content)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_news_article(article: NewsArticle) -> NewsArticle:
    article.title = normalize_text(article.title)
    article.content = normalize_text(article.content)
    article.summary = normalize_text(article.summary)
    article.url = normalize_url(article.url)
    article.article_hash = article.article_hash or build_dedup_hash(article.title, article.content)
    return article
