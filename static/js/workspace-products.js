/**
 * PermTrack Enterprise — Workspace 2: Product & Brand Movement Matrix
 * The Core Day / Week / Month Inventory & Sales Tracker
 */
const WorkspaceProducts = {
  expandedBrands: new Set(),

  render() {
    const container = document.getElementById('workspace-products-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:4rem;color:var(--text-muted);">Loading Product Movement...</div>`;
      return;
    }

    const subView = AppState.productSubView || 'brands';

    const subnavHTML = `
      <div class="segmented-subnav">
        <button class="seg-btn ${subView === 'brands' ? 'active' : ''}" onclick="AppState.productSubView='brands';WorkspaceProducts.render();">
          📦 Brand & SKU Matrix
        </button>
        <button class="seg-btn ${subView === 'packs' ? 'active' : ''}" onclick="AppState.productSubView='packs';WorkspaceProducts.render();">
          🍾 Pack-Size Architecture
        </button>
        <button class="seg-btn ${subView === 'picklist' ? 'active' : ''}" onclick="AppState.productSubView='picklist';WorkspaceProducts.render();">
          ⏳ Pending Loading Pick-List (${data.pending_pick_list ? data.pending_pick_list.length : 0})
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

    let brands = data.brands_full || [];
    if (catFilter !== 'ALL') {
      brands = brands.filter(b => b.category === catFilter);
    }
    if (query) {
      brands = brands.filter(b => b.name.toLowerCase().includes(query));
    }

    const totalDispatched = brands.reduce((acc, b) => acc + (b.dispatched_cases || 0), 0);
    const totalMRP = brands.reduce((acc, b) => acc + (b.total_mrp || 0), 0);
    const totalPending = brands.reduce((acc, b) => acc + (b.pending_cases || 0), 0);

    const toolbarHTML = `
      <div class="table-toolbar">
        <div class="search-box-wrap">
          <svg class="search-icon-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input type="text" class="search-input" placeholder="Search brand or SKU name..." value="${AppUtils.escapeHtml(AppState.productSearchQuery)}" oninput="AppState.productSearchQuery=this.value;WorkspaceProducts.render();" />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span class="table-stats-badge">
            Showing ${brands.length} Brands • ${AppUtils.formatNumber(totalDispatched)} cs • ${AppUtils.formatCurrencyINR(totalMRP, true)}
          </span>
          <button class="action-btn" onclick="WorkspaceProducts.toggleAllExpansions()">
            ${this.expandedBrands.size > 0 ? 'Collapse All' : 'Expand All SKUs'}
          </button>
        </div>
      </div>
    `;

    const tableHTML = `
      <div class="data-table-container">
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:36px;"></th>
                <th style="width:40px;">#</th>
                <th>Brand Name</th>
                <th>Category</th>
                <th>Pack Formats</th>
                <th style="text-align:right;">Dispatched (cs)</th>
                <th style="text-align:right;">Pending (cs)</th>
                <th style="text-align:right;">Loose (btls)</th>
                <th style="text-align:right;">Velocity (cs/d)</th>
                <th style="text-align:right;">Share</th>
                <th style="text-align:right;">Total MRP (₹)</th>
                <th style="text-align:center;width:110px;">Trend</th>
              </tr>
            </thead>
            <tbody>
              ${brands.length === 0 ? `
                <tr><td colspan="12" style="text-align:center;padding:3rem;color:var(--text-muted);">No brands match filter criteria</td></tr>
              ` : brands.map((b, idx) => {
                const isExp = this.expandedBrands.has(b.name);
                const packPills = Object.keys(b.pack_breakdown || {}).map(sz => {
                  const pinfo = b.pack_breakdown[sz];
                  return `<span class="pack-pill" title="${sz}: ${AppUtils.formatNumber(pinfo.cases)} cs">${sz}</span>`;
                }).join('');

                return `
                  <tr class="${isExp ? 'row-expanded' : ''}">
                    <td>
                      <button class="row-expand-btn ${isExp ? 'expanded' : ''}" onclick="WorkspaceProducts.toggleBrandExpansion('${AppUtils.escapeHtml(b.name)}')">
                        ▶
                      </button>
                    </td>
                    <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                    <td style="font-weight:600;">
                      <a href="#" onclick="window.inspectBrand('${encodeURIComponent(b.name)}');return false;" style="color:var(--text-primary);hover:underline;">
                        ${AppUtils.escapeHtml(b.name)}
                      </a>
                    </td>
                    <td>${AppComponents.renderCategoryBadge(b.category)}</td>
                    <td><div class="pack-pill-group">${packPills || '—'}</div></td>
                    <td class="cell-num" style="text-align:right;font-weight:700;">${AppUtils.formatNumber(b.dispatched_cases)}</td>
                    <td class="cell-num" style="text-align:right;color:${b.pending_cases > 0 ? 'var(--status-warning)' : 'var(--text-muted)'};font-weight:${b.pending_cases > 0 ? '700' : '400'};">
                      ${b.pending_cases > 0 ? AppUtils.formatNumber(b.pending_cases) : '—'}
                    </td>
                    <td class="cell-num" style="text-align:right;color:var(--text-secondary);">${AppUtils.formatInteger(b.bottles)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--text-secondary);">${AppUtils.formatNumber(b.velocity_per_day, 1)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--text-muted);">${b.share_pct}%</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(b.total_mrp)}</td>
                    <td style="text-align:center;">
                      ${AppComponents.renderSparklineSVG(b.daily_sparkline || [])}
                    </td>
                  </tr>
                  ${isExp ? this.renderInlineBrandDetails(b) : ''}
                `;
              }).join('')}
            </tbody>
            <tfoot>
              <tr style="background:var(--bg-elevated);font-weight:700;border-top:2px solid var(--border-strong);">
                <td colspan="5" style="text-align:right;text-transform:uppercase;font-size:0.75rem;color:var(--text-muted);">
                  Totals (${brands.length} Brands):
                </td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(totalDispatched)}</td>
                <td class="cell-num" style="text-align:right;color:var(--status-warning);">${AppUtils.formatNumber(totalPending)}</td>
                <td colspan="3"></td>
                <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(totalMRP)}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    `;

    return toolbarHTML + tableHTML;
  },

  renderInlineBrandDetails(b) {
    const packs = b.pack_breakdown || {};
    const buyers = b.top_buyers || [];

    return `
      <tr>
        <td colspan="12" style="padding:0;">
          <div class="nested-expansion-container">
            <div class="nested-grid">
              <!-- Sub-Table 1: SKU Pack Sizes -->
              <div>
                <div class="nested-section-title">🍾 Itemised Pack Sizes (${Object.keys(packs).length})</div>
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
                <div class="nested-section-title">🏪 Top Retailers Ordering This Brand</div>
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
                          <a href="#" onclick="window.inspectParty('${encodeURIComponent(byr.name)}');return false;" style="color:var(--text-primary);text-decoration:underline;">
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
                <th style="width:40px;">#</th>
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
                  <td style="font-weight:700;font-size:0.95rem;">${AppUtils.escapeHtml(p.size)}</td>
                  <td>${AppComponents.renderCategoryBadge(p.category)}</td>
                  <td class="cell-num" style="text-align:right;font-weight:700;">${AppUtils.formatNumber(p.cases)} cs</td>
                  <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatInteger(p.bottles)}</td>
                  <td class="cell-num" style="text-align:right;color:var(--text-secondary);">${p.share_pct}%</td>
                  <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(p.mrp)}</td>
                </tr>
              `).join('')}
            </tbody>
            <tfoot>
              <tr style="background:var(--bg-elevated);font-weight:700;border-top:2px solid var(--border-strong);">
                <td colspan="3" style="text-align:right;text-transform:uppercase;color:var(--text-muted);">Total Pack Movement:</td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(totalCases)} cs</td>
                <td></td>
                <td>100.0%</td>
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
    const totalCases = list.reduce((acc, item) => acc + (item.total_cases_eq || 0), 0);

    return `
      <div style="background:rgba(245, 158, 11, 0.08);border:1px solid rgba(245, 158, 11, 0.25);border-radius:var(--radius-lg);padding:1rem 1.25rem;margin-bottom:1rem;display:flex;align-items:center;justify-content:space-between;">
        <div>
          <div style="font-weight:700;color:var(--accent-amber);font-size:1rem;">
            📋 Warehouse Floor Pick-List (${list.length} Required SKUs • ${AppUtils.formatNumber(totalCases)} Total Cases)
          </div>
          <div style="font-size:0.8rem;color:var(--text-secondary);margin-top:2px;">
            Aggregated inventory required to fulfill all active Pending Indents in the bond.
          </div>
        </div>
        <button class="action-btn" onclick="window.print();" style="background:var(--accent-amber);color:#090B10;font-weight:700;">
          🖨️ Print Floor Pick-Slip
        </button>
      </div>

      <div class="data-table-container">
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:40px;">#</th>
                <th>Brand Name</th>
                <th>Pack Size</th>
                <th>Category</th>
                <th style="text-align:right;">Cases to Load</th>
                <th style="text-align:right;">Loose Btls</th>
                <th style="text-align:right;">Total Eq Cases</th>
                <th style="text-align:right;">Indents Waiting</th>
                <th>Destinations / Licensees Waiting</th>
              </tr>
            </thead>
            <tbody>
              ${list.length === 0 ? `
                <tr><td colspan="9" style="text-align:center;padding:3rem;color:var(--text-muted);">🎉 No pending indents currently waiting in bond! Floor is clear.</td></tr>
              ` : list.map((item, idx) => `
                <tr>
                  <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                  <td style="font-weight:700;">${AppUtils.escapeHtml(item.brand_name)}</td>
                  <td><span class="pack-pill">${AppUtils.escapeHtml(item.pack_size)}</span></td>
                  <td>${AppComponents.renderCategoryBadge(item.category)}</td>
                  <td class="cell-num" style="text-align:right;font-weight:700;font-size:1.05rem;color:var(--status-warning);">
                    ${AppUtils.formatNumber(item.cases)}
                  </td>
                  <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatInteger(item.bottles)}</td>
                  <td class="cell-num" style="text-align:right;font-weight:700;">${AppUtils.formatNumber(item.total_cases_eq)} cs</td>
                  <td class="cell-num" style="text-align:right;font-weight:600;">${item.permits_count}</td>
                  <td>
                    <div style="display:flex;flex-wrap:wrap;gap:4px;">
                      ${item.licensees.map(lic => `<span class="pack-pill" style="color:var(--text-primary);">${AppUtils.escapeHtml(lic)}</span>`).join('')}
                    </div>
                  </td>
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
