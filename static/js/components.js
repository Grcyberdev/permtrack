/**
 * PermTrack Enterprise — Reusable High-Precision UI Components
 */
const AppComponents = {
  renderCategoryBadge(category) {
    const cat = String(category || 'IMFL').toUpperCase();
    if (cat === 'BEER') {
      return `<span class="cat-badge cat-beer">🍺 BEER</span>`;
    }
    if (cat === 'CS') {
      return `<span class="cat-badge cat-cs">🍶 CS</span>`;
    }
    return `<span class="cat-badge cat-imfl">🥃 IMFL</span>`;
  },

  renderDeltaBadge(pct, label = 'vs prior') {
    if (pct === null || pct === undefined || isNaN(pct)) {
      return `<span class="kpi-delta-badge delta-neutral">—</span>`;
    }
    const val = Number(pct);
    if (val > 0) {
      return `<span class="kpi-delta-badge delta-up" title="${label}">▲ +${val.toFixed(1)}%</span>`;
    }
    if (val < 0) {
      return `<span class="kpi-delta-badge delta-down" title="${label}">▼ ${val.toFixed(1)}%</span>`;
    }
    return `<span class="kpi-delta-badge delta-neutral" title="${label}">0.0%</span>`;
  },

  renderAgingBadge(days) {
    const d = parseInt(days || 0, 10);
    if (d <= 0) {
      return `<span class="aging-badge aging-today">🟢 Fresh (0d)</span>`;
    }
    if (d === 1) {
      return `<span class="aging-badge aging-yesterday">🟡 +1d Yesterday</span>`;
    }
    return `<span class="aging-badge aging-critical">🔴 +${d}d Carry-Over</span>`;
  },

  /**
   * Generates a lightweight inline SVG sparkline
   */
  renderSparklineSVG(dataArray, width = 90, height = 24, strokeColor = 'var(--accent-amber)') {
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
        <polyline fill="none" stroke="${strokeColor}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" points="${points}" />
      </svg>
    `;
  },

  /**
   * Renders high-precision SVG stacked bar & trend line timeline chart
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

      // Bar Segments (Bottom: CS, Mid: IMFL, Top: Beer)
      barsSVG += `
        <g class="chart-day-group" style="cursor:pointer;" onclick="${onDayClickFnName}('${d.date_key}')">
          <title>${d.date_str} (${d.day})\nTotal: ${AppUtils.formatNumber(bTotal)} cs\nBeer: ${AppUtils.formatNumber(bBeer)} cs\nIMFL: ${AppUtils.formatNumber(bImfl)} cs\nCS: ${AppUtils.formatNumber(bCs)} cs\nMRP: ${AppUtils.formatCurrencyINR(d.mrp)}</title>
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
      <div style="position:relative;width:100%;overflow-x:auto;">
        <svg viewBox="0 0 ${w} ${h}" style="width:100%;min-width:600px;height:auto;display:block;">
          <!-- Grid lines -->
          <line x1="${padL}" y1="${padT}" x2="${w - padR}" y2="${padT}" stroke="var(--border-hairline)" stroke-dasharray="3,3" />
          <line x1="${padL}" y1="${padT + chartH/2}" x2="${w - padR}" y2="${padT + chartH/2}" stroke="var(--border-hairline)" stroke-dasharray="3,3" />
          <line x1="${padL}" y1="${padT + chartH}" x2="${w - padR}" y2="${padT + chartH}" stroke="var(--border-strong)" />

          <!-- Bars -->
          ${barsSVG}

          <!-- MRP Trend Line -->
          <polyline fill="none" stroke="var(--accent-amber)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="${mrpPolyline}" style="filter:drop-shadow(0 2px 4px rgba(245,158,11,0.3));" />
          ${dailySeries.map((d, idx) => {
            const [x, y] = mrpPoints[idx].split(',');
            return `<circle cx="${x}" cy="${y}" r="3" fill="#090B10" stroke="var(--accent-amber)" stroke-width="2" />`;
          }).join('')}
        </svg>
      </div>
      <div style="display:flex;align-items:center;justify-content:center;gap:1.5rem;margin-top:0.5rem;font-size:0.75rem;color:var(--text-secondary);">
        <span style="display:flex;align-items:center;gap:4px;"><span style="width:10px;height:10px;background:var(--brand-beer);border-radius:2px;"></span>Beer Cases</span>
        <span style="display:flex;align-items:center;gap:4px;"><span style="width:10px;height:10px;background:var(--brand-imfl);border-radius:2px;"></span>IMFL Cases</span>
        <span style="display:flex;align-items:center;gap:4px;"><span style="width:10px;height:10px;background:var(--brand-cs);border-radius:2px;"></span>CS Cases</span>
        <span style="display:flex;align-items:center;gap:4px;"><span style="width:16px;height:2px;background:var(--accent-amber);"></span>MRP Trend</span>
      </div>
    `;
  }
};

window.AppComponents = AppComponents;
