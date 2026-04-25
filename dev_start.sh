#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="$VENV_DIR/bin/python"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8030}"
SYNC_MARKET_OVERVIEW="${SYNC_MARKET_OVERVIEW:-1}"
SYNC_DRAGON_TIGER="${SYNC_DRAGON_TIGER:-0}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[stockgraph] error: virtualenv python not found at $PYTHON_BIN" >&2
  echo "[stockgraph] run ./deploy_python_env.sh first" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "[stockgraph] initializing database schema"
"$PYTHON_BIN" scripts/init_db.py

if [[ "$SYNC_DRAGON_TIGER" == "1" ]]; then
  echo "[stockgraph] syncing dragon tiger"
  "$PYTHON_BIN" scripts/sync_dragon_tiger.py || echo "[stockgraph] warning: dragon tiger sync failed, keep existing pages"
fi

echo "[stockgraph] generating dragon tiger dashboards"
"$PYTHON_BIN" scripts/generate_dashboards.py || true

if [[ "$SYNC_MARKET_OVERVIEW" == "1" ]]; then
  echo "[stockgraph] syncing market overview"
  "$PYTHON_BIN" scripts/sync_market_overview.py || echo "[stockgraph] warning: market overview sync failed, use existing cached pages if available"
fi

echo "[stockgraph] building unified app"
"$PYTHON_BIN" scripts/build_unified_app.py || true

echo "[stockgraph] building dev index"
"$PYTHON_BIN" scripts/build_dev_index.py

echo "[stockgraph] serving outputs at http://$HOST:$PORT/app/index.html"
cd "$ROOT_DIR/outputs"
exec "$PYTHON_BIN" -m http.server "$PORT" --bind "$HOST"
