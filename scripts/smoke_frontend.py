#!/usr/bin/env python3
"""统一前端浏览器冒烟测试。

为什么需要这个脚本：JSON 产物存在、字段齐全，并不代表前端跑得起来。
本轮就踩过两次——
  1. 行业强弱图表把"涨跌幅累加和"当涨幅，横轴跑到 -1000，数字荒唐但文件完全合法；
  2. echarts-gl 在无 WebGL 环境下抛异常，整个 3D 模块变空白，控制台才有动静。
这两类问题只有真的把页面跑起来才看得见，所以固化成脚本。

用法：
    python scripts/smoke_frontend.py                    # 起临时静态服务，跑全部模块
    python scripts/smoke_frontend.py --base-url http://localhost:8080
    python scripts/smoke_frontend.py --json             # 机器可读输出，供 CI 使用

依赖 playwright（`pip install playwright && playwright install chromium`）。
未安装时脚本打印跳过原因并以退出码 0 结束，避免在没装浏览器的环境里阻断流水线。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import http.server
import json
import socket
import socketserver
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "outputs" / "app"

# 每个模块：工作区 -> tab -> 断言
# - expect_canvas: 面板内必须有非零尺寸的 canvas
# - forbid_text: 面板内不得出现的文字（加载失败 / 数据不可用等）
MODULES: list[dict] = [
    {"workspace": "dragon", "tab": "dragon_query", "name": "龙虎榜明细", "expect_canvas": False},
    {"workspace": "dragon", "tab": "dragon_graph", "name": "龙虎榜关系网", "expect_canvas": True},
    {"workspace": "market", "tab": "market_hot", "name": "市场热度", "expect_canvas": True},
    {"workspace": "market", "tab": "stock_super_graph", "name": "全 A 图谱", "expect_canvas": True},
    {"workspace": "market", "tab": "china_city_bubble", "name": "城市气泡", "expect_canvas": True},
    {"workspace": "industry", "tab": "market_industry", "name": "行业强弱", "expect_canvas": True},
    {"workspace": "industry", "tab": "market_calendar", "name": "行业日历", "expect_canvas": False},
    {"workspace": "stock", "tab": "smart_analysis", "name": "智能分析", "expect_canvas": False},
]

FORBIDDEN = ("加载失败", "数据当前不可用", "无可用数据", "undefined", "NaN")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """只读静态文件服务，静默访问日志；directory 由 closure 注入。"""

    def __init__(self, *args, directory: str = ".", **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, *args):  # noqa: D401 - 静默访问日志
        pass


@contextlib.contextmanager
def serve(directory: Path):
    """起一个临时静态服务并返回 base_url。"""
    root = str(directory)

    def handler(*args, **kwargs):
        return _QuietHandler(*args, directory=root, **kwargs)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


async def _probe(base_url: str, wait_ms: int) -> list[dict]:
    from playwright.async_api import async_playwright

    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 1000})
        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        resp = await page.goto(f"{base_url}/index.html", wait_until="networkidle", timeout=120_000)
        if resp is None or resp.status != 200:
            await browser.close()
            return [{"name": "index.html", "ok": False, "reason": "index.html 无法加载"}]

        webgl = await page.evaluate(
            """() => { const c=document.createElement('canvas');
                 return !!(c.getContext('webgl2')||c.getContext('webgl')||c.getContext('experimental-webgl')); }"""
        )

        for mod in MODULES:
            page_errors.clear()
            entry: dict = {"name": mod["name"], "tab": mod["tab"], "ok": True, "notes": []}
            try:
                await page.click(f'button[data-workspace="{mod["workspace"]}"]')
                await page.wait_for_timeout(400)
                await page.click(f'button[data-tab="{mod["tab"]}"]')
                await page.wait_for_timeout(wait_ms)

                # 日历模块需要原始数据做数值校验；页面渲染函数不暴露 payload，这里单独取一份
                if mod["tab"] == "market_calendar":
                    await page.evaluate(
                        """async () => {
                            try { window.__calendarPayload = await (await fetch('./data/market_calendar.json')).json(); }
                            catch (e) { window.__calendarPayload = null; }
                        }"""
                    )

                state = await page.evaluate(
                    """(tab) => {
                        const panel = document.getElementById('panel-' + tab);
                        if (!panel) return { missing: true };                        const canvas = panel.querySelector('canvas');
                        const text = (panel.innerText || '');
                        return {
                            missing: false,
                            canvasW: canvas ? canvas.width : 0,
                            canvasH: canvas ? canvas.height : 0,
                            text,
                            empty: panel.querySelectorAll('.empty').length,
                        };
                    }""",
                    mod["tab"],
                )

                if state.get("missing"):
                    entry.update(ok=False, notes=["面板元素不存在"])
                else:
                    if state["empty"] and not state["text"].strip():
                        entry.update(ok=False, notes=["面板内容为空"])
                    if mod["expect_canvas"] and (state["canvasW"] == 0 or state["canvasH"] == 0):
                        entry.update(ok=False, notes=entry["notes"] + ["缺少有效 canvas"])
                    hits = [w for w in FORBIDDEN if w in state["text"]]
                    if hits:
                        entry.update(ok=False, notes=entry["notes"] + [f"出现异常文案 {hits}"])
                    entry["text_len"] = len(state["text"])
            except Exception as exc:  # noqa: BLE001 - 冒烟脚本要收集全部失败
                entry.update(ok=False, notes=entry["notes"] + [f"交互异常: {exc}"])

            real_errors = [e for e in page_errors if e.strip() and e.strip() != "Script error."]
            if real_errors:
                entry["notes"] = entry["notes"] + [f"pageerror: {real_errors[0][:120]}"]
                entry["ok"] = False
            results.append(entry)

        # —— 数值合理性：图表可以正常画出来，但数值本身可能是荒唐的。
        # 本项目真实踩过：行业榜单把"行业内涨跌幅累加和"当涨幅，横轴跑到 -1000。
        # 这里直接读 echarts 实例的 option，校验坐标轴数据落在物理可能区间内。
        for chk in await page.evaluate(_VALUE_CHECK_JS):
            results.append(chk)

        await browser.close()

    results.append({"name": "__webgl__", "ok": True, "notes": [f"WebGL 可用={webgl}"]})
    return results


# 行业单日涨跌幅不可能超过 ±30%（A 股 20% 涨跌停 + 余量）。
# 多日区间按"日均值累加"，放宽到 ±30% × 天数，但单日必须在物理区间内。
_VALUE_CHECK_JS = r"""
() => {
  const out = [];
  const push = (name, ok, note) => out.push({ name: '数值校验: ' + name, ok, notes: [note] });

  // 1) 行业强弱：图表 xAxis 的最大绝对值不能大到荒唐
  const miTop = document.getElementById('mi-top');
  if (miTop) {
    const inst = window.echarts && window.echarts.getInstanceByDom ? window.echarts.getInstanceByDom(miTop) : null;
    if (inst) {
      const opt = inst.getOption();
      const xOpt = (opt.xAxis && opt.xAxis[0]) || {};
      const series = (opt.series && opt.series[0]) || {};
      const data = (series.data || []).map(v => typeof v === 'number' ? v : Number(v && v.value));
      const maxAbs = data.length ? Math.max(...data.map(v => Math.abs(v || 0))) : 0;
      // 区间最多 203 天；即便按累计，也不应超过 30% × 天数。单日必须 <= 30。
      const isMulti = String((xOpt.name || '')).indexOf('区间') >= 0;
      const limit = isMulti ? 30 * 203 : 30;
      push('行业强弱', maxAbs <= limit,
           `xAxis="${xOpt.name || '(未命名)'}" 最大绝对值=${maxAbs.toFixed(2)} 上限=${limit}`);
    }
  }

  // 2) 城市气泡：加权涨跌幅必须在 ±30% 内
  const bubble = document.getElementById('chinaCityBubbleRoot');
  if (bubble) {
    const m = (bubble.innerText || '').match(/加权涨跌\s*(-?\d+(?:\.\d+)?)%/);
    if (m) {
      const v = Math.abs(parseFloat(m[1]));
      push('城市气泡', v <= 30, `加权涨跌幅=${m[1]}% 上限=30`);
    }
  }

  // 3) 行业日历：日历格子只显示行业名不显示百分比，所以直接查数据源。
  //    后端 market_calendar.json 的 top_change_pct / bottom_change_pct 是行业日均涨跌幅，
  //    物理上不可能超过 ±30%（A 股最大 20% 涨跌停）。
  const calRoot = document.getElementById('marketCalendarRoot');
  if (calRoot) {
    const payload = window.__calendarPayload;
    if (payload && payload.years) {
      let worst = 0, worstLabel = '';
      Object.entries(payload.years).forEach(([yr, days]) => (days || []).forEach(d => {
        [['top_change_pct', d.top_industry], ['bottom_change_pct', d.bottom_industry]].forEach(([k, label]) => {
          const v = Math.abs(Number(d[k] || 0));
          if (v > worst) { worst = v; worstLabel = `${d.date} ${label}`; }
        });
      }));
      push('行业日历', worst <= 30, `最大绝对值=${worst.toFixed(2)}% (${worstLabel}) 上限=30%`);
    }
  }

  return out;
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="统一前端浏览器冒烟测试")
    parser.add_argument("--base-url", default="", help="已运行的服务地址；留空则自动起临时服务")
    parser.add_argument("--wait", type=int, default=5000, help="每次切页后的等待毫秒数")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("跳过：未安装 playwright。执行 `pip install playwright && playwright install chromium` 后再跑。")
        return 0

    if not (APP_DIR / "index.html").exists():
        print(f"跳过：{APP_DIR / 'index.html'} 不存在，请先构建统一前端。")
        return 0

    if args.base_url:
        results = asyncio.run(_probe(args.base_url, args.wait))
    else:
        with serve(APP_DIR) as base_url:
            results = asyncio.run(_probe(base_url, args.wait))

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        failed = [r for r in results if not r["ok"]]
        for r in results:
            mark = "PASS" if r["ok"] else "FAIL"
            note = ("  " + "; ".join(r["notes"])) if r.get("notes") else ""
            print(f"[{mark}] {r['name']}{note}")
        print()
        print(f"{len(results) - len(failed)}/{len(results)} 通过")

    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
