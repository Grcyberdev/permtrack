/**
 * PermTrack Enterprise — API Communication Layer
 */
const AppAPI = {
  async fetchWithAuth(url, options = {}) {
    const defaultHeaders = {
      'Accept': 'application/json',
      'Content-Type': 'application/json'
    };
    options.headers = { ...defaultHeaders, ...options.headers };
    options.credentials = 'include'; // Ensure cookies sent

    try {
      const response = await fetch(url, options);
      if (response.status === 401) {
        AppState.isAuthenticated = false;
        AppState.user = null;
        if (typeof window.renderAuthOverlay === 'function') {
          window.renderAuthOverlay(true);
        }
        throw new Error('Authentication required');
      }
      return response;
    } catch (err) {
      console.error(`API Request failed: ${url}`, err);
      throw err;
    }
  },

  async checkAuthStatus() {
    try {
      const resp = await this.fetchWithAuth('/api/auth/status');
      if (resp.ok) {
        const data = await resp.json();
        AppState.isAuthenticated = data.authenticated;
        AppState.user = data.user;
        return data;
      }
    } catch (e) {
      AppState.isAuthenticated = false;
    }
    return { authenticated: false };
  },

  async login(username, password) {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password })
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.error || 'Login failed');
    }
    AppState.isAuthenticated = true;
    AppState.user = data.user;
    return data;
  },

  async logout() {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    } finally {
      AppState.isAuthenticated = false;
      AppState.user = null;
      if (typeof window.renderAuthOverlay === 'function') {
        window.renderAuthOverlay(true);
      }
    }
  },

  async fetchMovementAnalytics(mode = 'day', date = null, startDate = null, endDate = null) {
    AppState.isLoadingMovement = true;
    const params = new URLSearchParams();
    params.set('mode', mode);
    if (date) params.set('date', date);
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);

    try {
      const resp = await this.fetchWithAuth(`/api/analytics/movement?${params.toString()}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      AppState.movementData = data;
      if (data.horizon && data.horizon.available_dates) {
        AppState.availableDates = data.horizon.available_dates;
      }
      return data;
    } finally {
      AppState.isLoadingMovement = false;
    }
  },

  async fetchGodownReconciliation(dateKey = null) {
    const url = dateKey
      ? `/api/godown/reconciliation?date_key=${encodeURIComponent(dateKey)}`
      : '/api/godown/reconciliation';
    const resp = await this.fetchWithAuth(url);
    if (!resp.ok) throw new Error(`Failed to load godown reconciliation`);
    return await resp.json();
  },

  async saveGodownReconciliation(dateKey, godownCases) {
    const resp = await this.fetchWithAuth('/api/godown/reconciliation', {
      method: 'POST',
      body: JSON.stringify({
        date_key: dateKey,
        godown_cases: godownCases
      })
    });
    if (!resp.ok) throw new Error('Failed to save godown count');
    return await resp.json();
  },

  async triggerScraper(dateStr, bond = 'BOTH', lookback = 7) {
    const resp = await this.fetchWithAuth('/api/scraper/start', {
      method: 'POST',
      body: JSON.stringify({
        date: dateStr,
        bond: bond,
        lookback_days: lookback
      })
    });
    return await resp.json();
  },

  async getScraperStatus() {
    const resp = await this.fetchWithAuth('/api/scraper/status');
    return await resp.json();
  },

  async fetchBackupsList() {
    const resp = await this.fetchWithAuth('/api/backups');
    return await resp.json();
  }
};

window.AppAPI = AppAPI;
