import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
import auth

def test_analytics_movement_all_modes():
    client = TestClient(app)
    token = auth.create_session_token("rajdeep", remember_me=True)
    client.cookies.set("permtrack_session", token)

    # 1. Day Mode
    resp_day = client.get("/api/analytics/movement?mode=day&date=2026-10-30")
    assert resp_day.status_code == 200
    d_data = resp_day.json()
    assert d_data["horizon"]["mode"] == "day"
    assert d_data["summary"]["total_cases"] > 0
    assert len(d_data["brands_full"]) > 0
    assert len(d_data["daily_series"]) == 1

    # 2. Week Mode
    resp_week = client.get("/api/analytics/movement?mode=week&date=2026-10-30")
    assert resp_week.status_code == 200
    w_data = resp_week.json()
    assert w_data["horizon"]["mode"] == "week"
    assert len(w_data["daily_series"]) == 7
    assert "delta_cases_pct" in w_data["previous_period_summary"]

    # 3. Month Mode
    resp_month = client.get("/api/analytics/movement?mode=month&date=2026-10-30")
    assert resp_month.status_code == 200
    m_data = resp_month.json()
    assert m_data["horizon"]["mode"] == "month"
    assert len(m_data["daily_series"]) == 31
    assert len(m_data["brands_full"]) > 15  # Un-truncated!

    # 4. Range Mode
    resp_range = client.get("/api/analytics/movement?mode=range&start_date=2026-10-25&end_date=2026-10-30")
    assert resp_range.status_code == 200
    r_data = resp_range.json()
    assert r_data["horizon"]["mode"] == "range"
    assert len(r_data["daily_series"]) == 6

    # 5. Godown Key Normalization
    resp_recon = client.get("/api/godown/reconciliation?date_key=backup_permits_20261003_000000.json")
    assert resp_recon.status_code == 200
    recon_json = resp_recon.json()
    assert recon_json["date_key"] == "20261003"
    assert recon_json["data"].get("godown_cases") == 9091.0
