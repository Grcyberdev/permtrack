/**
 * PermTrack Enterprise — Workspace 2: Product & Brand Movement Matrix
 * Minimal, Calm, Executive Precision with Responsive Mobile Cards
 */
const WorkspaceProducts = {
  expandedBrands: new Set(),
  _debounceTimer: null,

  setSort(col) {
    if (AppState.productSortCol === col) {
      AppState.productSortDir = AppState.productSortDir === 'desc' ? 'asc' : 'desc';
    } else {
      AppState.productSortCol = col;
      AppState.productSortDir = 'desc';
    }
    this.renderResultsOnly();
  },

  renderSortIndicator(col) {
    if (AppState.productSortCol !== col) {
      return `<span class="sort-icon-neutral">↕</span>`;
    }
    return `<span class="sort-icon-active">${AppState.productSortDir === 'desc' ? '↓' : '↑'}</span>`;
  },

  getFilteredBrands(data) {
    const d = data || AppState.movementData;
    if (!d || !d.brands_full) return [];

    const query = (AppState.productSearchQuery || '').toLowerCase().trim();
    const catFilter = AppState.categoryFilter || 'ALL';

    let brands = d.brands_full || [];
    if (catFilter !== 'ALL') {
      brands = brands.filter(b => b.category === catFilter);
    }
    if (query) {
      brands = brands.filter(b => b.name.toLowerCase().includes(query));
    }

    const sortCol = AppState.productSortCol || 'dispatched_cases';
    const sortDir = AppState.productSortDir || 'desc';
    const mult = sortDir === 'asc' ? 1 : -1;

    return [...brands].sort((a, b) => {
      let valA = a[sortCol];
      let valB = b[sortCol];
      if (typeof valA === 'string') {
        return (valA || '').localeCompare(valB || '') * mult;
      }
      valA = Number(valA || 0);
      valB = Number(valB || 0);
      return (valA - valB) * mult;
    });
  },

  render() {
    const container = document.getElementById('workspace-products-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:5rem;color:var(--text-muted);">Loading Products...</div>`;
      return;
    }

    const catFilter = AppState.categoryFilter || 'ALL';
    let filteredPacks = data.pack_sizes_full || [];
    let filteredPickList = data.pending_pick_list || [];

    if (catFilter !== 'ALL') {
      filteredPacks = filteredPacks.filter(p => p.category === catFilter);
      filteredPickList = filteredPickList.filter(item => item.category === catFilter);
    }

    const subView = AppState.productSubView || 'brands';

    const subnavHTML = `
      <div class="segmented-subnav">
        <button class="seg-btn ${subView === 'brands' ? 'active' : ''}" data-action="subview" data-sub="brands">
          Brand & SKU Matrix
        </button>
        <button class="seg-btn ${subView === 'packs' ? 'active' : ''}" data-action="subview" data-sub="packs">
          Pack-Size Architecture
        </button>
        <button class="seg-btn ${subView === 'picklist' ? 'active' : ''}" data-action="subview" data-sub="picklist">
          Pending Pick-List (${filteredPickList.length})
        </button>
      </div>
    `;

    let contentHTML = '';
    if (subView === 'brands') {
      contentHTML = this.renderBrandMatrixShell(data);
    } else if (subView === 'packs') {
      contentHTML = this.renderPackSizeMatrix({ ...data, pack_sizes_full: filteredPacks });
    } else {
      // Fix 2: Pick-list shared floor component
      contentHTML = AppComponents.renderFloorPickList(filteredPickList);
    }

    container.innerHTML = subnavHTML + contentHTML;

    // Attach delegated listener (Fix 5)
    this.attachDelegatedListeners(container);

    if (subView === 'brands') {
      this.renderBrandMatrixResults(data);
    }
  },

  renderBrandMatrixShell(data) {
    return `
      <div class="table-toolbar">
        <div class="search-box-wrap">
          <svg class="search-icon-svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input
            type="text"
            id="products-search-input"
            class="search-input"
            placeholder="Search brands or SKUs..."
            value="${AppUtils.escapeHtml(AppState.productSearchQuery)}"
          />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span class="table-stats-badge" id="products-stats-badge">
            Loading...
          </span>
          <button class="action-btn" id="products-expand-all-btn" data-action="toggle-all-expansions">
            ${this.expandedBrands.size > 0 ? 'Collapse All' : 'Expand All'}
          </button>
        </div>
      </div>
      <div id="products-results-container"></div>
    `;
  },

  renderResultsOnly() {
    const data = AppState.movementData;
    if (!data) return;
    const subView = AppState.productSubView || 'brands';
    if (subView === 'brands') {
      this.renderBrandMatrixResults(data);
    } else {
      this.render();
    }
  },

  renderBrandMatrixResults(data) {
    const resultsContainer = document.getElementById('products-results-container');
    const statsBadge = document.getElementById('products-stats-badge');
    const expandBtn = document.getElementById('products-expand-all-btn');
    if (!resultsContainer) return;

    const brands = this.getFilteredBrands(data);
    const isSingleDay = (AppState.horizonMode === 'day') || ((data.daily_series || []).length <= 1);

    const totalDispatched = brands.reduce((acc, b) => acc + (b.dispatched_cases || 0), 0);
    const totalMRP = brands.reduce((acc, b) => acc + (b.total_mrp || 0), 0);
    const maxDispatched = brands.length > 0 ? Math.max(...brands.map(b => b.dispatched_cases || 0), 1) : 1;

    if (statsBadge) {
      statsBadge.innerText = `${brands.length} Brands • ${AppUtils.formatNumber(totalDispatched)} cs • ${AppUtils.formatCurrencyINR(totalMRP, true)}`;
    }
    if (expandBtn) {
      expandBtn.innerText = this.expandedBrands.size > 0 ? 'Collapse All' : 'Expand All';
    }

    // Responsive Mobile Cards View (< 768px)
    const mobileCardsHTML = `
      <div class="mobile-cards-view">
        ${brands.length === 0 ? `
          <div style="text-align:center;padding:3rem 1rem;color:var(--text-muted);">No brands match search or filter criteria</div>
        ` : brands.map(b => {
          const isExp = this.expandedBrands.has(b.name);
          const barW = Math.max(4, Math.round(((b.dispatched_cases || 0) / maxDispatched) * 100));
          return `
            <div class="mobile-entity-card ${isExp ? 'is-expanded' : ''}">
              <div class="mobile-card-header" data-action="toggle-brand" data-name="${AppUtils.escapeHtml(b.name)}" style="cursor:pointer;">
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
              
              <div class="inline-volume-bar" style="margin: 0.5rem 0;">
                <div class="bar-fill" style="width:${barW}%;"></div>
              </div>

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
                <th class="th-sortable" data-action="sort" data-col="name">
                  Brand Name ${this.renderSortIndicator('name')}
                </th>
                <th>Category</th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="dispatched_cases">
                  Dispatched (cs) ${this.renderSortIndicator('dispatched_cases')}
                </th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="pending_cases">
                  Pending in Bond ${this.renderSortIndicator('pending_cases')}
                </th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="bottles">
                  Loose Bottles ${this.renderSortIndicator('bottles')}
                </th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="velocity_per_day">
                  Velocity ${this.renderSortIndicator('velocity_per_day')}
                </th>
                <th style="width:100px;">Volume Share</th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="total_mrp">
                  Turnover (MRP) ${this.renderSortIndicator('total_mrp')}
                </th>
                <th style="text-align:center;width:60px;">Trend</th>
              </tr>
            </thead>
            <tbody>
              ${brands.length === 0 ? `
                <tr><td colspan="11" style="text-align:center;padding:3.5rem;color:var(--text-muted);">No brands match search or filter criteria</td></tr>
              ` : brands.map((b, idx) => {
                const isExp = this.expandedBrands.has(b.name);
                const barW = Math.max(4, Math.round(((b.dispatched_cases || 0) / maxDispatched) * 100));

                return `
                  <tr class="${isExp ? 'row-expanded' : ''}">
                    <td>
                      <button class="row-expand-btn ${isExp ? 'expanded' : ''}" data-action="toggle-brand" data-name="${AppUtils.escapeHtml(b.name)}">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
                      </button>
                    </td>
                    <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                    <td style="font-weight:600;">
                      <a href="#" data-action="inspect-brand" data-name="${AppUtils.escapeHtml(b.name)}" class="table-entity-link">
                        ${AppUtils.escapeHtml(b.name)}
                      </a>
                    </td>
                    <td>${AppComponents.renderCategoryBadge(b.category)}</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;">
                      ${AppUtils.formatNumber(b.dispatched_cases)}
                    </td>
                    <td class="cell-num" style="text-align:right;color:${b.pending_cases > 0 ? 'var(--status-warning)' : 'var(--text-muted)'};font-weight:${b.pending_cases > 0 ? '700' : '400'};">
                      ${b.pending_cases > 0 ? AppUtils.formatNumber(b.pending_cases) + ' cs' : '—'}
                    </td>
                    <td class="cell-num" style="text-align:right;color:var(--text-muted);">
                      ${AppUtils.formatInteger(b.bottles)}
                    </td>
                    <td class="cell-num" style="text-align:right;color:var(--text-secondary);">
                      ${isSingleDay ? '—' : AppUtils.formatNumber(b.velocity_per_day, 1) + ' cs/d'}
                    </td>
                    <td>
                      <div class="inline-volume-bar">
                        <div class="bar-fill" style="width:${barW}%;"></div>
                      </div>
                    </td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">
                      ${AppUtils.formatCurrencyINR(b.total_mrp)}
                    </td>
                    <td style="text-align:center;">
                      ${AppComponents.renderSparklineSVG(b.daily_sparkline || [])}
                    </td>
                  </tr>
                  ${isExp ? this.renderInlineBrandDetails(b, false, 11) : ''}
                `;
              }).join('')}
            </tbody>
            <tfoot>
              <tr style="background:var(--bg-elevated);font-weight:700;border-top:1px solid var(--border-strong);">
                <td colspan="4" style="text-align:right;text-transform:uppercase;font-size:0.75rem;color:var(--text-muted);">
                  Totals (${brands.length} Brands):
                </td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(totalDispatched)}</td>
                <td class="cell-num" style="text-align:right;color:var(--status-warning);">${AppUtils.formatNumber(brands.reduce((a, b) => a + (b.pending_cases || 0), 0))}</td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatInteger(brands.reduce((a, b) => a + (b.bottles || 0), 0))}</td>
                <td></td>
                <td></td>
                <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(totalMRP)}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    `;

    resultsContainer.innerHTML = mobileCardsHTML + tableHTML;
  },

  renderInlineBrandDetails(b, isMobile = false, colspan = 11) {
    const packs = b.pack_breakdown || {};
    const buyers = b.top_buyers || [];

    const innerHTML = `
      <div class="nested-expansion-container" style="padding:0.875rem 1.25rem;">
        <div class="nested-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;">
          <div>
            <div class="nested-section-title">Pack Sizes Moved (${Object.keys(packs).length} sizes)</div>
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
                      <a href="#" data-action="inspect-party" data-name="${AppUtils.escapeHtml(byr.name)}" class="table-entity-link">
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

    if (isMobile) return innerHTML;

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
              ${packs.map((p, idx) => {
                const packName = p.size || p.pack_size || 'Unknown';
                return `
                  <tr>
                    <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                    <td style="font-weight:700;">${AppUtils.escapeHtml(packName)}</td>
                    <td>${AppComponents.renderCategoryBadge(p.category)}</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;">${AppUtils.formatNumber(p.cases)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--text-secondary);">${AppUtils.formatInteger(p.bottles)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--text-muted);">${p.share_pct}%</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(p.mrp)}</td>
                  </tr>
                `;
              }).join('')}
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

  toggleBrandExpansion(brandName) {
    if (this.expandedBrands.has(brandName)) {
      this.expandedBrands.delete(brandName);
    } else {
      this.expandedBrands.add(brandName);
    }
    this.renderResultsOnly();
  },

  toggleAllExpansions() {
    if (this.expandedBrands.size > 0) {
      this.expandedBrands.clear();
      this.renderResultsOnly();
      return;
    }
    const visibleBrands = this.getFilteredBrands();
    const toExpand = visibleBrands.slice(0, 50);
    toExpand.forEach(b => this.expandedBrands.add(b.name));
    if (visibleBrands.length > 50) {
      AppUtils.showToast(`Expanded first 50 of ${visibleBrands.length} brands`, 'info');
    }
    this.renderResultsOnly();
  },

  attachDelegatedListeners(container) {
    if (container._delegatedProductListener) return;
    container._delegatedProductListener = true;

    // Delegated click handler (Fix 5)
    container.addEventListener('click', (e) => {
      const target = e.target.closest('[data-action]');
      if (!target) return;
      const action = target.dataset.action;

      if (action === 'subview') {
        AppState.productSubView = target.dataset.sub;
        WorkspaceProducts.render();
      } else if (action === 'toggle-brand') {
        WorkspaceProducts.toggleBrandExpansion(target.dataset.name);
      } else if (action === 'inspect-brand') {
        e.preventDefault();
        window.inspectBrand(target.dataset.name);
      } else if (action === 'inspect-party') {
        e.preventDefault();
        window.inspectParty(target.dataset.name);
      } else if (action === 'sort') {
        WorkspaceProducts.setSort(target.dataset.col);
      } else if (action === 'toggle-all-expansions') {
        WorkspaceProducts.toggleAllExpansions();
      }
    });

    // Debounced input handler for search (Fix 4)
    container.addEventListener('input', (e) => {
      if (e.target.id === 'products-search-input') {
        AppState.productSearchQuery = e.target.value;
        clearTimeout(WorkspaceProducts._debounceTimer);
        WorkspaceProducts._debounceTimer = setTimeout(() => {
          WorkspaceProducts.renderBrandMatrixResults();
        }, 150);
      }
    });
  }
};

window.WorkspaceProducts = WorkspaceProducts;
