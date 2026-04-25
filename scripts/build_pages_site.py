#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core import OUTPUT_DIR, ensure_runtime_dirs


def main() -> int:
    ensure_runtime_dirs()

    from build_dev_index import main as build_dev_index_main

    build_dev_index_main()
    (OUTPUT_DIR / ".nojekyll").touch()
    print(OUTPUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())