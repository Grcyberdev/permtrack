/**
 * PermTrack Enterprise — Workspace 3: Bond Indents & Live Dispatch Ledger
 * Minimal, Calm, Executive Precision with Responsive Mobile Cards
 */
const WorkspaceIndents = {
  expandedPermits: new Set(),

  setSort(col) {
    if (AppState.indentSortCol === col) {
      AppState.indentSortDir = AppState.indentSortDir === 'desc' ? 'asc' : 'desc';
    } else {
      AppState.indentSortCol = col;
      AppState.indentSortDir = 'desc';
    }
    this.render();
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
          challanDate: item['Challan Date'] || item['Date'] || '',
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

  render() {
    const container = document.getElementById('workspace-indents-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:5rem;color:var(--text-muted);">Loading Indents...</div>`;
      return;
    }

    const allGroups = this.groupPermits(data.permits || []);
    const pendingGroups = allGroups.filter(g => g.status === 'PENDING');
    const dispatchedGroups = allGroups.filter(g => g.status === 'COMPLETED');
    const fulfilledGroups = allGroups.filter(g => g.fulfilledFromCarryOver);

    // Apply active status tab
    const statusTab = AppState.indentStatusTab || 'ALL';
    
    // Check if Floor Pick-List sub-view is selected
    if (statusTab === 'PICKLIST') {
      this.renderFloorPickListTab(container, allGroups, pendingGroups, dispatchedGroups, fulfilledGroups);
      return;
    }

    let filtered = allGroups;
    if (statusTab === 'PENDING') filtered = pendingGroups;
    else if (statusTab === 'DISPATCHED') filtered = dispatchedGroups;
    else if (statusTab === 'FULFILLED') filtered = fulfilledGroups;

    // Apply Search
    const q = (AppState.indentSearchQuery || '').toLowerCase().trim();
    if (q) {
      filtered = filtered.filter(g =>
        g.licenseeName.toLowerCase().includes(q) ||
        g.permitNumber.toLowerCase().includes(q) ||
        g.transitPass.toLowerCase().includes(q) ||
        g.vehicleNumber.toLowerCase().includes(q) ||
        g.indentNumber.toLowerCase().includes(q)
      );
    }

    // Apply Category Filter
    if (AppState.categoryFilter !== 'ALL') {
      const cat = AppState.categoryFilter;
      filtered = filtered.filter(g =>
        g.lines.some(l => AppUtils.getProductCategory(l) === cat)
      );
    }

    // Apply Column Sorting
    const sortCol = AppState.indentSortCol || 'challanDate';
    const sortDir = AppState.indentSortDir || 'desc';
    const mult = sortDir === 'asc' ? 1 : -1;

    filtered = [...filtered].sort((a, b) => {
      let valA = a[sortCol];
      let valB = b[sortCol];
      if (typeof valA === 'string') {
        return (valA || '').localeCompare(valB || '') * mult;
      }
      valA = Number(valA || 0);
      valB = Number(valB || 0);
      return (valA - valB) * mult;
    });

    const totalEqCases = filtered.reduce((acc, g) => acc + g.totalEqCases, 0);
    const totalMRP = filtered.reduce((acc, g) => acc + g.totalMRP, 0);

    const tabsHTML = `
      <div class="ledger-status-tabs">
        <button class="ledger-tab-btn ${statusTab === 'ALL' ? 'active' : ''}" onclick="AppState.indentStatusTab='ALL';WorkspaceIndents.render();">
          All Indents (${allGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'PENDING' ? 'active' : ''}" onclick="AppState.indentStatusTab='PENDING';WorkspaceIndents.render();" style="${pendingGroups.length > 0 ? 'border-color:var(--status-warning);color:var(--status-warning);' : ''}">
          Pending in Bond (${pendingGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'DISPATCHED' ? 'active' : ''}" onclick="AppState.indentStatusTab='DISPATCHED';WorkspaceIndents.render();">
          Dispatched / TP Issued (${dispatchedGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'FULFILLED' ? 'active' : ''}" onclick="AppState.indentStatusTab='FULFILLED';WorkspaceIndents.render();">
          Fulfilled Carry-Overs (${fulfilledGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'PICKLIST' ? 'active' : ''}" onclick="AppState.indentStatusTab='PICKLIST';WorkspaceIndents.render();">
          Floor Pick-List
        </button>
      </div>

      <div class="table-toolbar">
        <div class="search-box-wrap">
          <svg class="search-icon-svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input type="text" class="search-input" placeholder="Search Permit #, Transit Pass, Licensee, Vehicle..." value="${AppUtils.escapeHtml(AppState.indentSearchQuery)}" oninput="AppState.indentSearchQuery=this.value;WorkspaceIndents.render();" />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span class="table-stats-badge">
            ${filtered.length} Indents • ${AppUtils.formatNumber(totalEqCases)} cs • ${AppUtils.formatCurrencyINR(totalMRP, true)}
          </span>
          <button class="action-btn" onclick="WorkspaceIndents.toggleAllExpansions()">
            ${this.expandedPermits.size > 0 ? 'Collapse All' : 'Expand All'}
          </button>
        </div>
      </div>
    `;

    // Mobile Cards View (< 768px)
    const mobileCardsHTML = `
      <div class="mobile-cards-view">
        ${filtered.length === 0 ? `
          <div style="text-align:center;padding:3rem 1rem;color:var(--text-muted);">No indents match criteria</div>
        ` : filtered.map(g => {
          const isExp = this.expandedPermits.has(g.key);
          const isPending = g.status === 'PENDING';
          const passNumber = g.transitPass || g.permitNumber || 'Pending Official Pass';
          return `
            <div class="mobile-entity-card ${isExp ? 'is-expanded' : ''}">
              <div class="mobile-card-header" onclick="WorkspaceIndents.togglePermitExpansion('${AppUtils.escapeHtml(g.key)}')">
                <div class="mobile-card-title-wrap">
                  <div class="mobile-card-title">${AppUtils.escapeHtml(g.licenseeName)}</div>
                  <div class="mobile-card-meta">
                    <span class="pass-mono-pill">${AppUtils.escapeHtml(passNumber)}</span>
                    ${isPending ? AppComponents.renderAgingBadge(g.agingDays) : `<span class="badge-status-dispatched">Dispatched</span>`}
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
                  <span class="m-metric-label">Vehicle</span>
                  <span class="m-metric-val">${AppUtils.escapeHtml(g.vehicleNumber || '—')}</span>
                </div>
                <div>
                  <span class="m-metric-label">SKUs</span>
                  <span class="m-metric-val">${g.lines.length} items</span>
                </div>
              </div>

              ${isExp ? `
                <div class="mobile-card-expanded-body">
                  ${this.renderInlineIndentSKUs(g, true)}
                </div>
              ` : ''}

              <div style="display:flex;justify-content:flex-end;gap:0.5rem;margin-top:0.75rem;padding-top:0.5rem;border-top:1px solid var(--border-hairline);">
                <button class="action-btn" style="padding:4px 10px;font-size:0.75rem;" onclick="event.stopPropagation();window.inspectPermit('${AppUtils.escapeHtml(g.key)}')">
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
                <th class="th-sortable" onclick="WorkspaceIndents.setSort('challanDate')">
                  Challan Date ${this.renderSortIndicator('challanDate')}
                </th>
                <th class="th-sortable" onclick="WorkspaceIndents.setSort('transitPass')">
                  Transit Pass / Permit # ${this.renderSortIndicator('transitPass')}
                </th>
                <th class="th-sortable" onclick="WorkspaceIndents.setSort('licenseeName')">
                  Licensee / Retailer ${this.renderSortIndicator('licenseeName')}
                </th>
                <th>Destination</th>
                <th>Vehicle #</th>
                <th class="th-sortable" style="text-align:right;" onclick="WorkspaceIndents.setSort('totalEqCases')">
                  Total Cases ${this.renderSortIndicator('totalEqCases')}
                </th>
                <th class="th-sortable" style="text-align:right;" onclick="WorkspaceIndents.setSort('totalMRP')">
                  Total MRP (₹) ${this.renderSortIndicator('totalMRP')}
                </th>
                <th class="th-sortable" style="text-align:center;" onclick="WorkspaceIndents.setSort('agingDays')">
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

                return `
                  <tr class="${isExp ? 'row-expanded' : ''}" style="cursor:pointer;" onclick="if(!event.target.closest('button') && !event.target.closest('a')) WorkspaceIndents.togglePermitExpansion('${AppUtils.escapeHtml(g.key)}')">
                    <td>
                      <button class="row-expand-btn ${isExp ? 'expanded' : ''}" onclick="event.stopPropagation();WorkspaceIndents.togglePermitExpansion('${AppUtils.escapeHtml(g.key)}')">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
                      </button>
                    </td>
                    <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                    <td class="num-tabular" style="font-size:0.8rem;white-space:nowrap;">
                      ${AppUtils.escapeHtml(g.challanDate || g.date || '—')}
                    </td>
                    <td>
                      <span class="pass-mono-pill" title="Click to inspect pass" onclick="event.stopPropagation();window.inspectPermit('${AppUtils.escapeHtml(g.key)}')">
                        ${AppUtils.escapeHtml(passNumber)}
                      </span>
                    </td>
                    <td style="font-weight:600;">
                      <a href="#" onclick="event.stopPropagation();window.inspectPermit('${AppUtils.escapeHtml(g.key)}');return false;" class="table-entity-link">
                        ${AppUtils.escapeHtml(g.licenseeName)}
                      </a>
                    </td>
                    <td><span class="pack-pill">${AppUtils.escapeHtml(g.district || 'Assam')}</span></td>
                    <td class="num-tabular" style="font-size:0.8rem;color:var(--text-secondary);">${AppUtils.escapeHtml(g.vehicleNumber || '—')}</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;">
                      ${AppUtils.formatNumber(g.totalEqCases)}
                    </td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">
                      ${AppUtils.formatCurrencyINR(g.totalMRP)}
                    </td>
                    <td style="text-align:center;">
                      ${isPending ? AppComponents.renderAgingBadge(g.agingDays) : `<span class="badge-status-dispatched">Dispatched</span>`}
                    </td>
                    <td style="text-align:center;">
                      <button class="action-btn" style="padding:3px 8px;font-size:0.75rem;" onclick="event.stopPropagation();window.inspectPermit('${AppUtils.escapeHtml(g.key)}')">
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

    container.innerHTML = tabsHTML + mobileCardsHTML + tableHTML;
  },

  renderInlineIndentSKUs(g, isMobile = false, colspan = 11) {
    const innerHTML = `
      <div class="nested-expansion-container" style="padding:0.75rem 1rem;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem;">
          <div class="nested-section-title">Itemised Products (${g.lines.length} SKUs • ${AppUtils.formatNumber(g.totalEqCases)} cs)</div>
          <button class="action-btn" style="padding:2px 8px;font-size:0.75rem;" onclick="event.stopPropagation();window.inspectPermit('${AppUtils.escapeHtml(g.key)}')">
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
              <th style="text-align:right;">Total MRP</th>
            </tr>
          </thead>
          <tbody>
            ${g.lines.map(l => `
              <tr>
                <td style="font-weight:600;">${AppUtils.escapeHtml(l['Product Name'] || l.ProductName)}</td>
                <td>${AppComponents.renderCategoryBadge(AppUtils.getProductCategory(l))}</td>
                <td><span class="pack-pill">${AppUtils.escapeHtml(l['Pack Size'] || l.Size)}</span></td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(l.Cases || 0, 0)}</td>
                <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatInteger(l.Bottles || 0)}</td>
                <td class="cell-num" style="text-align:right;color:var(--accent-amber);font-weight:600;">${AppUtils.formatCurrencyINR(l['Total MRP'] || l.TotalMRP)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
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

  renderFloorPickListTab(container, allGroups, pendingGroups, dispatchedGroups, fulfilledGroups) {
    const data = AppState.movementData;
    const list = data.pending_pick_list || [];
    const totalCases = list.reduce((acc, item) => acc + (item.cases_needed || 0), 0);

    const tabsHTML = `
      <div class="ledger-status-tabs">
        <button class="ledger-tab-btn" onclick="AppState.indentStatusTab='ALL';WorkspaceIndents.render();">
          All Indents (${allGroups.length})
        </button>
        <button class="ledger-tab-btn" onclick="AppState.indentStatusTab='PENDING';WorkspaceIndents.render();" style="${pendingGroups.length > 0 ? 'border-color:var(--status-warning);color:var(--status-warning);' : ''}">
          Pending in Bond (${pendingGroups.length})
        </button>
        <button class="ledger-tab-btn" onclick="AppState.indentStatusTab='DISPATCHED';WorkspaceIndents.render();">
          Dispatched / TP Issued (${dispatchedGroups.length})
        </button>
        <button class="ledger-tab-btn" onclick="AppState.indentStatusTab='FULFILLED';WorkspaceIndents.render();">
          Fulfilled Carry-Overs (${fulfilledGroups.length})
        </button>
        <button class="ledger-tab-btn active" onclick="AppState.indentStatusTab='PICKLIST';WorkspaceIndents.render();">
          Floor Pick-List
        </button>
      </div>

      <div class="surface-panel" style="margin-top:1rem;">
        <div class="panel-header">
          <div>
            <div class="panel-title">Pending Indents Floor Loading Pick-List</div>
            <div class="panel-subtitle">Total SKUs and quantities needed on the floor to load all ${pendingGroups.length} waiting indents</div>
          </div>
          <div style="font-family:var(--font-mono);font-weight:700;color:var(--status-warning);">
            ${AppUtils.formatNumber(totalCases)} cs Total
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
                <th style="text-align:right;">Waiting Indents</th>
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
                  <td class="cell-num" style="text-align:right;color:var(--status-warning);font-weight:700;">
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

    container.innerHTML = tabsHTML;
  },

  togglePermitExpansion(key) {
    if (this.expandedPermits.has(key)) {
      this.expandedPermits.delete(key);
    } else {
      this.expandedPermits.add(key);
    }
    this.render();
  },

  toggleAllExpansions() {
    const data = AppState.movementData;
    if (!data || !data.permits) return;
    const allGroups = this.groupPermits(data.permits);
    if (this.expandedPermits.size > 0) {
      this.expandedPermits.clear();
    } else {
      allGroups.forEach(g => this.expandedPermits.add(g.key));
    }
    this.render();
  }
};

window.WorkspaceIndents = WorkspaceIndents;
