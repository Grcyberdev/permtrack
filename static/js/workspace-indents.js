/**
 * PermTrack Enterprise — Workspace 3: Bond Indents & Live Dispatch Ledger
 */
const WorkspaceIndents = {
  expandedPermits: new Set(),

  groupPermits(rawRecords) {
    const groups = {};
    if (!rawRecords || !Array.isArray(rawRecords)) return [];

    rawRecords.forEach(item => {
      const pNum = String(item['Permit Number'] || '').trim();
      const tp = String(item['Transit Pass'] || '').trim();
      const ind = String(item['Indent Number'] || '').trim();
      const lic = String(item['Licensee Name'] || item['Retailer Name'] || '').trim();
      const dt = String(item['Challan Date'] || item['Date'] || '').trim();

      // Permit key
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
      const c = float(item['Cases'] || 0);
      const b = int(item['Bottles'] || 0);
      const bpc = AppUtils.getBottlesPerCase(item['Size'], item['Pack Size']);
      const eq = (b / bpc);
      const totEq = c + eq;
      const mrp = float(item['Total MRP'] || 0);
      const bl = float(item['Bulk Litres'] || 0);
      const lpl = float(item['LPL'] || 0);

      g.totalCases += c;
      g.totalBottles += b;
      g.totalEqCases += totEq;
      g.totalMRP += mrp;
      g.totalBL += bl;
      g.totalLPL += lpl;
    });

    function float(v) { return parseFloat(v) || 0.0; }
    function int(v) { return parseInt(v, 10) || 0; }

    return Object.values(groups);
  },

  render() {
    const container = document.getElementById('workspace-indents-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:4rem;color:var(--text-muted);">Loading Bond Indents...</div>`;
      return;
    }

    const allGroups = this.groupPermits(data.permits || []);
    const pendingGroups = allGroups.filter(g => g.status === 'PENDING');
    const dispatchedGroups = allGroups.filter(g => g.status === 'COMPLETED');
    const fulfilledGroups = allGroups.filter(g => g.fulfilledFromCarryOver);

    // Apply active status tab
    const statusTab = AppState.indentStatusTab || 'ALL';
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

    const tabsHTML = `
      <div class="ledger-status-tabs">
        <button class="ledger-tab-btn ${statusTab === 'ALL' ? 'active' : ''}" onclick="AppState.indentStatusTab='ALL';WorkspaceIndents.render();">
          All Indents (${allGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'PENDING' ? 'active' : ''}" onclick="AppState.indentStatusTab='PENDING';WorkspaceIndents.render();" style="${pendingGroups.length > 0 ? 'border-color:var(--status-warning);' : ''}">
          ⏳ Pending in Bond (${pendingGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'DISPATCHED' ? 'active' : ''}" onclick="AppState.indentStatusTab='DISPATCHED';WorkspaceIndents.render();">
          ✅ Dispatched / TP Issued (${dispatchedGroups.length})
        </button>
        <button class="ledger-tab-btn ${statusTab === 'FULFILLED' ? 'active' : ''}" onclick="AppState.indentStatusTab='FULFILLED';WorkspaceIndents.render();">
          🔄 Fulfilled Carry-Overs (${fulfilledGroups.length})
        </button>
      </div>

      <div class="table-toolbar">
        <div class="search-box-wrap">
          <svg class="search-icon-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input type="text" class="search-input" placeholder="Search Permit #, Transit Pass, Licensee, Vehicle..." value="${AppUtils.escapeHtml(AppState.indentSearchQuery)}" oninput="AppState.indentSearchQuery=this.value;WorkspaceIndents.render();" />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span class="table-stats-badge">
            ${filtered.length} Indents • ${AppUtils.formatNumber(filtered.reduce((a, g) => a + g.totalEqCases, 0))} Total Cases
          </span>
          <button class="action-btn" onclick="WorkspaceIndents.toggleAllExpansions()">
            ${this.expandedPermits.size > 0 ? 'Collapse All' : 'Expand All SKUs'}
          </button>
        </div>
      </div>
    `;

    // Render Desktop Table and Mobile Feed
    const desktopTableHTML = `
      <div class="data-table-container">
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:36px;"></th>
                <th>Status</th>
                <th>Permit & Pass #</th>
                <th>Challan Date</th>
                <th>Licensee / Party Name</th>
                <th>Vehicle #</th>
                <th>SKUs</th>
                <th style="text-align:right;">Physical Cases</th>
                <th style="text-align:right;">Loose Btls</th>
                <th style="text-align:right;">Total Eq Cases</th>
                <th style="text-align:right;">Total MRP (₹)</th>
              </tr>
            </thead>
            <tbody>
              ${filtered.length === 0 ? `
                <tr><td colspan="11" style="text-align:center;padding:3rem;color:var(--text-muted);">No indents match this view</td></tr>
              ` : filtered.map(g => {
                const isExp = this.expandedPermits.has(g.key);
                const isPending = g.status === 'PENDING';

                return `
                  <tr class="${isExp ? 'row-expanded' : ''}">
                    <td>
                      <button class="row-expand-btn ${isExp ? 'expanded' : ''}" onclick="WorkspaceIndents.togglePermitExpansion('${AppUtils.escapeHtml(g.key)}')">
                        ▶
                      </button>
                    </td>
                    <td>
                      ${isPending
                        ? AppComponents.renderAgingBadge(g.agingDays)
                        : `<span class="aging-badge" style="background:var(--status-success-bg);color:var(--status-success);">✅ Dispatched</span>`}
                    </td>
                    <td>
                      <div style="display:flex;flex-direction:column;">
                        <a href="#" class="permit-link" onclick="window.inspectPermit('${AppUtils.escapeHtml(g.key)}');return false;">
                          ${AppUtils.escapeHtml(g.permitNumber || g.indentNumber || 'Open Details')}
                        </a>
                        ${g.transitPass ? `
                          <span style="font-family:var(--font-mono);font-size:0.725rem;color:var(--text-muted);">${AppUtils.escapeHtml(g.transitPass)}</span>
                        ` : ''}
                      </div>
                    </td>
                    <td class="num-tabular" style="font-size:0.8rem;color:var(--text-secondary);">${AppUtils.escapeHtml(g.challanDate)}</td>
                    <td>
                      <div style="font-weight:600;">${AppUtils.escapeHtml(g.licenseeName)}</div>
                      <div style="font-size:0.725rem;color:var(--text-muted);">${AppUtils.escapeHtml(g.district || 'ASSAM')}</div>
                    </td>
                    <td>
                      <span class="pack-pill" style="font-weight:700;">${AppUtils.escapeHtml(g.vehicleNumber || '—')}</span>
                    </td>
                    <td class="num-tabular">${g.lines.length} items</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;">${AppUtils.formatNumber(g.totalCases, 0)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatInteger(g.totalBottles)}</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--text-primary);font-size:0.95rem;">
                      ${AppUtils.formatNumber(g.totalEqCases)}
                    </td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">
                      ${AppUtils.formatCurrencyINR(g.totalMRP)}
                    </td>
                  </tr>
                  ${isExp ? this.renderInlineSKUTable(g) : ''}
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;

    container.innerHTML = tabsHTML + desktopTableHTML;
  },

  renderInlineSKUTable(g) {
    return `
      <tr>
        <td colspan="11" style="padding:0;">
          <div class="nested-expansion-container">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem;">
              <div class="nested-section-title">
                📦 Itemised SKUs for Indent ${AppUtils.escapeHtml(g.permitNumber || g.indentNumber)} (${g.lines.length} items)
              </div>
              <div style="display:flex;gap:0.5rem;">
                <button class="action-btn" onclick="AppUtils.copyToClipboard('${AppUtils.escapeHtml(g.permitNumber)}', 'Copied Permit #')">
                  Copy Permit #
                </button>
                <button class="action-btn" onclick="window.inspectPermit('${AppUtils.escapeHtml(g.key)}')">
                  Full Form-34 Modal →
                </button>
              </div>
            </div>
            <table class="mini-data-table">
              <thead>
                <tr>
                  <th>Brand Name</th>
                  <th>Category</th>
                  <th>Pack Size</th>
                  <th style="text-align:right;">Cases</th>
                  <th style="text-align:right;">Loose Btls</th>
                  <th style="text-align:right;">Total Eq Cases</th>
                  <th style="text-align:right;">Bulk Litres</th>
                  <th style="text-align:right;">Total MRP (₹)</th>
                </tr>
              </thead>
              <tbody>
                ${g.lines.map(l => {
                  const c = parseFloat(l.Cases) || 0;
                  const b = parseInt(l.Bottles, 10) || 0;
                  const bpc = AppUtils.getBottlesPerCase(l.Size, l.PackSize || l['Pack Size']);
                  const totEq = c + (b / bpc);
                  const isEstimated = Boolean(l.MRP_Estimated);

                  return `
                    <tr>
                      <td style="font-weight:600;">${AppUtils.escapeHtml(l['Product Name'] || l.ProductName)}</td>
                      <td>${AppComponents.renderCategoryBadge(AppUtils.getProductCategory(l))}</td>
                      <td><span class="pack-pill">${AppUtils.escapeHtml(l['Pack Size'] || l.Size)}</span></td>
                      <td class="cell-num" style="text-align:right;font-weight:600;">${AppUtils.formatNumber(c, 0)}</td>
                      <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatInteger(b)}</td>
                      <td class="cell-num" style="text-align:right;font-weight:700;">${AppUtils.formatNumber(totEq)} cs</td>
                      <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatNumber(l['Bulk Litres'] || l.BulkLitres || 0, 1)} L</td>
                      <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">
                        ${AppUtils.formatCurrencyINR(l['Total MRP'] || l.TotalMRP)}
                        ${isEstimated ? `<span style="font-size:0.65rem;color:var(--status-warning);" title="Estimated from historical SKU rate"> (Est)</span>` : ''}
                      </td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
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
