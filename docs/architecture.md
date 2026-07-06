# Architecture

## 设计目标

当前只实现龙虎榜，但结构必须允许后续能力直接接入：

1. 多数据源并存：行情、龙虎榜、新闻、公告、舆情。
2. 多分析链路并存：规则分析、图分析、向量检索、大模型分析。
3. 展示层解耦：静态 HTML、API、任务流都能复用同一份领域数据和应用服务。

## 分层说明

- `domain`
  - 放领域对象、规则、标签识别逻辑。
  - 不依赖具体数据库、网络请求或页面模板。
- `application`
  - 负责编排业务流程，例如“抓取龙虎榜 -> 入库 -> 生成页面”。
  - 协调数据源、仓储、模板，但不直接承载底层细节。
- `infrastructure`
  - 外部系统实现：HTTP 抓取、SQLite、仓储适配器。
- `presentation`
  - 静态页面模板、视图数据装配。
- `cli`
  - 面向任务执行和运维入口。

## 扩展路线

- 新闻资讯：
  - 新增 `domain/news/models.py`
  - 新增 `infrastructure/data_sources/news/*`
  - 新增 `application/services/news_ingestion.py`
- 图分析挖掘：
  - 新增 `application/services/network_analysis.py`
  - 在 `domain/graph` 定义图节点、边、子图、画像等模型
- 大模型分析：
  - 在 `domain/llm` 中定义分析任务协议
  - 在 `application/services` 增加组合型分析服务，消费新闻、龙虎榜、图谱结果

## 当前运行时数据流

统一前端是当前最主要的用户入口，数据流如下：

1. 采集脚本把龙虎榜、新闻、市场概览写入 SQLite 或 `data/market_overview/*.json`。
2. `UnifiedFrontendService.generate()` 初始化数据库、构建全局股票名称映射，并为每个页面模块生成独立 JSON。
3. `outputs/app/data/app_manifest.json` 记录生成时间、全局 `stock_names`、各模块 JSON 路径和可用状态。
4. `outputs/app/index.html` 是静态单页应用，首次加载 manifest，切换 tab 时再加载对应 JSON。
5. 前端中的 AI/智能分析配置存放在浏览器 `localStorage`，当前不是后端持久化配置。

## 统一前端维护约定

- 源模板是 `src/stockgraph/presentation/templates/unified_app.py`，生成物是 `outputs/app/index.html`。
- 数据构建逻辑在 `src/stockgraph/application/services/unified_frontend.py`；如果页面缺字段，先改这里生成 JSON，再改模板渲染。
- 股票输入控件统一使用 `buildStockOptions`、`stockOptionsDatalist`、`resolveStockOption` 这组前端工具。新增股票筛选时要支持输入筛选和下拉候选。
- 全 A 图谱使用自定义多选下拉，其他单选/关键词类股票控件使用 `<input list=...>` + `<datalist>`。
- `outputs/app/data/*.json` 是运行数据产物，构建可能刷新时间戳或排序；除非明确要提交演示数据，否则不要把无关 diff 混入功能提交。

## 当前技术决策

- 数据主存储继续使用 SQLite，适合单机分析与快速迭代。
- 生成页面继续保留为静态 HTML，方便直接打开和离线分发。
- 不在现阶段引入重量级 Web 框架，避免为展示需求过早耦合 API/前端工程。
