#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core.paths import OUTPUT_DIR, ensure_runtime_dirs


def write_app_redirect() -> None:
    (OUTPUT_DIR / "index.html").write_text(
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="0; url=app/index.html">
  <title>StockGraph</title>
  <script>window.location.replace('app/index.html');</script>
</head>
<body>
  <p><a href="app/index.html">进入 StockGraph 应用</a></p>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> int:
    ensure_runtime_dirs()

    from build_dev_index import main as build_dev_index_main

    build_dev_index_main()
    write_app_redirect()
    (OUTPUT_DIR / ".nojekyll").touch()
    app_dir = OUTPUT_DIR / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / ".nojekyll").touch()
    print(app_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
