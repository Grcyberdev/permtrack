/**
 * PermTrack Enterprise — Workspace 5: Godown Reconciliation, Scraper & Operations
 */
const WorkspaceGodown = {
  render() {
    const container = document.getElementById('workspace-godown-content');
    if (!container) return;

    const data = AppState.movementData;
    if (!data) {
      container.innerHTML = `<div style="text-align:center;padding:4rem;color:var(--text-muted);">Loading Godown & Operations...</div>`;
      return;
    }

    const series = data.daily_series || [];

    const reconHTML = `
      <div class="card-title-row" style="margin-bottom:0.75rem;">
        <div>
          <div class="card-title">⚖️ Physical Godown vs Portal Dispatch Reconciliation</div>
          <div class="card-subtitle">Daily side-by-side audit with zero-mismatch normalized keys. Press Enter in any box to save and advance.</div>
        </div>
        <div style="display:flex;align-items:center;gap:0.5rem;">
          <button class="action-btn" onclick="WorkspaceGodown.matchAllPortal()">
            Match All to Portal
          </button>
        </div>
      </div>

      <div class="data-table-container" style="margin-bottom:1.5rem;">
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
                <th style="text-align:right;width:140px;">Physical Godown (cs)</th>
                <th style="text-align:right;">Net Variance</th>
                <th style="text-align:center;">Action</th>
              </tr>
            </thead>
            <tbody>
              ${series.length === 0 ? `
                <tr><td colspan="10" style="text-align:center;padding:2rem;color:var(--text-muted);">No calendar days in this horizon</td></tr>
              ` : series.map((d, idx) => {
                const diff = d.difference;
                let varBadge = `<span style="color:var(--text-muted);">—</span>`;
                if (diff !== null && diff !== undefined) {
                  if (diff === 0) {
                    varBadge = `<span class="variance-badge variance-zero">✓ Matched</span>`;
                  } else if (diff > 0) {
                    varBadge = `<span class="variance-badge variance-surplus">+${AppUtils.formatNumber(diff)} cs (Surplus)</span>`;
                  } else {
                    varBadge = `<span class="variance-badge variance-deficit">${AppUtils.formatNumber(diff)} cs (Deficit)</span>`;
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
                      <button class="action-btn" style="padding:2px 8px;font-size:0.75rem;" onclick="WorkspaceGodown.matchSingleDay('${d.date_key}', ${d.cases})">
                        Match
                      </button>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;

    // Live Scraper Terminal & Diagnostics Section
    const scraperHTML = `
      <div class="card-title-row">
        <div>
          <div class="card-title">🤖 Assam State Excise Live Scraper & Sync Console</div>
          <div class="card-subtitle">Trigger automated background syncs or real-time workflow dispatch with self-healing retries.</div>
        </div>
        <div style="display:flex;align-items:center;gap:0.5rem;">
          <button class="action-btn btn-sync" onclick="WorkspaceGodown.triggerSyncNow()">
            ⚡ Sync Today Now
          </button>
          <button class="action-btn" onclick="WorkspaceGodown.promptBackfill()">
            📅 Backfill Custom Date
          </button>
        </div>
      </div>

      <div class="scraper-terminal-container">
        <div class="scraper-terminal-header">
          <span class="terminal-title">
            <span style="color:#22C55E;">●</span> Live WebSocket Scraper Feed
          </span>
          <button class="action-btn" style="padding:2px 8px;font-size:0.7rem;" onclick="AppState.scraperLogs=[];WorkspaceGodown.updateTerminalLogs();">
            Clear Logs
          </button>
        </div>
        <div id="scraper-logs-window" class="terminal-logs-window">
          ${AppState.scraperLogs.length > 0
            ? AppState.scraperLogs.map(l => AppUtils.escapeHtml(l)).join('\n')
            : 'Terminal standby. Ready for sync trigger or real-time log streaming.'}
        </div>
      </div>
    `;

    container.innerHTML = reconHTML + scraperHTML;
    this.connectScraperWebSocket();
  },

  async handleInputKeydown(event, dateKey, index) {
    if (event.key === 'Enter') {
      event.preventDefault();
      await this.saveInput(dateKey);
      // Auto-advance to next day input
      const nextInput = document.querySelector(`input[data-index="${index + 1}"]`);
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

    try {
      await AppAPI.saveGodownReconciliation(dateKey, val === '' ? null : val);
      AppUtils.showToast(`Saved godown count for ${AppUtils.formatDateKeyToDisplay(dateKey)}`, 'success');
      // Refresh current movement view to recalculate variances
      window.refreshCurrentHorizon(false);
    } catch (e) {
      AppUtils.showToast(`Error saving godown count: ${e.message}`, 'error');
    }
  },

  async matchSingleDay(dateKey, portalCases) {
    const input = document.getElementById(`godown-input-${dateKey}`);
    if (input) input.value = portalCases;
    await AppAPI.saveGodownReconciliation(dateKey, portalCases);
    AppUtils.showToast(`Matched ${AppUtils.formatDateKeyToDisplay(dateKey)} to ${portalCases} cs`, 'success');
    window.refreshCurrentHorizon(false);
  },

  async matchAllPortal() {
    const data = AppState.movementData;
    if (!data || !data.daily_series) return;
    if (!confirm('Match all operating days in this horizon to Portal Dispatched Cases?')) return;

    for (const d of data.daily_series) {
      if (!d.is_closed && d.cases > 0) {
        await AppAPI.saveGodownReconciliation(d.date_key, d.cases);
      }
    }
    AppUtils.showToast('All operating days matched to portal figures!', 'success');
    window.refreshCurrentHorizon(false);
  },

  async triggerSyncNow() {
    AppUtils.showToast('Initiating live scraper sync for latest date...', 'info');
    try {
      const resp = await AppAPI.triggerScraper(null, 'BOTH', 7);
      if (resp.status === 'success' || resp.success) {
        AppUtils.showToast('Scraper job launched successfully!', 'success');
        this.appendLog(`[${new Date().toLocaleTimeString()}] 🚀 Scraper job launched.`);
      } else {
        AppUtils.showToast(resp.message || 'Scraper started', 'info');
      }
    } catch (e) {
      AppUtils.showToast(`Failed to trigger scraper: ${e.message}`, 'error');
    }
  },

  promptBackfill() {
    const dateInput = prompt('Enter date to scrape (DD-MM-YYYY or YYYY-MM-DD):');
    if (!dateInput) return;
    AppAPI.triggerScraper(dateInput.trim(), 'BOTH', 7)
      .then(resp => {
        AppUtils.showToast(`Backfill initiated for ${dateInput}`, 'success');
      })
      .catch(err => {
        AppUtils.showToast(`Error: ${err.message}`, 'error');
      });
  },

  connectScraperWebSocket() {
    if (AppState.scraperWs && AppState.scraperWs.readyState === WebSocket.OPEN) return;
    try {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${proto}//${window.location.host}/ws/run`);

      ws.onopen = () => {
        this.appendLog(`[${new Date().toLocaleTimeString()}] Connected to live scraper log stream.`);
      };

      ws.onmessage = (event) => {
        this.appendLog(event.data);
      };

      ws.onclose = () => {
        // Will reconnect on user action
      };

      AppState.scraperWs = ws;
    } catch (e) {
      console.warn('WebSocket connection not available:', e);
    }
  },

  appendLog(line) {
    AppState.scraperLogs.push(line);
    if (AppState.scraperLogs.length > 500) {
      AppState.scraperLogs.shift();
    }
    this.updateTerminalLogs();
  },

  updateTerminalLogs() {
    const win = document.getElementById('scraper-logs-window');
    if (win) {
      win.innerText = AppState.scraperLogs.join('\n');
      win.scrollTop = win.scrollHeight;
    }
  }
};

window.WorkspaceGodown = WorkspaceGodown;
