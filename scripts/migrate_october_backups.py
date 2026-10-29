import os
import sys
import glob
import json
import re
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reconciler import get_record_effective_date_key, get_unique_permit_key, parse_date_str

def rebalance_backups(data_dir: str):
    """
    Rebalances historical backups in data_dir so that completed dispatches
    are stored in the backup file matching their true operational Challan Date / Transit Pass date.
    """
    files = sorted([f for f in glob.glob(os.path.join(data_dir, "backup_permits_202610*.json")) if "latest" not in f])
    print(f"📦 Found {len(files)} October backup files in {data_dir}")
    
    tp_regex = re.compile(r"^TP\d{4}(\d{2})(\d{2})(\d{2})")
    
    # Map of date_key -> list of pending records originally in that date's file
    pending_by_date = {}
    
    # Map of unique permit key -> completed record
    unique_completed = {}
    
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
                if pkey not in unique_completed:
                    eff_k = get_record_effective_date_key(r, default_date_key=dkey)
                    unique_completed[pkey] = (r, eff_k)
            else:
                pending_list.append(r)
                
        pending_by_date[dkey] = pending_list

    # Group completed records by their operational effective date
    completed_by_eff_date = {}
    for pkey, (r, eff_k) in unique_completed.items():
        completed_by_eff_date.setdefault(eff_k, []).append(r)

    all_dkeys = sorted(set(list(pending_by_date.keys()) + list(completed_by_eff_date.keys())))
    print(f"📊 Rebalancing {len(unique_completed)} completed records across {len(all_dkeys)} date files...")

    rebalanced_count = 0
    for dkey in all_dkeys:
        out_fname = f"backup_permits_{dkey}_000000.json"
        out_fpath = os.path.join(data_dir, out_fname)
        
        c_recs = completed_by_eff_date.get(dkey, [])
        p_recs = pending_by_date.get(dkey, [])
        combined = c_recs + p_recs
        
        with open(out_fpath, "w", encoding="utf-8") as fp:
            json.dump(combined, fp, indent=4)
            
        print(f"   ✅ {out_fname}: {len(c_recs)} completed, {len(p_recs)} pending (Total: {len(combined)})")
        rebalanced_count += 1
        
    print(f"🎉 Successfully rebalanced {rebalanced_count} backup files!")

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "config"
    rebalance_backups(target_dir)
