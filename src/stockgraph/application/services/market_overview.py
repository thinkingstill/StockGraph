from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import plotly.express as px

from stockgraph.core import MARKET_DATA_DIR, MARKET_OUTPUT_DIR, REFERENCE_DATA_DIR, ensure_runtime_dirs
from stockgraph.domain.market_overview import IndustryRanking, MarketDailySnapshot, MarketOverviewBundle, StockHotRecord, min_max_normalize
from stockgraph.infrastructure.data_sources.market_overview import AkshareMarketOverviewSource
from stockgraph.infrastructure.db import MarketOverviewRepository

logger = logging.getLogger(__name__)


class MarketOverviewService:
    def __init__(
        self,
        source: AkshareMarketOverviewSource | None = None,
        repository: MarketOverviewRepository | None = None,
    ) -> None:
        self.source = source or AkshareMarketOverviewSource()
        self.repository = repository or MarketOverviewRepository()

    def sync_daily(self, trade_date: str | None = None) -> dict:
        ensure_runtime_dirs()
        target_date = trade_date or self.source.get_exchange_date()
        basic_info = self._load_stock_basic_info()
        industry_mapping = self._build_industry_mapping(basic_info)
        stock_name_industry = self._build_stock_name_industry_mapping(basic_info)

        try:
            market_df = self.source.fetch_market_spot()
        except Exception as exc:
            logger.warning("市场实时行情抓取失败，尝试回退到本地缓存: %s", exc)
            market_df = self._load_cached_daily_snapshot()
            if market_df.empty:
                raise
            logger.warning("市场实时行情已回退到本地缓存")
        market_df["date"] = target_date
        market_df["代码"] = market_df["代码"].astype(str).str[-6:].str.zfill(6)
        market_df["行业"] = market_df.apply(
            lambda row: self._resolve_industry(
                stock_code=row["代码"],
                stock_name=row.get("名称", ""),
                industry_mapping=industry_mapping,
                stock_name_industry=stock_name_industry,
            ),
            axis=1,
        )
        market_code_industry = {
            str(row["代码"])[-6:].zfill(6): str(row["行业"])
            for _, row in market_df[["代码", "行业"]].iterrows()
            if str(row["行业"]).strip()
        }
        market_name_industry = {
            str(row["名称"]).strip(): str(row["行业"])
            for _, row in market_df[["名称", "行业"]].iterrows()
            if str(row["名称"]).strip() and str(row["行业"]).strip()
        }

        try:
            hot_df = self.source.fetch_xueqiu_hot()
            hot_df["date"] = target_date
            hot_df["股票代码"] = hot_df["股票代码"].astype(str).str[-6:].str.zfill(6)
            hot_df = hot_df.dropna(subset=[column for column in ("关注", "讨论", "交易") if column in hot_df.columns]).copy()
            hot_df["行业"] = hot_df.apply(
                lambda row: self._resolve_industry(
                    stock_code=row["股票代码"],
                    stock_name=row.get("股票简称", ""),
                    industry_mapping=industry_mapping,
                    stock_name_industry=stock_name_industry,
                    default_value="缺失",
                ),
                axis=1,
            )
            hot_df["行业"] = hot_df.apply(
                lambda row: self._resolve_industry_from_market_snapshot(
                    industry=row.get("行业", "缺失"),
                    stock_code=row.get("股票代码", ""),
                    stock_name=row.get("股票简称", ""),
                    market_code_industry=market_code_industry,
                    market_name_industry=market_name_industry,
                ),
                axis=1,
            )
            hot_df = hot_df.drop_duplicates(subset=["股票代码", "股票简称"], keep="first")
            hot_df["涨跌幅"] = hot_df["股票简称"].apply(lambda name: self._lookup_change_pct(market_df, name))
            hot_df.rename(columns={"关注": "关注_r", "讨论": "讨论_r", "交易": "交易_r"}, inplace=True)
            for column in ("关注", "讨论", "交易"):
                raw_column = f"{column}_r"
                if raw_column in hot_df.columns:
                    hot_df[column] = min_max_normalize(hot_df[raw_column].astype(float))
        except Exception as exc:
            logger.warning("雪球热度抓取失败，尝试回退到本地缓存: %s", exc)
            hot_df = self._load_cached_hot_snapshot()
            if not hot_df.empty:
                hot_df["date"] = target_date
                logger.warning("雪球热度已回退到本地缓存")
            else:
                logger.warning("无可用热度缓存，本次跳过热度可视化数据")
                hot_df = pd.DataFrame(columns=["股票代码", "股票简称", "关注", "讨论", "交易", "涨跌幅", "行业", "最新价"])

        top_industry = self._get_industry_extreme(market_df, largest=True)
        bottom_industry = self._get_industry_extreme(market_df, largest=False)

        bundle = MarketOverviewBundle(
            trade_date=target_date,
            daily_snapshot=MarketDailySnapshot(trade_date=target_date, records=market_df.to_dict(orient="records")),
            hot_records=[
                StockHotRecord(
                    trade_date=target_date,
                    stock_code=str(row["股票代码"]),
                    stock_name=str(row["股票简称"]),
                    latest_price=float(row["最新价"]) if pd.notna(row["最新价"]) else None,
                    follow_rank=float(row["关注"]) if "关注" in row and pd.notna(row["关注"]) else None,
                    tweet_rank=float(row["讨论"]) if "讨论" in row and pd.notna(row["讨论"]) else None,
                    deal_rank=float(row["交易"]) if "交易" in row and pd.notna(row["交易"]) else None,
                    change_pct=float(row["涨跌幅"]) if pd.notna(row["涨跌幅"]) else None,
                    industry=str(row["行业"]),
                )
                for _, row in hot_df.iterrows()
            ],
            top_industries=[IndustryRanking(trade_date=target_date, industry=top_industry, direction="top")] if top_industry else [],
            bottom_industries=[IndustryRanking(trade_date=target_date, industry=bottom_industry, direction="bottom")] if bottom_industry else [],
        )
        self.repository.save_bundle(bundle)

        daily_json = self._write_json(MARKET_DATA_DIR / f"stock_daily_{target_date}.json", market_df.to_dict(orient="records"))
        hot_json = self._write_json(MARKET_DATA_DIR / f"hot_daily_{target_date}.json", hot_df.to_dict(orient="records"))
        viz_html = self._build_hot_visualization(target_date, hot_df)
        return {
            "trade_date": target_date,
            "daily_json": str(daily_json),
            "hot_json": str(hot_json),
            "viz_html": str(viz_html) if viz_html else "",
            "top_industry": top_industry,
            "bottom_industry": bottom_industry,
            "hot_count": len(hot_df),
        }

    def build_yearly_industry_rankings(self, year: str | None = None) -> dict:
        ensure_runtime_dirs()
        current_year = year or self.source.get_exchange_date()[:4]
        start_date = f"{current_year}0101"
        end_date = f"{int(current_year) + 1}0101"

        basic_info = self._load_stock_basic_info()
        history_df = self.source.fetch_stock_histories(
            stock_codes=basic_info["股票代码"].astype(str).str[-6:].str.zfill(6).tolist(),
            start_date=start_date,
            end_date=end_date,
        )
        if history_df.empty:
            return {"year": current_year, "top_file": "", "bottom_file": ""}
        merged = pd.merge(history_df, basic_info, on="股票代码", how="left")
        top_df = self._group_industry_by_date(merged, largest=True)
        bottom_df = self._group_industry_by_date(merged, largest=False)
        top_file = self._write_json(MARKET_DATA_DIR / f"industry_top_{current_year}.json", top_df.to_dict(orient="records"))
        bottom_file = self._write_json(MARKET_DATA_DIR / f"industry_top_{current_year}s.json", bottom_df.to_dict(orient="records"))
        return {"year": current_year, "top_file": str(top_file), "bottom_file": str(bottom_file)}

    @staticmethod
    def _write_json(path: Path, payload) -> Path:
        path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
        return path

    def _build_hot_visualization(self, trade_date: str, hot_df: pd.DataFrame) -> Path | None:
        if hot_df.empty:
            return None
        figure = px.scatter_3d(
            hot_df,
            x="关注",
            y="讨论",
            z="涨跌幅",
            color="行业",
            hover_name="股票简称",
            title=f"A股每日热度 {trade_date}",
        )
        figure.update_layout(scene=dict(xaxis_title="关注", yaxis_title="讨论", zaxis_title="涨跌幅"))
        figure.update_traces(marker=dict(opacity=0.7))
        output = MARKET_OUTPUT_DIR / f"stock_hot_vis_{trade_date}.html"
        figure.write_html(str(output))
        return output

    @staticmethod
    def _lookup_change_pct(market_df: pd.DataFrame, stock_name: str) -> float:
        matches = market_df.loc[market_df["名称"] == stock_name, "涨跌幅"]
        if matches.empty:
            return float(market_df["涨跌幅"].min()) - 0.1
        return float(matches.iloc[0])

    @staticmethod
    def _get_industry_extreme(market_df: pd.DataFrame, largest: bool) -> str:
        filtered = market_df[market_df["行业"] != "未知"]
        grouped = filtered.groupby("行业")["涨跌幅"].sum().reset_index()
        if grouped.empty:
            grouped = market_df.groupby("行业")["涨跌幅"].sum().reset_index()
        if grouped.empty:
            return ""
        ordered = grouped.nlargest(1, "涨跌幅") if largest else grouped.nsmallest(1, "涨跌幅")
        return str(ordered.iloc[0]["行业"])

    @staticmethod
    def _group_industry_by_date(frame: pd.DataFrame, largest: bool) -> pd.DataFrame:
        def pick(group: pd.DataFrame) -> str:
            aggregate = group[group["行业"] != "未知"].groupby("行业")["涨跌幅"].sum().reset_index()
            if aggregate.empty:
                aggregate = group.groupby("行业")["涨跌幅"].sum().reset_index()
            ordered = aggregate.nlargest(1, "涨跌幅") if largest else aggregate.nsmallest(1, "涨跌幅")
            return str(ordered.iloc[0]["行业"])

        result = frame.groupby("日期").apply(pick).reset_index(name="行业")
        result["日期"] = result["日期"].astype(str)
        return result

    @staticmethod
    def _load_industry_mapping() -> dict:
        path = REFERENCE_DATA_DIR / "industry_mapping.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _load_stock_basic_info() -> pd.DataFrame:
        path = REFERENCE_DATA_DIR / "stock_basic_info.pkl"
        if not path.exists():
            raise FileNotFoundError(f"未找到股票基础信息文件: {path}")
        frame = pd.read_pickle(path)
        frame["股票代码"] = frame["股票代码"].astype(str).str[-6:].str.zfill(6)
        return frame

    @staticmethod
    def _build_industry_mapping(basic_info: pd.DataFrame) -> dict:
        mapping = MarketOverviewService._load_industry_mapping()
        if "股票代码" in basic_info.columns and "行业" in basic_info.columns:
            for _, row in basic_info[["股票代码", "行业"]].dropna().iterrows():
                code = str(row["股票代码"])[-6:].zfill(6)
                industry = str(row["行业"]).strip()
                if industry:
                    mapping[code] = industry
        return mapping

    @staticmethod
    def _build_stock_name_industry_mapping(basic_info: pd.DataFrame) -> dict:
        if "股票简称" not in basic_info.columns or "行业" not in basic_info.columns:
            return {}
        result = {}
        for _, row in basic_info[["股票简称", "行业"]].dropna().iterrows():
            name = str(row["股票简称"]).strip()
            industry = str(row["行业"]).strip()
            if name and industry:
                result[name] = industry
        return result

    @staticmethod
    def _resolve_industry(
        stock_code: str,
        stock_name: str,
        industry_mapping: dict,
        stock_name_industry: dict,
        default_value: str = "未知",
    ) -> str:
        code = str(stock_code)[-6:].zfill(6)
        if code in industry_mapping and industry_mapping[code]:
            return industry_mapping[code]
        name = str(stock_name).strip()
        if name and name in stock_name_industry:
            return stock_name_industry[name]
        return default_value

    @staticmethod
    def _resolve_industry_from_market_snapshot(
        industry: str,
        stock_code: str,
        stock_name: str,
        market_code_industry: dict,
        market_name_industry: dict,
    ) -> str:
        current = str(industry).strip()
        if current and current not in {"未知", "缺失"}:
            return current
        code = str(stock_code)[-6:].zfill(6)
        if code in market_code_industry and market_code_industry[code]:
            return market_code_industry[code]
        name = str(stock_name).strip()
        if name and name in market_name_industry and market_name_industry[name]:
            return market_name_industry[name]
        return current or "缺失"

    @staticmethod
    def _load_cached_daily_snapshot() -> pd.DataFrame:
        candidates = sorted(MARKET_DATA_DIR.glob("stock_daily_*.json"), reverse=True)
        if not candidates:
            return pd.DataFrame()
        return pd.read_json(candidates[0])

    @staticmethod
    def _load_cached_hot_snapshot() -> pd.DataFrame:
        candidates = sorted(MARKET_DATA_DIR.glob("hot_daily_*.json"), reverse=True)
        if not candidates:
            return pd.DataFrame()
        return pd.read_json(candidates[0])
