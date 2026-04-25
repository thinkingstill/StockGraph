SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    listing_reason TEXT,
    total_buy REAL,
    total_sell REAL,
    net_amount REAL,
    buy_seat_count INTEGER,
    sell_seat_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, stock_code)
);

CREATE TABLE IF NOT EXISTS stock_seat_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    seat_name TEXT NOT NULL,
    direction TEXT NOT NULL,
    amount REAL NOT NULL,
    net_amount REAL,
    seat_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trader_alias TEXT,
    UNIQUE(date, stock_code, seat_name, direction)
);

CREATE TABLE IF NOT EXISTS seat_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seat_name TEXT NOT NULL UNIQUE,
    seat_code TEXT,
    seat_type TEXT NOT NULL,
    characteristics TEXT,
    first_seen_date TEXT,
    last_seen_date TEXT,
    total_operations INTEGER DEFAULT 0,
    total_amount REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hot_money_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_name TEXT NOT NULL UNIQUE,
    tag_type TEXT NOT NULL CHECK(tag_type IN ('代号', '操作手法')),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS seat_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seat_name TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tag_id) REFERENCES hot_money_tags(id),
    UNIQUE(seat_name, tag_id)
);

CREATE TABLE IF NOT EXISTS dragon_tiger_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT,
    stock_code TEXT,
    stock_name TEXT,
    close_price REAL,
    change_pct REAL,
    turnover_rate REAL,
    amount REAL,
    reason TEXT,
    net_amount REAL,
    seat_count INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS dragon_tiger_detail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT,
    stock_code TEXT,
    stock_name TEXT,
    seat_name TEXT,
    seat_type TEXT,
    buy_amount REAL,
    sell_amount REAL,
    net_amount REAL,
    trader_alias TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS dragon_tiger_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT,
    code TEXT,
    name TEXT,
    reason TEXT,
    close_price REAL,
    change_pct REAL,
    volume REAL,
    amount REAL,
    buy_amount REAL,
    sell_amount REAL,
    net_amount REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dragon_tiger_seat_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT,
    code TEXT,
    name TEXT,
    seat_name TEXT,
    direction TEXT,
    amount REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, code, seat_name, direction)
);

CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    summary TEXT,
    published_at TEXT,
    url TEXT,
    hash TEXT NOT NULL UNIQUE,
    sentiment TEXT,
    event_type TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS news_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    entity_code TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES news_articles(id),
    UNIQUE(article_id, entity_type, entity_code, entity_name)
);

CREATE TABLE IF NOT EXISTS news_article_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    target_code TEXT NOT NULL,
    target_name TEXT NOT NULL,
    link_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES news_articles(id),
    UNIQUE(article_id, target_type, target_code, target_name, link_reason)
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL UNIQUE,
    node_type TEXT NOT NULL,
    node_key TEXT NOT NULL,
    node_name TEXT NOT NULL,
    attributes_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL DEFAULT 0,
    trade_date TEXT,
    snapshot_type TEXT,
    attributes_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS graph_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    snapshot_type TEXT NOT NULL,
    version TEXT DEFAULT 'v1',
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date, snapshot_type, version)
);

CREATE TABLE IF NOT EXISTS market_daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    latest_price REAL,
    change_pct REAL,
    industry TEXT,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, stock_code)
);

CREATE TABLE IF NOT EXISTS market_hot_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    latest_price REAL,
    follow_rank REAL,
    tweet_rank REAL,
    deal_rank REAL,
    change_pct REAL,
    industry TEXT,
    raw_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, stock_code)
);

CREATE TABLE IF NOT EXISTS market_industry_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    industry TEXT NOT NULL,
    direction TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(trade_date, industry, direction)
);

CREATE INDEX IF NOT EXISTS idx_daily_summaries_date ON daily_summaries(date);
CREATE INDEX IF NOT EXISTS idx_daily_summaries_stock_code ON daily_summaries(stock_code);
CREATE INDEX IF NOT EXISTS idx_graph_edges_source_target ON graph_edges(source_node_id, target_node_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_snapshot_type ON graph_edges(snapshot_type, trade_date);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_type_key ON graph_nodes(node_type, node_key);
CREATE INDEX IF NOT EXISTS idx_market_daily_trade_date ON market_daily_snapshots(trade_date);
CREATE INDEX IF NOT EXISTS idx_market_hot_trade_date ON market_hot_rankings(trade_date);
CREATE INDEX IF NOT EXISTS idx_market_industry_trade_date ON market_industry_rankings(trade_date);
CREATE INDEX IF NOT EXISTS idx_news_articles_published_at ON news_articles(published_at);
CREATE INDEX IF NOT EXISTS idx_news_articles_source ON news_articles(source);
CREATE INDEX IF NOT EXISTS idx_news_entities_article_id ON news_entities(article_id);
CREATE INDEX IF NOT EXISTS idx_news_entities_type_code ON news_entities(entity_type, entity_code);
CREATE INDEX IF NOT EXISTS idx_news_links_article_id ON news_article_links(article_id);
CREATE INDEX IF NOT EXISTS idx_seat_details_seat_type ON seat_details(seat_type);
CREATE INDEX IF NOT EXISTS idx_seat_tags_seat_name ON seat_tags(seat_name);
CREATE INDEX IF NOT EXISTS idx_seat_tags_tag_id ON seat_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_stock_seat_operations_date_stock ON stock_seat_operations(date, stock_code);
CREATE INDEX IF NOT EXISTS idx_stock_seat_operations_seat ON stock_seat_operations(seat_name);
CREATE INDEX IF NOT EXISTS idx_stock_seat_operations_stock_seat ON stock_seat_operations(stock_code, seat_name);
"""
