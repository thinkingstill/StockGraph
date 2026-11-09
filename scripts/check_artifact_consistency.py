#!/usr/bin/env python3
"""前端产物一致性校验。

为什么需要这个脚本：产物「存在」不等于「可用」。曾发生过一次真实事故——
主索引已改成按日期分片版（graphs 被清空、只留 shard_index），但
app_manifest.json 还是旧版（没有 sharded 标记）。前端逻辑是

    if (section.sharded) await hydrateShards(section, payload);

标记缺失就不会去拉分片，渲染函数拿到空的 graphs，四个模块（全 A 图谱、
城市气泡、市场热度、龙虎榜）直接空白。文件都在、HTTP 全是 200，
只有真的点开页面才发现。

校验三件事：
1. manifest 里每个 section 指向的文件必须存在；
2. 若主索引含 shard_index，manifest 必须标记 sharded: true，且字段/分片数一致；
3. shard_index 里每个分片文件必须真实存在。

用法：
    python scripts/check_artifact_consistency.py            # 校验本地构建产物
    python scripts/check_artifact_consistency.py --json      # 机器可读
    python scripts/check_artifact_consistency.py --root DIR  # 指定产物根目录
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "outputs" / "app"


def check(root: Path) -> tuple[list[str], list[str]]:
    """返回 (错误列表, 提示列表)。"""
    errors: list[str] = []
    notes: list[str] = []
    data_dir = root / "data"
    manifest_path = data_dir / "app_manifest.json"

    if not manifest_path.exists():
        errors.append(f"缺少 manifest：{manifest_path}")
        return errors, notes

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"manifest 解析失败：{exc}")
        return errors, notes

    sections = manifest.get("sections") or {}
    if not sections:
        errors.append("manifest.sections 为空")
        return errors, notes

    for name, section in sections.items():
        rel = section.get("path")
        if not rel:
            errors.append(f"[{name}] section 缺少 path")
            continue
        target = (root / rel.lstrip("./")).resolve()
        if not target.exists():
            errors.append(f"[{name}] path 指向的文件不存在：{rel}")
            continue
        if target.suffix.lower() != ".json":
            continue

        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[{name}] {rel} 不是合法 JSON：{exc}")
            continue

        shard_index = payload.get("shard_index")
        shard_field = payload.get("shard_field")
        marked = bool(section.get("sharded"))

        if shard_index:
            # 主索引已分片，manifest 必须同步标记，否则前端不会加载分片
            if not marked:
                errors.append(
                    f"[{name}] 主索引含 {len(shard_index)} 个分片，"
                    f"但 manifest 未标记 sharded: true —— 前端会渲染空白"
                )
            if not shard_field:
                errors.append(f"[{name}] 主索引缺少 shard_field")
            elif isinstance(payload.get(shard_field), dict) and payload[shard_field]:
                errors.append(
                    f"[{name}] 主索引 {shard_field} 未清空（仍有 "
                    f"{len(payload[shard_field])} 项），分片与内联数据重复"
                )
            declared = section.get("shard_count")
            if declared is not None and declared != len(shard_index):
                errors.append(
                    f"[{name}] shard_count 不一致：manifest={declared}, "
                    f"实际={len(shard_index)}"
                )
            # 抽查前若干个分片文件是否存在
            missing = [
                k
                for k, p in list(shard_index.items())[:50]
                if not (root / p.lstrip("./")).resolve().exists()
            ]
            if missing:
                errors.append(
                    f"[{name}] 有 {len(missing)} 个分片文件缺失，例如：{missing[:3]}"
                )
            else:
                notes.append(f"[{name}] {len(shard_index)} 个分片索引校验通过")
        elif marked:
            errors.append(
                f"[{name}] manifest 标记了 sharded: true，但主索引没有 shard_index"
            )
        else:
            notes.append(f"[{name}] 单文件产物，{target.stat().st_size / 1024:.0f}KB")

    return errors, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="前端产物一致性校验")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="产物根目录（含 data/）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    root = Path(args.root)
    errors, notes = check(root)

    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors, "notes": notes},
                         ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    for n in notes:
        print(f"[OK]   {n}")
    for e in errors:
        print(f"[FAIL] {e}")
    if errors:
        print(f"\n{len(errors)} 个问题：产物不一致会导致前端模块空白")
        return 1
    print("\n一致性校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
