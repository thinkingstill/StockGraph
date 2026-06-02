---
name: stockgraph-dragon-tiger
description: 在 StockGraph 项目中拉取指定日期区间的龙虎榜数据并生成分析产物，供大模型进一步洞察使用。支持单日、区间回溯和后续分析结构化输出。
---

# StockGraph 龙虎榜数据拉取与分析 Skill

本 skill 用于复用 `StockGraph` 环境完成 A 股龙虎榜的指定日期区间拉取、分析 JSON 导出，以及为后续大模型洞察提供清晰的输入说明。

## 适用场景

- 需要指定日期/日期区间分析龙虎榜资金行为。
- 需要导出结构化 JSON，供规则分析、图表展示或调用大模型做洞察。
- 需要得到可直接消费的结论/下一步建议。

## 目录约定

- 项目根目录：`/root/StockGraph`
- 数据库：`data/shared_state/dragon_tiger.db`
- 分析输出：`outputs/dragon_tiger/`
- Python 环境：使用项目自带 `.venv/bin/python`
- 源码路径：命令统一加 `PYTHONPATH=src` 或使用 `scripts/` 兼容脚本

## 执行链路

1. 初始化数据库 schema  
   - `cd /root/StockGraph && .venv/bin/python scripts/init_db.py`
2. 同步指定日期龙虎榜  
   - `cd /root/StockGraph && .venv/bin/python scripts/sync_dragon_tiger.py --date YYYY-MM-DD`
   - 多条日期需逐日重复执行
3. 导出分析 JSON  
   - 单日：`cd /root/StockGraph && .venv/bin/python scripts/analyze_dragon_tiger.py --date YYYY-MM-DD`
   - 区间：`cd /root/StockGraph && .venv/bin/python scripts/analyze_dragon_tiger.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD`
4. 汇总结果并继续 LLM 洞察  
   - 读取 `outputs/dragon_tiger/dragon_tiger_analysis_*.json`
   - 调用大模型分析前，优先抽取出：`period/tradeDates`、`stats`、`rankings.topStocksByNetBuy`、`rankings.topSeatsByNetBuy`、`graphs`

## 日期处理规则

- `--date`：单个交易日
- `--start-date` + `--end-date`：日期区间
- 节假日/非交易日会返回空结果 JSON；后续 LLM 分析需降级处理
- 批量日期建议按调用方提供的日期列表逐日轮询

## 输出产物

脚本输出稳定 schema：`dragon_tiger_analysis.v1`，核心字段见：

- `period`
- `stats`
- `rankings`
- `daily`
- `operations`
- `graphs`

金额单位统一为 `万元`。

## 异常处理

- 远端接口失败时，脚本会写入空 JSON 并返回；不会中断批量任务
- 可定期检查 `data/shared_state/dragon_tiger.db` 是否正常增长即可
- 避免在高峰期高频并发调用

## 与 LLM 洞察的衔接建议

为减少下游大模型分析成本，方法调用前建议先抽关键统计，再组织成一段精简 prompt：

1. 先给 top N 股票、席位净额、图摘要
2. 再给 2~3 条显著信号（如机构净买、游资共现）
3. 最后让大模型输出市场情绪、资金结构和潜在策略含义

## 依赖

- 仅依赖 `StockGraph` 现有源码与 `.venv`
- 不修改 `source/` 目录
- 不重复实现抓取逻辑
