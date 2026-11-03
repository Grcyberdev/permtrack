/**
 * PermTrack Enterprise — Reusable High-Precision UI Components
 * Quiet Luxury & Calm Executive Polish
 */
const AppComponents = {
  renderCategoryBadge(category) {
    const cat = String(category || 'IMFL').toUpperCase();
    if (cat === 'BEER') {
      return `<span class="cat-badge cat-beer"><span class="cat-dot dot-beer"></span>Beer</span>`;
    }
    if (cat === 'CS') {
      return `<span class="cat-badge cat-cs"><span class="cat-dot dot-cs"></span>CS</span>`;
    }
    return `<span class="cat-badge cat-imfl"><span class="cat-dot dot-imfl"></span>IMFL</span>`;
  },

  renderDeltaBadge(pct, label = 'vs prior') {
    if (pct === null || pct === undefined || isNaN(pct)) {
      return `<span class="kpi-delta-badge delta-neutral">—</span>`;
    }
    const val = Number(pct);
    if (val > 0) {
      return `<span class="kpi-delta-badge delta-up" title="${label}">+${val.toFixed(1)}%</span>`;
    }
    if (val < 0) {
      return `<span class="kpi-delta-badge delta-down" title="${label}">${val.toFixed(1)}%</span>`;
    }
    return `<span class="kpi-delta-badge delta-neutral" title="${label}">0.0%</span>`;
  },

  renderAgingBadge(days) {
    const d = parseInt(days || 0, 10);
    if (d <= 0) {
      return `<span class="aging-badge aging-today"><span class="status-dot dot-success"></span>Today</span>`;
    }
    if (d === 1) {
      return `<span class="aging-badge aging-yesterday"><span class="status-dot dot-warning"></span>Yesterday</span>`;
    }
    return `<span class="aging-badge aging-critical"><span class="status-dot dot-danger"></span>+${d}d Aging</span>`;
  },

  /**
   * Generates a lightweight inline SVG sparkline
   */
  renderSparklineSVG(dataArray, width = 84, height = 20, strokeColor = 'var(--accent-amber)') {
    if (!dataArray || dataArray.length < 2) {
      return `<span style="color:var(--text-muted);font-size:0.75rem;">—</span>`;
    }
    const max = Math.max(...dataArray, 1);
    const min = Math.min(...dataArray, 0);
    const range = max - min || 1;
    const padding = 2;
    const effH = height - padding * 2;
    const step = width / (dataArray.length - 1);

    const points = dataArray.map((v, i) => {
      const x = i * step;
      const y = height - padding - ((v - min) / range) * effH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    return `
      <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="overflow:visible;vertical-align:middle;">
        <polyline fill="none" stroke="${strokeColor}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" points="${points}" />
      </svg>
    `;
  },

  /**
   * Renders high-precision SVG stacked bar & trend line timeline chart
   * with custom floating HTML tooltip on hover and click-to-drill
   */
  renderTimelineChartSVG(dailySeries, onDayClickFnName = 'window.handleDayClick') {
    if (!dailySeries || dailySeries.length === 0) {
      return `<div style="text-align:center;padding:2rem;color:var(--text-muted);">No daily activity in this horizon</div>`;
    }

    const w = 840;
    const h = 220;
    const padL = 40;
    const padR = 40;
    const padT = 20;
    const padB = 30;
    const chartW = w - padL - padR;
    const chartH = h - padT - padB;

    const maxCases = Math.max(...dailySeries.map(d => d.cases || 0), 10);
    const maxMrp = Math.max(...dailySeries.map(d => d.mrp || 0), 1000);
    const numDays = dailySeries.length;
    const barWidth = Math.max(8, Math.min(32, (chartW / numDays) * 0.65));
    const stepX = chartW / numDays;

    let barsSVG = '';
    let mrpPoints = [];

    dailySeries.forEach((d, idx) => {
      const cx = padL + idx * stepX + stepX / 2;
      const bTotal = d.cases || 0;
      const bBeer = d.beer_cases || 0;
      const bImfl = d.imfl_cases || 0;
      const bCs = d.cs_cases || 0;

      // Heights
      const hTotal = (bTotal / maxCases) * chartH;
      const hBeer = (bBeer / maxCases) * chartH;
      const hImfl = (bImfl / maxCases) * chartH;
      const hCs = (bCs / maxCases) * chartH;

      const yBottom = padT + chartH;
      const yCs = yBottom - hCs;
      const yImfl = yCs - hImfl;
      const yBeer = yImfl - hBeer;

      const rx = cx - barWidth / 2;

      const tooltipData = JSON.stringify({
        date: d.date_str,
        day: d.day,
        total: AppUtils.formatNumber(bTotal),
        beer: AppUtils.formatNumber(bBeer),
        imfl: AppUtils.formatNumber(bImfl),
        cs: AppUtils.formatNumber(bCs),
        mrp: AppUtils.formatCurrencyINR(d.mrp, true)
      }).replace(/"/g, '&quot;');

      // Bar Segments (Bottom: CS, Mid: IMFL, Top: Beer)
      barsSVG += `
        <g class="chart-day-group" style="cursor:pointer;" 
           data-tooltip="${tooltipData}"
           onmouseenter="AppComponents.showChartTooltip(event, this)"
           onmouseleave="AppComponents.hideChartTooltip()"
           onclick="${onDayClickFnName}('${d.date_key}')">
          <!-- Background hover hit target -->
          <rect x="${cx - stepX/2}" y="${padT}" width="${stepX}" height="${chartH}" fill="transparent" class="chart-hit-area" />
          ${hCs > 0 ? `<rect x="${rx}" y="${yCs}" width="${barWidth}" height="${hCs}" fill="var(--brand-cs)" opacity="0.85" rx="1"/>` : ''}
          ${hImfl > 0 ? `<rect x="${rx}" y="${yImfl}" width="${barWidth}" height="${hImfl}" fill="var(--brand-imfl)" opacity="0.85" rx="1"/>` : ''}
          ${hBeer > 0 ? `<rect x="${rx}" y="${yBeer}" width="${barWidth}" height="${hBeer}" fill="var(--brand-beer)" opacity="0.85" rx="2"/>` : ''}
          <!-- X-Axis label -->
          <text x="${cx}" y="${yBottom + 16}" fill="var(--text-muted)" font-size="10" font-family="var(--font-mono)" text-anchor="middle">
            ${d.date_key.slice(6, 8)}
          </text>
        </g>
      `;

      // MRP Line point
      const mrpY = padT + chartH - ((d.mrp || 0) / maxMrp) * chartH;
      mrpPoints.push(`${cx.toFixed(1)},${mrpY.toFixed(1)}`);
    });

    const mrpPolyline = mrpPoints.join(' ');

    return `
      <div style="position:relative;width:100%;overflow-x:auto;" id="timeline-chart-wrapper">
        <svg viewBox="0 0 ${w} ${h}" style="width:100%;min-width:600px;height:auto;display:block;">
          <!-- Grid lines -->
          <line x1="${padL}" y1="${padT}" x2="${w - padR}" y2="${padT}" stroke="var(--border-hairline)" stroke-dasharray="3,3" />
          <line x1="${padL}" y1="${padT + chartH/2}" x2="${w - padR}" y2="${padT + chartH/2}" stroke="var(--border-hairline)" stroke-dasharray="3,3" />
          <line x1="${padL}" y1="${padT + chartH}" x2="${w - padR}" y2="${padT + chartH}" stroke="var(--border-strong)" />

          <!-- Bars -->
          ${barsSVG}

          <!-- MRP Trend Line -->
          <polyline fill="none" stroke="var(--accent-amber)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" points="${mrpPolyline}" />
          ${dailySeries.map((d, idx) => {
            const [x, y] = mrpPoints[idx].split(',');
            return `<circle cx="${x}" cy="${y}" r="3" fill="#090B10" stroke="var(--accent-amber)" stroke-width="1.8" />`;
          }).join('')}
        </svg>
        <div id="chart-floating-tooltip" class="chart-floating-tooltip"></div>
      </div>
      <div style="display:flex;align-items:center;justify-content:center;gap:1.5rem;margin-top:0.6rem;font-size:0.75rem;color:var(--text-secondary);">
        <span style="display:flex;align-items:center;gap:5px;"><span class="cat-dot dot-beer"></span>Beer</span>
        <span style="display:flex;align-items:center;gap:5px;"><span class="cat-dot dot-imfl"></span>IMFL</span>
        <span style="display:flex;align-items:center;gap:5px;"><span class="cat-dot dot-cs"></span>CS</span>
        <span style="display:flex;align-items:center;gap:5px;"><span style="width:14px;height:2px;background:var(--accent-amber);display:inline-block;border-radius:1px;"></span>MRP Trend</span>
      </div>
    `;
  },

  showChartTooltip(event, el) {
    const raw = el.getAttribute('data-tooltip');
    if (!raw) return;
    try {
      const data = JSON.parse(raw);
      const tip = document.getElementById('chart-floating-tooltip');
      if (!tip) return;
      tip.innerHTML = `
        <div style="font-weight:700;color:var(--text-primary);margin-bottom:3px;">${data.date} <span style="font-weight:400;color:var(--text-muted);">(${data.day})</span></div>
        <div style="display:flex;justify-content:space-between;gap:12px;color:var(--text-secondary);font-size:0.75rem;">
          <span>Total Dispatched:</span><strong style="color:var(--text-primary);">${data.total} cs</strong>
        </div>
        <div style="display:flex;justify-content:space-between;gap:12px;font-size:0.75rem;margin-top:2px;">
          <span><span class="cat-dot dot-beer"></span> ${data.beer} cs</span>
          <span><span class="cat-dot dot-imfl"></span> ${data.imfl} cs</span>
          <span><span class="cat-dot dot-cs"></span> ${data.cs} cs</span>
        </div>
        <div style="display:flex;justify-content:space-between;gap:12px;margin-top:4px;padding-top:4px;border-top:1px solid var(--border-hairline);color:var(--accent-amber);font-size:0.75rem;font-weight:700;">
          <span>Turnover (MRP):</span><span>${data.mrp}</span>
        </div>
      `;
      tip.style.display = 'block';

      const rect = el.getBoundingClientRect();
      const wrapRect = document.getElementById('timeline-chart-wrapper').getBoundingClientRect();
      const left = rect.left - wrapRect.left + (rect.width / 2) - 80;
      tip.style.left = Math.max(10, Math.min(wrapRect.width - 180, left)) + 'px';
      tip.style.top = '15px';
    } catch (e) {}
  },

  hideChartTooltip() {
    const tip = document.getElementById('chart-floating-tooltip');
    if (tip) tip.style.display = 'none';
  }
};

window.AppComponents = AppComponents;
