import os
import sys
import glob
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reconciler import (
    get_record_effective_date_key,
    build_historical_sku_rates,
    backfill_missing_mrps,
    reconcile_permits,
    clean_permit_records,
    get_unique_permit_key,
    get_unique_indent_id
)

def sanitize_data_directory(data_dir: str):
    print(f"🧹 Starting data sanitization in {data_dir}...")
    
    # 1. Build historical SKU rates
    sku_rates = build_historical_sku_rates(data_dir)
    print(f"📊 Built {len(sku_rates)} historical SKU rate entries")
    
    # 2. Load 20261029 backup
    f29_path = os.path.join(data_dir, "backup_permits_20261029_000000.json")
    if not os.path.exists(f29_path):
        print(f"⚠️ {f29_path} does not exist, skipping.")
        return
        
    with open(f29_path, "r", encoding="utf-8") as f:
        data29 = json.load(f)
        
    print(f"📥 Loaded {len(data29)} raw records from {os.path.basename(f29_path)}")
    
    # Partition by effective date
    oct29_records = []
    crossover_by_date = {}
    
    for r in data29:
        status = str(r.get("Status", "")).upper()
        if status == "PENDING":
            oct29_records.append(r)
        else:
            eff_k = get_record_effective_date_key(r, default_date_key="20261029")
            if eff_k == "20261029":
                oct29_records.append(r)
            else:
                crossover_by_date.setdefault(eff_k, []).append(r)
                
    print(f"🎯 Oct 29 records partitioned: {len(oct29_records)} (Completed: {sum(1 for r in oct29_records if r.get('Status') == 'COMPLETED')}, Pending: {sum(1 for r in oct29_records if r.get('Status') == 'PENDING')})")
    for d_k, d_recs in crossover_by_date.items():
        print(f"   ↳ Prior date {d_k}: {len(d_recs)} crossover records separated out")
        
    # 3. Backfill missing MRPs for Oct 29 records
    oct29_records = backfill_missing_mrps(oct29_records, sku_rates)
    
    # 4. Reconcile Oct 29 with 7-day lookback
    dt29 = datetime(2026, 10, 29)
    reconciled_29 = reconcile_permits(oct29_records, dt29, data_dir, lookback_days=7)
    
    # Save back to 20261029 and latest
    with open(f29_path, "w", encoding="utf-8") as f:
        json.dump(reconciled_29, f, indent=4)
        
    latest_path = os.path.join(data_dir, "backup_permits_latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(reconciled_29, f, indent=4)
        
    print(f"✅ Successfully wrote clean, partitioned, and MRP-healed data to {os.path.basename(f29_path)} ({len(reconciled_29)} records)")
    
    # 5. Route crossover records to prior dates if missing
    for d_k, d_recs in crossover_by_date.items():
        prior_file = os.path.join(data_dir, f"backup_permits_{d_k}_000000.json")
        prior_data = []
        if os.path.exists(prior_file):
            try:
                with open(prior_file, "r", encoding="utf-8") as pf:
                    prior_data = json.load(pf) or []
            except Exception:
                prior_data = []
                
        p_keys = {get_unique_permit_key(it) for it in prior_data}
        added = 0
        for nr in d_recs:
            k = get_unique_permit_key(nr)
            if k not in p_keys:
                prior_data.append(nr)
                p_keys.add(k)
                added += 1
                
        if added > 0:
            p_dt = datetime.strptime(d_k, "%Y%m%d")
            cleaned_p = reconcile_permits(prior_data, p_dt, data_dir, lookback_days=7)
            with open(prior_file, "w", encoding="utf-8") as pf:
                json.dump(cleaned_p, pf, indent=4)
            print(f"✅ Added {added} missing crossover records into {os.path.basename(prior_file)}")
        else:
            print(f"ℹ️ All {len(d_recs)} crossover records already present in {os.path.basename(prior_file)}")

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "config"
    sanitize_data_directory(target_dir)
