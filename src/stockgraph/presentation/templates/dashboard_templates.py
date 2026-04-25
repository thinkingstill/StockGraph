import json


def render_query_dashboard(
    latest_date: str,
    date_list: list[str],
    all_operations: dict,
    all_active_stocks: dict,
    all_active_seats: dict,
    all_famous_traders: dict,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>龙虎榜查询</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        h1 {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; }}
        .stats {{ background: white; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .stats span {{ margin-right: 30px; }}
        .search-box {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .search-box input {{ padding: 10px; width: 200px; margin-right: 10px; border: 1px solid #ddd; border-radius: 4px; }}
        .search-box button {{ padding: 10px 20px; background: #1a73e8; color: white; border: none; border-radius: 4px; cursor: pointer; }}
        .search-box select {{ padding: 10px; width: 150px; margin-right: 10px; border: 1px solid #ddd; border-radius: 4px; }}
        .result, .active-stocks, .active-seats, .famous-traders {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .buy {{ color: #ea4335; }}
        .sell {{ color: #34a853; }}
        .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
        .tag-机构 {{ background: #e3f2fd; color: #1976d2; }}
        .tag-游资 {{ background: #fff3e0; color: #e65100; }}
        .tag-外资 {{ background: #e8f5e9; color: #388e3c; }}
        .alias {{ background: #fce4ec; color: #c2185b; font-weight: bold; }}
        .row-机构 {{ background: #e3f2fd; }}
        .row-自然人 {{ background: #fff8e1; }}
        .row-外资 {{ background: #e8f5e9; }}
        .row-游资 {{ background: #fafafa; }}
        .summary-bold {{ font-weight: 600; }}
    </style>
</head>
<body>
    <h1>龙虎榜查询</h1>
    <div class="stats" id="statsBox">
        <span><strong>日期:</strong> <span id="currentDate">{latest_date}</span></span>
        <span><strong>股票数:</strong> <span id="stockCount">0</span></span>
        <span><strong>席位数:</strong> <span id="seatCount">0</span></span>
    </div>
    <div class="search-box">
        <select id="dateSelect" onchange="changeDate()">
            {"".join(f'<option value="{d}" {"selected" if d == latest_date else ""}>{d}</option>' for d in date_list)}
        </select>
        <input type="text" id="stockInput" placeholder="股票代码或名称">
        <input type="text" id="seatInput" placeholder="席位或外号">
        <button onclick="search()">查询</button>
        <button onclick="clearSearch()" style="background:#666;margin-left:10px;">清空</button>
    </div>
    <div class="active-stocks">
        <h3 style="color:#ea4335;">活跃股票 TOP20</h3>
        <table id="stocksTable"><tr><th>股票代码</th><th>股票名称</th><th>席位数</th><th>买入(万)</th><th>卖出(万)</th><th>净额(万)</th></tr></table>
    </div>
    <div class="active-seats">
        <h3 style="color:#1a73e8;">活跃席位 TOP20</h3>
        <table id="activeTable"><tr><th>席位名称</th><th>游资外号</th><th>类型</th><th>次数</th><th>买入(万)</th><th>卖出(万)</th><th>净额(万)</th></tr></table>
    </div>
    <div class="famous-traders">
        <h3 style="color:#c2185b;">知名游资</h3>
        <table id="famousTable"><tr><th>席位名称</th><th>外号</th><th>类型</th><th>次数</th><th>买入(万)</th><th>卖出(万)</th><th>净额(万)</th></tr></table>
    </div>
    <div class="result">
        <h3 id="resultTitle">查询结果</h3>
        <table id="resultTable"><tr><th>股票</th><th>席位</th><th>外号</th><th>类型</th><th>方向</th><th>金额(万)</th></tr></table>
    </div>
    <script>
        const allData = {json.dumps(all_operations, ensure_ascii=False)};
        const allActiveStocks = {json.dumps(all_active_stocks, ensure_ascii=False)};
        const allActiveSeats = {json.dumps(all_active_seats, ensure_ascii=False)};
        const allFamousTraders = {json.dumps(all_famous_traders, ensure_ascii=False)};
        let currentDate = '{latest_date}';

        function changeDate() {{
            currentDate = document.getElementById('dateSelect').value;
            document.getElementById('currentDate').textContent = currentDate;
            initActiveStocks();
            initActiveSeats();
            initFamousTraders();
            updateStats();
            clearSearch();
        }}

        function updateStats() {{
            const ops = allData[currentDate] || [];
            document.getElementById('stockCount').textContent = new Set(ops.map(o => o.stockCode)).size;
            document.getElementById('seatCount').textContent = new Set(ops.map(o => o.seatName)).size;
        }}

        function initActiveStocks() {{
            const tbody = document.querySelector('#stocksTable');
            tbody.innerHTML = '<tr><th>股票代码</th><th>股票名称</th><th>席位数</th><th>买入(万)</th><th>卖出(万)</th><th>净额(万)</th></tr>';
            (allActiveStocks[currentDate] || []).forEach(s => {{
                const row = tbody.insertRow();
                row.innerHTML = `<td>${{s.code}}</td><td>${{s.name}}</td><td>${{s.seatCount}}</td><td class="buy">${{s.buy.toFixed(2)}}</td><td class="sell">${{s.sell.toFixed(2)}}</td><td class="${{s.net > 0 ? 'buy' : 'sell'}}">${{s.net.toFixed(2)}}</td>`;
            }});
        }}

        function initActiveSeats() {{
            const tbody = document.querySelector('#activeTable');
            tbody.innerHTML = '<tr><th>席位名称</th><th>游资外号</th><th>类型</th><th>次数</th><th>买入(万)</th><th>卖出(万)</th><th>净额(万)</th></tr>';
            (allActiveSeats[currentDate] || []).forEach(s => {{
                const row = tbody.insertRow();
                row.innerHTML = `<td>${{s.name}}</td><td>${{s.alias ? '<span class="tag alias">' + s.alias + '</span>' : '-'}}</td><td><span class="tag tag-${{s.type}}">${{s.type}}</span></td><td>${{s.count}}</td><td class="buy">${{s.buy.toFixed(2)}}</td><td class="sell">${{s.sell.toFixed(2)}}</td><td class="${{s.net > 0 ? 'buy' : 'sell'}}">${{s.net.toFixed(2)}}</td>`;
            }});
        }}

        function initFamousTraders() {{
            const tbody = document.querySelector('#famousTable');
            tbody.innerHTML = '<tr><th>席位名称</th><th>外号</th><th>类型</th><th>次数</th><th>买入(万)</th><th>卖出(万)</th><th>净额(万)</th></tr>';
            const traders = allFamousTraders[currentDate] || [];
            if (traders.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#999;">今日暂无知名游资上榜</td></tr>';
                return;
            }}
            traders.forEach(s => {{
                const row = tbody.insertRow();
                row.innerHTML = `<td>${{s.name}}</td><td><span class="tag alias">${{s.alias}}</span></td><td><span class="tag tag-${{s.type}}">${{s.type}}</span></td><td>${{s.count}}</td><td class="buy">${{s.buy.toFixed(2)}}</td><td class="sell">${{s.sell.toFixed(2)}}</td><td class="${{s.net > 0 ? 'buy' : 'sell'}}">${{s.net.toFixed(2)}}</td>`;
            }});
        }}

        function search() {{
            const stockQ = document.getElementById('stockInput').value.trim().toLowerCase();
            const seatQ = document.getElementById('seatInput').value.trim().toLowerCase();
            const ops = allData[currentDate] || [];
            renderResults(ops.filter(o => {{
                const matchStock = !stockQ || o.stockCode.toLowerCase().includes(stockQ) || o.stockName.toLowerCase().includes(stockQ);
                const matchSeat = !seatQ || o.seatName.toLowerCase().includes(seatQ) || (o.alias && o.alias.toLowerCase().includes(seatQ));
                return matchStock && matchSeat;
            }}));
        }}

        function clearSearch() {{
            document.getElementById('stockInput').value = '';
            document.getElementById('seatInput').value = '';
            renderResults([]);
        }}

        function renderResults(data) {{
            const tbody = document.querySelector('#resultTable');
            tbody.innerHTML = '<tr><th>股票</th><th>席位</th><th>外号</th><th>类型</th><th>方向</th><th>金额(万)</th></tr>';
            document.getElementById('resultTitle').textContent = '查询结果: ' + data.length + '条';
            const summarySeats = {{ '机构专用': '机构', '沪股通专用': '外资', '深股通专用': '外资', '自然人': '自然人', '中小投资者': '自然人', '其他自然人': '自然人' }};
            data.slice(0, 100).forEach(o => {{
                const row = tbody.insertRow();
                row.className = summarySeats[o.seatName] ? ('row-' + summarySeats[o.seatName] + ' summary-bold') : ('row-' + o.seatType);
                row.innerHTML = `<td>${{o.stockCode}} ${{o.stockName}}</td><td>${{o.seatName}}</td><td>${{o.alias ? '<span class="tag alias">' + o.alias + '</span>' : '-'}}</td><td><span class="tag tag-${{o.seatType}}">${{o.seatType}}</span></td><td class="${{o.direction === '买' ? 'buy' : 'sell'}}">${{o.direction}}</td><td>${{o.amount.toFixed(2)}}</td>`;
            }});
        }}

        initActiveStocks();
        initActiveSeats();
        initFamousTraders();
        updateStats();
    </script>
</body>
</html>"""


def render_comprehensive_dashboard(data: list[dict], famous_traders: dict) -> str:
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>龙虎榜综合分析</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f5f5f5; padding: 20px; }
.container { max-width: 1400px; margin: 0 auto; }
h1 { color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 12px; margin-bottom: 20px; }
.section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
.section-title { font-size: 16px; font-weight: 600; color: #333; margin-bottom: 15px; border-bottom: 2px solid #1a73e8; padding-bottom: 10px; }
.filter-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 15px; }
input, select { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
.btn { padding: 8px 20px; background: #1a73e8; color: white; border: none; border-radius: 4px; cursor: pointer; }
.btn:hover { background: #1557b0; }
.btn-secondary { background: #666; }
.quick-btn { padding: 4px 12px; background: #e8f0fe; color: #1a73e8; border: 1px solid #d2e3fc; border-radius: 4px; cursor: pointer; font-size: 12px; margin: 2px; }
.quick-btn.active { background: #1a73e8; color: white; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 8px; text-align: left; border-bottom: 1px solid #eee; font-size: 13px; }
th { background: #f8f9fa; font-weight: 600; }
tr:hover { background: #f5f5f5; cursor: pointer; }
.buy { color: #ea4335; font-weight: 500; }
.sell { color: #34a853; font-weight: 500; }
.tag { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.tag-机构 { background: #e3f2fd; color: #1976d2; }
.tag-游资 { background: #fff3e0; color: #e65100; }
.tag-外资 { background: #e8f5e9; color: #388e3c; }
.alias-tag { background: #fce4ec; color: #c2185b; padding: 1px 4px; border-radius: 3px; font-size: 11px; margin-left: 4px; }
.divider { border: none; border-top: 3px solid #1a73e8; margin: 30px 0; }
#graphChart { width: 100%; height: 500px; background: #fafafa; border: 2px solid #ddd; border-radius: 8px; }
.stats-row { display: flex; gap: 20px; margin: 15px 0; padding: 15px; background: #f8f9fa; border-radius: 6px; }
.stat-item { text-align: center; }
.stat-item .label { font-size: 12px; color: #666; }
.stat-item .value { font-size: 18px; font-weight: 600; color: #333; }
#graphDebug { margin: 10px 0; padding: 10px; background: #fff3cd; border-radius: 4px; font-size: 12px; }
</style>
</head>
<body>
<div class="container">
<h1>龙虎榜综合分析</h1>

<div class="section">
    <div class="section-title">📅 龙虎榜查询</div>
    <div class="filter-row">
        <label>起始日期：</label>
        <input type="date" id="startDate" onchange="onDateChange()">
        <label>结束日期：</label>
        <input type="date" id="endDate" onchange="onDateChange()">
        <label>股票：</label>
        <input type="text" id="queryStock" placeholder="代码或名称">
        <label>席位：</label>
        <input type="text" id="querySeat" placeholder="席位名称或外号">
        <button class="btn" onclick="querySearch()">查询</button>
        <button class="btn btn-secondary" onclick="queryClear()">清空</button>
    </div>
    <div class="stats-row">
        <div class="stat-item"><div class="label">日期区间</div><div class="value" id="queryDateDisplay">-</div></div>
        <div class="stat-item"><div class="label">股票数</div><div class="value" id="queryStockCount">0</div></div>
        <div class="stat-item"><div class="label">席位数</div><div class="value" id="querySeatCount">0</div></div>
        <div class="stat-item"><div class="label">总记录</div><div class="value" id="queryTotalCount">0</div></div>
    </div>
    <div style="display:flex; gap:20px;">
        <div style="flex:1;">
            <div style="font-weight:600;margin-bottom:10px;">活跃股票 TOP15</div>
            <table id="topStocksTable"><thead><tr><th>股票</th><th>次数</th><th>买入</th><th>卖出</th></tr></thead><tbody></tbody></table>
        </div>
        <div style="flex:1;">
            <div style="font-weight:600;margin-bottom:10px;">活跃席位 TOP15</div>
            <table id="topSeatsTable"><thead><tr><th>席位</th><th>类型</th><th>次数</th><th>净额</th></tr></thead><tbody></tbody></table>
        </div>
    </div>
    <div style="margin-top:15px;">
        <div style="font-weight:600;margin-bottom:10px;">知名游资</div>
        <div id="famousTradersBtns"></div>
    </div>
    <div style="margin-top:15px;">
        <div style="font-weight:600;margin-bottom:10px;">查询结果</div>
        <table id="queryResultTable"><thead><tr><th>日期</th><th>股票</th><th>席位</th><th>类型</th><th>方向</th><th>金额</th></tr></thead><tbody></tbody></table>
    </div>
</div>

<hr class="divider">

<div class="section">
    <div class="section-title">🔗 关系网络分析</div>
    <div class="filter-row">
        <label>筛选：</label>
        <input type="text" id="graphFilterInput" placeholder="关键词">
        <button class="btn" onclick="doGraphSearch()">查询</button>
        <button class="btn btn-secondary" onclick="graphReset()">重置</button>
    </div>
    <div style="margin:10px 0;">
        <button class="quick-btn" onclick="graphQuickFilter('机构')">机构</button>
        <button class="quick-btn" onclick="graphQuickFilter('外资')">外资</button>
        <button class="quick-btn" onclick="graphQuickFilter('章盟主')">章盟主</button>
        <button class="quick-btn" onclick="graphQuickFilter('赵老哥')">赵老哥</button>
        <button class="quick-btn" onclick="graphQuickFilter('孙哥')">孙哥</button>
    </div>
    <div class="stats-row">
        <div class="stat-item"><div class="label">席位</div><div class="value" id="graphSeatNum">0</div></div>
        <div class="stat-item"><div class="label">股票</div><div class="value" id="graphStockNum">0</div></div>
        <div class="stat-item"><div class="label">买入</div><div class="value" id="graphBuyTotal">0</div></div>
        <div class="stat-item"><div class="label">卖出</div><div class="value" id="graphSellTotal">0</div></div>
    </div>
    <div id="graphDebug"></div>
    <div id="graphChart"></div>
    <div style="margin-top:15px;">
        <div style="font-weight:600;margin-bottom:10px;">明细</div>
        <table id="graphDetailTable"><thead><tr><th>日期</th><th>股票</th><th>席位</th><th>类型</th><th>方向</th><th>金额</th></tr></thead><tbody></tbody></table>
    </div>
</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<script>
const ALL_DATA = __DATA_PLACEHOLDER__;
const FAMOUS_TRADERS = __TRADERS_PLACEHOLDER__;
let myChart = null;

function formatAmount(amt) { return amt >= 10000 ? (amt / 10000).toFixed(2) + '亿' : amt.toFixed(2) + '万'; }
function truncateText(text, maxLen) { return text.length > maxLen ? text.substring(0, maxLen) + '...' : text; }
function getUniqueDates() { return [...new Set(ALL_DATA.map(d => d.date))].sort().reverse(); }
function getDataByDateRange(startDate, endDate) {
    let result = [...ALL_DATA];
    if (startDate) result = result.filter(d => d.date >= startDate);
    if (endDate) result = result.filter(d => d.date <= endDate);
    return result;
}
function getTopStocks(data) {
    const map = new Map();
    data.forEach(r => {
        if (!map.has(r.stock_code)) map.set(r.stock_code, { stock_code: r.stock_code, stock_name: r.stock_name, buy_amount: 0, sell_amount: 0, count: 0 });
        const info = map.get(r.stock_code);
        if (r.direction === '买') info.buy_amount += r.amount; else info.sell_amount += r.amount;
        info.count++;
    });
    return Array.from(map.values()).sort((a, b) => (b.buy_amount + b.sell_amount) - (a.buy_amount + a.sell_amount)).slice(0, 15);
}
function getTopSeats(data) {
    const map = new Map();
    data.forEach(r => {
        if (!map.has(r.seat_name)) map.set(r.seat_name, { seat_name: r.seat_name, seat_type: r.seat_type, trader_alias: r.trader_alias, buy_amount: 0, sell_amount: 0, count: 0 });
        const info = map.get(r.seat_name);
        if (r.direction === '买') info.buy_amount += r.amount; else info.sell_amount += r.amount;
        info.count++;
    });
    return Array.from(map.values()).sort((a, b) => (b.buy_amount + b.sell_amount) - (a.buy_amount + a.sell_amount)).slice(0, 15);
}
function getDateRange() { return { start: document.getElementById('startDate').value, end: document.getElementById('endDate').value }; }
function onDateChange() { querySearch(); doGraphSearch(); }
function renderTopStocks(data) {
    const tbody = document.querySelector('#topStocksTable tbody');
    tbody.innerHTML = '';
    getTopStocks(data).forEach(s => {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td>' + s.stock_name + '(' + s.stock_code + ')</td><td>' + s.count + '</td><td class="buy">' + formatAmount(s.buy_amount) + '</td><td class="sell">' + formatAmount(s.sell_amount) + '</td>';
        tr.onclick = () => { scrollToGraph(); filterByStock(s.stock_code); };
        tbody.appendChild(tr);
    });
}
function renderTopSeats(data) {
    const tbody = document.querySelector('#topSeatsTable tbody');
    tbody.innerHTML = '';
    getTopSeats(data).forEach(s => {
        const tr = document.createElement('tr');
        const name = s.trader_alias ? s.seat_name + '<span class="alias-tag">' + s.trader_alias + '</span>' : truncateText(s.seat_name, 15);
        const net = s.buy_amount - s.sell_amount;
        tr.innerHTML = '<td title="' + s.seat_name + '">' + name + '</td><td><span class="tag tag-' + s.seat_type + '">' + s.seat_type + '</span></td><td>' + s.count + '</td><td class="' + (net >= 0 ? 'buy' : 'sell') + '">' + formatAmount(Math.abs(net)) + '</td>';
        tr.onclick = () => { scrollToGraph(); filterBySeat(s.trader_alias || s.seat_name); };
        tbody.appendChild(tr);
    });
}
function renderFamousTraders() {
    const container = document.getElementById('famousTradersBtns');
    container.innerHTML = '';
    Object.keys(FAMOUS_TRADERS).forEach(name => {
        const btn = document.createElement('button');
        btn.className = 'quick-btn';
        btn.textContent = name;
        btn.onclick = () => { document.getElementById('querySeat').value = name; querySearch(); };
        container.appendChild(btn);
    });
}
function querySearch() {
    const range = getDateRange();
    const stockKw = document.getElementById('queryStock').value.trim().toLowerCase();
    const seatKw = document.getElementById('querySeat').value.trim();
    let data = getDataByDateRange(range.start, range.end);
    if (stockKw) data = data.filter(d => d.stock_code.toLowerCase().includes(stockKw) || d.stock_name.toLowerCase().includes(stockKw));
    if (seatKw) {
        const traderKws = FAMOUS_TRADERS[seatKw];
        data = data.filter(d => d.seat_name.includes(seatKw) || (d.trader_alias && d.trader_alias.includes(seatKw)) || d.seat_type === seatKw || (traderKws && traderKws.some(k => d.seat_name.includes(k))));
    }
    document.getElementById('queryDateDisplay').textContent = (range.start || range.end) ? (range.start || '起始') + ' ~ ' + (range.end || '结束') : '全部';
    document.getElementById('queryStockCount').textContent = new Set(data.map(d => d.stock_code)).size;
    document.getElementById('querySeatCount').textContent = new Set(data.map(d => d.seat_name)).size;
    document.getElementById('queryTotalCount').textContent = data.length;
    renderTopStocks(data);
    renderTopSeats(data);
    const tbody = document.querySelector('#queryResultTable tbody');
    tbody.innerHTML = '';
    data.sort((a, b) => b.amount - a.amount).slice(0, 100).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td>' + r.date + '</td><td>' + r.stock_name + '</td><td title="' + r.seat_name + '">' + (r.trader_alias ? truncateText(r.seat_name, 12) + '<span class="alias-tag">' + r.trader_alias + '</span>' : truncateText(r.seat_name, 12)) + '</td><td><span class="tag tag-' + r.seat_type + '">' + r.seat_type + '</span></td><td class="' + (r.direction === '买' ? 'buy' : 'sell') + '">' + r.direction + '</td><td class="' + (r.direction === '买' ? 'buy' : 'sell') + '">' + formatAmount(r.amount) + '</td>';
        tbody.appendChild(tr);
    });
}
function queryClear() { document.getElementById('queryStock').value = ''; document.getElementById('querySeat').value = ''; querySearch(); }
function scrollToGraph() { document.querySelector('.divider').scrollIntoView({ behavior: 'smooth' }); }
function filterByStock(code) { document.getElementById('graphFilterInput').value = code; doGraphSearch(); }
function filterBySeat(kw) { document.getElementById('graphFilterInput').value = kw; doGraphSearch(); }
function doGraphSearch() {
    const range = getDateRange();
    const kw = document.getElementById('graphFilterInput').value.trim();
    let data = getDataByDateRange(range.start, range.end);
    if (kw) {
        const traderKws = FAMOUS_TRADERS[kw];
        data = data.filter(d => d.stock_code.toLowerCase().includes(kw.toLowerCase()) || d.stock_name.toLowerCase().includes(kw.toLowerCase()) || d.seat_name.includes(kw) || (d.trader_alias && d.trader_alias.includes(kw)) || d.seat_type === kw || (traderKws && traderKws.some(k => d.seat_name.includes(k))));
    }
    renderGraph(data);
    updateGraphDetail(data);
    document.querySelectorAll('.quick-btn').forEach(btn => btn.classList.toggle('active', btn.textContent === kw));
}
function renderGraph(data) {
    const chartDom = document.getElementById('graphChart');
    const debugDom = document.getElementById('graphDebug');
    debugDom.innerHTML = '原始数据: ' + data.length + ' 条';
    if (typeof echarts === 'undefined') { chartDom.innerHTML = '<div style="padding:20px;color:red;">ECharts加载失败</div>'; return; }
    if (!myChart) myChart = echarts.init(chartDom);
    const seatMap = new Map();
    const stockMap = new Map();
    data.forEach(r => {
        const seatName = r.seat_name || '未知席位';
        if (!seatMap.has(seatName)) seatMap.set(seatName, { name: seatName, type: r.seat_type || '游资', alias: r.trader_alias, buy: 0, sell: 0, operations: [] });
        const s = seatMap.get(seatName);
        if (r.direction === '买') s.buy += r.amount || 0; else s.sell += r.amount || 0;
        s.operations.push({ date: r.date, stock: r.stock_name, direction: r.direction, amount: r.amount });
        const stockCode = r.stock_code || '未知代码';
        if (!stockMap.has(stockCode)) stockMap.set(stockCode, { code: stockCode, name: r.stock_name || '未知股票', buy: 0, sell: 0, operations: [] });
        const st = stockMap.get(stockCode);
        if (r.direction === '买') st.buy += r.amount || 0; else st.sell += r.amount || 0;
        st.operations.push({ date: r.date, seat: r.seat_name, direction: r.direction, amount: r.amount });
    });
    const topSeats = Array.from(seatMap.values()).sort((a, b) => (b.buy + b.sell) - (a.buy + a.sell)).slice(0, 25);
    const topStocks = Array.from(stockMap.values()).sort((a, b) => (b.buy + b.sell) - (a.buy + a.sell)).slice(0, 25);
    debugDom.innerHTML += ' | 席位数: ' + topSeats.length + ' | 股票数: ' + topStocks.length;
    const nodes = [];
    const nodeMap = new Map();
    topSeats.forEach((s, i) => {
        const nodeName = 'S' + i;
        let cat = 2;
        if (s.type === '机构') cat = 1; else if (s.type === '外资') cat = 3;
        const displayName = (s.alias || s.name || '未知').toString();
        nodes.push({ name: nodeName, label: displayName.length > 4 ? displayName.substring(0, 4) : displayName, fullName: s.name || '未知', category: cat, seatType: s.type, value: (s.buy || 0) + (s.sell || 0), operations: s.operations, nodeType: 'seat' });
        nodeMap.set(s.name, nodeName);
    });
    topStocks.forEach((s, i) => {
        const nodeName = 'T' + i;
        const stockName = (s.name || '未知').toString();
        nodes.push({ name: nodeName, label: stockName.length > 4 ? stockName.substring(0, 4) : stockName, fullName: stockName + '(' + (s.code || '') + ')', code: s.code, category: 0, value: (s.buy || 0) + (s.sell || 0), operations: s.operations, nodeType: 'stock' });
        nodeMap.set(s.code, nodeName);
    });
    const links = [];
    data.forEach(r => {
        const src = nodeMap.get(r.seat_name);
        const tgt = nodeMap.get(r.stock_code);
        if (src && tgt) links.push({ source: src, target: tgt, value: r.amount, lineStyle: { color: r.direction === '买' ? '#ea4335' : '#34a853' } });
    });
    document.getElementById('graphSeatNum').textContent = topSeats.length;
    document.getElementById('graphStockNum').textContent = topStocks.length;
    document.getElementById('graphBuyTotal').textContent = formatAmount(data.reduce((sum, d) => sum + (d.direction === '买' ? d.amount : 0), 0));
    document.getElementById('graphSellTotal').textContent = formatAmount(data.reduce((sum, d) => sum + (d.direction === '卖' ? d.amount : 0), 0));
    if (nodes.length === 0 || links.length === 0) { chartDom.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#666;">数据不足</div>'; return; }
    myChart.setOption({
        backgroundColor: '#fff',
        tooltip: {
            trigger: 'item',
            formatter: function(p) {
                if (p.dataType === 'node') {
                    const d = p.data;
                    let html = '<b>' + d.fullName + '</b><br/>类型: ' + (d.nodeType === 'stock' ? '股票' : d.seatType) + '<br/>总金额: ' + formatAmount(d.value) + '<br/>';
                    if (d.operations && d.operations.length > 0) {
                        html += '<hr><div style="max-height:120px;overflow-y:auto;">';
                        d.operations.slice().sort((a, b) => (b.date || '').localeCompare(a.date || '')).slice(0, 5).forEach(op => {
                            const target = d.nodeType === 'stock' ? op.seat : op.stock;
                            html += '<div style="font-size:11px;">' + op.date + ' ' + (op.direction === '买' ? '<span style="color:#ea4335">买</span>' : '<span style="color:#34a853">卖</span>') + ' ' + truncateText(target, 6) + ' ' + formatAmount(op.amount) + '</div>';
                        });
                        html += '</div>';
                    }
                    return html;
                }
                return formatAmount(p.data.value);
            }
        },
        toolbox: { show: true, right: 20, top: 10, feature: { restore: { show: true, title: '还原' }, saveAsImage: { show: true, title: '下载图片', pixelRatio: 2 } } },
        legend: { data: ['股票', '机构', '游资', '外资'], top: 10 },
        series: [{
            type: 'graph',
            layout: 'force',
            roam: true,
            draggable: true,
            symbolSize: 35,
            categories: [{ name: '股票', itemStyle: { color: '#5470c6' } }, { name: '机构', itemStyle: { color: '#1a73e8' } }, { name: '游资', itemStyle: { color: '#ff9800' } }, { name: '外资', itemStyle: { color: '#4caf50' } }],
            label: { show: true, position: 'inside', color: '#fff', fontSize: 11, fontWeight: 'bold', formatter: p => p.data.label },
            force: { repulsion: 500, edgeLength: 80, gravity: 0.1 },
            data: nodes,
            links: links,
            lineStyle: { opacity: 0.6, curveness: 0.1 },
            emphasis: { focus: 'adjacency', lineStyle: { width: 3 } }
        }]
    }, true);
    myChart.off('click');
    myChart.on('click', function(params) {
        if (params.dataType === 'node') {
            const d = params.data;
            document.getElementById('graphFilterInput').value = d.nodeType === 'stock' ? d.code : d.fullName;
            doGraphSearch();
        }
    });
}
function updateGraphDetail(data) {
    const tbody = document.querySelector('#graphDetailTable tbody');
    tbody.innerHTML = '';
    data.sort((a, b) => b.amount - a.amount).slice(0, 100).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td>' + r.date + '</td><td>' + r.stock_name + '</td><td title="' + r.seat_name + '">' + (r.trader_alias ? truncateText(r.seat_name, 12) + '<span class="alias-tag">' + r.trader_alias + '</span>' : truncateText(r.seat_name, 12)) + '</td><td><span class="tag tag-' + r.seat_type + '">' + r.seat_type + '</span></td><td class="' + (r.direction === '买' ? 'buy' : 'sell') + '">' + r.direction + '</td><td class="' + (r.direction === '买' ? 'buy' : 'sell') + '">' + formatAmount(r.amount) + '</td>';
        tbody.appendChild(tr);
    });
}
function graphReset() { document.getElementById('graphFilterInput').value = ''; document.querySelectorAll('.quick-btn').forEach(btn => btn.classList.remove('active')); doGraphSearch(); }
function graphQuickFilter(kw) { document.getElementById('graphFilterInput').value = kw; doGraphSearch(); }
function init() {
    const dates = getUniqueDates();
    if (dates.length === 0) { alert('没有数据'); return; }
    document.getElementById('startDate').value = dates[dates.length - 1];
    document.getElementById('endDate').value = dates[0];
    renderFamousTraders();
    querySearch();
    doGraphSearch();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
window.addEventListener('resize', () => { if (myChart) myChart.resize(); });
</script>
</body>
</html>"""
    return html.replace("__DATA_PLACEHOLDER__", json.dumps(data, ensure_ascii=False)).replace(
        "__TRADERS_PLACEHOLDER__", json.dumps(famous_traders, ensure_ascii=False)
    )
