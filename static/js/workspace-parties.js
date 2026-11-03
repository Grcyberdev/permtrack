/**
 * PermTrack Enterprise — Workspace 4: Retailer (Party) Intelligence
 */
const WorkspaceParties = {
  render() {
    const container = document.getElementById('workspace-parties-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:4rem;color:var(--text-muted);">Loading Retailer Intelligence...</div>`;
      return;
    }

    let parties = data.parties_full || [];
    const q = (AppState.partySearchQuery || '').toLowerCase().trim();
    if (q) {
      parties = parties.filter(p =>
        p.name.toLowerCase().includes(q) ||
        (p.district && p.district.toLowerCase().includes(q))
      );
    }

    const totalCases = parties.reduce((acc, p) => acc + (p.dispatched_cases || 0), 0);
    const totalMRP = parties.reduce((acc, p) => acc + (p.mrp || 0), 0);

    const toolbarHTML = `
      <div class="table-toolbar">
        <div class="search-box-wrap">
          <svg class="search-icon-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input type="text" class="search-input" placeholder="Search retailer or shop name, district..." value="${AppUtils.escapeHtml(AppState.partySearchQuery)}" oninput="AppState.partySearchQuery=this.value;WorkspaceParties.render();" />
        </div>
        <div style="display:flex;align-items:center;gap:0.75rem;">
          <span class="table-stats-badge">
            ${parties.length} Retailers • ${AppUtils.formatNumber(totalCases)} Total Cases • ${AppUtils.formatCurrencyINR(totalMRP, true)}
          </span>
        </div>
      </div>
    `;

    const tableHTML = `
      <div class="data-table-container">
        <div class="data-table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:40px;">#</th>
                <th>Licensee / Retail Shop Name</th>
                <th>District</th>
                <th style="text-align:right;">Dispatched (cs)</th>
                <th style="text-align:right;">Pending in Bond</th>
                <th style="text-align:right;">Beer</th>
                <th style="text-align:right;">IMFL</th>
                <th style="text-align:right;">CS</th>
                <th style="text-align:right;">Total Turnover (₹)</th>
                <th style="text-align:center;">Cadence</th>
                <th>Last Order</th>
                <th>Top Brands Bought</th>
              </tr>
            </thead>
            <tbody>
              ${parties.length === 0 ? `
                <tr><td colspan="12" style="text-align:center;padding:3rem;color:var(--text-muted);">No retailers found matching search</td></tr>
              ` : parties.map((p, idx) => {
                const brandsBoughtPills = (p.brands_bought || []).map(b =>
                  `<span class="pack-pill" title="${b.name}: ${AppUtils.formatNumber(b.cases)} cs">${AppUtils.escapeHtml(b.name.split(' ')[0])} (${AppUtils.formatNumber(b.cases, 0)}cs)</span>`
                ).join('');

                let cadenceBadge = `<span class="party-cadence-badge cadence-active">Active</span>`;
                if (p.cadence_status === 'regular') {
                  cadenceBadge = `<span class="party-cadence-badge cadence-regular">🟢 Regular</span>`;
                } else if (p.cadence_status === 'dormant') {
                  cadenceBadge = `<span class="party-cadence-badge cadence-dormant">⚪ Dormant</span>`;
                }

                return `
                  <tr>
                    <td class="num-tabular" style="color:var(--text-muted);font-size:0.75rem;">${idx + 1}</td>
                    <td style="font-weight:700;">
                      <a href="#" onclick="window.inspectParty('${encodeURIComponent(p.name)}');return false;" style="color:var(--text-primary);text-decoration:underline;">
                        ${AppUtils.escapeHtml(p.name)}
                      </a>
                    </td>
                    <td><span class="pack-pill">${AppUtils.escapeHtml(p.district || 'ASSAM')}</span></td>
                    <td class="cell-num" style="text-align:right;font-weight:700;font-size:0.95rem;">
                      ${AppUtils.formatNumber(p.dispatched_cases)}
                    </td>
                    <td class="cell-num" style="text-align:right;color:${p.pending_cases > 0 ? 'var(--status-warning)' : 'var(--text-muted)'};font-weight:${p.pending_cases > 0 ? '700' : '400'};">
                      ${p.pending_cases > 0 ? AppUtils.formatNumber(p.pending_cases) + ' cs' : '—'}
                    </td>
                    <td class="cell-num" style="text-align:right;color:var(--brand-beer);">${AppUtils.formatNumber(p.beer_cases, 0)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--brand-imfl);">${AppUtils.formatNumber(p.imfl_cases, 0)}</td>
                    <td class="cell-num" style="text-align:right;color:var(--brand-cs);">${AppUtils.formatNumber(p.cs_cases, 0)}</td>
                    <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">
                      ${AppUtils.formatCurrencyINR(p.mrp)}
                    </td>
                    <td style="text-align:center;">${cadenceBadge}</td>
                    <td class="num-tabular" style="font-size:0.8rem;color:var(--text-secondary);white-space:nowrap;">
                      ${AppUtils.escapeHtml(p.last_order_date || '—')}
                    </td>
                    <td>
                      <div class="pack-pill-group">${brandsBoughtPills || '—'}</div>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
            <tfoot>
              <tr style="background:var(--bg-elevated);font-weight:700;border-top:2px solid var(--border-strong);">
                <td colspan="3" style="text-align:right;text-transform:uppercase;color:var(--text-muted);">
                  Totals (${parties.length} Retailers):
                </td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(totalCases)}</td>
                <td colspan="4"></td>
                <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(totalMRP)}</td>
                <td colspan="3"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    `;

    container.innerHTML = toolbarHTML + tableHTML;
  }
};

window.WorkspaceParties = WorkspaceParties;
