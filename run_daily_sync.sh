#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
DEFAULT_PYTHON_BIN="$VENV_DIR/bin/python"
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON_BIN}"
TARGET_DATE="${TARGET_DATE:-}"
SYNC_NEWS="${SYNC_NEWS:-0}"
BUILD_GRAPHS="${BUILD_GRAPHS:-0}"
SYNC_STOCK_LOCATIONS="${SYNC_STOCK_LOCATIONS:-0}"
SYNC_MARKET_OVERVIEW="${SYNC_MARKET_OVERVIEW:-1}"
SYNC_DRAGON_TIGER="${SYNC_DRAGON_TIGER:-1}"
MARKET_OVERVIEW_YEAR="${MARKET_OVERVIEW_YEAR:-}"
ANALYZE_DRAGON_TIGER="${ANALYZE_DRAGON_TIGER:-0}"
DRAGON_TIGER_ANALYSIS_START_DATE="${DRAGON_TIGER_ANALYSIS_START_DATE:-$TARGET_DATE}"
DRAGON_TIGER_ANALYSIS_END_DATE="${DRAGON_TIGER_ANALYSIS_END_DATE:-$TARGET_DATE}"

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

if [[ "$SYNC_DRAGON_TIGER" == "1" ]]; then
  if [[ -n "$TARGET_DATE" ]]; then
    echo "[stockgraph] syncing dragon tiger for date: $TARGET_DATE"
    run_task "sync_dragon_tiger" "$PYTHON_BIN" scripts/sync_dragon_tiger.py --date "$TARGET_DATE" || true
  else
    echo "[stockgraph] syncing dragon tiger for previous trading date"
    run_task "sync_dragon_tiger" "$PYTHON_BIN" scripts/sync_dragon_tiger.py || true
  fi
else
  echo "[stockgraph] skipping dragon tiger sync"
fi

echo "[stockgraph] regenerating dashboards"
run_task "generate_dashboards" "$PYTHON_BIN" scripts/generate_dashboards.py || true

if [[ "$ANALYZE_DRAGON_TIGER" == "1" ]]; then
  echo "[stockgraph] exporting dragon tiger analysis"
  ANALYSIS_ARGS=()
  if [[ -n "$DRAGON_TIGER_ANALYSIS_START_DATE" ]]; then
    ANALYSIS_ARGS+=(--start-date "$DRAGON_TIGER_ANALYSIS_START_DATE")
  fi
  if [[ -n "$DRAGON_TIGER_ANALYSIS_END_DATE" ]]; then
    ANALYSIS_ARGS+=(--end-date "$DRAGON_TIGER_ANALYSIS_END_DATE")
  fi
  if [[ "${DRAGON_TIGER_ANALYSIS_PERSIST_GRAPHS:-0}" == "1" ]]; then
    ANALYSIS_ARGS+=(--persist-graphs)
  fi
  run_task "analyze_dragon_tiger" "$PYTHON_BIN" scripts/analyze_dragon_tiger.py "${ANALYSIS_ARGS[@]}" || true
fi

if [[ "$SYNC_NEWS" == "1" ]]; then
  echo "[stockgraph] syncing news"
  NEWS_ARGS=(--limit "${NEWS_LIMIT:-50}" --stock-limit "${NEWS_STOCK_LIMIT:-5}")
  if [[ -n "${NEWS_STOCK_CODES:-}" ]]; then
    NEWS_ARGS+=(--stock-codes "$NEWS_STOCK_CODES")
  fi
  if [[ "${SKIP_STOCK_NEWS:-0}" == "1" ]]; then
    NEWS_ARGS+=(--skip-stock-news)
  fi
  run_task "sync_news" "$PYTHON_BIN" scripts/sync_news.py "${NEWS_ARGS[@]}" || true
fi

if [[ "$BUILD_GRAPHS" == "1" ]]; then
  echo "[stockgraph] building graph snapshots"
  run_task "build_graph_snapshots" "$PYTHON_BIN" scripts/build_graph_snapshots.py --persist || true
fi

if [[ "$SYNC_STOCK_LOCATIONS" == "1" ]]; then
  echo "[stockgraph] syncing stock locations"
  LOCATION_ARGS=(--limit "${STOCK_LOCATION_LIMIT:-100}" --sleep "${STOCK_LOCATION_SLEEP:-1.2}")
  if [[ -n "${STOCK_LOCATION_CODES:-}" ]]; then
    LOCATION_ARGS+=(--codes "$STOCK_LOCATION_CODES")
  fi
  if [[ "${STOCK_LOCATION_FORCE:-0}" == "1" ]]; then
    LOCATION_ARGS+=(--force)
  fi
  run_task "sync_stock_locations" "$PYTHON_BIN" scripts/sync_stock_locations.py "${LOCATION_ARGS[@]}" || true
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
