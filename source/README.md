# 龙虎榜综合分析 v1.0.0

## 版本信息
- 版本号: v1.0.0
- 发布日期: 2026-04-18
- 数据截止: 2026-04-16

## 快速部署

### 方式一：直接使用（推荐）
无需任何配置，直接用浏览器打开HTML文件：
```bash
# 双击打开或使用命令
open 龙虎榜查询.html          # macOS
start 龙虎榜查询.html          # Windows
xdg-open 龙虎榜查询.html       # Linux
```

### 方式二：完整部署
如需更新数据，按以下步骤操作：

```bash
# 1. 进入目录
cd 龙虎榜综合分析-v1.0.0

# 2. 创建虚拟环境（可选）
python3 -m venv venv
source venv/bin/activate      # Linux/macOS
# venv\Scripts\activate       # Windows

# 3. 安装依赖
pip install akshare requests beautifulsoup4

# 4. 抓取最新数据（会自动更新数据库和生成查询页面）
python3 dragon_tiger_scraper.py --date 2026-04-17

# 5. 生成综合分析页面
python3 generate_comprehensive_html.py

# 6. 查看结果
open 龙虎榜综合分析.html
```

### 定时任务配置（可选）
如需每日自动更新，可配置crontab：
```bash
# 编辑crontab
crontab -e

# 添加以下内容（每天早上9点执行）
0 9 * * 1-5 cd /path/to/龙虎榜综合分析-v1.0.0 && /path/to/venv/bin/python3 dragon_tiger_scraper.py --date $(date -d "yesterday" +\%Y-\%m-\%d) && /path/to/venv/bin/python3 generate_comprehensive_html.py
```

## 功能特性
1. **龙虎榜查询页面** - 按股票/席位/时间查询龙虎榜数据
2. **综合分析页面** - ECharts Graph关系网络可视化
   - 席位-股票关系网络图
   - 点击节点自动筛选
   - 鼠标悬停显示操作明细
   - 支持还原和下载图片
   - 统一时间区间选择

## 文件说明
| 文件 | 说明 |
|------|------|
| `dragon_tiger_scraper.py` | 数据抓取脚本 |
| `generate_comprehensive_html.py` | 综合分析页面生成脚本 |
| `dragon_tiger.db` | SQLite数据库 |
| `龙虎榜查询.html` | 查询页面 |
| `龙虎榜综合分析.html` | 综合分析页面 |

## 数据说明
- 已过滤汇总类别：自然人、中小投资者、其他自然人、机构专用
- 席位类型：游资、机构、外资
- 支持知名游资别名识别（章盟主、赵老哥、孙哥等）

## 依赖
- Python 3.x
- akshare (数据源)
- SQLite3 (数据库)
- ECharts 5.x (前端图表，CDN加载)
