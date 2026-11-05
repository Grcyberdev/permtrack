/**
 * PermTrack Enterprise — Workspace 1: Overview (Command Pulse)
 * Quiet Luxury & Calm Executive Polish
 */
const WorkspacePulse = {
  render() {
    const container = document.getElementById('workspace-pulse-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `
        <div style="text-align:center;padding:5rem;color:var(--text-muted);">
          <div style="font-size:0.9rem;font-weight:600;">Loading Overview...</div>
        </div>
      `;
      return;
    }

    const s = data.summary || {};
    const prev = data.previous_period_summary || {};
    const cat = data.category_breakdown || {};
    const horizon = data.horizon || {};
    const isSingleDay = (AppState.horizonMode === 'day') || ((data.daily_series || []).length <= 1);
    const catFilter = AppState.categoryFilter || 'ALL';

    // Fix 12: Category filter applied to Overview KPIs
    let displayCases = s.total_cases;
    let displayCasesOnly = s.cases_only;
    let displayBottlesOnly = s.bottles_only;
    let displayMRP = s.total_mrp;
    let displayAvgCasePrice = s.avg_case_price;
    let displayPendingCases = s.pending_cases;
    let displayPendingMRP = s.pending_mrp;
    let displayDispatchedPermits = s.permits_count;

    if (catFilter !== 'ALL' && cat[catFilter]) {
      const cinfo = cat[catFilter];
      displayCases = cinfo.cases;
      displayCasesOnly = cinfo.cases_only;
      displayBottlesOnly = cinfo.bottles;
      displayMRP = cinfo.mrp;
      displayAvgCasePrice = cinfo.cases > 0 ? (cinfo.mrp / cinfo.cases) : 0;
      displayPendingCases = cinfo.pending_cases || 0;
      displayPendingMRP = cinfo.pending_mrp || 0;
      displayDispatchedPermits = cinfo.permits || 0;
    }

    // Filter indicator chip (Fix 12)
    const filterChipHTML = catFilter !== 'ALL' ? `
      <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:1rem;">
        <span class="badge-filter-active">
          Filtered: ${catFilter === 'BEER' ? 'Beer' : (catFilter === 'CS' ? 'Country Spirit' : 'IMFL Spirits')}
          <button data-action="clear-category-filter" style="background:none;border:none;color:currentColor;cursor:pointer;padding:0 2px;margin-left:4px;font-weight:700;">✕</button>
        </span>
      </div>
    ` : '';

    // 1. Top Executive Strip (4 Clean Cards)
    const kpiHTML = `
      ${filterChipHTML}
      <div class="executive-kpi-grid">
        <!-- Card 1: Dispatched Volume -->
        <div class="kpi-surface-card">
          <div class="kpi-header">
            <span class="kpi-title">Dispatched Volume</span>
            ${AppComponents.renderDeltaBadge(prev.delta_cases_pct, 'vs ' + (horizon.prev_display_label || 'prior'))}
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${AppUtils.formatNumber(displayCases)}</span>
            <span class="kpi-unit">cs</span>
          </div>
          <div class="kpi-subtitle">
            <span>${AppUtils.formatNumber(displayCasesOnly, 0)} Cases</span>
            <span class="sep-dot">•</span>
            <span>${AppUtils.formatInteger(displayBottlesOnly)} Loose Btls</span>
          </div>
        </div>

        <!-- Card 2: Bond Turnover (MRP) -->
        <div class="kpi-surface-card">
          <div class="kpi-header">
            <span class="kpi-title">Bond Turnover (MRP)</span>
            ${AppComponents.renderDeltaBadge(prev.delta_mrp_pct, 'vs ' + (horizon.prev_display_label || 'prior'))}
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${AppUtils.formatCurrencyINR(displayMRP, true)}</span>
          </div>
          <div class="kpi-subtitle">
            <span>Avg ₹${AppUtils.formatNumber(displayAvgCasePrice, 0)}/cs</span>
            <span class="sep-dot">•</span>
            <span>Pending: ${AppUtils.formatCurrencyINR(displayPendingMRP, true)}</span>
          </div>
        </div>

        <!-- Card 3: Bond Indents & Pipeline (Fix 37: main value = dispatched permits, subtitle = +N pending) -->
        <div class="kpi-surface-card">
          <div class="kpi-header">
            <span class="kpi-title">Indents & Pipeline</span>
            <span class="kpi-counter">${AppUtils.formatInteger(s.permits_count + (s.pending_permits_count || 0))} Total</span>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${AppUtils.formatInteger(displayDispatchedPermits)}</span>
            <span class="kpi-unit">dispatched</span>
          </div>
          <div class="kpi-subtitle">
            ${s.pending_permits_count > 0 ? `
              <button class="kpi-pending-link" data-action="go-pending-indents">
                <span class="status-dot dot-warning"></span>
                <span>+${s.pending_permits_count} pending (${AppUtils.formatNumber(displayPendingCases)} cs)</span>
              </button>
            ` : `<span style="color:var(--status-success);"><span class="status-dot dot-success"></span>All Indents Clear</span>`}
          </div>
        </div>

        <!-- Card 4: Monthly Sales (MTD) / Monthly Total Sales -->
        <div class="kpi-surface-card" style="cursor:pointer;" data-action="view-month" title="Click to view full Month breakdown">
          <div class="kpi-header">
            <span class="kpi-title">${AppState.horizonMode === 'month' ? 'Monthly Total Sales' : 'Monthly Sales (MTD)'}</span>
            <span class="kpi-counter">${s.mtd_label || (horizon.display_label || 'Month')}</span>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${AppUtils.formatNumber(s.mtd_cases || s.total_cases)}</span>
            <span class="kpi-unit">cs</span>
          </div>
          <div class="kpi-subtitle">
            <span style="color:var(--accent-amber);font-weight:600;">${AppUtils.formatCurrencyINR(s.mtd_mrp || s.total_mrp, true)}</span>
            <span class="sep-dot">•</span>
            <span>${s.mtd_active_days || s.active_days || 1} Operating Days</span>
          </div>
        </div>
      </div>
    `;

    // 2. Interactive Category Strip (Beer, IMFL, CS)
    const beer = cat.BEER || { cases: 0, mrp: 0, share_pct: 0, velocity_per_day: 0 };
    const imfl = cat.IMFL || { cases: 0, mrp: 0, share_pct: 0, velocity_per_day: 0 };
    const cs = cat.CS || { cases: 0, mrp: 0, share_pct: 0, velocity_per_day: 0 };

    const categoryStripHTML = `
      <div class="category-overview-card">
        <!-- Unified Proportional Volume Bar -->
        <div class="proportional-bar-container">
          <div class="bar-seg seg-beer" style="width:${beer.share_pct || 0}%;" title="Beer: ${beer.share_pct || 0}%"></div>
          <div class="bar-seg seg-imfl" style="width:${imfl.share_pct || 0}%;" title="IMFL: ${imfl.share_pct || 0}%"></div>
          <div class="bar-seg seg-cs" style="width:${cs.share_pct || 0}%;" title="Country Spirit: ${cs.share_pct || 0}%"></div>
        </div>

        <!-- 3 Interactive Category Columns -->
        <div class="cat-columns-grid">
          <div class="cat-interactive-card ${AppState.categoryFilter === 'BEER' ? 'active-filter' : ''}" data-action="filter-category" data-cat="BEER" style="cursor:pointer;">
            <div class="cat-col-header">
              <span class="cat-col-title"><span class="cat-dot dot-beer"></span>Beer</span>
              <span class="cat-col-share">${beer.share_pct || 0}%</span>
            </div>
            <div class="cat-col-val">${AppUtils.formatNumber(beer.cases)} <span class="unit">cs</span></div>
            <div class="cat-col-sub">
              <span>${AppUtils.formatCurrencyINR(beer.mrp, true)}</span>
              <span class="sep-dot">•</span>
              <span>${AppUtils.formatNumber(beer.velocity_per_day, 1)} cs/d</span>
            </div>
          </div>

          <div class="cat-interactive-card ${AppState.categoryFilter === 'IMFL' ? 'active-filter' : ''}" data-action="filter-category" data-cat="IMFL" style="cursor:pointer;">
            <div class="cat-col-header">
              <span class="cat-col-title"><span class="cat-dot dot-imfl"></span>IMFL Spirits</span>
              <span class="cat-col-share">${imfl.share_pct || 0}%</span>
            </div>
            <div class="cat-col-val">${AppUtils.formatNumber(imfl.cases)} <span class="unit">cs</span></div>
            <div class="cat-col-sub">
              <span>${AppUtils.formatCurrencyINR(imfl.mrp, true)}</span>
              <span class="sep-dot">•</span>
              <span>${AppUtils.formatNumber(imfl.velocity_per_day, 1)} cs/d</span>
            </div>
          </div>

          <div class="cat-interactive-card ${AppState.categoryFilter === 'CS' ? 'active-filter' : ''}" data-action="filter-category" data-cat="CS" style="cursor:pointer;">
            <div class="cat-col-header">
              <span class="cat-col-title"><span class="cat-dot dot-cs"></span>Country Spirit</span>
              <span class="cat-col-share">${cs.share_pct || 0}%</span>
            </div>
            <div class="cat-col-val">${AppUtils.formatNumber(cs.cases)} <span class="unit">cs</span></div>
            <div class="cat-col-sub">
              <span>${AppUtils.formatCurrencyINR(cs.mrp, true)}</span>
              <span class="sep-dot">•</span>
              <span>${AppUtils.formatNumber(cs.velocity_per_day, 1)} cs/d</span>
            </div>
          </div>
        </div>
      </div>
    `;

    // 3. Context-Aware Visual Section
    let visualSectionHTML = '';
    if (!isSingleDay) {
      // Multi-Day / Week / Month / Range View: Show interactive SVG timeline chart
      visualSectionHTML = `
        <div class="surface-panel" style="margin-bottom:1.25rem;">
          <div class="panel-header">
            <div>
              <div class="panel-title">Dispatch Movement & Revenue Timeline</div>
              <div class="panel-subtitle">Daily accumulation and MRP progression across ${horizon.display_label || 'selected horizon'}</div>
            </div>
            <div class="panel-action-hint">Click any bar to drill down</div>
          </div>
          <div class="panel-body">
            ${AppComponents.renderTimelineChartSVG(data.daily_series || [])}
          </div>
        </div>
      `;
    } else {
      // Single-Day Mode: Show 2-Column Daily Operational Breakdown (Pack-Size Demand + Floor Bottlenecks)
      // Fix 3: use p.size and compute percentages against total of ALL pack_sizes_full
      let allPacks = data.pack_sizes_full || [];
      let pickList = data.pending_pick_list || [];
      if (catFilter !== 'ALL') {
        allPacks = allPacks.filter(p => p.category === catFilter);
        pickList = pickList.filter(item => item.category === catFilter);
      }
      const totalAllPackCases = allPacks.reduce((acc, p) => acc + (p.cases || 0), 0) || 1;
      const packSizes = allPacks.slice(0, 6);
      pickList = pickList.slice(0, 6);

      visualSectionHTML = `
        <div class="day-breakdown-grid" style="margin-bottom:1.25rem;">
          <!-- Left Column: Pack Size Movement -->
          <div class="surface-panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Pack-Size Movement</div>
                <div class="panel-subtitle">Volume distribution by bottle size for today</div>
              </div>
              <a href="#" data-action="go-packs" class="panel-link">
                All Packs →
              </a>
            </div>
            <div class="panel-body" style="padding:0.75rem 1rem;">
              ${packSizes.length === 0 ? `
                <div style="text-align:center;padding:2rem;color:var(--text-muted);">No pack volume recorded</div>
              ` : packSizes.map(p => {
                const packName = p.size || p.pack_size || 'Unknown';
                const pct = ((p.cases / totalAllPackCases) * 100).toFixed(1);
                return `
                  <div class="pack-demand-row">
                    <div class="pack-demand-label">
                      <span class="pack-name">${AppUtils.escapeHtml(packName)}</span>
                      <span class="pack-cases">${AppUtils.formatNumber(p.cases)} cs (${pct}%)</span>
                    </div>
                    <div class="progress-track">
                      <div class="progress-fill" style="width:${pct}%;"></div>
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
          </div>

          <!-- Right Column: Pending Floor Bottlenecks -->
          <div class="surface-panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Pending Loading Bottlenecks</div>
                <div class="panel-subtitle">Products waiting to be loaded from warehouse floor</div>
              </div>
              <a href="#" data-action="go-picklist" class="panel-link">
                Pick-List →
              </a>
            </div>
            <div class="panel-body" style="padding:0.75rem 1rem;">
              ${pickList.length === 0 ? `
                <div style="text-align:center;padding:2.5rem 1rem;color:var(--status-success);">
                  <div style="font-size:1.2rem;font-weight:700;margin-bottom:4px;">Floor Clear</div>
                  <div style="font-size:0.8rem;color:var(--text-muted);">All indents for this day have been officially issued and dispatched.</div>
                </div>
              ` : `
                <table class="mini-data-table">
                  <thead>
                    <tr>
                      <th>Product / SKU</th>
                      <th>Pack</th>
                      <th style="text-align:right;">Needed</th>
                      <th style="text-align:right;">Indents</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${pickList.map(item => `
                      <tr>
                        <td style="font-weight:600;">${AppUtils.escapeHtml(item.brand_name || item.brand)}</td>
                        <td><span class="pack-pill">${AppUtils.escapeHtml(item.pack_size)}</span></td>
                        <td class="cell-num" style="text-align:right;color:var(--status-warning);font-weight:700;">
                          ${AppUtils.formatNumber(item.total_cases_eq || item.cases)} cs
                        </td>
                        <td class="cell-num" style="text-align:right;color:var(--text-muted);">${item.permits_count || 1} indents</td>
                      </tr>
                    `).join('')}
                  </tbody>
                </table>
              `}
            </div>
          </div>
        </div>
      `;
    }

    // 4. Bottom Dual Tables: Top 10 Moving Brands vs Top 10 Ordering Retailers
    let brandsList = data.brands_full || [];
    if (catFilter !== 'ALL') {
      brandsList = brandsList.filter(b => b.category === catFilter);
    }
    const topBrands = brandsList.slice(0, 10);
    let partiesList = data.parties_full || [];
    if (catFilter !== 'ALL') {
      const volProp = catFilter === 'BEER' ? 'beer_cases' : (catFilter === 'CS' ? 'cs_cases' : 'imfl_cases');
      partiesList = partiesList
        .map(p => ({
          ...p,
          dispatched_cases: p[volProp] !== undefined ? p[volProp] : p.dispatched_cases
        }))
        .filter(p => (p.dispatched_cases > 0) || (p.pending_cases > 0));
      partiesList.sort((a, b) => (b.dispatched_cases || 0) - (a.dispatched_cases || 0));
    }
    const topParties = partiesList.slice(0, 10);
    const maxBrandCases = topBrands.length > 0 ? (topBrands[0].dispatched_cases || 1) : 1;
    const maxPartyCases = topParties.length > 0 ? (topParties[0].dispatched_cases || 1) : 1;

    const leaderboardsHTML = `
      <div class="leaderboard-dual-grid">
        <!-- Top Brands -->
        <div class="surface-panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Top Moving Brands</div>
              <div class="panel-subtitle">By total dispatched volume</div>
            </div>
            <a href="#" data-action="go-products" class="panel-link">
              View All (${brandsList.length}) →
            </a>
          </div>
          <div class="panel-body" style="padding:0;">
            <div class="leaderboard-table-wrap">
              <table class="leaderboard-table">
                <thead>
                  <tr>
                    <th style="width:32px;">#</th>
                    <th>Brand</th>
                    <th style="text-align:right;">Cases</th>
                    <th style="width:100px;">Share</th>
                    <th style="text-align:right;">MRP</th>
                  </tr>
                </thead>
                <tbody>
                  ${topBrands.length === 0 ? `
                    <tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text-muted);">No brand activity</td></tr>
                  ` : topBrands.map((b, i) => {
                    const barW = Math.max(4, Math.round((b.dispatched_cases / maxBrandCases) * 100));
                    return `
                      <tr data-action="inspect-brand" data-name="${AppUtils.escapeHtml(b.name)}" style="cursor:pointer;">
                        <td class="rank-num">${i + 1}</td>
                        <td class="brand-cell">
                          <div class="brand-name-main">${AppUtils.escapeHtml(b.name)}</div>
                          <div class="brand-cat-meta">${AppComponents.renderCategoryBadge(b.category)}</div>
                        </td>
                        <td class="cell-num" style="text-align:right;font-weight:700;">${AppUtils.formatNumber(b.dispatched_cases)}</td>
                        <td>
                          <div class="inline-volume-bar">
                            <div class="bar-fill" style="width:${barW}%;"></div>
                          </div>
                        </td>
                        <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(b.total_mrp, true)}</td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Top Retailers -->
        <div class="surface-panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Top Ordering Retailers</div>
              <div class="panel-subtitle">By total purchased volume</div>
            </div>
            <a href="#" data-action="go-parties" class="panel-link">
              View All (${partiesList.length}) →
            </a>
          </div>
          <div class="panel-body" style="padding:0;">
            <div class="leaderboard-table-wrap">
              <table class="leaderboard-table">
                <thead>
                  <tr>
                    <th style="width:32px;">#</th>
                    <th>Retailer</th>
                    <th style="text-align:right;">Cases</th>
                    <th style="width:100px;">Share</th>
                    <th style="text-align:right;">MRP</th>
                  </tr>
                </thead>
                <tbody>
                  ${topParties.length === 0 ? `
                    <tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text-muted);">No retailer activity</td></tr>
                  ` : topParties.map((p, i) => {
                    const barW = Math.max(4, Math.round((p.dispatched_cases / maxPartyCases) * 100));
                    return `
                      <tr data-action="inspect-party" data-name="${AppUtils.escapeHtml(p.name)}" style="cursor:pointer;">
                        <td class="rank-num">${i + 1}</td>
                        <td class="brand-cell">
                          <div class="brand-name-main">${AppUtils.escapeHtml(p.name)}</div>
                          <div class="party-district-meta">${AppUtils.escapeHtml(p.district || 'Assam')} • ${p.indent_count} indents</div>
                        </td>
                        <td class="cell-num" style="text-align:right;font-weight:700;">${AppUtils.formatNumber(p.dispatched_cases)}</td>
                        <td>
                          <div class="inline-volume-bar">
                            <div class="bar-fill bar-fill-party" style="width:${barW}%;"></div>
                          </div>
                        </td>
                        <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(p.mrp, true)}</td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    `;

    container.innerHTML = kpiHTML + categoryStripHTML + visualSectionHTML + leaderboardsHTML;

    // Delegated event listener for quote-safe click handling (Fix 5)
    if (!container._delegatedPulseListener) {
      container._delegatedPulseListener = true;
      container.addEventListener('click', (e) => {
        const target = e.target.closest('[data-action]');
        if (!target) return;
        const action = target.dataset.action;
        if (action === 'inspect-brand') {
          window.inspectBrand(target.dataset.name);
        } else if (action === 'inspect-party') {
          window.inspectParty(target.dataset.name);
        } else if (action === 'filter-category') {
          const c = target.dataset.cat;
          window.setCategoryFilter(AppState.categoryFilter === c ? 'ALL' : c);
        } else if (action === 'clear-category-filter') {
          window.setCategoryFilter('ALL');
        } else if (action === 'go-pending-indents') {
          AppState.activeWorkspace = 'indents';
          AppState.indentStatusTab = 'PENDING';
          window.syncWorkspaceTabs();
          renderActiveWorkspace();
        } else if (action === 'view-month') {
          setHorizonMode('month');
        } else if (action === 'go-packs') {
          e.preventDefault();
          AppState.activeWorkspace = 'products';
          AppState.productSubView = 'packs';
          window.syncWorkspaceTabs();
          renderActiveWorkspace();
        } else if (action === 'go-picklist') {
          e.preventDefault();
          AppState.activeWorkspace = 'products';
          AppState.productSubView = 'picklist';
          window.syncWorkspaceTabs();
          renderActiveWorkspace();
        } else if (action === 'go-products') {
          e.preventDefault();
          AppState.activeWorkspace = 'products';
          window.syncWorkspaceTabs();
          renderActiveWorkspace();
        } else if (action === 'go-parties') {
          e.preventDefault();
          AppState.activeWorkspace = 'parties';
          window.syncWorkspaceTabs();
          renderActiveWorkspace();
        }
      });
    }
  }
};

window.WorkspacePulse = WorkspacePulse;
