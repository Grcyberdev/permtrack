/**
 * PermTrack Enterprise — Workspace 4: Retailer Intelligence
 * Minimal, Calm, Executive Precision with Responsive Mobile Cards
 */
const WorkspaceParties = {
  _debounceTimer: null,

  setSort(col) {
    if (AppState.partySortCol === col) {
      AppState.partySortDir = AppState.partySortDir === 'desc' ? 'asc' : 'desc';
    } else {
      AppState.partySortCol = col;
      AppState.partySortDir = 'desc';
    }
    this.renderResultsOnly();
  },

  renderSortIndicator(col) {
    if (AppState.partySortCol !== col) {
      return `<span class="sort-icon-neutral">↕</span>`;
    }
    return `<span class="sort-icon-active">${AppState.partySortDir === 'desc' ? '↓' : '↑'}</span>`;
  },

  getFilteredParties(data) {
    const d = data || AppState.movementData;
    if (!d || !d.parties_full) return [];

    let parties = d.parties_full || [];
    const q = (AppState.partySearchQuery || '').toLowerCase().trim();
    if (q) {
      parties = parties.filter(p =>
        p.name.toLowerCase().includes(q) ||
        (p.district && p.district.toLowerCase().includes(q))
      );
    }

    // Fix 12: Category filter in Retailers — use category cases as volume metric
    const catFilter = AppState.categoryFilter || 'ALL';
    if (catFilter !== 'ALL') {
      const volProp = catFilter === 'BEER' ? 'beer_cases' : (catFilter === 'CS' ? 'cs_cases' : 'imfl_cases');
      parties = parties
        .map(p => ({
          ...p,
          filteredVolume: p[volProp] || 0.0
        }))
        .filter(p => p.filteredVolume > 0 || (p.pending_cases > 0));
    } else {
      parties = parties.map(p => ({
        ...p,
        filteredVolume: p.dispatched_cases || 0.0
      }));
    }

    const sortCol = AppState.partySortCol || 'dispatched_cases';
    const sortDir = AppState.partySortDir || 'desc';
    const mult = sortDir === 'asc' ? 1 : -1;

    return [...parties].sort((a, b) => {
      let valA = a[sortCol];
      let valB = b[sortCol];
      if (sortCol === 'dispatched_cases' && catFilter !== 'ALL') {
        valA = a.filteredVolume;
        valB = b.filteredVolume;
      }
      if (typeof valA === 'string') {
        return (valA || '').localeCompare(valB || '') * mult;
      }
      valA = Number(valA || 0);
      valB = Number(valB || 0);
      return (valA - valB) * mult;
    });
  },

  render() {
    const container = document.getElementById('workspace-parties-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:5rem;color:var(--text-muted);">Loading Retailers...</div>`;
      return;
    }

    const toolbarHTML = `
      <div class="table-toolbar">
        <div class="search-box-wrap">
          <svg class="search-icon-svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input
            type="text"
            id="parties-search-input"
            class="search-input"
            placeholder="Search retailer name, shop or district..."
            value="${AppUtils.escapeHtml(AppState.partySearchQuery)}"
          />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span class="table-stats-badge" id="parties-stats-badge">
            Loading...
          </span>
        </div>
      </div>
      <div id="parties-results-container"></div>
    `;

    container.innerHTML = toolbarHTML;
    this.attachDelegatedListeners(container);
    this.renderPartiesResults(data);
  },

  renderResultsOnly() {
    const data = AppState.movementData;
    if (!data) return;
    this.renderPartiesResults(data);
  },

  renderPartiesResults(data) {
    const resultsContainer = document.getElementById('parties-results-container');
    const statsBadge = document.getElementById('parties-stats-badge');
    if (!resultsContainer) return;

    const parties = this.getFilteredParties(data);
    const catFilter = AppState.categoryFilter || 'ALL';
    const totalCases = parties.reduce((acc, p) => acc + (p.filteredVolume || 0), 0);
    const totalMRP = parties.reduce((acc, p) => acc + (p.mrp || 0), 0);
    const totalPending = parties.reduce((acc, p) => acc + (p.pending_cases || 0), 0);

    if (statsBadge) {
      statsBadge.innerText = `${parties.length} Retailers • ${AppUtils.formatNumber(totalCases)} cs • ${AppUtils.formatCurrencyINR(totalMRP, true)}`;
    }

    // Responsive Mobile Cards View (< 768px)
    const mobileCardsHTML = `
      <div class="mobile-cards-view">
        ${parties.length === 0 ? `
          <div style="text-align:center;padding:3rem 1rem;color:var(--text-muted);">No retailers found matching search</div>
        ` : parties.map(p => {
          const tot = (p.dispatched_cases || 0) || 1;
          const beerPct = Math.round(((p.beer_cases || 0) / tot) * 100);
          const imflPct = Math.round(((p.imfl_cases || 0) / tot) * 100);
          const csPct = Math.round(((p.cs_cases || 0) / tot) * 100);

          return `
            <div class="mobile-entity-card" data-action="inspect-party" data-name="${AppUtils.escapeHtml(p.name)}" style="cursor:pointer;">
              <div class="mobile-card-header">
                <div class="mobile-card-title-wrap">
                  <div class="mobile-card-title">${AppUtils.escapeHtml(p.name)}</div>
                  <div class="mobile-card-meta">
                    <span class="pack-pill">${AppUtils.escapeHtml(p.district || 'Assam')}</span>
                    <span class="mobile-card-share">${p.indent_count} indents</span>
                  </div>
                </div>
                <div class="mobile-card-stat">
                  <div class="mobile-stat-primary">${AppUtils.formatNumber(p.filteredVolume)} cs</div>
                  <div class="mobile-stat-secondary">${AppUtils.formatCurrencyINR(p.mrp, true)}</div>
                </div>
              </div>

              <!-- Proportional Category Mix Mini-Bar -->
              <div class="proportional-bar-container" style="height:4px;margin:0.5rem 0;">
                <div class="bar-seg seg-beer" style="width:${beerPct}%;"></div>
                <div class="bar-seg seg-imfl" style="width:${imflPct}%;"></div>
                <div class="bar-seg seg-cs" style="width:${csPct}%;"></div>
              </div>

              <div class="mobile-card-metrics-grid">
                <div>
                  <span class="m-metric-label">Pending</span>
                  <span class="m-metric-val" style="${p.pending_cases > 0 ? 'color:var(--status-warning);font-weight:700;' : ''}">${p.pending_cases > 0 ? AppUtils.formatNumber(p.pending_cases) + ' cs' : '—'}</span>
                </div>
                <div>
                  <span class="m-metric-label">Last Order</span>
                  <span class="m-metric-val">${AppUtils.escapeHtml(p.last_order_date || '—')}</span>
                </div>
                <div>
                  <span class="m-metric-label">Status</span>
                  <span class="m-metric-val">${p.cadence_status === 'regular' ? 'Regular' : (p.cadence_status === 'dormant' ? 'Dormant' : 'Active')}</span>
                </div>
              </div>

              ${(p.brands_bought && p.brands_bought.length > 0) ? `
                <div style="margin-top:0.6rem;padding-top:0.5rem;border-top:1px solid var(--border-hairline);">
                  <div style="font-size:0.7rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:4px;">Top Brands:</div>
                  <div class="pack-pill-group">
                    ${p.brands_bought.slice(0, 3).map(b => `
                      <span class="pack-pill" style="font-size:0.725rem;">${AppUtils.escapeHtml(b.name)} (${AppUtils.formatNumber(b.cases, 0)}cs)</span>
                    `).join('')}
                  </div>
                </div>
              ` : ''}
            </div>
          `;
        }).join('')}
      </div>
    `;

    // Desktop Data Table View (>= 768px)
    const volumeHeaderLabel = catFilter === 'ALL' ? 'Dispatched (cs)' : `Dispatched (${catFilter} cs)`;

    const tableHTML = `
      <div class="data-table-container desktop-table-view">
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:36px;">#</th>
                <th class="th-sortable" data-action="sort" data-col="name">
                  Licensee / Retail Shop Name ${this.renderSortIndicator('name')}
                </th>
                <th>District</th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="dispatched_cases">
                  ${volumeHeaderLabel} ${this.renderSortIndicator('dispatched_cases')}
                </th>
                <th style="text-align:center;width:140px;">Category Mix</th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="pending_cases">
                  Pending in Bond ${this.renderSortIndicator('pending_cases')}
                </th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="mrp">
                  Total Turnover (₹) ${this.renderSortIndicator('mrp')}
                </th>
                <th class="th-sortable" style="text-align:center;" data-action="sort" data-col="last_order_date">
                  Cadence & Last Order ${this.renderSortIndicator('last_order_date')}
                </th>
                <th>Top Brands Bought</th>
              </tr>
            </thead>
            <tbody>
              ${parties.length === 0 ? `
                <tr><td colspan="9" style="text-align:center;padding:3.5rem;color:var(--text-muted);">No retailers found matching search</td></tr>
              ` : parties.map((p, idx) => {
                const tot = (p.dispatched_cases || 0) || 1;
                const beerPct = Math.round(((p.beer_cases || 0) / tot) * 100);
                const imflPct = Math.round(((p.imfl_cases || 0) / tot) * 100);
                const csPct = Math.round(((p.cs_cases || 0) / tot) * 100);

                const topBrandsList = (p.brands_bought || []).slice(0, 2).map(b =>
                  `<span class="pack-pill" title="${AppUtils.escapeHtml(b.name)}: ${AppUtils.formatNumber(b.cases)} cs">${AppUtils.escapeHtml(b.name)} (${AppUtils.formatNumber(b.cases, 0)}cs)</span>`
                ).join('');

                let cadenceBadge = `<span class="party-cadence-badge cadence-active">Active</span>`;
                if (p.cadence_status === 'regular') {
                  cadenceBadge = `<span class="party-cadence-badge cadence-regular">Regular</span>`;
                } else if (p.cadence_status === 'dormant') {
                  cadenceBadge = `<span class="party-cadence-badge cadence-dormant">Dormant</span>`;
                }

                return `
                  <tr style="cursor:pointer;" data-action="inspect-party" data-name="${AppUtils.escapeHtml(p.name)}">
                    <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                    <td style="font-weight:600;">
                      <a href="#" data-action="inspect-party" data-name="${AppUtils.escapeHtml(p.name)}" class="table-entity-link">
                        ${AppUtils.escapeHtml(p.name)}
                      </a>
                    </td>
                    <td><span class="pack-pill">${AppUtils.escapeHtml(p.district || 'Assam')}</span></td>
                    <td class="cell-num" style="text-align:right;font-weight:700;">
                      ${AppUtils.formatNumber(p.filteredVolume)}
                    </td>
                    <td>
                      <div class="proportional-bar-container" style="height:5px;" title="Beer: ${AppUtils.formatNumber(p.beer_cases, 0)} cs (${beerPct}%) | IMFL: ${AppUtils.formatNumber(p.imfl_cases, 0)} cs (${imflPct}%) | CS: ${AppUtils.formatNumber(p.cs_cases, 0)} cs (${csPct}%)">
                        <div class="bar-seg seg-beer" style="width:${beerPct}%;"></div>
                        <div class="bar-seg seg-imfl" style="width:${imflPct}%;"></div>
                        <div class="bar-seg seg-cs" style="width:${csPct}%;"></div>
                      </div>
                    </td>
                    <td class="cell-num" style="text-align:right;color:${p.pending_cases > 0 ? 'var(--status-warning)' : 'var(--text-muted)'};font-weight:${p.pending_cases > 0 ? '700' : '400'};">
                      ${p.pending_cases > 0 ? AppUtils.formatNumber(p.pending_cases) + ' cs' : '—'}
                    </td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">
                      ${AppUtils.formatCurrencyINR(p.mrp)}
                    </td>
                    <td style="text-align:center;">
                      <div style="display:flex;flex-direction:column;align-items:center;gap:2px;">
                        ${cadenceBadge}
                        <span class="num-tabular" style="font-size:0.75rem;color:var(--text-muted);white-space:nowrap;">
                          ${AppUtils.escapeHtml(p.last_order_date || '—')}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div class="pack-pill-group">${topBrandsList || '—'}</div>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
            <tfoot>
              <tr style="background:var(--bg-elevated);font-weight:700;border-top:1px solid var(--border-strong);">
                <td colspan="3" style="text-align:right;text-transform:uppercase;font-size:0.75rem;color:var(--text-muted);">
                  Totals (${parties.length} Retailers):
                </td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(totalCases)}</td>
                <td></td>
                <td class="cell-num" style="text-align:right;color:var(--status-warning);">${AppUtils.formatNumber(totalPending)}</td>
                <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(totalMRP)}</td>
                <td colspan="2"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    `;

    resultsContainer.innerHTML = mobileCardsHTML + tableHTML;
  },

  attachDelegatedListeners(container) {
    if (container._delegatedPartyListener) return;
    container._delegatedPartyListener = true;

    // Delegated click handler (Fix 5: quote-safe inspection)
    container.addEventListener('click', (e) => {
      const target = e.target.closest('[data-action]');
      if (!target) return;
      const action = target.dataset.action;

      if (action === 'inspect-party') {
        e.preventDefault();
        window.inspectParty(target.dataset.name);
      } else if (action === 'sort') {
        WorkspaceParties.setSort(target.dataset.col);
      }
    });

    // Debounced input handler for search (Fix 4)
    container.addEventListener('input', (e) => {
      if (e.target.id === 'parties-search-input') {
        AppState.partySearchQuery = e.target.value;
        clearTimeout(WorkspaceParties._debounceTimer);
        WorkspaceParties._debounceTimer = setTimeout(() => {
          WorkspaceParties.renderPartiesResults();
        }, 150);
      }
    });
  }
};

window.WorkspaceParties = WorkspaceParties;
