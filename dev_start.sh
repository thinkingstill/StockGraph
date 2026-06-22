#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
DEFAULT_PYTHON_BIN="$VENV_DIR/bin/python"
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON_BIN}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8030}"
SYNC_MARKET_OVERVIEW="${SYNC_MARKET_OVERVIEW:-0}"
SYNC_DRAGON_TIGER="${SYNC_DRAGON_TIGER:-0}"
BACKFILL_FROM_JSON="${BACKFILL_FROM_JSON:-auto}"
BACKFILL_AREAS="${BACKFILL_AREAS:-all}"
DB_PATH="$ROOT_DIR/data/shared_state/dragon_tiger.db"

if [[ "$PYTHON_BIN" == */* ]]; then
  RESOLVED_PYTHON_BIN="$PYTHON_BIN"
else
  RESOLVED_PYTHON_BIN="$(command -v "$PYTHON_BIN" || true)"
fi

if [[ -z "$RESOLVED_PYTHON_BIN" || ! -x "$RESOLVED_PYTHON_BIN" ]]; then
  echo "[stockgraph] error: virtualenv python not found at $PYTHON_BIN" >&2
  echo "[stockgraph] run ./deploy_python_env.sh first, or set PYTHON_BIN to a valid python executable" >&2
  exit 1
fi

PYTHON_BIN="$RESOLVED_PYTHON_BIN"

cd "$ROOT_DIR"

BOOTSTRAP_FROM_JSON=0
if [[ "$BACKFILL_FROM_JSON" == "1" ]]; then
  BOOTSTRAP_FROM_JSON=1
elif [[ "$BACKFILL_FROM_JSON" == "auto" && ! -s "$DB_PATH" ]]; then
  BOOTSTRAP_FROM_JSON=1
fi

echo "[stockgraph] initializing database schema"
"$PYTHON_BIN" scripts/init_db.py

if [[ "$BOOTSTRAP_FROM_JSON" == "1" ]]; then
  echo "[stockgraph] backfilling local database from existing JSON outputs"
  "$PYTHON_BIN" scripts/backfill_from_json.py --areas "$BACKFILL_AREAS" || echo "[stockgraph] warning: JSON backfill failed, continue with existing data"
fi

if [[ "$SYNC_DRAGON_TIGER" == "1" ]]; then
  echo "[stockgraph] syncing dragon tiger"
  "$PYTHON_BIN" scripts/sync_dragon_tiger.py || echo "[stockgraph] warning: dragon tiger sync failed, keep existing pages"
else
  echo "[stockgraph] skipping dragon tiger sync; reusing existing JSON/database data"
fi

echo "[stockgraph] generating dragon tiger dashboards"
"$PYTHON_BIN" scripts/generate_dashboards.py || true

if [[ "$SYNC_MARKET_OVERVIEW" == "1" ]]; then
  echo "[stockgraph] syncing market overview"
  "$PYTHON_BIN" scripts/sync_market_overview.py || echo "[stockgraph] warning: market overview sync failed, use existing cached pages if available"
else
  echo "[stockgraph] skipping market overview sync; reusing data/market_overview JSON"
fi

echo "[stockgraph] building unified app"
"$PYTHON_BIN" scripts/build_unified_app.py || true

echo "[stockgraph] building dev index"
"$PYTHON_BIN" scripts/build_dev_index.py

echo "[stockgraph] starting API server at http://$HOST:$PORT/app/index.html"
exec "$PYTHON_BIN" scripts/api_server.py --host "$HOST" --port "$PORT"
