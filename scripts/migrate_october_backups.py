import os
import sys
import glob
import json
import re
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reconciler import (
    get_record_effective_date_key,
    get_unique_permit_key,
    get_unique_indent_id,
    parse_date_str,
    build_historical_sku_rates,
    backfill_missing_mrps,
    reconcile_permits,
    clean_permit_records
)
import automation_utils

def rebalance_backups(data_dir: str):
    """
    Rebalances and heals all historical October backups in data_dir so that:
    1. Completed dispatches are partitioned strictly into the backup file matching their true
       operational Challan Date / Transit Pass date.
    2. Zero-case overrides and empty dummy lines are cleaned.
    3. Missing or zero Total MRP values are healed using historical SKU rates.
    4. Pending records are mutually exclusive from completed records and have verified aging.
    5. A comprehensive day-by-day reconciliation audit is performed against Godown records.
    """
    files = sorted([f for f in glob.glob(os.path.join(data_dir, "backup_permits_202610*.json")) if "latest" not in f])
    print(f"📦 Found {len(files)} October backup files in {data_dir}")
    
    tp_regex = re.compile(r"^TP\d{4}(\d{2})(\d{2})(\d{2})")
    
    # 1. Build SKU Rate catalog across all available backups for MRP healing
    sku_rates = build_historical_sku_rates(data_dir)
    print(f"💡 Built historical SKU rates catalog with {len(sku_rates)} SKU price points.")
    
    # 2. Gather all completed records with quality deduplication
    pending_by_date = {}
    unique_completed = {}
    completed_indent_ids = set()
    
    for fpath in files:
        fname = os.path.basename(fpath)
        dkey = fname.replace("backup_permits_", "").replace(".json", "").split("_")[0]
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                records = json.load(fp) or []
        except Exception as e:
            print(f"   ⚠️ Could not read {fname}: {e}")
            continue
            
        pending_list = []
        for r in records:
            status = str(r.get("Status") or "").strip().upper()
            if status == "COMPLETED":
                # Ensure Challan Date is populated from Transit Pass if blank
                ch = str(r.get("Challan Date") or "").strip()
                tp = str(r.get("Transit Pass") or "").strip()
                if not ch and tp:
                    m = tp_regex.match(tp)
                    if m:
                        dd, mm, yy = m.groups()
                        try:
                            dt = datetime(2000 + int(yy), int(mm), int(dd))
                            r["Challan Date"] = dt.strftime("%d-%b-%Y")
                        except ValueError:
                            pass
                            
                pkey = get_unique_permit_key(r)
                iid = get_unique_indent_id(r)
                completed_indent_ids.add(iid)
                
                eff_k = get_record_effective_date_key(r, default_date_key=dkey)
                
                # Deduplication with quality scoring: prefer positive cases, positive MRP, and non-empty details
                if pkey not in unique_completed:
                    unique_completed[pkey] = (r, eff_k)
                else:
                    existing_r, existing_eff = unique_completed[pkey]
                    new_cases = float(r.get("Cases") or 0)
                    old_cases = float(existing_r.get("Cases") or 0)
                    new_mrp = float(r.get("Total MRP") or 0)
                    old_mrp = float(existing_r.get("Total MRP") or 0)
                    
                    # Replace if new record has more cases, or equal cases with higher MRP/details
                    if (new_cases > old_cases) or (new_cases == old_cases and new_mrp > old_mrp):
                        unique_completed[pkey] = (r, eff_k)
                    else:
                        # Merge any missing fields into existing
                        for fld in ["Total MRP", "Bulk Litres", "LPL", "Vehicle Number", "Challan Date", "Licensee Name", "Pack Size", "Category"]:
                            if not existing_r.get(fld) and r.get(fld):
                                existing_r[fld] = r[fld]
            else:
                pending_list.append(r)
                
        pending_by_date[dkey] = pending_list

    # Group completed records by their true operational effective date
    completed_by_eff_date = {}
    for pkey, (r, eff_k) in unique_completed.items():
        completed_by_eff_date.setdefault(eff_k, []).append(r)

    all_dkeys = sorted(set(list(pending_by_date.keys()) + list(completed_by_eff_date.keys())))
    print(f"📊 Rebalancing and healing {len(unique_completed)} completed records across {len(all_dkeys)} date files...")

    rebalanced_count = 0
    latest_dkey = None
    latest_combined = []
    
    for dkey in all_dkeys:
        out_fname = f"backup_permits_{dkey}_000000.json"
        out_fpath = os.path.join(data_dir, out_fname)
        
        c_recs = completed_by_eff_date.get(dkey, [])
        p_recs = pending_by_date.get(dkey, [])
        
        # Enforce that completed indents are never kept in pending
        c_iids_on_date = {get_unique_indent_id(r) for r in c_recs}
        filtered_p = [p for p in p_recs if get_unique_indent_id(p) not in c_iids_on_date]
        
        # Format target date display string
        try:
            target_dt = datetime.strptime(dkey, "%Y%m%d")
            formatted_date_str = target_dt.strftime("%d-%b-%Y")
        except Exception:
            formatted_date_str = dkey
            target_dt = datetime.now()
            
        # Update Date attribute on records to reflect effective date
        for r in c_recs:
            r["Date"] = formatted_date_str
            r["Status"] = "COMPLETED"
            
        for r in filtered_p:
            r["Status"] = "PENDING"
            
        combined = c_recs + filtered_p
        
        # Clean dummy 0-case placeholder rows if valid lines exist
        combined = clean_permit_records(combined)
        
        # Backfill any missing MRPs using historical SKU rate catalog
        combined = backfill_missing_mrps(combined, sku_rates)
        
        with open(out_fpath, "w", encoding="utf-8") as fp:
            json.dump(combined, fp, indent=4)
            
        print(f"   ✅ {out_fname}: {len(c_recs)} completed, {len(filtered_p)} pending (Total: {len(combined)})")
        rebalanced_count += 1
        
        latest_dkey = dkey
        latest_combined = combined

    # Update latest backup pointer to the latest date
    if latest_combined and latest_dkey:
        latest_fpath = os.path.join(data_dir, "backup_permits_latest.json")
        with open(latest_fpath, "w", encoding="utf-8") as fp:
            json.dump(latest_combined, fp, indent=4)
        print(f"📌 Updated backup_permits_latest.json with latest date {latest_dkey} ({len(latest_combined)} records)")

    print(f"\n🎉 Successfully rebalanced and healed {rebalanced_count} October backup files!")

    # 3. Comprehensive Verification Audit against Godown Reconciliation
    recon_path = os.path.join(data_dir, "godown_reconciliation.json")
    godown_data = {}
    if os.path.exists(recon_path):
        try:
            with open(recon_path, "r", encoding="utf-8") as rf:
                godown_data = json.load(rf) or {}
        except Exception:
            pass

    print("\n" + "═" * 90)
    print("📈 COMPREHENSIVE OCTOBER 2026 DAILY RECONCILIATION & VARIANCE AUDIT")
    print("═" * 90)
    print(f"{'Date':12} | {'PermTrack':10} | {'Godown':10} | {'Variance':10} | {'Turnover (MRP)':15} | {'Status'}")
    print("─" * 90)

    cum_permtrack = 0.0
    cum_godown = 0.0
    cum_mrp = 0.0

    for day in range(1, 32):
        dkey = f"202610{day:02d}"
        if dkey not in all_dkeys and dkey not in godown_data:
            continue
            
        fpath = os.path.join(data_dir, f"backup_permits_{dkey}_000000.json")
        recs = []
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as fp:
                    recs = json.load(fp) or []
            except Exception:
                pass
                
        c_recs = [r for r in recs if str(r.get("Status", "")).upper() == "COMPLETED"]
        tot_phys_cases = sum(float(r.get("Cases") or 0) for r in c_recs)
        tot_loose_cases = sum(float(r.get("Bottles") or 0) / automation_utils.get_bottles_per_case(r.get("Size")) for r in c_recs)
        tot_pt_cases = round(tot_phys_cases + tot_loose_cases, 2)
        tot_mrp = round(sum(float(r.get("Total MRP") or 0) for r in c_recs), 2)
        
        g_entry = godown_data.get(dkey)
        godown_cases = g_entry.get("godown_cases") if (g_entry and isinstance(g_entry, dict)) else None
        
        if godown_cases is not None:
            diff = round(godown_cases - tot_pt_cases, 2)
            cum_permtrack += tot_pt_cases
            cum_godown += godown_cases
            cum_mrp += tot_mrp
            if abs(diff) <= 25:
                status = "✅ MATCH"
            elif abs(diff) <= 250:
                status = "🟡 NORMAL VARIANCE"
            else:
                status = "⚠️ NOTABLE GAP"
        else:
            diff = "N/A"
            status = "CLOSED / SUNDAY" if tot_pt_cases == 0 else "NO GODOWN DATA"
            cum_mrp += tot_mrp
            
        diff_str = f"{diff:+.2f}" if isinstance(diff, (int, float)) else str(diff)
        g_str = f"{godown_cases:.2f}" if godown_cases is not None else "None"
        mrp_str = f"₹ {tot_mrp:,.2f}"
        
        print(f"2026-10-{day:02d}   | {tot_pt_cases:10.2f} | {g_str:>10} | {diff_str:>10} | {mrp_str:>15} | {status}")

    print("─" * 90)
    cum_diff = round(cum_godown - cum_permtrack, 2)
    cum_pct = round(abs(cum_diff) / cum_godown * 100, 2) if cum_godown > 0 else 0.0
    print(f"CUMULATIVE   | {cum_permtrack:10.2f} | {cum_godown:10.2f} | {cum_diff:+10.2f} | ₹ {cum_mrp:,.2f}")
    print(f"Overall Month Variance: {cum_pct}% across all operational days.")
    print("═" * 90)

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "config"
    rebalance_backups(target_dir)
