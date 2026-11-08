"""新闻数据源公共工具：限速、会话、股票实体提取。

三个适配器（东方财富 / 财联社 / RSS）共用这些工具，避免各自复制限速逻辑。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


class PoliteSession:
    """带全局最小间隔的 requests 会话。

    财经站点普遍对高频请求返回空响应或 403，统一限速比每个适配器各写一遍更可靠。
    """

    def __init__(self, delay_seconds: float | None = None, timeout: float = 15.0) -> None:
        self.delay_seconds = (
            delay_seconds if delay_seconds is not None
            else env_float("STOCKGRAPH_REQUEST_DELAY_SECONDS", 0.8)
        )
        self.timeout = timeout
        self._session = None
        self._last_call = 0.0

    @property
    def session(self):
        if self._session is None:
            import requests

            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                }
            )
            self._session = session
        return self._session

    def get_json(self, url: str, params: dict[str, Any] | None = None, referer: str | None = None) -> dict:
        self._throttle()
        headers = {"Referer": referer} if referer else None
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        self._throttle()
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        return response.text

    def _throttle(self) -> None:
        if self.delay_seconds <= 0:
            return
        elapsed = time.time() - self._last_call
        if self._last_call and elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self._last_call = time.time()


def normalize_em_stock_list(raw: list[str] | None) -> list[dict[str, str]]:
    """东方财富的 stockList 形如 ["90.BK0704", "1.600000", "0.002827"]。

    只保留 A 股：市场前缀必须是 0（深/北）或 1（沪），
    像 `150.014238`（港股）、`90.BK0704`（板块）一律丢弃。
    """
    result: list[dict[str, str]] = []
    for item in raw or []:
        text = str(item)
        market, _, code = text.partition(".")
        if not code:
            continue
        if market not in {"0", "1"}:
            continue
        if len(code) == 6 and code.isdigit() and code not in {item["stock_code"] for item in result}:
            result.append({"stock_code": code})
    return result
