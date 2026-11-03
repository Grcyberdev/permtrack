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

    const series = data.daily_series || [];
    const totalPortalCases = series.reduce((acc, d) => acc + (d.cases || 0), 0);
    const hasAnyPhysical = series.some(d => d.godown_cases !== null && d.godown_cases !== undefined);
    const totalPhysicalCases = series.reduce((acc, d) => acc + (d.godown_cases !== null && d.godown_cases !== undefined ? Number(d.godown_cases) : 0), 0);
    const netVariance = hasAnyPhysical ? (totalPhysicalCases - totalPortalCases) : 0;
    const reconciledDays = series.filter(d => d.difference !== null && Math.abs(d.difference) < 0.01).length;
    const operatingDays = series.filter(d => !d.is_closed).length;

    // 1. Top Summary Cards (4 Cards)
    const summaryCardsHTML = `
      <div class="executive-kpi-grid" style="margin-bottom:1.25rem;">
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
            <span class="kpi-value">${hasAnyPhysical ? AppUtils.formatNumber(totalPhysicalCases) : '—'}</span>
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
            <span class="kpi-value" style="${hasAnyPhysical ? (netVariance === 0 ? 'color:var(--status-success);' : (netVariance > 0 ? 'color:var(--accent-amber);' : 'color:var(--status-danger);')) : ''}">
              ${hasAnyPhysical ? (netVariance > 0 ? '+' : '') + AppUtils.formatNumber(netVariance) : '—'}
            </span>
            <span class="kpi-unit">cs</span>
          </div>
          <div class="kpi-subtitle">
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
            <span class="kpi-value">${reconciledDays} / ${operatingDays}</span>
            <span class="kpi-unit">days</span>
          </div>
          <div class="kpi-subtitle">
            <span>${operatingDays > 0 ? Math.round((reconciledDays / operatingDays) * 100) : 100}% reconciled</span>
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

    // 3. Mobile Cards View (< 768px)
    const mobileCardsHTML = `
      <div class="mobile-cards-view">
        ${series.length === 0 ? `
          <div style="text-align:center;padding:3rem 1rem;color:var(--text-muted);">No calendar days in this horizon</div>
        ` : series.map((d, idx) => {
          const diff = d.difference;
          let varBadge = `<span style="color:var(--text-muted);">—</span>`;
          if (diff !== null && diff !== undefined) {
            if (Math.abs(diff) < 0.01) {
              varBadge = `<span class="variance-badge variance-zero">Balanced</span>`;
            } else if (diff > 0) {
              varBadge = `<span class="variance-badge variance-surplus">+${AppUtils.formatNumber(diff)} cs</span>`;
            } else {
              varBadge = `<span class="variance-badge variance-deficit">${AppUtils.formatNumber(diff)} cs</span>`;
            }
          }

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
                    class="godown-input-cell"
                    style="max-width:110px;"
                    value="${d.godown_cases !== null && d.godown_cases !== undefined ? d.godown_cases : ''}"
                    placeholder="0.00"
                    onkeydown="if(event.key==='Enter')WorkspaceGodown.saveMobileInput('${d.date_key}')"
                    onblur="WorkspaceGodown.saveMobileInput('${d.date_key}')"
                  />
                  <button class="action-btn" style="padding:4px 8px;font-size:0.75rem;" onclick="WorkspaceGodown.matchSingleDay('${d.date_key}', ${d.cases})">
                    Match
                  </button>
                </div>
                <div>
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
                const diff = d.difference;
                let varBadge = `<span style="color:var(--text-muted);">—</span>`;
                if (diff !== null && diff !== undefined) {
                  if (Math.abs(diff) < 0.01) {
                    varBadge = `<span class="variance-badge variance-zero">Balanced</span>`;
                  } else if (diff > 0) {
                    varBadge = `<span class="variance-badge variance-surplus">+${AppUtils.formatNumber(diff)} cs</span>`;
                  } else {
                    varBadge = `<span class="variance-badge variance-deficit">${AppUtils.formatNumber(diff)} cs</span>`;
                  }
                }

                return `
                  <tr>
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
                        class="godown-input-cell"
                        value="${d.godown_cases !== null && d.godown_cases !== undefined ? d.godown_cases : ''}"
                        placeholder="0.00"
                        onkeydown="WorkspaceGodown.handleInputKeydown(event, '${d.date_key}', ${idx})"
                        onblur="WorkspaceGodown.saveInput('${d.date_key}')"
                      />
                    </td>
                    <td style="text-align:right;">${varBadge}</td>
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
                <td class="cell-num" style="text-align:right;">${hasAnyPhysical ? AppUtils.formatNumber(totalPhysicalCases) : '—'}</td>
                <td class="cell-num" style="text-align:right;${hasAnyPhysical ? (netVariance === 0 ? 'color:var(--status-success);' : (netVariance > 0 ? 'color:var(--accent-amber);' : 'color:var(--status-danger);')) : ''}">
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

  handleInputKeydown(e, dateKey, idx) {
    if (e.key === 'Enter') {
      e.preventDefault();
      this.saveInput(dateKey);
      const nextInput = document.querySelector(`input[data-index="${idx + 1}"]`);
      if (nextInput) {
        nextInput.focus();
        nextInput.select();
      }
    }
  },

  async saveInput(dateKey) {
    const input = document.getElementById(`godown-input-${dateKey}`);
    if (!input) return;
    const val = input.value.trim();
    const casesVal = val === '' ? null : parseFloat(val);

    try {
      await AppAPI.saveGodownEntry(dateKey, casesVal, '');
      AppUtils.showToast(`Saved godown count for ${AppUtils.formatDateKeyToDisplay(dateKey)}`, 'success');
      // Update local state and re-render
      const data = AppState.movementData;
      if (data && data.daily_series) {
        const row = data.daily_series.find(d => d.date_key === dateKey);
        if (row) {
          row.godown_cases = casesVal;
          row.difference = casesVal !== null ? (casesVal - (row.cases || 0)) : null;
        }
      }
      this.render();
    } catch (e) {
      AppUtils.showToast('Failed to save godown count', 'danger');
    }
  },

  async saveMobileInput(dateKey) {
    const input = document.getElementById(`godown-mobile-input-${dateKey}`);
    if (!input) return;
    const val = input.value.trim();
    const casesVal = val === '' ? null : parseFloat(val);

    try {
      await AppAPI.saveGodownEntry(dateKey, casesVal, '');
      AppUtils.showToast(`Saved godown count for ${AppUtils.formatDateKeyToDisplay(dateKey)}`, 'success');
      const data = AppState.movementData;
      if (data && data.daily_series) {
        const row = data.daily_series.find(d => d.date_key === dateKey);
        if (row) {
          row.godown_cases = casesVal;
          row.difference = casesVal !== null ? (casesVal - (row.cases || 0)) : null;
        }
      }
      this.render();
    } catch (e) {
      AppUtils.showToast('Failed to save godown count', 'danger');
    }
  },

  async matchSingleDay(dateKey, portalCases) {
    const val = parseFloat(portalCases) || 0.0;
    const input = document.getElementById(`godown-input-${dateKey}`) || document.getElementById(`godown-mobile-input-${dateKey}`);
    if (input) input.value = val.toFixed(2);

    try {
      await AppAPI.saveGodownEntry(dateKey, val, 'Matched to portal');
      AppUtils.showToast(`Matched ${AppUtils.formatDateKeyToDisplay(dateKey)} to portal (${val} cs)`, 'success');
      const data = AppState.movementData;
      if (data && data.daily_series) {
        const row = data.daily_series.find(d => d.date_key === dateKey);
        if (row) {
          row.godown_cases = val;
          row.difference = 0.0;
        }
      }
      this.render();
    } catch (e) {
      AppUtils.showToast('Failed to update entry', 'danger');
    }
  },

  async matchAllPortal() {
    const data = AppState.movementData;
    if (!data || !data.daily_series) return;
    if (!confirm('Match all operating days to portal dispatched counts?')) return;

    for (const d of data.daily_series) {
      if (!d.is_closed) {
        try {
          await AppAPI.saveGodownEntry(d.date_key, d.cases, 'Batch matched to portal');
          d.godown_cases = d.cases;
          d.difference = 0.0;
        } catch (e) {}
      }
    }
    AppUtils.showToast('All operating days matched to portal counts', 'success');
    this.render();
  }
};

window.WorkspaceGodown = WorkspaceGodown;
