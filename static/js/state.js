/**
 * PermTrack Enterprise — Global Reactive State
 */
const AppState = {
  // Authentication
  user: null,
  isAuthenticated: false,

  // Global Time Horizon: 'day' | 'week' | 'month' | 'range'
  horizonMode: 'day',
  anchorDate: null,       // 'YYYY-MM-DD'
  customStartDate: null,  // 'YYYY-MM-DD'
  customEndDate: null,    // 'YYYY-MM-DD'
  availableDates: [],     // Array of 'YYYYMMDD' strings

  // Category Filter: 'ALL' | 'BEER' | 'IMFL' | 'CS'
  categoryFilter: 'ALL',

  // Active Workspace: 'pulse' | 'products' | 'indents' | 'parties' | 'godown'
  activeWorkspace: 'pulse',

  // Current Theme: 'dark' | 'light'
  theme: localStorage.getItem('permtrack_theme') || 'dark',

  // Loaded Movement Data for Current Horizon
  movementData: null,
  isLoadingMovement: false,

  // Sub-view selectors
  productSubView: 'brands', // 'brands' | 'packs' | 'picklist'
  indentStatusTab: 'ALL',   // 'ALL' | 'PENDING' | 'DISPATCHED' | 'FULFILLED'
  indentSearchQuery: '',
  productSearchQuery: '',
  partySearchQuery: '',

  // Active Inspect Drawer
  drawerItem: null,
  drawerType: null, // 'permit' | 'party' | 'brand'

  // Godown Edit state
  godownReconMap: {}, // normalized 'YYYYMMDD' -> { godown_cases, updated_at, updated_by }

  // Scraper WebSocket & Logs
  scraperWs: null,
  scraperLogs: [],
  isScraperRunning: false
};

window.AppState = AppState;
