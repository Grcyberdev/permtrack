import os
import sys
import json
from datetime import datetime

# Add scripts directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reconciler import reconcile_permits, get_reconciliation_summary

def test_reconciliation():
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
    
    # Load 20260723 backup as current records
    target_file = os.path.join(config_dir, "backup_permits_20260723_000000.json")
    assert os.path.exists(target_file), "Target backup file missing"
    
    with open(target_file, "r") as f:
        records_23 = json.load(f)
        
    target_date = datetime(2026, 7, 23)
    reconciled = reconcile_permits(records_23, target_date, config_dir, lookback_days=7)
    
    summary = get_reconciliation_summary(reconciled)
    print("Reconciliation Summary for 23-Jul-2026:")
    print(json.dumps(summary, indent=2))
    
    # Verify properties
    pending = [r for r in reconciled if r.get("Status") == "PENDING"]
    completed = [r for r in reconciled if r.get("Status") == "COMPLETED"]
    
    carried_over = [p for p in pending if p.get("is_carried_over")]
    fresh = [p for p in pending if not p.get("is_carried_over")]
    
    print(f"Total Pending: {len(pending)} (Fresh: {len(fresh)}, Carried Over: {len(carried_over)})")
    print(f"Total Completed: {len(completed)}")
    
    assert len(reconciled) >= len(records_23), "Reconciled records should be >= raw records"
    print("✅ test_reconciliation passed successfully!")

def test_no_pending_completed_overlap():
    from reconciler import get_unique_indent_id
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
    target_file = os.path.join(config_dir, "backup_permits_20261016_000000.json")
    with open(target_file, "r") as f:
        records_16 = json.load(f)
        
    reconciled = reconcile_permits(records_16, datetime(2026, 10, 16), config_dir, lookback_days=7)
    completed_iids = {get_unique_indent_id(r) for r in reconciled if r.get("Status") == "COMPLETED"}
    pending_iids = {get_unique_indent_id(r) for r in reconciled if r.get("Status") == "PENDING"}
    
    overlap = completed_iids.intersection(pending_iids)
    assert len(overlap) == 0, f"No indent should exist in both completed and pending: {overlap}"
    print("✅ test_no_pending_completed_overlap passed: 0 overlap!")

def test_brand_variant_separation():
    from reconciler import get_unique_permit_key, clean_permit_records
    
    item1 = {
        "Status": "COMPLETED",
        "Indent Number": "IND2026DEPOLD309816422",
        "Product Name": "MASTI SPECIAL",
        "Size": "300",
        "Cases": 5,
        "Total MRP": 6166.15
    }
    item2 = {
        "Status": "COMPLETED",
        "Indent Number": "IND2026DEPOLD309816422",
        "Product Name": "MASTI",
        "Size": "300",
        "Cases": 20,
        "Total MRP": 24664.6
    }
    
    k1 = get_unique_permit_key(item1)
    k2 = get_unique_permit_key(item2)
    assert k1 != k2, f"Keys must be distinct: {k1} vs {k2}"
    
    cleaned = clean_permit_records([item1, item2])
    assert len(cleaned) == 2, f"Both distinct brand variants must survive deduplication: got {len(cleaned)}"
    tot_cases = sum(c.get("Cases", 0) for c in cleaned)
    assert tot_cases == 25, f"Expected 25 total cases, got {tot_cases}"
    print("✅ test_brand_variant_separation passed: MASTI and MASTI SPECIAL correctly preserved without collision!")

def test_historical_completed_indent_purges_pending():
    import tempfile, json, shutil
    from datetime import datetime
    from reconciler import reconcile_permits
    
    tmpdir = tempfile.mkdtemp()
    try:
        # Day 1: backup has indent IND_TEST as PENDING with 0 cases (ghost record)
        day1_records = [{
            "Date": "28-Oct-2026",
            "Indent Number": "IND_TEST",
            "Retailer Name": "TEST WINE",
            "Status": "PENDING",
            "Product Name": "",
            "Cases": 0,
            "Bottles": 0
        }]
        with open(os.path.join(tmpdir, "backup_permits_20261028_000000.json"), "w") as f:
            json.dump(day1_records, f)
            
        # Day 2: IND_TEST was completed with 150 cases
        day2_records = [{
            "Date": "29-Oct-2026",
            "Indent Number": "IND_TEST",
            "Transit Pass": "TP309729102699999",
            "Retailer Name": "TEST WINE",
            "Status": "COMPLETED",
            "Product Name": "ROYAL STAG",
            "Size": "750",
            "Cases": 150,
            "Bottles": 0
        }]
        with open(os.path.join(tmpdir, "backup_permits_20261029_000000.json"), "w") as f:
            json.dump(day2_records, f)
            
        # Day 3: when reconciling for 30-Oct, IND_TEST must NEVER appear as CARRIED PENDING!
        day3_current = []
        reconciled = reconcile_permits(day3_current, datetime(2026, 10, 30), tmpdir, lookback_days=7)
        
        pending_indents = [r.get("Indent Number") for r in reconciled if r.get("Status") == "PENDING"]
        assert "IND_TEST" not in pending_indents, f"IND_TEST was completed on Day 2; must not be carried over as pending on Day 3: {pending_indents}"
        print("✅ test_historical_completed_indent_purges_pending passed: completed indent properly removed from pending pool!")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def test_empty_ghost_row_dropped():
    from reconciler import clean_permit_records
    records = [
        {
            "Indent Number": "IND_GHOST",
            "Retailer Name": "GHOST SHOP",
            "Status": "PENDING",
            "Product Name": "",
            "Cases": 0,
            "Bottles": 0
        },
        {
            "Indent Number": "IND_VALID",
            "Retailer Name": "VALID SHOP",
            "Status": "PENDING",
            "Product Name": "BEER",
            "Cases": 10,
            "Bottles": 0
        }
    ]
    cleaned = clean_permit_records(records)
    iids = [r.get("Indent Number") for r in cleaned]
    assert "IND_GHOST" not in iids, "Empty 0-case ghost record should be dropped"
    assert "IND_VALID" in iids, "Valid pending record should be retained"
    print("✅ test_empty_ghost_row_dropped passed!")

if __name__ == "__main__":
    test_reconciliation()
    test_no_pending_completed_overlap()
    test_brand_variant_separation()
    test_historical_completed_indent_purges_pending()
    test_empty_ghost_row_dropped()
