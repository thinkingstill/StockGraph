"""只重建前端的「轻量模块」，跳过耗时的全 A 超图与城市气泡。

`UnifiedFrontendService.generate()` 把这些模块写在一个字典字面量里顺序求值，
任何一个超时都会让整条链路中断 —— 实测 203 个交易日的全 A 超图（每天 5500 只股票）
需要十几分钟，期间新闻模块根本来不及刷新。

这个脚本用于「数据已更新，只想让新闻/AI 分析 tab 立刻可用」的场景：
    python scripts/rebuild_frontend_sections.py
    python scripts/rebuild_frontend_sections.py --sections stock_news ai_analysis
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.application.services.unified_frontend import UnifiedFrontendService  # noqa: E402
from stockgraph.core import configure_logging  # noqa: E402
from stockgraph.core.paths import APP_DATA_DIR, APP_OUTPUT_DIR  # noqa: E402
from stockgraph.presentation.templates.unified_app import render_unified_app  # noqa: E402

# 模块名 -> 构建方法
BUILDERS = {
    "dragon_query": "_build_dragon_query_data",
    "dragon_graph": "_build_dragon_graph_data",
    "market_hot": "_build_market_hot_data",
    "market_calendar": "_build_market_calendar_data",
    "market_industry": "_build_market_industry_data",
    "stock_super_graph": "_build_stock_super_graph_data",
    "china_city_bubble": "_build_china_city_bubble_data",
    "stock_news": "_build_stock_news_data",
    "ai_analysis": "_build_ai_analysis_data",
}

DEFAULT_SECTIONS = ["stock_news", "ai_analysis"]


def main() -> int:
    parser = argparse.ArgumentParser(description="按模块重建前端产物")
    parser.add_argument(
        "--sections",
        nargs="+",
        choices=sorted(BUILDERS),
        default=DEFAULT_SECTIONS,
        help="要重建的模块（默认只重建新闻与 AI 分析）",
    )
    parser.add_argument("--render-html", action="store_true", default=True, help="同时重新渲染 index.html")
    args = parser.parse_args()

    configure_logging()
    service = UnifiedFrontendService()
    service.dragon_tiger_repository.initialize_database()
    service.news_repository.initialize_database()

    manifest_path = APP_DATA_DIR / "app_manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            manifest = {}
    sections = manifest.setdefault("sections", {})

    for name in args.sections:
        method = getattr(service, BUILDERS[name], None)
        if method is None:
            print(f"跳过 {name}：方法 {BUILDERS[name]} 不存在", file=sys.stderr)
            continue
        result = method()
        sections[name] = result
        print(f"{name}: available={result.get('available')} path={result.get('path')}")

    manifest["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "stock_names" not in manifest:
        manifest["stock_names"] = service._build_stock_names()  # noqa: SLF001
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, default=str), encoding="utf-8")

    if args.render_html:
        (APP_OUTPUT_DIR / "index.html").write_text(render_unified_app(), encoding="utf-8")

    print(f"已更新 {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
