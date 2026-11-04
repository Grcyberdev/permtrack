import os
import sys
import json
from datetime import datetime

# Add scripts directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

def test_pack_size_normalization():
    from reconciler import normalize_pack_size
    assert normalize_pack_size("375") == "375/24"
    assert normalize_pack_size("375 ML") == "375/24"
    assert normalize_pack_size("375/24") == "375/24"
    assert normalize_pack_size("750") == "750/12"
    assert normalize_pack_size("750 ML") == "750/12"
    assert normalize_pack_size("180") == "180/48"
    assert normalize_pack_size("650") == "650/12"
    assert normalize_pack_size("500") == "500/24"
    assert normalize_pack_size("700/6") == "700/6"
    assert normalize_pack_size("250/36") == "250/36"
    assert normalize_pack_size("600/20") == "600/20"
    print("✅ test_pack_size_normalization passed!")

def test_ghost_line_pruning():
    from reconciler import clean_permit_records
    # Simulate an indent with genuine Form-34 records and injected modal ghost lines
    records = [
        {
            "Indent Number": "IND_JOGOMAYA",
            "Permit Number": "PER1015302112601461",
            "Licensee Name": "JOGOMAYA HATIKAKOTY SONS",
            "Status": "COMPLETED",
            "Product Name": "MCDOWELL'S NO.1 RESERVE WHISKY",
            "Pack Size": "180/48",
            "Cases": 5,
            "Bottles": 0,
        },
        {
            "Indent Number": "IND_JOGOMAYA",
            "Permit Number": "PER1015302112601461",
            "Licensee Name": "JOGOMAYA HATIKAKOTY SONS",
            "Status": "COMPLETED",
            "Product Name": "OFFICER'S CHOICE PREMIUM WHISKY",
            "Pack Size": "750/12",
            "Cases": 1,
            "Bottles": 0,
        },
        # Injected ghost line lacking Licensee Name and valid Pack Size
        {
            "Indent Number": "IND_JOGOMAYA",
            "Permit Number": "PER1015302112601461",
            "Licensee Name": "",
            "Status": "COMPLETED",
            "Product Name": "AFTER DARK BLUE RARE GRAIN WHISKY",
            "Pack Size": "",
            "Size": "750",
            "Cases": 1,
            "Bottles": 0,
        }
    ]
    cleaned = clean_permit_records(records)
    assert len(cleaned) == 2, f"Ghost line must be pruned, expected 2 items, got {len(cleaned)}"
    prod_names = [r["Product Name"] for r in cleaned]
    assert "AFTER DARK BLUE RARE GRAIN WHISKY" not in prod_names, "Ghost line must not be present in cleaned records"
    assert "180/48" in [r["Pack Size"] for r in cleaned]
    print("✅ test_ghost_line_pruning passed!")

def test_product_categorization():
    from app import get_product_category
    # Calenter Premium Rum must be IMFL, not BEER (not matched by 'ALE')
    assert get_product_category({"Product Name": "CALENTER PREMIUM RUM"}) == "IMFL"
    # Jameson Irish Whiskey Caskmates must be IMFL, not BEER (not matched by 'STOUT')
    assert get_product_category({"Product Name": "JAMESON IRISH WHISKEY CASKMATES (STOUT EDITION)"}) == "IMFL"
    # Old Monk Beer must be BEER
    assert get_product_category({"Product Name": "OLD MONK THE ORIGINAL PLATINUM STRONG BEER"}) == "BEER"
    # Standard beers
    assert get_product_category({"Product Name": "KINGFISHER ORIGINAL STRONG BEER"}) == "BEER"
    assert get_product_category({"Product Name": "BUDWEISER MAGNUM BEER"}) == "BEER"
    assert get_product_category({"Product Name": "TUBORG STRONG BEER"}) == "BEER"
    assert get_product_category({"Product Name": "BREEZER PREMIUM DELUXE TASTY BLUEBERRY"}) == "BEER"
    assert get_product_category({"Product Name": "HOEGAARDEN WITBIER"}) == "BEER"
    # Country Spirit
    assert get_product_category({"Product Name": "MASTI"}) == "CS"
    assert get_product_category({"Product Name": "RHINO NO 1"}) == "CS"
    assert get_product_category({"Bond Type": "CS", "Product Name": "SPECIAL"}) == "CS"
    # Standard IMFL
    assert get_product_category({"Product Name": "AFTER DARK BLUE RARE GRAIN WHISKY"}) == "IMFL"
    assert get_product_category({"Product Name": "AC BLACK LUXURY PURE GRAIN WHISKY"}) == "IMFL"
    print("✅ test_product_categorization passed!")

def test_monotonic_completed_preservation():
    from reconciler import get_unique_indent_id, get_unique_permit_key, clean_permit_records
    
    # Simulate run 1 with 2 verified completed SKUs (total 15 cases)
    run1_records = [
        {
            "Date": "04-Nov-2026",
            "Bond Type": "IMFL",
            "Indent Number": "IND_TEST_01",
            "Permit Number": "PER_TEST_01",
            "Transit Pass": "TP_TEST_01",
            "Licensee Name": "TEST RETAILER",
            "Status": "COMPLETED",
            "Product Name": "ROYAL STAG WHISKY",
            "Pack Size": "750/12",
            "Cases": 10,
            "Bottles": 0
        },
        {
            "Date": "04-Nov-2026",
            "Bond Type": "IMFL",
            "Indent Number": "IND_TEST_01",
            "Permit Number": "PER_TEST_01",
            "Transit Pass": "TP_TEST_01",
            "Licensee Name": "TEST RETAILER",
            "Status": "COMPLETED",
            "Product Name": "IMPERIAL BLUE WHISKY",
            "Pack Size": "375/24",
            "Cases": 5,
            "Bottles": 0
        }
    ]
    
    # Simulate run 2 where IND_TEST_01 experienced extraction error (0 cases) and IND_TEST_02 succeeded (20 cases)
    run2_records = [
        {
            "Date": "04-Nov-2026",
            "Bond Type": "IMFL",
            "Indent Number": "IND_TEST_01",
            "Permit Number": "PER_TEST_01",
            "Transit Pass": "TP_TEST_01",
            "Status": "COMPLETED",
            "Product Name": "EXTRACTION_FAILED",
            "Pack Size": "Unknown",
            "Cases": 0,
            "Bottles": 0,
            "extraction_error": True
        },
        {
            "Date": "04-Nov-2026",
            "Bond Type": "IMFL",
            "Indent Number": "IND_TEST_02",
            "Permit Number": "PER_TEST_02",
            "Transit Pass": "TP_TEST_02",
            "Licensee Name": "TEST RETAILER 2",
            "Status": "COMPLETED",
            "Product Name": "MAGIC MOMENTS VODKA",
            "Pack Size": "750/12",
            "Cases": 20,
            "Bottles": 0
        }
    ]
    
    # Merge using our robust monotonic logic
    existing_completed = run1_records
    existing_indent_cases = {get_unique_indent_id(r): float(r.get("Cases") or 0) for r in existing_completed}
    
    current_indent_cases = {}
    current_indent_has_valid_skus = set()
    for c in run2_records:
        pname = str(c.get("Product Name") or "").strip().upper()
        is_err = bool(c.get("extraction_error")) or (pname in ["EXTRACTION_FAILED", "UNKNOWN", ""])
        if not is_err:
            iid = get_unique_indent_id(c)
            current_indent_cases[iid] = current_indent_cases.get(iid, 0.0) + float(c.get("Cases") or 0)
            if float(c.get("Cases") or 0) > 0:
                current_indent_has_valid_skus.add(iid)

    degraded_or_missing_indents = set()
    for iid, ex_c in existing_indent_cases.items():
        inc_c = current_indent_cases.get(iid, 0.0)
        if iid not in current_indent_has_valid_skus or inc_c < (ex_c - 0.01):
            degraded_or_missing_indents.add(iid)

    assert "IND_TEST_01" in degraded_or_missing_indents, "IND_TEST_01 must be flagged as degraded/missing"

    protected = [
        c for c in run2_records
        if not (
            get_unique_indent_id(c) in degraded_or_missing_indents
            or bool(c.get("extraction_error"))
            or str(c.get("Product Name") or "").strip().upper() in ["EXTRACTION_FAILED", "UNKNOWN", ""]
        )
    ]
    
    current_keys = {get_unique_permit_key(c) for c in protected}
    for ex in existing_completed:
        ex_iid = get_unique_indent_id(ex)
        ex_key = get_unique_permit_key(ex)
        if ex_iid in degraded_or_missing_indents or ex_key not in current_keys:
            if ex_key not in current_keys:
                protected.append(ex)
                current_keys.add(ex_key)

    cleaned = clean_permit_records(protected)
    assert len(cleaned) == 3, f"Expected 3 records (2 from run1 + 1 from run2), got {len(cleaned)}"
    tot_cases = sum(r["Cases"] for r in cleaned)
    assert tot_cases == 35.0, f"Expected 35 cases (15 + 20), got {tot_cases}"
    print("✅ test_monotonic_completed_preservation passed!")

if __name__ == "__main__":
    test_reconciliation()
    test_no_pending_completed_overlap()
    test_brand_variant_separation()
    test_historical_completed_indent_purges_pending()
    test_empty_ghost_row_dropped()
    test_pack_size_normalization()
    test_ghost_line_pruning()
    test_product_categorization()
    test_monotonic_completed_preservation()
