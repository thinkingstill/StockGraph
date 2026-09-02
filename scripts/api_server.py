#!/usr/bin/env python3
"""简单的 API 服务器，提供新闻采集等接口。"""

import json
import logging
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from stockgraph.application.services.news_ingestion import NewsIngestionService
from stockgraph.domain.stock_analysis import analyze_price_history
from stockgraph.infrastructure.db.repositories import DragonTigerRepository, NewsRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 输出目录
OUTPUT_DIR = ROOT_DIR / "outputs"


class APIHandler(SimpleHTTPRequestHandler):
    """处理 API 请求和静态文件服务。"""

    def __init__(self, *args, **kwargs):
        self.directory = str(OUTPUT_DIR)
        super().__init__(*args, directory=self.directory, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        # API 路由
        if parsed.path == "/api/news/sync":
            self._handle_news_sync(parsed)
        elif parsed.path == "/api/stock/context":
            self._handle_stock_context(parsed)
        elif parsed.path == "/api/health":
            self._handle_health()
        else:
            # 静态文件服务
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/news/sync":
            self._handle_news_sync_post()
        elif parsed.path == "/api/stock/context":
            self._handle_stock_context_post()
        else:
            self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        """处理 CORS 预检请求。"""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _handle_health(self):
        self._send_json({"status": "ok", "message": "API server is running"})

    def _handle_news_sync(self, parsed):
        """GET /api/news/sync?codes=000001,000002&limit=20"""
        params = parse_qs(parsed.query)
        codes = params.get("codes", [""])[0]
        limit = int(params.get("limit", ["20"])[0])

        if not codes:
            self._send_json({"error": "缺少 codes 参数"}, 400)
            return

        stock_codes = [c.strip() for c in codes.split(",") if c.strip()]
        if not stock_codes:
            self._send_json({"error": "codes 参数为空"}, 400)
            return

        try:
            service = NewsIngestionService()
            result = service.sync_stock_news(stock_codes, limit=limit)
            self._send_json({"success": True, "result": result})
        except Exception as e:
            logger.error("新闻同步失败: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_news_sync_post(self):
        """POST /api/news/sync {codes: [...], limit: 20}"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._send_json({"error": "请求体为空"}, 400)
            return

        try:
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            stock_codes = data.get("codes", [])
            limit = data.get("limit", 20)

            if not stock_codes:
                self._send_json({"error": "缺少 codes 字段"}, 400)
                return

            service = NewsIngestionService()
            result = service.sync_stock_news(stock_codes, limit=limit)
            self._send_json({"success": True, "result": result})
        except json.JSONDecodeError:
            self._send_json({"error": "无效的 JSON"}, 400)
        except Exception as e:
            logger.error("新闻同步失败: %s", e)
            self._send_json({"error": str(e)}, 500)

    def _handle_stock_context(self, parsed):
        """GET /api/stock/context?code=600519&start_date=2026-01-01&end_date=2026-07-26"""
        params = parse_qs(parsed.query)
        self._build_stock_context(
            params.get("code", [""])[0],
            params.get("start_date", [""])[0],
            params.get("end_date", [""])[0],
            sync_news=params.get("sync_news", ["false"])[0].lower() == "true",
        )

    def _handle_stock_context_post(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            self._build_stock_context(
                str(data.get("code") or data.get("stock_code") or ""),
                str(data.get("start_date") or ""),
                str(data.get("end_date") or ""),
                sync_news=bool(data.get("sync_news", True)),
            )
        except json.JSONDecodeError:
            self._send_json({"error": "无效的 JSON"}, 400)

    def _build_stock_context(self, code: str, start_date: str, end_date: str, *, sync_news: bool):
        digits = "".join(char for char in code if char.isdigit())
        if len(digits) != 6:
            self._send_json({"error": "请提供 6 位股票代码"}, 400)
            return
        code = digits
        start = (start_date or "").replace("-", "") or "20250101"
        end = (end_date or "").replace("-", "") or __import__("datetime").date.today().strftime("%Y%m%d")
        try:
            # 结构化行情来自 akshare；新闻和龙虎榜来自本项目的本地数据层。
            import akshare as ak
            frame = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="")
            history = []
            for _, row in frame.tail(180).iterrows():
                history.append({
                    "date": str(row.get("日期", "")), "open": float(row.get("开盘", 0) or 0),
                    "close": float(row.get("收盘", 0) or 0), "high": float(row.get("最高", 0) or 0),
                    "low": float(row.get("最低", 0) or 0), "volume": float(row.get("成交量", 0) or 0),
                    "amount": float(row.get("成交额", 0) or 0), "change_pct": float(row.get("涨跌幅", 0) or 0),
                })
            ingestion = None
            if sync_news:
                try:
                    ingestion = NewsIngestionService().sync_stock_news([code], limit=30)
                except Exception as exc:  # 行情可用时不因新闻源失败而整体失败
                    ingestion = {"warning": str(exc)}
            news = NewsRepository().query_news_by_stock(code, limit=30)
            dragon = DragonTigerRepository().export_query_dataset()
            dragon_days = [
                {"date": date, "operations": [op for op in operations if op.get("stockCode") == code]}
                for date, operations in dragon.items()
                if any(op.get("stockCode") == code for op in operations)
            ][:10]
            analysis = analyze_price_history(history, news=news, dragon_tiger=dragon_days)
            self._send_json({"success": True, "stock_code": code, "history": history, "news": news,
                             "dragon_tiger": dragon_days, "analysis": analysis, "news_sync": ingestion})
        except Exception as exc:
            logger.exception("个股结构化数据采集失败: %s", code)
            self._send_json({"error": str(exc)}, 500)

    def log_message(self, format, *args):
        logger.info(format, *args)


def run_server(host: str = "127.0.0.1", port: int = 8030):
    server = HTTPServer((host, port), APIHandler)
    logger.info("API 服务器启动: http://%s:%d", host, port)
    logger.info("静态文件目录: %s", OUTPUT_DIR)
    logger.info("API 端点:")
    logger.info("  GET  /api/health - 健康检查")
    logger.info("  GET  /api/news/sync?codes=000001,000002&limit=20 - 同步新闻")
    logger.info("  POST /api/news/sync {codes: [...], limit: 20} - 同步新闻")
    logger.info("  POST /api/stock/context - 拉取日线、新闻、龙虎榜并执行规则研判")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务器关闭")
        server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="StockGraph API Server")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址")
    parser.add_argument("--port", type=int, default=8030, help="端口号")
    args = parser.parse_args()

    run_server(args.host, args.port)
