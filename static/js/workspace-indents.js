/**
 * PermTrack Enterprise — Workspace 3: Bond Indents & Live Dispatch Ledger
 * Minimal, Calm, Executive Precision with Responsive Mobile Cards
 */
const WorkspaceIndents = {
  expandedPermits: new Set(),
  _debounceTimer: null,

  parseDateSortKey(dateStr) {
    if (!dateStr) return '00000000';
    const s = String(dateStr).trim();
    if (/^\d{8}$/.test(s)) return s;
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s.replace(/-/g, '');
    const dmy = s.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
    if (dmy) {
      return `${dmy[3]}${dmy[2].padStart(2, '0')}${dmy[1].padStart(2, '0')}`;
    }
    const dmon = s.match(/^(\d{1,2})[-/\s]([A-Za-z]+)[-/\s](\d{4})$/);
    if (dmon) {
      const monthMap = { jan: '01', feb: '02', mar: '03', apr: '04', may: '05', jun: '06', jul: '07', aug: '08', sep: '09', oct: '10', nov: '11', dec: '12' };
      const mStr = monthMap[dmon[2].slice(0, 3).toLowerCase()] || '01';
      return `${dmon[3]}${mStr}${dmon[1].padStart(2, '0')}`;
    }
    return s.replace(/\D/g, '').padEnd(8, '0').slice(0, 8) || '00000000';
  },

  setSort(col) {
    if (AppState.indentSortCol === col) {
      AppState.indentSortDir = AppState.indentSortDir === 'desc' ? 'asc' : 'desc';
    } else {
      AppState.indentSortCol = col;
      AppState.indentSortDir = 'desc';
    }
    this.renderResultsOnly();
  },

  renderSortIndicator(col) {
    if (AppState.indentSortCol !== col) {
      return `<span class="sort-icon-neutral">↕</span>`;
    }
    return `<span class="sort-icon-active">${AppState.indentSortDir === 'desc' ? '↓' : '↑'}</span>`;
  },

  groupPermits(rawRecords) {
    const groups = {};
    if (!rawRecords || !Array.isArray(rawRecords)) return [];

    rawRecords.forEach(item => {
      const pNum = String(item['Permit Number'] || '').trim();
      const tp = String(item['Transit Pass'] || '').trim();
      const ind = String(item['Indent Number'] || '').trim();
      const lic = String(item['Licensee Name'] || item['Retailer Name'] || '').trim();
      const dt = String(item['Challan Date'] || item['Date'] || '').trim();

      const key = pNum || tp || ind || `${lic}_${dt}`;

      if (!groups[key]) {
        const rawDate = item['Challan Date'] || item['Date'] || '';
        groups[key] = {
          key: key,
          permitNumber: pNum,
          transitPass: tp,
          indentNumber: ind,
          licenseeName: item['Licensee Name'] || item['Retailer Name'] || 'Unknown Licensee',
          retailerName: item['Retailer Name'] || item['Licensee Name'] || '',
          retailerCode: item['Retailer Code'] || '',
          district: item['District'] || item['Destination District'] || '',
          vehicleNumber: item['Vehicle Number'] || '',
          date: item['Date'] || '',
          challanDate: rawDate,
          dateSortKey: this.parseDateSortKey(rawDate || item['Transit Pass Date'] || item['Date']),
          status: String(item['Status'] || 'COMPLETED').toUpperCase(),
          bondType: item['Bond Type'] || '',
          agingDays: parseInt(item['aging_days'] || item['Days_Pending'] || 0, 10),
          isCarriedOver: Boolean(item['is_carried_over'] || item['Carry_Over_Pending']),
          fulfilledFromCarryOver: Boolean(item['fulfilled_from_carry_over'] || item['Fulfilled_Carry_Over_Records']),
          lines: [],
          totalCases: 0.0,
          totalBottles: 0,
          totalEqCases: 0.0,
          totalMRP: 0.0,
          totalBL: 0.0,
          totalLPL: 0.0
        };
      }

      const g = groups[key];
      g.lines.push(item);
      const c = parseFloat(item['Cases']) || 0.0;
      const b = parseInt(item['Bottles'], 10) || 0;
      const bpc = AppUtils.getBottlesPerCase(item['Size'], item['Pack Size']);
      const eq = (b / bpc);
      const totEq = c + eq;
      const mrp = parseFloat(item['Total MRP']) || 0.0;
      const bl = parseFloat(item['Bulk Litres']) || 0.0;
      const lpl = parseFloat(item['LPL']) || 0.0;

      g.totalCases += c;
      g.totalBottles += b;
      g.totalEqCases += totEq;
      g.totalMRP += mrp;
      g.totalBL += bl;
      g.totalLPL += lpl;
    });

    return Object.values(groups);
  },

  getFilteredGroups(data) {
    const d = data || AppState.movementData;
    if (!d) return [];

    const allGroups = this.groupPermits(d.permits || []);
    const statusTab = AppState.indentStatusTab || 'ALL';

    let filtered = allGroups;
    if (statusTab === 'PENDING') {
      filtered = allGroups.filter(g => g.status === 'PENDING');
    } else if (statusTab === 'DISPATCHED') {
      filtered = allGroups.filter(g => g.status === 'COMPLETED');
    } else if (statusTab === 'FULFILLED') {
      filtered = allGroups.filter(g => g.fulfilledFromCarryOver);
    }

    // Fix 23: search matches retailer name, licensee, retailer code, permit, TP, indent number, vehicle
    const q = (AppState.indentSearchQuery || '').toLowerCase().trim();
    if (q) {
      filtered = filtered.filter(g =>
        (g.retailerName || '').toLowerCase().includes(q) ||
        (g.licenseeName || '').toLowerCase().includes(q) ||
        (g.retailerCode || '').toLowerCase().includes(q) ||
        (g.permitNumber || '').toLowerCase().includes(q) ||
        (g.transitPass || '').toLowerCase().includes(q) ||
        (g.indentNumber || '').toLowerCase().includes(q) ||
        (g.vehicleNumber || '').toLowerCase().includes(q)
      );
    }

    // Fix 13: Category filter and row calculation from matching lines only
    const catFilter = AppState.categoryFilter || 'ALL';
    if (catFilter !== 'ALL') {
      const catMatching = [];
      filtered.forEach(g => {
        const matchingLines = g.lines.filter(l => AppUtils.getProductCategory(l) === catFilter);
        if (matchingLines.length > 0) {
          // Compute category-filtered volume and MRP for this group
          let catCases = 0.0;
          let catBottles = 0;
          let catEqCases = 0.0;
          let catMRP = 0.0;

          matchingLines.forEach(l => {
            const c = parseFloat(l['Cases']) || 0.0;
            const b = parseInt(l['Bottles'], 10) || 0;
            const bpc = AppUtils.getBottlesPerCase(l['Size'], l['Pack Size']);
            catCases += c;
            catBottles += b;
            catEqCases += (c + (b / bpc));
            catMRP += (parseFloat(l['Total MRP']) || 0.0);
          });

          catMatching.push({
            ...g,
            filteredLines: matchingLines,
            totalCases: catCases,
            totalBottles: catBottles,
            totalEqCases: catEqCases,
            totalMRP: catMRP,
            isMixed: matchingLines.length < g.lines.length
          });
        }
      });
      filtered = catMatching;
    }

    // Fix 11: Sort by dateSortKey when sorting by challanDate
    const sortCol = AppState.indentSortCol || 'challanDate';
    const sortDir = AppState.indentSortDir || 'desc';
    const mult = sortDir === 'asc' ? 1 : -1;

    return [...filtered].sort((a, b) => {
      let valA = a[sortCol];
      let valB = b[sortCol];
      if (sortCol === 'challanDate') {
        valA = a.dateSortKey || '';
        valB = b.dateSortKey || '';
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
    const container = document.getElementById('workspace-indents-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:5rem;color:var(--text-muted);">Loading Indents...</div>`;
      return;
    }

    const catFilter = AppState.categoryFilter || 'ALL';
    let baseGroups = this.groupPermits(data.permits || []);
    if (catFilter !== 'ALL') {
      baseGroups = baseGroups.filter(g => g.lines && g.lines.some(l => AppUtils.getProductCategory(l) === catFilter));
    }
    const allGroups = baseGroups;
    const pendingGroups = allGroups.filter(g => g.status === 'PENDING');
    const dispatchedGroups = allGroups.filter(g => g.status === 'COMPLETED');
    const fulfilledGroups = allGroups.filter(g => g.fulfilledFromCarryOver);
    const statusTab = AppState.indentStatusTab || 'ALL';

    let pickList = data.pending_pick_list || [];
    if (catFilter !== 'ALL') {
      pickList = pickList.filter(item => item.category === catFilter);
    }

    const tabsHTML = `
      <div class="ledger-status-tabs">
        <button class="ledger-tab-btn ${statusTab === 'ALL' ? 'active' : ''}" data-action="tab" data-tab="ALL">
          All Indents (${allGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'PENDING' ? 'active' : ''}" data-action="tab" data-tab="PENDING" style="${pendingGroups.length > 0 ? 'border-color:var(--status-warning);color:var(--status-warning);' : ''}">
          Pending in Bond (${pendingGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'DISPATCHED' ? 'active' : ''}" data-action="tab" data-tab="DISPATCHED">
          Dispatched / TP Issued (${dispatchedGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'FULFILLED' ? 'active' : ''}" data-action="tab" data-tab="FULFILLED">
          Fulfilled Carry-Overs (${fulfilledGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'PICKLIST' ? 'active' : ''}" data-action="tab" data-tab="PICKLIST">
          Floor Pick-List
        </button>
      </div>
    `;

    if (statusTab === 'PICKLIST') {
      // Fix 2: Pick-list shared floor component
      container.innerHTML = tabsHTML + AppComponents.renderFloorPickList(pickList);
      this.attachDelegatedListeners(container);
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
            id="indents-search-input"
            class="search-input"
            placeholder="Search Retailer, Licensee, Code, Permit #, Transit Pass, Vehicle..."
            value="${AppUtils.escapeHtml(AppState.indentSearchQuery)}"
          />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span class="table-stats-badge" id="indents-stats-badge">
            Loading...
          </span>
          <button class="action-btn" id="indents-expand-all-btn" data-action="toggle-all-expansions">
            ${this.expandedPermits.size > 0 ? 'Collapse All' : 'Expand All'}
          </button>
        </div>
      </div>
      <div id="indents-results-container"></div>
    `;

    container.innerHTML = tabsHTML + toolbarHTML;
    this.attachDelegatedListeners(container);
    this.renderIndentsResults(data);
  },

  renderResultsOnly() {
    const data = AppState.movementData;
    if (!data) return;
    if (AppState.indentStatusTab === 'PICKLIST') {
      this.render();
    } else {
      this.renderIndentsResults(data);
    }
  },

  renderIndentsResults(data) {
    const resultsContainer = document.getElementById('indents-results-container');
    const statsBadge = document.getElementById('indents-stats-badge');
    const expandBtn = document.getElementById('indents-expand-all-btn');
    if (!resultsContainer) return;

    const filtered = this.getFilteredGroups(data);
    const totalEqCases = filtered.reduce((acc, g) => acc + g.totalEqCases, 0);
    const totalMRP = filtered.reduce((acc, g) => acc + g.totalMRP, 0);

    if (statsBadge) {
      statsBadge.innerText = `${filtered.length} Indents • ${AppUtils.formatNumber(totalEqCases)} cs • ${AppUtils.formatCurrencyINR(totalMRP, true)}`;
    }
    if (expandBtn) {
      expandBtn.innerText = this.expandedPermits.size > 0 ? 'Collapse All' : 'Expand All';
    }

    // Responsive Mobile Cards View (< 768px)
    const mobileCardsHTML = `
      <div class="mobile-cards-view">
        ${filtered.length === 0 ? `
          <div style="text-align:center;padding:3rem 1rem;color:var(--text-muted);">No indents match search or filter criteria</div>
        ` : filtered.map(g => {
          const isExp = this.expandedPermits.has(g.key);
          const isPending = g.status === 'PENDING';
          const passNumber = g.transitPass || g.permitNumber || 'Pending Official Pass';
          const mixedBadge = g.isMixed ? `<span class="badge-mixed" title="Indent contains items from other categories">Mixed</span>` : '';

          return `
            <div class="mobile-entity-card ${isExp ? 'is-expanded' : ''}">
              <div class="mobile-card-header" data-action="toggle-permit" data-key="${AppUtils.escapeHtml(g.key)}" style="cursor:pointer;">
                <div class="mobile-card-title-wrap">
                  <div class="mobile-card-title">${AppUtils.escapeHtml(g.retailerName || g.licenseeName)}</div>
                  ${g.retailerName && g.retailerName !== g.licenseeName ? `<div style="font-size:0.75rem;color:var(--text-muted);">${AppUtils.escapeHtml(g.licenseeName)}</div>` : ''}
                  <div class="mobile-card-meta" style="margin-top:4px;">
                    <span class="pass-mono-pill">${AppUtils.escapeHtml(passNumber)}</span>
                    ${isPending ? AppComponents.renderAgingBadge(g.agingDays) : `<span class="badge-status-dispatched">Dispatched</span>`}
                    ${mixedBadge}
                  </div>
                </div>
                <div class="mobile-card-stat">
                  <div class="mobile-stat-primary">${AppUtils.formatNumber(g.totalEqCases)} cs</div>
                  <div class="mobile-stat-secondary">${AppUtils.formatCurrencyINR(g.totalMRP, true)}</div>
                </div>
              </div>

              <div class="mobile-card-metrics-grid" style="margin-top:0.5rem;">
                <div>
                  <span class="m-metric-label">Date</span>
                  <span class="m-metric-val">${AppUtils.escapeHtml(g.challanDate || g.date || '—')}</span>
                </div>
                <div>
                  <span class="m-metric-label">Code / District</span>
                  <span class="m-metric-val">${AppUtils.escapeHtml(g.retailerCode || g.district || '—')}</span>
                </div>
                <div>
                  <span class="m-metric-label">Vehicle</span>
                  <span class="m-metric-val">${AppUtils.escapeHtml(g.vehicleNumber || '—')}</span>
                </div>
              </div>

              ${isExp ? `
                <div class="mobile-card-expanded-body">
                  ${this.renderInlineIndentSKUs(g, true)}
                </div>
              ` : ''}

              <div style="display:flex;justify-content:flex-end;gap:0.5rem;margin-top:0.75rem;padding-top:0.5rem;border-top:1px solid var(--border-hairline);">
                <button class="action-btn" style="padding:4px 10px;font-size:0.75rem;" data-action="inspect-permit" data-key="${AppUtils.escapeHtml(g.key)}">
                  Inspect Pass →
                </button>
              </div>
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
                <th class="th-sortable" data-action="sort" data-col="challanDate">
                  Challan Date ${this.renderSortIndicator('challanDate')}
                </th>
                <th class="th-sortable" data-action="sort" data-col="transitPass">
                  Transit Pass / Permit # ${this.renderSortIndicator('transitPass')}
                </th>
                <th class="th-sortable" data-action="sort" data-col="retailerName">
                  Retailer & Licensee ${this.renderSortIndicator('retailerName')}
                </th>
                <th>Retailer Code</th>
                <th>Vehicle #</th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="totalEqCases">
                  Total Cases ${this.renderSortIndicator('totalEqCases')}
                </th>
                <th class="th-sortable" style="text-align:right;" data-action="sort" data-col="totalMRP">
                  Total MRP (₹) ${this.renderSortIndicator('totalMRP')}
                </th>
                <th class="th-sortable" style="text-align:center;" data-action="sort" data-col="agingDays">
                  Status / Aging ${this.renderSortIndicator('agingDays')}
                </th>
                <th style="text-align:center;width:95px;">Action</th>
              </tr>
            </thead>
            <tbody>
              ${filtered.length === 0 ? `
                <tr><td colspan="11" style="text-align:center;padding:3.5rem;color:var(--text-muted);">No indents found matching filter</td></tr>
              ` : filtered.map((g, idx) => {
                const isExp = this.expandedPermits.has(g.key);
                const isPending = g.status === 'PENDING';
                const passNumber = g.transitPass || g.permitNumber || 'Pending Pass';
                const mixedBadge = g.isMixed ? `<span class="badge-mixed" title="Contains items from other categories">Mixed</span>` : '';

                return `
                  <tr class="${isExp ? 'row-expanded' : ''}">
                    <td>
                      <button class="row-expand-btn ${isExp ? 'expanded' : ''}" data-action="toggle-permit" data-key="${AppUtils.escapeHtml(g.key)}">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
                      </button>
                    </td>
                    <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                    <td class="num-tabular" style="font-size:0.8rem;white-space:nowrap;">
                      ${AppUtils.escapeHtml(g.challanDate || g.date || '—')}
                    </td>
                    <td>
                      <span class="pass-mono-pill" title="Click to inspect pass" data-action="inspect-permit" data-key="${AppUtils.escapeHtml(g.key)}" style="cursor:pointer;">
                        ${AppUtils.escapeHtml(passNumber)}
                      </span>
                    </td>
                    <td>
                      <div style="font-weight:600;color:var(--text-primary);">
                        <a href="#" data-action="inspect-permit" data-key="${AppUtils.escapeHtml(g.key)}" class="table-entity-link">
                          ${AppUtils.escapeHtml(g.retailerName || g.licenseeName)}
                        </a>
                      </div>
                      ${g.retailerName && g.retailerName !== g.licenseeName ? `<div style="font-size:0.75rem;color:var(--text-muted);">${AppUtils.escapeHtml(g.licenseeName)}</div>` : ''}
                    </td>
                    <td><span class="pack-pill">${AppUtils.escapeHtml(g.retailerCode || g.district || '—')}</span></td>
                    <td class="num-tabular" style="font-size:0.8rem;color:var(--text-secondary);">${AppUtils.escapeHtml(g.vehicleNumber || '—')}</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;">
                      ${AppUtils.formatNumber(g.totalEqCases)}
                    </td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">
                      ${AppUtils.formatCurrencyINR(g.totalMRP)}
                    </td>
                    <td style="text-align:center;">
                      <div style="display:flex;align-items:center;justify-content:center;gap:4px;">
                        ${isPending ? AppComponents.renderAgingBadge(g.agingDays) : `<span class="badge-status-dispatched">Dispatched</span>`}
                        ${mixedBadge}
                      </div>
                    </td>
                    <td style="text-align:center;">
                      <button class="action-btn" style="padding:3px 8px;font-size:0.75rem;" data-action="inspect-permit" data-key="${AppUtils.escapeHtml(g.key)}">
                        Inspect →
                      </button>
                    </td>
                  </tr>
                  ${isExp ? this.renderInlineIndentSKUs(g, false, 11) : ''}
                `;
              }).join('')}
            </tbody>
            <tfoot>
              <tr style="background:var(--bg-elevated);font-weight:700;border-top:1px solid var(--border-strong);">
                <td colspan="7" style="text-align:right;text-transform:uppercase;font-size:0.75rem;color:var(--text-muted);">
                  Totals (${filtered.length} Indents):
                </td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(totalEqCases)}</td>
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

  renderInlineIndentSKUs(g, isMobile = false, colspan = 11) {
    const linesToDisplay = g.filteredLines || g.lines || [];
    const innerHTML = `
      <div class="nested-expansion-container" style="padding:0.75rem 1rem;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem;">
          <div class="nested-section-title">Itemised Products (${linesToDisplay.length} SKUs • ${AppUtils.formatNumber(g.totalEqCases)} cs)</div>
          <button class="action-btn" style="padding:2px 8px;font-size:0.75rem;" data-action="inspect-permit" data-key="${AppUtils.escapeHtml(g.key)}">
            Open Full Pass Slide-Over →
          </button>
        </div>
        <table class="mini-data-table">
          <thead>
            <tr>
              <th>Product Name</th>
              <th>Category</th>
              <th>Pack</th>
              <th style="text-align:right;">Cases</th>
              <th style="text-align:right;">Loose Btls</th>
              <th style="text-align:right;">MRP (₹)</th>
            </tr>
          </thead>
          <tbody>
            ${linesToDisplay.map(l => `
              <tr>
                <td style="font-weight:600;">${AppUtils.escapeHtml(l['Product Name'] || l.ProductName)}</td>
                <td>${AppComponents.renderCategoryBadge(AppUtils.getProductCategory(l))}</td>
                <td><span class="pack-pill">${AppUtils.escapeHtml(l['Pack Size'] || l.Size)}</span></td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(l.Cases || 0, 0)}</td>
                <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatInteger(l.Bottles || 0)}</td>
                <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(l['Total MRP'] || l.TotalMRP)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
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

  togglePermitExpansion(key) {
    if (this.expandedPermits.has(key)) {
      this.expandedPermits.delete(key);
    } else {
      this.expandedPermits.add(key);
    }
    this.renderResultsOnly();
  },

  toggleAllExpansions() {
    if (this.expandedPermits.size > 0) {
      this.expandedPermits.clear();
      this.renderResultsOnly();
      return;
    }
    const visible = this.getFilteredGroups();
    const toExpand = visible.slice(0, 50);
    toExpand.forEach(g => this.expandedPermits.add(g.key));
    if (visible.length > 50) {
      AppUtils.showToast(`Expanded first 50 of ${visible.length} indents`, 'info');
    }
    this.renderResultsOnly();
  },

  attachDelegatedListeners(container) {
    if (container._delegatedIndentListener) return;
    container._delegatedIndentListener = true;

    container.addEventListener('click', (e) => {
      const target = e.target.closest('[data-action]');
      if (!target) return;
      const action = target.dataset.action;

      if (action === 'tab') {
        AppState.indentStatusTab = target.dataset.tab;
        WorkspaceIndents.render();
      } else if (action === 'toggle-permit') {
        WorkspaceIndents.togglePermitExpansion(target.dataset.key);
      } else if (action === 'inspect-permit') {
        e.preventDefault();
        window.inspectPermit(target.dataset.key);
      } else if (action === 'sort') {
        WorkspaceIndents.setSort(target.dataset.col);
      } else if (action === 'toggle-all-expansions') {
        WorkspaceIndents.toggleAllExpansions();
      }
    });

    container.addEventListener('input', (e) => {
      if (e.target.id === 'indents-search-input') {
        AppState.indentSearchQuery = e.target.value;
        clearTimeout(WorkspaceIndents._debounceTimer);
        WorkspaceIndents._debounceTimer = setTimeout(() => {
          WorkspaceIndents.renderIndentsResults();
        }, 150);
      }
    });
  }
};

window.WorkspaceIndents = WorkspaceIndents;
