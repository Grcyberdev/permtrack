/**
 * PermTrack Enterprise — Main Application Coordinator & Event Router
 * Minimal, Calm, Executive Precision Architecture
 */
(function() {
  let scraperStatusPollTimer = null;
  let wsReconnectTimer = null;
  let wsReconnectDelay = 2000;
  let lastWsDataRefresh = 0;
  let isWsHistoryReplay = true;

  window.addEventListener('DOMContentLoaded', async () => {
    // 1. Initialize Theme
    initTheme();

    // 2. Bind Global Shortcuts & Document Listeners
    bindGlobalListeners();

    // 3. Check Auth Status (Fix 6: do NOT fetch data or start WS until auth succeeds)
    const isAuthed = await checkInitialAuth();
    if (isAuthed) {
      await refreshCurrentHorizon();
      initScraperWebSocket();
    }
  });

  function initTheme() {
    const savedTheme = localStorage.getItem('permtrack_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    AppState.theme = savedTheme;
    updateThemeColorMeta(savedTheme);
    updateThemeToggleIcon();
  }

  function updateThemeColorMeta(theme) {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', theme === 'dark' ? '#090B10' : '#F8FAFC');
    }
  }

  window.toggleTheme = function() {
    const next = AppState.theme === 'dark' ? 'light' : 'dark';
    AppState.theme = next;
    localStorage.setItem('permtrack_theme', next);
    document.documentElement.setAttribute('data-theme', next);
    updateThemeColorMeta(next);
    updateThemeToggleIcon();
    AppUtils.showToast(`Switched to ${next === 'dark' ? 'Obsidian Reserve (Dark)' : 'Warm Alabaster (Light)'}`, 'info');
  };

  function updateThemeToggleIcon() {
    const btn = document.getElementById('theme-toggle-btn');
    if (!btn) return;
    if (AppState.theme === 'dark') {
      btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
      btn.title = 'Switch to Light Theme';
    } else {
      btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
      btn.title = 'Switch to Dark Theme';
    }
  }

  // Fix 6 & 36: Auth overlay exposure and handling
  window.renderAuthOverlay = function(show) {
    showAuthModal(show);
  };

  async function checkInitialAuth() {
    try {
      const auth = await AppAPI.checkAuthStatus();
      if (!auth.authenticated) {
        showAuthModal(true);
        return false;
      } else {
        updateUserBadge();
        return true;
      }
    } catch (e) {
      showAuthModal(true);
      return false;
    }
  }

  function updateUserBadge() {
    const el = document.getElementById('user-profile-badge');
    if (el && AppState.user) {
      el.innerHTML = `
        <span style="font-weight:600;font-size:0.8rem;color:var(--text-primary);">${AppUtils.escapeHtml(AppState.user.name || AppState.user.username)}</span>
        <button onclick="handleLogout()" style="margin-left:8px;font-size:0.75rem;color:var(--text-muted);text-decoration:underline;background:none;border:none;cursor:pointer;">Logout</button>
      `;
    }
  }

  // Fix 6: Do not trim password; start WS and fetch data only after successful login
  window.handleLoginSubmit = async function(e) {
    if (e) e.preventDefault();
    const u = (document.getElementById('login-username').value || '').trim();
    const p = document.getElementById('login-password').value; // NOT trimmed
    const errEl = document.getElementById('login-error-msg');
    if (errEl) errEl.innerText = '';

    try {
      await AppAPI.login(u, p);
      showAuthModal(false);
      updateUserBadge();
      AppUtils.showToast('Terminal session authorized', 'success');
      await refreshCurrentHorizon();
      initScraperWebSocket();
    } catch (err) {
      if (errEl) errEl.innerText = err.message || 'Login failed';
    }
  };

  // Fix 6: Clear state, DOM and logs on logout
  window.handleLogout = async function() {
    if (AppState.scraperWs) {
      try { AppState.scraperWs.close(); } catch (e) {}
      AppState.scraperWs = null;
    }
    clearTimeout(wsReconnectTimer);
    try {
      await AppAPI.logout();
    } catch (e) {}
    AppState.movementData = null;
    AppState.scraperLogs = [];
    document.querySelectorAll('.workspace-view').forEach(v => v.innerHTML = '');
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
    if (!AppState.isAuthenticated) return;

    const ind = document.getElementById('sync-status-indicator');
    if (ind) ind.innerText = 'Syncing...';

    try {
      const data = await AppAPI.fetchMovementAnalytics(
        AppState.horizonMode,
        AppState.anchorDate,
        AppState.customStartDate,
        AppState.customEndDate
      );

      if (data.horizon && data.horizon.available_dates) {
        AppState.availableDates = data.horizon.available_dates;
      }

      // Synchronize Header Time-Horizon Bar & Bounds
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

    // Fix 17: Stepping bounds & disable buttons at bounds
    const avail = AppState.availableDates || [];
    const mode = AppState.horizonMode;
    let canStepBack = true;
    let canStepForward = true;

    if (avail.length > 0) {
      const earliestKey = avail[0];
      const latestKey = avail[avail.length - 1];

      if (mode === 'day') {
        const curKey = horizon.start_date_key;
        const curIdx = avail.indexOf(curKey);
        if (curIdx <= 0) canStepBack = false;
        if (curIdx >= avail.length - 1 || curIdx === -1) canStepForward = false;
      } else if (mode === 'month') {
        const curYM = horizon.start_date ? horizon.start_date.slice(0, 7).replace('-', '') : '';
        const earliestYM = earliestKey.slice(0, 6);
        const latestYM = latestKey.slice(0, 6);
        if (curYM <= earliestYM) canStepBack = false;
        if (curYM >= latestYM) canStepForward = false;
      }
    }

    const btnBack = document.getElementById('stepper-btn-back');
    const btnForward = document.getElementById('stepper-btn-forward');
    if (btnBack) btnBack.disabled = !canStepBack;
    if (btnForward) btnForward.disabled = !canStepForward;

    // Fix 8: Update PDF menu item label
    updatePdfExportLabel(horizon);
  }

  // Fix 8: "Download Daily PDF (DD-Mon-YYYY)"
  function updatePdfExportLabel(horizon) {
    const pdfLabel = document.getElementById('export-pdf-label');
    if (!pdfLabel) return;

    const avail = horizon.available_dates || AppState.availableDates || [];
    let targetKey = horizon.start_date_key;
    if (AppState.horizonMode === 'day') {
      targetKey = horizon.start_date_key || horizon.end_date_key;
    } else {
      const eligible = avail.filter(k => k <= horizon.end_date_key).sort();
      targetKey = eligible.length > 0 ? eligible[eligible.length - 1] : horizon.end_date_key;
    }
    const displayDate = AppUtils.formatDateKeyToDisplay(targetKey);
    pdfLabel.innerText = `Download Daily PDF (${displayDate})`;
  }

  window.setHorizonMode = function(mode) {
    AppState.horizonMode = mode;
    if (mode === 'day') {
      AppState.anchorDate = null;
    }
    window.refreshCurrentHorizon();
  };

  /**
   * Smart Period Stepping (Fix 17: Clamped bounds, walk available_dates only for day, range shift by span+1)
   */
  window.stepPeriod = function(direction) {
    const data = AppState.movementData;
    if (!data || !data.horizon) return;
    const h = data.horizon;
    const mode = AppState.horizonMode;
    const avail = AppState.availableDates || [];

    if (avail.length === 0) return;

    if (mode === 'day') {
      const curKey = h.start_date_key;
      const curIdx = avail.indexOf(curKey);
      if (curIdx === -1) {
        if (direction < 0) {
          AppState.anchorDate = AppUtils.formatDateKeyToInput(avail[avail.length - 1]);
        }
      } else {
        const nextIdx = curIdx + direction;
        if (nextIdx >= 0 && nextIdx < avail.length) {
          AppState.anchorDate = AppUtils.formatDateKeyToInput(avail[nextIdx]);
        } else {
          return; // Clamped at bound
        }
      }
      window.refreshCurrentHorizon();
    } else if (mode === 'week') {
      const baseStr = AppState.anchorDate || h.end_date || h.start_date;
      const dt = new Date(baseStr);
      dt.setDate(dt.getDate() + (direction * 7));
      const targetStr = dt.toISOString().slice(0, 10);
      const targetKey = targetStr.replace(/-/g, '');
      const earliestKey = avail[0];
      const latestKey = avail[avail.length - 1];

      if (targetKey < earliestKey && direction < 0) return;
      if (targetKey > latestKey && direction > 0) return;

      AppState.anchorDate = targetStr;
      window.refreshCurrentHorizon();
    } else if (mode === 'month') {
      const baseStr = AppState.anchorDate || h.start_date;
      const dt = new Date(baseStr);
      dt.setDate(1);
      dt.setMonth(dt.getMonth() + direction);
      const targetStr = dt.toISOString().slice(0, 10);
      const targetYM = targetStr.slice(0, 7).replace('-', '');
      const earliestYM = avail[0].slice(0, 6);
      const latestYM = avail[avail.length - 1].slice(0, 6);

      if (targetYM < earliestYM && direction < 0) return;
      if (targetYM > latestYM && direction > 0) return;

      AppState.anchorDate = targetStr;
      window.refreshCurrentHorizon();
    } else if (mode === 'range') {
      if (h.start_date && h.end_date) {
        const dt1 = new Date(h.start_date);
        const dt2 = new Date(h.end_date);
        const span = Math.max(1, Math.round((dt2 - dt1) / (1000 * 60 * 60 * 24))) + 1;
        const shiftDays = span * direction;
        dt1.setDate(dt1.getDate() + shiftDays);
        dt2.setDate(dt2.getDate() + shiftDays);
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
   * Intuitive Period Picker Popover (Fix 18: dynamic month list; Fix 19: rename button)
   */
  window.openPeriodPicker = function() {
    const modal = document.getElementById('period-picker-modal');
    const body = document.getElementById('period-picker-body');
    if (!modal || !body) return;

    const mode = AppState.horizonMode;
    const avail = AppState.availableDates || [];
    const curDateKey = (AppState.movementData && AppState.movementData.horizon) ? AppState.movementData.horizon.start_date_key : '';
    const latestDateKey = avail.length > 0 ? avail[avail.length - 1] : '';

    if (mode === 'day') {
      const recentDates = avail.slice(-6).reverse();
      const latestLabel = latestDateKey ? `Latest (${AppUtils.formatDateKeyToDisplay(latestDateKey)})` : 'Latest Date';

      body.innerHTML = `
        <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:1rem;">Select an operating day to inspect:</div>
        
        <div style="margin-bottom:1rem;">
          <label style="font-size:0.75rem;text-transform:uppercase;color:var(--text-muted);font-weight:600;display:block;margin-bottom:4px;">Direct Date</label>
          <input type="date" id="single-date-picker-input" class="search-input" value="${AppUtils.formatDateKeyToInput(curDateKey)}" />
        </div>

        <div style="margin-bottom:1.25rem;">
          <div style="font-size:0.75rem;text-transform:uppercase;color:var(--text-muted);font-weight:600;margin-bottom:6px;">Available Operating Dates</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;">
            <button class="action-btn" style="padding:4px 8px;font-size:0.775rem;background:var(--accent-amber-glow);color:var(--accent-amber);" onclick="setSpecificDate(null)">
              ${AppUtils.escapeHtml(latestLabel)}
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
      // Fix 18: Build dynamic month list from available_dates
      const monthMap = {};
      const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

      avail.forEach(dk => {
        const ym = `${dk.slice(0, 4)}-${dk.slice(4, 6)}`;
        if (!monthMap[ym]) {
          const mIdx = parseInt(dk.slice(4, 6), 10) - 1;
          const y = dk.slice(0, 4);
          monthMap[ym] = {
            key: `${ym}-01`,
            label: `${monthNames[mIdx]} ${y}`,
            count: 0
          };
        }
        monthMap[ym].count++;
      });

      const months = Object.keys(monthMap).sort().reverse().map(k => monthMap[k]);

      body.innerHTML = `
        <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:1rem;">Select a monthly cycle:</div>
        <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:1.25rem;">
          ${months.map(m => `
            <button class="action-btn" style="justify-content:space-between;padding:8px 12px;font-size:0.85rem;" onclick="setSpecificMonth('${m.key}')">
              <span style="font-weight:600;">${m.label}</span>
              <span style="font-size:0.75rem;color:var(--text-muted);">${m.count} operating days</span>
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
   * Scraper Live Sync Modal, Polling & WebSocket (Fix 7, 20, 32, 33)
   */
  window.openSyncModal = function() {
    const modal = document.getElementById('sync-modal');
    if (modal) {
      modal.classList.add('open');
      updateModalLogs();
      pollScraperJobStatus();
      if (!scraperStatusPollTimer) {
        scraperStatusPollTimer = setInterval(pollScraperJobStatus, 3000);
      }
    }
  };

  window.closeSyncModal = function() {
    const modal = document.getElementById('sync-modal');
    if (modal) modal.classList.remove('open');
    if (scraperStatusPollTimer) {
      clearInterval(scraperStatusPollTimer);
      scraperStatusPollTimer = null;
    }
  };

  async function pollScraperJobStatus() {
    try {
      const status = await AppAPI.getScraperStatus();
      updateSyncModalStatusUI(status);
    } catch (e) {}
  }

  function updateSyncModalStatusUI(st) {
    if (!st) return;
    const dot = document.getElementById('sync-job-dot');
    const stageEl = document.getElementById('sync-job-stage');
    const detailsEl = document.getElementById('sync-job-details');
    const prgEl = document.getElementById('sync-job-progress');
    const cancelBtn = document.getElementById('sync-cancel-btn');

    const isRunning = Boolean(st.is_running || st.status === 'running');
    const isFailed = st.status === 'failed' || st.success === false;

    if (dot) {
      dot.className = `sync-dot ${isRunning ? 'live' : (isFailed ? 'error' : 'idle')}`;
    }
    if (stageEl) {
      stageEl.innerText = isRunning ? (st.stage || 'Scraping in progress...') : (st.error || isFailed ? 'Error / Failed' : (st.status || 'Idle'));
    }
    if (detailsEl) {
      const elapsed = st.elapsed_seconds ? `${Math.round(st.elapsed_seconds)}s elapsed` : '';
      const targetDate = st.date || st.target_date;
      const dateTarget = targetDate ? `Target: ${targetDate}` : '';
      detailsEl.innerText = [dateTarget, elapsed].filter(Boolean).join(' • ') || 'Standby';
    }
    if (prgEl) {
      const pct = (st.progress !== undefined) ? st.progress : (st.progress_percent || 0);
      prgEl.innerText = isRunning ? `${pct}%` : '';
    }
    if (cancelBtn) {
      cancelBtn.style.display = isRunning ? 'inline-flex' : 'none';
    }
  }

  window.cancelSyncJob = async function() {
    if (!confirm('Cancel the active scraper job?')) return;
    try {
      await AppAPI.cancelScraper();
      AppUtils.showToast('Scraper job cancelled', 'info');
      pollScraperJobStatus();
    } catch (e) {
      AppUtils.showToast('Failed to cancel job: ' + e.message, 'danger');
    }
  };

  window.triggerSyncNowFromModal = async function() {
    try {
      AppUtils.showToast('Triggering background scraper sync...', 'info');
      await AppAPI.triggerScraper();
      appendScraperLog('🚀 Scraper job triggered from executive console.\n');
      pollScraperJobStatus();
    } catch (e) {
      AppUtils.showToast('Failed to trigger sync: ' + e.message, 'danger');
    }
  };

  // Fix 7: Call triggerScraper(dateStr, 'BOTH', 7) with normalized DD-MM-YYYY
  window.triggerBackfillFromInput = async function() {
    const inp = document.getElementById('sync-backfill-date-input');
    if (!inp || !inp.value) {
      AppUtils.showToast('Please select a date for backfill', 'warning');
      return;
    }

    // Convert YYYY-MM-DD input value to DD-MM-YYYY format
    const parts = inp.value.split('-');
    if (parts.length !== 3) {
      AppUtils.showToast('Invalid date format', 'warning');
      return;
    }
    const dateFormatted = `${parts[2]}-${parts[1]}-${parts[0]}`;

    try {
      AppUtils.showToast(`Dispatching scraper backfill for ${dateFormatted}...`, 'info');
      await AppAPI.triggerScraper(dateFormatted, 'BOTH', 7);
      appendScraperLog(`🚀 Cloud backfill dispatched for ${dateFormatted}.\n`);
      pollScraperJobStatus();
    } catch (e) {
      AppUtils.showToast('Failed to dispatch backfill: ' + e.message, 'danger');
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

  // Fix 20: Split incoming lines before storing to avoid doubled blank lines
  function appendScraperLog(rawChunk) {
    if (!rawChunk) return;
    const lines = String(rawChunk).split('\n');
    lines.forEach(l => {
      const trimmed = l.trimEnd();
      if (trimmed || AppState.scraperLogs[AppState.scraperLogs.length - 1] !== '') {
        AppState.scraperLogs.push(trimmed);
      }
    });
    if (AppState.scraperLogs.length > 500) {
      AppState.scraperLogs = AppState.scraperLogs.slice(-500);
    }
    updateModalLogs();
  }

  // Fix 20 & 33: WebSocket auth-first, exponential backoff (max 60s), stop on 1008, debounce refresh
  function initScraperWebSocket() {
    if (!AppState.isAuthenticated) return;

    try {
      const loc = window.location;
      const wsProto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProto}//${loc.host}/ws/run`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        AppState.scraperWs = ws;
        wsReconnectDelay = 2000;
        isWsHistoryReplay = true;
      };

      ws.onmessage = (event) => {
        const text = event.data || '';
        appendScraperLog(text);

        // Ignore replay of past history
        if (isWsHistoryReplay) {
          isWsHistoryReplay = false;
          return;
        }

        // Trigger refresh only on exact server completion markers, debounced to >= 10s
        const isCompletion = text.includes('SUCCESS: Permit scraping') || text.includes('Webhook received & saved');
        if (isCompletion) {
          const now = Date.now();
          if (now - lastWsDataRefresh > 10000) {
            lastWsDataRefresh = now;
            window.refreshCurrentHorizon(false);
          }
        }
      };

      ws.onerror = () => {};

      ws.onclose = (event) => {
        AppState.scraperWs = null;
        // Stop retrying if unauthorized (1008) or logged out
        if (event.code === 1008 || !AppState.isAuthenticated) {
          return;
        }
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = setTimeout(() => {
          wsReconnectDelay = Math.min(60000, wsReconnectDelay * 1.5);
          initScraperWebSocket();
        }, wsReconnectDelay);
      };
    } catch (e) {}
  }

  /**
   * Category Filter Handler (Fix 12: Updates active state across tabs & overview)
   */
  window.setCategoryFilter = function(cat) {
    AppState.categoryFilter = cat;
    document.querySelectorAll('.category-chips .chip-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-cat') === cat);
    });
    document.querySelectorAll('.cat-interactive-card').forEach(b => {
      b.classList.toggle('active-filter', b.getAttribute('data-cat') === cat);
    });
    renderActiveWorkspace();
  };

  /**
   * Workspace Switcher (Fix 31: Day mode switch to month when opening Godown)
   */
  window.switchWorkspace = async function(ws) {
    AppState.activeWorkspace = ws;
    syncWorkspaceTabs();

    if (ws === 'godown' && AppState.horizonMode === 'day') {
      const dayDateKey = (AppState.movementData && AppState.movementData.horizon)
        ? AppState.movementData.horizon.start_date_key
        : AppState.anchorDate;
      AppState._godownMonthSwitchedFromDay = dayDateKey;
      AppState.horizonMode = 'month';
      AppState.anchorDate = dayDateKey ? AppUtils.formatDateKeyToInput(dayDateKey) : null;
      await window.refreshCurrentHorizon();
    }

    renderActiveWorkspace();
  };

  window.syncWorkspaceTabs = function() {
    const ws = AppState.activeWorkspace;

    document.querySelectorAll('.desktop-workspace-nav .nav-tab-btn').forEach(t => {
      t.classList.toggle('active', t.getAttribute('data-ws') === ws);
    });

    document.querySelectorAll('.mobile-bottom-nav .mobile-nav-item').forEach(m => {
      m.classList.toggle('active', m.getAttribute('data-ws') === ws);
    });

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

    titleEl.innerText = g.retailerName || g.licenseeName;
    subEl.innerText = `Challan: ${g.challanDate} • Transit Pass: ${g.transitPass || 'Pending'}`;

    bodyEl.innerHTML = `
      <div class="drawer-section">
        <div class="drawer-section-title">Official Pass & Transport Identifiers</div>
        <div class="detail-key-value-grid">
          <div class="kv-item"><span class="kv-key">Transit Pass #</span><span class="kv-val">${AppUtils.escapeHtml(g.transitPass || 'Pending')}</span></div>
          <div class="kv-item"><span class="kv-key">Permit Number</span><span class="kv-val">${AppUtils.escapeHtml(g.permitNumber || '—')}</span></div>
          <div class="kv-item"><span class="kv-key">Licensee Name</span><span class="kv-val">${AppUtils.escapeHtml(g.licenseeName)}</span></div>
          <div class="kv-item"><span class="kv-key">Retailer Code</span><span class="kv-val">${AppUtils.escapeHtml(g.retailerCode || '—')}</span></div>
          <div class="kv-item"><span class="kv-key">Destination District</span><span class="kv-val">${AppUtils.escapeHtml(g.district || 'Assam')}</span></div>
          <div class="kv-item"><span class="kv-key">Vehicle Number</span><span class="kv-val">${AppUtils.escapeHtml(g.vehicleNumber || '—')}</span></div>
          <div class="kv-item"><span class="kv-key">Fulfillment Status</span><span class="kv-val">${g.status}</span></div>
          <div class="kv-item"><span class="kv-key">Bond Type</span><span class="kv-val">${g.bondType || 'IMFL'}</span></div>
        </div>
      </div>

      <div style="display:flex;gap:0.5rem;margin-bottom:1.5rem;">
        <button class="action-btn" onclick="AppUtils.copyToClipboard('${AppUtils.escapeHtml(g.transitPass || g.permitNumber)}', 'Copied Pass #')">
          Copy Pass #
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

  // Fix 5: Accepts decoded partyName directly
  window.inspectParty = function(partyName) {
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
          <div class="kv-item"><span class="kv-key">Active Order Days (30D)</span><span class="kv-val">${p.active_days} days</span></div>
          <div class="kv-item"><span class="kv-key">Last Order Date</span><span class="kv-val">${p.last_order_date || '—'}</span></div>
          <div class="kv-item"><span class="kv-key">Pending in Bond</span><span class="kv-val" style="color:var(--status-warning);">${AppUtils.formatNumber(p.pending_cases)} cs</span></div>
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Top Purchased Brands</div>
        <div class="leaderboard-list">
          ${(p.brands_bought || []).map(b => `
            <div class="leaderboard-item" style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-hairline);">
              <span class="lb-name" style="font-weight:600;">${AppUtils.escapeHtml(b.name)}</span>
              <span class="lb-cases" style="color:var(--accent-amber);">${AppUtils.formatNumber(b.cases)} cs</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;

    openDrawer(true);
  };

  // Fix 5: Accepts decoded brandName directly
  window.inspectBrand = function(brandName) {
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
            <div class="leaderboard-item" style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-hairline);">
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

  window.closeAllDrawers = function() {
    window.openDrawer(false);
  };

  // Helper to focus active search input (Fix 29)
  function focusActiveSearch() {
    const ws = AppState.activeWorkspace;
    const view = document.getElementById(`workspace-${ws}-content`);
    if (view) {
      const input = view.querySelector('.search-input');
      if (input) {
        input.focus();
        input.select();
      }
    }
  }

  /**
   * Keyboard Shortcuts & Document Click Listeners (Fix 29)
   */
  function bindGlobalListeners() {
    document.addEventListener('click', (e) => {
      const dropWrap = document.getElementById('export-dropdown-wrapper');
      if (dropWrap && !dropWrap.contains(e.target)) {
        closeExportDropdown();
      }
    });

    window.addEventListener('keydown', (e) => {
      // 1. Allow ⌘K or Ctrl+K anytime to focus active search
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        focusActiveSearch();
        return;
      }

      // If user is currently typing in an input, textarea, or select, do not trigger single-key shortcuts
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
        if (e.key === 'Escape') e.target.blur();
        return;
      }

      // 2. Ignore single-key shortcuts if meta, ctrl, or alt is pressed
      if (e.metaKey || e.ctrlKey || e.altKey) {
        return;
      }

      if (e.key === '/') {
        e.preventDefault();
        focusActiveSearch();
      } else if (e.key === '[') {
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
