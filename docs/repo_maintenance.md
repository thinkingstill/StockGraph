# StockGraph 仓库维护建议

本文档用于明确：**StockGraph 作为新的独立 repo 时，哪些内容建议提交到 Git，哪些内容只保留本地。**

## 1. 建议提交（push）到仓库的内容

这些属于源码、配置、文档或小体积参考资料，适合作为仓库的一部分长期维护：

- 根目录配置
  - `.gitignore`
  - `pyproject.toml`
  - `README.md`
  - `deploy_python_env.sh`
  - `dev_start.sh`
  - `run_daily_sync.sh`
- 文档
  - `docs/architecture.md`
  - `docs/repo_maintenance.md`
- 源代码
  - `scripts/`
  - `src/stockgraph/`
- 参考实现与参考资料
  - `source/*.py`
  - `source/*.html`
  - `data/reference/industry_mapping.json`
  - `data/reference/stock_basic_info.pkl`（如果你希望新 clone 后可直接运行，建议一并提交）

## 2. 建议仅本地保留的内容

这些内容要么是运行时缓存，要么是数据库、构建产物、静态页面产物，不适合频繁提交：

- Python 运行环境
  - `.venv/`
- Python 缓存 / 打包产物
  - `__pycache__/`
  - `*.pyc`
  - `*.egg-info/`
  - `build/`
  - `dist/`
- 数据库
  - `data/shared_state/*.db`
  - `source/*.db`
- 市场概览运行缓存
  - `data/market_overview/*.json`
- 前端生成产物
  - `outputs/index.html`
  - `outputs/html/*.html`
  - `outputs/market/*.html`
  - `outputs/app/index.html`
  - `outputs/app/data/*.json`
- 日志文件
  - `*.log`

## 3. 当前推荐的目录定位

### 源码层（应 push）

- `src/stockgraph/`
- `scripts/`
- `docs/`

### 参考资料层（通常应 push）

- `data/reference/`

### 运行时状态层（本地）

- `data/shared_state/`
- `data/market_overview/`

### 生成展示层（本地）

- `outputs/`

补充说明：

- `outputs/` 仍然是**运行时生成目录**，平时不需要提交 HTML / JSON 产物。
- 如果启用了 GitHub Pages，也依然推荐保持这一策略。
- 统一做法是：由 GitHub Actions 在 CI 中执行构建，再把 `outputs/` 作为 Pages artifact 发布。
- 因此仓库里只需要保留目录占位文件（如 `.gitkeep`）以及构建脚本，不需要把生成结果纳入版本管理。

### 原始参考实现层（按需 push）

- `source/`

`source/` 当前更像“迁移前参考代码归档”。如果你希望新 repo 更干净，可以后续只保留：

- `source/README.md`
- 少量关键参考脚本

而把已完全迁移、不会再回看的原始 HTML 或临时脚本逐步移除。

## 4. 推荐首次建仓方式

如果你准备把 `/home/wlh/StockGraph` 初始化成新的 GitHub 仓库，建议首批提交内容按下面顺序整理：

### 第一批：基础工程

- `README.md`
- `pyproject.toml`
- `.gitignore`
- `docs/`
- `scripts/`
- `src/stockgraph/`

### 第二批：必要参考数据

- `data/reference/industry_mapping.json`
- `data/reference/stock_basic_info.pkl`

### 第三批：参考实现归档（可选）

- `source/` 中仍有价值的脚本或页面模板

## 5. 一个实用判断标准

判断某个文件该不该 push，可以直接看它属于哪一类：

- **自己写的代码 / 配置 / 文档** → push
- **别人 clone 后运行必需的小体积参考资料** → push
- **每天会变的数据缓存** → 本地
- **数据库、HTML 生成结果、JSON 产物** → 本地
- **虚拟环境、缓存、日志** → 本地

## 6. 当前最推荐的 push 清单

最简洁也最实用的一套是：

- push：
  - `.gitignore`
  - `README.md`
  - `pyproject.toml`
  - `deploy_python_env.sh`
  - `dev_start.sh`
  - `run_daily_sync.sh`
  - `docs/`
  - `scripts/`
  - `src/stockgraph/`
  - `data/reference/industry_mapping.json`
  - `data/reference/stock_basic_info.pkl`
- 本地：
  - `.venv/`
  - `data/shared_state/*.db`
  - `data/market_overview/*.json`
  - `outputs/**`
  - `*.log`

## 7. GitHub Actions / Pages 场景下的额外建议

如果仓库已经同步到 GitHub，并准备启用自动运行与 GitHub Pages，推荐额外提交这些内容：

- `.github/workflows/pages.yml`
- `scripts/build_pages_site.py`
- `data/shared_state/.gitkeep`
- `outputs/.gitkeep`
- `outputs/app/.gitkeep`
- `outputs/app/data/.gitkeep`
- `outputs/html/.gitkeep`
- `outputs/market/.gitkeep`

这样做的目的：

- 让空目录结构在新 clone 后仍然存在
- 让 CI / Pages 有稳定的输出目录约定
- 保持“源码入库、生成物不入库”的仓库边界清晰

如果你后续希望仓库更“开源友好”，下一步建议再补一个：

- `scripts/bootstrap_reference_data.py` 或类似脚本

用于自动生成 `data/reference/stock_basic_info.pkl`，这样未来就可以把这个二进制文件也从仓库里移除。