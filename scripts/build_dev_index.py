#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core import PROJECT_ROOT, ensure_runtime_dirs


def main() -> int:
    ensure_runtime_dirs()
    output = PROJECT_ROOT / "outputs" / "index.html"
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="0; url=app/index.html">
  <title>StockGraph</title>
  <script>window.location.replace('app/index.html');</script>
  <style>
    :root {
      --bg: #f3f4ef;
      --text: #182028;
      --muted: #5f6b76;
      --accent: #14532d;
      --line: #d9e2d8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: linear-gradient(180deg, #f8faf7 0%, var(--bg) 100%);
    }
    .box {
      width: min(520px, 100%);
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 12px 30px rgba(24, 32, 40, 0.06);
    }
    h1 {
      margin: 0 0 8px;
      font-size: 22px;
    }
    p {
      margin: 0 0 16px;
      color: var(--muted);
      line-height: 1.6;
    }
    a {
      display: inline-block;
      color: #fff;
      background: var(--accent);
      text-decoration: none;
      font-weight: 600;
      border-radius: 6px;
      padding: 10px 14px;
    }
  </style>
</head>
<body>
  <div class="box">
    <h1>正在进入 StockGraph 应用</h1>
    <p>如果浏览器没有自动跳转，请点击下方按钮。</p>
    <a href="app/index.html">进入应用</a>
  </div>
</body>
</html>"""

    output.write_text(html, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
