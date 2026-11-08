# 图数据库后端：SQLite / FalkorDB 一键切换

StockGraph 的关系图默认存在 SQLite 的 `graph_nodes / graph_edges / graph_snapshots` 三张表里。
如果要做跨快照的路径挖掘、或者把图接到别的分析工具上，可以切到 [FalkorDB](https://github.com/FalkorDB/falkordb)——
一个基于 Redis 模块的图数据库，用 Cypher 查询，内存计算，启动成本很低。

两种后端的**分析结果完全一致**，切换只改一个配置项，业务代码不用动。

---

## 1. 一句话切换

```bash
# 看当前用哪个后端
python scripts/graph_backend.py status

# 切到 FalkorDB，并把 SQLite 里已有的图快照全量复制过去
python scripts/graph_backend.py switch falkordb --migrate

# 切回 SQLite
python scripts/graph_backend.py switch sqlite
```

切换后**立即生效**，不需要重启服务：所有图读写都走 `create_graph_store()`，
它每次都按配置解析后端（进程内做了缓存，`switch` 会自动清缓存）。

---

## 2. 先把 FalkorDB 跑起来

### 方式 A：Docker Compose（推荐）

```bash
docker compose up -d
docker compose ps          # 等 healthcheck 变成 healthy
```

Redis 协议在 `6379`，FalkorDB Browser 在 `http://localhost:3000`。

### 方式 B：一条 Docker 命令

```bash
docker run -d --name stockgraph-falkordb \
  -p 6379:6379 -p 3000:3000 \
  -v stockgraph-falkordb-data:/var/lib/falkordb/data \
  falkordb/falkordb:latest
```

### 方式 C：仓库自带脚本

```bash
./scripts/falkordb_up.sh          # 启动并等待就绪
./scripts/falkordb_up.sh status   # 看状态
./scripts/falkordb_up.sh stop     # 停止并删除
```

### 方式 D：不用 Docker

参考[官方安装文档](https://docs.falkordb.com/getting-started/installation.html)装二进制，
然后按默认端口 `6379` 启动即可，StockGraph 侧的配置不用改。

---

## 3. 配置项

优先级：**环境变量 > `config/graph_backend.json` > 默认值（sqlite）**。

配置文件长这样（仓库里已带一份默认值）：

```json
{
  "backend": "sqlite",
  "falkordb": {
    "host": "127.0.0.1",
    "port": 6379,
    "graph_name": "stockgraph",
    "username": "",
    "password": "",
    "timeout": 5
  },
  "fallback_to_sqlite": true
}
```

对应的环境变量：

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `STOCKGRAPH_GRAPH_BACKEND` | 强制指定后端：`sqlite` / `falkordb` / `auto` | 读配置文件 |
| `STOCKGRAPH_FALKORDB_HOST` | FalkorDB 主机 | `127.0.0.1` |
| `STOCKGRAPH_FALKORDB_PORT` | 端口 | `6379` |
| `STOCKGRAPH_FALKORDB_GRAPH` | 图名（相当于 Redis key 前缀） | `stockgraph` |
| `STOCKGRAPH_FALKORDB_USERNAME` | ACL 用户名（可选） | 空 |
| `STOCKGRAPH_FALKORDB_PASSWORD` | 密码（可选） | 空 |
| `STOCKGRAPH_FALKORDB_TIMEOUT` | 连接/命令超时（秒） | `5` |
| `STOCKGRAPH_GRAPH_FALLBACK` | `0` 关闭自动回退 | 开启 |
| `STOCKGRAPH_GRAPH_CONFIG` | 配置文件路径覆盖 | `config/graph_backend.json` |

**关于 `auto`**：先探 FalkorDB，通了用图库，不通静默回退 SQLite。
适合「有图库就用、没有也能跑」的部署环境。

**关于自动回退**：即使显式写了 `falkordb`，只要 `fallback_to_sqlite` 为真，
FalkorDB 连不上时也会回退到 SQLite 并在日志里告警，不会让整条数据链路挂掉。
要严格模式就加 `--no-fallback` 或设 `STOCKGRAPH_GRAPH_FALLBACK=0`。

---

## 4. 命令行工具

### 4.1 `scripts/graph_backend.py` — 后端管理与迁移

```bash
python scripts/graph_backend.py status                       # 当前后端 + 两个候选的连通性
python scripts/graph_backend.py ping falkordb                # 只探活
python scripts/graph_backend.py switch falkordb \
    --host 10.0.0.5 --port 6379 --graph-name stockgraph \
    --password secret --migrate                              # 切换 + 迁移
python scripts/graph_backend.py switch falkordb --no-fallback # 严格模式，连不上就报错
python scripts/graph_backend.py migrate --to falkordb --dry-run   # 只算不写
python scripts/graph_backend.py migrate --to sqlite          # 反向迁移（图库 → SQLite）
python scripts/graph_backend.py reset --backend falkordb     # 清空图库
```

`switch` 会做三件事：写配置文件、清进程内缓存、立刻探活。
探活失败且没开回退时返回退出码 1，方便串在 CI/部署脚本里。

### 4.2 `scripts/graph_query.py` — 图查询与分析

```bash
python scripts/graph_query.py stats                                   # 全局统计
python scripts/graph_query.py status                                  # 后端状态
python scripts/graph_query.py top --type dragon_tiger --date 2026-11-05 --limit 20
python scripts/graph_query.py pagerank --type dragon_tiger --date 2026-11-05
python scripts/graph_query.py communities --type dragon_tiger --date 2026-11-05 --min-size 3
python scripts/graph_query.py neighbors --node "stock:600519"
python scripts/graph_query.py path --from "seat:机构专用" --to "stock:000001" --depth 4
```

每个命令在两种后端上都返回同样的结构，可以拿来做回归对比。

---

## 5. 数据模型

同一个 `snapshot_key = "<snapshot_type>|<snapshot_date>"` 在两种后端里语义一致。

### FalkorDB 侧

| 概念 | 标签 / 关系 | 属性 |
| --- | --- | --- |
| 实体节点 | `(:Entity)` | `node_id`（唯一索引）、`node_type`、`node_key`、`node_name`、`attributes_json` |
| 关系边 | `(:Entity)-[:EDGE_TYPE]->(:Entity)` | `snapshot_key`、`edge_type`、`weight`、`trade_date`、`attributes_json` |
| 快照元信息 | `(:GraphSnapshot)` | `snapshot_key`（唯一索引）、`snapshot_type`、`snapshot_date`、`version`、`metadata_json` |

关系类型由 `edge_type` 清洗成大写标识符（`[^A-Za-z0-9_]` 全部替换掉），
所以 `buy` 变成 `:BUY`、`news-stock` 变成 `:NEWS_STOCK`。

**为什么关系类型要单独存一份 `edge_type` 属性**：清洗是有损的（`a-b` 和 `a_b` 会撞），
查询时用 `type(r)` 做粗筛、用 `r.edge_type` 做精确判断。

### SQLite 侧

`graph_nodes` / `graph_edges` / `graph_snapshots` 三张表，字段与上面一一对应。
`graph_edges` 上有 `(snapshot_type, trade_date)` 和 `(target_node_id)` 索引。

---

## 6. 一致性保证

这是两套后端能互换的前提，也是重构时最容易踩坑的地方：

### 6.1 分析算法在后端之外

PageRank、标签传播社区发现、BFS 最短路径、连通分量、度中心性**全部只用标准库实现**
（`infrastructure/graph/algorithms.py`），不依赖 networkx，也不依赖某后端的图算法扩展。

两个后端都实现 `fetch_edges()` 返回统一的边列表，分析层拿同一份数据算，
所以 `pagerank` 的小数点后 8 位在两边完全一致。这是有意为之：图算法的语言差异
（浮点累加顺序、并行归约）足以让同一张图在两个库里给出不同的排名。

### 6.2 同一快照的写入是幂等的

`save_snapshot()` 重复调用不会让边数翻倍：
- SQLite：先按 `(snapshot_type, trade_date)` 删旧边再插；
- FalkorDB：先 `MATCH` 出同 `snapshot_key` 的旧边 `DELETE`，再用 `UNWIND` 批量写。

### 6.3 跨快照共享节点不能被覆盖

龙虎榜快照里「机构专用」这个席位节点会出现在全年 200 多个快照里。
原实现用 `INSERT OR REPLACE`，后一天的写入会把前一天的节点属性（比如当时记录的营业部名称）刷掉。

现在改成 `ON CONFLICT(node_id) DO UPDATE`，只更新非空字段；FalkorDB 侧用 `MERGE` + `SET`。

### 6.4 删除快照要清孤点

`delete_snapshot()` 删完后会清理不再被任何边引用的节点，否则图里会留一堆度数为 0 的"幽灵节点"，
污染 `top_nodes` 和社区发现的输入。

---

## 7. 性能参考

本机实测（4 核，FalkorDB 单机 Docker）：

| 操作 | SQLite | FalkorDB |
| --- | --- | --- |
| 写入单快照（约 60 节点 / 600 边） | ~15 ms | ~40 ms |
| PageRank（40 次迭代，2000 节点） | ~30 ms | ~35 ms（边列表从库里取出后本地算） |
| 一跳邻居查询 | ~2 ms | ~3 ms |
| 跨快照全图最短路径 | 全表扫描，较慢 | Cypher `shortestPath`，明显更快 |

结论：**日常写入和单快照分析 SQLite 更快**（没有网络往返），
FalkorDB 的优势在**跨快照的大图交互查询**和多进程共享图数据。

所以默认用 SQLite，需要做全局关系挖掘时再切。

---

## 8. 常见问题

**Q: 切换后 `graph_query.py stats` 显示 0 个快照？**
A: 没有迁移。执行 `python scripts/graph_backend.py migrate --to falkordb`。

**Q: `switch falkordb` 报 `FalkorDB 不可用` 但没失败？**
A: 开了自动回退，实际还在用 SQLite。加 `--no-fallback` 可以让它硬失败。

**Q: 关系类型里的中文怎么办？**
A: Cypher 的关系类型不支持中文标识符。清洗会去掉非 ASCII 字符，
原始值仍完整保存在 `edge_type` 属性里，需要按类型过滤时查属性而不是 `type(r)`。

**Q: 指定了 `snapshot_type` 的最短路径为什么和跨快照的不一样？**
A: 语义不同。指定快照 = 只在该快照的边里找路（FalkorDB 的 `RETURN shortestPath`
无法附加边过滤条件），所以这条路径走本地 BFS，与 SQLite 结果严格一致；
不指定快照才是真正的全图最短路，走 Cypher。

**Q: 想清空重来？**
A: `python scripts/graph_backend.py reset --backend falkordb`（或 `sqlite`）。
注意 SQLite 侧会逐个 `delete_snapshot`，不会动 `daily_summaries` 这些业务表。
