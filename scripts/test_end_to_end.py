import os
import sys
import json
from datetime import datetime

# Add scripts to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from reconciler import reconcile_permits, get_reconciliation_summary
from pdf_report import generate_report_pdf
from automation_utils import get_data_dir, get_bottles_per_case

def test_full_pipeline():
    config_dir = get_data_dir()
    
    # 0. Test pack size conversion helper
    assert get_bottles_per_case(650) == 12, "650ml should be 12 b/cs"
    assert get_bottles_per_case(750) == 12, "750ml should be 12 b/cs"
    assert get_bottles_per_case(375) == 24, "375ml should be 24 b/cs"
    assert get_bottles_per_case(500) == 24, "500ml should be 24 b/cs"
    assert get_bottles_per_case(180) == 48, "180ml should be 48 b/cs"
    assert get_bottles_per_case(90) == 96, "90ml should be 96 b/cs"
    print("✅ Pack size conversions verified!")

    # 1. Test Reconciliation on historical backups
    backup_file = os.path.join(config_dir, "backup_permits_20260723_000000.json")
    assert os.path.exists(backup_file), f"Backup file {backup_file} not found"
    
    with open(backup_file, "r") as f:
        raw_data = json.load(f)
        
    target_dt = datetime(2026, 7, 23)
    reconciled = reconcile_permits(raw_data, target_dt, config_dir, lookback_days=7)
    summary = get_reconciliation_summary(reconciled)
    
    print("📊 23-Jul-2026 Reconciliation Results:")
    print(f"   • Total Reconciled Records: {len(reconciled)}")
    print(f"   • Fresh Pending: {summary['fresh_pending_lines']}")
    print(f"   • Carried Over Pending: {summary['carried_over_pending_lines']}")
    print(f"   • Aging Breakdown: {summary['aging_breakdown']}")
    print(f"   • Unique Pending Indents: {summary['unique_pending_indents_count']}")
    print(f"   • Unique Dispatched Indents: {summary['unique_completed_indents_count']}")
    
    assert summary["carried_over_pending_lines"] > 0, "Should have carried-over permits from 20-22 Jul"
    assert summary["fresh_pending_lines"] > 0, "Should have fresh pending permits on 23 Jul"
    
    # 2. Test PDF Report Generation with Reconciled Records
    print("\n📄 Testing PDF Report generation with unified calculations...")
    pdf_bytes = generate_report_pdf(reconciled)
    assert len(pdf_bytes) > 1000, "PDF output should be valid binary content"
    print(f"   ✅ PDF successfully generated ({len(pdf_bytes)} bytes)")
    
    # 3. Test API Data Shape compatibility
    pending = [r for r in reconciled if r.get("Status") == "PENDING"]
    completed = [r for r in reconciled if r.get("Status") == "COMPLETED"]
    
    carried_records = [p for p in pending if p.get("is_carried_over")]
    assert len(carried_records) == summary["carried_over_pending_lines"]
    
    for c in carried_records:
        assert "aging_days" in c and c["aging_days"] >= 1
        assert "Application Date" in c
        
    print("\n✅ All End-to-End Tests Passed Successfully!")

if __name__ == "__main__":
    test_full_pipeline()
