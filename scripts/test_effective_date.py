import os
import sys
import pytest
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
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
