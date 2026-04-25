from dataclasses import dataclass, field


@dataclass(slots=True)
class SeatOperation:
    seat_name: str
    direction: str
    amount: float
    seat_type: str | None = None
    trader_alias: str | None = None


@dataclass(slots=True)
class DailySummary:
    stock_code: str
    stock_name: str
    listing_reason: str = ""
    total_buy: float = 0.0
    total_sell: float = 0.0
    net_amount: float = 0.0
    buy_seat_count: int = 0
    sell_seat_count: int = 0
    seat_operations: list[SeatOperation] = field(default_factory=list)


@dataclass(slots=True)
class DragonTigerBatch:
    trade_date: str
    stocks: list[DailySummary] = field(default_factory=list)
