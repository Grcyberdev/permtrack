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

if __name__ == "__main__":
    test_reconciliation()
    test_no_pending_completed_overlap()
