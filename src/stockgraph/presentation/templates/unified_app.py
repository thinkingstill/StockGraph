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
      <button class="tab-btn" data-tab="market_calendar">行业日历</button>
      <button class="tab-btn" data-tab="market_industry">行业强弱</button>
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

    <section class="panel" id="panel-market_calendar">
      <div id="marketCalendarRoot" class="empty">正在加载行业日历数据...</div>
    </section>

    <section class="panel" id="panel-market_industry">
      <div id="marketIndustryRoot" class="empty">正在加载行业强弱数据...</div>
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
        market_calendar: 'marketCalendarRoot',
        market_industry: 'marketIndustryRoot',
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
        if (name === 'market_calendar') renderMarketCalendar(root, payload);
        if (name === 'market_industry') renderMarketIndustry(root, payload);
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

    async function main() {
      bindTabs();
      await loadManifest();
      await loadTab('dragon_query');
    }
    main();
  </script>
</body>
</html>"""
