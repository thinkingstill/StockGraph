# StockGraph

`StockGraph` 是一个面向 A 股市场数据分析的可扩展工程骨架，当前已将 `source/` 中已有的龙虎榜抓取、SQLite 存储、查询页面生成、关系图页面生成能力拆分进稳定的分层结构中，并为后续新闻资讯接入、图关系分析与挖掘、大模型分析预留模块边界。

## 目录结构

```text
StockGraph/
├── data/
│   └── shared_state/         # SQLite、缓存、跨模块共享数据
├── docs/
│   └── architecture.md
├── outputs/
│   ├── app/                  # 统一前端产物（index.html + data/）
│   ├── html/                 # 生成的静态页面
│   └── market/               # 市场热度 HTML
├── scripts/                  # 根目录执行入口
├── source/                   # 原始参考实现，保留不动
└── src/stockgraph/
    ├── application/          # 应用服务编排
    ├── cli/                  # python -m 入口
    ├── core/                 # 路径、日志、配置
    ├── domain/               # 领域模型与规则
    ├── infrastructure/       # 数据源、数据库、外部依赖
    │   └── data_sources/news/
    │       ├── akshare_source.py  # akshare 个股新闻 + 财联社快讯
    │       ├── base.py            # 新闻源统一接口
    │       ├── eastmoney.py       # 东方财富资讯（占位）
    │       ├── cls.py             # 财联社（占位）
    │       └── rss.py             # RSS/通用网页源（占位）
    └── presentation/         # HTML 模板与展示拼装
```

## 已实现能力

- 龙虎榜数据抓取编排
- SQLite 初始化与数据写入
- 席位类型识别、知名游资别名识别
- 查询页面生成
- 综合关系网络页面生成
- 新闻领域模型、清洗/标签规则骨架
- 新闻入库服务与新闻数据源占位接口
- **akshare 个股新闻采集**：通过 `stock_news_em` 获取东方财富个股近期新闻，支持按股票代码批量拉取
- **akshare 财联社快讯采集**：通过 `stock_news_main_cx` 获取财联社新闻快讯
- **个股新闻 UI 展示**：统一前端新增「个股新闻」tab，支持股票卡片浏览、情绪筛选、新闻时间线详情
- **🤖 AI 智能分析**：统一前端新增「AI 分析」tab，支持配置兼容 OpenAI 的 API（baseurl/key/model），选择股票后自动组装新闻+龙虎榜上下文，调用大模型进行流式分析
- 图节点/边模型、二部图/投影图构建骨架
- 图快照持久化与图分析 CLI 入口
- 市场概览模块：全市场行情、雪球热度、行业强弱、3D 热度可视化
- **全 A 股超大关系图谱**：基于 ECharts Graph 展示全市场股票节点，并按交易日叠加行业、交易所、涨跌状态、交易分层、龙虎榜席位、知名游资别名、新闻、事件、情绪等关系节点

## 当前状态

当前仓库已经不是纯骨架，下面这些已经落地：

- 龙虎榜主流程可运行：
  - `sync_dragon_tiger` 可抓取、入库、生成页面
- 展示层可运行：
  - `generate_dashboards` 可生成查询页和综合分析页
- 新闻链路已打通：
  - 已有 `NewsArticle / NewsEntity / NewsLink` 领域模型
  - 已有标准化、去重 hash、基础情绪/事件类型标注
  - **已接入 akshare 个股新闻**：通过 `stock_news_em` 获取东方财富个股近期新闻
  - **已接入 akshare 财联社快讯**：通过 `stock_news_main_cx` 获取全局新闻
  - `sync_news` 支持全局新闻同步和按股票代码的个股新闻同步
  - 新闻可通过实体关联（`news_entities`）和 metadata 双路径按股票代码查询
  - 统一前端新增「个股新闻」tab，支持卡片浏览、情绪筛选、时间线详情
- **AI 分析链路已打通**：
  - 统一前端新增「🤖 AI 分析」tab
  - 支持配置兼容 OpenAI 的 API（Base URL / API Key / 模型名称），配置保存到 localStorage
  - 选择股票后自动组装新闻 + 龙虎榜上下文，调用大模型进行流式分析
  - 后端 `_build_ai_analysis_data` 合并新闻和龙虎榜两个来源的股票，构建完整分析上下文
- 图分析链路已打通框架：
  - 已能从现有龙虎榜数据构建 `seat-stock`、`seat-seat`、`stock-stock` 图快照
  - 已有 `build_graph_snapshots` 入口并支持写入数据库
- **全 A 股图谱展示链路已打通**：
  - 统一前端新增「全 A 图谱」tab
  - 数据文件：`outputs/app/data/stock_super_graph.json`
  - 股票全集复用 `data/market_overview/stock_daily_*.json`
  - 热度属性复用 `data/market_overview/hot_daily_*.json`
  - 龙虎榜席位边复用 `stock_seat_operations`
  - 新闻边复用 `news_articles / news_entities`
  - 支持按交易日切换，并支持行业、交易所、节点类型、关键词和核心节点规模筛选

当前还没有完成的部分：

- 东方财富资讯、RSS 的真实抓取与解析（财联社已通过 akshare 接入）
- 新闻标题/正文到股票、机构、概念的更准确映射
- 新闻和龙虎榜的后端联动分析服务
- 图谱社区发现、路径挖掘、主题簇分析
- 大模型分析服务的后端独立服务化（当前已通过前端直调 OpenAI 兼容 API 实现）
- 全 A 图谱里的“概念/题材/基金/公告/股东”等节点还未接入，但现有 `node.category + attributes + relation_types` 结构已预留扩展空间

## 功能完整度检查

按当前 README 和代码状态看，项目已达到“可运行分析应用”阶段，不再是单纯工程骨架：

- 数据采集完整度：龙虎榜、全市场行情、雪球热度、akshare 个股新闻/财联社快讯已可用；东方财富资讯、RSS 等多源新闻仍是占位或待增强。
- 数据存储完整度：SQLite schema 覆盖龙虎榜、新闻实体、图节点边、市场概览；图谱快照和统一前端 JSON 已能落盘。
- 可视化完整度：统一前端已有龙虎榜查询、龙虎榜关系网、市场热度、行业日历、行业强弱、全 A 图谱、个股新闻、AI 分析 8 个模块。
- 图谱完整度：已有龙虎榜小图和全 A 多类型大图；社区发现、路径分析、主题簇和图摘要仍需继续实现。
- AI 分析完整度：前端直调 OpenAI 兼容 API 已可用；后端服务化、结构化提示词契约和图谱摘要接入仍待扩展。

## 运行方式

```bash
cd /home/wlh/StockGraph
PYTHONPATH=src python3 -m stockgraph.cli.init_db
PYTHONPATH=src python3 -m stockgraph.cli.generate_dashboards
PYTHONPATH=src python3 -m stockgraph.cli.sync_dragon_tiger --date 2026-04-17
PYTHONPATH=src python3 -m stockgraph.cli.sync_news --limit 50
PYTHONPATH=src python3 -m stockgraph.cli.sync_news --stock-codes "000001,600519" --stock-limit 10
PYTHONPATH=src python3 -m stockgraph.cli.build_graph_snapshots --persist
PYTHONPATH=src python3 -m stockgraph.cli.sync_market_overview --year 2025
PYTHONPATH=src python3 -m stockgraph.cli.build_unified_app
```

也可以直接用根目录脚本：

```bash
python3 scripts/init_db.py
python3 scripts/generate_dashboards.py
python3 scripts/sync_dragon_tiger.py --date 2026-04-17
python3 scripts/sync_news.py --limit 50
python3 scripts/sync_news.py --stock-codes "000001,600519" --stock-limit 10
python3 scripts/build_graph_snapshots.py --persist
python3 scripts/sync_market_overview.py --year 2025
python3 scripts/build_unified_app.py
```

如果希望一次性生成所有数据和页面，直接运行：

```bash
cd /home/wlh/StockGraph
bash run_full_sync.sh
```

`run_full_sync.sh` 默认会执行：

- 初始化数据库 schema
- 同步龙虎榜
- 生成龙虎榜页面
- 同步市场概览数据
- 同步新闻
- 构建图快照
- 生成统一前端，包括「全 A 图谱」所需的 `stock_super_graph.json`
- 生成开发首页

市场数据不需要每次都“按年运行”。`sync_market_overview` 每次都会同步一个交易日的全市场行情和热度数据；`--year` 只是额外生成某一年的年度行业榜单。日常同步建议不传 `--year`，需要刷新年度行业榜单时再运行：

```bash
BUILD_YEARLY_MARKET=1 MARKET_OVERVIEW_YEAR=2026 bash run_full_sync.sh
```

常用开关：

- `TARGET_DATE=2026-04-24` — 指定龙虎榜和市场概览同步日期
- `NEWS_LIMIT=100` — 控制新闻同步数量
- `SYNC_NEWS=0` — 跳过新闻同步，复用已有新闻数据
- `BUILD_GRAPHS=0` — 跳过图快照构建，但仍会生成统一前端里的全 A 图谱 JSON
- `BUILD_YEARLY_MARKET=1` — 额外生成年度行业榜单

`sync_news` 新增参数：

- `--stock-codes "000001,600519"` — 逗号分隔的股票代码列表，用于个股新闻采集。留空则自动从龙虎榜获取近期活跃股票
- `--stock-limit 10` — 每个股票最多采集多少条新闻，默认 20
- `--skip-stock-news` — 跳过个股新闻采集，仅同步全局新闻

## 统一前端入口

现在的主入口页面改为：

- [outputs/app/index.html](/home/wlh/StockGraph/outputs/app/index.html)

页面内按 tab 划分为 8 个模块：

- 龙虎榜查询
- 龙虎榜关系网
- 热度图
- **全 A 图谱**（ECharts Graph 超大关系图，按交易日展示股票、行业、交易所、席位、新闻、交易状态等多类型节点）
- 行业日历
- 行业强弱
- **个股新闻**（基于 akshare 采集的东方财富个股新闻，支持股票卡片浏览、情绪筛选、新闻时间线详情）
- **🤖 AI 分析**（配置兼容 OpenAI 的 API，选择股票后自动组装上下文进行流式分析）

其中“热度图”已经补成接近原 `stock-se stock_daily.html` 的完整交互版，支持：

- X/Y/Z 轴切换
- 点大小维度切换
- 交易所筛选
- 行业筛选
- 关键词搜索
- 表格与 3D 图联动查看

前后端分离方式：

- 前端 HTML:
  - `outputs/app/index.html`
- 独立数据文件:
  - `outputs/app/data/app_manifest.json`
  - `outputs/app/data/dragon_tiger_query.json`
  - `outputs/app/data/dragon_tiger_graph.json`
- `outputs/app/data/market_hot.json`
- `outputs/app/data/stock_super_graph.json`
- `outputs/app/data/market_calendar.json`
- `outputs/app/data/market_industry.json`
- `outputs/app/data/stock_news.json`
- `outputs/app/data/ai_analysis.json`

设计原则：

- 每个 tab 单独 fetch 自己的数据文件
- 每个 tab 单独显示可用/不可用状态
- 某一个数据文件生成失败，不影响其他 tab 使用
- daily 最后统一刷新一次前端产物

## 开发一键启动

开发环境下可直接用根目录脚本启动静态预览：

```bash
cd /home/wlh/StockGraph
bash dev_start.sh
```

启动脚本会执行：

1. 初始化数据库 schema
2. 生成龙虎榜查询页和综合分析页
3. 默认尝试同步市场概览
4. 生成统一开发首页
5. 启动本地静态服务

默认访问地址：

- `http://127.0.0.1:8030/app/index.html`

可选环境变量：

- `HOST=0.0.0.0`
  - 对容器或局域网开放访问
- `PORT=8031`
  - 自定义端口
- `SYNC_MARKET_OVERVIEW=0`
  - 启动时跳过市场概览同步
- `SYNC_DRAGON_TIGER=1`
  - 启动时顺便同步龙虎榜最新数据

开发首页会聚合这些页面：

- 统一入口
- 龙虎榜查询
- 龙虎榜综合分析
- 最新市场热度 3D 可视化页面

## stock-se 已整合内容

`/home/wlh/stock-se` 的核心能力已经整合进 `StockGraph`，不再需要把它作为独立项目维护。

已整合范围：

- 全市场日行情抓取
- 雪球关注/讨论/交易热度抓取
- 行业映射与行业强弱统计
- Plotly 3D 热度页面生成
- 年度行业强势/弱势榜单生成

对应模块：

- 领域模型：
  - `src/stockgraph/domain/market_overview/`
- 数据源：
  - `src/stockgraph/infrastructure/data_sources/market_overview/akshare_source.py`
- 应用服务：
  - `src/stockgraph/application/services/market_overview.py`
- CLI：
  - `src/stockgraph/cli/sync_market_overview.py`
- 兼容脚本：
  - `scripts/sync_market_overview.py`

迁移过来的参考数据：

- [data/reference/industry\_mapping.json](/home/wlh/StockGraph/data/reference/industry_mapping.json)
- [data/reference/stock\_basic\_info.pkl](/home/wlh/StockGraph/data/reference/stock_basic_info.pkl)

新的输出位置：

- 市场数据 JSON：
  - `data/market_overview/`
- 市场热度 HTML：
  - `outputs/market/`

### 市场概览拉取策略

市场概览的数据源现在不是固定单源，而是按“历史状态 + 当前运行状态”自动调整：

- 市场实时行情会按状态动态选择：
  - `eastmoney_all`：`stock_zh_a_spot_em`
  - `eastmoney_segmented`：`stock_sh_a_spot_em` / `stock_sz_a_spot_em` / `stock_bj_a_spot_em`
  - `sina_all`：`stock_zh_a_spot`
- 运行状态会写入：
  - `data/market_overview/source_runtime_state.json`
- 评分会综合这些因素：
  - 最近成功次数
  - 最近成功时间
  - 连续失败次数
  - 平均耗时
  - 是否仍在冷却期
- 某个源连续失败后会进入冷却期，后续运行会自动降低优先级。
- 雪球热度和历史行情抓取也会根据最近失败情况自动降低并发，减少被远端限流或断连的概率。

这套策略的目标不是“永远只用一个最优源”，而是：

- 东财状态稳定时优先使用东财
- 东财波动时自动切到分市场接口
- 东财整体不可用时自动回退新浪
- 下一次定时任务再根据最新运行结果重新调整顺序

## 容器定时执行

项目根目录提供了两个适合容器/cron 使用的脚本：

- [deploy\_python\_env.sh](/home/wlh/StockGraph/deploy_python_env.sh)
  - 创建 `.venv`
  - 安装项目依赖
  - 安装 `akshare / pandas / plotly / tqdm`
  - 初始化数据库
  - 默认执行一次源码编译检查
- [run\_daily\_sync.sh](/home/wlh/StockGraph/run_daily_sync.sh)
  - 初始化 schema
  - 执行龙虎榜同步
  - 重新生成 HTML 页面
  - 默认执行市场概览同步
  - 可选执行新闻同步和图快照构建

首次部署：

```bash
cd /home/wlh/StockGraph
bash deploy_python_env.sh
```

每天执行：

```bash
cd /home/wlh/StockGraph
bash run_daily_sync.sh
```

完整日常执行链路现在是：

1. 初始化数据库 schema。
2. 同步龙虎榜数据。
3. 生成龙虎榜查询页和综合分析页。
4. 默认同步市场概览：
   - 全市场日行情
   - 雪球热度
   - 行业强弱
   - 3D 热度可视化
5. 按开关决定是否同步新闻和构建图快照。

如果你希望容器里每天直接跑完整版本，推荐这样：

```bash
cd /home/wlh/StockGraph
SYNC_MARKET_OVERVIEW=1 \
SYNC_NEWS=1 \
BUILD_GRAPHS=1 \
bash run_daily_sync.sh
```

常用环境变量：

- `VENV_DIR`
  - 指定虚拟环境目录，默认 `.venv`
- `PYTHON_BIN`
  - 只用于 `deploy_python_env.sh`，指定创建虚拟环境用的 Python
- `RUN_SMOKE_TEST=0`
  - 部署时跳过 `compileall` 检查
- `TARGET_DATE`
  - 指定同步日期，例如 `2026-04-17`
- `SYNC_NEWS=1`
  - 额外执行新闻同步
- `BUILD_GRAPHS=1`
  - 额外执行图快照构建
- `SYNC_MARKET_OVERVIEW=1`
  - 执行全市场概览和热度同步，默认已开启
- `MARKET_OVERVIEW_YEAR=2025`
  - 同步市场概览时额外生成某一年的行业强弱榜单
- `NEWS_LIMIT=100`
  - 控制新闻同步条数
- `NEWS_STOCK_LIMIT=5`
  - 控制每只股票最多采集多少条个股新闻，默认较保守，避免对同一站点连续请求过多
- `SYNC_DRAGON_TIGER=0`
  - 跳过龙虎榜远端同步，只初始化数据库并复用已有数据生成页面
- `STOCKGRAPH_HOT_MAX_WORKERS=1`
  - 控制雪球热度抓取并发数，默认 1
- `STOCKGRAPH_HISTORY_MAX_WORKERS=2`
  - 控制年度历史行情抓取并发数，默认 2
- `STOCKGRAPH_REQUEST_DELAY_SECONDS=0.8`
  - 控制 akshare 相关连续请求之间的礼貌延迟

cron 示例：

```cron
0 9 * * 1-5 cd /home/wlh/StockGraph && SYNC_MARKET_OVERVIEW=1 SYNC_NEWS=1 BUILD_GRAPHS=1 /bin/bash /home/wlh/StockGraph/run_daily_sync.sh >> /var/log/stockgraph.log 2>&1
```

如果只想跑“龙虎榜 + 市场概览”，用默认命令即可：

```cron
0 9 * * 1-5 cd /home/wlh/StockGraph && /bin/bash /home/wlh/StockGraph/run_daily_sync.sh >> /var/log/stockgraph.log 2>&1
```

## GitHub Actions 自动运行

仓库已预留 GitHub Actions 工作流：

- `.github/workflows/pages.yml`

它会在以下场景触发，但不同触发方式的行为不同：

- push 到 `main`
- GitHub Actions 页面手动触发 `workflow_dispatch`
- 工作日 10:00 UTC 定时执行（对应北京时间 18:00，尽量避开盘中高频访问）

push 到 `main` 时只做离线校验，不访问 akshare 或远端行情站点：

1. 安装 Python 依赖：`python -m pip install -e .`
2. 运行 `python -m compileall src scripts`
3. 使用 `SYNC_DRAGON_TIGER=0 SYNC_MARKET_OVERVIEW=0 SYNC_NEWS=0 BUILD_GRAPHS=0 bash run_daily_sync.sh` 做离线页面构建检查

手动触发和定时触发才会生成并发布 GitHub Pages：

1. 安装 Python 依赖：`python -m pip install -e .`
2. 运行 `bash run_daily_sync.sh`
3. 运行 `python scripts/build_pages_site.py`
4. 将 `outputs/` 上传为 GitHub Pages artifact
5. 发布到 GitHub Pages

为降低 akshare 或目标站点封禁风险，Actions 里的默认策略是：

- push 不抓取远端数据。
- 定时任务默认同步龙虎榜和市场概览，但不默认同步新闻、不默认构建年度历史榜单。
- 手动触发时才建议打开 `sync_news` / `build_graphs`。
- 年度行业榜单只有传入 `market_overview_year` 时才生成；它会拉取大量历史行情，不建议每天跑。
- Actions 默认设置 `STOCKGRAPH_HOT_MAX_WORKERS=1`、`STOCKGRAPH_HISTORY_MAX_WORKERS=2`、`STOCKGRAPH_REQUEST_DELAY_SECONDS=0.8`。

手动触发时可选输入：

- `target_date`
  - 指定同步日期，例如 `2026-04-17`
- `market_overview_year`
  - 额外生成年度行业强弱榜单，例如 `2025`
- `sync_news`
  - 是否同时执行新闻同步
- `build_graphs`
  - 是否同时执行图快照构建

为了兼容 CI，`run_daily_sync.sh` 和 `dev_start.sh` 现在都支持通过 `PYTHON_BIN` 指定解释器；在 GitHub Actions 中默认使用：

```bash
PYTHON_BIN=python
```

## GitHub Pages 发布方式

当前 Pages 采用“**CI 构建产物 + artifact 部署**”模式，而不是把 `outputs/` 里的 HTML / JSON 直接提交进仓库。

这意味着：

- 仓库里保留源码、脚本、配置和文档
- `outputs/` 仍然作为运行时生成目录被 `.gitignore` 忽略
- `data/market_overview/*.json`、`data/shared_state/*.db`、`source/*.db` 也不提交，避免把运行缓存、数据库和抓取产物混入源码库
- GitHub Actions 每次执行时重新构建 `outputs/`
- Pages 实际发布的内容来自 CI 上传的 artifact

当前页面入口约定：

- Pages 根入口：`outputs/index.html`
- 主功能页：`outputs/app/index.html`

其中：

- `scripts/build_dev_index.py` 负责生成 `outputs/index.html`
- `scripts/build_pages_site.py` 负责补齐 Pages 发布所需文件，例如 `.nojekyll`

### 首次启用 GitHub Pages 的仓库设置建议

在 GitHub 仓库页面中建议确认以下配置：

1. `Settings -> Pages`
   - Source 选择 **GitHub Actions**
2. `Settings -> Actions -> General`
   - 确认允许工作流运行
3. 若仓库是私有仓库
   - 需要确认当前账号方案支持 GitHub Pages

首次工作流跑完后，GitHub 会给出一个 Pages 地址。后续访问方式通常是：

- 仓库首页 Pages 根地址：对应 `outputs/index.html`
- 统一应用页面：`<pages-base-url>/app/index.html`

## 后续扩展建议

- `domain/news` + `infrastructure/data_sources/news`：资讯抓取、清洗、事件抽取
- `domain/graph` + `application/services/network_analysis.py`：图构建、社区发现、路径挖掘
- `domain/llm`：提示词、分析协议、解释与摘要
- `data/shared_state/`：继续作为跨模块共享层，避免不同能力各自产生孤岛数据库

## 扩展路线一：新闻资讯接入

目标是把新闻变成可被后续规则分析、图谱分析和大模型分析复用的标准化事件数据，而不是只做一层抓取。

建议按下面的目录继续扩展：

```text
src/stockgraph/
├── domain/news/
│   ├── models.py                # NewsArticle、NewsEntity、NewsEvent
│   ├── normalization.py         # 标题、时间、来源、去重规则
│   └── tagging.py               # 股票、行业、机构、情绪标签
├── infrastructure/data_sources/news/
│   ├── base.py                  # 新闻源统一接口
│   ├── akshare_source.py        # akshare 个股新闻 + 财联社快讯（已实现）
│   ├── eastmoney.py             # 东方财富资讯（占位）
│   ├── cls.py                   # 财联社（占位）
│   └── rss.py                   # RSS/通用网页源（占位）
├── infrastructure/db/
│   ├── schema.py                # news_articles、news_entities、news_article_links
│   └── repositories.py          # NewsRepository：save_batch、query_news_by_stock、query_all_news
└── application/services/
    └── news_ingestion.py        # 抓取 -> 清洗 -> 去重 -> 入库（支持全局 + 个股新闻）
```

建议的数据流：

1. `data_source` 抓原始新闻，统一输出 `NewsArticle`。
2. `domain/news/normalization.py` 做时间标准化、正文清洗、URL 标准化、标题去噪。
3. `domain/news/tagging.py` 做股票代码映射、机构名识别、情绪和事件类型标注。
4. `application/services/news_ingestion.py` 负责编排去重、入库、重试、增量更新。
5. 将结果存入 `data/shared_state/dragon_tiger.db` 或后续拆分出的 `market_intel.db`。

建议新增的表：

- `news_articles`
  - `id`, `source`, `title`, `content`, `published_at`, `url`, `hash`, `sentiment`, `event_type`, `created_at`
- `news_entities`
  - `id`, `article_id`, `entity_type`, `entity_code`, `entity_name`, `confidence`
- `news_article_links`
  - `id`, `article_id`, `target_type`, `target_code`, `target_name`, `link_reason`

落地顺序建议：

1. 先做单一数据源接入和入库，保证能稳定增量同步。
2. 再做去重和股票映射，解决“同一条新闻多处转载”的问题。
3. 再补事件抽取，例如业绩、减持、停牌、并购、监管、产业政策。
4. 最后把新闻和龙虎榜、席位、个股关联起来，供图分析和大模型消费。

实现上的关键原则：

- 新闻原文和结构化标签分开存，避免后续重跑抽取时反复抓取。
- `entity_code` 统一使用股票代码、机构名标准名，避免图谱节点碎片化。
- 去重不要只靠 URL，至少同时保留 `hash(title + normalized_content)`。
- 不把新闻处理逻辑塞进抓取脚本，抓取和语义处理必须解耦。

已完成的工作：

1. ✅ 在 `infrastructure/data_sources/news/akshare_source.py` 里接入了 akshare 个股新闻（`stock_news_em`）和财联社快讯（`stock_news_main_cx`）。
2. ✅ `sync_news` 能真实抓回标题、正文、发布时间、原始链接，并支持按股票代码批量采集。
3. ✅ `domain/news/tagging.py` 已有股票代码正则映射和情绪/事件类型标注。
4. ✅ `NewsRepository` 支持按股票代码查询关联新闻（实体关联 + metadata 双路径）。
5. ✅ 统一前端新增「个股新闻」tab，支持股票卡片浏览、情绪筛选、新闻时间线详情。

接下来可以继续做的：

1. 在 `domain/news/tagging.py` 里补股票简称到代码的映射，而不只是正则命中股票代码。
2. 给 `news_articles` 增加增量同步策略，例如按发布时间窗口抓取。
3. 补一组最小测试数据，验证去重、标签和入库不重复。
4. 把新闻和龙虎榜数据联接，形成可解释事件上下文。

新闻方向建议按这个顺序落地：

1. ✅ 先只做一个稳定新闻源（akshare 已接入）。
2. ✅ 把抓取结果存稳，再做更复杂的实体识别。
3. ✅ 先完成"新闻 -> 股票"关联，再考虑"新闻 -> 席位/主题/事件"。
4. 等有稳定数据后，再把新闻接入图谱与大模型分析。

## 扩展路线二：图关系分析与挖掘

目标是从“龙虎榜席位-股票二部图”扩展到“股票-席位-新闻-事件-主题”的多类型关系图，为关系挖掘和解释分析打基础。

建议按下面的目录继续扩展：

```text
src/stockgraph/
├── domain/graph/
│   ├── models.py                # GraphNode、GraphEdge、Subgraph、Community
│   ├── builders.py              # 从龙虎榜/新闻/事件构图
│   └── metrics.py               # 中心性、共现强度、时间衰减
├── application/services/
│   ├── network_analysis.py      # 图构建与挖掘编排
│   └── graph_materialization.py # 图快照、导出、缓存
├── infrastructure/db/
│   └── schema.py                # graph_nodes、graph_edges、graph_snapshots
└── presentation/
    └── templates/               # 后续可接更强的图可视化页面
```

建议分三层建图：

1. 基础关系层
   - 席位 -> 股票：买入、卖出、净额、出现次数、时间区间
   - 新闻 -> 股票：提及、利好、利空、事件归因
2. 聚合关系层
   - 席位 -> 席位：共同参与同一股票、同日/多日共现
   - 股票 -> 股票：被同一席位连续操作、受同类新闻驱动
3. 分析结果层
   - 社区、核心节点、异动路径、主题簇、活跃资金链条

建议新增的表：

- `graph_nodes`
  - `node_id`, `node_type`, `node_key`, `node_name`, `attributes_json`
- `graph_edges`
  - `edge_id`, `source_node_id`, `target_node_id`, `edge_type`, `weight`, `trade_date`, `attributes_json`
- `graph_snapshots`
  - `snapshot_id`, `snapshot_date`, `snapshot_type`, `version`, `metadata_json`

建议先实现的分析能力：

1. 席位-股票二部图构建。
2. 席位共现图和股票共现图。
3. 节点活跃度、中心性、共现强度统计。
4. 时间窗口分析，例如近 5 日、10 日、20 日的关系演化。
5. 输出给前端和 LLM 的统一子图结构。

实现上的关键原则：

- 图分析服务不直接依赖 HTML 页面，页面只是消费者。
- 边要保留 `edge_type` 和时间信息，否则后续无法做路径解释和时序分析。
- 图谱节点要有稳定主键，例如 `seat:国泰海通上海江苏路`、`stock:000001`。
- 图计算结果和原始关系边分开存，避免每次页面打开都现场重算。

接下来具体要做什么：

1. 先把 `NetworkAnalysisService` 的时间窗口参数固定下来，例如近 5/10/20/60 日。
2. 给图快照补 `graph_materialization.py`，统一管理不同类型图的构建与缓存。
3. 在 `domain/graph/metrics.py` 里补加权度、时间衰减权重、共现强度标准化。
4. 引入新闻边后，扩展出 `news-stock`、`news-theme`、`theme-stock` 类型边。
5. 把图摘要结果做成稳定输出，供前端页面和 LLM 分析直接消费。

图分析方向建议按这个顺序落地：

1. 先把龙虎榜单一数据源图分析做好。
2. 再接新闻节点，不要一开始就做多模态大图。
3. 先做可解释的共现分析和中心性分析，再做社区发现和路径挖掘。
4. 等图谱质量稳定后，再把图谱子图交给大模型做解释和总结。

## 后续实施计划

建议按三个阶段推进，这样风险最低，也最容易持续看到结果。

### 第一阶段：把新闻接入做成可用能力 ✅ 已完成

目标：

- ✅ 至少一个真实新闻源可抓取（akshare 个股新闻 + 财联社快讯）
- ✅ 新闻能增量入库
- ✅ 新闻能关联到股票

已实现的文件：

- `src/stockgraph/infrastructure/data_sources/news/akshare_source.py` — akshare 个股新闻 + 财联社快讯数据源
- `src/stockgraph/application/services/news_ingestion.py` — 全局新闻 + 个股新闻同步服务
- `src/stockgraph/domain/news/tagging.py` — 股票代码正则映射、情绪/事件类型标注
- `src/stockgraph/infrastructure/db/repositories.py` — NewsRepository 新增按股票代码查询方法
- `src/stockgraph/presentation/templates/unified_app.py` — 新增「个股新闻」tab UI
- `src/stockgraph/application/services/unified_frontend.py` — 新增 stock_news 数据构建
- `src/stockgraph/cli/sync_news.py` — 支持 `--stock-codes`、`--stock-limit`、`--skip-stock-news` 参数

验收结果：

- ✅ `python3 scripts/sync_news.py --stock-codes "000001,600519" --stock-limit 10` 能新增真实新闻数据
- ✅ 数据库里 `news_articles / news_entities / news_article_links` 有内容
- ✅ 同一新闻重复同步不会重复插入（基于 hash 去重）
- ✅ 统一前端「个股新闻」tab 正确展示股票卡片、情绪分布、新闻时间线

### 第二阶段：把图分析做成稳定分析层

目标：

- 固化几个稳定的图快照类型
- 形成可重复执行的关系分析结果
- 给页面和后续 LLM 提供统一图摘要

要做的文件：

- `src/stockgraph/application/services/network_analysis.py`
- `src/stockgraph/domain/graph/builders.py`
- `src/stockgraph/domain/graph/metrics.py`
- `src/stockgraph/application/services/graph_materialization.py`

验收标准：

- `python3 scripts/build_graph_snapshots.py --persist` 能稳定生成多类图快照
- 数据库里 `graph_nodes / graph_edges / graph_snapshots` 有稳定结果
- 能输出某个时间窗口内的关键席位、关键股票、强共现关系

### 第三阶段：把新闻和图谱接到大模型分析 ✅ 基本完成

目标：

- 让大模型基于"龙虎榜 + 新闻 + 图谱摘要"输出解释分析
- 支持个股、席位、主题三个维度的自然语言分析

已实现：

- 统一前端「🤖 AI 分析」tab，支持配置兼容 OpenAI 的 API（Base URL / API Key / 模型名称）
- 后端 `_build_ai_analysis_data` 自动合并新闻和龙虎榜两个来源的股票上下文
- 前端直调 OpenAI 兼容 API，支持流式输出（SSE）
- 可自定义分析提示词，默认从资金面和消息面两个维度分析
- API 配置持久化到 localStorage

待扩展：

- `src/stockgraph/domain/llm/prompts.py` — 更多结构化提示词模板
- `src/stockgraph/domain/llm/contracts.py` — 分析结果结构化契约
- `src/stockgraph/application/services/llm_analysis.py` — 后端独立 LLM 分析服务
- 席位维度、主题维度的自然语言分析
- 图谱摘要接入分析上下文

## 推荐迭代顺序

如果按投入产出比排序，建议这样推进：

1. ✅ 先做新闻入库和股票映射。（已完成：akshare 个股新闻 + 财联社快讯，支持按股票代码查询）
2. ✅ 新闻与龙虎榜数据联接，形成可解释事件上下文。（已完成：AI 分析页面自动合并新闻+龙虎榜上下文）
3. 再做图构建和共现分析。
4. ✅ 接入大模型分析。（已完成：前端直调 OpenAI 兼容 API，支持流式输出，可配置 baseurl/key/model）
