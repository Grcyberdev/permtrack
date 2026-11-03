/**
 * PermTrack Enterprise — Workspace 2: Product & Brand Movement Matrix
 * The Core Day / Week / Month Inventory & Sales Tracker
 * Minimal, Calm, Executive Precision with Responsive Mobile Cards
 */
const WorkspaceProducts = {
  expandedBrands: new Set(),

  setSort(col) {
    if (AppState.productSortCol === col) {
      AppState.productSortDir = AppState.productSortDir === 'desc' ? 'asc' : 'desc';
    } else {
      AppState.productSortCol = col;
      AppState.productSortDir = 'desc';
    }
    this.render();
  },

  renderSortIndicator(col) {
    if (AppState.productSortCol !== col) {
      return `<span class="sort-icon-neutral">↕</span>`;
    }
    return `<span class="sort-icon-active">${AppState.productSortDir === 'desc' ? '↓' : '↑'}</span>`;
  },

  render() {
    const container = document.getElementById('workspace-products-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:5rem;color:var(--text-muted);">Loading Products...</div>`;
      return;
    }

    const subView = AppState.productSubView || 'brands';

    const subnavHTML = `
      <div class="segmented-subnav">
        <button class="seg-btn ${subView === 'brands' ? 'active' : ''}" onclick="AppState.productSubView='brands';WorkspaceProducts.render();">
          Brand & SKU Matrix
        </button>
        <button class="seg-btn ${subView === 'packs' ? 'active' : ''}" onclick="AppState.productSubView='packs';WorkspaceProducts.render();">
          Pack-Size Architecture
        </button>
        <button class="seg-btn ${subView === 'picklist' ? 'active' : ''}" onclick="AppState.productSubView='picklist';WorkspaceProducts.render();">
          Pending Pick-List (${data.pending_pick_list ? data.pending_pick_list.length : 0})
        </button>
      </div>
    `;

    let contentHTML = '';
    if (subView === 'brands') {
      contentHTML = this.renderBrandMatrix(data);
    } else if (subView === 'packs') {
      contentHTML = this.renderPackSizeMatrix(data);
    } else {
      contentHTML = this.renderPendingPickList(data);
    }

    container.innerHTML = subnavHTML + contentHTML;
  },

  renderBrandMatrix(data) {
    const query = (AppState.productSearchQuery || '').toLowerCase().trim();
    const catFilter = AppState.categoryFilter || 'ALL';
    const isSingleDay = (AppState.horizonMode === 'day') || ((data.daily_series || []).length <= 1);

    let brands = data.brands_full || [];
    if (catFilter !== 'ALL') {
      brands = brands.filter(b => b.category === catFilter);
    }
    if (query) {
      brands = brands.filter(b => b.name.toLowerCase().includes(query));
    }

    // Apply Column Sorting
    const sortCol = AppState.productSortCol || 'dispatched_cases';
    const sortDir = AppState.productSortDir || 'desc';
    const mult = sortDir === 'asc' ? 1 : -1;

    brands = [...brands].sort((a, b) => {
      let valA = a[sortCol];
      let valB = b[sortCol];
      if (typeof valA === 'string') {
        return (valA || '').localeCompare(valB || '') * mult;
      }
      valA = Number(valA || 0);
      valB = Number(valB || 0);
      return (valA - valB) * mult;
    });

    const totalDispatched = brands.reduce((acc, b) => acc + (b.dispatched_cases || 0), 0);
    const totalMRP = brands.reduce((acc, b) => acc + (b.total_mrp || 0), 0);
    const totalPending = brands.reduce((acc, b) => acc + (b.pending_cases || 0), 0);
    const maxDispatched = brands.length > 0 ? Math.max(...brands.map(b => b.dispatched_cases || 0), 1) : 1;

    const toolbarHTML = `
      <div class="table-toolbar">
        <div class="search-box-wrap">
          <svg class="search-icon-svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input type="text" class="search-input" placeholder="Search brands or SKUs..." value="${AppUtils.escapeHtml(AppState.productSearchQuery)}" oninput="AppState.productSearchQuery=this.value;WorkspaceProducts.render();" />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span class="table-stats-badge">
            ${brands.length} Brands • ${AppUtils.formatNumber(totalDispatched)} cs • ${AppUtils.formatCurrencyINR(totalMRP, true)}
          </span>
          <button class="action-btn" onclick="WorkspaceProducts.toggleAllExpansions()">
            ${this.expandedBrands.size > 0 ? 'Collapse All' : 'Expand All'}
          </button>
        </div>
      </div>
    `;

    // Responsive Mobile Cards View (< 768px)
    const mobileCardsHTML = `
      <div class="mobile-cards-view">
        ${brands.length === 0 ? `
          <div style="text-align:center;padding:3rem 1rem;color:var(--text-muted);">No brands match filter criteria</div>
        ` : brands.map(b => {
          const isExp = this.expandedBrands.has(b.name);
          const barW = Math.max(4, Math.round(((b.dispatched_cases || 0) / maxDispatched) * 100));
          return `
            <div class="mobile-entity-card ${isExp ? 'is-expanded' : ''}">
              <div class="mobile-card-header" onclick="WorkspaceProducts.toggleBrandExpansion('${AppUtils.escapeHtml(b.name)}')">
                <div class="mobile-card-title-wrap">
                  <div class="mobile-card-title">${AppUtils.escapeHtml(b.name)}</div>
                  <div class="mobile-card-meta">
                    ${AppComponents.renderCategoryBadge(b.category)}
                    <span class="mobile-card-share">${b.share_pct}% share</span>
                  </div>
                </div>
                <div class="mobile-card-stat">
                  <div class="mobile-stat-primary">${AppUtils.formatNumber(b.dispatched_cases)} cs</div>
                  <div class="mobile-stat-secondary">${AppUtils.formatCurrencyINR(b.total_mrp, true)}</div>
                </div>
              </div>
              
              <!-- Subtle Volume Bar -->
              <div class="inline-volume-bar" style="margin: 0.5rem 0;">
                <div class="bar-fill" style="width:${barW}%;"></div>
              </div>

              <!-- Metrics Strip -->
              <div class="mobile-card-metrics-grid">
                <div>
                  <span class="m-metric-label">Pending</span>
                  <span class="m-metric-val" style="${b.pending_cases > 0 ? 'color:var(--status-warning);font-weight:700;' : ''}">${b.pending_cases > 0 ? AppUtils.formatNumber(b.pending_cases) + ' cs' : '—'}</span>
                </div>
                <div>
                  <span class="m-metric-label">Loose Btls</span>
                  <span class="m-metric-val">${AppUtils.formatInteger(b.bottles)}</span>
                </div>
                <div>
                  <span class="m-metric-label">${isSingleDay ? 'Packs' : 'Velocity'}</span>
                  <span class="m-metric-val">${isSingleDay ? Object.keys(b.pack_breakdown || {}).length + ' sizes' : AppUtils.formatNumber(b.velocity_per_day, 1) + ' cs/d'}</span>
                </div>
              </div>

              ${isExp ? `
                <div class="mobile-card-expanded-body">
                  ${this.renderInlineBrandDetails(b, true)}
                </div>
              ` : ''}
            </div>
          `;
        }).join('')}
      </div>
    `;

    // Desktop Data Table View (>= 768px)
    const tableHTML = `
      <div class="data-table-container desktop-table-view">
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:32px;"></th>
                <th style="width:36px;">#</th>
                <th class="th-sortable" onclick="WorkspaceProducts.setSort('name')">
                  Brand Name ${this.renderSortIndicator('name')}
                </th>
                <th>Category</th>
                <th>Pack Formats</th>
                <th class="th-sortable" style="text-align:right;" onclick="WorkspaceProducts.setSort('dispatched_cases')">
                  Dispatched (cs) ${this.renderSortIndicator('dispatched_cases')}
                </th>
                <th class="th-sortable" style="text-align:right;" onclick="WorkspaceProducts.setSort('pending_cases')">
                  Pending (cs) ${this.renderSortIndicator('pending_cases')}
                </th>
                <th class="th-sortable" style="text-align:right;" onclick="WorkspaceProducts.setSort('bottles')">
                  Loose (btls) ${this.renderSortIndicator('bottles')}
                </th>
                ${!isSingleDay ? `
                  <th class="th-sortable" style="text-align:right;" onclick="WorkspaceProducts.setSort('velocity_per_day')">
                    Velocity (cs/d) ${this.renderSortIndicator('velocity_per_day')}
                  </th>
                ` : ''}
                <th class="th-sortable" style="text-align:right;" onclick="WorkspaceProducts.setSort('share_pct')">
                  Share ${this.renderSortIndicator('share_pct')}
                </th>
                <th class="th-sortable" style="text-align:right;" onclick="WorkspaceProducts.setSort('total_mrp')">
                  Total MRP (₹) ${this.renderSortIndicator('total_mrp')}
                </th>
                ${!isSingleDay ? `
                  <th style="text-align:center;width:95px;">Trend</th>
                ` : ''}
              </tr>
            </thead>
            <tbody>
              ${brands.length === 0 ? `
                <tr><td colspan="${isSingleDay ? 10 : 12}" style="text-align:center;padding:3.5rem;color:var(--text-muted);">No brands match filter criteria</td></tr>
              ` : brands.map((b, idx) => {
                const isExp = this.expandedBrands.has(b.name);
                const packPills = Object.keys(b.pack_breakdown || {}).map(sz => {
                  const pinfo = b.pack_breakdown[sz];
                  return `<span class="pack-pill" title="${sz}: ${AppUtils.formatNumber(pinfo.cases)} cs">${sz}</span>`;
                }).join('');
                const barW = Math.max(4, Math.round(((b.dispatched_cases || 0) / maxDispatched) * 100));

                return `
                  <tr class="${isExp ? 'row-expanded' : ''}" style="cursor:pointer;" onclick="if(!event.target.closest('a') && !event.target.closest('.row-expand-btn')) WorkspaceProducts.toggleBrandExpansion('${AppUtils.escapeHtml(b.name)}')">
                    <td>
                      <button class="row-expand-btn ${isExp ? 'expanded' : ''}" onclick="event.stopPropagation();WorkspaceProducts.toggleBrandExpansion('${AppUtils.escapeHtml(b.name)}')">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
                      </button>
                    </td>
                    <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                    <td style="font-weight:600;">
                      <a href="#" onclick="event.stopPropagation();window.inspectBrand('${encodeURIComponent(b.name)}');return false;" class="table-entity-link">
                        ${AppUtils.escapeHtml(b.name)}
                      </a>
                    </td>
                    <td>${AppComponents.renderCategoryBadge(b.category)}</td>
                    <td><div class="pack-pill-group">${packPills || '—'}</div></td>
                    <td class="cell-num" style="text-align:right;">
                      <div style="font-weight:700;">${AppUtils.formatNumber(b.dispatched_cases)}</div>
                      <div class="inline-volume-bar" style="margin-top:3px;">
                        <div class="bar-fill" style="width:${barW}%;"></div>
                      </div>
                    </td>
                    <td class="cell-num" style="text-align:right;color:${b.pending_cases > 0 ? 'var(--status-warning)' : 'var(--text-muted)'};font-weight:${b.pending_cases > 0 ? '700' : '400'};">
                      ${b.pending_cases > 0 ? AppUtils.formatNumber(b.pending_cases) : '—'}
                    </td>
                    <td class="cell-num" style="text-align:right;color:var(--text-secondary);">${AppUtils.formatInteger(b.bottles)}</td>
                    ${!isSingleDay ? `
                      <td class="cell-num" style="text-align:right;color:var(--text-secondary);">${AppUtils.formatNumber(b.velocity_per_day, 1)}</td>
                    ` : ''}
                    <td class="cell-num" style="text-align:right;color:var(--text-muted);">${b.share_pct}%</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(b.total_mrp)}</td>
                    ${!isSingleDay ? `
                      <td style="text-align:center;">
                        ${AppComponents.renderSparklineSVG(b.daily_sparkline || [])}
                      </td>
                    ` : ''}
                  </tr>
                  ${isExp ? this.renderInlineBrandDetails(b, false, isSingleDay ? 10 : 12) : ''}
                `;
              }).join('')}
            </tbody>
            <tfoot>
              <tr style="background:var(--bg-elevated);font-weight:700;border-top:1px solid var(--border-strong);">
                <td colspan="5" style="text-align:right;text-transform:uppercase;font-size:0.75rem;color:var(--text-muted);">
                  Totals (${brands.length} Brands):
                </td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(totalDispatched)}</td>
                <td class="cell-num" style="text-align:right;color:var(--status-warning);">${AppUtils.formatNumber(totalPending)}</td>
                <td></td>
                ${!isSingleDay ? `<td></td>` : ''}
                <td></td>
                <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(totalMRP)}</td>
                ${!isSingleDay ? `<td></td>` : ''}
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    `;

    return toolbarHTML + mobileCardsHTML + tableHTML;
  },

  renderInlineBrandDetails(b, isMobile = false, colspan = 12) {
    const packs = b.pack_breakdown || {};
    const buyers = b.top_buyers || [];

    const innerHTML = `
      <div class="nested-expansion-container">
        <div class="nested-grid">
          <!-- Sub-Table 1: SKU Pack Sizes -->
          <div>
            <div class="nested-section-title">Itemised Pack Sizes (${Object.keys(packs).length})</div>
            <table class="mini-data-table">
              <thead>
                <tr>
                  <th>Pack Size</th>
                  <th style="text-align:right;">Cases</th>
                  <th style="text-align:right;">Loose Btls</th>
                  <th style="text-align:right;">Total MRP</th>
                </tr>
              </thead>
              <tbody>
                ${Object.entries(packs).map(([sz, info]) => `
                  <tr>
                    <td style="font-weight:600;">${AppUtils.escapeHtml(sz)}</td>
                    <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(info.cases)} cs</td>
                    <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatInteger(info.bottles)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(info.mrp)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>

          <!-- Sub-Table 2: Top Buying Retailers -->
          <div>
            <div class="nested-section-title">Top Retailers Ordering This Brand</div>
            <table class="mini-data-table">
              <thead>
                <tr>
                  <th>Retailer Name</th>
                  <th style="text-align:right;">Cases Bought</th>
                  <th style="text-align:right;">Total Value</th>
                </tr>
              </thead>
              <tbody>
                ${buyers.length === 0 ? `
                  <tr><td colspan="3" style="color:var(--text-muted);">No direct buyer records found</td></tr>
                ` : buyers.map(byr => `
                  <tr>
                    <td>
                      <a href="#" onclick="event.stopPropagation();window.inspectParty('${encodeURIComponent(byr.name)}');return false;" class="table-entity-link">
                        ${AppUtils.escapeHtml(byr.name)}
                      </a>
                    </td>
                    <td class="cell-num" style="text-align:right;font-weight:600;">${AppUtils.formatNumber(byr.cases)} cs</td>
                    <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(byr.mrp)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    if (isMobile) {
      return innerHTML;
    }

    return `
      <tr class="nested-expansion-row">
        <td colspan="${colspan}" style="padding:0;">
          ${innerHTML}
        </td>
      </tr>
    `;
  },

  renderPackSizeMatrix(data) {
    const packs = data.pack_sizes_full || [];
    const totalCases = packs.reduce((acc, p) => acc + (p.cases || 0), 0);
    const totalMRP = packs.reduce((acc, p) => acc + (p.mrp || 0), 0);

    return `
      <div class="data-table-container">
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:36px;">#</th>
                <th>Pack Format / Container Size</th>
                <th>Category</th>
                <th style="text-align:right;">Cases Moved</th>
                <th style="text-align:right;">Loose Bottles</th>
                <th style="text-align:right;">Volume Share</th>
                <th style="text-align:right;">Total MRP (₹)</th>
              </tr>
            </thead>
            <tbody>
              ${packs.map((p, idx) => `
                <tr>
                  <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                  <td style="font-weight:700;">${AppUtils.escapeHtml(p.pack_size)}</td>
                  <td>${AppComponents.renderCategoryBadge(p.category)}</td>
                  <td class="cell-num" style="text-align:right;font-weight:700;">${AppUtils.formatNumber(p.cases)}</td>
                  <td class="cell-num" style="text-align:right;color:var(--text-secondary);">${AppUtils.formatInteger(p.bottles)}</td>
                  <td class="cell-num" style="text-align:right;color:var(--text-muted);">${p.share_pct}%</td>
                  <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(p.mrp)}</td>
                </tr>
              `).join('')}
            </tbody>
            <tfoot>
              <tr style="background:var(--bg-elevated);font-weight:700;border-top:1px solid var(--border-strong);">
                <td colspan="3" style="text-align:right;text-transform:uppercase;color:var(--text-muted);">Totals:</td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(totalCases)}</td>
                <td></td>
                <td></td>
                <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(totalMRP)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    `;
  },

  renderPendingPickList(data) {
    const list = data.pending_pick_list || [];
    const totalCasesNeeded = list.reduce((acc, item) => acc + (item.cases_needed || 0), 0);

    return `
      <div class="surface-panel" style="margin-top:1rem;">
        <div class="panel-header">
          <div>
            <div class="panel-title">Warehouse Floor Loading Pick-List</div>
            <div class="panel-subtitle">Aggregated inventory requirements to fulfill all pending bond indents</div>
          </div>
          <div style="font-family:var(--font-mono);font-weight:700;color:var(--status-warning);">
            ${AppUtils.formatNumber(totalCasesNeeded)} cs Total Pending
          </div>
        </div>
        <div class="panel-body" style="padding:0;">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:36px;">#</th>
                <th>Brand / SKU</th>
                <th>Pack Format</th>
                <th>Category</th>
                <th style="text-align:right;">Cases Needed</th>
                <th style="text-align:right;">Loose Btls</th>
                <th style="text-align:right;">Indents Waiting</th>
              </tr>
            </thead>
            <tbody>
              ${list.length === 0 ? `
                <tr><td colspan="7" style="text-align:center;padding:3rem;color:var(--status-success);">Floor Clear — No pending indents awaiting dispatch</td></tr>
              ` : list.map((item, idx) => `
                <tr>
                  <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                  <td style="font-weight:600;">${AppUtils.escapeHtml(item.brand)}</td>
                  <td><span class="pack-pill">${AppUtils.escapeHtml(item.pack_size)}</span></td>
                  <td>${AppComponents.renderCategoryBadge(item.category)}</td>
                  <td class="cell-num" style="text-align:right;color:var(--status-warning);font-weight:700;font-size:0.95rem;">
                    ${AppUtils.formatNumber(item.cases_needed)}
                  </td>
                  <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatInteger(item.bottles_needed)}</td>
                  <td class="cell-num" style="text-align:right;font-weight:600;">${item.indents_waiting}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },

  toggleBrandExpansion(brandName) {
    if (this.expandedBrands.has(brandName)) {
      this.expandedBrands.delete(brandName);
    } else {
      this.expandedBrands.add(brandName);
    }
    this.render();
  },

  toggleAllExpansions() {
    const data = AppState.movementData;
    if (!data || !data.brands_full) return;
    if (this.expandedBrands.size > 0) {
      this.expandedBrands.clear();
    } else {
      data.brands_full.forEach(b => this.expandedBrands.add(b.name));
    }
    this.render();
  }
};

window.WorkspaceProducts = WorkspaceProducts;
