#!/usr/bin/env python3
"""同步所有 A 股股票代码和名称。

设计要点（曾多次导致 CI 失败）：
- akshare 背后是深交所/上交所官网，境外出口（如 GitHub Actions 美国 IP）
  经常被 reset（ConnectionResetError 104）。因此必须有降级路径，
  不能因为拿不到最新列表就让整条同步链失败。
- 降级优先级：akshare 原始接口 -> akshare 备用接口 -> 已有 all_stock_codes.json
  兜底。只有全部失败且本地也没有历史文件时才真正报错。
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core.paths import REFERENCE_DATA_DIR, ensure_runtime_dirs

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_NAME = "all_stock_codes.json"


def _from_akshare_primary() -> dict:
    """主接口：akshare 聚合的沪深京 A 股代码名称。"""
    import akshare as ak

    df = ak.stock_info_a_code_name()
    result = {}
    for _, row in df.iterrows():
        code = str(row["code"]).strip()
        name = str(row["name"]).strip()
        if code and name:
            result[code] = name
    return result


def _from_akshare_secondary() -> dict:
    """备用接口：东财实时行情快照（不依赖交易所官网）。"""
    import akshare as ak

    df = ak.stock_zh_a_spot_em()
    result = {}
    for _, row in df.iterrows():
        code = str(row["代码"]).strip()
        name = str(row["名称"]).strip()
        if code and name:
            result[code] = name
    return result


def _load_existing() -> dict:
    path = REFERENCE_DATA_DIR / OUTPUT_NAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取历史 %s 失败：%s", OUTPUT_NAME, exc)
        return {}


def sync_all_stock_codes() -> dict:
    """获取所有 A 股股票代码和名称，多源降级，失败不中断同步链。"""
    sources = (
        ("akshare 主接口", _from_akshare_primary),
        ("akshare 东财快照", _from_akshare_secondary),
    )

    for label, loader in sources:
        try:
            logger.info("尝试通过%s获取 A 股列表...", label)
            stock_dict = loader()
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s获取失败：%s: %s", label, type(exc).__name__, exc)
            continue
        if stock_dict:
            logger.info("%s获取成功，共 %d 只股票", label, len(stock_dict))
            ensure_runtime_dirs()
            output_path = REFERENCE_DATA_DIR / OUTPUT_NAME
            output_path.write_text(
                json.dumps(stock_dict, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info("已保存到 %s", output_path)
            return stock_dict
        logger.warning("%s返回空列表，尝试下一个源", label)

    # 全部网络源失败：用仓库内已有的历史文件兜底，保证后续新闻同步仍可执行
    existing = _load_existing()
    if existing:
        logger.warning(
            "所有网络源获取失败，降级使用仓库内已有的 %s（%d 只股票）。"
            "本次不更新该文件，仅保证同步链继续。",
            OUTPUT_NAME,
            len(existing),
        )
        return existing

    raise RuntimeError("无法获取 A 股列表，且本地无历史 all_stock_codes.json 可兜底")


if __name__ == "__main__":
    try:
        result = sync_all_stock_codes()
    except Exception as exc:  # noqa: BLE001
        logger.error("同步股票代码失败：%s", exc)
        sys.exit(1)
    print(f"同步完成，共 {len(result)} 只股票")
