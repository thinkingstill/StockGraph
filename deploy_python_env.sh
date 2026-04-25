#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_SMOKE_TEST="${RUN_SMOKE_TEST:-1}"

echo "[stockgraph] root: $ROOT_DIR"
echo "[stockgraph] venv: $VENV_DIR"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[stockgraph] error: python not found: $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e "$ROOT_DIR"

python scripts/init_db.py

if [[ "$RUN_SMOKE_TEST" == "1" ]]; then
  python -m compileall "$ROOT_DIR/src" >/dev/null
fi

echo "[stockgraph] environment ready"
echo "[stockgraph] activate with: source $VENV_DIR/bin/activate"
