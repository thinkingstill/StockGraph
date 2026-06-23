#!/usr/bin/env python3
"""同步所有 A 股股票代码和名称。"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stockgraph.core.paths import REFERENCE_DATA_DIR, ensure_runtime_dirs

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def sync_all_stock_codes() -> dict:
    """获取所有 A 股股票代码和名称。"""
    import akshare as ak

    logger.info("正在获取所有 A 股股票列表...")
    df = ak.stock_info_a_code_name()
    
    # 转换为字典 {code: name}
    stock_dict = {}
    for _, row in df.iterrows():
        code = str(row["code"]).strip()
        name = str(row["name"]).strip()
        if code and name:
            stock_dict[code] = name
    
    logger.info(f"获取到 {len(stock_dict)} 只股票")
    
    # 保存到文件
    ensure_runtime_dirs()
    output_path = REFERENCE_DATA_DIR / "all_stock_codes.json"
    output_path.write_text(json.dumps(stock_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"已保存到 {output_path}")
    
    return stock_dict


if __name__ == "__main__":
    result = sync_all_stock_codes()
    print(f"同步完成，共 {len(result)} 只股票")
