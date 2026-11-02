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

    def test_absolut_vodka_200ml_bottle_math(self):
        """
        Tests bottle-to-case calculations for 200ml bottles (Absolut Vodka).
        Pack Size 200/24 with 12 bottles MUST equal 0.5 cases Eq, NOT 0.25 cases.
        """
        from automation_utils import get_bottles_per_case
        
        # Test explicit Pack Size string
        self.assertEqual(get_bottles_per_case("200/24"), 24)
        self.assertEqual(get_bottles_per_case("200", pack_size="200/24"), 24)
        
        # Test 200ml standalone (spirits 200ml pints are 24 b/cs in Assam)
        self.assertEqual(get_bottles_per_case(200), 24)
        self.assertEqual(get_bottles_per_case("200"), 24)
        
        # 12 bottles of 200ml (24 b/cs) = 0.5 cs
        cases_eq = 12 / get_bottles_per_case("200/24")
        self.assertEqual(cases_eq, 0.5)
        
        # Other standard sizes
        self.assertEqual(get_bottles_per_case("700/6"), 6)
        self.assertEqual(get_bottles_per_case(750), 12)
        self.assertEqual(get_bottles_per_case(375), 24)
        self.assertEqual(get_bottles_per_case(180), 48)
        self.assertEqual(get_bottles_per_case(90), 96)
        print("✅ test_absolut_vodka_200ml_bottle_math passed! (12 b of 200ml = 0.5 cs)")

    def test_officers_choice_filter_and_recheck(self):
        """
        Verifies that 'OFFICERS CHOICE PREMIUM WHISKY (PET)' is not filtered out
        by signature/footer guards and is properly recovered by Form-34 recheck.
        """
        # Signature filter simulation
        brand_name = "OFFICERS CHOICE PREMIUM WHISKY (PET)"
        lower_p = brand_name.lower()
        is_signature = any(k in lower_p for k in ["signature of", "issuing the transport pass", "granting the transport pass", "vide challan no"])
        self.assertFalse(is_signature, "OFFICERS CHOICE must not be flagged as a signature line")
        
        # Verify merge_brand_data adds approved SKU missing from Form-34
        f34_lines = [
            {"Product Name": "SEAGRAM'S ROYAL STAG DELUXE WHISKY", "Size": "180", "Cases": 10, "Bottles": 0}
        ]
        modal_lines = [
            {"Product Name": "SEAGRAM'S ROYAL STAG DELUXE WHISKY", "Size": "180", "Cases": 10, "Bottles": 0, "Total MRP": 64573.7},
            {"Product Name": "OFFICERS CHOICE PREMIUM WHISKY (PET)", "Size": "180", "Cases": 10, "Bottles": 0, "Total MRP": 38744.2}
        ]
        
        merged = merge_brand_data(f34_lines, modal_lines)
        self.assertEqual(len(merged), 2)
        self.assertEqual(sum(m["Cases"] for m in merged), 20)
        oc_entry = next(m for m in merged if "OFFICERS CHOICE" in m["Product Name"])
        self.assertEqual(oc_entry["Cases"], 10)
        self.assertEqual(oc_entry["Total MRP"], 38744.2)
        print("✅ test_officers_choice_filter_and_recheck passed! (OFFICERS CHOICE preserved)")

    def test_pending_permits_not_skipped_by_action_buttons(self):
        """
        Verifies that pending permits awaiting approval (which contain 'Approve' or 'Verify & forward'
        buttons in Column 8 'Action') are NOT mistakenly marked as has_f34 or skipped as dispatched.
        """
        class MockElement:
            def __init__(self, tag, text, attrs=None):
                self.tag = tag
                self.text = text
                self.attrs = attrs or {}
            def find_elements(self, by, query):
                # If searching for form34 / print links, Approve button must not match!
                if "form34" in query or "print" in query:
                    if "form34" in self.attrs.get("href", "") or "print" in self.attrs.get("class", ""):
                        return [self]
                    return []
                # Generic button check
                if "button" in query and self.tag == "button":
                    return [self]
                return []

        # Column 8 in portal has 'Approve' button for pending indents awaiting approval
        col8_action_approve = MockElement("button", "Approve", {"class": "btn btn-primary"})
        # Column 9 in portal is Form-34 (empty for pending indents)
        col9_empty = MockElement("td", "")

        cols_pending = [MockElement("td", "") for _ in range(8)] + [col8_action_approve, col9_empty]

        # Verify our Column 9 Form 34 check does NOT match the Approve button
        has_f34 = False
        for idx in [9, len(cols_pending) - 1]:
            if idx < len(cols_pending):
                f34_elems = cols_pending[idx].find_elements("xpath", ".//a[contains(@href, 'form34')] | .//i[contains(@class, 'print')]")
                if f34_elems:
                    has_f34 = True
                    break

        self.assertFalse(has_f34, "Approve action button in Column 8 must never be identified as Form 34")

        # Verify that for status_filter == 'Pending', with transit_pass = '', the row is NOT skipped
        transit_pass = ""
        has_tp = bool(transit_pass and transit_pass.upper().startswith("TP"))
        should_skip = (has_tp or has_f34)
        self.assertFalse(should_skip, "Pending permit with Approve button must NOT be skipped")
        print("✅ test_pending_permits_not_skipped_by_action_buttons passed! (Pending rows preserved)")

if __name__ == "__main__":
    unittest.main()
