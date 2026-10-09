import os
import sys
import unittest
import json
import tempfile
from datetime import datetime

# Add scripts directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main_permits import merge_brand_data, recheck_permit_from_portal
from reconciler import get_unique_permit_key, get_unique_indent_id

class TestMultiTableAndRecheck(unittest.TestCase):

    def test_merge_brand_data_multitable(self):
        """
        Tests bidirectional merging when Form-34 has only Whisky (15 cs)
        and Modal contains Whisky (15 cs) + Beer (135 cs).
        """
        f34_lines = [
            {"Product Name": "SEAGRAM'S XCLAMATION RESERVE WHISKY", "Category": "Whisky", "Size": "180", "Pack Size": "180/48", "Cases": 2, "Bottles": 0, "Bulk Litres": 17.28, "LPL": 7.4, "Total MRP": 0.0},
            {"Product Name": "SEAGRAM'S XCLAMATION RESERVE WHISKY", "Category": "Whisky", "Size": "375", "Pack Size": "375/24", "Cases": 1, "Bottles": 0, "Bulk Litres": 9.0, "LPL": 3.8, "Total MRP": 0.0},
            {"Product Name": "SEAGRAM'S XCLAMATION RESERVE WHISKY", "Category": "Whisky", "Size": "750", "Pack Size": "750/12", "Cases": 2, "Bottles": 0, "Bulk Litres": 18.0, "LPL": 7.7, "Total MRP": 0.0},
            {"Product Name": "AC BLACK LUXURY PURE GRAIN WHISKY", "Category": "Whisky", "Size": "375", "Pack Size": "375/24", "Cases": 10, "Bottles": 0, "Bulk Litres": 90.0, "LPL": 38.5, "Total MRP": 0.0},
        ]
        
        modal_lines = [
            {"Product Name": "SEAGRAM'S XCLAMATION RESERVE WHISKY", "Size": "180", "Cases": 2, "Bottles": 0, "Total MRP": 13440.0},
            {"Product Name": "SEAGRAM'S XCLAMATION RESERVE WHISKY", "Size": "375", "Cases": 1, "Bottles": 0, "Total MRP": 6480.0},
            {"Product Name": "SEAGRAM'S XCLAMATION RESERVE WHISKY", "Size": "750", "Cases": 2, "Bottles": 0, "Total MRP": 13200.0},
            {"Product Name": "AC BLACK LUXURY PURE GRAIN WHISKY", "Size": "375", "Cases": 10, "Bottles": 0, "Total MRP": 60573.0},
            {"Product Name": "KINGFISHER PREMIUM LAGER BEER", "Size": "650", "Cases": 135, "Bottles": 0, "Total MRP": 250000.0},
        ]
        
        merged = merge_brand_data(f34_lines, modal_lines)
        
        # Verify all 5 lines are present
        self.assertEqual(len(merged), 5)
        
        # Verify total cases equals 150
        tot_cases = sum(m["Cases"] for m in merged)
        self.assertEqual(tot_cases, 150)
        
        # Verify Kingfisher Beer was retained with proper category and Bulk Litres
        beer_item = next(m for m in merged if "KINGFISHER" in m["Product Name"])
        self.assertEqual(beer_item["Cases"], 135)
        self.assertEqual(beer_item["Category"], "Beer")
        self.assertGreater(beer_item["Bulk Litres"], 0)
        self.assertEqual(beer_item["Total MRP"], 250000.0)
        print("✅ test_merge_brand_data_multitable passed! (150 cs preserved)")

    def test_recheck_backup_balance_fallback(self):
        """
        Tests recheck fallback when lines total 15 cases but official portal total is 150 cases.
        """
        brand_lines = [
            {"Product Name": "SEAGRAM'S XCLAMATION RESERVE WHISKY", "Cases": 15, "Bottles": 0}
        ]
        official_cases = 150
        official_bottles = 0
        indent_num = "IND2026DEPOLD309777025"
        
        # Calling recheck with driver=None should gracefully recover missing balance
        rechecked_lines, final_cases, final_bottles = recheck_permit_from_portal(
            None, None, indent_num, [], brand_lines, official_cases, official_bottles
        )
        
        tot_c = sum(r["Cases"] for r in rechecked_lines)
        self.assertEqual(tot_c, 150)
        self.assertEqual(final_cases, 150)
        
        # Ensure verified balance entry was generated
        balance_entry = next((r for r in rechecked_lines if r.get("is_reconciled_balance")), None)
        self.assertIsNotNone(balance_entry)
        self.assertEqual(balance_entry["Cases"], 135)
        print("✅ test_recheck_backup_balance_fallback passed! (135 cs balance applied)")

    def test_upload_guard_against_degradation(self):
        """
        Tests server upload guard logic:
        Existing record has 150 cs. Incoming erroneously reports 15 cs.
        Verifies degraded incoming record is ignored and 150 cs record is preserved.
        """
        existing = [
            {"Indent Number": "IND999", "Product Name": "WHISKY", "Size": "750", "Cases": 15, "Status": "COMPLETED", "Bond Type": "IMFL"},
            {"Indent Number": "IND999", "Product Name": "BEER", "Size": "650", "Cases": 135, "Status": "COMPLETED", "Bond Type": "IMFL"}
        ]
        incoming_degraded = [
            {"Indent Number": "IND999", "Product Name": "WHISKY", "Size": "750", "Cases": 15, "Status": "COMPLETED", "Bond Type": "IMFL"}
        ]
        
        # Simulate upload guard logic from app.py
        existing_indent_cases = {}
        for it in existing:
            iid = get_unique_indent_id(it)
            existing_indent_cases[iid] = existing_indent_cases.get(iid, 0.0) + float(it.get("Cases") or 0)
            
        incoming_indent_cases = {}
        for it in incoming_degraded:
            iid = get_unique_indent_id(it)
            incoming_indent_cases[iid] = incoming_indent_cases.get(iid, 0.0) + float(it.get("Cases") or 0)
            
        degraded_indents = set()
        for iid, ex_c in existing_indent_cases.items():
            inc_c = incoming_indent_cases.get(iid, 0.0)
            if inc_c > 0 and inc_c < (ex_c - 0.01):
                degraded_indents.add(iid)
                
        self.assertIn("IND999", degraded_indents)
        
        protected_records = [
            it for it in incoming_degraded 
            if not (str(it.get("Status", "")).upper() == "COMPLETED" and get_unique_indent_id(it) in degraded_indents)
        ]
        
        records_to_reconcile = list(protected_records)
        incoming_completed_keys = {get_unique_permit_key(it) for it in protected_records}
        
        for ex in existing:
            ex_key = get_unique_permit_key(ex)
            ex_iid = get_unique_indent_id(ex)
            if ex_iid in degraded_indents or ex_key not in incoming_completed_keys:
                records_to_reconcile.append(ex)
                incoming_completed_keys.add(ex_key)
                
        final_cases = sum(r["Cases"] for r in records_to_reconcile)
        self.assertEqual(final_cases, 150)
        print("✅ test_upload_guard_against_degradation passed! (150 cs defended against regression)")

if __name__ == "__main__":
    unittest.main()
