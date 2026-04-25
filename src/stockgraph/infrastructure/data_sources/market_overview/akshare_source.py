import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import akshare as ak
import pandas as pd

from stockgraph.core.paths import MARKET_DATA_DIR

logger = logging.getLogger(__name__)


class AkshareMarketOverviewSource:
    def __init__(self) -> None:
        self.state_path = MARKET_DATA_DIR / "source_runtime_state.json"
        self.runtime_state = self._load_state()

    def get_exchange_date(self) -> str:
        sse_info = ak.stock_sse_summary()
        return str(sse_info.loc[sse_info["项目"] == "报告时间", "股票"].values[0])

    def fetch_market_spot(self) -> pd.DataFrame:
        providers = [
            {
                "name": "eastmoney_all",
                "runner": lambda: self._call_with_retry(
                    ak.stock_zh_a_spot_em,
                    name="stock_zh_a_spot_em",
                    attempts=2,
                ),
            },
            {
                "name": "eastmoney_segmented",
                "runner": self._fetch_market_spot_segmented,
            },
            {
                "name": "sina_all",
                "runner": lambda: self._call_with_retry(
                    ak.stock_zh_a_spot,
                    name="stock_zh_a_spot",
                    attempts=2,
                ),
            },
        ]

        last_exception = None
        for provider in self._ordered_providers("market_spot", providers):
            started = time.time()
            try:
                frame = provider["runner"]()
                frame = self._normalize_market_frame(frame)
                self._record_success(
                    category="market_spot",
                    provider=provider["name"],
                    duration_ms=(time.time() - started) * 1000,
                    record_count=len(frame),
                )
                return frame
            except Exception as exc:
                last_exception = exc
                logger.warning("市场概览源失败 %s: %s", provider["name"], exc)
                self._record_failure(
                    category="market_spot",
                    provider=provider["name"],
                    duration_ms=(time.time() - started) * 1000,
                    error=exc,
                )
        raise last_exception

    def fetch_xueqiu_hot(self) -> pd.DataFrame:
        hot_state = self._get_provider_state("hot_xueqiu", "parallel")
        max_workers = 1 if hot_state.get("consecutive_failures", 0) >= 2 else 3
        tasks = {
            "关注": lambda: ak.stock_hot_follow_xq(symbol="最热门"),
            "讨论": lambda: ak.stock_hot_tweet_xq(symbol="最热门").rename(columns={"关注": "讨论"}),
            "交易": lambda: ak.stock_hot_deal_xq(symbol="最热门").rename(columns={"关注": "交易"}),
        }

        results = {}
        started = time.time()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(func): name for name, func in tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as exc:
                    logger.warning("雪球热度拉取失败 %s: %s", name, exc)

        if "关注" not in results:
            self._record_failure(
                category="hot_xueqiu",
                provider="parallel",
                duration_ms=(time.time() - started) * 1000,
                error=RuntimeError("未能获取雪球关注热度"),
            )
            raise RuntimeError("未能获取雪球关注热度")

        merged = results["关注"]
        for column in ("讨论", "交易"):
            if column in results:
                merged = pd.merge(
                    merged,
                    results[column],
                    on=["股票代码", "股票简称", "最新价"],
                    how="outer",
                )
        self._record_success(
            category="hot_xueqiu",
            provider="parallel",
            duration_ms=(time.time() - started) * 1000,
            record_count=len(merged),
        )
        return merged

    def fetch_stock_histories(self, stock_codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        history_state = self._get_provider_state("stock_history", "parallel")
        max_workers = 4 if history_state.get("consecutive_failures", 0) >= 3 else 10

        def fetch_one(code: str) -> pd.DataFrame | None:
            try:
                return ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="",
                )
            except Exception:
                return None

        frames: list[pd.DataFrame] = []
        started = time.time()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, code): code for code in stock_codes}
            for future in as_completed(futures):
                frame = future.result()
                if frame is not None and not frame.empty:
                    frames.append(frame)

        if not frames:
            self._record_failure(
                category="stock_history",
                provider="parallel",
                duration_ms=(time.time() - started) * 1000,
                error=RuntimeError("未获取到历史行情"),
            )
            return pd.DataFrame()

        result = pd.concat(frames, ignore_index=True)
        self._record_success(
            category="stock_history",
            provider="parallel",
            duration_ms=(time.time() - started) * 1000,
            record_count=len(result),
        )
        return result

    def fetch_index_history(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        return ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)

    def _fetch_market_spot_segmented(self) -> pd.DataFrame:
        segmented_frames: list[pd.DataFrame] = []
        segmented_sources = [
            ("stock_sh_a_spot_em", ak.stock_sh_a_spot_em),
            ("stock_sz_a_spot_em", ak.stock_sz_a_spot_em),
            ("stock_bj_a_spot_em", ak.stock_bj_a_spot_em),
        ]
        for name, func in segmented_sources:
            try:
                frame = self._call_with_retry(func, name=name, attempts=2)
                if frame is not None and not frame.empty:
                    segmented_frames.append(frame)
                time.sleep(0.4)
            except Exception as exc:
                logger.warning("分市场实时行情拉取失败 %s: %s", name, exc)

        if not segmented_frames:
            raise RuntimeError("分市场实时行情全部失败")
        return pd.concat(segmented_frames, ignore_index=True)

    def _ordered_providers(self, category: str, providers: list[dict]) -> list[dict]:
        now = time.time()
        scored = []
        for index, provider in enumerate(providers):
            state = self._get_provider_state(category, provider["name"])
            cooldown_until = float(state.get("cooldown_until", 0))
            is_available = cooldown_until <= now
            success_count = int(state.get("success_count", 0))
            consecutive_failures = int(state.get("consecutive_failures", 0))
            last_success = float(state.get("last_success_ts", 0))
            average_duration = float(state.get("average_duration_ms", 0))
            recent_success_bonus = 0.0
            if last_success > 0:
                success_age = max(0.0, now - last_success)
                recent_success_bonus = max(0.0, 604800.0 - success_age) / 120.0
            score = (
                (10_000 if is_available else -10_000)
                + success_count * 120
                + recent_success_bonus
                - consecutive_failures * 900
                - average_duration / 50.0
                - index * 10
            )
            scored.append((score, provider))
        scored.sort(key=lambda item: item[0], reverse=True)
        ordered = [provider for _, provider in scored]
        logger.info("市场概览源顺序 %s: %s", category, [provider["name"] for provider in ordered])
        return ordered

    def _record_success(self, category: str, provider: str, duration_ms: float, record_count: int) -> None:
        state = self._get_provider_state(category, provider)
        previous_avg = float(state.get("average_duration_ms", 0))
        success_count = int(state.get("success_count", 0)) + 1
        state.update(
            {
                "success_count": success_count,
                "consecutive_failures": 0,
                "last_success_ts": time.time(),
                "last_success_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "average_duration_ms": duration_ms if previous_avg <= 0 else round(previous_avg * 0.7 + duration_ms * 0.3, 2),
                "last_record_count": record_count,
                "cooldown_until": 0,
                "last_error": "",
            }
        )
        self._save_state()

    def _record_failure(self, category: str, provider: str, duration_ms: float, error: Exception) -> None:
        state = self._get_provider_state(category, provider)
        failures = int(state.get("consecutive_failures", 0)) + 1
        cooldown_seconds = min(900, 30 * failures * failures)
        state.update(
            {
                "failure_count": int(state.get("failure_count", 0)) + 1,
                "consecutive_failures": failures,
                "last_failure_ts": time.time(),
                "last_failure_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "average_duration_ms": duration_ms,
                "cooldown_until": time.time() + cooldown_seconds,
                "last_error": str(error),
            }
        )
        self._save_state()

    def _get_provider_state(self, category: str, provider: str) -> dict:
        category_state = self.runtime_state.setdefault(category, {})
        return category_state.setdefault(provider, {})

    def _load_state(self) -> dict:
        try:
            if self.state_path.exists():
                return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("读取市场概览运行状态失败: %s", exc)
        return {}

    def _save_state(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(self.runtime_state, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("写入市场概览运行状态失败: %s", exc)

    @staticmethod
    def _normalize_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        normalized = frame.copy()
        if "代码" in normalized.columns:
            normalized["代码"] = normalized["代码"].astype(str).str[-6:].str.zfill(6)
            normalized = normalized.drop_duplicates(subset=["代码"], keep="first")
        return normalized

    @staticmethod
    def _call_with_retry(func, name: str, attempts: int = 3, base_sleep: float = 1.2):
        last_exception = None
        for attempt in range(1, attempts + 1):
            try:
                return func()
            except Exception as exc:
                last_exception = exc
                if attempt >= attempts:
                    break
                sleep_seconds = base_sleep * attempt
                logger.warning("%s 第 %s/%s 次失败，%.1f 秒后重试: %s", name, attempt, attempts, sleep_seconds, exc)
                time.sleep(sleep_seconds)
        raise last_exception
