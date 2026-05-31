from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from stockgraph.core import REFERENCE_DATA_DIR, SHARED_STATE_DIR, ensure_runtime_dirs

logger = logging.getLogger(__name__)


ADMIN_LOCATIONS_URL = "https://geo.datav.aliyun.com/areas_v3/bound/all.json"
ADMIN_LOCATIONS_PATH = REFERENCE_DATA_DIR / "china_admin_locations.json"
LOCATION_MAPPING_PATH = REFERENCE_DATA_DIR / "stock_location_mapping.json"
PROFILE_CACHE_PATH = SHARED_STATE_DIR / "stock_location_profile_cache.json"


@dataclass
class ResolvedLocation:
    province: str
    city: str
    district: str
    lng: float
    lat: float
    adcode: int
    city_adcode: int
    province_adcode: int


class ChinaAdminResolver:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.by_adcode = {int(row["adcode"]): row for row in rows if row.get("adcode") is not None}
        self.provinces = [row for row in rows if row.get("level") == "province"]
        self.cities = [row for row in rows if row.get("level") == "city"]
        self.districts = [row for row in rows if row.get("level") == "district"]

    def resolve(self, address: str) -> ResolvedLocation | None:
        text = self._normalize_text(address)
        if not text:
            return None

        province = self._match_one(text, self.provinces)
        city_candidates = [row for row in self.cities if not province or int(row.get("parent") or 0) == int(province["adcode"])]
        district_candidates = [row for row in self.districts if not province or self._belongs_to_province(row, int(province["adcode"]))]

        city = self._match_one(text, city_candidates)
        district = self._match_one(text, district_candidates)

        if district and not city:
            parent = self.by_adcode.get(int(district.get("parent") or 0))
            if parent and parent.get("level") == "city":
                city = parent
            elif parent and parent.get("level") == "province":
                province = province or parent

        if city and not province:
            province = self.by_adcode.get(int(city.get("parent") or 0))
        if district and not province:
            parent = self.by_adcode.get(int(district.get("parent") or 0))
            if parent and parent.get("level") == "city":
                province = self.by_adcode.get(int(parent.get("parent") or 0))
            elif parent and parent.get("level") == "province":
                province = parent

        if province and not city and province.get("name") in {"北京市", "上海市", "天津市", "重庆市", "香港特别行政区", "澳门特别行政区"}:
            city = province

        coordinate_row = city or district or province
        if not province or not coordinate_row:
            return None

        if city:
            city_name = self._display_city_name(str(city["name"]))
            city_adcode = int(city["adcode"])
        else:
            city_name = self._display_city_name(str(province["name"]))
            city_adcode = int(province["adcode"])
        district_name = str(district["name"]) if district else ""

        return ResolvedLocation(
            province=str(province["name"]),
            city=city_name,
            district=district_name,
            lng=float(coordinate_row["lng"]),
            lat=float(coordinate_row["lat"]),
            adcode=int(coordinate_row["adcode"]),
            city_adcode=city_adcode,
            province_adcode=int(province["adcode"]),
        )

    def _belongs_to_province(self, row: dict, province_adcode: int) -> bool:
        parent = self.by_adcode.get(int(row.get("parent") or 0))
        if not parent:
            return False
        if int(parent.get("adcode") or 0) == province_adcode:
            return True
        grand_parent = self.by_adcode.get(int(parent.get("parent") or 0))
        return bool(grand_parent and int(grand_parent.get("adcode") or 0) == province_adcode)

    @staticmethod
    def _display_city_name(name: str) -> str:
        direct = {"北京市", "上海市", "天津市", "重庆市", "香港特别行政区", "澳门特别行政区"}
        return name[:-1] if name in direct and name.endswith("市") else name

    def _match_one(self, text: str, candidates: Iterable[dict]) -> dict | None:
        scored: list[tuple[int, int, dict]] = []
        for row in candidates:
            aliases = self._aliases(str(row.get("name") or ""))
            for alias in aliases:
                if alias and alias in text:
                    scored.append((len(alias), 1 if alias == row.get("name") else 0, row))
                    break
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return scored[0][2]

    @staticmethod
    def _normalize_text(value: str) -> str:
        return (
            str(value or "")
            .replace(" ", "")
            .replace("\u3000", "")
            .replace("(", "")
            .replace(")", "")
            .replace("（", "")
            .replace("）", "")
        )

    @staticmethod
    def _aliases(name: str) -> list[str]:
        suffixes = [
            "壮族自治区",
            "回族自治区",
            "维吾尔自治区",
            "特别行政区",
            "自治区",
            "自治州",
            "地区",
            "盟",
            "省",
            "市",
            "县",
            "区",
        ]
        aliases = [name]
        short = name
        for suffix in suffixes:
            if short.endswith(suffix) and len(short) > len(suffix):
                aliases.append(short[: -len(suffix)])
                break
        return sorted(set(aliases), key=len, reverse=True)


class StockLocationService:
    def sync(
        self,
        *,
        codes: list[str] | None = None,
        limit: int = 100,
        sleep_seconds: float = 1.2,
        force: bool = False,
        rebuild_only: bool = False,
        flush_every: int = 20,
    ) -> dict:
        ensure_runtime_dirs()
        admin_rows = self._load_admin_locations()
        resolver = ChinaAdminResolver(admin_rows)
        basic_info = self._load_stock_basic_info()
        existing_mapping = self._load_json_dict(LOCATION_MAPPING_PATH)
        profile_cache = self._load_json_dict(PROFILE_CACHE_PATH)

        target_codes = codes or basic_info["股票代码"].astype(str).str[-6:].str.zfill(6).tolist()
        target_codes = [self._normalize_code(code) for code in target_codes if self._normalize_code(code)]

        mapping = dict(existing_mapping)
        rebuilt_from_cache = 0
        for code in target_codes:
            if code in mapping and not force:
                continue
            cached = profile_cache.get(code)
            if cached and cached.get("status") == "ok":
                item = self._mapping_from_profile(code, cached.get("profile", {}), resolver, basic_info)
                if item:
                    mapping[code] = item
                    rebuilt_from_cache += 1

        if rebuild_only:
            self._write_json(LOCATION_MAPPING_PATH, mapping)
            return {
                "total_codes": len(target_codes),
                "mapping_count": len(mapping),
                "fetched": 0,
                "failed": 0,
                "rebuilt_from_cache": rebuilt_from_cache,
                "mapping_path": str(LOCATION_MAPPING_PATH),
            }

        fetched = 0
        failed = 0
        max_fetch = None if limit <= 0 else limit
        for code in target_codes:
            if max_fetch is not None and fetched >= max_fetch:
                break
            if code in mapping and not force:
                continue
            if code in profile_cache and profile_cache[code].get("status") == "ok" and not force:
                continue

            try:
                profile = self._fetch_cninfo_profile(code)
                if not profile:
                    profile_cache[code] = {"status": "empty", "updated_at": self._now()}
                    failed += 1
                else:
                    profile_cache[code] = {"status": "ok", "profile": profile, "updated_at": self._now()}
                    item = self._mapping_from_profile(code, profile, resolver, basic_info)
                    if item:
                        mapping[code] = item
                    else:
                        failed += 1
                fetched += 1
            except Exception as exc:
                logger.warning("股票所在地抓取失败 code=%s error=%s", code, exc)
                profile_cache[code] = {"status": "error", "error": str(exc)[:300], "updated_at": self._now()}
                fetched += 1
                failed += 1

            if fetched % max(flush_every, 1) == 0:
                self._write_json(PROFILE_CACHE_PATH, profile_cache)
                self._write_json(LOCATION_MAPPING_PATH, mapping)
                logger.info("股票所在地同步进度: fetched=%s mapping=%s failed=%s", fetched, len(mapping), failed)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        self._write_json(PROFILE_CACHE_PATH, profile_cache)
        self._write_json(LOCATION_MAPPING_PATH, mapping)
        return {
            "total_codes": len(target_codes),
            "mapping_count": len(mapping),
            "fetched": fetched,
            "failed": failed,
            "rebuilt_from_cache": rebuilt_from_cache,
            "mapping_path": str(LOCATION_MAPPING_PATH),
            "cache_path": str(PROFILE_CACHE_PATH),
        }

    def _mapping_from_profile(self, code: str, profile: dict, resolver: ChinaAdminResolver, basic_info: pd.DataFrame) -> dict | None:
        registered_address = str(profile.get("注册地址") or "").strip()
        office_address = str(profile.get("办公地址") or "").strip()
        resolved = resolver.resolve(registered_address) or resolver.resolve(office_address)
        if not resolved:
            return None
        basic_row = basic_info[basic_info["股票代码"] == code]
        basic_name = str(basic_row.iloc[0].get("股票简称") or "") if not basic_row.empty else ""
        stock_name = str(profile.get("A股简称") or basic_name or "").strip()
        return {
            "province": resolved.province,
            "city": resolved.city,
            "district": resolved.district,
            "lng": resolved.lng,
            "lat": resolved.lat,
            "adcode": resolved.adcode,
            "city_adcode": resolved.city_adcode,
            "province_adcode": resolved.province_adcode,
            "stock_name": stock_name,
            "registered_address": registered_address,
            "office_address": office_address,
            "source": "akshare.stock_profile_cninfo",
            "updated_at": self._now(),
        }

    @staticmethod
    def _fetch_cninfo_profile(code: str) -> dict:
        import akshare as ak

        frame = ak.stock_profile_cninfo(symbol=code)
        if frame is None or frame.empty:
            return {}
        row = frame.iloc[0].to_dict()
        return {str(key): value for key, value in row.items()}

    @staticmethod
    def _load_stock_basic_info() -> pd.DataFrame:
        path = REFERENCE_DATA_DIR / "stock_basic_info.pkl"
        if not path.exists():
            raise FileNotFoundError(f"未找到股票基础信息文件: {path}")
        frame = pd.read_pickle(path)
        frame["股票代码"] = frame["股票代码"].astype(str).str[-6:].str.zfill(6)
        return frame

    @staticmethod
    def _load_admin_locations() -> list[dict]:
        if not ADMIN_LOCATIONS_PATH.exists():
            logger.info("下载中国行政区划坐标: %s", ADMIN_LOCATIONS_URL)
            response = requests.get(ADMIN_LOCATIONS_URL, timeout=30)
            response.raise_for_status()
            ADMIN_LOCATIONS_PATH.write_text(response.text, encoding="utf-8")
        rows = json.loads(ADMIN_LOCATIONS_PATH.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError(f"行政区划坐标格式错误: {ADMIN_LOCATIONS_PATH}")
        return rows

    @staticmethod
    def _load_json_dict(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _normalize_code(value) -> str:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        return digits[-6:].zfill(6) if digits else ""

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
