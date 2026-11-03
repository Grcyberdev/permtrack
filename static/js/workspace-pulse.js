/**
 * PermTrack Enterprise — Workspace 1: Command Pulse
 */
const WorkspacePulse = {
  render() {
    const container = document.getElementById('workspace-pulse-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `
        <div style="text-align:center;padding:4rem;color:var(--text-muted);">
          <div style="font-size:1.5rem;margin-bottom:0.5rem;">⏳</div>
          <div>Loading Command Pulse...</div>
        </div>
      `;
      return;
    }

    const s = data.summary || {};
    const prev = data.previous_period_summary || {};
    const cat = data.category_breakdown || {};
    const horizon = data.horizon || {};

    // 1. Hero KPI Strip (5 High-Density Cards)
    const kpiHTML = `
      <div class="hero-kpi-grid">
        <!-- KPI 1: Dispatched Volume -->
        <div class="kpi-card kpi-amber">
          <div class="kpi-header">
            <span class="kpi-title">Dispatched Volume</span>
            ${AppComponents.renderDeltaBadge(prev.delta_cases_pct, 'vs ' + horizon.prev_display_label)}
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${AppUtils.formatNumber(s.total_cases)}</span>
            <span class="kpi-unit">cases</span>
          </div>
          <div class="kpi-subtitle">
            <span>Physical: ${AppUtils.formatNumber(s.cases_only, 0)} cs</span>
            <span>•</span>
            <span>Loose: ${AppUtils.formatInteger(s.bottles_only)} btls</span>
          </div>
        </div>

        <!-- KPI 2: Bond Revenue -->
        <div class="kpi-card kpi-emerald">
          <div class="kpi-header">
            <span class="kpi-title">Bond Revenue (MRP)</span>
            ${AppComponents.renderDeltaBadge(prev.delta_mrp_pct, 'vs ' + horizon.prev_display_label)}
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${AppUtils.formatCurrencyINR(s.total_mrp, true)}</span>
          </div>
          <div class="kpi-subtitle">
            <span>Avg: ₹${AppUtils.formatNumber(s.avg_case_price, 0)}/cs</span>
            <span>•</span>
            <span>Pending: ${AppUtils.formatCurrencyINR(s.pending_mrp, true)}</span>
          </div>
        </div>

        <!-- KPI 3: Indent Fulfillment Flow -->
        <div class="kpi-card kpi-indigo">
          <div class="kpi-header">
            <span class="kpi-title">Indent Flow</span>
            ${AppComponents.renderDeltaBadge(prev.delta_permits_pct, 'vs ' + horizon.prev_display_label)}
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${AppUtils.formatInteger(s.permits_count)}</span>
            <span class="kpi-unit">dispatched</span>
          </div>
          <div class="kpi-subtitle">
            <span style="color:var(--status-warning);">⏳ ${AppUtils.formatInteger(s.pending_permits_count)} Pending in Bond</span>
            <span>(${AppUtils.formatNumber(s.pending_cases)} cs)</span>
          </div>
        </div>

        <!-- KPI 4: Daily Sales Velocity -->
        <div class="kpi-card kpi-gold">
          <div class="kpi-header">
            <span class="kpi-title">Daily Velocity</span>
            <span class="badge-count" style="font-family:var(--font-mono);font-size:0.75rem;color:var(--text-secondary);">
              ${s.active_days} active days
            </span>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${AppUtils.formatNumber(s.cases_per_day, 1)}</span>
            <span class="kpi-unit">cs/day</span>
          </div>
          <div class="kpi-subtitle">
            <span>${AppUtils.formatCurrencyINR(s.mrp_per_day, true)}/day</span>
            <span>•</span>
            <span>Parties: ${s.active_parties_count} active</span>
          </div>
        </div>

        <!-- KPI 5: Godown Audit & Variance -->
        <div class="kpi-card kpi-rose">
          <div class="kpi-header">
            <span class="kpi-title">Godown Audit</span>
            <span class="badge-count" style="font-family:var(--font-mono);font-size:0.75rem;color:var(--text-secondary);">
              Physical vs Portal
            </span>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${s.godown_cases !== null ? AppUtils.formatNumber(s.godown_cases) : '—'}</span>
            <span class="kpi-unit">cs</span>
          </div>
          <div class="kpi-subtitle">
            ${s.difference !== null ? `
              <span class="${s.difference === 0 ? 'variance-zero' : (s.difference > 0 ? 'variance-surplus' : 'variance-deficit')}" style="font-weight:700;">
                Variance: ${s.difference > 0 ? '+' : ''}${AppUtils.formatNumber(s.difference)} cs
              </span>
            ` : `<span style="color:var(--text-muted);">No physical count entered</span>`}
          </div>
        </div>
      </div>
    `;

    // 2. Pending SLA Alert Banner (if pending indents exist)
    let alertBannerHTML = '';
    if (s.pending_permits_count > 0) {
      alertBannerHTML = `
        <div style="background:rgba(245, 158, 11, 0.1);border:1px solid rgba(245, 158, 11, 0.3);border-radius:var(--radius-lg);padding:0.75rem 1.25rem;display:flex;align-items:center;justify-content:space-between;margin-bottom:1.25rem;">
          <div style="display:flex;align-items:center;gap:0.75rem;">
            <span style="font-size:1.2rem;">⏳</span>
            <div>
              <div style="font-weight:700;color:var(--accent-amber);font-size:0.9rem;">
                ${s.pending_permits_count} Indents Waiting in Bond (${AppUtils.formatNumber(s.pending_cases)} Cases • ${AppUtils.formatCurrencyINR(s.pending_mrp)})
              </div>
              <div style="font-size:0.75rem;color:var(--text-secondary);">
                Requires loading & dispatch fulfillment. Check Product Matrix pick-list for floor requirements.
              </div>
            </div>
          </div>
          <button class="action-btn" style="background:var(--accent-amber);color:#090B10;font-weight:700;" onclick="AppState.activeWorkspace='indents';AppState.indentStatusTab='PENDING';window.syncWorkspaceTabs();">
            View Pending Ledger →
          </button>
        </div>
      `;
    }

    // 3. Category Mix & Velocity Strip (Beer, IMFL, CS)
    const beer = cat.BEER || {};
    const imfl = cat.IMFL || {};
    const cs = cat.CS || {};

    const categoryStripHTML = `
      <div class="category-velocity-strip">
        <!-- Beer -->
        <div class="cat-velocity-card">
          <div class="cat-header">
            <span class="cat-badge cat-beer">🍺 BEER</span>
            <span class="cat-share">${beer.share_pct || 0}% share</span>
          </div>
          <div class="cat-stats-row">
            <div class="cat-stat-item">
              <span class="cat-stat-label">Dispatched</span>
              <span class="cat-stat-val">${AppUtils.formatNumber(beer.cases)} cs</span>
            </div>
            <div class="cat-stat-item">
              <span class="cat-stat-label">Value (MRP)</span>
              <span class="cat-stat-val" style="color:var(--brand-beer);">${AppUtils.formatCurrencyINR(beer.mrp, true)}</span>
            </div>
          </div>
          <div class="cat-subtitle" style="font-size:0.75rem;color:var(--text-secondary);display:flex;justify-content:space-between;margin-bottom:0.5rem;">
            <span>Velocity: ${AppUtils.formatNumber(beer.velocity_per_day, 1)} cs/d</span>
            <span>BL: ${AppUtils.formatNumber(beer.bulk_litres, 0)} L</span>
          </div>
          <div class="cat-progress-track">
            <div class="cat-progress-bar bar-beer" style="width:${beer.share_pct || 0}%;"></div>
          </div>
        </div>

        <!-- IMFL -->
        <div class="cat-velocity-card">
          <div class="cat-header">
            <span class="cat-badge cat-imfl">🥃 IMFL SPIRITS</span>
            <span class="cat-share">${imfl.share_pct || 0}% share</span>
          </div>
          <div class="cat-stats-row">
            <div class="cat-stat-item">
              <span class="cat-stat-label">Dispatched</span>
              <span class="cat-stat-val">${AppUtils.formatNumber(imfl.cases)} cs</span>
            </div>
            <div class="cat-stat-item">
              <span class="cat-stat-label">Value (MRP)</span>
              <span class="cat-stat-val" style="color:var(--brand-imfl);">${AppUtils.formatCurrencyINR(imfl.mrp, true)}</span>
            </div>
          </div>
          <div class="cat-subtitle" style="font-size:0.75rem;color:var(--text-secondary);display:flex;justify-content:space-between;margin-bottom:0.5rem;">
            <span>Velocity: ${AppUtils.formatNumber(imfl.velocity_per_day, 1)} cs/d</span>
            <span>LPL: ${AppUtils.formatNumber(imfl.lpl, 0)} L</span>
          </div>
          <div class="cat-progress-track">
            <div class="cat-progress-bar bar-imfl" style="width:${imfl.share_pct || 0}%;"></div>
          </div>
        </div>

        <!-- Country Spirit -->
        <div class="cat-velocity-card">
          <div class="cat-header">
            <span class="cat-badge cat-cs">🍶 COUNTRY SPIRIT</span>
            <span class="cat-share">${cs.share_pct || 0}% share</span>
          </div>
          <div class="cat-stats-row">
            <div class="cat-stat-item">
              <span class="cat-stat-label">Dispatched</span>
              <span class="cat-stat-val">${AppUtils.formatNumber(cs.cases)} cs</span>
            </div>
            <div class="cat-stat-item">
              <span class="cat-stat-label">Value (MRP)</span>
              <span class="cat-stat-val" style="color:var(--brand-cs);">${AppUtils.formatCurrencyINR(cs.mrp, true)}</span>
            </div>
          </div>
          <div class="cat-subtitle" style="font-size:0.75rem;color:var(--text-secondary);display:flex;justify-content:space-between;margin-bottom:0.5rem;">
            <span>Velocity: ${AppUtils.formatNumber(cs.velocity_per_day, 1)} cs/d</span>
            <span>LPL: ${AppUtils.formatNumber(cs.lpl, 0)} L</span>
          </div>
          <div class="cat-progress-track">
            <div class="cat-progress-bar bar-cs" style="width:${cs.share_pct || 0}%;"></div>
          </div>
        </div>
      </div>
    `;

    // 4. Movement Timeline Chart (Daily Series)
    const chartHTML = `
      <div class="chart-card" style="margin-bottom:1.25rem;">
        <div class="card-title-row">
          <div>
            <div class="card-title">📈 Dispatch Movement & Revenue Timeline</div>
            <div class="card-subtitle">Daily Beer, IMFL, CS accumulation & MRP trend for ${horizon.display_label}</div>
          </div>
          <div style="font-family:var(--font-mono);font-size:0.8rem;color:var(--text-muted);">
            Tip: Click any bar to drill into that single day
          </div>
        </div>
        <div class="chart-container-svg">
          ${AppComponents.renderTimelineChartSVG(data.daily_series || [])}
        </div>
      </div>
    `;

    // 5. Leaderboard Dual Strip (Top 5 Moving Brands vs Top 5 Ordering Parties)
    const topBrands = (data.brands_full || []).slice(0, 5);
    const topParties = (data.parties_full || []).slice(0, 5);

    const leaderboardsHTML = `
      <div class="leaderboard-dual-strip">
        <!-- Top Brands -->
        <div class="leaderboard-card">
          <div class="card-title-row">
            <div class="card-title">🔥 Top Moving Brands</div>
            <a href="#" onclick="AppState.activeWorkspace='products';window.syncWorkspaceTabs();return false;" style="font-size:0.8rem;color:var(--accent-amber);font-weight:600;">
              View All ${data.brands_full ? data.brands_full.length : 0} Brands →
            </a>
          </div>
          <div class="leaderboard-list">
            ${topBrands.map((b, i) => `
              <div class="leaderboard-item" onclick="window.inspectBrand('${encodeURIComponent(b.name)}')">
                <span class="lb-rank">#${i + 1}</span>
                <div class="lb-info">
                  <span class="lb-name">${AppUtils.escapeHtml(b.name)}</span>
                  <span class="lb-meta">
                    ${AppComponents.renderCategoryBadge(b.category)}
                    <span>${b.share_pct}% share</span>
                  </span>
                </div>
                <div class="lb-values">
                  <span class="lb-cases">${AppUtils.formatNumber(b.dispatched_cases)} cs</span>
                  <span class="lb-mrp">${AppUtils.formatCurrencyINR(b.total_mrp, true)}</span>
                </div>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Top Retailers -->
        <div class="leaderboard-card">
          <div class="card-title-row">
            <div class="card-title">🏪 Top Ordering Retailers</div>
            <a href="#" onclick="AppState.activeWorkspace='parties';window.syncWorkspaceTabs();return false;" style="font-size:0.8rem;color:var(--accent-amber);font-weight:600;">
              View All ${data.parties_full ? data.parties_full.length : 0} Retailers →
            </a>
          </div>
          <div class="leaderboard-list">
            ${topParties.map((p, i) => `
              <div class="leaderboard-item" onclick="window.inspectParty('${encodeURIComponent(p.name)}')">
                <span class="lb-rank">#${i + 1}</span>
                <div class="lb-info">
                  <span class="lb-name">${AppUtils.escapeHtml(p.name)}</span>
                  <span class="lb-meta">
                    <span>${AppUtils.escapeHtml(p.district)}</span>
                    <span>•</span>
                    <span>${p.indent_count} indents</span>
                  </span>
                </div>
                <div class="lb-values">
                  <span class="lb-cases">${AppUtils.formatNumber(p.dispatched_cases)} cs</span>
                  <span class="lb-mrp">${AppUtils.formatCurrencyINR(p.mrp, true)}</span>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `;

    container.innerHTML = kpiHTML + alertBannerHTML + categoryStripHTML + chartHTML + leaderboardsHTML;
  }
};

window.WorkspacePulse = WorkspacePulse;
