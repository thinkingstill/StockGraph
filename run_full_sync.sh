#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export SYNC_MARKET_OVERVIEW="${SYNC_MARKET_OVERVIEW:-1}"
export SYNC_DRAGON_TIGER="${SYNC_DRAGON_TIGER:-1}"
export SYNC_NEWS="${SYNC_NEWS:-1}"
export BUILD_GRAPHS="${BUILD_GRAPHS:-1}"
export NEWS_LIMIT="${NEWS_LIMIT:-100}"
export NEWS_STOCK_LIMIT="${NEWS_STOCK_LIMIT:-5}"
export STOCKGRAPH_HOT_MAX_WORKERS="${STOCKGRAPH_HOT_MAX_WORKERS:-1}"
export STOCKGRAPH_HISTORY_MAX_WORKERS="${STOCKGRAPH_HISTORY_MAX_WORKERS:-2}"
export STOCKGRAPH_REQUEST_DELAY_SECONDS="${STOCKGRAPH_REQUEST_DELAY_SECONDS:-0.8}"

if [[ "${BUILD_YEARLY_MARKET:-0}" == "1" && -z "${MARKET_OVERVIEW_YEAR:-}" ]]; then
  export MARKET_OVERVIEW_YEAR="$(date +%Y)"
fi

echo "[stockgraph] full sync selected"
echo "[stockgraph] dragon tiger: $SYNC_DRAGON_TIGER"
echo "[stockgraph] market overview: $SYNC_MARKET_OVERVIEW"
echo "[stockgraph] news: $SYNC_NEWS, limit: $NEWS_LIMIT, per-stock limit: $NEWS_STOCK_LIMIT"
echo "[stockgraph] graph snapshots: $BUILD_GRAPHS"
echo "[stockgraph] akshare throttle: hot_workers=$STOCKGRAPH_HOT_MAX_WORKERS, history_workers=$STOCKGRAPH_HISTORY_MAX_WORKERS, delay=${STOCKGRAPH_REQUEST_DELAY_SECONDS}s"
if [[ -n "${MARKET_OVERVIEW_YEAR:-}" ]]; then
  echo "[stockgraph] yearly market rankings: $MARKET_OVERVIEW_YEAR"
else
  echo "[stockgraph] yearly market rankings: skipped"
fi

exec "$ROOT_DIR/run_daily_sync.sh"
