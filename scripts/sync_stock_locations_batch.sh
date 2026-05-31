#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    PYTHON_BIN="$VENV_DIR/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
fi

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "[stockgraph] error: python executable not found. Set PYTHON_BIN or create .venv first." >&2
  exit 1
fi

cd "$ROOT_DIR"

STOCK_LOCATION_LIMIT="${STOCK_LOCATION_LIMIT:-300}"
STOCK_LOCATION_SLEEP="${STOCK_LOCATION_SLEEP:-1.5}"
STOCK_LOCATION_ROUNDS="${STOCK_LOCATION_ROUNDS:-1}"
STOCK_LOCATION_CODES="${STOCK_LOCATION_CODES:-}"
STOCK_LOCATION_FORCE="${STOCK_LOCATION_FORCE:-0}"
STOCK_LOCATION_REBUILD_ONLY="${STOCK_LOCATION_REBUILD_ONLY:-0}"
BUILD_APP_AFTER="${BUILD_APP_AFTER:-0}"

print_status() {
  PYTHONPATH="$ROOT_DIR/src" "$PYTHON_BIN" - <<'PY'
from pathlib import Path
import json

import pandas as pd

root = Path.cwd()
mapping_path = root / "data/reference/stock_location_mapping.json"
basic_path = root / "data/reference/stock_basic_info.pkl"

mapping = {}
if mapping_path.exists():
    payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    mapping = payload if isinstance(payload, dict) else {}

total = 0
if basic_path.exists():
    basic = pd.read_pickle(basic_path)
    total = len(basic)

coverage = (len(mapping) / total * 100) if total else 0
print(f"[stockgraph] stock location coverage: {len(mapping)}/{total} ({coverage:.2f}%)")
PY
}

echo "[stockgraph] syncing stock locations"
echo "[stockgraph] python: $PYTHON_BIN"
echo "[stockgraph] limit=$STOCK_LOCATION_LIMIT sleep=$STOCK_LOCATION_SLEEP rounds=$STOCK_LOCATION_ROUNDS"
print_status

for round in $(seq 1 "$STOCK_LOCATION_ROUNDS"); do
  echo "[stockgraph] location sync round $round/$STOCK_LOCATION_ROUNDS"
  args=(scripts/sync_stock_locations.py --limit "$STOCK_LOCATION_LIMIT" --sleep "$STOCK_LOCATION_SLEEP")

  if [[ -n "$STOCK_LOCATION_CODES" ]]; then
    args+=(--codes "$STOCK_LOCATION_CODES")
  fi
  if [[ "$STOCK_LOCATION_FORCE" == "1" ]]; then
    args+=(--force)
  fi
  if [[ "$STOCK_LOCATION_REBUILD_ONLY" == "1" ]]; then
    args+=(--rebuild-only)
  fi

  PYTHONPATH="$ROOT_DIR/src" "$PYTHON_BIN" "${args[@]}"
  print_status
done

if [[ "$BUILD_APP_AFTER" == "1" ]]; then
  echo "[stockgraph] rebuilding unified app after stock location sync"
  PYTHONPATH="$ROOT_DIR/src" "$PYTHON_BIN" -m stockgraph.cli.build_unified_app
fi

echo "[stockgraph] stock location sync completed"
