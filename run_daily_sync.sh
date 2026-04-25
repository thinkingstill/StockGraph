#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
DEFAULT_PYTHON_BIN="$VENV_DIR/bin/python"
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON_BIN}"
TARGET_DATE="${TARGET_DATE:-}"
SYNC_NEWS="${SYNC_NEWS:-0}"
BUILD_GRAPHS="${BUILD_GRAPHS:-0}"
SYNC_MARKET_OVERVIEW="${SYNC_MARKET_OVERVIEW:-1}"
MARKET_OVERVIEW_YEAR="${MARKET_OVERVIEW_YEAR:-}"

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

TASK_FAILURES=()
TASK_SUCCESSES=0

run_task() {
  local name="$1"
  shift
  echo "[stockgraph] running task: $name"
  if "$@"; then
    TASK_SUCCESSES=$((TASK_SUCCESSES + 1))
    return 0
  fi
  echo "[stockgraph] warning: task failed: $name" >&2
  TASK_FAILURES+=("$name")
  return 1
}

echo "[stockgraph] initializing database schema"
"$PYTHON_BIN" scripts/init_db.py

if [[ -n "$TARGET_DATE" ]]; then
  echo "[stockgraph] syncing dragon tiger for date: $TARGET_DATE"
  run_task "sync_dragon_tiger" "$PYTHON_BIN" scripts/sync_dragon_tiger.py --date "$TARGET_DATE" || true
else
  echo "[stockgraph] syncing dragon tiger for previous trading date"
  run_task "sync_dragon_tiger" "$PYTHON_BIN" scripts/sync_dragon_tiger.py || true
fi

echo "[stockgraph] regenerating dashboards"
run_task "generate_dashboards" "$PYTHON_BIN" scripts/generate_dashboards.py || true

if [[ "$SYNC_NEWS" == "1" ]]; then
  echo "[stockgraph] syncing news"
  run_task "sync_news" "$PYTHON_BIN" scripts/sync_news.py --limit "${NEWS_LIMIT:-50}" || true
fi

if [[ "$BUILD_GRAPHS" == "1" ]]; then
  echo "[stockgraph] building graph snapshots"
  run_task "build_graph_snapshots" "$PYTHON_BIN" scripts/build_graph_snapshots.py --persist || true
fi

if [[ "$SYNC_MARKET_OVERVIEW" == "1" ]]; then
  echo "[stockgraph] syncing market overview"
  if [[ -n "$TARGET_DATE" ]]; then
    if [[ -n "$MARKET_OVERVIEW_YEAR" ]]; then
      run_task "sync_market_overview" "$PYTHON_BIN" scripts/sync_market_overview.py --date "$TARGET_DATE" --year "$MARKET_OVERVIEW_YEAR" || true
    else
      run_task "sync_market_overview" "$PYTHON_BIN" scripts/sync_market_overview.py --date "$TARGET_DATE" || true
    fi
  else
    if [[ -n "$MARKET_OVERVIEW_YEAR" ]]; then
      run_task "sync_market_overview" "$PYTHON_BIN" scripts/sync_market_overview.py --year "$MARKET_OVERVIEW_YEAR" || true
    else
      run_task "sync_market_overview" "$PYTHON_BIN" scripts/sync_market_overview.py || true
    fi
  fi
fi

run_task "build_unified_app" "$PYTHON_BIN" scripts/build_unified_app.py || true
run_task "build_dev_index" "$PYTHON_BIN" scripts/build_dev_index.py || true

if [[ "${#TASK_FAILURES[@]}" -gt 0 ]]; then
  echo "[stockgraph] completed with warnings. failed tasks: ${TASK_FAILURES[*]}" >&2
else
  echo "[stockgraph] all selected tasks completed successfully"
fi

if [[ "$TASK_SUCCESSES" -eq 0 ]]; then
  echo "[stockgraph] error: no selected task completed successfully" >&2
  exit 1
fi

echo "[stockgraph] daily sync completed"
