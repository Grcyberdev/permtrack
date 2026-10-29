import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
import auth

def test_godown_monthly_summary_effective_dates():
    client = TestClient(app)
    
    # Generate auth cookie
    token = auth.create_session_token("rajdeep", remember_me=True)
    client.cookies.set("permtrack_session", token)
    
    resp = client.get("/api/godown/monthly-summary")
    assert resp.status_code == 200, f"Failed: {resp.text}"
    
    data = resp.json()
    assert "months" in data
    assert len(data["months"]) > 0
    
    # Find October 2026
    oct_month = None
    for m in data["months"]:
        if "October" in m.get("month_key", "") or "October" in m.get("month_name", ""):
            oct_month = m
            break
            
    assert oct_month is not None, "October 2026 data missing from monthly summary"
    
    # Check days
    days_dict = {d["date_key"]: d for d in oct_month["days"]}
    
    # Oct 18 should be closed with 0 permtrack cases
    if "20261018" in days_dict:
        oct18 = days_dict["20261018"]
        assert oct18["is_closed"] is True, "Oct 18 Sunday should be closed"
        assert oct18["permtrack_cases"] == 0.0, f"Oct 18 cases should be 0, got {oct18['permtrack_cases']}"
        assert oct18["difference"] == 0.0, f"Oct 18 difference should be 0, got {oct18['difference']}"
        
    # Oct 16 should have > 12000 cases (credited with late-night dispatches)
    if "20261016" in days_dict:
        oct16 = days_dict["20261016"]
        assert oct16["permtrack_cases"] > 12000, f"Oct 16 cases should be > 12000, got {oct16['permtrack_cases']}"
