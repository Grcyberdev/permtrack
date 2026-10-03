import os
import sys
import json
import glob
import asyncio
import argparse
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

IST = timezone(timedelta(hours=5, minutes=30))

def get_now_ist() -> datetime:
    return datetime.now(IST)

# Add scripts directory to path to import helpers
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(PROJECT_ROOT, "scripts"))

from pdf_report import generate_report_pdf
from reconciler import reconcile_permits, get_reconciliation_summary, parse_date_str, get_unique_permit_key
import automation_utils
import auth

app = FastAPI(title="PermTrack - Assam Excise Revenue Tracker")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------
# Authentication & Access Control Endpoints
# -------------------------------------------------------------
@app.post("/api/auth/login")
async def auth_login(request: Request):
    """
    Validates executive credentials and creates an HMAC-SHA256 session cookie.
    """
    try:
        body = await request.json()
        username = body.get("username", "").strip()
        password = body.get("password", "")
        remember_me = bool(body.get("remember_me", False))

        user = auth.authenticate_user(username, password)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "error": "Invalid username or password"}
            )

        token = auth.create_session_token(user["username"], remember_me=remember_me)
        max_age = (30 * 24 * 3600) if remember_me else (24 * 3600)

        response = JSONResponse(content={
            "status": "success",
            "token": token,
            "user": user
        })

        is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
        response.set_cookie(
            key="permtrack_session",
            value=token,
            max_age=max_age,
            httponly=True,
            samesite="lax",
            secure=is_https
        )
        return response
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Login failed: {str(e)}"})

@app.get("/api/auth/status")
async def auth_status(request: Request):
    """
    Returns authentication state for current browser session.
    """
    user = auth.get_current_user(request)
    if user:
        return JSONResponse(content={"authenticated": True, "user": user})
    return JSONResponse(content={"authenticated": False})

@app.post("/api/auth/logout")
async def auth_logout():
    """
    Clears the session cookie.
    """
    response = JSONResponse(content={"status": "success", "message": "Logged out successfully"})
    response.delete_cookie("permtrack_session")
    return response

# Serve static frontend files
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return HTMLResponse(content="<h1>Permit Tracker Dashboard</h1><p>Static index.html not found.</p>", status_code=404)

def get_sorted_backup_files(config_dir):
    """
    Returns backup files sorted chronologically by date key (YYYYMMDD) descending,
    with mtime as secondary tiebreaker.
    """
    files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
    files = [f for f in files if "latest.json" not in f]
    
    def sort_key(filepath):
        basename = os.path.basename(filepath)
        ts = basename.replace("backup_permits_", "").replace(".json", "")
        date_key = ts.split("_")[0]
        try:
            mtime = os.path.getmtime(filepath)
        except:
            mtime = 0
        return (date_key if date_key.isdigit() and len(date_key) == 8 else "00000000", mtime)
        
    files.sort(key=sort_key, reverse=True)
    return files

@app.get("/api/today-permits")
async def get_today_permits(request: Request, filename: str = None, lookback_days: int = 7):
    """
    Returns latest scraped permits or specified backup file with 7-day carry-over reconciliation.
    Requires authenticated executive session.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})

    global LATEST_WEBHOOK_DATA
    config_dir = automation_utils.get_data_dir()
    
    if not filename and LATEST_WEBHOOK_DATA:
        data = LATEST_WEBHOOK_DATA
        latest_backup_name = "latest_webhook.json"
    else:
        if filename:
            filename = os.path.basename(filename)
            target_path = os.path.join(config_dir, filename)
            if not os.path.exists(target_path) or not filename.startswith("backup_permits_"):
                return JSONResponse(status_code=404, content={"error": "Backup file not found"})
            latest_backup = target_path
        else:
            backup_files = get_sorted_backup_files(config_dir)
            
            if not backup_files:
                fallback = os.path.join(config_dir, "backup_permits_latest.json")
                if os.path.exists(fallback):
                    latest_backup = fallback
                else:
                    return JSONResponse(content={"date": None, "pending": [], "completed": [], "summary": {}})
            else:
                latest_backup = backup_files[0]
            
        try:
            with open(latest_backup, "r") as f:
                data = json.load(f)
            latest_backup_name = os.path.basename(latest_backup)
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to read latest backup data: {str(e)}"}
            )
            
    target_date = None
    for item in data:
        if item.get("Date"):
            target_date = item.get("Date")
            break
            
    # Apply reconciliation across past lookback_days
    reconciled_data = reconcile_permits(data, target_date, config_dir, lookback_days=lookback_days)
    summary_metrics = get_reconciliation_summary(reconciled_data)
    
    pending = []
    completed = []
    
    for item in reconciled_data:
        status = item.get("Status", "").upper()
        if status == "PENDING":
            pending.append(item)
        elif status == "COMPLETED":
            completed.append(item)
            
    last_updated_str = "Live (Updated)"
    last_updated_ts = None
    if latest_backup and os.path.exists(latest_backup):
        try:
            mtime = os.path.getmtime(latest_backup)
            last_updated_ts = mtime
            from datetime import datetime, timezone, timedelta
            ist = timezone(timedelta(hours=5, minutes=30))
            dt_ist = datetime.fromtimestamp(mtime, tz=ist)
            last_updated_str = dt_ist.strftime("%d-%b-%Y, %I:%M %p")
        except Exception:
            pass

    response_headers = {}
    if filename and filename.startswith("backup_permits_") and not filename.endswith("latest.json"):
        response_headers["Cache-Control"] = "public, max-age=3600"

    return JSONResponse(content={
        "date": target_date,
        "filename": latest_backup_name,
        "last_updated": last_updated_str,
        "last_updated_ts": last_updated_ts,
        "pending": pending,
        "completed": completed,
        "summary": summary_metrics
    }, headers=response_headers)

@app.get("/api/download-pdf")
async def download_pdf_report(request: Request, filename: str = None):
    """
    Retrieves selected permit JSON file and returns PDF report.
    Requires authenticated executive session.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})

    config_dir = automation_utils.get_data_dir()
    
    if filename:
        filename = os.path.basename(filename)
        target_path = os.path.join(config_dir, filename)
        if not os.path.exists(target_path) or not filename.startswith("backup_permits_"):
            return JSONResponse(status_code=404, content={"error": "Backup file not found"})
        latest_backup = target_path
    else:
        backup_files = get_sorted_backup_files(config_dir)
        if not backup_files:
            fallback = os.path.join(config_dir, "backup_permits_latest.json")
            if os.path.exists(fallback):
                latest_backup = fallback
            else:
                return JSONResponse(
                    status_code=404,
                    content={"error": "No cached permit files found to generate PDF report."}
                )
        else:
            latest_backup = backup_files[0]
        
    try:
        with open(latest_backup, "r") as f:
            data = json.load(f)
            
        pdf_bytes = generate_report_pdf(data)
        
        target_date = "report"
        for item in data:
            if item.get("Date"):
                target_date = item.get("Date").replace("-", "_")
                break
                
        headers = {
            "Content-Disposition": f"attachment; filename=permit_report_{target_date}.pdf"
        }
        
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate PDF: {str(e)}"}
        )

@app.get("/api/backups")
async def get_backups(request: Request):
    """
    Returns deduplicated, hierarchically sorted list of available date backups.
    Requires authenticated executive session.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
    config_dir = automation_utils.get_data_dir()
    backup_files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
    backup_files = [f for f in backup_files if "latest.json" not in f]
    
    by_date = {}
    today_str = get_now_ist().strftime("%Y%m%d")
    yesterday_str = (get_now_ist() - timedelta(days=1)).strftime("%Y%m%d")
    
    for filepath in backup_files:
        basename = os.path.basename(filepath)
        ts = basename.replace("backup_permits_", "").replace(".json", "")
        date_key = ts.split("_")[0]
        
        if not date_key.isdigit() or len(date_key) != 8 or date_key < "20260101":
            continue
            
        mtime = os.path.getmtime(filepath)
        if date_key not in by_date or mtime > by_date[date_key]["mtime"]:
            by_date[date_key] = {
                "filepath": filepath,
                "filename": basename,
                "mtime": mtime,
                "date_key": date_key
            }
            
    sorted_dates = sorted(by_date.keys(), reverse=True)
    
    results = []
    for date_key in sorted_dates:
        item = by_date[date_key]
        year = date_key[0:4]
        month = date_key[4:6]
        day = date_key[6:8]
        
        try:
            dt = datetime(int(year), int(month), int(day), tzinfo=IST)
            formatted_date = dt.strftime("%d-%b-%Y")
            day_of_week = dt.strftime("%a")
            month_year = dt.strftime("%B %Y")
        except:
            formatted_date = f"{day}-{month}-{year}"
            day_of_week = ""
            month_year = ""
            
        if date_key == today_str:
            display_name = f"Today ({formatted_date})"
        elif date_key == yesterday_str:
            display_name = f"Yesterday ({formatted_date})"
        else:
            display_name = formatted_date

        total_count = 0
        dispatched_count = 0
        pending_count = 0
        try:
            with open(item["filepath"], "r", encoding="utf-8") as bf:
                bdata = json.load(bf)
                if isinstance(bdata, list):
                    total_count = len(bdata)
                    for rec in bdata:
                        if rec.get("Status") == "PENDING":
                            pending_count += 1
                        else:
                            dispatched_count += 1
                elif isinstance(bdata, dict):
                    comp = bdata.get("completed", [])
                    pend = bdata.get("pending", [])
                    dispatched_count = len(comp)
                    pending_count = len(pend)
                    total_count = dispatched_count + pending_count
        except Exception:
            pass

        # Option B: Closed / No Data if dispatched_count == 0 (no loading occurred that day)
        is_closed = (dispatched_count == 0)
            
        results.append({
            "filename": item["filename"],
            "display": display_name,
            "date_key": date_key,
            "formatted_date": formatted_date,
            "day_of_week": day_of_week,
            "month_year": month_year,
            "total_count": total_count,
            "dispatched_count": dispatched_count,
            "pending_count": pending_count,
            "is_closed": is_closed
        })
        
    return JSONResponse(content=results)

@app.get("/api/godown/monthly-summary")
async def get_godown_monthly_summary(request: Request):
    """
    Returns monthly aggregated reconciliation data comparing PermTrack calculated sales
    vs physical Godown sales, cumulative totals, discrepancies, and month-by-month summaries.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
        
    config_dir = automation_utils.get_data_dir()
    recon_filepath = os.path.join(config_dir, GODOWN_RECON_FILE)
    recon_data = {}
    if os.path.exists(recon_filepath):
        try:
            with open(recon_filepath, "r", encoding="utf-8") as f:
                recon_data = json.load(f)
        except Exception:
            pass

    backup_files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
    backup_files = [f for f in backup_files if "latest.json" not in f]

    by_date = {}
    for filepath in backup_files:
        basename = os.path.basename(filepath)
        ts = basename.replace("backup_permits_", "").replace(".json", "")
        date_key = ts.split("_")[0]
        if not date_key.isdigit() or len(date_key) != 8 or date_key < "20260101":
            continue
        mtime = os.path.getmtime(filepath)
        if date_key not in by_date or mtime > by_date[date_key]["mtime"]:
            by_date[date_key] = {"filepath": filepath, "filename": basename, "mtime": mtime}

    def get_b_per_cs(size_val):
        try:
            s = int(str(size_val).replace("ml", "").strip())
            if s >= 250:
                return 24
            return 48
        except:
            return 24

    def get_cat(item):
        b = (item.get("Bond Type") or "").upper()
        c = (item.get("Category") or "").upper()
        p = (item.get("Product Name") or "").upper()
        if b == "CS" or "COUNTRY" in c or "MASTI" in p or "CS " in p:
            return "CS"
        beer_keywords = ["BEER", "DRAUGHT", "LAGER", "ALE", "STOUT", "PILSNER", "CIDER", "WHEAT",
                         "BIRA", "KINGFISHER", "TUBORG", "CARLSBERG", "BUDWEISER", "HE-MAN",
                         "GODFATHER", "SIMBA", "CORONA", "HEINEKEN", "FOSTERS", "BREEZER",
                         "BACARDI BREEZER", "HAYWARDS 5000", "KNOCK OUT", "KALYANI", "BLACK FORT",
                         "ROYAL CHALLENGE BEER", "STERREN", "HUNTER", "BROCODE", "WHITE RHINO",
                         "LONE WOLF", "SIX FIELDS", "MACH 11", "HOEGAARDEN", "STELLA", "MILLER",
                         "SUPER STRONG BEER", "PREMIUM LAGER"]
        if any(k in c or k in p for k in beer_keywords):
            return "BEER"
        return "IMFL"

    # Build per-day data sorted chronologically
    sorted_date_keys = sorted(by_date.keys())
    
    # Group by month
    months = {}
    for date_key in sorted_date_keys:
        filepath = by_date[date_key]["filepath"]
        year, month, day = int(date_key[:4]), int(date_key[4:6]), int(date_key[6:8])
        try:
            dt = datetime(year, month, day, tzinfo=IST)
            date_str = dt.strftime("%d-%b-%Y")
            day_name = dt.strftime("%A")
            month_key = dt.strftime("%B %Y")
            month_name = dt.strftime("%B")
        except Exception:
            date_str = f"{day:02d}-{month:02d}-{year}"
            day_name = ""
            month_key = f"{month:02d}-{year}"
            month_name = month_key

        dispatched_cases = 0.0
        dispatched_bottles = 0
        dispatched_cs_eq = 0.0
        permits_count = 0
        day_mrp = 0.0
        day_beer_eq = 0.0
        day_imfl_eq = 0.0
        day_cs_eq = 0.0

        if month_key not in months:
            months[month_key] = {
                "month_name": month_name,
                "month_key": month_key,
                "days": [],
                "totals": {
                    "permtrack_cases": 0.0,
                    "godown_cases": 0.0,
                    "has_godown_entries": False,
                    "difference": 0.0,
                    "total_mrp": 0.0,
                    "beer_eq": 0.0,
                    "imfl_eq": 0.0,
                    "cs_eq": 0.0,
                    "active_days": 0
                },
                "brand_totals": {},
                "party_totals": {}
            }

        m_dict = months[month_key]

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                bdata = json.load(f)
                if isinstance(bdata, list):
                    for rec in bdata:
                        if rec.get("Status") == "PENDING":
                            continue
                        permits_count += 1
                        c = float(rec.get("Cases") or 0)
                        b = int(rec.get("Bottles") or 0)
                        eq = b / get_b_per_cs(rec.get("Size"))
                        tot_eq = c + eq
                        mrp_val = float(rec.get("Total MRP") or 0)
                        cat = get_cat(rec)
                        brand_name = rec.get("Product Name") or "Unknown Brand"
                        party_name = rec.get("Retailer Name") or "Unknown Licensee"

                        dispatched_cases += c
                        dispatched_bottles += b
                        dispatched_cs_eq += eq
                        day_mrp += mrp_val

                        if cat == "BEER":
                            day_beer_eq += tot_eq
                        elif cat == "CS":
                            day_cs_eq += tot_eq
                        else:
                            day_imfl_eq += tot_eq

                        m_dict["brand_totals"][brand_name] = m_dict["brand_totals"].get(brand_name, 0.0) + tot_eq
                        m_dict["party_totals"][party_name] = m_dict["party_totals"].get(party_name, 0.0) + tot_eq
        except Exception:
            pass

        permtrack_total_cases = round(dispatched_cases + dispatched_cs_eq, 2)
        is_closed = (permits_count == 0)
        if not is_closed:
            m_dict["totals"]["active_days"] += 1

        m_dict["totals"]["total_mrp"] += round(day_mrp, 2)
        m_dict["totals"]["beer_eq"] += round(day_beer_eq, 2)
        m_dict["totals"]["imfl_eq"] += round(day_imfl_eq, 2)
        m_dict["totals"]["cs_eq"] += round(day_cs_eq, 2)

        # Godown figure from saved reconciliation
        recon_entry = recon_data.get(date_key, {})
        godown_cases = recon_entry.get("godown_cases")
        updated_at = recon_entry.get("updated_at")
        updated_by = recon_entry.get("updated_by")

        difference = None
        if godown_cases is not None:
            try:
                diff_val = float(godown_cases) - permtrack_total_cases
                difference = round(diff_val, 2)
            except (ValueError, TypeError):
                pass

        months[month_key]["days"].append({
            "date_key": date_key,
            "filename": by_date[date_key]["filename"],
            "date_str": date_str,
            "day": day_name,
            "permtrack_cases": permtrack_total_cases,
            "cases_only": round(dispatched_cases, 2),
            "bottles_only": dispatched_bottles,
            "mrp": round(day_mrp, 2),
            "beer_eq": round(day_beer_eq, 2),
            "imfl_eq": round(day_imfl_eq, 2),
            "cs_eq": round(day_cs_eq, 2),
            "godown_cases": godown_cases,
            "difference": difference,
            "is_closed": is_closed,
            "updated_at": updated_at,
            "updated_by": updated_by
        })

    # Compute cumulative totals and prepare top rankings
    result_months = []
    for month_key, mdata in months.items():
        cum_permtrack = 0.0
        cum_godown = 0.0
        has_godown = False
        tot_godown = 0.0

        for day in mdata["days"]:
            cum_permtrack += day["permtrack_cases"]
            day["cumulative_permtrack"] = round(cum_permtrack, 2)

            if day["godown_cases"] is not None:
                has_godown = True
                g_val = float(day["godown_cases"])
                cum_godown += g_val
                tot_godown += g_val
                day["cumulative_godown"] = round(cum_godown, 2)
                day["cumulative_difference"] = round(cum_godown - cum_permtrack, 2)
            else:
                day["cumulative_godown"] = None
                day["cumulative_difference"] = None

        mdata["totals"]["permtrack_cases"] = round(cum_permtrack, 2)
        mdata["totals"]["godown_cases"] = round(tot_godown, 2) if has_godown else None
        mdata["totals"]["has_godown_entries"] = has_godown
        mdata["totals"]["difference"] = round(tot_godown - cum_permtrack, 2) if has_godown else None

        # Sort top 10 brands & retailers for the month
        top_brands_sorted = sorted(mdata["brand_totals"].items(), key=lambda x: x[1], reverse=True)[:10]
        top_parties_sorted = sorted(mdata["party_totals"].items(), key=lambda x: x[1], reverse=True)[:10]
        mdata["top_brands"] = [{"name": k, "cases": round(v, 2)} for k, v in top_brands_sorted]
        mdata["top_parties"] = [{"name": k, "cases": round(v, 2)} for k, v in top_parties_sorted]
        mdata.pop("brand_totals", None)
        mdata.pop("party_totals", None)

        result_months.append(mdata)

    # Return in reverse chronological order for recent months first
    return JSONResponse(content={"months": list(reversed(result_months))})

GODOWN_RECON_FILE = "godown_reconciliation.json"

@app.get("/api/godown/reconciliation")
async def get_godown_reconciliation(request: Request, date_key: str = None):
    """
    Returns saved physical godown counts for reconciliation across devices.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
    
    config_dir = automation_utils.get_data_dir()
    filepath = os.path.join(config_dir, GODOWN_RECON_FILE)
    recon_data = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                recon_data = json.load(f)
        except Exception:
            pass
            
    if date_key:
        clean_key = date_key.replace(".json", "").strip()
        item = recon_data.get(clean_key, {})
        return JSONResponse(content={"date_key": clean_key, "data": item})
        
    return JSONResponse(content=recon_data)

@app.post("/api/godown/reconciliation")
async def save_godown_reconciliation(request: Request):
    """
    Saves or clears physical godown count for a specific date dataset.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
        
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})
        
    date_key = str(body.get("date_key", "")).replace(".json", "").strip()
    val = body.get("godown_cases")
    
    if not date_key:
        return JSONResponse(status_code=400, content={"error": "Missing date_key"})
        
    config_dir = automation_utils.get_data_dir()
    os.makedirs(config_dir, exist_ok=True)
    filepath = os.path.join(config_dir, GODOWN_RECON_FILE)
    recon_data = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                recon_data = json.load(f)
        except Exception:
            recon_data = {}
            
    if val is None or str(val).strip() == "":
        recon_data.pop(date_key, None)
    else:
        try:
            val_float = float(val)
            recon_data[date_key] = {
                "godown_cases": val_float,
                "updated_at": get_now_ist().strftime("%d-%b-%Y %I:%M %p"),
                "updated_by": user.get("name") or user.get("username") or "Supervisor"
            }
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "Invalid godown cases number"})
            
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(recon_data, f, indent=2)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to save reconciliation: {e}"})
        
    return JSONResponse(content={
        "status": "success",
        "date_key": date_key,
        "entry": recon_data.get(date_key)
    })

LATEST_WEBHOOK_DATA = None

@app.post("/api/upload-results")
async def upload_results(request: Request):
    """
    Endpoint for GitHub Actions (or remote runners) to POST scraped JSON records to Fly.io.
    """
    global LATEST_WEBHOOK_DATA
    try:
        payload = await request.json()
        secret = payload.get("secret")
        expected_secret = os.environ.get("WEBHOOK_SECRET")
        
        if expected_secret and secret != expected_secret:
            return JSONResponse(status_code=403, content={"error": "Invalid webhook secret authorization"})
        
        records = payload.get("records", [])
        date_str = payload.get("date")
        
        config_dir = automation_utils.get_data_dir()
        os.makedirs(config_dir, exist_ok=True)
        
        from datetime import datetime, timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
        parsed_date = None
        target_dt = None
        
        if date_str:
            target_dt = parse_date_str(date_str)
            if target_dt:
                parsed_date = target_dt.strftime("%Y%m%d")
                
        if not target_dt:
            for item in records:
                d = item.get("Date")
                if d:
                    target_dt = parse_date_str(d)
                    if target_dt:
                        parsed_date = target_dt.strftime("%Y%m%d")
                        break
                        
        if not target_dt:
            target_dt = datetime.now(ist)
            parsed_date = target_dt.strftime("%Y%m%d")
            
        canonical_filename = f"backup_permits_{parsed_date}_000000.json"
        latest_filename = "backup_permits_latest.json"
        canonical_path = os.path.join(config_dir, canonical_filename)
        
        # Server-side merge protection: Preserve previously completed dispatches
        existing_completed = []
        if os.path.exists(canonical_path):
            try:
                with open(canonical_path, "r") as ef:
                    ex_data = json.load(ef)
                for it in ex_data:
                    if str(it.get("Status", "")).upper() == "COMPLETED":
                        existing_completed.append(it)
            except Exception: pass
            
        incoming_completed_keys = {get_unique_permit_key(it) for it in records if str(it.get("Status", "")).upper() == "COMPLETED"}
        incoming_completed_bonds = {str(it.get("Bond Type", "")).upper() for it in records if str(it.get("Status", "")).upper() == "COMPLETED"}
        
        records_to_reconcile = list(records)
        for ex in existing_completed:
            ex_key = get_unique_permit_key(ex)
            ex_bond = str(ex.get("Bond Type", "")).upper()
            if ex_bond not in incoming_completed_bonds or ex_key not in incoming_completed_keys:
                records_to_reconcile.append(ex)
                incoming_completed_keys.add(ex_key)
                
        # Reconcile merged records with 7-day backups
        reconciled_records = reconcile_permits(records_to_reconcile, target_dt, config_dir, lookback_days=7)
        LATEST_WEBHOOK_DATA = reconciled_records
            
        with open(os.path.join(config_dir, canonical_filename), "w") as f:
            json.dump(reconciled_records, f, indent=4)
        with open(os.path.join(config_dir, latest_filename), "w") as f:
            json.dump(reconciled_records, f, indent=4)
            
        # Clean up any extra timestamp files for the same target date
        for old_f in glob.glob(os.path.join(config_dir, f"backup_permits_{parsed_date}_*.json")):
            if os.path.basename(old_f) != canonical_filename:
                try: os.remove(old_f)
                except: pass
                
        print(f"📥 Received & Reconciled {len(reconciled_records)} scraped records via webhook for date {date_str} -> saved to {canonical_filename}")
        
        # Notify Job Manager of completion if cloud run was active
        JOB_MANAGER.mark_completed(success=True)
        JOB_MANAGER.add_log(f"📥 Webhook received & saved {len(reconciled_records)} records for date {date_str} -> {canonical_filename}\n")
        
        return JSONResponse(content={
            "status": "success",
            "message": f"Saved and reconciled {len(reconciled_records)} records for date {date_str}",
            "filename": canonical_filename
        })
    except Exception as e:
        JOB_MANAGER.mark_completed(success=False, error=str(e))
        return JSONResponse(status_code=500, content={"error": f"Failed to save uploaded records: {str(e)}"})

# -------------------------------------------------------------
# Persistent Scraper Job Manager
# -------------------------------------------------------------
from collections import deque
import time

class ScraperJobManager:
    def __init__(self):
        self.status = "idle"  # "idle", "running", "success", "failed"
        self.mode = "local"   # "cloud" or "local"
        self.job_id = None
        self.start_time = None
        self.end_time = None
        self.target_date = ""
        self.bond_type = "BOTH"
        self.lookback_days = 7
        self.stage = "Ready"
        self.progress_pct = 0
        self.progress_curr = 0
        self.progress_total = 0
        self.logs = deque(maxlen=600)
        self.process = None
        self.error_msg = None
        self._lock = asyncio.Lock()

    def add_log(self, text: str):
        if not text:
            return
        lines = text.splitlines(keepends=True)
        for line in lines:
            self.logs.append(line)
            # Parse progress & stages
            if "Scraping Pending Permits" in line:
                self.stage = "Stage 1/4: Scraping Pending Permits"
            elif "IMFL" in line and "Pass Issued" in line:
                self.stage = "Stage 2/4: Scraping IMFL Dispatches"
            elif "CS" in line and "Pass Issued" in line:
                self.stage = "Stage 3/4: Scraping CS Dispatches"
            elif "Form-34" in line:
                self.stage = "Stage 4/4: Extracting Form-34 Data"
            
            import re
            m = re.search(r'\[(\d+)/(\d+)\]', line)
            if m:
                curr = int(m.group(1))
                total = int(m.group(2))
                self.progress_curr = curr
                self.progress_total = total
                if total > 0:
                    self.progress_pct = min(100, int((curr / total) * 100))

    def get_state(self):
        elapsed = 0
        if self.start_time:
            if self.end_time:
                elapsed = int(self.end_time - self.start_time)
            else:
                elapsed = int(time.time() - self.start_time)
        return {
            "status": self.status,
            "mode": self.mode,
            "job_id": self.job_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "elapsed_seconds": elapsed,
            "target_date": self.target_date,
            "bond_type": self.bond_type,
            "lookback_days": self.lookback_days,
            "stage": self.stage,
            "progress_percent": self.progress_pct,
            "progress_current": self.progress_curr,
            "progress_total": self.progress_total,
            "logs": "".join(self.logs),
            "error": self.error_msg
        }

    async def start_job(self, target_date="", bond_type="BOTH", lookback_days=7, mode="local"):
        async with self._lock:
            if self.status == "running":
                return False, "A scraper job is already running."
            
            self.status = "running"
            self.mode = mode
            self.job_id = f"job_{int(time.time())}"
            self.start_time = time.time()
            self.end_time = None
            self.target_date = target_date or "Today"
            self.bond_type = bond_type
            self.lookback_days = lookback_days
            self.stage = "Initializing..."
            self.progress_pct = 5
            self.progress_curr = 0
            self.progress_total = 0
            self.logs.clear()
            self.error_msg = None

            self.add_log(f"🚀 [{mode.upper()} SCRAPER] Job {self.job_id} initiated\n")
            self.add_log(f"📅 Target Date: {self.target_date} | Bond: {bond_type} | Lookback: {lookback_days}d\n")
            self.add_log("═" * 60 + "\n")
            return True, self.job_id

    def mark_completed(self, success=True, error=None):
        self.status = "success" if success else "failed"
        self.end_time = time.time()
        self.stage = "✅ Completed!" if success else "❌ Failed"
        self.progress_pct = 100 if success else self.progress_pct
        if error:
            self.error_msg = error
            self.add_log(f"\n❌ Error: {error}\n")
        else:
            self.add_log("\n🎉 SUCCESS: Permit scraping and reconciliation completed successfully!\n")

JOB_MANAGER = ScraperJobManager()

async def run_local_scraper_task(target_date_val, bond_type, headless, lookback_days):
    """Runs local scraper process asynchronously detached from WebSocket connections."""
    try:
        args_list = []
        if target_date_val:
            args_list.extend(["--date", target_date_val])
        if bond_type:
            args_list.extend(["--bond", bond_type])
        if not headless:
            args_list.append("--no-headless")
        if lookback_days is not None:
            args_list.extend(["--lookback-days", str(lookback_days)])
            
        script_path = os.path.join(PROJECT_ROOT, "scripts", "main_permits.py")
        if not os.path.exists(script_path):
            JOB_MANAGER.mark_completed(success=False, error=f"Script not found at {script_path}")
            return
            
        python_exe = sys.executable
        cmd = [python_exe, "-u", script_path] + args_list
        
        JOB_MANAGER.add_log(f"🛠️ Starting Permit Scraper: {' '.join(cmd)}\n")
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=PROJECT_ROOT,
            env=env
        )
        JOB_MANAGER.process = process
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded_line = line.decode("utf-8", errors="ignore")
            JOB_MANAGER.add_log(decoded_line)
            await asyncio.sleep(0.001)
            
        returncode = await process.wait()
        JOB_MANAGER.process = None
        
        if returncode == 0:
            JOB_MANAGER.mark_completed(success=True)
        else:
            JOB_MANAGER.mark_completed(success=False, error=f"Process exited with code {returncode}")
            
    except Exception as e:
        JOB_MANAGER.mark_completed(success=False, error=str(e))

@app.get("/api/scraper/status")
async def get_scraper_status(request: Request):
    """
    Returns the persistent state and latest logs of the scraper job.
    Requires authenticated executive session.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
    return JSONResponse(content=JOB_MANAGER.get_state())

@app.post("/api/scraper/start")
async def start_scraper_endpoint(request: Request):
    """
    Starts a scraper run (cloud GitHub dispatch or local background process).
    Requires authenticated executive session.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
    try:
        body = await request.json()
        date_val = str(body.get("date") or body.get("target_date") or "").strip()
        bond_val = str(body.get("bond") or body.get("bond_type") or "BOTH").strip()
        lookback_val = int(body.get("lookback_days", 7))
        headless_val = bool(body.get("headless", True))
        
        gh_token = os.environ.get("GITHUB_TOKEN")
        gh_repo = os.environ.get("GITHUB_REPO")
        
        # If GitHub cloud dispatch is available:
        if gh_token and gh_repo:
            ok, job_or_err = await JOB_MANAGER.start_job(date_val, bond_val, lookback_val, mode="cloud")
            if not ok:
                return JSONResponse(status_code=400, content={"error": job_or_err})
                
            import requests
            dispatch_url = f"https://api.github.com/repos/{gh_repo}/dispatches"
            headers = {
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github+json"
            }
            payload = {
                "event_type": "run-scraper",
                "client_payload": {
                    "date": date_val,
                    "target_date": date_val,
                    "bond": bond_val,
                    "bond_type": bond_val,
                    "lookback_days": lookback_val
                }
            }
            res = requests.post(dispatch_url, headers=headers, json=payload, timeout=10)
            if res.status_code in [204, 200]:
                JOB_MANAGER.add_log("🚀 GitHub Actions Cloud Scraper triggered successfully!\nWaiting for background execution and webhook sync...\n")
                return JSONResponse(content={"status": "running", "started": True, "mode": "cloud", "message": "Dispatched to GitHub Actions in cloud."})
            else:
                JOB_MANAGER.mark_completed(success=False, error=f"GitHub API Error: {res.text}")
                return JSONResponse(status_code=res.status_code, content={"error": res.text})
                
        # Local / Server background task
        ok, job_or_err = await JOB_MANAGER.start_job(date_val, bond_val, lookback_val, mode="local")
        if not ok:
            return JSONResponse(status_code=400, content={"error": job_or_err})
            
        asyncio.create_task(run_local_scraper_task(date_val, bond_val, headless_val, lookback_val))
        return JSONResponse(content={"status": "running", "started": True, "mode": "local", "message": "Started local background scraper task."})
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/scraper/cancel")
async def cancel_scraper(request: Request):
    """
    Cancels any running scraper process.
    Requires authenticated executive session.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
    if JOB_MANAGER.process:
        try:
            JOB_MANAGER.process.terminate()
            await asyncio.sleep(0.5)
            if JOB_MANAGER.process:
                JOB_MANAGER.process.kill()
        except: pass
    JOB_MANAGER.mark_completed(success=False, error="Job was cancelled by user.")
    return JSONResponse(content={"status": "cancelled", "message": "Scraper job cancelled."})

@app.get("/api/cron/trigger")
@app.post("/api/cron/trigger")
async def cron_trigger(request: Request, key: str = None):
    """
    Precision cron endpoint for cron-job.org.
    Validates secret key and triggers the scraper pipeline to run.
    Uses IST to determine today's target date.
    """
    secret = (key or request.query_params.get("key") or request.headers.get("x-cron-secret") or "").strip()
    
    valid_keys = {
        "permtrack_cron_2026",
        "PermTrack@2026",
        "permtrack2026"
    }
    cron_env = os.environ.get("CRON_SECRET", "").strip()
    webhook_env = os.environ.get("WEBHOOK_SECRET", "").strip()
    if cron_env: valid_keys.add(cron_env)
    if webhook_env: valid_keys.add(webhook_env)
    
    cron_secret_file = os.path.join(automation_utils.get_data_dir(), ".cron_secret")
    if os.path.exists(cron_secret_file):
        try:
            with open(cron_secret_file, "r") as cf:
                k = cf.read().strip()
                if k: valid_keys.add(k)
        except Exception: pass
        
    valid_keys = {k for k in valid_keys if k}
    
    if secret not in valid_keys:
        return JSONResponse(status_code=401, content={"error": "Invalid or missing cron key"})

    gh_token = os.environ.get("GITHUB_TOKEN")
    gh_repo = os.environ.get("GITHUB_REPO") or "Grcyberdev/permtrack"

    today_ist = get_now_ist().strftime("%d-%m-%Y")

    if gh_token:
        import requests
        dispatch_url = f"https://api.github.com/repos/{gh_repo}/dispatches"
        headers = {
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github+json"
        }
        payload = {
            "event_type": "run-scraper",
            "client_payload": {
                "date": today_ist,
                "target_date": today_ist,
                "bond": "BOTH",
                "bond_type": "BOTH",
                "lookback_days": 7
            }
        }
        res = requests.post(dispatch_url, headers=headers, json=payload, timeout=10)
        if res.status_code in [204, 200]:
            return JSONResponse(content={"status": "success", "message": f"Dispatched cloud scraper to GitHub Actions for date {today_ist}", "target": gh_repo})
        else:
            return JSONResponse(status_code=res.status_code, content={"error": res.text})
    else:
        # Local background runner fallback
        ok, job_or_err = await JOB_MANAGER.start_job(today_ist, "BOTH", 7, mode="local")
        if ok:
            asyncio.create_task(run_local_scraper_task(today_ist, "BOTH", True, 7))
            return JSONResponse(content={"status": "success", "message": f"Started local background scraper task for date {today_ist}"})
        return JSONResponse(status_code=400, content={"error": job_or_err})

@app.websocket("/ws/run")
async def websocket_run(websocket: WebSocket):
    user = auth.get_current_user(websocket)
    if not user:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    print("🔌 Client connected to logs WebSocket.")
    
    # Stream current logs to newly connected client
    await websocket.send_text(JOB_MANAGER.get_state()["logs"])
    
    last_log_len = len(JOB_MANAGER.logs)
    try:
        while True:
            curr_len = len(JOB_MANAGER.logs)
            if curr_len > last_log_len:
                # Send delta lines
                all_logs = list(JOB_MANAGER.logs)
                delta = all_logs[last_log_len:curr_len]
                await websocket.send_text("".join(delta))
                last_log_len = curr_len
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        print("🔌 Client disconnected from WebSocket.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
