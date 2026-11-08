# StockGraph 代码审计与修复报告

审计对象：`github.com/thinkingstill/StockGraph`（main 分支，2026-11 快照）
审计方式：全量读源码 + 逐条实测接口 + 双后端一致性回归

> 结论先说：这个仓库的**架构分层是干净的**，问题不在设计，而在**数据链路的地基**——
> 三个新闻源是空壳、龙虎榜抓不到时会**编造数据**、图快照的日期语义是错的、
> 没有任何测试、行情源被封就没有备用方案。这些都不是"待优化"，是会直接毁掉数据可信度的硬伤。
>
> 下面每一条都标注了「原实现 → 现象 → 修复 → 验证」。

---

## 一、严重缺陷（会产生错误数据 / 静默失效）

### 1.1 三个新闻源全是空壳，返回空批次

| 项 | 内容 |
| --- | --- |
| 位置 | `infrastructure/data_sources/news/{eastmoney,cls,rss}.py` |
| 原实现 | `fetch()` 直接 `return NewsBatch(source=self.name, articles=[])`，无任何网络请求 |
| 现象 | `sync_news.py` 每天"成功完成"，库里新闻数为 0；`NewsIngestionService` 的日志全是"新增 0 条"，看起来像"今天没新闻" |
| 影响 | 新闻 tab 空白、AI 分析拿不到消息面、`news_entities` 永远是 0 行。**这是静默失效，最难被发现** |

**修复**：三个源全部重写成真实抓取。

- `eastmoney.py`：东方财富 7×24 快讯，`np-weblist.eastmoney.com/comm/web/getFastNewsList`，游标 `sortEnd` 持久化分页
- `cls.py`：财联社电报 `www.cls.cn/v1/roll/get_roll_list`，实现了签名 `sign = md5(sha1(sorted_query))`，游标 `last_time`
- `rss.py`：标准库 `xml.etree` 解析 RSS 2.0 / Atom 1.0，源地址由 `STOCKGRAPH_RSS_FEEDS` 配置
- 新增 `_common.py`：`PoliteSession` 全局限速（默认 0.8s 间隔）+ `normalize_em_stock_list`（按市场前缀 `0`/`1` 过滤港股与板块）

**验证**：实测财联社与东财快讯各返回 5 条真实电报；2026 全年回补中单页 50 条稳定拿到。

---

### 1.2 龙虎榜抓不到席位时**凭空编造**数据

| 项 | 内容 |
| --- | --- |
| 位置 | `infrastructure/data_sources/dragon_tiger/eastmoney.py` |
| 原实现 | `_build_mock_operations()` / `_mock_from_change()`：接口没返回席位明细时，**自己编造**「知名游资席位」「机构专用」「深股通专用」以及对应金额 |
| 现象 | 库里的席位数据真假混杂，且无法区分。假数据会顺着 图构建 → PageRank → 前端 → AI 分析 一路传下去 |
| 影响 | **整个项目的分析结论都建立在部分伪造的数据上**。这是最严重的一条 |

**修复**：

- 彻底删除 `_build_mock_operations`、`_mock_from_change`
- 删除同样依赖第三方付费接口且继续造假的 `StockApiFallbackSource`
- 新增 `fetch_seat_details_bulk(trade_date)`：一次请求同时拉 `RPT_BILLBOARD_DAILYDETAILSBUY` 和 `RPT_BILLBOARD_DAILYDETAILSSELL`，按股票聚合，**一次拿全市场席位**
- 拿不到就留空并记数据质量告警，**不再编造**

**验证**：`fetch_seat_details_bulk('2026-11-06')` → 63 只股票 / 569 条席位；全年 203 个交易日共 65,031 条席位、2,458 只股票，与行情交易日历完全对齐。

---

### 1.3 新闻股票代码正则在中文语境下失效

| 项 | 内容 |
| --- | --- |
| 位置 | `domain/news/tagging.py` |
| 原实现 | `re.compile(r"\b(\d{6})\b")` |
| 现象 | 中文是 Unicode 单词字符，`600519股今日涨停` 里 `600519` 后面紧跟 `股`，`\b` 不成立 → **匹配失败** |
| 影响 | 中文财经新闻里的股票代码几乎全部漏识别 |

**修复**：改为上下文断言

```python
STOCK_CODE_PATTERN = re.compile(r"(?<!\d)((?:00|30|60|68|43|83|87|92)\d{4})(?!\d)")
```

同时补齐**公司简称识别**（原实现完全没有）：从 `data/reference/all_stock_codes.json` 建简称索引，滑动窗口匹配，只接受长度 ≥ 3 的简称（2 字简称误报率过高）。实体置信度分三档：数据源标注 `1.0` > 文本命中代码 `0.9` > 文本命中简称 `0.75`。

**验证**：`600519股今日涨停` 正确提取；`宁德时代宣布扩产` 这类纯文字新闻能关联到 `300750`。

---

### 1.4 行情只依赖东财 `push2`，被封即全盘停摆

| 项 | 内容 |
| --- | --- |
| 现象 | 本机实测 `push2.eastmoney.com` 返回空响应（`RemoteDisconnected`），`akshare` 的 `stock_zh_a_spot_em` / `stock_zh_a_hist` 全部失败 |
| 原实现 | 没有任何备用源，也没有历史回补脚本 → 历史行情永远补不上 |

**修复**：新增 `scripts/backfill_market_daily.py`，改用新浪历史 K 线

```
money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData
```

按 `sh/sz/bj` 前缀逐股拉日线，再按交易日聚合入库。

**口径如实标注**（不掩饰估算）：
- 开高低收、成交量来自新浪日线
- 新浪日线**不含成交额**，`成交额` 用 `成交量 × (最高+最低+收盘)/3` 估算，字段标 `成交额估算=true`
- 雪球热度接口按 IP 封锁（403），历史热度**无法回补**，`hot_daily_*` 不做伪造，报告里标 `hot_data_available: false`

**验证**：5,524 只股票 / 203 个交易日 / 1,114,379 行 / 失败 0 只，每日覆盖 5,439~5,513 只。

---

### 1.5 `akshare` 个股新闻在 pandas 3.0 下彻底不可用

| 项 | 内容 |
| --- | --- |
| 现象 | `ak.stock_news_em(symbol="600519")` 抛 `ArrowInvalid: Invalid regular expression: invalid escape sequence: \u` |
| 原因 | pandas 3.0 / pyarrow 的字符串正则引擎不再接受 `\u` 转义 |
| 影响 | `AkShareStockNewsSource` 静默返回空，个股新闻永远是 0 条 |

**修复**：新增 `EastMoneyStockNewsSource`（`news/eastmoney_search.py`）直连东财搜索底层接口，不经过 pandas。
关键坑：普通 `requests` 请求返回 `passportWeb` 跳转页（`hitsTotal=1`），必须用 `curl_cffi` + `impersonate="chrome"` 伪造浏览器 TLS 指纹才能拿到 `hitsTotal=552` 的正常结果。

`NewsIngestionService.sync_stock_news()` 改为「自研源优先、akshare 兜底」。

**验证**：`600519` 拉 2 页返回 40 条真实新闻（含「贵州茅台：第三季度净利润199.51亿元 同比增长3.78%」）。

---

## 二、架构缺陷

### 2.1 图快照日期语义是错的（会毁掉所有时序分析）

| 项 | 内容 |
| --- | --- |
| 位置 | `application/services/network_analysis.py` |
| 原实现 | `build_stock_seat_projection(start_date, end_date)` 把**整个区间**的记录塞进一个以 `end_date` 命名的快照 |
| 现象 | 传一整年会得到一张「名叫 `2026-11-06`、但边上带着 `2026-01-05`~`2026-11-06` 全部交易」的图 |
| 影响 | `fetch_edges(type, date)` 的语义完全失效；跨快照路径分析、社区演化、时间窗口对比全部不可信 |

**修复**：
- `build_snapshot(builder_name, snapshot_date)` 严格单日
- `build_range(...)` 按交易日逐日构建，支持 `skip_existing` 断点续跑
- 传入区间给单快照接口会**抛 ValueError**，而不是静默混数据
- CLI 重写：`--date` 单日 / `--start-date + --end-date` 区间 / `--types` 选类型 / `--rebuild` 强制重建

**验证**：609 张快照（203 天 × 3 类），`snapshot_date` 与 `edge.trade_date` 100% 一致。

### 2.2 投影图会生成自环边

| 项 | 内容 |
| --- | --- |
| 现象 | 同一席位在同一只股票上常同时有买入和卖出两条记录，投影时把自己和自己配对 → `seat:X -> seat:X` |
| 规模 | 12,625 条自环（占 `graph_edges` 的 2.8%） |
| 影响 | 自环在 Cypher 里是**零长度路径**不是边，导致 FalkorDB 与 SQLite 边数对不上；分析上也是纯噪声 |

**修复**：`build_trader_seat_projection` / `build_stock_stock_projection` 先按实体去重再配对（同实体多条记录取最大金额）；存储层（两个后端）再兜底丢弃自环。

**验证**：重建后自环 0 条。

### 2.3 `GraphRepository` 只是半截委托层

原实现只委托了 `initialize_database` / `save_snapshot`，上层想调 `list_snapshots` 就 AttributeError。
**修复**：补齐 `GraphStore` 协议全部方法的委托，保证「一键切换后端」对所有调用路径生效。

### 2.4 没有测试

原仓库 `pyproject.toml` 无 dev 依赖，`tests/` 目录不存在，没有一个 `test_*.py`。所有改动只能靠手工跑脚本验证。

**修复**：新增 7 个测试文件、**78 个用例**，覆盖图算法数值正确性、SQLite 后端幂等与孤立节点清理、自环防护、配置优先级、新闻实体识别、数据源签名与单位换算、SQLite 并发模式。

```bash
pip install -e ".[dev]"
pytest          # 62 passed
```

### 2.5 数据库没有并发能力

原实现用默认 `delete` 日志模式，写事务独占整库。实测在回补 609 张图快照的同时采集新闻，直接 `database is locked` 中断回补。

**修复**：`connection.py` 默认 WAL + `busy_timeout=10s` + `synchronous=NORMAL`，并支持 `STOCKGRAPH_DB_PATH` 覆盖（便于测试隔离与多实例部署）。同时新增 `STOCKGRAPH_SQLITE_WAL=0` 逃生开关。

### 2.6 `domain/llm/` 是空壳

`__init__.py` 只有一行注释 `"""Reserved for LLM analysis contracts and prompts."""`，`README.md` 里规划的 `prompts.py` / `contracts.py` / `llm_analysis.py` 全都不存在。LLM 分析完全靠前端直调 OpenAI 兼容接口拼字符串 —— 提示词无法版本化、无法测试、无法复用。

**状态**：**未实现**（见第四章）。

### 2.7 `Community` / `Subgraph` 定义了没人用

`domain/graph/models.py` 定义了这两个数据结构，`GraphSnapshot.communities` 也留了字段，但全仓库无任何地方填充或消费。

**已部分修复**：新增图算法层（PageRank / 标签传播社区发现 / BFS / 连通分量），社区发现结果可以通过 `graph_query.py communities` 拿到；`Community` 模型本身仍未与算法层打通（算法层返回 dict，未构造 `Community` 对象）。

### 2.8 图分析结果不确定：同分节点名次会漂移

`pagerank` 的排序键只有 `-score`，`top_nodes` 只有 `weighted_degree DESC, degree DESC`。
营业部重名极常见，两个节点权重精确相等到小数点后 8 位时，名次取决于后端返回顺序。

实测：`seat_stock@2026-11-06` 的 PageRank 第 40 名，SQLite 给"国泰海通…江苏路证券营业部"，
FalkorDB 给"东方证券…曹安公路证券营业部"，**两者分数完全相同**。
集合一致、名次不一致，写进报告就是两个结论。

修复：全部排序补上 `node_id` 作为确定性次级键（`analytics.pagerank`、两侧 `top_nodes`、两侧 `neighbors`）。

### 2.9 FalkorDB 查询结果被静默截断在 1 万行

FalkorDB 单次查询默认 `RESULTSET_SIZE = 10000`，超出部分**直接丢弃，不报错**。

`_edges_of_type()` 用于取某类型全部历史边，`seat_stock` 实际有 **75,960 条**，只拿到 10,000 条。
后果：跨快照最短路只在 13% 的边上搜索——
`seat:深股通专用 -> stock:002929` 明明有直接边，FalkorDB 却返回 `found: false`。

修复：新增 `_query_all()`，用 `SKIP/LIMIT` 自动翻页取全量（页大小 5,000，5 万行防御上限），
`_edges_of_type` 改用它。修复后该类型边数从 10,000 恢复到 75,960。

---

## 三、FalkorDB 后端（新增能力）

用户要求：为 graph 部分提供 FalkorDB 作为备选，且必须能**一键切换**。

原有实现把图读写直接写死在 `GraphRepository` 里对 SQLite 三张表做 SQL，没有任何抽象层。

**新增 `infrastructure/graph/` 抽象层**：

| 文件 | 职责 |
| --- | --- |
| `base.py` | `GraphStore` 协议（18 个方法）、`SnapshotKey`、`GraphStoreStats` |
| `algorithms.py` | 纯标准库图算法：加权 PageRank、标签传播社区发现、BFS 最短路、连通分量、度中心性 |
| `analytics.py` | `GraphAnalyticsMixin`：基于 `fetch_edges()` + `node_names()` 提供分析能力，两后端共用 |
| `sqlite_store.py` | SQLite 实现 |
| `falkordb_store.py` | FalkorDB 实现（Cypher） |
| `config.py` | 配置解析：环境变量 > `config/graph_backend.json` > 默认 `sqlite` |
| `factory.py` | `create_graph_store()` —— 全项目唯一图入口 |

配套：`scripts/graph_backend.py`（status/ping/switch/migrate/reset）、`scripts/graph_query.py`（stats/top/pagerank/communities/neighbors/path）、`docker-compose.yml`、`scripts/falkordb_up.sh`、`docs/graph_backend.md`。

**一键切换**：

```bash
python scripts/graph_backend.py switch falkordb --migrate   # 切过去并迁移全部历史快照
python scripts/graph_backend.py switch sqlite               # 切回来
```

### 一致性验证中发现并修掉的三个真实缺陷

这部分值得单独说，因为都是**只有真正跑起来才会暴露**的问题：

**① 关系类型清洗导致买入/卖出边被合并**

`sanitize_rel_type` 把中文替换成 `_`，于是 `seat_stock_买` 和 `seat_stock_卖` 都变成 `SEAT_STOCK`，同一对节点的买入/卖出两条边在 `MERGE` 时撞成一条 —— **609 张快照少了 16,075 条边**。

修复：检测到清洗过程中有信息损失时，追加原始值的 sha1 前 8 位后缀。纯 ASCII 类型仍保持可读（`SEAT_SEAT_COOCCURRENCE`），含中文的变成 `SEAT_STOCK_401e3f19`。

**② 邻居查询与快照列表在大图上超时**

`OPTIONAL MATCH ()-[r {snapshot_key: s.snapshot_key}]->()` 对 609 个快照轮询全图 44 万条边，**几分钟都跑不完**。而且 FalkorDB **不支持无类型关系索引**（`FOR ()-[r]-()` 语法直接报错），没法靠建索引解决。

修复：
- `list_snapshots` 改为「一次全边聚合 + 字典左连接」，**0.55 秒**
- `neighbors` 把 `snapshot_type` 条件下推进关系模式剪枝，**33 秒 → 0.01 秒**
- 只对已知固定类型建关系索引

**③ 按类型查最短路径只看了最新一天**

FalkorDB 侧取 `list_snapshots()[0]`（最新快照）的边做 BFS，而 SQLite 是扫该类型**全部**快照 → 语义不一致。改为新增 `_edges_of_type()` 取全部，与 SQLite 对齐。同时把路径边类型的选择改为「取权重最大的那条边」，消除遍历顺序带来的不确定性。

### 最终一致性结果

609 张快照、7,967 个节点、443,456 条边，两个后端逐项对比：

| 检查项 | 结果 |
| --- | --- |
| `snapshot_stats` | 一致 |
| `top_nodes`（加权度） | 一致 |
| `pagerank`（8 位小数） | 一致 |
| `communities`（含成员与总权重） | 一致 |
| `neighbors` | 一致 |
| `shortest_path`（同类型 / 跨快照） | 一致 |
| `list_snapshots`（逐快照边数） | 一致 |
| 节点数 / 边数 / 快照数 | 7,967 / 443,456 / 609，全部一致 |

分析算法**刻意用标准库实现**、放在两个后端之外，共产出同一份数值 —— 图算法的浮点累加顺序与并行归约差异足以让同一张图在两个库里给出不同排名。

---

## 四、仍未实现 / 后续建议

诚实地列出来，这些**没有做**：

| 项 | 状态 | 说明 |
| --- | --- | --- |
| `domain/llm/` 完整实现 | 未做 | 提示词模板、结构化契约、后端 LLM 服务仍缺失。当前 AI 分析靠前端直调，提示词无法版本化 |
| `Community` 模型与算法层打通 | 未做 | 社区发现返回 dict，没有构造 `Community` 对象写回 `GraphSnapshot.communities` |
| 雪球热度历史回补 | 无法做 | 接口按 IP 封锁（403），不做伪造 |
| 新闻去重语义 | 偏弱 | 仅按标题 hash 去重；同一事件不同媒体转载仍会重复入库 |
| 席位别名归一 | 未做 | 「机构专用」「深股通专用」是交易所汇总席位，不是真实营业部；营业部改名无映射表 |
| 前端图谱可视化 | 未做 | `graph_query.py` 只有 CLI 输出，没接页面 |
| CI 配置 | 未做 | 仓库有 GitHub Actions 定时任务，但没有跑 `pytest` 的 workflow |

建议优先级：**① CI 跑测试**（防止再次退化）→ **② 席位别名表**（直接影响图质量）→ **③ LLM 契约层** → **④ 前端图谱**。

---

## 五、2026 年数据回补结果

| 数据集 | 覆盖 | 规模 | 备注 |
| --- | --- | --- | --- |
| 日行情快照 | 2026-01-05 ~ 2026-11-06，**203/203 个交易日** | 1,114,395 行 / 5,528 只股票 | 每日覆盖 5,439~5,513 只；成交额为估算值并已标记 |
| 龙虎榜汇总 | 同上，**203/203** | 9,137 条 / 2,660 只股票 | 19 个"失败"日期经核对全部为法定节假日（元旦/春节/清明/劳动/端午/中秋/国庆），非缺口 |
| 席位明细 | 同上 | 75,960 条 | 一次请求拿全市场买卖席位 |
| 图快照 | 同上 | 609 张（203 天 × 3 类）/ 443,456 条边 | 席位-股票二部图、席位共现、股票共现；自环 0 条 |
| 新闻 | 2025-12-31 ~ 2026-11-08，**2026 年 12 个月全覆盖** | **336,891 条** / 286,351 个实体 / 关联 6,484 只股票 | 东财快讯 165,335 + 财联社 148,436 + 个股新闻 23,120 |

新闻月度分布（分布均匀，说明不是只抓到某几段）：

```
2026-01  29,793    2026-05  28,935    2026-09  36,188
2026-02  21,522    2026-06  33,141    2026-10  40,585
2026-03  30,902    2026-07  36,702    2026-11  11,974（截至 11-08）
2026-04  32,420    2026-08  34,592    2025-12     137（边界）
```

日粒度也正常：工作日 1,100~1,250 条、周末 300~580 条，符合财经资讯发布规律。

数据来源全部是真实接口，**没有任何一处是生成的假数据**。估算字段（成交额）与不可得字段（历史热度）都在数据里显式标注。

可用 `python scripts/report_completeness.py` 随时重新核验，输出含 `backfill_complete` 布尔值与缺口日期列表。

### 回补过程中修掉的两个工程缺陷

**① 断点续传是假的**

`backfill_news.py` 定义了 `earliest_published_at()` 却从未调用。后果有两层：

- 每次中断重启都从最新开始翻，实测白跑 960 页 / 约 12 分钟才回到断点
- 更糟的是 `if inserted == 0 and pages > 3: break` —— 重跑时前几页全是重复数据，
  第 4 页就判定「已覆盖」直接退出，**历史永远补不完**

修复：新增 `resume_cursor()`，把库里该来源最早一篇的发布时间反推成游标
（财联社 `last_time` 是秒、东财 `sortEnd` 是微秒，用 `CURSOR_SCALE` 区分），
启动时 `set_cursor()` 接上断点；「无新增」阈值从 3 页放宽到连续 30 页。

**② 单页容量和限速把吞吐卡死了 16 倍**

实测接口上限：东财 `pageSize` 支持 200（50 → 200 即 4 倍）、财联社 `rn` 上限 50。
配合 `STOCKGRAPH_REQUEST_DELAY_SECONDS=0.25` 与 `--sleep 0`，单页耗时从 1.0 秒降到 0.4 秒。

| 源 | 修复前 | 修复后 |
| --- | --- | --- |
| 东财快讯 | 50 条/页，1.0 秒/页 | 200 条/页，0.4 秒/页 |
| 财联社 | 50 条/页（2 次请求凑 50） | 50 条/页，1 次请求 |

结果：东财 **3 分钟补完 2026 全年**（575 页），财联社 **9 分 48 秒**（2,300 页）。

### 顺带修掉的前端构建 N+1

`_build_stock_news_data()` 原实现对库里每只有新闻的股票各调一次 `query_news_by_stock()`，
该方法内部是「实体 JOIN + `metadata_json LIKE '%code%'` 全表扫描」两次查询。
新闻 246 条时无感，涨到 33 万条 / 6,000+ 只股票后，**构建 3 分半仍未跑完**。

修复：新增 `query_news_grouped_by_stock()`，用一条带 `ROW_NUMBER() OVER (PARTITION BY ...)`
的 SQL 完成「每只股票取最近 N 条」，构建耗时 **65 秒**。已加测试断言只建立 1 次连接，防止 N+1 回归。

---

## 五、收尾阶段新发现的两个缺陷（自伤型）

这两个不是上游的锅，是本次改动引入的，记录在此以免重犯。

### 5.1 天数截取被当成"数据全集"回写，污染了源文件

为压住全 A 超图与城市气泡的产物体积（203 个交易日 × 5500 只股票 ≈ 900MB，
构建时直接被系统 SIGKILL），新增了 `_limited_stock_files()`：两个重型模块只读最近 N 天。

问题出在**它在回补阶段被当成了数据来源**。结果 `stock_daily_20261103~20261106.json`
从 1.7MB / 5500 行被覆盖成 1.3KB / 4 行。

**真正的危险不是文件变小，而是没有任何东西报错。** 四个模块同时静默失真：

| 模块 | 污染后的表现 |
| --- | --- |
| 全 A 超图 | 每天 16 个节点（正常 6,099） |
| 城市气泡 | 290 个城市塌缩成 1 个 |
| 行业强弱 | 87 个行业塌缩成 3 个、5508 只股票塌缩成 4 只 |
| 行情日历 | "行业冠军"是 4 只股票里的银行 |

修复：
- 从 `market_daily_snapshots` 表的 `raw_json` 字段原样还原 4 个文件（每日 5506~5508 行，与数据库逐行一致）
- `_limited_stock_files()` 增加**完整性闸门**：逐文件校验行数，低于 `MIN_STOCKS_PER_DAY = 3000` 即 WARNING 告警并点名文件
- `tests/test_frontend_guard.py` 覆盖：天数截取、`0` 表示不限、残缺触发告警、完整不误报

### 5.2 行业日历把"涨跌幅累加和"当成了"行业涨幅"

`_build_market_calendar_data()` 里 `total_change_pct` 是行业内所有成分股涨跌幅的**累加**，
却被直接当作行业涨幅输出，还用它排名。于是一个 100 只股票的行业能报出 `+65.78%`，
最差行业报出 `-894.45%` —— 数字荒唐到一眼能看出来，但它就那样安静地躺在产物里。

修复：按成分股数量取均值，并在输出中新增 `top_industry_stock_count` / `bottom_industry_stock_count`，
让前端可以显示"该行业由多少只股票构成"。

修复后全 203 个交易日的行业涨跌幅落回 **+0.27% ~ +10.96%** 与 **-10.81% ~ +0.32%**，
符合 A 股 ±10%/±20% 涨跌停的物理约束（行业均值必然落在个股涨跌停区间内）。

### 5.3 行业强弱榜单同样拿"累加和"当涨幅（前端）

同 5.2 的根因，但发生在**前端**：`aggregateIndustryRange()` 用 `total_change_pct` 排序并画柱状图。

后果比日历更明显——横轴范围被拉到 **-1000 ~ 0** 和 **-20 ~ 80**，
"总涨跌幅"列出现 `65.78%`、`41.49%` 这种数字，整张图基本不可读。

修复：榜单与柱状图改用**平均涨跌幅**；跨多日时把每日均值累加成"区间累计涨跌幅"
（单日等价于当日均值，多日等价于区间累计）。表头从"平均涨跌幅/总涨跌幅"
改为"日均涨跌幅/区间累计涨跌幅"，并在横轴标注单位。
修复后横轴回到 **-1 ~ 1.5** 与 **-5 ~ 0**，符合 A 股涨跌停约束。

---

## 六、浏览器端实测结果

用 Playwright 加载 `outputs/app/index.html`，逐模块切换验证（不只看 JSON 文件是否存在）：

| 模块 | 结果 |
| --- | --- |
| 龙虎榜明细查询 | 正常，2026-11-06：35 只股票 / 125 席位 / 289 条记录 |
| 龙虎榜关系网 | 正常 |
| 市场热度（3D） | **已修**。见 5.4，无 WebGL 时降级为 2D 气泡图 |
| 全 A 图谱 | 正常，398 节点 / 1,619 条边，力导向图正常 |
| 城市气泡 | 正常，290 城 / 5,507 家公司，北京 28.07 万亿居首 |
| 强弱排行 | 修复后正常，87 个行业 |
| 行业日历 | 正常，2026 全年 203 个交易日 / 48 个活跃行业 |
| 智能分析 | 正常 |
| 页面整体 | 9/9 模块清单加载成功，无 fatal pageerror |

### 5.4 3D 模块在无 WebGL 环境下整个崩掉

`echarts-gl` 在没有 WebGL 的环境（虚拟机、远程桌面、旧显卡、企业策略禁用）下不会优雅降级，
而是在 `addView` 内部抛 `Cannot read properties of undefined (reading 'indexOf')`，
并连带触发 `clearColor` 空引用，最终整个"3D 热度"页面**变成空白**，只有控制台有动静。

排查过程值得一提：先怀疑是 `echarts@5` 浮动标签解析到最新版导致版本不匹配，
锁了 5 个版本组合（含 `echarts@5.4.3 + gl@2.0.9`）全部复现，才确认是 WebGL 缺失而非版本问题。

修复：
- 新增 `webgl3dSupported()` 能力探测（缓存结果，`webgl2` → `webgl` → `experimental-webgl`）
- 不可用时渲染 **2D 气泡散点图**，保留 X/Y/颜色(Z)/大小(成交热度) 全部语义，并在图顶部标注降级原因
- 双保险：即使探测通过，`setOption` 运行期抛错也自动回落 2D（页面顶部提示 + 控制台 warn）
- 2D 也失败才 `chart.clear()`，绝不留白屏

### 5.5 前端冒烟测试固化

`scripts/smoke_frontend.py`：起临时静态服务 → 真实 Chromium 逐模块切换 → 断言
canvas 尺寸、异常文案、`pageerror`，并**读取 echarts 实例的 option 校验图表数值合理性**
（行业涨跌幅必须在 ±30% 内、城市加权涨跌幅同理、日历区间累计值同理）。

后者是关键：本轮验证过脚本确实能抓到缺陷——把行业图表数据人为放大 100 倍后，
脚本报 `[FAIL] 数值校验: 行业强弱 最大绝对值=113.42 上限=30`；恢复后回到 12/12 通过。

---

## 七、双后端一致性复测（重建 FalkorDB 后）

重建容器 → `migrate --to falkordb` 迁移 609 张快照 → 运行
`scripts/graph_backend_consistency.py`（本次新增，把此前临时会话里的比对固化成脚本）。

| 项 | 结果 |
| --- | --- |
| 规模 | 7,967 节点 / 443,456 边 / 609 快照，两侧相同 |
| 比对范围 | 4 张样本快照 × 10 项检查（stats / list_snapshots / snapshot_stats / fetch_edges / node_names / top_nodes / degree_centrality / pagerank / communities / components / neighbors / shortest_path） |
| 最终结果 | **42/42 全部一致**（浮点按 8 位小数比较） |

比对时忽略 `backend`（后端名本就不同）与 `created_at`（SQLite 入库时间，FalkorDB 无对应概念），
其余字段一律严格比较。

第一轮跑出 7 处不一致，全部是真问题，逐项修完才收敛到 42/42：

| # | 现象 | 根因 |
| --- | --- | --- |
| 1 | `shortest_path` 一侧 `found:false` | RESULTSET_SIZE 1 万行截断（§2.9） |
| 2 | `neighbors` 同权重顺序不同 | 缺 `node_id` 次级排序键（§2.8） |
| 3 | `pagerank` 第 40 名互换 | 同上，同分漂移（§2.8） |
| 4 | `stats` / `list_snapshots` 不等 | 元数据字段，非语义差异，比对脚本忽略 |

---

## 八、日更流程实跑验证（含一个新的日期格式缺陷）

用 `TARGET_DATE=2026-11-06` 全链路实跑 `run_daily_sync.sh`，
覆盖：龙虎榜 → 仪表盘 → 新闻（4 源）→ 图快照 → 市场概览 → 统一前端 → 开发索引。

**链路本身跑通、零任务失败**（`all selected tasks completed successfully`），
但暴露了一个**日期格式分裂**的真实缺陷：

### 8.1 日更写入的 trade_date 与历史回补格式不一致

`AkshareMarketOverviewSource.get_exchange_date()` 返回"报告时间"是 `20261106`（无横线），
而 `backfill_market_daily.py` 写库用 `2026-11-06`（带横线）。
`sync_market_overview` 没有做规范化，直接拿无横线日期当主键 `INSERT OR REPLACE`。

后果：同一天在 `market_daily_snapshots` 里**分裂成两批**——
实测 111 万行带横线（历史）vs 5,578 行无横线（本次日更）。
`INSERT OR REPLACE` 主键不冲突，所以两边都活着，任何按日期聚合的查询都会漏掉一半。

修复：
- `MarketOverviewService._normalize_trade_date()`：统一把 8 位数字归一成 `YYYY-MM-DD`
- **文件名**用紧凑 `YYYYMMDD`（与回补脚本 `emit_json` 约定一致），**数据库键**用带横线 `YYYY-MM-DD`（与历史 111 万行一致）——两套约定显式分离
- 清理存量脏数据：把无横线的 5,578 行中 71 只新股（新浪实时源额外拿到的）合并进带横线日期，删除全部无横线残留行
- 新增 `tests/test_market_overview_date.py`（7 个用例）钉死规范化与分离逻辑

修复后重跑日更：`trade_date` 正确写入 `2026-11-06`，无横线残留归零，
全表 203 天日期格式统一。总行数 1,114,466（原 1,114,395 + 71 只新股）。

**附带发现**：新浪实时源（`sina_all`）作为首选数据源，拿不到行业分类
（71 只新股中 65 只行业"未知"），且会覆盖之前带 `数据源: sina_kline` 字段的回补文件。
这是数据源优先级带来的已知取舍，已在日志里标注，不属于本次缺陷。

---

## 附：本次改动清单

**新增**

```
src/stockgraph/infrastructure/graph/{__init__,base,algorithms,analytics,config,factory,sqlite_store,falkordb_store}.py
src/stockgraph/cli/graph_backend.py
src/stockgraph/cli/graph_query.py
src/stockgraph/infrastructure/data_sources/news/{_common,eastmoney_search}.py
scripts/{graph_backend,graph_query,graph_backend_consistency,smoke_frontend,backfill_dragon_tiger,backfill_market_daily,backfill_news,falkordb_up.sh}
tests/{test_graph_algorithms,test_graph_sqlite_store,test_graph_determinism,test_news_tagging,test_data_sources,test_db_connection,test_news_repository,test_frontend_guard,test_market_overview_date}.py
config/graph_backend.json
docker-compose.yml
docs/{AUDIT,graph_backend}.md
```

**重写**

```
infrastructure/data_sources/news/{eastmoney,cls,rss}.py        空壳 → 真实抓取
infrastructure/data_sources/dragon_tiger/eastmoney.py          删除造假逻辑
domain/news/tagging.py                                         修正则 + 加简称识别
application/services/{network_analysis,news_ingestion}.py      按日切分 + 源优先级
cli/build_graph_snapshots.py                                   单日/区间
infrastructure/db/{connection,repositories}.py                 WAL + 补齐委托
domain/graph/builders.py                                       去自环
pyproject.toml                                                 可选依赖 + pytest 配置
```
