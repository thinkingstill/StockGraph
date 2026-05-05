def render_unified_app() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>StockGraph</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/echarts-gl/dist/echarts-gl.min.js"></script>
  <style>
    :root {
      --bg: #eef2e6;
      --surface: rgba(255,255,255,0.88);
      --card: #ffffff;
      --text: #182026;
      --muted: #5f6c76;
      --line: #d9dfd1;
      --accent: #164e63;
      --accent-2: #2f6f55;
      --danger: #c2410c;
      --success: #166534;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(22,78,99,0.12), transparent 25%),
        radial-gradient(circle at bottom right, rgba(47,111,85,0.10), transparent 30%),
        linear-gradient(180deg, #f8faf6 0%, var(--bg) 100%);
    }
    .shell {
      max-width: 1480px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }
    .hero {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: end;
      margin-bottom: 20px;
    }
    .hero h1 {
      margin: 0;
      font-size: 34px;
      line-height: 1.1;
    }
    .hero p {
      margin: 8px 0 0;
      color: var(--muted);
    }
    .status {
      min-width: 280px;
      padding: 16px 18px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--surface);
      backdrop-filter: blur(8px);
      font-size: 13px;
      color: var(--muted);
    }
    .tabs {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }
    .tab-btn {
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.75);
      color: var(--text);
      padding: 10px 16px;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 600;
    }
    .tab-btn.active {
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #fff;
      border-color: transparent;
    }
    .panel {
      display: none;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 20px;
      backdrop-filter: blur(10px);
      box-shadow: 0 18px 50px rgba(24,32,38,0.06);
    }
    .panel.active { display: block; }
    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 16px;
    }
    .card {
      grid-column: span 12;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .stat {
      background: #f8faf7;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
    }
    .stat .k { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    .stat .v { font-size: 24px; font-weight: 700; }
    .filters {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    input, select, button {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 14px;
    }
    button {
      background: #fff;
      cursor: pointer;
    }
    .primary {
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      color: #fff;
      border-color: transparent;
    }
    .chart {
      width: 100%;
      min-height: 420px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      padding: 10px 8px;
      border-bottom: 1px solid #edf0e8;
      text-align: left;
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
    .muted { color: var(--muted); }
    .buy { color: #dc2626; font-weight: 600; }
    .sell { color: #15803d; font-weight: 600; }
    .empty {
      padding: 28px;
      text-align: center;
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 16px;
      background: #fafbf8;
    }
    .split-2 { grid-column: span 6; }
    @media (max-width: 980px) {
      .hero { flex-direction: column; align-items: stretch; }
      .split-2 { grid-column: span 12; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <div>
        <h1>StockGraph</h1>
        <p>统一入口，按 tab 查看龙虎榜查询、关系网络、市场热度和行业强弱。每个 tab 独立取数，互不阻塞。</p>
      </div>
      <div class="status">
        <div>页面: <strong>app/index.html</strong></div>
        <div id="manifestStatus" style="margin-top:8px;">正在加载数据清单...</div>
      </div>
    </div>

    <div class="tabs" id="tabs">
      <button class="tab-btn active" data-tab="dragon_query">龙虎榜查询</button>
      <button class="tab-btn" data-tab="dragon_graph">龙虎榜关系网</button>
      <button class="tab-btn" data-tab="market_hot">热度图</button>
      <button class="tab-btn" data-tab="stock_super_graph">全 A 图谱</button>
      <button class="tab-btn" data-tab="market_calendar">行业日历</button>
      <button class="tab-btn" data-tab="market_industry">行业强弱</button>
      <button class="tab-btn" data-tab="stock_news">个股新闻</button>
      <button class="tab-btn" data-tab="ai_analysis">🤖 AI 分析</button>
    </div>

    <section class="panel active" id="panel-dragon_query">
      <div id="dragonQueryRoot" class="empty">正在加载龙虎榜查询数据...</div>
    </section>

    <section class="panel" id="panel-dragon_graph">
      <div id="dragonGraphRoot" class="empty">正在加载龙虎榜关系网数据...</div>
    </section>

    <section class="panel" id="panel-market_hot">
      <div id="marketHotRoot" class="empty">正在加载市场热度数据...</div>
    </section>

    <section class="panel" id="panel-stock_super_graph">
      <div id="stockSuperGraphRoot" class="empty">正在加载全 A 图谱数据...</div>
    </section>

    <section class="panel" id="panel-market_calendar">
      <div id="marketCalendarRoot" class="empty">正在加载行业日历数据...</div>
    </section>

    <section class="panel" id="panel-market_industry">
      <div id="marketIndustryRoot" class="empty">正在加载行业强弱数据...</div>
    </section>

    <section class="panel" id="panel-stock_news">
      <div id="stockNewsRoot" class="empty">正在加载个股新闻数据...</div>
    </section>

    <section class="panel" id="panel-ai_analysis">
      <div id="aiAnalysisRoot" class="empty">正在加载 AI 分析数据...</div>
    </section>
  </div>

  <script>
    const state = { manifest: null, loaded: {} };

    function fmtAmount(v) {
      const n = Number(v || 0);
      return n >= 10000 ? (n / 10000).toFixed(2) + '亿' : n.toFixed(2) + '万';
    }
    function escapeHtml(text) {
      return String(text ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',\"'\":'&#39;'}[s]));
    }
    async function fetchJson(path) {
      const res = await fetch(path, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    }
    function bindTabs() {
      document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('.tab-btn').forEach(x => x.classList.remove('active'));
          document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
          btn.classList.add('active');
          document.getElementById(`panel-${btn.dataset.tab}`).classList.add('active');
          loadTab(btn.dataset.tab);
        });
      });
    }
    async function loadManifest() {
      try {
        state.manifest = await fetchJson('./data/app_manifest.json');
        const ok = Object.entries(state.manifest.sections || {}).filter(([,v]) => v.available).length;
        document.getElementById('manifestStatus').textContent = `已加载数据清单，可用模块 ${ok}/${Object.keys(state.manifest.sections || {}).length}，生成时间 ${state.manifest.generated_at || '-'}`;
      } catch (e) {
        document.getElementById('manifestStatus').textContent = `数据清单加载失败: ${e.message}`;
      }
    }
    async function loadTab(name) {
      if (!state.manifest || state.loaded[name]) return;
      const section = state.manifest.sections[name];
      const rootMap = {
        dragon_query: 'dragonQueryRoot',
        dragon_graph: 'dragonGraphRoot',
        market_hot: 'marketHotRoot',
        stock_super_graph: 'stockSuperGraphRoot',
        market_calendar: 'marketCalendarRoot',
        market_industry: 'marketIndustryRoot',
        stock_news: 'stockNewsRoot',
        ai_analysis: 'aiAnalysisRoot',
      };
      const root = document.getElementById(rootMap[name]);
      if (!section || !section.available) {
        root.innerHTML = `<div class="empty">该页面当前无可用数据。<div style="margin-top:8px;">${escapeHtml(section?.message || '未生成对应数据文件')}</div></div>`;
        state.loaded[name] = true;
        return;
      }
      try {
        const payload = await fetchJson(section.path);
        if (name === 'dragon_query') renderDragonQuery(root, payload);
        if (name === 'dragon_graph') renderDragonGraph(root, payload);
        if (name === 'market_hot') renderMarketHot(root, payload);
        if (name === 'stock_super_graph') renderStockSuperGraph(root, payload);
        if (name === 'market_calendar') renderMarketCalendar(root, payload);
        if (name === 'market_industry') renderMarketIndustry(root, payload);
        if (name === 'stock_news') renderStockNews(root, payload);
        if (name === 'ai_analysis') renderAIAnalysis(root, payload);
        state.loaded[name] = true;
      } catch (e) {
        root.innerHTML = `<div class="empty">数据加载失败<div style="margin-top:8px;">${escapeHtml(e.message)}</div></div>`;
        state.loaded[name] = true;
      }
    }

    function renderDragonQuery(root, payload) {
      const dates = payload.date_list || [];
      let currentDate = payload.latest_date || dates[0] || '';
      root.innerHTML = `
        <div class="stats">
          <div class="stat"><div class="k">当前日期</div><div class="v" id="dq-date">-</div></div>
          <div class="stat"><div class="k">股票数</div><div class="v" id="dq-stock-count">0</div></div>
          <div class="stat"><div class="k">席位数</div><div class="v" id="dq-seat-count">0</div></div>
          <div class="stat"><div class="k">记录数</div><div class="v" id="dq-total">0</div></div>
        </div>
        <div class="filters">
          <select id="dq-select">${dates.map(d => `<option value="${d}" ${d === currentDate ? 'selected' : ''}>${d}</option>`).join('')}</select>
          <input id="dq-stock" placeholder="股票代码或名称">
          <input id="dq-seat" placeholder="席位或外号">
          <button class="primary" id="dq-search">查询</button>
          <button id="dq-clear">清空</button>
        </div>
        <div class="grid">
          <div class="card split-2"><div class="muted" style="margin-bottom:10px;">活跃股票</div><table><thead><tr><th>股票</th><th>席位数</th><th>买入</th><th>卖出</th></tr></thead><tbody id="dq-stocks"></tbody></table></div>
          <div class="card split-2"><div class="muted" style="margin-bottom:10px;">活跃席位</div><table><thead><tr><th>席位</th><th>类型</th><th>次数</th><th>净额</th></tr></thead><tbody id="dq-seats"></tbody></table></div>
          <div class="card"><div class="muted" style="margin-bottom:10px;">查询结果</div><table><thead><tr><th>股票</th><th>席位</th><th>方向</th><th>金额</th></tr></thead><tbody id="dq-results"></tbody></table></div>
        </div>`;

      const allData = payload.all_operations || {};
      const activeStocks = payload.all_active_stocks || {};
      const activeSeats = payload.all_active_seats || {};

      function draw() {
        currentDate = document.getElementById('dq-select').value;
        const stockKw = document.getElementById('dq-stock').value.trim().toLowerCase();
        const seatKw = document.getElementById('dq-seat').value.trim().toLowerCase();
        const ops = (allData[currentDate] || []).filter(item => {
          const stockPass = !stockKw || item.stockCode.toLowerCase().includes(stockKw) || item.stockName.toLowerCase().includes(stockKw);
          const seatPass = !seatKw || item.seatName.toLowerCase().includes(seatKw) || String(item.alias || '').toLowerCase().includes(seatKw);
          return stockPass && seatPass;
        });
        document.getElementById('dq-date').textContent = currentDate || '-';
        document.getElementById('dq-stock-count').textContent = new Set(ops.map(x => x.stockCode)).size;
        document.getElementById('dq-seat-count').textContent = new Set(ops.map(x => x.seatName)).size;
        document.getElementById('dq-total').textContent = ops.length;
        document.getElementById('dq-stocks').innerHTML = (activeStocks[currentDate] || []).slice(0, 12).map(x => `<tr><td>${escapeHtml(x.name)} (${escapeHtml(x.code)})</td><td>${x.seatCount}</td><td class="buy">${x.buy.toFixed(2)}</td><td class="sell">${x.sell.toFixed(2)}</td></tr>`).join('');
        document.getElementById('dq-seats').innerHTML = (activeSeats[currentDate] || []).slice(0, 12).map(x => `<tr><td>${escapeHtml(x.name)}</td><td>${escapeHtml(x.type || '-')}</td><td>${x.count}</td><td class="${x.net >= 0 ? 'buy' : 'sell'}">${x.net.toFixed(2)}</td></tr>`).join('');
        document.getElementById('dq-results').innerHTML = ops.slice(0, 120).map(x => `<tr><td>${escapeHtml(x.stockName)} (${escapeHtml(x.stockCode)})</td><td>${escapeHtml(x.seatName)}</td><td class="${x.direction === '买' ? 'buy' : 'sell'}">${x.direction}</td><td>${Number(x.amount || 0).toFixed(2)}</td></tr>`).join('');
      }

      document.getElementById('dq-search').addEventListener('click', draw);
      document.getElementById('dq-clear').addEventListener('click', () => {
        document.getElementById('dq-stock').value = '';
        document.getElementById('dq-seat').value = '';
        draw();
      });
      document.getElementById('dq-select').addEventListener('change', draw);
      draw();
    }

    function renderDragonGraph(root, payload) {
      root.innerHTML = `
        <div class="filters">
          <input id="dg-keyword" placeholder="股票、席位、类型关键词">
          <button class="primary" id="dg-run">查询</button>
          <button id="dg-reset">重置</button>
        </div>
        <div class="stats">
          <div class="stat"><div class="k">关系记录</div><div class="v" id="dg-total">0</div></div>
          <div class="stat"><div class="k">席位数</div><div class="v" id="dg-seats">0</div></div>
          <div class="stat"><div class="k">股票数</div><div class="v" id="dg-stocks">0</div></div>
          <div class="stat"><div class="k">边数</div><div class="v" id="dg-links">0</div></div>
        </div>
        <div class="card"><div id="dg-chart" class="chart"></div></div>`;
      const chart = echarts.init(document.getElementById('dg-chart'));
      const all = payload.records || [];
      function draw() {
        const kw = document.getElementById('dg-keyword').value.trim().toLowerCase();
        const data = all.filter(x => !kw || x.stock_code.toLowerCase().includes(kw) || x.stock_name.toLowerCase().includes(kw) || x.seat_name.toLowerCase().includes(kw) || String(x.seat_type || '').toLowerCase().includes(kw) || String(x.trader_alias || '').toLowerCase().includes(kw));
        const seatMap = new Map();
        const stockMap = new Map();
        data.forEach(r => {
          if (!seatMap.has(r.seat_name)) seatMap.set(r.seat_name, { name: r.seat_name, type: r.seat_type, value: 0 });
          if (!stockMap.has(r.stock_code)) stockMap.set(r.stock_code, { code: r.stock_code, name: r.stock_name, value: 0 });
          seatMap.get(r.seat_name).value += Number(r.amount || 0);
          stockMap.get(r.stock_code).value += Number(r.amount || 0);
        });
        const topSeats = Array.from(seatMap.values()).sort((a,b) => b.value - a.value).slice(0, 30);
        const topStocks = Array.from(stockMap.values()).sort((a,b) => b.value - a.value).slice(0, 30);
        const nodeMap = new Map();
        const nodes = [];
        topSeats.forEach((x, i) => {
          const id = `S${i}`;
          nodeMap.set(x.name, id);
          nodes.push({ name: id, value: x.value, category: x.type === '机构' ? 1 : x.type === '外资' ? 3 : 2, label: { show: true }, fullName: x.name, shortName: x.name.slice(0,4) });
        });
        topStocks.forEach((x, i) => {
          const id = `T${i}`;
          nodeMap.set(x.code, id);
          nodes.push({ name: id, value: x.value, category: 0, label: { show: true }, fullName: `${x.name}(${x.code})`, shortName: x.name.slice(0,4) });
        });
        const links = data.map(r => {
          const s = nodeMap.get(r.seat_name);
          const t = nodeMap.get(r.stock_code);
          if (!s || !t) return null;
          return { source: s, target: t, value: Number(r.amount || 0), lineStyle: { color: r.direction === '买' ? '#dc2626' : '#15803d' } };
        }).filter(Boolean);
        document.getElementById('dg-total').textContent = data.length;
        document.getElementById('dg-seats').textContent = topSeats.length;
        document.getElementById('dg-stocks').textContent = topStocks.length;
        document.getElementById('dg-links').textContent = links.length;
        chart.setOption({
          tooltip: { formatter: p => p.dataType === 'node' ? (p.data.fullName || p.name) : fmtAmount(p.data.value || 0) },
          legend: [{ data: ['股票','机构','游资','外资'] }],
          series: [{
            type: 'graph',
            layout: 'force',
            roam: true,
            force: { repulsion: 380, edgeLength: 90 },
            categories: [{name:'股票'},{name:'机构'},{name:'游资'},{name:'外资'}],
            label: { formatter: p => p.data.shortName || '' },
            data: nodes,
            links: links,
            lineStyle: { opacity: 0.55, curveness: 0.12 },
          }]
        }, true);
      }
      document.getElementById('dg-run').addEventListener('click', draw);
      document.getElementById('dg-reset').addEventListener('click', () => { document.getElementById('dg-keyword').value = ''; draw(); });
      draw();
    }

    function renderMarketHot(root, payload) {
      const records = payload.records || [];
      if (!records.length) {
        root.innerHTML = '<div class="empty">市场热度数据当前不可用</div>';
        return;
      }
      const numericFields = payload.numeric_fields || {};
      const fieldEntries = Object.entries(numericFields);
      const defaultX = fieldEntries.find(([k]) => k === 'follow_rank')?.[0] || fieldEntries[0][0];
      const defaultY = fieldEntries.find(([k]) => k === 'tweet_rank')?.[0] || fieldEntries[1]?.[0] || fieldEntries[0][0];
      const defaultZ = fieldEntries.find(([k]) => k === 'change_pct')?.[0] || fieldEntries[2]?.[0] || fieldEntries[0][0];
      const defaultSize = fieldEntries.find(([k]) => k === 'deal_rank')?.[0] || fieldEntries[3]?.[0] || fieldEntries[0][0];
      const industries = Array.from(new Set(records.map(x => x.industry))).sort();
      const exchanges = Array.from(new Set(records.map(x => x.exchange))).sort();
      root.innerHTML = `
        <div class="stats">
          <div class="stat"><div class="k">交易日</div><div class="v">${escapeHtml(payload.trade_date || '-')}</div></div>
          <div class="stat"><div class="k">热度记录</div><div class="v">${records.length}</div></div>
          <div class="stat"><div class="k">行业数</div><div class="v" id="mh-industry-count">${industries.length}</div></div>
          <div class="stat"><div class="k">交易所数</div><div class="v">${exchanges.length}</div></div>
        </div>
        <div class="filters">
          <select id="mh-x">${fieldEntries.map(([k,v]) => `<option value="${k}" ${k===defaultX?'selected':''}>X轴: ${v}</option>`).join('')}</select>
          <select id="mh-y">${fieldEntries.map(([k,v]) => `<option value="${k}" ${k===defaultY?'selected':''}>Y轴: ${v}</option>`).join('')}</select>
          <select id="mh-z">${fieldEntries.map(([k,v]) => `<option value="${k}" ${k===defaultZ?'selected':''}>Z轴: ${v}</option>`).join('')}</select>
          <select id="mh-size">${fieldEntries.map(([k,v]) => `<option value="${k}" ${k===defaultSize?'selected':''}>大小: ${v}</option>`).join('')}</select>
          <select id="mh-exchange"><option value="">全部交易所</option>${exchanges.map(x => `<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join('')}</select>
          <select id="mh-industry"><option value="">全部行业</option>${industries.map(x => `<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join('')}</select>
          <input id="mh-keyword" placeholder="股票代码/名称/行业关键词">
          <button class="primary" id="mh-run">刷新</button>
          <button id="mh-reset">重置</button>
        </div>
        <div class="card"><div id="mh-chart" class="chart"></div></div>
        <div class="card" style="margin-top:16px;"><table><thead><tr><th>股票</th><th>行业</th><th>交易所</th><th>关注</th><th>讨论</th><th>交易</th><th>涨跌幅</th><th>成交额</th></tr></thead><tbody id="mh-table"></tbody></table></div>`;
      document.getElementById('mh-table').innerHTML = records.slice(0, 120).map(x => `<tr><td>${escapeHtml(x.stock_name)} (${escapeHtml(x.stock_code)})</td><td>${escapeHtml(x.industry)}</td><td>${Number(x.follow_rank || 0).toFixed(1)}</td><td>${Number(x.tweet_rank || 0).toFixed(1)}</td><td>${Number(x.deal_rank || 0).toFixed(1)}</td><td class="${Number(x.change_pct || 0) >= 0 ? 'buy' : 'sell'}">${Number(x.change_pct || 0).toFixed(2)}%</td></tr>`).join('');
      const chart = echarts.init(document.getElementById('mh-chart'));
      function draw() {
        const xField = document.getElementById('mh-x').value;
        const yField = document.getElementById('mh-y').value;
        const zField = document.getElementById('mh-z').value;
        const sizeField = document.getElementById('mh-size').value;
        const exchange = document.getElementById('mh-exchange').value;
        const industry = document.getElementById('mh-industry').value;
        const keyword = document.getElementById('mh-keyword').value.trim().toLowerCase();
        const filtered = records.filter(x => {
          const matchExchange = !exchange || x.exchange === exchange;
          const matchIndustry = !industry || x.industry === industry;
          const matchKeyword = !keyword || x.stock_code.toLowerCase().includes(keyword) || x.stock_name.toLowerCase().includes(keyword) || x.industry.toLowerCase().includes(keyword);
          return matchExchange && matchIndustry && matchKeyword;
        });
        document.getElementById('mh-industry-count').textContent = new Set(filtered.map(x => x.industry)).size;
        document.getElementById('mh-table').innerHTML = filtered.slice(0, 150).map(x => `<tr><td>${escapeHtml(x.stock_name)} (${escapeHtml(x.stock_code)})</td><td>${escapeHtml(x.industry)}</td><td>${escapeHtml(x.exchange)}</td><td>${Number(x.follow_rank || 0).toFixed(1)}</td><td>${Number(x.tweet_rank || 0).toFixed(1)}</td><td>${Number(x.deal_rank || 0).toFixed(1)}</td><td class="${Number(x.change_pct || 0) >= 0 ? 'buy' : 'sell'}">${Number(x.change_pct || 0).toFixed(2)}%</td><td>${Number(x.amount || 0).toFixed(0)}</td></tr>`).join('');
        chart.setOption({
          tooltip: {
            formatter: p => `${escapeHtml(p.data.stock_name)} (${escapeHtml(p.data.stock_code)})<br/>行业: ${escapeHtml(p.data.industry)}<br/>交易所: ${escapeHtml(p.data.exchange)}<br/>${escapeHtml(numericFields[xField])}: ${Number(p.data.raw[xField] || 0).toFixed(2)}<br/>${escapeHtml(numericFields[yField])}: ${Number(p.data.raw[yField] || 0).toFixed(2)}<br/>${escapeHtml(numericFields[zField])}: ${Number(p.data.raw[zField] || 0).toFixed(2)}`,
          },
          visualMap: { dimension: 2, min: Math.min(...filtered.map(x => Number(x[zField] || 0)), 0), max: Math.max(...filtered.map(x => Number(x[zField] || 0)), 1), calculable: true, orient: 'horizontal', left: 'center', bottom: 0 },
          xAxis3D: { name: numericFields[xField] || xField },
          yAxis3D: { name: numericFields[yField] || yField },
          zAxis3D: { name: numericFields[zField] || zField },
          grid3D: { viewControl: { projection: 'perspective' } },
          series: [{
            type: 'scatter3D',
            data: filtered.map(x => ({
              value: [Number(x[xField] || 0), Number(x[yField] || 0), Number(x[zField] || 0)],
              raw: x,
              stock_name: x.stock_name,
              stock_code: x.stock_code,
              industry: x.industry,
              exchange: x.exchange,
              symbolSize: Math.max(8, Math.min(34, Number(x[sizeField] || 0) / 5 + 8)),
            })),
            symbolSize: function (value, params) { return params.data.symbolSize || 12; },
          }]
        }, true);
      }
      document.getElementById('mh-run').addEventListener('click', draw);
      document.getElementById('mh-reset').addEventListener('click', () => {
        document.getElementById('mh-x').value = defaultX;
        document.getElementById('mh-y').value = defaultY;
        document.getElementById('mh-z').value = defaultZ;
        document.getElementById('mh-size').value = defaultSize;
        document.getElementById('mh-exchange').value = '';
        document.getElementById('mh-industry').value = '';
        document.getElementById('mh-keyword').value = '';
        draw();
      });
      ['mh-x','mh-y','mh-z','mh-size','mh-exchange','mh-industry'].forEach(id => document.getElementById(id).addEventListener('change', draw));
      draw();
    }

    function renderStockSuperGraph(root, payload) {
      const dates = payload.date_list || [];
      const graphs = payload.graphs || {};
      const categories = payload.categories || [];
      if (!dates.length) {
        root.innerHTML = '<div class="empty">全 A 图谱数据当前不可用</div>';
        return;
      }
      const categoryNames = categories.map(x => x.name);
      const categoryByKey = new Map(categories.map((x, idx) => [x.key, { ...x, idx }]));
      const relationLabels = payload.relation_types || {};
      let currentDate = payload.latest_date || dates[0];
      let currentFocus = null;
      const styles = `
        <style>
          .sg-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:16px;}
          .sg-chart-wrap{background:#fff;border:1px solid var(--line);border-radius:16px;padding:10px;}
          .sg-chart{width:100%;height:720px;min-height:620px;}
          .sg-side{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px;max-height:742px;overflow:auto;}
          .sg-side h3{margin:0 0 10px;font-size:16px;}
          .sg-mini{border-bottom:1px solid #edf0e8;padding:10px 0;font-size:13px;}
          .sg-mini:last-child{border-bottom:none;}
          .sg-mini .name{font-weight:700;margin-bottom:4px;}
          .sg-mini .meta{color:var(--muted);font-size:12px;line-height:1.5;}
          .sg-checks{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;}
          .sg-checks label{display:flex;align-items:center;gap:5px;background:#fff;border:1px solid var(--line);border-radius:999px;padding:7px 10px;font-size:12px;}
          .sg-checks input{padding:0;}
          @media (max-width:1100px){.sg-layout{grid-template-columns:1fr;}.sg-side{max-height:none;}.sg-chart{height:620px;}}
        </style>`;
      root.innerHTML = styles + `
        <div class="stats">
          <div class="stat"><div class="k">交易日</div><div class="v" id="sg-date-v">-</div></div>
          <div class="stat"><div class="k">股票节点</div><div class="v" id="sg-stock-v">0</div></div>
          <div class="stat"><div class="k">关系边</div><div class="v" id="sg-edge-v">0</div></div>
          <div class="stat"><div class="k">席位/新闻</div><div class="v" id="sg-alt-v">0</div></div>
        </div>
        <div class="filters">
          <select id="sg-date">${dates.map(d => `<option value="${escapeHtml(d)}" ${d === currentDate ? 'selected' : ''}>${escapeHtml(d)}</option>`).join('')}</select>
          <input id="sg-keyword" placeholder="股票、行业、席位、新闻关键词">
          <select id="sg-industry"><option value="">全部行业</option></select>
          <select id="sg-exchange"><option value="">全部交易所</option></select>
          <select id="sg-scale">
            <option value="800">核心800节点</option>
            <option value="1500" selected>核心1500节点</option>
            <option value="3000">核心3000节点</option>
            <option value="all">尽量全量</option>
          </select>
          <button class="primary" id="sg-run">刷新</button>
          <button id="sg-reset">重置</button>
        </div>
        <div class="sg-checks" id="sg-category-checks"></div>
        <div class="sg-layout">
          <div class="sg-chart-wrap"><div id="sg-chart" class="sg-chart"></div></div>
          <aside class="sg-side">
            <h3>节点详情</h3>
            <div id="sg-detail" class="muted">点击图中的节点查看属性和强关联边。</div>
          </aside>
        </div>`;

      document.getElementById('sg-category-checks').innerHTML = categories.map(c => `
        <label><input type="checkbox" class="sg-cat" value="${escapeHtml(c.key)}" checked>${escapeHtml(c.name)}</label>
      `).join('');

      const chart = echarts.init(document.getElementById('sg-chart'));

      function graph() {
        return graphs[currentDate] || { nodes: [], links: [], stats: {} };
      }
      function getCheckedCategories() {
        return new Set(Array.from(document.querySelectorAll('.sg-cat:checked')).map(x => x.value));
      }
      function fillFilters() {
        const g = graph();
        const industries = Array.from(new Set((g.nodes || []).filter(n => n.category === 'industry').map(n => n.name))).sort();
        const exchanges = Array.from(new Set((g.nodes || []).filter(n => n.category === 'exchange').map(n => n.name))).sort();
        document.getElementById('sg-industry').innerHTML = '<option value="">全部行业</option>' + industries.map(x => `<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join('');
        document.getElementById('sg-exchange').innerHTML = '<option value="">全部交易所</option>' + exchanges.map(x => `<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join('');
      }
      function nodeMatchesFilters(node, keyword, industry, exchange, checked) {
        if (!checked.has(node.category)) return false;
        const attr = node.attributes || {};
        const text = `${node.name} ${attr.code || ''} ${attr.stock_name || ''} ${attr.industry || ''} ${attr.exchange || ''} ${attr.title || ''} ${attr.seat_type || ''} ${attr.trader_alias || ''}`.toLowerCase();
        if (keyword && !text.includes(keyword)) return false;
        if (industry) {
          if (node.category === 'stock' && attr.industry !== industry) return false;
          if (node.category === 'industry' && node.name !== industry) return false;
        }
        if (exchange) {
          if (node.category === 'stock' && attr.exchange !== exchange) return false;
          if (node.category === 'exchange' && node.name !== exchange) return false;
        }
        return true;
      }
      function selectCore(g, keyword, industry, exchange, checked, scale) {
        const allNodes = g.nodes || [];
        const allLinks = g.links || [];
        let limit = scale === 'all' ? allNodes.length : Number(scale || 1500);
        const score = new Map(allNodes.map(n => [n.id, Number(n.value || 0)]));
        allLinks.forEach(l => {
          score.set(l.source, (score.get(l.source) || 0) + Number(l.value || 0) * 0.05);
          score.set(l.target, (score.get(l.target) || 0) + Number(l.value || 0) * 0.05);
        });
        const base = allNodes.filter(n => nodeMatchesFilters(n, keyword, industry, exchange, checked));
        const selectedIds = new Set(base.sort((a,b) => (score.get(b.id) || 0) - (score.get(a.id) || 0)).slice(0, limit).map(n => n.id));
        if (keyword || industry || exchange) {
          allLinks.forEach(l => {
            if (selectedIds.has(l.source) || selectedIds.has(l.target)) {
              const s = allNodes.find(n => n.id === l.source);
              const t = allNodes.find(n => n.id === l.target);
              if (s && checked.has(s.category)) selectedIds.add(s.id);
              if (t && checked.has(t.category)) selectedIds.add(t.id);
            }
          });
        }
        const nodes = allNodes.filter(n => selectedIds.has(n.id));
        const links = allLinks.filter(l => selectedIds.has(l.source) && selectedIds.has(l.target));
        return { nodes, links };
      }
      function draw() {
        currentDate = document.getElementById('sg-date').value;
        const g = graph();
        const keyword = document.getElementById('sg-keyword').value.trim().toLowerCase();
        const industry = document.getElementById('sg-industry').value;
        const exchange = document.getElementById('sg-exchange').value;
        const checked = getCheckedCategories();
        const scale = document.getElementById('sg-scale').value;
        const view = selectCore(g, keyword, industry, exchange, checked, scale);
        const catIndex = key => categoryByKey.get(key)?.idx ?? 0;
        const lineColor = rel => {
          if (rel === 'seat_stock_trade') return '#dc2626';
          if (rel === 'news_stock') return '#475569';
          if (rel === 'stock_industry') return '#0f766e';
          if (rel === 'stock_exchange') return '#7c3aed';
          return '#94a3b8';
        };
        document.getElementById('sg-date-v').textContent = currentDate;
        document.getElementById('sg-stock-v').textContent = g.stats?.stock_count || 0;
        document.getElementById('sg-edge-v').textContent = view.links.length;
        document.getElementById('sg-alt-v').textContent = `${g.stats?.seat_count || 0}/${g.stats?.news_count || 0}`;
        chart.setOption({
          color: categories.map(c => c.color),
          tooltip: {
            confine: true,
            formatter: p => {
              if (p.dataType === 'edge') {
                const attrs = p.data.attributes || {};
                return `${escapeHtml(relationLabels[p.data.type] || p.data.type)}<br/>权重: ${Number(p.data.value || 0).toFixed(2)}${attrs.direction ? '<br/>方向: ' + escapeHtml(attrs.direction) : ''}${attrs.amount ? '<br/>金额: ' + fmtAmount(attrs.amount) : ''}`;
              }
              const a = p.data.attributes || {};
              return `${escapeHtml(p.data.name)}<br/>类型: ${escapeHtml(categoryNames[p.data.category] || '')}${a.industry ? '<br/>行业: ' + escapeHtml(a.industry) : ''}${a.exchange ? '<br/>交易所: ' + escapeHtml(a.exchange) : ''}${a.change_pct != null ? '<br/>涨跌幅: ' + Number(a.change_pct).toFixed(2) + '%' : ''}${a.amount != null ? '<br/>成交额: ' + fmtAmount(Number(a.amount) / 10000) : ''}`;
            }
          },
          legend: [{ data: categoryNames, type: 'scroll', top: 0 }],
          series: [{
            type: 'graph',
            layout: 'force',
            roam: true,
            animationDurationUpdate: 450,
            categories: categoryNames.map(name => ({ name })),
            force: { repulsion: 150, gravity: 0.055, edgeLength: [24, 120], friction: 0.18 },
            label: {
              show: true,
              position: 'right',
              formatter: p => {
                const cat = categoryNames[p.data.category];
                if (['行业','交易所','涨跌状态','交易分层','游资别名'].includes(cat)) return p.data.name;
                if (cat === '股票' && Number(p.data.value || 0) > 16) return (p.data.attributes?.stock_name || p.data.name).slice(0, 6);
                return '';
              },
              fontSize: 10
            },
            emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
            lineStyle: { opacity: 0.28, curveness: 0.08 },
            data: view.nodes.map(n => ({
              ...n,
              category: catIndex(n.category),
              symbolSize: Math.max(6, Math.min(34, Math.sqrt(Number(n.value || 1)) * 3.2)),
              draggable: true
            })),
            links: view.links.map(l => ({
              ...l,
              lineStyle: { color: lineColor(l.type), width: Math.max(0.4, Math.min(4, Math.sqrt(Number(l.value || 1)) / 4)) }
            }))
          }]
        }, true);
      }
      function renderNodeDetail(node) {
        const g = graph();
        const attrs = node.attributes || {};
        const related = (g.links || []).filter(l => l.source === node.id || l.target === node.id)
          .sort((a,b) => Number(b.value || 0) - Number(a.value || 0))
          .slice(0, 24);
        const nodeById = new Map((g.nodes || []).map(n => [n.id, n]));
        document.getElementById('sg-detail').innerHTML = `
          <div class="sg-mini">
            <div class="name">${escapeHtml(node.name)}</div>
            <div class="meta">${Object.entries(attrs).slice(0, 10).map(([k,v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join('<br/>')}</div>
          </div>
          <div class="muted" style="margin:12px 0 4px;">强关联关系</div>
          ${related.map(l => {
            const otherId = l.source === node.id ? l.target : l.source;
            const other = nodeById.get(otherId) || { name: otherId };
            return `<div class="sg-mini"><div class="name">${escapeHtml(other.name)}</div><div class="meta">${escapeHtml(relationLabels[l.type] || l.type)} · 权重 ${Number(l.value || 0).toFixed(2)}</div></div>`;
          }).join('') || '<div class="muted">暂无关联边</div>'}`;
      }
      document.getElementById('sg-date').addEventListener('change', () => { fillFilters(); draw(); });
      document.getElementById('sg-run').addEventListener('click', draw);
      document.getElementById('sg-reset').addEventListener('click', () => {
        document.getElementById('sg-keyword').value = '';
        document.getElementById('sg-industry').value = '';
        document.getElementById('sg-exchange').value = '';
        document.getElementById('sg-scale').value = '1500';
        document.querySelectorAll('.sg-cat').forEach(x => { x.checked = true; });
        currentFocus = null;
        document.getElementById('sg-detail').innerHTML = '点击图中的节点查看属性和强关联边。';
        draw();
      });
      document.getElementById('sg-keyword').addEventListener('keyup', e => { if (e.key === 'Enter') draw(); });
      ['sg-industry','sg-exchange','sg-scale'].forEach(id => document.getElementById(id).addEventListener('change', draw));
      document.querySelectorAll('.sg-cat').forEach(x => x.addEventListener('change', draw));
      chart.on('click', params => {
        if (params.dataType === 'node') {
          currentFocus = params.data.id;
          renderNodeDetail(params.data);
        }
      });
      fillFilters();
      draw();
    }

    function renderMarketCalendar(root, payload) {
      const years = Object.keys(payload.years || {}).sort().reverse();
      if (!years.length) {
        root.innerHTML = '<div class="empty">行业日历数据当前不可用</div>';
        return;
      }
      const styles = `
        <style>
          .cal-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;}
          .cal-wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;}
          .cal-card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:14px;}
          .cal-title{font-size:16px;font-weight:700;margin-bottom:10px;}
          .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;}
          .cal-head,.cal-day{font-size:12px;text-align:center;}
          .cal-head{color:var(--muted);padding:4px 0;}
          .cal-day{border-radius:10px;padding:8px 4px;min-height:56px;border:1px solid #edf0e8;display:flex;flex-direction:column;justify-content:space-between;}
          .cal-day.empty{background:#fafbf8;border-style:dashed;color:#b8c0b4;}
          .cal-day .d{font-weight:700;font-size:12px;}
          .cal-day .l{font-size:10px;line-height:1.15;word-break:break-all;}
          .legend{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px;}
          .legend-item{display:flex;align-items:center;gap:6px;background:#fff;border:1px solid var(--line);border-radius:999px;padding:6px 10px;font-size:12px;}
          .legend-dot{width:12px;height:12px;border-radius:999px;display:inline-block;}
        </style>`;
      root.innerHTML = styles + `
        <div class="stats">
          <div class="stat"><div class="k">年份</div><div class="v" id="mc-year-v">${years[0]}</div></div>
          <div class="stat"><div class="k">交易日数</div><div class="v" id="mc-days-v">0</div></div>
          <div class="stat"><div class="k">活跃行业</div><div class="v" id="mc-industry-v">0</div></div>
        </div>
        <div class="cal-toolbar">
          <select id="mc-year">${years.map(y => `<option value="${y}">${y}</option>`).join('')}</select>
        </div>
        <div class="cal-wrap" id="mc-wrap"></div>
        <div class="legend" id="mc-legend"></div>`;

      const palette = ['#dbeafe','#bfdbfe','#fde68a','#fecaca','#bbf7d0','#ddd6fe','#fecdd3','#a7f3d0','#fdba74','#c7d2fe','#f5d0fe','#bae6fd','#e9d5ff','#fef3c7','#cbd5e1','#99f6e4','#fca5a5','#86efac','#fcd34d','#93c5fd'];
      function buildMonthCard(year, month, lookup, colorMap) {
        const first = new Date(year, month - 1, 1);
        const last = new Date(year, month, 0).getDate();
        const startWeekday = (first.getDay() + 6) % 7;
        const weekNames = ['一','二','三','四','五','六','日'];
        const items = [];
        for (let i = 0; i < startWeekday; i++) items.push('<div class="cal-day empty"></div>');
        for (let day = 1; day <= last; day++) {
          const ds = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
          const item = lookup[ds];
          if (!item) {
            items.push(`<div class="cal-day empty"><div class="d">${day}</div><div class="l">休市</div></div>`);
            continue;
          }
          const bg = colorMap[item.top_industry] || '#f3f4f6';
          items.push(`<div class="cal-day" style="background:${bg};"><div class="d">${day}</div><div class="l">${escapeHtml(item.top_industry)}</div></div>`);
        }
        return `<div class="cal-card"><div class="cal-title">${year}年${month}月</div><div class="cal-grid">${weekNames.map(x => `<div class="cal-head">${x}</div>`).join('')}${items.join('')}</div></div>`;
      }
      function draw() {
        const year = document.getElementById('mc-year').value;
        const rows = payload.years[year] || [];
        const lookup = {};
        const industries = [];
        rows.forEach(r => { lookup[r.date] = r; if (!industries.includes(r.top_industry)) industries.push(r.top_industry); });
        const colorMap = {};
        industries.forEach((name, idx) => { colorMap[name] = palette[idx % palette.length]; });
        document.getElementById('mc-year-v').textContent = year;
        document.getElementById('mc-days-v').textContent = rows.length;
        document.getElementById('mc-industry-v').textContent = industries.length;
        document.getElementById('mc-wrap').innerHTML = Array.from({length:12}, (_, i) => buildMonthCard(Number(year), i + 1, lookup, colorMap)).join('');
        document.getElementById('mc-legend').innerHTML = industries.map(name => `<div class="legend-item"><span class="legend-dot" style="background:${colorMap[name]}"></span>${escapeHtml(name)}</div>`).join('');
      }
      document.getElementById('mc-year').addEventListener('change', draw);
      draw();
    }

    function renderMarketIndustry(root, payload) {
      const records = payload.records || [];
      if (!records.length) {
        root.innerHTML = '<div class="empty">行业强弱数据当前不可用</div>';
        return;
      }
      const top = records.slice(0, 12);
      const bottom = records.slice(-12);
      root.innerHTML = `
        <div class="stats">
          <div class="stat"><div class="k">交易日</div><div class="v">${escapeHtml(payload.trade_date || '-')}</div></div>
          <div class="stat"><div class="k">行业数</div><div class="v">${records.length}</div></div>
        </div>
        <div class="grid">
          <div class="card split-2"><div id="mi-top" class="chart" style="min-height:360px;"></div></div>
          <div class="card split-2"><div id="mi-bottom" class="chart" style="min-height:360px;"></div></div>
          <div class="card"><table><thead><tr><th>行业</th><th>股票数</th><th>平均涨跌幅</th><th>总涨跌幅</th></tr></thead><tbody id="mi-table"></tbody></table></div>
        </div>`;
      document.getElementById('mi-table').innerHTML = records.map(x => `<tr><td>${escapeHtml(x.industry)}</td><td>${x.stock_count}</td><td class="${Number(x.avg_change_pct) >= 0 ? 'buy' : 'sell'}">${Number(x.avg_change_pct).toFixed(2)}%</td><td class="${Number(x.total_change_pct) >= 0 ? 'buy' : 'sell'}">${Number(x.total_change_pct).toFixed(2)}%</td></tr>`).join('');
      echarts.init(document.getElementById('mi-top')).setOption({
        xAxis: { type: 'value' }, yAxis: { type: 'category', data: top.map(x => x.industry) },
        series: [{ type: 'bar', data: top.map(x => x.total_change_pct), itemStyle: { color: '#0f766e' } }]
      });
      echarts.init(document.getElementById('mi-bottom')).setOption({
        xAxis: { type: 'value' }, yAxis: { type: 'category', data: bottom.map(x => x.industry) },
        series: [{ type: 'bar', data: bottom.map(x => x.total_change_pct), itemStyle: { color: '#b45309' } }]
      });
    }

    function renderStockNews(root, payload) {
      const summaries = payload.stock_summaries || [];
      const stockNews = payload.stock_news || {};
      const totalArticles = payload.total_articles || 0;
      const stockCodes = payload.stock_codes || [];

      if (!summaries.length) {
        root.innerHTML = '<div class="empty">暂无个股新闻数据，请先运行新闻同步</div>';
        return;
      }

      const styles = `
        <style>
          .news-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;align-items:center;}
          .news-toolbar select,.news-toolbar input{min-width:160px;}
          .news-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px;}
          .news-stat{background:#f8faf7;border:1px solid var(--line);border-radius:16px;padding:14px;}
          .news-stat .k{font-size:12px;color:var(--muted);margin-bottom:6px;}
          .news-stat .v{font-size:24px;font-weight:700;}
          .news-stock-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-bottom:20px;}
          .news-stock-card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px;cursor:pointer;transition:all 0.2s;}
          .news-stock-card:hover{border-color:var(--accent);box-shadow:0 4px 16px rgba(22,78,99,0.1);}
          .news-stock-card.selected{border-color:var(--accent);background:#f0f7f4;}
          .news-stock-card .stock-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;}
          .news-stock-card .stock-code{font-weight:700;font-size:15px;}
          .news-stock-card .news-count{background:var(--accent);color:#fff;border-radius:999px;padding:2px 10px;font-size:12px;}
          .news-stock-card .latest-title{font-size:13px;color:var(--muted);line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
          .news-stock-card .latest-time{font-size:11px;color:#999;margin-top:6px;}
          .sentiment-bar{display:flex;gap:6px;margin-top:8px;}
          .sentiment-tag{font-size:11px;padding:2px 8px;border-radius:999px;}
          .sentiment-tag.positive{background:#dcfce7;color:#166534;}
          .sentiment-tag.negative{background:#fee2e2;color:#991b1b;}
          .sentiment-tag.neutral{background:#f3f4f6;color:#6b7280;}
          .news-detail{margin-top:16px;}
          .news-detail-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;}
          .news-detail-header h3{margin:0;font-size:18px;}
          .news-detail-header .back-btn{border:1px solid var(--line);background:#fff;border-radius:12px;padding:8px 14px;cursor:pointer;font-size:13px;}
          .news-timeline{position:relative;padding-left:24px;}
          .news-timeline::before{content:'';position:absolute;left:8px;top:0;bottom:0;width:2px;background:var(--line);}
          .news-item{position:relative;margin-bottom:16px;padding:14px;background:#fff;border:1px solid var(--line);border-radius:14px;}
          .news-item::before{content:'';position:absolute;left:-20px;top:18px;width:10px;height:10px;border-radius:50%;background:var(--accent);border:2px solid #fff;}
          .news-item .news-title{font-weight:600;font-size:14px;margin-bottom:6px;line-height:1.4;}
          .news-item .news-title a{color:var(--text);text-decoration:none;}
          .news-item .news-title a:hover{color:var(--accent);text-decoration:underline;}
          .news-item .news-meta{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-bottom:6px;}
          .news-item .news-content{font-size:13px;color:#444;line-height:1.6;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}
          .news-item .news-content.expanded{-webkit-line-clamp:unset;}
          .news-item .expand-btn{font-size:12px;color:var(--accent);cursor:pointer;margin-top:4px;border:none;background:none;padding:0;}
          .news-overview{margin-top:16px;}
          .news-overview .overview-title{font-size:16px;font-weight:700;margin-bottom:12px;}
          .news-overview .all-news-list .news-item{margin-bottom:12px;}
        </style>`;

      // 概览模式：显示股票卡片列表
      function renderOverview() {
        root.innerHTML = styles + `
          <div class="news-stats">
            <div class="news-stat"><div class="k">关联股票</div><div class="v">${stockCodes.length}</div></div>
            <div class="news-stat"><div class="k">新闻总数</div><div class="v">${totalArticles}</div></div>
            <div class="news-stat"><div class="k">数据来源</div><div class="v" style="font-size:14px;">akshare</div></div>
          </div>
          <div class="news-toolbar">
            <input id="sn-search" placeholder="搜索股票代码或名称">
            <select id="sn-sentiment">
              <option value="">全部情绪</option>
              <option value="利好">利好</option>
              <option value="利空">利空</option>
              <option value="中性">中性</option>
            </select>
            <button class="primary" id="sn-filter-btn">筛选</button>
          </div>
          <div class="news-stock-grid" id="sn-grid"></div>
          <div class="news-overview" id="sn-overview">
            <div class="overview-title">全部最新新闻</div>
            <div class="all-news-list" id="sn-all-news"></div>
          </div>`;

        function drawCards() {
          const kw = document.getElementById('sn-search').value.trim().toLowerCase();
          const sentiment = document.getElementById('sn-sentiment').value;
          const filtered = summaries.filter(s => {
            const matchKw = !kw || s.stock_code.includes(kw);
            const matchSentiment = !sentiment || (s.sentiment_summary[sentiment] || 0) > 0;
            return matchKw && matchSentiment;
          });

          document.getElementById('sn-grid').innerHTML = filtered.map(s => {
            const ss = s.sentiment_summary || {};
            const tags = [];
            if (ss['利好'] > 0) tags.push(`<span class="sentiment-tag positive">利好${ss['利好']}</span>`);
            if (ss['利空'] > 0) tags.push(`<span class="sentiment-tag negative">利空${ss['利空']}</span>`);
            if (ss['中性'] > 0) tags.push(`<span class="sentiment-tag neutral">中性${ss['中性']}</span>`);
            return `<div class="news-stock-card" data-code="${escapeHtml(s.stock_code)}">
              <div class="stock-header">
                <span class="stock-code">${escapeHtml(s.stock_code)}</span>
                <span class="news-count">${s.news_count}条</span>
              </div>
              <div class="latest-title">${escapeHtml(s.latest_news)}</div>
              <div class="sentiment-bar">${tags.join('')}</div>
              <div class="latest-time">${escapeHtml(s.latest_time)}</div>
            </div>`;
          }).join('');

          // 显示全部最新新闻（取每个股票的第一条）
          const allLatest = [];
          for (const code of Object.keys(stockNews)) {
            const news = stockNews[code];
            if (news && news.length) {
              allLatest.push({...news[0], stock_code: code});
            }
          }
          allLatest.sort((a, b) => (b.published_at || '').localeCompare(a.published_at || ''));
          document.getElementById('sn-all-news').innerHTML = allLatest.slice(0, 30).map(n => renderNewsItem(n)).join('');

          // 绑定卡片点击
          document.querySelectorAll('.news-stock-card').forEach(card => {
            card.addEventListener('click', () => {
              const code = card.dataset.code;
              renderDetail(code);
            });
          });
        }

        document.getElementById('sn-filter-btn').addEventListener('click', drawCards);
        document.getElementById('sn-search').addEventListener('keyup', e => { if (e.key === 'Enter') drawCards(); });
        drawCards();
      }

      // 详情模式：显示某只股票的新闻时间线
      function renderDetail(stockCode) {
        const news = stockNews[stockCode] || [];
        const summary = summaries.find(s => s.stock_code === stockCode) || {};
        const ss = summary.sentiment_summary || {};

        root.innerHTML = styles + `
          <div class="news-detail">
            <div class="news-detail-header">
              <h3>📰 ${escapeHtml(stockCode)} 相关新闻 <span style="font-size:14px;color:var(--muted);">(${news.length}条)</span></h3>
              <button class="back-btn" id="sn-back">← 返回列表</button>
            </div>
            <div class="news-stats">
              <div class="news-stat"><div class="k">新闻总数</div><div class="v">${news.length}</div></div>
              <div class="news-stat"><div class="k">利好</div><div class="v" style="color:#166534;">${ss['利好'] || 0}</div></div>
              <div class="news-stat"><div class="k">利空</div><div class="v" style="color:#991b1b;">${ss['利空'] || 0}</div></div>
              <div class="news-stat"><div class="k">中性</div><div class="v" style="color:#6b7280;">${ss['中性'] || 0}</div></div>
            </div>
            <div class="news-timeline" id="sn-timeline"></div>
          </div>`;

        document.getElementById('sn-timeline').innerHTML = news.map(n => renderNewsItem(n)).join('');
        document.getElementById('sn-back').addEventListener('click', renderOverview);

        // 绑定展开/收起按钮
        document.querySelectorAll('.expand-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            const content = btn.previousElementSibling;
            if (content.classList.contains('expanded')) {
              content.classList.remove('expanded');
              btn.textContent = '展开全文';
            } else {
              content.classList.add('expanded');
              btn.textContent = '收起';
            }
          });
        });
      }

      function renderNewsItem(n) {
        const sentimentClass = n.sentiment === '利好' ? 'positive' : n.sentiment === '利空' ? 'negative' : 'neutral';
        const titleHtml = n.url ? `<a href="${escapeHtml(n.url)}" target="_blank" rel="noopener">${escapeHtml(n.title)}</a>` : escapeHtml(n.title);
        const meta = [];
        if (n.published_at) meta.push(`🕐 ${escapeHtml(n.published_at)}`);
        if (n.source) meta.push(`📰 ${escapeHtml(n.source)}`);
        if (n.event_type && n.event_type !== '其他') meta.push(`📌 ${escapeHtml(n.event_type)}`);
        if (n.sentiment) meta.push(`<span class="sentiment-tag ${sentimentClass}">${escapeHtml(n.sentiment)}</span>`);
        const content = n.content || n.summary || '';
        const needExpand = content.length > 120;
        return `<div class="news-item">
          <div class="news-title">${titleHtml}</div>
          <div class="news-meta">${meta.join('')}</div>
          ${content ? `<div class="news-content">${escapeHtml(content)}</div>` : ''}
          ${needExpand ? '<button class="expand-btn">展开全文</button>' : ''}
        </div>`;
      }

      renderOverview();
    }

    /* ==================== AI 分析 ==================== */
    function renderAIAnalysis(root, payload) {
      if (!payload || !payload.stock_codes || payload.stock_codes.length === 0) {
        root.innerHTML = '<div class="empty">暂无可分析的股票数据，请先同步龙虎榜或新闻。</div>';
        return;
      }

      const stockCodes = payload.stock_codes;
      const stockContexts = payload.stock_contexts || {};

      // 从 localStorage 读取配置
      const savedBaseUrl = localStorage.getItem('ai_base_url') || '';
      const savedKey = localStorage.getItem('ai_api_key') || '';
      const savedModel = localStorage.getItem('ai_model') || '';

      const styles = `<style>
        .ai-config { display:grid; grid-template-columns:1fr 1fr 1fr auto; gap:10px; align-items:end; margin-bottom:18px; }
        .ai-config label { display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }
        .ai-config input { width:100%; }
        .ai-stock-bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:16px; }
        .ai-stock-bar select { min-width:200px; }
        .ai-context { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:18px; }
        .ai-context-card { background:#f8faf7; border:1px solid var(--line); border-radius:14px; padding:14px; max-height:320px; overflow-y:auto; }
        .ai-context-card h4 { margin:0 0 10px; font-size:14px; color:var(--accent); }
        .ai-news-mini { font-size:13px; margin-bottom:8px; padding-bottom:8px; border-bottom:1px solid #edf0e8; }
        .ai-news-mini:last-child { border-bottom:none; margin-bottom:0; padding-bottom:0; }
        .ai-news-mini .t { font-weight:600; }
        .ai-news-mini .m { font-size:11px; color:var(--muted); margin-top:2px; }
        .ai-dt-mini { font-size:13px; margin-bottom:8px; }
        .ai-dt-mini .d { font-weight:600; color:var(--accent); }
        .ai-result { background:#fff; border:1px solid var(--line); border-radius:14px; padding:18px; min-height:200px; white-space:pre-wrap; line-height:1.7; font-size:14px; }
        .ai-result .thinking { color:var(--muted); font-style:italic; }
        .ai-actions { display:flex; gap:10px; margin-bottom:14px; }
        .ai-prompt-area { margin-bottom:14px; }
        .ai-prompt-area textarea { width:100%; min-height:60px; border:1px solid var(--line); border-radius:12px; padding:10px; font-size:14px; font-family:inherit; resize:vertical; }
        .ai-status { font-size:12px; color:var(--muted); margin-top:8px; }
        @media (max-width:980px) { .ai-config { grid-template-columns:1fr; } .ai-context { grid-template-columns:1fr; } }
      </style>`;

      root.innerHTML = styles + `
        <h3 style="margin:0 0 16px;">🤖 AI 智能分析</h3>
        <div class="ai-config" id="ai-config">
          <div><label>API Base URL</label><input id="ai-baseurl" placeholder="https://api.openai.com/v1" value="${escapeHtml(savedBaseUrl)}"></div>
          <div><label>API Key</label><input id="ai-key" type="password" placeholder="sk-..." value="${escapeHtml(savedKey)}"></div>
          <div><label>模型名称</label><input id="ai-model" placeholder="gpt-4o-mini" value="${escapeHtml(savedModel)}"></div>
          <div><button class="primary" id="ai-save-config" style="margin-top:18px;">💾 保存</button></div>
        </div>
        <div class="ai-stock-bar">
          <select id="ai-stock-select">
            <option value="">-- 选择股票 --</option>
            ${stockCodes.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('')}
          </select>
          <button class="primary" id="ai-analyze-btn">🔍 开始分析</button>
          <button id="ai-stop-btn" style="display:none;">⏹ 停止</button>
        </div>
        <div class="ai-prompt-area">
          <textarea id="ai-prompt" placeholder="可自定义分析提示词，留空使用默认提示词。例如：请从资金面、消息面、技术面三个维度分析该股票的短期走势。">请从资金面（龙虎榜数据）、消息面（近期新闻）两个维度，综合分析该股票的近期走势和市场关注度，给出简要的投资参考意见。</textarea>
        </div>
        <div id="ai-context-area"></div>
        <div id="ai-result-area"></div>
        <div id="ai-status" class="ai-status"></div>
      `;

      // 保存配置
      document.getElementById('ai-save-config').addEventListener('click', () => {
        localStorage.setItem('ai_base_url', document.getElementById('ai-baseurl').value.trim());
        localStorage.setItem('ai_api_key', document.getElementById('ai-key').value.trim());
        localStorage.setItem('ai_model', document.getElementById('ai-model').value.trim());
        document.getElementById('ai-status').textContent = '✅ 配置已保存到本地浏览器';
        setTimeout(() => { document.getElementById('ai-status').textContent = ''; }, 2000);
      });

      // 股票选择变化时显示上下文
      const stockSelect = document.getElementById('ai-stock-select');
      stockSelect.addEventListener('change', () => {
        const code = stockSelect.value;
        const ctxArea = document.getElementById('ai-context-area');
        if (!code) { ctxArea.innerHTML = ''; return; }
        const ctx = stockContexts[code];
        if (!ctx) { ctxArea.innerHTML = '<div class="empty">未找到该股票的上下文数据</div>'; return; }
        renderContext(ctxArea, ctx);
      });

      function renderContext(area, ctx) {
        const news = ctx.news || [];
        const dt = ctx.dragon_tiger || [];
        let html = '<div class="ai-context">';

        // 新闻卡片
        html += '<div class="ai-context-card"><h4>📰 近期新闻 (' + news.length + '条)</h4>';
        if (news.length === 0) {
          html += '<div class="muted">暂无新闻数据</div>';
        } else {
          html += news.slice(0, 10).map(n => {
            const sCls = n.sentiment === '利好' ? 'positive' : n.sentiment === '利空' ? 'negative' : 'neutral';
            return '<div class="ai-news-mini">' +
              '<div class="t">' + escapeHtml(n.title) + '</div>' +
              '<div class="m">' + escapeHtml(n.published_at || '') + ' · ' + escapeHtml(n.source || '') +
              ' <span class="sentiment-tag ' + sCls + '">' + escapeHtml(n.sentiment || '中性') + '</span></div>' +
              '</div>';
          }).join('');
        }
        html += '</div>';

        // 龙虎榜卡片
        html += '<div class="ai-context-card"><h4>📊 龙虎榜数据 (' + dt.length + '个交易日)</h4>';
        if (dt.length === 0) {
          html += '<div class="muted">暂无龙虎榜数据</div>';
        } else {
          html += dt.slice(0, 5).map(d => {
            const ops = (d.operations || []).slice(0, 5);
            return '<div class="ai-dt-mini"><div class="d">📅 ' + escapeHtml(d.date) + '</div>' +
              ops.map(op => {
                const dir = op.direction === '买入' ? 'buy' : 'sell';
                return '<div style="font-size:12px;margin-left:8px;">' +
                  '<span class="' + dir + '">' + escapeHtml(op.direction || '') + '</span> ' +
                  escapeHtml(op.seatName || op.seat_name || '') +
                  (op.amount != null ? ' · ' + Number(op.amount).toFixed(0) + '万' : '') +
                  '</div>';
              }).join('') +
              '</div>';
          }).join('');
        }
        html += '</div></div>';
        area.innerHTML = html;
      }

      // 分析按钮
      let abortController = null;
      document.getElementById('ai-analyze-btn').addEventListener('click', async () => {
        const code = stockSelect.value;
        if (!code) { alert('请先选择一只股票'); return; }

        const baseUrl = (document.getElementById('ai-baseurl').value || localStorage.getItem('ai_base_url') || '').replace(/\\/+$/, '');
        const apiKey = document.getElementById('ai-key').value || localStorage.getItem('ai_api_key') || '';
        const model = document.getElementById('ai-model').value || localStorage.getItem('ai_model') || '';

        if (!baseUrl || !apiKey || !model) {
          alert('请先配置 API Base URL、API Key 和模型名称');
          return;
        }

        const ctx = stockContexts[code] || {};
        const userPrompt = document.getElementById('ai-prompt').value.trim() ||
          '请从资金面（龙虎榜数据）、消息面（近期新闻）两个维度，综合分析该股票的近期走势和市场关注度，给出简要的投资参考意见。';

        // 构建上下文文本
        let contextText = '## 股票代码: ' + code + '\\n\\n';
        const news = ctx.news || [];
        if (news.length > 0) {
          contextText += '### 近期新闻\\n';
          news.forEach((n, i) => {
            contextText += (i+1) + '. [' + (n.sentiment || '中性') + '] ' + n.title +
              ' (' + (n.source || '') + ', ' + (n.published_at || '') + ')\\n';
            if (n.content) contextText += '   摘要: ' + n.content.substring(0, 200) + '\\n';
          });
          contextText += '\\n';
        }
        const dt = ctx.dragon_tiger || [];
        if (dt.length > 0) {
          contextText += '### 龙虎榜数据\\n';
          dt.forEach(d => {
            contextText += '日期: ' + d.date + '\\n';
            (d.operations || []).forEach(op => {
              contextText += '  ' + (op.direction || '') + ' ' + (op.seatName || op.seat_name || '') +
                (op.amount != null ? ' 金额:' + op.amount + '万' : '') + '\\n';
            });
          });
        }

        const resultArea = document.getElementById('ai-result-area');
        const statusEl = document.getElementById('ai-status');
        const analyzeBtn = document.getElementById('ai-analyze-btn');
        const stopBtn = document.getElementById('ai-stop-btn');

        resultArea.innerHTML = '<div class="ai-result" id="ai-stream"></div>';
        const streamEl = document.getElementById('ai-stream');
        streamEl.textContent = '⏳ 正在请求 AI 分析...';
        statusEl.textContent = '';
        analyzeBtn.disabled = true;
        stopBtn.style.display = 'inline-block';

        abortController = new AbortController();

        try {
          const apiUrl = baseUrl + '/chat/completions';
          const body = {
            model: model,
            messages: [
              { role: 'system', content: '你是一位专业的 A 股市场分析师。请基于提供的股票数据和新闻信息，给出专业、客观的分析。回答使用中文。' },
              { role: 'user', content: contextText + '\\n---\\n' + userPrompt }
            ],
            stream: true,
            temperature: 0.7,
            max_tokens: 2000,
          };

          const resp = await fetch(apiUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer ' + apiKey,
            },
            body: JSON.stringify(body),
            signal: abortController.signal,
          });

          if (!resp.ok) {
            const errText = await resp.text();
            throw new Error('API 请求失败 (' + resp.status + '): ' + errText.substring(0, 300));
          }

          streamEl.textContent = '';
          const reader = resp.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          let fullText = '';
          let tokenCount = 0;

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed || !trimmed.startsWith('data:')) continue;
              const data = trimmed.slice(5).trim();
              if (data === '[DONE]') continue;
              try {
                const json = JSON.parse(data);
                const delta = json.choices && json.choices[0] && json.choices[0].delta;
                if (delta && delta.content) {
                  fullText += delta.content;
                  tokenCount++;
                  streamEl.textContent = fullText;
                  streamEl.scrollTop = streamEl.scrollHeight;
                }
              } catch (e) { /* skip malformed chunks */ }
            }
          }

          statusEl.textContent = '✅ 分析完成，共 ' + tokenCount + ' 个 token 片段';
        } catch (err) {
          if (err.name === 'AbortError') {
            streamEl.textContent += '\\n\\n⏹ 已停止生成';
            statusEl.textContent = '已手动停止';
          } else {
            streamEl.textContent = '❌ 错误: ' + escapeHtml(err.message);
            statusEl.textContent = '请求失败';
          }
        } finally {
          analyzeBtn.disabled = false;
          stopBtn.style.display = 'none';
          abortController = null;
        }
      });

      // 停止按钮
      document.getElementById('ai-stop-btn').addEventListener('click', () => {
        if (abortController) abortController.abort();
      });
    }

    async function main() {
      bindTabs();
      await loadManifest();
      await loadTab('dragon_query');
    }
    main();
  </script>
</body>
</html>"""
