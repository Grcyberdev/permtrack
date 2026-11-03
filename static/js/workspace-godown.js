/**
 * PermTrack Enterprise — Workspace 5: Godown Reconciliation
 * 100% Focused on Physical vs. Portal Case Audit
 * Minimal, Calm, Executive Precision with Responsive Mobile Cards
 */
const WorkspaceGodown = {
  render() {
    const container = document.getElementById('workspace-godown-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:5rem;color:var(--text-muted);">Loading Godown Audit...</div>`;
      return;
    }

    // Fix 31: When in Day mode, notify user that month is shown
    const dayModeNotice = AppState._godownMonthSwitchedFromDay ? `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:0.6rem 1rem;background:rgba(229,169,60,0.1);border:1px solid rgba(229,169,60,0.25);border-radius:var(--radius-sm);margin-bottom:1rem;font-size:0.8rem;color:var(--accent-amber);">
        <span>Showing full month of <strong>${AppUtils.formatDateKeyToDisplay(AppState._godownMonthSwitchedFromDay)}</strong> for audit reconciliation</span>
        <button onclick="delete AppState._godownMonthSwitchedFromDay;WorkspaceGodown.render();" style="background:none;border:none;color:currentColor;cursor:pointer;font-weight:700;">✕</button>
      </div>
    ` : '';

    const series = data.daily_series || [];
    const totalPortalCases = series.reduce((acc, d) => acc + (d.cases || 0), 0);
    const hasAnyPhysical = series.some(d => d.godown_cases !== null && d.godown_cases !== undefined);
    const totalPhysicalCases = series.reduce((acc, d) => acc + (d.godown_cases !== null && d.godown_cases !== undefined ? Number(d.godown_cases) : 0), 0);
    const netVariance = hasAnyPhysical ? (totalPhysicalCases - totalPortalCases) : 0;

    // Fix 16: Audit Progress = days with physical entry / operating days; matched as separate sub-number
    const operatingDays = series.filter(d => !d.is_closed).length;
    const daysWithEntry = series.filter(d => d.godown_cases !== null && d.godown_cases !== undefined && !d.is_closed).length;
    const matchedDays = series.filter(d => d.difference !== null && Math.abs(d.difference) < 0.01 && !d.is_closed).length;

    // 1. Top Summary Cards (4 Cards)
    const summaryCardsHTML = `
      ${dayModeNotice}
      <div class="executive-kpi-grid" id="godown-kpi-grid" style="margin-bottom:1.25rem;">
        <div class="kpi-surface-card">
          <div class="kpi-header">
            <span class="kpi-title">Portal Dispatched</span>
            <span class="kpi-counter">Excise Stamped</span>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${AppUtils.formatNumber(totalPortalCases)}</span>
            <span class="kpi-unit">cs</span>
          </div>
          <div class="kpi-subtitle">
            <span>Official Assam Excise volume</span>
          </div>
        </div>

        <div class="kpi-surface-card">
          <div class="kpi-header">
            <span class="kpi-title">Physical Godown</span>
            <span class="kpi-counter">Warehouse Ledger</span>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value" id="kpi-godown-physical-val">${hasAnyPhysical ? AppUtils.formatNumber(totalPhysicalCases) : '—'}</span>
            <span class="kpi-unit">cs</span>
          </div>
          <div class="kpi-subtitle">
            <span>Physical count out of gate</span>
          </div>
        </div>

        <div class="kpi-surface-card">
          <div class="kpi-header">
            <span class="kpi-title">Net Variance</span>
            <span class="kpi-counter">Physical - Portal</span>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value" id="kpi-godown-variance-val" style="${hasAnyPhysical ? (Math.abs(netVariance) < 0.01 ? 'color:var(--status-success);' : (netVariance > 0 ? 'color:var(--accent-amber);' : 'color:var(--status-danger);')) : ''}">
              ${hasAnyPhysical ? (netVariance > 0 ? '+' : '') + AppUtils.formatNumber(netVariance) : '—'}
            </span>
            <span class="kpi-unit">cs</span>
          </div>
          <div class="kpi-subtitle" id="kpi-godown-variance-sub">
            ${hasAnyPhysical ? (
              Math.abs(netVariance) < 0.01 ? '<span style="color:var(--status-success);">100% Balanced</span>' :
              (netVariance > 0 ? `<span style="color:var(--accent-amber);">Surplus (${AppUtils.formatNumber(netVariance)} cs)</span>` :
              `<span style="color:var(--status-danger);">Deficit (${AppUtils.formatNumber(netVariance)} cs)</span>`)
            ) : '<span style="color:var(--text-muted);">No physical entries</span>'}
          </div>
        </div>

        <div class="kpi-surface-card">
          <div class="kpi-header">
            <span class="kpi-title">Audit Progress</span>
            <span class="kpi-counter">${operatingDays} Operating Days</span>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value" id="kpi-godown-progress-val">${daysWithEntry} / ${operatingDays}</span>
            <span class="kpi-unit">days</span>
          </div>
          <div class="kpi-subtitle" id="kpi-godown-progress-sub">
            <span>${matchedDays} matched (|var| &lt; 0.01)</span>
          </div>
        </div>
      </div>
    `;

    // 2. Toolbar & Action Row
    const toolbarHTML = `
      <div class="table-toolbar">
        <div>
          <div class="card-title" style="font-size:0.95rem;font-weight:700;">Physical vs Portal Case Reconciliation</div>
          <div class="card-subtitle" style="font-size:0.75rem;color:var(--text-muted);">Enter daily physical gate count. Press Enter to save and advance to next row.</div>
        </div>
        <div style="display:flex;align-items:center;gap:0.5rem;">
          <button class="action-btn" onclick="WorkspaceGodown.matchAllPortal()">
            Match All to Portal
          </button>
        </div>
      </div>
    `;

    // Helper for rendering variance badge
    const renderVarianceBadge = (diff) => {
      if (diff === null || diff === undefined) {
        return `<span style="color:var(--text-muted);">—</span>`;
      }
      if (Math.abs(diff) < 0.01) {
        return `<span class="variance-badge variance-zero">Balanced</span>`;
      }
      if (diff > 0) {
        return `<span class="variance-badge variance-surplus">+${AppUtils.formatNumber(diff)} cs</span>`;
      }
      return `<span class="variance-badge variance-deficit">${AppUtils.formatNumber(diff)} cs</span>`;
    };

    // 3. Mobile Cards View (< 768px)
    const mobileCardsHTML = `
      <div class="mobile-cards-view">
        ${series.length === 0 ? `
          <div style="text-align:center;padding:3rem 1rem;color:var(--text-muted);">No calendar days in this horizon</div>
        ` : series.map((d, idx) => {
          const varBadge = renderVarianceBadge(d.difference);
          const initVal = (d.godown_cases !== null && d.godown_cases !== undefined) ? String(d.godown_cases) : '';

          return `
            <div class="mobile-entity-card">
              <div class="mobile-card-header">
                <div>
                  <div class="mobile-card-title">${AppUtils.escapeHtml(d.date_str)}</div>
                  <div class="mobile-card-meta">
                    <span style="color:var(--text-secondary);">${AppUtils.escapeHtml(d.day)}</span>
                    <span class="pack-pill">${d.is_closed ? 'Closed' : 'Operating'}</span>
                  </div>
                </div>
                <div class="mobile-card-stat">
                  <div class="mobile-stat-primary">${AppUtils.formatNumber(d.cases)} cs</div>
                  <div class="mobile-stat-secondary">Portal Total</div>
                </div>
              </div>

              <!-- Category Volumes -->
              <div class="mobile-card-metrics-grid" style="margin:0.5rem 0;">
                <div>
                  <span class="m-metric-label">Beer</span>
                  <span class="m-metric-val" style="color:var(--brand-beer);">${AppUtils.formatNumber(d.beer_cases, 0)} cs</span>
                </div>
                <div>
                  <span class="m-metric-label">IMFL</span>
                  <span class="m-metric-val" style="color:var(--brand-imfl);">${AppUtils.formatNumber(d.imfl_cases, 0)} cs</span>
                </div>
                <div>
                  <span class="m-metric-label">CS</span>
                  <span class="m-metric-val" style="color:var(--brand-cs);">${AppUtils.formatNumber(d.cs_cases, 0)} cs</span>
                </div>
              </div>

              <!-- Physical Godown Input & Match Row -->
              <div style="display:flex;align-items:center;justify-content:space-between;gap:0.75rem;padding-top:0.6rem;border-top:1px solid var(--border-hairline);">
                <div style="display:flex;align-items:center;gap:0.5rem;flex:1;">
                  <span style="font-size:0.75rem;color:var(--text-muted);text-transform:uppercase;">Physical:</span>
                  <input
                    type="number"
                    step="0.01"
                    id="godown-mobile-input-${d.date_key}"
                    data-date-key="${d.date_key}"
                    data-last-saved="${initVal}"
                    class="godown-input-cell"
                    style="max-width:110px;"
                    value="${initVal}"
                    placeholder="0.00"
                    onkeydown="WorkspaceGodown.handleInputKeydown(event, '${d.date_key}', ${idx}, true)"
                    onblur="WorkspaceGodown.saveInput('${d.date_key}', this, true)"
                  />
                  <button class="action-btn" style="padding:4px 8px;font-size:0.75rem;" onclick="WorkspaceGodown.matchSingleDay('${d.date_key}', ${d.cases})">
                    Match
                  </button>
                </div>
                <div id="godown-mobile-variance-${d.date_key}">
                  ${varBadge}
                </div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    // 4. Desktop Data Table View (>= 768px)
    const tableHTML = `
      <div class="data-table-container desktop-table-view">
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Day</th>
                <th>Status</th>
                <th style="text-align:right;">Beer Cases</th>
                <th style="text-align:right;">IMFL Cases</th>
                <th style="text-align:right;">CS Cases</th>
                <th style="text-align:right;">Portal Dispatched (cs)</th>
                <th style="text-align:right;width:150px;">Physical Godown (cs)</th>
                <th style="text-align:right;">Net Variance</th>
                <th style="text-align:center;width:90px;">Action</th>
              </tr>
            </thead>
            <tbody>
              ${series.length === 0 ? `
                <tr><td colspan="10" style="text-align:center;padding:3rem;color:var(--text-muted);">No calendar days in this horizon</td></tr>
              ` : series.map((d, idx) => {
                const varBadge = renderVarianceBadge(d.difference);
                const initVal = (d.godown_cases !== null && d.godown_cases !== undefined) ? String(d.godown_cases) : '';

                return `
                  <tr id="godown-row-${d.date_key}">
                    <td class="num-tabular" style="font-weight:700;">${AppUtils.escapeHtml(d.date_str)}</td>
                    <td style="color:var(--text-secondary);">${AppUtils.escapeHtml(d.day)}</td>
                    <td>
                      ${d.is_closed
                        ? `<span class="party-cadence-badge cadence-dormant">Closed</span>`
                        : `<span class="party-cadence-badge cadence-regular">Operating</span>`}
                    </td>
                    <td class="cell-num" style="text-align:right;color:var(--brand-beer);">${AppUtils.formatNumber(d.beer_cases, 0)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--brand-imfl);">${AppUtils.formatNumber(d.imfl_cases, 0)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--brand-cs);">${AppUtils.formatNumber(d.cs_cases, 0)}</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;font-size:0.95rem;">
                      ${AppUtils.formatNumber(d.cases)}
                    </td>
                    <td style="text-align:right;">
                      <input
                        type="number"
                        step="0.01"
                        id="godown-input-${d.date_key}"
                        data-date-key="${d.date_key}"
                        data-index="${idx}"
                        data-last-saved="${initVal}"
                        class="godown-input-cell"
                        value="${initVal}"
                        placeholder="0.00"
                        onkeydown="WorkspaceGodown.handleInputKeydown(event, '${d.date_key}', ${idx}, false)"
                        onblur="WorkspaceGodown.saveInput('${d.date_key}', this, false)"
                      />
                    </td>
                    <td style="text-align:right;" id="godown-variance-${d.date_key}">${varBadge}</td>
                    <td style="text-align:center;">
                      <button class="action-btn" style="padding:3px 8px;font-size:0.75rem;" onclick="WorkspaceGodown.matchSingleDay('${d.date_key}', ${d.cases})">
                        Match
                      </button>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
            <tfoot>
              <tr style="background:var(--bg-elevated);font-weight:700;border-top:1px solid var(--border-strong);">
                <td colspan="6" style="text-align:right;text-transform:uppercase;font-size:0.75rem;color:var(--text-muted);">Totals:</td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(totalPortalCases)}</td>
                <td class="cell-num" style="text-align:right;" id="godown-foot-physical">${hasAnyPhysical ? AppUtils.formatNumber(totalPhysicalCases) : '—'}</td>
                <td class="cell-num" style="text-align:right;${hasAnyPhysical ? (Math.abs(netVariance) < 0.01 ? 'color:var(--status-success);' : (netVariance > 0 ? 'color:var(--accent-amber);' : 'color:var(--status-danger);')) : ''}" id="godown-foot-variance">
                  ${hasAnyPhysical ? (netVariance > 0 ? '+' : '') + AppUtils.formatNumber(netVariance) : '—'}
                </td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    `;

    container.innerHTML = summaryCardsHTML + toolbarHTML + mobileCardsHTML + tableHTML;
  },

  // Fix 15: Enter flow awaits save, updates cells in place, then advances focus
  async handleInputKeydown(e, dateKey, idx, isMobile = false) {
    if (e.key === 'Enter') {
      e.preventDefault();
      const input = e.target;
      await this.saveInput(dateKey, input, isMobile);

      // Advance focus to next input
      const nextIdx = idx + 1;
      const selector = isMobile
        ? `#godown-mobile-input-`
        : `input[data-index="${nextIdx}"]`;
      const nextInput = isMobile
        ? document.querySelectorAll('.mobile-cards-view .godown-input-cell')[nextIdx]
        : document.querySelector(selector);

      if (nextInput) {
        nextInput.focus();
        nextInput.select();
      }
    }
  },

  // Fix 1 & 14 & 15: Save with changed-value guard and in-place row cell updates
  async saveInput(dateKey, inputEl = null, isMobile = false) {
    const input = inputEl || document.getElementById(isMobile ? `godown-mobile-input-${dateKey}` : `godown-input-${dateKey}`);
    if (!input) return;

    const val = input.value.trim();
    const casesVal = val === '' ? null : parseFloat(val);
    const currentValStr = casesVal !== null ? String(casesVal) : '';

    // Prevent double POST on enter + blur if unchanged
    if (input.dataset.lastSaved !== undefined && input.dataset.lastSaved === currentValStr) {
      return;
    }

    try {
      // Fix 1: Call AppAPI.saveGodownEntry
      await AppAPI.saveGodownEntry(dateKey, casesVal, '');
      input.dataset.lastSaved = currentValStr;

      // Sync the twin input (desktop vs mobile)
      const otherInput = document.getElementById(isMobile ? `godown-input-${dateKey}` : `godown-mobile-input-${dateKey}`);
      if (otherInput) {
        otherInput.value = currentValStr;
        otherInput.dataset.lastSaved = currentValStr;
      }

      AppUtils.showToast(`Saved godown count for ${AppUtils.formatDateKeyToDisplay(dateKey)}`, 'success');

      // Update local movementData state
      const data = AppState.movementData;
      if (data && data.daily_series) {
        const row = data.daily_series.find(d => d.date_key === dateKey);
        if (row) {
          row.godown_cases = casesVal;
          row.difference = casesVal !== null ? (casesVal - (row.cases || 0)) : null;

          // Update variance badge in place (no full re-render)
          this.updateRowVarianceInPlace(dateKey, row);
        }
      }

      // Fix 14: recompute summary and update KPI cards in place
      this.updateSummaryFromDailySeries();
      this.updateTopCardsInPlace();
    } catch (e) {
      AppUtils.showToast('Failed to save godown count: ' + e.message, 'danger');
    }
  },

  updateRowVarianceInPlace(dateKey, row) {
    const renderBadge = (diff) => {
      if (diff === null || diff === undefined) {
        return `<span style="color:var(--text-muted);">—</span>`;
      }
      if (Math.abs(diff) < 0.01) {
        return `<span class="variance-badge variance-zero">Balanced</span>`;
      }
      if (diff > 0) {
        return `<span class="variance-badge variance-surplus">+${AppUtils.formatNumber(diff)} cs</span>`;
      }
      return `<span class="variance-badge variance-deficit">${AppUtils.formatNumber(diff)} cs</span>`;
    };

    const dEl = document.getElementById(`godown-variance-${dateKey}`);
    if (dEl) dEl.innerHTML = renderBadge(row.difference);

    const mEl = document.getElementById(`godown-mobile-variance-${dateKey}`);
    if (mEl) mEl.innerHTML = renderBadge(row.difference);
  },

  updateSummaryFromDailySeries() {
    const data = AppState.movementData;
    if (!data || !data.daily_series || !data.summary) return;

    const series = data.daily_series;
    const totalPortalCases = series.reduce((acc, d) => acc + (d.cases || 0), 0);
    const hasAnyPhysical = series.some(d => d.godown_cases !== null && d.godown_cases !== undefined);
    const totalPhysicalCases = series.reduce((acc, d) => acc + (d.godown_cases !== null && d.godown_cases !== undefined ? Number(d.godown_cases) : 0), 0);

    data.summary.godown_cases = hasAnyPhysical ? roundTo2(totalPhysicalCases) : null;
    data.summary.difference = hasAnyPhysical ? roundTo2(totalPhysicalCases - totalPortalCases) : null;

    function roundTo2(n) {
      return Math.round(n * 100) / 100;
    }
  },

  updateTopCardsInPlace() {
    const data = AppState.movementData;
    if (!data || !data.daily_series) return;

    const series = data.daily_series;
    const totalPortalCases = series.reduce((acc, d) => acc + (d.cases || 0), 0);
    const hasAnyPhysical = series.some(d => d.godown_cases !== null && d.godown_cases !== undefined);
    const totalPhysicalCases = series.reduce((acc, d) => acc + (d.godown_cases !== null && d.godown_cases !== undefined ? Number(d.godown_cases) : 0), 0);
    const netVariance = hasAnyPhysical ? (totalPhysicalCases - totalPortalCases) : 0;

    const operatingDays = series.filter(d => !d.is_closed).length;
    const daysWithEntry = series.filter(d => d.godown_cases !== null && d.godown_cases !== undefined && !d.is_closed).length;
    const matchedDays = series.filter(d => d.difference !== null && Math.abs(d.difference) < 0.01 && !d.is_closed).length;

    const pVal = document.getElementById('kpi-godown-physical-val');
    if (pVal) pVal.innerText = hasAnyPhysical ? AppUtils.formatNumber(totalPhysicalCases) : '—';

    const vVal = document.getElementById('kpi-godown-variance-val');
    if (vVal) {
      vVal.innerText = hasAnyPhysical ? (netVariance > 0 ? '+' : '') + AppUtils.formatNumber(netVariance) : '—';
      vVal.style.color = hasAnyPhysical ? (Math.abs(netVariance) < 0.01 ? 'var(--status-success)' : (netVariance > 0 ? 'var(--accent-amber)' : 'var(--status-danger)')) : '';
    }

    const vSub = document.getElementById('kpi-godown-variance-sub');
    if (vSub) {
      vSub.innerHTML = hasAnyPhysical ? (
        Math.abs(netVariance) < 0.01 ? '<span style="color:var(--status-success);">100% Balanced</span>' :
        (netVariance > 0 ? `<span style="color:var(--accent-amber);">Surplus (${AppUtils.formatNumber(netVariance)} cs)</span>` :
        `<span style="color:var(--status-danger);">Deficit (${AppUtils.formatNumber(netVariance)} cs)</span>`)
      ) : '<span style="color:var(--text-muted);">No physical entries</span>';
    }

    const prgVal = document.getElementById('kpi-godown-progress-val');
    if (prgVal) prgVal.innerText = `${daysWithEntry} / ${operatingDays}`;

    const prgSub = document.getElementById('kpi-godown-progress-sub');
    if (prgSub) prgSub.innerHTML = `<span>${matchedDays} matched (|var| &lt; 0.01)</span>`;

    const fPhys = document.getElementById('godown-foot-physical');
    if (fPhys) fPhys.innerText = hasAnyPhysical ? AppUtils.formatNumber(totalPhysicalCases) : '—';

    const fVar = document.getElementById('godown-foot-variance');
    if (fVar) {
      fVar.innerText = hasAnyPhysical ? (netVariance > 0 ? '+' : '') + AppUtils.formatNumber(netVariance) : '—';
      fVar.style.color = hasAnyPhysical ? (Math.abs(netVariance) < 0.01 ? 'var(--status-success)' : (netVariance > 0 ? 'var(--accent-amber)' : 'var(--status-danger)')) : '';
    }
  },

  async matchSingleDay(dateKey, portalCases) {
    const val = parseFloat(portalCases) || 0.0;
    const desktopInput = document.getElementById(`godown-input-${dateKey}`);
    const mobileInput = document.getElementById(`godown-mobile-input-${dateKey}`);
    if (desktopInput) desktopInput.value = val.toFixed(2);
    if (mobileInput) mobileInput.value = val.toFixed(2);

    try {
      await AppAPI.saveGodownEntry(dateKey, val, 'Matched to portal');
      AppUtils.showToast(`Matched ${AppUtils.formatDateKeyToDisplay(dateKey)} to portal (${val} cs)`, 'success');

      if (desktopInput) desktopInput.dataset.lastSaved = String(val);
      if (mobileInput) mobileInput.dataset.lastSaved = String(val);

      const data = AppState.movementData;
      if (data && data.daily_series) {
        const row = data.daily_series.find(d => d.date_key === dateKey);
        if (row) {
          row.godown_cases = val;
          row.difference = 0.0;
          this.updateRowVarianceInPlace(dateKey, row);
        }
      }
      this.updateSummaryFromDailySeries();
      this.updateTopCardsInPlace();
    } catch (e) {
      AppUtils.showToast('Failed to update entry: ' + e.message, 'danger');
    }
  },

  // Fix 1: Count failures, show real error toast if any fail, update state only on confirmed save
  async matchAllPortal() {
    const data = AppState.movementData;
    if (!data || !data.daily_series) return;
    if (!confirm('Match all operating days to portal dispatched counts?')) return;

    let successCount = 0;
    let failCount = 0;

    for (const d of data.daily_series) {
      if (!d.is_closed) {
        try {
          await AppAPI.saveGodownEntry(d.date_key, d.cases, 'Batch matched to portal');
          d.godown_cases = d.cases;
          d.difference = 0.0;
          successCount++;

          const inpD = document.getElementById(`godown-input-${d.date_key}`);
          const inpM = document.getElementById(`godown-mobile-input-${d.date_key}`);
          if (inpD) { inpD.value = d.cases.toFixed(2); inpD.dataset.lastSaved = String(d.cases); }
          if (inpM) { inpM.value = d.cases.toFixed(2); inpM.dataset.lastSaved = String(d.cases); }
          this.updateRowVarianceInPlace(d.date_key, d);
        } catch (e) {
          failCount++;
        }
      }
    }

    if (failCount > 0) {
      AppUtils.showToast(`Matched ${successCount} days, but ${failCount} failed to save`, 'danger');
    } else {
      AppUtils.showToast(`All ${successCount} operating days matched to portal counts`, 'success');
    }

    this.updateSummaryFromDailySeries();
    this.updateTopCardsInPlace();
  }
};

window.WorkspaceGodown = WorkspaceGodown;
