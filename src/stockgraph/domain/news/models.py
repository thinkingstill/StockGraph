from dataclasses import dataclass, field


@dataclass(slots=True)
class NewsEntity:
    entity_type: str
    entity_code: str
    entity_name: str
    confidence: float = 1.0


@dataclass(slots=True)
class NewsLink:
    target_type: str
    target_code: str
    target_name: str
    link_reason: str


@dataclass(slots=True)
class NewsArticle:
    source: str
    title: str
    content: str
    published_at: str
    url: str
    article_hash: str = ""
    sentiment: str = "中性"
    event_type: str = "其他"
    summary: str = ""
    entities: list[NewsEntity] = field(default_factory=list)
    links: list[NewsLink] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class NewsBatch:
    source: str
    articles: list[NewsArticle] = field(default_factory=list)
