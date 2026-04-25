#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core import MARKET_OUTPUT_DIR, OUTPUT_HTML_DIR, PROJECT_ROOT, ensure_runtime_dirs


def main() -> int:
    ensure_runtime_dirs()
    output = PROJECT_ROOT / "outputs" / "index.html"

    pages = [
        ("统一入口（龙虎榜 / 热度图 / 行业日历）", "app/index.html"),
        ("龙虎榜查询", "html/龙虎榜查询.html"),
        ("龙虎榜综合分析", "html/龙虎榜综合分析.html"),
    ]

    market_pages = sorted(MARKET_OUTPUT_DIR.glob("*.html"), reverse=True)
    if market_pages:
        latest = market_pages[0]
        pages.append((f"市场热度 3D 可视化 ({latest.stem})", f"market/{latest.name}"))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>StockGraph Dev</title>
  <style>
    :root {{
      --bg: #f3f4ef;
      --card: #ffffff;
      --text: #182028;
      --muted: #5f6b76;
      --accent: #14532d;
      --accent-soft: #d1fae5;
      --border: #d9e2d8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 40px 20px;
      font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(20, 83, 45, 0.10), transparent 28%),
        linear-gradient(180deg, #f8faf7 0%, var(--bg) 100%);
    }}
    .wrap {{
      max-width: 960px;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 34px;
    }}
    p {{
      margin: 0 0 28px;
      color: var(--muted);
      line-height: 1.6;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
    .card {{
      display: block;
      text-decoration: none;
      color: inherit;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 12px 30px rgba(24, 32, 40, 0.06);
      transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
    }}
    .card:hover {{
      transform: translateY(-2px);
      border-color: #86efac;
      box-shadow: 0 18px 40px rgba(20, 83, 45, 0.12);
    }}
    .badge {{
      display: inline-block;
      margin-bottom: 12px;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 600;
    }}
    .title {{
      font-size: 20px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .path {{
      font-size: 13px;
      color: var(--muted);
      word-break: break-all;
    }}
    .footer {{
      margin-top: 28px;
      font-size: 13px;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>StockGraph 页面入口</h1>
    <p>本页聚合当前可直接访问的页面，可同时用于本地预览和 GitHub Pages 发布后的统一入口。</p>
    <div class="grid">
      {"".join(f'<a class="card" href="{href}" target="_blank" rel="noreferrer"><div class="badge">Page</div><div class="title">{title}</div><div class="path">{href}</div></a>' for title, href in pages)}
    </div>
    <div class="footer">页面根目录: {output.parent}</div>
  </div>
</body>
</html>"""

    output.write_text(html, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
