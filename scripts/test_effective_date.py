import os
import sys
import pytest
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reconciler import get_record_effective_date_key, parse_effective_date

def test_effective_date_priority_challan():
    # Challan date takes highest priority
    record = {
        "Challan Date": "16-Oct-2026",
        "Transit Pass": "TP309717102600123",
        "Date": "18-Oct-2026"
    }
    assert get_record_effective_date_key(record, "20261019") == "20261016"
    dt = parse_effective_date(record)
    assert dt == datetime(2026, 10, 16)

def test_effective_date_transit_pass_fallback():
    # When Challan Date is empty, fallback to Transit Pass embedded date
    record = {
        "Challan Date": "",
        "Transit Pass": "TP309717102600123",
        "Date": "18-Oct-2026"
    }
    assert get_record_effective_date_key(record, "20261019") == "20261017"
    dt = parse_effective_date(record)
    assert dt == datetime(2026, 10, 17)

def test_effective_date_record_date_fallback():
    # When Challan Date and Transit Pass are empty/invalid, fallback to Date
    record = {
        "Challan Date": "",
        "Transit Pass": "INVALID_TP",
        "Date": "18-Oct-2026"
    }
    assert get_record_effective_date_key(record, "20261019") == "20261018"
    dt = parse_effective_date(record)
    assert dt == datetime(2026, 10, 18)

def test_effective_date_default_key_fallback():
    # When everything is missing, fallback to default_date_key
    record = {
        "Challan Date": None,
        "Transit Pass": None,
        "Date": None
    }
    assert get_record_effective_date_key(record, "20261019") == "20261019"
    default_dt = datetime(2026, 10, 19)
    assert parse_effective_date(record, default_dt) == default_dt

def test_effective_date_formats():
    # Supports various date formats in Challan Date
    for fmt_val in ["16-Oct-2026", "16-10-2026", "2026-10-16", "16/10/2026"]:
        rec = {"Challan Date": fmt_val}
        assert get_record_effective_date_key(rec) == "20261016"

def test_backfill_missing_mrps():
    from reconciler import backfill_missing_mrps, normalize_brand_key, normalize_size
    sku_rates = {
        f"{normalize_brand_key('ROYAL STAG WHISKY')}_{normalize_size('750')}": 6500.0,
        f"{normalize_brand_key('TUBORG STRONG BEER')}_{normalize_size('650')}": 2400.0
    }
    records = [
        {
            "Product Name": "ROYAL STAG WHISKY",
            "Size": "750",
            "Pack Size": "750/12",
            "Cases": 10,
            "Bottles": 0,
            "Total MRP": 0.0,
            "Status": "COMPLETED"
        },
        {
            "Product Name": "TUBORG STRONG BEER",
            "Size": "650",
            "Pack Size": "650/12",
            "Cases": 5,
            "Bottles": 0,
            "Total MRP": 0.0,
            "Status": "COMPLETED"
        }
    ]
    backfilled = backfill_missing_mrps(records, sku_rates)
    assert backfilled[0]["Total MRP"] == 65000.0
    assert backfilled[1]["Total MRP"] == 12000.0

def test_strict_date_partitioning():
    records = [
        {"Indent Number": "IND1", "Transit Pass": "TP3097281026001", "Challan Date": "28-Oct-2026", "Status": "COMPLETED", "Cases": 50},
        {"Indent Number": "IND2", "Transit Pass": "TP3097291026002", "Challan Date": "29-Oct-2026", "Status": "COMPLETED", "Cases": 30},
        {"Indent Number": "IND3", "Transit Pass": "", "Challan Date": "", "Date": "29-Oct-2026", "Status": "PENDING", "Cases": 15}
    ]
    target_key = "20261029"
    partitioned = [
        r for r in records
        if str(r.get("Status", "")).upper() == "PENDING" or get_record_effective_date_key(r, default_date_key=target_key) == target_key
    ]
    assert len(partitioned) == 2
    assert {r["Indent Number"] for r in partitioned} == {"IND2", "IND3"}

def test_sync_bundled_data_repairs_truncated(tmp_path, monkeypatch):
    import json
    from app import sync_bundled_data
    # Create fake bundled config and target data dir
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    target = tmp_path / "target"
    target.mkdir()

    # Bundled has 10 completed dispatches
    b_records = [{"Indent Number": f"IND{i}", "Status": "COMPLETED", "Cases": 10, "Total MRP": 1000} for i in range(10)]

    monkeypatch.setattr("app.PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("app.automation_utils.get_data_dir", lambda: str(target))
    monkeypatch.setattr("scripts.automation_utils.get_data_dir", lambda: str(target))

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "backup_permits_99990101_000000.json").write_text(json.dumps(b_records))

    # Target has corrupted 1 record
    t_records = [{"Indent Number": "IND0", "Status": "COMPLETED", "Cases": 10, "Total MRP": 1000}]
    (target / "backup_permits_99990101_000000.json").write_text(json.dumps(t_records))

    res = sync_bundled_data()
    assert res["status"] == "success"
    
    # Target should now be repaired with 10 records
    repaired = json.loads((target / "backup_permits_99990101_000000.json").read_text())
    assert len(repaired) == 10

def test_forward_cross_day_attribution_and_pending_purge(tmp_path, monkeypatch):
    import json
    from starlette.testclient import TestClient
    from app import app
    import scripts.auth as auth

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Pre-populate 02-Nov backup with 1 completed and 2 pending
    nov2_initial = [
        {"Indent Number": "IND_NOV2_A", "Transit Pass": "TP3097021126001", "Challan Date": "02-Nov-2026", "Status": "COMPLETED", "Cases": 50, "Total MRP": 50000, "Date": "02-Nov-2026"},
        {"Indent Number": "IND_NOV2_B", "Transit Pass": "", "Challan Date": "", "Status": "PENDING", "Cases": 20, "Total MRP": 20000, "Date": "02-Nov-2026", "Application Date": "02-Nov-2026"},
        {"Indent Number": "IND_NOV2_TRULY_PENDING", "Transit Pass": "", "Challan Date": "", "Status": "PENDING", "Cases": 10, "Total MRP": 10000, "Date": "02-Nov-2026", "Application Date": "02-Nov-2026"}
    ]
    (data_dir / "backup_permits_20261102_000000.json").write_text(json.dumps(nov2_initial))

    monkeypatch.setattr("app.automation_utils.get_data_dir", lambda: str(data_dir))
    monkeypatch.setattr("scripts.automation_utils.get_data_dir", lambda: str(data_dir))

    client = TestClient(app)
    # Simulate scraper run for 02-Nov that finds IND_NOV2_B was approved on 03-Nov with Form-34 Challan Date = 03-Nov-2026
    upload_payload = {
        "secret": "test_secret",
        "date": "02-11-2026",
        "has_errors": False,
        "failed_bonds": [],
        "records": [
            {"Indent Number": "IND_NOV2_A", "Transit Pass": "TP3097021126001", "Challan Date": "02-Nov-2026", "Status": "COMPLETED", "Cases": 50, "Total MRP": 50000, "Date": "02-Nov-2026"},
            {"Indent Number": "IND_NOV2_B", "Transit Pass": "TP3097031126002", "Challan Date": "03-Nov-2026", "Status": "COMPLETED", "Cases": 20, "Total MRP": 20000, "Date": "02-Nov-2026"},
            {"Indent Number": "IND_NOV2_TRULY_PENDING", "Transit Pass": "", "Challan Date": "", "Status": "PENDING", "Cases": 10, "Total MRP": 10000, "Date": "02-Nov-2026", "Application Date": "02-Nov-2026"}
        ]
    }
    monkeypatch.setenv("WEBHOOK_SECRET", "test_secret")
    resp = client.post("/api/upload-results", json=upload_payload)
    assert resp.status_code == 200

    # Verify 02-Nov backup: IND_NOV2_B must NOT be pending and must NOT be completed in 02-Nov!
    # Only IND_NOV2_A (completed on 02-Nov) and IND_NOV2_TRULY_PENDING (truly pending) should be in 02-Nov!
    nov2_after = json.loads((data_dir / "backup_permits_20261102_000000.json").read_text())
    nov2_iids = {r["Indent Number"] for r in nov2_after}
    assert nov2_iids == {"IND_NOV2_A", "IND_NOV2_TRULY_PENDING"}
    
    nov2_statuses = {r["Indent Number"]: r["Status"] for r in nov2_after}
    assert nov2_statuses["IND_NOV2_A"] == "COMPLETED"
    assert nov2_statuses["IND_NOV2_TRULY_PENDING"] == "PENDING"

    # Verify forward attribution: 03-Nov backup MUST exist and contain IND_NOV2_B as COMPLETED!
    assert (data_dir / "backup_permits_20261103_000000.json").exists()
    nov3_data = json.loads((data_dir / "backup_permits_20261103_000000.json").read_text())
    assert len(nov3_data) == 1
    assert nov3_data[0]["Indent Number"] == "IND_NOV2_B"
    assert nov3_data[0]["Status"] == "COMPLETED"
    assert nov3_data[0]["Challan Date"] == "03-Nov-2026"



