from dataclasses import dataclass, field


@dataclass(slots=True)
class MarketDailySnapshot:
    trade_date: str
    records: list[dict] = field(default_factory=list)


@dataclass(slots=True)
class StockHotRecord:
    trade_date: str
    stock_code: str
    stock_name: str
    latest_price: float | None = None
    follow_rank: float | None = None
    tweet_rank: float | None = None
    deal_rank: float | None = None
    change_pct: float | None = None
    industry: str = "未知"


@dataclass(slots=True)
class IndustryRanking:
    trade_date: str
    industry: str
    direction: str


@dataclass(slots=True)
class MarketOverviewBundle:
    trade_date: str
    daily_snapshot: MarketDailySnapshot
    hot_records: list[StockHotRecord] = field(default_factory=list)
    top_industries: list[IndustryRanking] = field(default_factory=list)
    bottom_industries: list[IndustryRanking] = field(default_factory=list)
