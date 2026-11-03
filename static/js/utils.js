/**
 * PermTrack Enterprise — Utilities & Mathematical Core
 * STRICT PRESERVATION OF ZERO-MUTATION FORMULAS
 */
const AppUtils = {
  /**
   * Bottle-to-case conversion strictly preserving existing thresholds:
   * 1. Slash notation (e.g. "200/24" -> 24)
   * 2. ml volume: >=600 -> 12, >=200 -> 24, >=180 -> 48, <180 -> 96
   */
  getBottlesPerCase(sizeVal, packSize) {
    const raw = String(packSize || sizeVal || '').trim();
    if (raw.includes('/')) {
      const parts = raw.split('/');
      const denom = parseInt(parts[1], 10);
      if (!isNaN(denom) && denom > 0) return denom;
    }
    const numMatch = raw.match(/\d+/);
    if (!numMatch) return 12;
    const ml = parseInt(numMatch[0], 10);
    if (ml >= 600) return 12;
    if (ml >= 200) return 24;
    if (ml >= 180) return 48;
    return 96;
  },

  /**
   * Canonical Category Classification
   */
  getProductCategory(item) {
    const b = String(item['Bond Type'] || '').toUpperCase();
    const c = String(item['Category'] || '').toUpperCase();
    const p = String(item['Product Name'] || '').toUpperCase();

    if (b === 'CS' || c.includes('COUNTRY') || p.includes('MASTI') || p.includes('CS ')) {
      return 'CS';
    }
    const beerKeywords = [
      'BEER', 'DRAUGHT', 'LAGER', 'ALE', 'STOUT', 'PILSNER', 'CIDER', 'WHEAT',
      'BIRA', 'KINGFISHER', 'TUBORG', 'CARLSBERG', 'BUDWEISER', 'HE-MAN',
      'GODFATHER', 'SIMBA', 'CORONA', 'HEINEKEN', 'FOSTERS', 'BREEZER',
      'BACARDI BREEZER', 'HAYWARDS 5000', 'KNOCK OUT', 'KALYANI', 'BLACK FORT',
      'ROYAL CHALLENGE BEER', 'STERREN', 'HUNTER', 'BROCODE', 'WHITE RHINO',
      'LONE WOLF', 'SIX FIELDS', 'MACH 11', 'HOEGAARDEN', 'STELLA', 'MILLER',
      'SUPER STRONG BEER', 'PREMIUM LAGER'
    ];
    if (beerKeywords.some(k => c.includes(k) || p.includes(k))) {
      return 'BEER';
    }
    return 'IMFL';
  },

  formatNumber(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return '0.00';
    return Number(val).toLocaleString('en-IN', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
  },

  formatInteger(val) {
    if (val === null || val === undefined || isNaN(val)) return '0';
    return Number(val).toLocaleString('en-IN', {
      maximumFractionDigits: 0
    });
  },

  formatCurrencyINR(val, compact = false) {
    if (val === null || val === undefined || isNaN(val)) return '₹0';
    const num = Number(val);
    if (compact) {
      if (Math.abs(num) >= 10000000) {
        return `₹${(num / 10000000).toFixed(2)} Cr`;
      }
      if (Math.abs(num) >= 100000) {
        return `₹${(num / 100000).toFixed(2)} L`;
      }
    }
    return `₹${num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  },

  formatDateKeyToDisplay(dateKey) {
    if (!dateKey || String(dateKey).length !== 8) return dateKey || '';
    const s = String(dateKey);
    const y = s.slice(0, 4);
    const m = parseInt(s.slice(4, 6), 10) - 1;
    const d = s.slice(6, 8);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${d}-${months[m] || 'Unknown'}-${y}`;
  },

  formatDateKeyToInput(dateKey) {
    if (!dateKey || String(dateKey).length !== 8) return '';
    const s = String(dateKey);
    return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  },

  parseDateToKey(dateStr) {
    if (!dateStr) return '';
    return dateStr.replace(/[^0-9]/g, '');
  },

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },

  showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = type === 'success' ? '✓' : (type === 'warning' ? '⚠️' : '❌');
    toast.innerHTML = `<span>${icon}</span><span>${this.escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      toast.style.transition = 'all 0.2s ease';
      setTimeout(() => toast.remove(), 250);
    }, 3200);
  },

  async copyToClipboard(text, successMsg = 'Copied to clipboard!') {
    try {
      await navigator.clipboard.writeText(text);
      this.showToast(successMsg, 'success');
      return true;
    } catch (e) {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      this.showToast(successMsg, 'success');
      return true;
    }
  }
};

window.AppUtils = AppUtils;
