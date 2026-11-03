/**
 * PermTrack Enterprise — Export Studio & QoL Utilities
 * Multi-Tab Excel (.xlsx), WhatsApp / Telegram Digest & PDF
 */
const AppExports = {
  /**
   * 1-Click WhatsApp / Telegram Executive Digest
   */
  generateWhatsAppDigest() {
    const data = AppState.movementData;
    if (!data) {
      AppUtils.showToast('No active period data loaded', 'warning');
      return;
    }

    const s = data.summary || {};
    const h = data.horizon || {};
    const cat = data.category_breakdown || {};
    const beer = cat.BEER || {};
    const imfl = cat.IMFL || {};
    const cs = cat.CS || {};
    const prev = data.previous_period_summary || {};
    const topBrands = (data.brands_full || []).slice(0, 5);

    const deltaSign = prev.delta_cases_pct >= 0 ? '+' : '';
    const deltaStr = prev.delta_cases_pct ? ` (${deltaSign}${prev.delta_cases_pct}% vs ${h.prev_display_label})` : '';

    let text = `🏛️ *BORGOHAIN ENTERPRISES — EXCISE DISPATCH DIGEST*\n`;
    text += `📅 *Period:* ${h.display_label}\n\n`;

    text += `📦 *TOTAL DISPATCH:* *${AppUtils.formatNumber(s.total_cases)} Cases* (${AppUtils.formatCurrencyINR(s.total_mrp, true)})\n`;
    text += `📈 *Velocity:* ${AppUtils.formatNumber(s.cases_per_day, 1)} cs/day${deltaStr}\n`;
    text += `🏢 *Active Licensees:* ${s.active_parties_count} | *Dispatches:* ${s.permits_count}\n\n`;

    text += `*Category Breakdown:*\n`;
    text += `🍺 *Beer:* ${AppUtils.formatNumber(beer.cases)} cs (${beer.share_pct || 0}%) • ${AppUtils.formatCurrencyINR(beer.mrp, true)}\n`;
    text += `🥃 *IMFL:* ${AppUtils.formatNumber(imfl.cases)} cs (${imfl.share_pct || 0}%) • ${AppUtils.formatCurrencyINR(imfl.mrp, true)}\n`;
    text += `🍶 *CS:* ${AppUtils.formatNumber(cs.cases)} cs (${cs.share_pct || 0}%) • ${AppUtils.formatCurrencyINR(cs.mrp, true)}\n\n`;

    if (s.pending_permits_count > 0) {
      text += `⏳ *Active Pending in Bond:* ${s.pending_permits_count} Indents (${AppUtils.formatNumber(s.pending_cases)} cs • ${AppUtils.formatCurrencyINR(s.pending_mrp, true)})\n\n`;
    }

    if (s.godown_cases !== null && s.godown_cases !== undefined) {
      const varSign = s.difference >= 0 ? '+' : '';
      text += `⚖️ *Godown Audit:* Physical: ${AppUtils.formatNumber(s.godown_cases)} cs | Variance: *${varSign}${AppUtils.formatNumber(s.difference)} cs*\n\n`;
    }

    text += `🔥 *Top 5 Moving Brands:*\n`;
    topBrands.forEach((b, i) => {
      text += `${i + 1}. ${b.name}: *${AppUtils.formatNumber(b.dispatched_cases)} cs* (${AppUtils.formatCurrencyINR(b.total_mrp, true)})\n`;
    });

    text += `\n_Generated via PermTrack Enterprise Revenue Terminal_`;

    AppUtils.copyToClipboard(text, '📲 WhatsApp digest copied to clipboard!');
  },

  /**
   * Multi-Tab Excel Workbook Export using SheetJS
   */
  exportMultiSheetExcel() {
    const data = AppState.movementData;
    if (!data) {
      AppUtils.showToast('No active data loaded to export', 'warning');
      return;
    }

    if (typeof XLSX === 'undefined') {
      AppUtils.showToast('SheetJS library is still loading, please retry in 2 seconds...', 'warning');
      return;
    }

    const wb = XLSX.utils.book_new();
    const h = data.horizon || {};
    const s = data.summary || {};
    const cat = data.category_breakdown || {};

    // Tab 1: 1_Summary
    const summaryRows = [
      ["BORGOHAIN ENTERPRISES PRIVATE LIMITED - ASSAM EXCISE TERMINAL"],
      ["Time Horizon", h.display_label || ""],
      ["Start Date", h.start_date || ""],
      ["End Date", h.end_date || ""],
      [],
      ["Metric", "Value", "Unit"],
      ["Total Dispatched Equivalent Cases", s.total_cases || 0, "Cases"],
      ["Physical Dispatched Cases", s.cases_only || 0, "Cases"],
      ["Loose Bottles Dispatched", s.bottles_only || 0, "Bottles"],
      ["Total Bond Revenue (MRP)", s.total_mrp || 0, "INR"],
      ["Average Case Realization", s.avg_case_price || 0, "INR / Case"],
      ["Operating Days", s.active_days || 0, "Days"],
      ["Daily Sales Velocity", s.cases_per_day || 0, "Cases / Day"],
      ["Active Ordering Retailers", s.active_parties_count || 0, "Retailers"],
      ["Total Dispatches / Permits", s.permits_count || 0, "Permits"],
      [],
      ["Category", "Dispatched Cases", "Volume Share (%)", "Total MRP (INR)", "Bulk Litres (BL)", "LPL"],
      ["BEER", cat.BEER?.cases || 0, cat.BEER?.share_pct || 0, cat.BEER?.mrp || 0, cat.BEER?.bulk_litres || 0, cat.BEER?.lpl || 0],
      ["IMFL", cat.IMFL?.cases || 0, cat.IMFL?.share_pct || 0, cat.IMFL?.mrp || 0, cat.IMFL?.bulk_litres || 0, cat.IMFL?.lpl || 0],
      ["CS", cat.CS?.cases || 0, cat.CS?.share_pct || 0, cat.CS?.mrp || 0, cat.CS?.bulk_litres || 0, cat.CS?.lpl || 0],
      [],
      ["Pending Indents in Bond", s.pending_permits_count || 0, "Indents"],
      ["Pending Volume Required", s.pending_cases || 0, "Cases"],
      ["Physical Godown Cases", s.godown_cases !== null ? s.godown_cases : "N/A", "Cases"],
      ["Net Variance", s.difference !== null ? s.difference : "N/A", "Cases"]
    ];
    const wsSummary = XLSX.utils.aoa_to_sheet(summaryRows);
    XLSX.utils.book_append_sheet(wb, wsSummary, "1_Summary");

    // Tab 2: 2_Brand_SKU_Movement
    const brandHeaders = [
      "Rank", "Brand Name", "Category", "Dispatched Cases", "Pending Cases (In Bond)",
      "Loose Bottles", "Velocity (cs/day)", "Volume Share (%)", "Total MRP (INR)", "Bulk Litres (BL)", "LPL"
    ];
    const brandRows = (data.brands_full || []).map((b, i) => [
      i + 1,
      b.name,
      b.category,
      b.dispatched_cases,
      b.pending_cases,
      b.bottles,
      b.velocity_per_day,
      b.share_pct,
      b.total_mrp,
      b.bulk_litres,
      b.lpl
    ]);
    const wsBrands = XLSX.utils.aoa_to_sheet([brandHeaders, ...brandRows]);
    XLSX.utils.book_append_sheet(wb, wsBrands, "2_Brand_SKU_Movement");

    // Tab 3: 3_Pack_Size_Matrix
    const packHeaders = ["Rank", "Pack Format / Size", "Category", "Cases Moved", "Loose Bottles", "Volume Share (%)", "Total MRP (INR)"];
    const packRows = (data.pack_sizes_full || []).map((p, i) => [
      i + 1,
      p.size,
      p.category,
      p.cases,
      p.bottles,
      p.share_pct,
      p.mrp
    ]);
    const wsPacks = XLSX.utils.aoa_to_sheet([packHeaders, ...packRows]);
    XLSX.utils.book_append_sheet(wb, wsPacks, "3_Pack_Size_Matrix");

    // Tab 4: 4_Party_Sales
    const partyHeaders = [
      "Rank", "Licensee / Retail Shop Name", "District", "Dispatched Cases", "Pending Cases in Bond",
      "Beer Cases", "IMFL Cases", "CS Cases", "Total Turnover MRP (INR)", "Indents Count", "Cadence", "Last Order Date"
    ];
    const partyRows = (data.parties_full || []).map((p, i) => [
      i + 1,
      p.name,
      p.district,
      p.dispatched_cases,
      p.pending_cases,
      p.beer_cases,
      p.imfl_cases,
      p.cs_cases,
      p.mrp,
      p.indent_count,
      p.cadence_status,
      p.last_order_date
    ]);
    const wsParties = XLSX.utils.aoa_to_sheet([partyHeaders, ...partyRows]);
    XLSX.utils.book_append_sheet(wb, wsParties, "4_Party_Sales");

    // Tab 5: 5_Indent_Register
    const indentHeaders = [
      "Challan Date", "Permit Number", "Transit Pass", "Indent Number", "Status",
      "Licensee Name", "Retailer Code", "District", "Vehicle Number", "Product Name",
      "Pack Size", "Category", "Cases", "Bottles", "Total MRP (INR)", "Bulk Litres", "LPL"
    ];
    const indentRows = (data.permits || []).map(r => [
      r['Challan Date'] || r.Date || "",
      r['Permit Number'] || "",
      r['Transit Pass'] || "",
      r['Indent Number'] || "",
      r.Status || "",
      r['Licensee Name'] || r['Retailer Name'] || "",
      r['Retailer Code'] || "",
      r.District || r['Destination District'] || "",
      r['Vehicle Number'] || "",
      r['Product Name'] || "",
      r['Pack Size'] || r.Size || "",
      AppUtils.getProductCategory(r),
      parseFloat(r.Cases || 0),
      parseInt(r.Bottles || 0, 10),
      parseFloat(r['Total MRP'] || 0),
      parseFloat(r['Bulk Litres'] || 0),
      parseFloat(r.LPL || 0)
    ]);
    const wsIndents = XLSX.utils.aoa_to_sheet([indentHeaders, ...indentRows]);
    XLSX.utils.book_append_sheet(wb, wsIndents, "5_Indent_Register");

    // Tab 6: 6_Godown_Reconciliation
    const godownHeaders = [
      "Date Key", "Date", "Day", "Operating Status", "Beer Cases", "IMFL Cases", "CS Cases",
      "Portal Dispatched Total Cases", "Physical Godown Cases", "Net Variance"
    ];
    const godownRows = (data.daily_series || []).map(d => [
      d.date_key,
      d.date_str,
      d.day,
      d.is_closed ? "Closed" : "Operating",
      d.beer_cases,
      d.imfl_cases,
      d.cs_cases,
      d.cases,
      d.godown_cases !== null ? d.godown_cases : "",
      d.difference !== null ? d.difference : ""
    ]);
    const wsGodown = XLSX.utils.aoa_to_sheet([godownHeaders, ...godownRows]);
    XLSX.utils.book_append_sheet(wb, wsGodown, "6_Godown_Reconciliation");

    // Export file
    const cleanLabel = (h.display_label || 'Dispatch').replace(/[^a-zA-Z0-9_-]/g, '_');
    XLSX.writeFile(wb, `PermTrack_Dispatch_${cleanLabel}.xlsx`);
    AppUtils.showToast(`Exported 6-Sheet Workbook: PermTrack_Dispatch_${cleanLabel}.xlsx`, 'success');
  },

  /**
   * Triggers Official PDF report download
   */
  downloadPDF() {
    const data = AppState.movementData;
    const h = data ? data.horizon : {};
    let dateParam = '';
    if (h && h.end_date_key) {
      dateParam = `?filename=backup_permits_${h.end_date_key}_000000.json`;
    }
    window.location.href = `/api/download-pdf${dateParam}`;
  }
};

window.AppExports = AppExports;
