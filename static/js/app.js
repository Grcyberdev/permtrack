/**
 * PermTrack Enterprise — Main Application Coordinator & Event Router
 */
(function() {
  window.addEventListener('DOMContentLoaded', async () => {
    // 1. Initialize Theme
    initTheme();

    // 2. Check Auth Status
    await checkInitialAuth();

    // 3. Bind Keyboard Shortcuts
    bindKeyboardShortcuts();

    // 4. Initial Data Load
    await refreshCurrentHorizon();
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
    AppUtils.showToast(`Switched to ${next === 'dark' ? 'Obsidian & Amber (Dark)' : 'Warm Alabaster (Light)'} theme`, 'info');
  };

  function updateThemeToggleIcon() {
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
      btn.innerHTML = AppState.theme === 'dark' ? '☀️' : '🌙';
      btn.title = `Switch to ${AppState.theme === 'dark' ? 'Light' : 'Dark'} mode`;
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
        <button onclick="handleLogout()" style="margin-left:6px;font-size:0.75rem;color:var(--text-muted);text-decoration:underline;">Logout</button>
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
      AppUtils.showToast('Authentication successful!', 'success');
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
  window.refreshCurrentHorizon = async function(showLoadingToast = true) {
    if (showLoadingToast) {
      // Small status indicator
      const ind = document.getElementById('sync-status-indicator');
      if (ind) ind.innerText = 'Syncing...';
    }

    try {
      const data = await AppAPI.fetchMovementAnalytics(
        AppState.horizonMode,
        AppState.anchorDate,
        AppState.customStartDate,
        AppState.customEndDate
      );

      // Synchronize Header Time-Horizon Bar
      renderHeaderHorizonBar(data.horizon);

      // Render Active Workspace
      renderActiveWorkspace();

      const ind = document.getElementById('sync-status-indicator');
      if (ind) ind.innerText = 'Live (Synced)';
    } catch (e) {
      console.error('Failed to refresh horizon:', e);
      const ind = document.getElementById('sync-status-indicator');
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
      labelEl.innerText = horizon.display_label;
    }
  }

  window.setHorizonMode = function(mode) {
    AppState.horizonMode = mode;
    window.refreshCurrentHorizon();
  };

  window.stepDay = function(direction) {
    const data = AppState.movementData;
    if (!data || !data.horizon) return;
    const avail = AppState.availableDates || [];
    const curKey = data.horizon.start_date_key;

    let targetDateKey = null;
    const curIdx = avail.indexOf(curKey);
    if (curIdx !== -1) {
      const nextIdx = curIdx + direction;
      if (nextIdx >= 0 && nextIdx < avail.length) {
        targetDateKey = avail[nextIdx];
      }
    }

    if (!targetDateKey) {
      // Fallback calculation using Date math
      const dt = new Date(data.horizon.start_date);
      dt.setDate(dt.getDate() + direction);
      targetDateKey = dt.toISOString().slice(0, 10);
    } else {
      targetDateKey = AppUtils.formatDateKeyToInput(targetDateKey);
    }

    AppState.anchorDate = targetDateKey;
    window.refreshCurrentHorizon();
  };

  window.handleDayClick = function(dateKey) {
    AppState.horizonMode = 'day';
    AppState.anchorDate = AppUtils.formatDateKeyToInput(dateKey);
    window.refreshCurrentHorizon();
  };

  window.setCategoryFilter = function(cat) {
    AppState.categoryFilter = cat;
    document.querySelectorAll('.chip-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-cat') === cat);
    });
    renderActiveWorkspace();
  };

  window.switchWorkspace = function(ws) {
    AppState.activeWorkspace = ws;
    syncWorkspaceTabs();
    renderActiveWorkspace();
  };

  window.syncWorkspaceTabs = function() {
    const ws = AppState.activeWorkspace;

    // Desktop Tabs
    document.querySelectorAll('.workspace-tab').forEach(t => {
      t.classList.toggle('active', t.getAttribute('data-ws') === ws);
    });

    // Mobile Bottom Nav Tabs
    document.querySelectorAll('.mobile-nav-item').forEach(m => {
      m.classList.toggle('active', m.getAttribute('data-ws') === ws);
    });

    // Workspace Views
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

    const drawer = document.getElementById('slide-drawer');
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
          📋 Copy Permit #
        </button>
        <button class="action-btn" onclick="AppUtils.copyToClipboard('${AppUtils.escapeHtml(g.vehicleNumber)}', 'Copied Vehicle #')">
          🚚 Copy Vehicle #
        </button>
        <button class="action-btn" onclick="window.print();">
          🖨️ Print Slip
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
            <tr style="font-weight:700;border-top:2px solid var(--border-strong);">
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
   * Keyboard Shortcuts
   */
  function bindKeyboardShortcuts() {
    window.addEventListener('keydown', (e) => {
      // Ignore if inside an input or textarea
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
        if (e.key === 'Escape') e.target.blur();
        return;
      }

      if (e.key === '[') {
        window.stepDay(-1);
      } else if (e.key === ']') {
        window.stepDay(1);
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
      }
    });
  }
})();
