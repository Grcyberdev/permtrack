/**
 * PermTrack Enterprise — Main Application Coordinator & Event Router
 * Minimal, Calm, Executive Precision Architecture
 */
(function() {
  window.addEventListener('DOMContentLoaded', async () => {
    // 1. Initialize Theme
    initTheme();

    // 2. Check Auth Status
    await checkInitialAuth();

    // 3. Bind Global Shortcuts & Document Listeners
    bindGlobalListeners();

    // 4. Initial Data Load
    await refreshCurrentHorizon();

    // 5. Connect Scraper Live WebSocket in Background
    initScraperWebSocket();
  });

  function initTheme() {
    const savedTheme = localStorage.getItem('permtrack_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    AppState.theme = savedTheme;
    updateThemeToggleIcon();
  }

  window.toggleTheme = function() {
    const next = AppState.theme === 'dark' ? 'light' : 'dark';
    AppState.theme = next;
    localStorage.setItem('permtrack_theme', next);
    document.documentElement.setAttribute('data-theme', next);
    updateThemeToggleIcon();
    AppUtils.showToast(`Switched to ${next === 'dark' ? 'Obsidian Reserve (Dark)' : 'Warm Alabaster (Light)'}`, 'info');
  };

  function updateThemeToggleIcon() {
    const btn = document.getElementById('theme-toggle-btn');
    if (!btn) return;
    if (AppState.theme === 'dark') {
      // Sun icon
      btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
      btn.title = 'Switch to Light Theme';
    } else {
      // Moon icon
      btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
      btn.title = 'Switch to Dark Theme';
    }
  }

  async function checkInitialAuth() {
    try {
      const auth = await AppAPI.checkAuthStatus();
      if (!auth.authenticated) {
        showAuthModal(true);
      } else {
        updateUserBadge();
      }
    } catch (e) {
      showAuthModal(true);
    }
  }

  function updateUserBadge() {
    const el = document.getElementById('user-profile-badge');
    if (el && AppState.user) {
      el.innerHTML = `
        <span style="font-weight:600;font-size:0.8rem;color:var(--text-primary);">${AppUtils.escapeHtml(AppState.user.name || AppState.user.username)}</span>
        <button onclick="handleLogout()" style="margin-left:8px;font-size:0.75rem;color:var(--text-muted);text-decoration:underline;">Logout</button>
      `;
    }
  }

  window.handleLoginSubmit = async function(e) {
    if (e) e.preventDefault();
    const u = document.getElementById('login-username').value.trim();
    const p = document.getElementById('login-password').value.trim();
    const errEl = document.getElementById('login-error-msg');
    if (errEl) errEl.innerText = '';

    try {
      await AppAPI.login(u, p);
      showAuthModal(false);
      updateUserBadge();
      AppUtils.showToast('Terminal session authorized', 'success');
      await refreshCurrentHorizon();
    } catch (err) {
      if (errEl) errEl.innerText = err.message || 'Login failed';
    }
  };

  window.handleLogout = async function() {
    await AppAPI.logout();
    showAuthModal(true);
  };

  function showAuthModal(show) {
    const overlay = document.getElementById('auth-modal-overlay');
    if (overlay) {
      overlay.style.display = show ? 'flex' : 'none';
    }
  }

  /**
   * Main Horizon Loader & Workspace Synchronizer
   */
  window.refreshCurrentHorizon = async function(showLoadingToast = false) {
    const ind = document.getElementById('sync-status-indicator');
    if (ind) ind.innerText = 'Syncing...';

    try {
      const data = await AppAPI.fetchMovementAnalytics(
        AppState.horizonMode,
        AppState.anchorDate,
        AppState.customStartDate,
        AppState.customEndDate
      );

      // Store available dates list
      if (data.available_dates && Array.isArray(data.available_dates)) {
        AppState.availableDates = data.available_dates;
      }

      // Synchronize Header Time-Horizon Bar
      renderHeaderHorizonBar(data.horizon);

      // Render Active Workspace
      renderActiveWorkspace();

      if (ind) ind.innerText = 'Live';
      if (showLoadingToast) {
        AppUtils.showToast('Data refreshed successfully', 'success');
      }
    } catch (e) {
      console.error('Failed to refresh horizon:', e);
      if (ind) ind.innerText = 'Offline';
    }
  };

  function renderHeaderHorizonBar(horizon) {
    if (!horizon) return;

    // Active pill state
    document.querySelectorAll('.horizon-pill').forEach(el => {
      const mode = el.getAttribute('data-mode');
      el.classList.toggle('active', mode === AppState.horizonMode);
    });

    // Update stepper label
    const labelEl = document.getElementById('stepper-current-label');
    if (labelEl) {
      labelEl.innerText = horizon.display_label || 'Current Period';
    }
  }

  window.setHorizonMode = function(mode) {
    AppState.horizonMode = mode;
    // When switching to 'day', reset anchorDate back to latest date
    if (mode === 'day') {
      AppState.anchorDate = null;
    }
    window.refreshCurrentHorizon();
  };

  /**
   * Smart Period Stepping
   * Day: 1 Day back/forward
   * Week: 7 Days back/forward
   * Month: 1 Calendar Month back/forward
   * Range: Shift range by its span
   */
  window.stepPeriod = function(direction) {
    const data = AppState.movementData;
    if (!data || !data.horizon) return;
    const h = data.horizon;
    const mode = AppState.horizonMode;

    if (mode === 'day') {
      const avail = AppState.availableDates || [];
      const curKey = h.start_date_key;
      let targetDateKey = null;

      const curIdx = avail.indexOf(curKey);
      if (curIdx !== -1) {
        const nextIdx = curIdx + direction;
        if (nextIdx >= 0 && nextIdx < avail.length) {
          targetDateKey = avail[nextIdx];
        }
      }

      if (!targetDateKey) {
        const dt = new Date(h.start_date);
        dt.setDate(dt.getDate() + direction);
        targetDateKey = dt.toISOString().slice(0, 10);
      } else {
        targetDateKey = AppUtils.formatDateKeyToInput(targetDateKey);
      }

      AppState.anchorDate = targetDateKey;
      window.refreshCurrentHorizon();
    } else if (mode === 'week') {
      // Step anchor date by 7 days
      const baseStr = AppState.anchorDate || h.end_date || h.start_date;
      const dt = new Date(baseStr);
      dt.setDate(dt.getDate() + (direction * 7));
      AppState.anchorDate = dt.toISOString().slice(0, 10);
      window.refreshCurrentHorizon();
    } else if (mode === 'month') {
      // Step anchor date by 1 calendar month
      const baseStr = AppState.anchorDate || h.start_date;
      const dt = new Date(baseStr);
      dt.setDate(1); // Set to 1st of month
      dt.setMonth(dt.getMonth() + direction);
      AppState.anchorDate = dt.toISOString().slice(0, 10);
      window.refreshCurrentHorizon();
    } else if (mode === 'range') {
      if (h.start_date && h.end_date) {
        const dt1 = new Date(h.start_date);
        const dt2 = new Date(h.end_date);
        const diffDays = Math.max(1, Math.round((dt2 - dt1) / (1000 * 60 * 60 * 24))) * direction;
        dt1.setDate(dt1.getDate() + diffDays);
        dt2.setDate(dt2.getDate() + diffDays);
        AppState.customStartDate = dt1.toISOString().slice(0, 10);
        AppState.customEndDate = dt2.toISOString().slice(0, 10);
        window.refreshCurrentHorizon();
      }
    }
  };

  window.handleDayClick = function(dateKey) {
    AppState.horizonMode = 'day';
    AppState.anchorDate = AppUtils.formatDateKeyToInput(dateKey);
    window.refreshCurrentHorizon();
  };

  /**
   * Intuitive Period Picker Popover
   */
  window.openPeriodPicker = function() {
    const modal = document.getElementById('period-picker-modal');
    const body = document.getElementById('period-picker-body');
    if (!modal || !body) return;

    const mode = AppState.horizonMode;
    const avail = AppState.availableDates || [];
    const curDateKey = (AppState.movementData && AppState.movementData.horizon) ? AppState.movementData.horizon.start_date_key : '';

    if (mode === 'day') {
      const recentDates = avail.slice(-6).reverse();
      body.innerHTML = `
        <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:1rem;">Select an operating day to inspect:</div>
        
        <div style="margin-bottom:1rem;">
          <label style="font-size:0.75rem;text-transform:uppercase;color:var(--text-muted);font-weight:600;display:block;margin-bottom:4px;">Direct Date</label>
          <input type="date" id="single-date-picker-input" class="search-input" value="${AppUtils.formatDateKeyToInput(curDateKey)}" />
        </div>

        <div style="margin-bottom:1.25rem;">
          <div style="font-size:0.75rem;text-transform:uppercase;color:var(--text-muted);font-weight:600;margin-bottom:6px;">Recent Active Days</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;">
            <button class="action-btn" style="padding:4px 8px;font-size:0.775rem;" onclick="setSpecificDate(null)">
              Latest Today
            </button>
            ${recentDates.map(dk => `
              <button class="action-btn ${dk === curDateKey ? 'active' : ''}" style="padding:4px 8px;font-size:0.775rem;" onclick="setSpecificDate('${dk}')">
                ${AppUtils.formatDateKeyToDisplay(dk)}
              </button>
            `).join('')}
          </div>
        </div>

        <div style="display:flex;justify-content:flex-end;gap:0.5rem;">
          <button class="action-btn" onclick="closePeriodPicker()">Cancel</button>
          <button class="action-btn" style="background:var(--accent-amber);color:#090B10;font-weight:700;" onclick="applySingleDateInput()">Apply Date</button>
        </div>
      `;
    } else if (mode === 'month') {
      const months = [
        { label: 'November 2026', key: '2026-11-01' },
        { label: 'October 2026', key: '2026-10-01' },
        { label: 'September 2026', key: '2026-09-01' },
        { label: 'August 2026', key: '2026-08-01' }
      ];

      body.innerHTML = `
        <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:1rem;">Select a monthly billing cycle:</div>
        <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:1.25rem;">
          ${months.map(m => `
            <button class="action-btn" style="justify-content:flex-start;padding:8px 12px;font-size:0.85rem;" onclick="setSpecificMonth('${m.key}')">
              ${m.label}
            </button>
          `).join('')}
        </div>
        <div style="display:flex;justify-content:flex-end;">
          <button class="action-btn" onclick="closePeriodPicker()">Cancel</button>
        </div>
      `;
    } else {
      closePeriodPicker();
      openDateRangeModal();
      return;
    }

    modal.classList.add('open');
  };

  window.closePeriodPicker = function() {
    const modal = document.getElementById('period-picker-modal');
    if (modal) modal.classList.remove('open');
  };

  window.setSpecificDate = function(dateKey) {
    AppState.horizonMode = 'day';
    AppState.anchorDate = dateKey ? AppUtils.formatDateKeyToInput(dateKey) : null;
    closePeriodPicker();
    window.refreshCurrentHorizon();
  };

  window.setSpecificMonth = function(monthDateStr) {
    AppState.horizonMode = 'month';
    AppState.anchorDate = monthDateStr;
    closePeriodPicker();
    window.refreshCurrentHorizon();
  };

  window.applySingleDateInput = function() {
    const inp = document.getElementById('single-date-picker-input');
    if (!inp || !inp.value) return;
    AppState.horizonMode = 'day';
    AppState.anchorDate = inp.value;
    closePeriodPicker();
    window.refreshCurrentHorizon();
  };

  /**
   * Custom Range Modal
   */
  window.openDateRangeModal = function() {
    const modal = document.getElementById('custom-range-modal');
    const startInp = document.getElementById('range-modal-start');
    const endInp = document.getElementById('range-modal-end');
    if (modal) {
      if (AppState.movementData && AppState.movementData.horizon) {
        const h = AppState.movementData.horizon;
        if (startInp) startInp.value = h.start_date || '';
        if (endInp) endInp.value = h.end_date || '';
      }
      modal.classList.add('open');
    }
  };

  window.closeDateRangeModal = function() {
    const modal = document.getElementById('custom-range-modal');
    if (modal) modal.classList.remove('open');
  };

  window.applyDateRangeModal = function() {
    const s = document.getElementById('range-modal-start').value;
    const e = document.getElementById('range-modal-end').value;
    if (!s || !e) {
      AppUtils.showToast('Please select both start and end date', 'warning');
      return;
    }
    AppState.horizonMode = 'range';
    AppState.customStartDate = s;
    AppState.customEndDate = e;
    closeDateRangeModal();
    window.refreshCurrentHorizon();
  };

  /**
   * Export Dropdown
   */
  window.toggleExportDropdown = function(e) {
    if (e) e.stopPropagation();
    const menu = document.getElementById('export-dropdown-menu');
    if (menu) menu.classList.toggle('open');
  };

  window.closeExportDropdown = function() {
    const menu = document.getElementById('export-dropdown-menu');
    if (menu) menu.classList.remove('open');
  };

  /**
   * Scraper Live Sync Modal & WebSocket
   */
  window.openSyncModal = function() {
    const modal = document.getElementById('sync-modal');
    if (modal) {
      modal.classList.add('open');
      updateModalLogs();
    }
  };

  window.closeSyncModal = function() {
    const modal = document.getElementById('sync-modal');
    if (modal) modal.classList.remove('open');
  };

  window.triggerSyncNowFromModal = async function() {
    try {
      AppUtils.showToast('Triggering background scraper sync...', 'info');
      await AppAPI.triggerScraper();
      appendScraperLog('🚀 Scraper job triggered from executive console.\nStreaming live feed...\n');
    } catch (e) {
      AppUtils.showToast('Failed to trigger sync: ' + e.message, 'danger');
    }
  };

  window.promptBackfillFromModal = async function() {
    const cur = (AppState.movementData && AppState.movementData.horizon) ? AppUtils.formatDateKeyToDisplay(AppState.movementData.horizon.start_date_key) : '';
    const dateInput = prompt('Enter backfill date (DD-MM-YYYY format):', cur || '02-11-2026');
    if (!dateInput) return;

    try {
      AppUtils.showToast(`Dispatching cloud backfill for ${dateInput}...`, 'info');
      await AppAPI.triggerScraper(dateInput, 'BOTH', false, 7);
      appendScraperLog(`🚀 Cloud backfill dispatched for ${dateInput}.\n`);
    } catch (e) {
      AppUtils.showToast('Failed: ' + e.message, 'danger');
    }
  };

  function updateModalLogs() {
    const logBox = document.getElementById('sync-modal-logs');
    if (logBox) {
      logBox.innerText = AppState.scraperLogs.length > 0
        ? AppState.scraperLogs.join('\n')
        : 'Terminal standby. Ready for sync trigger or real-time log streaming.';
      logBox.scrollTop = logBox.scrollHeight;
    }
  }

  function appendScraperLog(line) {
    AppState.scraperLogs.push(line);
    if (AppState.scraperLogs.length > 500) {
      AppState.scraperLogs.shift();
    }
    updateModalLogs();
  }

  function initScraperWebSocket() {
    try {
      const loc = window.location;
      const wsProto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProto}//${loc.host}/ws/run`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        AppState.scraperWs = ws;
      };

      ws.onmessage = (event) => {
        appendScraperLog(event.data);
        if (event.data.includes('COMPLETED') || event.data.includes('Webhook response received')) {
          window.refreshCurrentHorizon(false);
        }
      };

      ws.onerror = () => {};
      ws.onclose = () => {
        setTimeout(initScraperWebSocket, 10000);
      };
    } catch (e) {}
  }

  /**
   * Category Filter Handler
   */
  window.setCategoryFilter = function(cat) {
    AppState.categoryFilter = cat;
    document.querySelectorAll('.chip-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-cat') === cat);
    });
    renderActiveWorkspace();
  };

  /**
   * Workspace Switcher
   */
  window.switchWorkspace = function(ws) {
    AppState.activeWorkspace = ws;
    syncWorkspaceTabs();
    renderActiveWorkspace();
  };

  window.syncWorkspaceTabs = function() {
    const ws = AppState.activeWorkspace;

    // Desktop Nav Tabs
    document.querySelectorAll('.desktop-workspace-nav .nav-tab-btn').forEach(t => {
      t.classList.toggle('active', t.getAttribute('data-ws') === ws);
    });

    // Mobile Bottom Nav Items
    document.querySelectorAll('.mobile-bottom-nav .mobile-nav-item').forEach(m => {
      m.classList.toggle('active', m.getAttribute('data-ws') === ws);
    });

    // Workspace Content Views
    document.querySelectorAll('.workspace-view').forEach(v => {
      v.classList.toggle('active', v.id === `workspace-${ws}-content`);
    });
  };

  function renderActiveWorkspace() {
    const ws = AppState.activeWorkspace;
    if (ws === 'pulse') WorkspacePulse.render();
    else if (ws === 'products') WorkspaceProducts.render();
    else if (ws === 'indents') WorkspaceIndents.render();
    else if (ws === 'parties') WorkspaceParties.render();
    else if (ws === 'godown') WorkspaceGodown.render();
  }

  window.renderActiveWorkspace = renderActiveWorkspace;

  /**
   * Inspector Drawers (Permit, Party, Brand)
   */
  window.inspectPermit = function(permitKey) {
    const data = AppState.movementData;
    if (!data || !data.permits) return;
    const allGroups = WorkspaceIndents.groupPermits(data.permits);
    const g = allGroups.find(item => item.key === permitKey || item.permitNumber === permitKey);
    if (!g) return;

    AppState.drawerItem = g;
    AppState.drawerType = 'permit';

    const titleEl = document.getElementById('drawer-title');
    const subEl = document.getElementById('drawer-subtitle');
    const bodyEl = document.getElementById('drawer-body');

    titleEl.innerText = `Indent: ${g.permitNumber || g.indentNumber || 'Transit Pass'}`;
    subEl.innerText = `Challan Date: ${g.challanDate} • Destination: ${g.district || 'Assam'}`;

    bodyEl.innerHTML = `
      <div class="drawer-section">
        <div class="drawer-section-title">Official Pass & Transport Identifiers</div>
        <div class="detail-key-value-grid">
          <div class="kv-item"><span class="kv-key">Permit Number</span><span class="kv-val">${AppUtils.escapeHtml(g.permitNumber || 'Pending')}</span></div>
          <div class="kv-item"><span class="kv-key">Transit Pass #</span><span class="kv-val">${AppUtils.escapeHtml(g.transitPass || 'Pending')}</span></div>
          <div class="kv-item"><span class="kv-key">Indent Number</span><span class="kv-val">${AppUtils.escapeHtml(g.indentNumber || '—')}</span></div>
          <div class="kv-item"><span class="kv-key">Vehicle Number</span><span class="kv-val">${AppUtils.escapeHtml(g.vehicleNumber || '—')}</span></div>
          <div class="kv-item"><span class="kv-key">Licensee Name</span><span class="kv-val">${AppUtils.escapeHtml(g.licenseeName)}</span></div>
          <div class="kv-item"><span class="kv-key">Retailer Code</span><span class="kv-val">${AppUtils.escapeHtml(g.retailerCode || '—')}</span></div>
          <div class="kv-item"><span class="kv-key">Fulfillment Status</span><span class="kv-val">${g.status}</span></div>
          <div class="kv-item"><span class="kv-key">Bond Type</span><span class="kv-val">${g.bondType || 'IMFL'}</span></div>
        </div>
      </div>

      <div style="display:flex;gap:0.5rem;margin-bottom:1.5rem;">
        <button class="action-btn" onclick="AppUtils.copyToClipboard('${AppUtils.escapeHtml(g.permitNumber)}', 'Copied Permit #')">
          Copy Permit #
        </button>
        <button class="action-btn" onclick="AppUtils.copyToClipboard('${AppUtils.escapeHtml(g.vehicleNumber)}', 'Copied Vehicle #')">
          Copy Vehicle #
        </button>
        <button class="action-btn" onclick="window.print();">
          Print Slip
        </button>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Itemised Products (${g.lines.length} SKUs • ${AppUtils.formatNumber(g.totalEqCases)} cs)</div>
        <table class="mini-data-table">
          <thead>
            <tr>
              <th>Product Name</th>
              <th>Pack</th>
              <th style="text-align:right;">Cases</th>
              <th style="text-align:right;">Btls</th>
              <th style="text-align:right;">MRP (₹)</th>
            </tr>
          </thead>
          <tbody>
            ${g.lines.map(l => `
              <tr>
                <td style="font-weight:600;">${AppUtils.escapeHtml(l['Product Name'] || l.ProductName)}</td>
                <td><span class="pack-pill">${AppUtils.escapeHtml(l['Pack Size'] || l.Size)}</span></td>
                <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(l.Cases || 0, 0)}</td>
                <td class="cell-num" style="text-align:right;color:var(--text-muted);">${AppUtils.formatInteger(l.Bottles || 0)}</td>
                <td class="cell-num" style="text-align:right;font-weight:700;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(l['Total MRP'] || l.TotalMRP)}</td>
              </tr>
            `).join('')}
          </tbody>
          <tfoot>
            <tr style="font-weight:700;border-top:1px solid var(--border-strong);">
              <td colspan="2">Total Value</td>
              <td class="cell-num" style="text-align:right;">${AppUtils.formatNumber(g.totalCases, 0)}</td>
              <td class="cell-num" style="text-align:right;">${AppUtils.formatInteger(g.totalBottles)}</td>
              <td class="cell-num" style="text-align:right;color:var(--accent-amber);">${AppUtils.formatCurrencyINR(g.totalMRP)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    `;

    openDrawer(true);
  };

  window.inspectParty = function(partyNameEncoded) {
    const partyName = decodeURIComponent(partyNameEncoded);
    const data = AppState.movementData;
    if (!data || !data.parties_full) return;
    const p = data.parties_full.find(item => item.name === partyName);
    if (!p) return;

    AppState.drawerItem = p;
    AppState.drawerType = 'party';

    const titleEl = document.getElementById('drawer-title');
    const subEl = document.getElementById('drawer-subtitle');
    const bodyEl = document.getElementById('drawer-body');

    titleEl.innerText = p.name;
    subEl.innerText = `District: ${p.district || 'Assam'} • Cadence: ${p.cadence_status.toUpperCase()}`;

    bodyEl.innerHTML = `
      <div class="drawer-section">
        <div class="drawer-section-title">Retailer Account Overview</div>
        <div class="detail-key-value-grid">
          <div class="kv-item"><span class="kv-key">Total Volume Bought</span><span class="kv-val">${AppUtils.formatNumber(p.dispatched_cases)} cs</span></div>
          <div class="kv-item"><span class="kv-key">Total Turnover (MRP)</span><span class="kv-val" style="color:var(--accent-amber);">${AppUtils.formatCurrencyINR(p.mrp)}</span></div>
          <div class="kv-item"><span class="kv-key">Beer Cases</span><span class="kv-val" style="color:var(--brand-beer);">${AppUtils.formatNumber(p.beer_cases)} cs</span></div>
          <div class="kv-item"><span class="kv-key">IMFL Spirits</span><span class="kv-val" style="color:var(--brand-imfl);">${AppUtils.formatNumber(p.imfl_cases)} cs</span></div>
          <div class="kv-item"><span class="kv-key">Country Spirit</span><span class="kv-val" style="color:var(--brand-cs);">${AppUtils.formatNumber(p.cs_cases)} cs</span></div>
          <div class="kv-item"><span class="kv-key">Indents Placed</span><span class="kv-val">${p.indent_count} indents</span></div>
          <div class="kv-item"><span class="kv-key">Last Order Date</span><span class="kv-val">${p.last_order_date || '—'}</span></div>
          <div class="kv-item"><span class="kv-key">Pending in Bond</span><span class="kv-val" style="color:var(--status-warning);">${AppUtils.formatNumber(p.pending_cases)} cs</span></div>
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Top Purchased Brands</div>
        <div class="leaderboard-list">
          ${(p.brands_bought || []).map(b => `
            <div class="leaderboard-item">
              <span class="lb-name" style="font-weight:600;">${AppUtils.escapeHtml(b.name)}</span>
              <span class="lb-cases" style="color:var(--accent-amber);">${AppUtils.formatNumber(b.cases)} cs</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;

    openDrawer(true);
  };

  window.inspectBrand = function(brandNameEncoded) {
    const brandName = decodeURIComponent(brandNameEncoded);
    const data = AppState.movementData;
    if (!data || !data.brands_full) return;
    const b = data.brands_full.find(item => item.name === brandName);
    if (!b) return;

    AppState.drawerItem = b;
    AppState.drawerType = 'brand';

    const titleEl = document.getElementById('drawer-title');
    const subEl = document.getElementById('drawer-subtitle');
    const bodyEl = document.getElementById('drawer-body');

    titleEl.innerText = b.name;
    subEl.innerText = `Category: ${b.category} • Share: ${b.share_pct}% of bond volume`;

    bodyEl.innerHTML = `
      <div class="drawer-section">
        <div class="drawer-section-title">Brand Movement Metrics</div>
        <div class="detail-key-value-grid">
          <div class="kv-item"><span class="kv-key">Dispatched Cases</span><span class="kv-val">${AppUtils.formatNumber(b.dispatched_cases)} cs</span></div>
          <div class="kv-item"><span class="kv-key">Pending Cases</span><span class="kv-val" style="color:var(--status-warning);">${AppUtils.formatNumber(b.pending_cases)} cs</span></div>
          <div class="kv-item"><span class="kv-key">Total MRP</span><span class="kv-val" style="color:var(--accent-amber);">${AppUtils.formatCurrencyINR(b.total_mrp)}</span></div>
          <div class="kv-item"><span class="kv-key">Daily Velocity</span><span class="kv-val">${AppUtils.formatNumber(b.velocity_per_day, 1)} cs/d</span></div>
          <div class="kv-item"><span class="kv-key">Bulk Litres</span><span class="kv-val">${AppUtils.formatNumber(b.bulk_litres, 1)} L</span></div>
          <div class="kv-item"><span class="kv-key">LPL</span><span class="kv-val">${AppUtils.formatNumber(b.lpl, 1)} L</span></div>
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Top Retailers Buying This Brand</div>
        <div class="leaderboard-list">
          ${(b.top_buyers || []).map(byr => `
            <div class="leaderboard-item">
              <span class="lb-name">${AppUtils.escapeHtml(byr.name)}</span>
              <span class="lb-cases">${AppUtils.formatNumber(byr.cases)} cs (${AppUtils.formatCurrencyINR(byr.mrp, true)})</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;

    openDrawer(true);
  };

  window.openDrawer = function(open) {
    const backdrop = document.getElementById('drawer-backdrop');
    const drawer = document.getElementById('slide-drawer');
    if (backdrop && drawer) {
      backdrop.classList.toggle('open', open);
      drawer.classList.toggle('open', open);
    }
  };

  /**
   * Keyboard Shortcuts & Document Click Listeners
   */
  function bindGlobalListeners() {
    // Close export dropdown on click outside
    document.addEventListener('click', (e) => {
      const dropWrap = document.getElementById('export-dropdown-wrapper');
      if (dropWrap && !dropWrap.contains(e.target)) {
        closeExportDropdown();
      }
    });

    window.addEventListener('keydown', (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
        if (e.key === 'Escape') e.target.blur();
        return;
      }

      if (e.key === '[') {
        window.stepPeriod(-1);
      } else if (e.key === ']') {
        window.stepPeriod(1);
      } else if (e.key.toLowerCase() === 'd') {
        window.setHorizonMode('day');
      } else if (e.key.toLowerCase() === 'w') {
        window.setHorizonMode('week');
      } else if (e.key.toLowerCase() === 'm') {
        window.setHorizonMode('month');
      } else if (['1', '2', '3', '4', '5'].includes(e.key)) {
        const mapping = { '1': 'pulse', '2': 'products', '3': 'indents', '4': 'parties', '5': 'godown' };
        window.switchWorkspace(mapping[e.key]);
      } else if (e.key === '/' || (e.metaKey && e.key === 'k')) {
        e.preventDefault();
        const searchInput = document.querySelector('.search-input');
        if (searchInput) searchInput.focus();
      } else if (e.key === 'Escape') {
        window.openDrawer(false);
        window.closePeriodPicker();
        window.closeDateRangeModal();
        window.closeSyncModal();
        window.closeExportDropdown();
      }
    });
  }
})();
