import os
import sys
import json
import glob
import asyncio
import argparse
import re
from typing import Optional, Dict, Any, List, Tuple, Set
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
from reconciler import (
    reconcile_permits,
    clean_permit_records,
    get_reconciliation_summary,
    parse_date_str,
    get_unique_permit_key,
    get_unique_indent_id,
    get_record_effective_date_key,
    normalize_brand_key,
    normalize_size,
    build_historical_sku_rates
)
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

def sync_bundled_data(force: bool = False) -> dict:
    """
    Synchronizes bundled repository configuration and historical datasets
    into the active runtime DATA_DIR (e.g. Fly.io persistent storage /data).
    Preserves data integrity:
    1. Copies missing files.
    2. Overwrites/repairs corrupted or truncated files (e.g. if bundled version has more dispatches/cases).
    3. Merges physical godown counts without overwriting newer live counts.
    """
    bundled_dir = os.path.join(PROJECT_ROOT, "config")
    target_dir = automation_utils.get_data_dir()
    os.makedirs(target_dir, exist_ok=True)
    
    if os.path.abspath(bundled_dir) == os.path.abspath(target_dir):
        return {"status": "skipped", "message": "bundled_dir equals target_dir"}
        
    synced_files = []
    diagnostics = {}
    import shutil
    
    # 1. Sync godown_reconciliation.json
    bundled_recon_path = os.path.join(bundled_dir, "godown_reconciliation.json")
    target_recon_path = os.path.join(target_dir, "godown_reconciliation.json")
    if os.path.exists(bundled_recon_path):
        if not os.path.exists(target_recon_path) or force:
            shutil.copy2(bundled_recon_path, target_recon_path)
            synced_files.append("godown_reconciliation.json (copied)")
        else:
            try:
                with open(bundled_recon_path, "r", encoding="utf-8") as bf:
                    b_data = json.load(bf) or {}
                with open(target_recon_path, "r", encoding="utf-8") as tf:
                    t_data = json.load(tf) or {}
                updated = False
                for k, v in b_data.items():
                    if k not in t_data or (isinstance(v, dict) and t_data.get(k) is None):
                        t_data[k] = v
                        updated = True
                if updated:
                    with open(target_recon_path, "w", encoding="utf-8") as tf:
                        json.dump(t_data, tf, indent=4)
                    synced_files.append("godown_reconciliation.json (merged)")
            except Exception as e_recon:
                print(f"⚠️ Error syncing godown reconciliation: {e_recon}")

    # 2. Sync config.json
    bundled_cfg = os.path.join(bundled_dir, "config.json")
    target_cfg = os.path.join(target_dir, "config.json")
    if os.path.exists(bundled_cfg) and (not os.path.exists(target_cfg) or force):
        shutil.copy2(bundled_cfg, target_cfg)
        synced_files.append("config.json (copied)")

    # 3. Sync backup_permits_*.json
    bundled_backups = glob.glob(os.path.join(bundled_dir, "backup_permits_*.json"))
    for b_path in bundled_backups:
        fname = os.path.basename(b_path)
        t_path = os.path.join(target_dir, fname)
        if not os.path.exists(t_path) or force:
            shutil.copy2(b_path, t_path)
            synced_files.append(f"{fname} (copied new or forced)")
        else:
            try:
                with open(b_path, "r", encoding="utf-8") as bf:
                    b_records = json.load(bf) or []
                with open(t_path, "r", encoding="utf-8") as tf:
                    t_records = json.load(tf) or []
                    
                b_comp = [r for r in b_records if str(r.get("Status", "")).upper() == "COMPLETED"]
                t_comp = [r for r in t_records if str(r.get("Status", "")).upper() == "COMPLETED"]
                
                b_cases = sum(float(r.get("Cases") or 0) for r in b_comp)
                t_cases = sum(float(r.get("Cases") or 0) for r in t_comp)
                
                diagnostics[fname] = {
                    "b_len": len(b_records), "t_len": len(t_records),
                    "b_comp": len(b_comp), "t_comp": len(t_comp),
                    "b_cases": b_cases, "t_cases": t_cases
                }
                
                # If bundled has more completed records or cases (e.g. Oct 26 has 1453 vs 0 on Fly volume)
                if len(b_comp) > len(t_comp) or (b_cases > t_cases + 1.0):
                    shutil.copy2(b_path, t_path)
                    synced_files.append(f"{fname} (repaired: {len(b_comp)} comp vs {len(t_comp)})")
                elif len(t_comp) > len(b_comp) and len(b_comp) > 0:
                    t_keys = {get_unique_permit_key(r) for r in t_records}
                    merged = list(t_records)
                    added = 0
                    for br in b_records:
                        bk = get_unique_permit_key(br)
                        if bk not in t_keys:
                            merged.append(br)
                            t_keys.add(bk)
                            added += 1
                    if added > 0:
                        with open(t_path, "w", encoding="utf-8") as wf:
                            json.dump(merged, wf, indent=4)
                        synced_files.append(f"{fname} (merged {added} records)")
            except Exception as e_sync:
                diagnostics[fname] = {"error": str(e_sync)}
                print(f"⚠️ Error comparing backup {fname}: {e_sync}")

    # Ensure backup_permits_latest.json exists
    t_latest = os.path.join(target_dir, "backup_permits_latest.json")
    b_latest = os.path.join(bundled_dir, "backup_permits_latest.json")
    if os.path.exists(b_latest) and (not os.path.exists(t_latest) or force):
        shutil.copy2(b_latest, t_latest)
        synced_files.append("backup_permits_latest.json (copied)")
        
    print(f"✅ Bundled data sync completed. Synced files: {len(synced_files)}")
    return {"status": "success", "synced_files": synced_files, "diagnostics": diagnostics}

@app.on_event("startup")
async def on_startup():
    try:
        sync_bundled_data()
    except Exception as e:
        print(f"⚠️ Startup sync failed: {e}")

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
    latest_backup = None
    
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
    target_date_key = None
    
    # Try extracting target_date_key from filename first
    if latest_backup_name:
        import re
        m = re.search(r'backup_permits_(\d{8})', latest_backup_name)
        if m:
            target_date_key = m.group(1)
            try:
                from reconciler import parse_date_str
                target_dt = datetime.strptime(target_date_key, "%Y%m%d")
                target_date = target_dt.strftime("%d-%b-%Y")
            except Exception:
                pass

    if not target_date:
        for item in data:
            if item.get("Date"):
                target_date = item.get("Date")
                break
        if target_date:
            from reconciler import parse_date_str
            dt = parse_date_str(target_date)
            if dt:
                target_date_key = dt.strftime("%Y%m%d")
            
    # Apply reconciliation across past lookback_days
    reconciled_data = reconcile_permits(data, target_date, config_dir, lookback_days=lookback_days)
    
    pending = []
    completed = []
    
    all_completed_indents_global = set()
    for bf in glob.glob(os.path.join(config_dir, "backup_permits_*.json")):
        if "latest.json" in bf:
            continue
        try:
            with open(bf, "r", encoding="utf-8") as fp:
                bdata = json.load(fp) or []
            for it in bdata:
                if str(it.get("Status", "")).upper() == "COMPLETED" or str(it.get("Transit Pass", "")).upper().startswith("TP"):
                    all_completed_indents_global.add(get_unique_indent_id(it))
        except Exception:
            pass

    for item in reconciled_data:
        status = item.get("Status", "").upper()
        iid = get_unique_indent_id(item)
        if status == "PENDING":
            if iid in all_completed_indents_global:
                continue
            pending.append(item)
        elif status == "COMPLETED":
            # Strict date partition guard: completed dispatches must strictly match target date
            if target_date_key:
                from reconciler import get_record_effective_date_key
                eff_k = get_record_effective_date_key(item, default_date_key=target_date_key)
                if eff_k != target_date_key:
                    continue
            completed.append(item)

    summary_metrics = get_reconciliation_summary(pending + completed)
    
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

    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    return JSONResponse(content={
        "date": target_date,
        "filename": latest_backup_name,
        "last_updated": last_updated_str,
        "last_updated_ts": last_updated_ts,
        "pending": pending,
        "completed": completed,
        "summary": summary_metrics
    }, headers=no_cache_headers)

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
            
        try:
            mtime = os.path.getmtime(filepath)
        except Exception:
            mtime = 0

        ts_val = ts
        if date_key not in by_date or ts_val > by_date[date_key].get("ts", "") or (ts_val == by_date[date_key].get("ts", "") and mtime > by_date[date_key]["mtime"]):
            by_date[date_key] = {
                "filepath": filepath,
                "filename": basename,
                "mtime": mtime,
                "date_key": date_key,
                "ts": ts_val
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
        
    return JSONResponse(
        content=results,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

GODOWN_RECON_FILE = "godown_reconciliation.json"

def normalize_recon_date_key(key: Any) -> str:
    """
    Standardizes any date key (e.g. 'backup_permits_20261003_000000.json' or '20261003')
    into a clean 8-digit YYYYMMDD string.
    """
    if not key:
        return ""
    s = str(key).strip()
    m = re.search(r"(\d{8})", s)
    if m:
        return m.group(1)
    return s.replace(".json", "").strip()

def load_normalized_godown_recon(config_dir: str) -> Dict[str, Any]:
    """
    Loads godown_reconciliation.json, safely migrating legacy keys to 8-digit YYYYMMDD format
    without losing any saved counts or notes.
    """
    recon_filepath = os.path.join(config_dir, GODOWN_RECON_FILE)
    if not os.path.exists(recon_filepath):
        return {}
    try:
        with open(recon_filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        normalized = {}
        has_legacy = False
        for k, v in data.items():
            norm_k = normalize_recon_date_key(k)
            if norm_k != k:
                has_legacy = True
            if norm_k not in normalized:
                normalized[norm_k] = v
            else:
                existing = normalized[norm_k]
                if v.get("godown_cases") is not None and existing.get("godown_cases") is None:
                    normalized[norm_k] = v
                elif str(v.get("updated_at", "")) > str(existing.get("updated_at", "")):
                    normalized[norm_k] = v
        if has_legacy:
            try:
                with open(recon_filepath, "w", encoding="utf-8") as wf:
                    json.dump(normalized, wf, indent=2)
            except Exception:
                pass
        return normalized
    except Exception:
        return {}

_FILE_RECORDS_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

def get_cached_backup_records(filepath: str) -> List[Dict[str, Any]]:
    """
    Caches parsed JSON records in memory, reloading only when the file's mtime changes.
    """
    try:
        mtime = os.path.getmtime(filepath)
    except Exception:
        mtime = 0
    if filepath in _FILE_RECORDS_CACHE and _FILE_RECORDS_CACHE[filepath][0] == mtime:
        return _FILE_RECORDS_CACHE[filepath][1]
    recs = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            bdata = json.load(f)
        if isinstance(bdata, list):
            recs = bdata
        elif isinstance(bdata, dict):
            recs = (bdata.get("completed") or []) + (bdata.get("pending") or [])
    except Exception:
        recs = []
    _FILE_RECORDS_CACHE[filepath] = (mtime, recs)
    return recs

_CACHED_SKU_RATES: Optional[Dict[str, float]] = None
_CACHED_SKU_RATES_MTIME: float = 0.0
_CACHED_SKU_RATES_LAST_CHECK: float = 0.0

def get_cached_sku_rates(config_dir: str) -> Dict[str, float]:
    """
    Returns historical SKU case rates, preferring cached config/sku_rates.json if available.
    Invalidates when the newest backup's mtime changes or after 10 minutes.
    """
    global _CACHED_SKU_RATES, _CACHED_SKU_RATES_MTIME, _CACHED_SKU_RATES_LAST_CHECK
    now = time.time()
    
    max_mtime = 0.0
    backup_files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
    for bf in backup_files:
        if "latest.json" in bf:
            continue
        try:
            mt = os.path.getmtime(bf)
            if mt > max_mtime:
                max_mtime = mt
        except Exception:
            pass

    if _CACHED_SKU_RATES is not None:
        if max_mtime <= _CACHED_SKU_RATES_MTIME and (now - _CACHED_SKU_RATES_LAST_CHECK < 600):
            return _CACHED_SKU_RATES

    sku_file = os.path.join(config_dir, "sku_rates.json")
    if os.path.exists(sku_file):
        try:
            with open(sku_file, "r", encoding="utf-8") as sf:
                rates = json.load(sf)
                if isinstance(rates, dict) and rates:
                    _CACHED_SKU_RATES = rates
                    _CACHED_SKU_RATES_MTIME = max_mtime
                    _CACHED_SKU_RATES_LAST_CHECK = now
                    return _CACHED_SKU_RATES
        except Exception:
            pass

    _CACHED_SKU_RATES = build_historical_sku_rates(config_dir)
    _CACHED_SKU_RATES_MTIME = max_mtime
    _CACHED_SKU_RATES_LAST_CHECK = now
    return _CACHED_SKU_RATES

_RECONCILED_PENDING_CACHE: Dict[Tuple[str, float], List[Dict[str, Any]]] = {}

def get_cached_reconciled_pending(
    target_recon_date_key: str,
    config_dir: str,
    by_date: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Small in-memory cache for reconciled pending snapshot per
    (target_date_key, max_mtime_of_8_relevant_backups).
    Results are byte-identical to the uncached path.
    """
    global _RECONCILED_PENDING_CACHE
    if target_recon_date_key not in by_date:
        return []

    try:
        t_dt = datetime.strptime(target_recon_date_key, "%Y%m%d")
        t_date_only = t_dt.date()
        min_date_only = t_date_only - timedelta(days=7)
    except Exception:
        t_dt = None
        t_date_only = None
        min_date_only = None

    relevant_mtimes = [by_date[target_recon_date_key].get("mtime", 0.0)]
    if t_date_only and min_date_only:
        for dk, finfo in by_date.items():
            try:
                b_dt = datetime.strptime(dk, "%Y%m%d").date()
                if min_date_only <= b_dt < t_date_only:
                    relevant_mtimes.append(finfo.get("mtime", 0.0))
            except Exception:
                pass

    cache_key = (target_recon_date_key, max(relevant_mtimes) if relevant_mtimes else 0.0)
    if cache_key in _RECONCILED_PENDING_CACHE:
        return [dict(r) for r in _RECONCILED_PENDING_CACHE[cache_key]]

    t_finfo = by_date[target_recon_date_key]
    raw_target_records = get_cached_backup_records(t_finfo["filepath"])
    t_date_str = t_dt.strftime("%d-%b-%Y") if t_dt else None
    reconciled_target = reconcile_permits(raw_target_records, t_date_str, config_dir, lookback_days=7)
    
    # Pre-collect all completed indents across all available backups
    all_completed_iids = set()
    for _, finfo in by_date.items():
        recs = get_cached_backup_records(finfo["filepath"])
        for it in recs:
            st = str(it.get("Status") or "").strip().upper()
            tp = str(it.get("Transit Pass") or "").strip().upper()
            if st == "COMPLETED" or tp.startswith("TP"):
                all_completed_iids.add(get_unique_indent_id(it))

    pending_list = [
        r for r in reconciled_target
        if str(r.get("Status") or "").strip().upper() == "PENDING"
        and get_unique_indent_id(r) not in all_completed_iids
    ]

    if len(_RECONCILED_PENDING_CACHE) > 50:
        _RECONCILED_PENDING_CACHE.clear()
    _RECONCILED_PENDING_CACHE[cache_key] = pending_list
    return [dict(r) for r in pending_list]

def parse_flexible_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parses flexible date formats (YYYY-MM-DD, YYYYMMDD, DD-MM-YYYY, DD-Mon-YYYY) into IST datetime.
    """
    if not date_str:
        return None
    s = str(date_str).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d-%m-%Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=IST)
        except Exception:
            pass
    return None

def find_prev_operating_date(sorted_available_dates: List[str], before_key: str, by_date: Dict[str, Any]) -> Optional[str]:
    """
    Finds the latest available date strictly before before_key that has at least one completed TP dispatch.
    """
    for dk in reversed([k for k in sorted_available_dates if k < before_key]):
        finfo = by_date.get(dk)
        if not finfo:
            continue
        recs = get_cached_backup_records(finfo["filepath"])
        for r in recs:
            if str(r.get("Status") or "").strip().upper() == "COMPLETED":
                tp = str(r.get("Transit Pass") or "").strip().upper()
                if tp.startswith("TP") and "VERIFIED DISPATCH BALANCE" not in str(r.get("Product Name") or "").upper():
                    return dk
    return None

def get_product_category(item: Dict[str, Any]) -> str:
    """
    Canonical liquor category classification preserving exact rules.
    """
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
    recon_data = load_normalized_godown_recon(config_dir)

    backup_files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
    backup_files = [f for f in backup_files if "latest.json" not in f]

    by_date = {}
    for filepath in backup_files:
        basename = os.path.basename(filepath)
        ts = basename.replace("backup_permits_", "").replace(".json", "")
        date_key = ts.split("_")[0]
        if not date_key.isdigit() or len(date_key) != 8 or date_key < "20260101":
            continue
        try:
            mtime = os.path.getmtime(filepath)
        except Exception:
            mtime = 0

        ts_val = ts
        if date_key not in by_date or ts_val > by_date[date_key].get("ts", "") or (ts_val == by_date[date_key].get("ts", "") and mtime > by_date[date_key]["mtime"]):
            by_date[date_key] = {"filepath": filepath, "filename": basename, "mtime": mtime, "ts": ts_val}

    def get_b_per_cs(size_val, pack_size=None):
        return automation_utils.get_bottles_per_case(size_val, pack_size=pack_size)

    def get_cat(item):
        return get_product_category(item)

    # Extract and deduplicate completed records across all latest backup files,
    # mapping each to its true operational effective date (Challan Date -> Transit Pass -> File Date)
    unique_completed_records = {}
    for f_date_key, finfo in by_date.items():
        fpath = finfo["filepath"]
        try:
            records = get_cached_backup_records(fpath)
            for rec in records:
                status = str(rec.get("Status") or "").strip().upper()
                if status != "COMPLETED":
                    continue
                # Strict validation: Only officially approved Transit Passes (TP...) count toward sales
                tp = str(rec.get("Transit Pass") or "").strip().upper()
                if not tp.startswith("TP"):
                    continue
                pname = str(rec.get("Product Name") or "").upper()
                if "VERIFIED DISPATCH BALANCE" in pname:
                    continue
                pkey = get_unique_permit_key(rec)
                if pkey not in unique_completed_records:
                    eff_k = get_record_effective_date_key(rec, default_date_key=f_date_key)
                    compact_rec = {
                        "Cases": float(rec.get("Cases") or 0),
                        "Bottles": int(rec.get("Bottles") or 0),
                        "Size": str(rec.get("Size") or rec.get("Pack Size") or "Unknown"),
                        "Total MRP": float(rec.get("Total MRP") or 0),
                        "Bond Type": str(rec.get("Bond Type") or ""),
                        "Category": str(rec.get("Category") or ""),
                        "Product Name": str(rec.get("Product Name") or "Unknown Brand"),
                        "Retailer Name": str(rec.get("Retailer Name") or "Unknown Licensee")
                    }
                    unique_completed_records[pkey] = (compact_rec, eff_k, finfo["filename"])
        except Exception:
            pass

    records_by_effective_date = {}
    for pkey, (rec, eff_k, orig_fname) in unique_completed_records.items():
        records_by_effective_date.setdefault(eff_k, []).append((rec, orig_fname))

    # Determine all calendar dates to cover across all active months (ensuring no missing Sundays/holidays)
    all_raw_date_keys = set(by_date.keys()) | set(records_by_effective_date.keys()) | set(recon_data.keys())
    months_span = {}
    for k in all_raw_date_keys:
        if len(k) == 8 and k.isdigit() and k >= "20260101":
            ym = k[:6]
            months_span.setdefault(ym, []).append(int(k[6:8]))

    full_date_keys = set()
    for ym, days_list in months_span.items():
        y, m = int(ym[:4]), int(ym[4:6])
        min_d = min(days_list)
        max_d = max(days_list)
        for d in range(min_d, max_d + 1):
            full_date_keys.add(f"{y:04d}{m:02d}{d:02d}")

    sorted_date_keys = sorted(full_date_keys)
    
    # Group by month
    months = {}
    for date_key in sorted_date_keys:
        fallback_filename = by_date.get(date_key, {}).get("filename", f"backup_permits_{date_key}_000000.json")
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
                    "cases_only": 0.0,
                    "bottles_only": 0,
                    "godown_cases": 0.0,
                    "has_godown_entries": False,
                    "difference": 0.0,
                    "total_mrp": 0.0,
                    "beer_eq": 0.0,
                    "imfl_eq": 0.0,
                    "cs_eq": 0.0,
                    "beer_mrp": 0.0,
                    "imfl_mrp": 0.0,
                    "cs_mrp": 0.0,
                    "total_permits": 0,
                    "active_days": 0
                },
                "brand_totals": {},
                "party_totals": {},
                "size_totals": {},
                "dow_totals": {d: {"cases": 0.0, "mrp": 0.0, "permits": 0, "active_days": 0, "closed_days": 0} for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
            }

        m_dict = months[month_key]

        day_beer_mrp = 0.0
        day_imfl_mrp = 0.0
        day_cs_mrp = 0.0

        day_items = records_by_effective_date.get(date_key, [])
        for item_tuple in day_items:
            rec = item_tuple[0]
            permits_count += 1
            c = float(rec.get("Cases") or 0)
            b = int(rec.get("Bottles") or 0)
            pack_size = str(rec.get("Pack Size") or rec.get("Size") or "Unknown")
            b_per_cs = automation_utils.get_bottles_per_case(rec.get("Size"), pack_size=pack_size)
            eq = (b / b_per_cs) if b_per_cs > 0 else 0.0
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
                day_beer_mrp += mrp_val
            elif cat == "CS":
                day_cs_eq += tot_eq
                day_cs_mrp += mrp_val
            else:
                day_imfl_eq += tot_eq
                day_imfl_mrp += mrp_val

            # Brand SKU tracking
            if brand_name not in m_dict["brand_totals"]:
                m_dict["brand_totals"][brand_name] = {"cases": 0.0, "bottles": 0, "mrp": 0.0, "category": cat}
            m_dict["brand_totals"][brand_name]["cases"] += tot_eq
            m_dict["brand_totals"][brand_name]["bottles"] += b
            m_dict["brand_totals"][brand_name]["mrp"] += mrp_val

            # Party / Licensee tracking
            if party_name not in m_dict["party_totals"]:
                m_dict["party_totals"][party_name] = {"cases": 0.0, "bottles": 0, "mrp": 0.0, "permits": 0}
            m_dict["party_totals"][party_name]["cases"] += tot_eq
            m_dict["party_totals"][party_name]["bottles"] += b
            m_dict["party_totals"][party_name]["mrp"] += mrp_val
            m_dict["party_totals"][party_name]["permits"] += 1

            # Size / Pack format tracking
            s_key = f"{pack_size} ML" if pack_size.isdigit() else pack_size
            if s_key not in m_dict["size_totals"]:
                m_dict["size_totals"][s_key] = {"cases": 0.0, "bottles": 0, "mrp": 0.0}
            m_dict["size_totals"][s_key]["cases"] += tot_eq
            m_dict["size_totals"][s_key]["bottles"] += b
            m_dict["size_totals"][s_key]["mrp"] += mrp_val

        permtrack_total_cases = round(dispatched_cases + dispatched_cs_eq, 2)
        is_closed = (permits_count == 0)

        # Day of week aggregation
        if day_name in m_dict["dow_totals"]:
            dow = m_dict["dow_totals"][day_name]
            if is_closed:
                dow["closed_days"] += 1
            else:
                dow["active_days"] += 1
                dow["cases"] = round(dow["cases"] + permtrack_total_cases, 2)
                dow["mrp"] = round(dow["mrp"] + day_mrp, 2)
                dow["permits"] += permits_count

        if not is_closed:
            m_dict["totals"]["active_days"] += 1

        m_dict["totals"]["cases_only"] += dispatched_cases
        m_dict["totals"]["bottles_only"] += dispatched_bottles
        m_dict["totals"]["total_mrp"] += day_mrp
        m_dict["totals"]["beer_eq"] += day_beer_eq
        m_dict["totals"]["imfl_eq"] += day_imfl_eq
        m_dict["totals"]["cs_eq"] += day_cs_eq
        m_dict["totals"]["beer_mrp"] += day_beer_mrp
        m_dict["totals"]["imfl_mrp"] += day_imfl_mrp
        m_dict["totals"]["cs_mrp"] += day_cs_mrp
        m_dict["totals"]["total_permits"] += permits_count

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
            "filename": fallback_filename,
            "date_str": date_str,
            "day": day_name,
            "permtrack_cases": permtrack_total_cases,
            "cases_only": round(dispatched_cases, 2),
            "bottles_only": dispatched_bottles,
            "mrp": round(day_mrp, 2),
            "beer_eq": round(day_beer_eq, 2),
            "imfl_eq": round(day_imfl_eq, 2),
            "cs_eq": round(day_cs_eq, 2),
            "beer_mrp": round(day_beer_mrp, 2),
            "imfl_mrp": round(day_imfl_mrp, 2),
            "cs_mrp": round(day_cs_mrp, 2),
            "permits_count": permits_count,
            "godown_cases": godown_cases,
            "difference": difference,
            "is_closed": is_closed,
            "updated_at": updated_at,
            "updated_by": updated_by
        })

    # Compute cumulative totals and prepare enriched multi-dimensional rankings
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
        mdata["totals"]["cases_only"] = round(mdata["totals"]["cases_only"], 2)
        mdata["totals"]["bottles_only"] = int(mdata["totals"]["bottles_only"])
        mdata["totals"]["godown_cases"] = round(tot_godown, 2) if has_godown else None
        mdata["totals"]["has_godown_entries"] = has_godown
        mdata["totals"]["difference"] = round(tot_godown - cum_permtrack, 2) if has_godown else None
        mdata["totals"]["operating_days"] = mdata["totals"].get("active_days", 0)
        mdata["totals"]["closed_days"] = len(mdata["days"]) - mdata["totals"]["operating_days"]
        mdata["totals"]["total_days"] = len(mdata["days"])
        mdata["totals"]["total_mrp"] = round(mdata["totals"]["total_mrp"], 2)
        mdata["totals"]["beer_eq"] = round(mdata["totals"]["beer_eq"], 2)
        mdata["totals"]["imfl_eq"] = round(mdata["totals"]["imfl_eq"], 2)
        mdata["totals"]["cs_eq"] = round(mdata["totals"]["cs_eq"], 2)
        mdata["totals"]["beer_mrp"] = round(mdata["totals"]["beer_mrp"], 2)
        mdata["totals"]["imfl_mrp"] = round(mdata["totals"]["imfl_mrp"], 2)
        mdata["totals"]["cs_mrp"] = round(mdata["totals"]["cs_mrp"], 2)

        op_days = mdata["totals"]["operating_days"]
        tot_cs = mdata["totals"]["permtrack_cases"]
        tot_rev = mdata["totals"]["total_mrp"]

        mdata["totals"]["avg_case_price"] = round(tot_rev / tot_cs, 2) if tot_cs > 0 else 0.0
        mdata["totals"]["daily_avg_cases"] = round(tot_cs / op_days, 2) if op_days > 0 else 0.0
        mdata["totals"]["daily_avg_mrp"] = round(tot_rev / op_days, 2) if op_days > 0 else 0.0

        # Peak and Lowest Dispatch Days (among operational days)
        active_days_list = [d for d in mdata["days"] if not d["is_closed"] and d["permtrack_cases"] > 0]
        if active_days_list:
            peak_day = max(active_days_list, key=lambda d: d["permtrack_cases"])
            lowest_day = min(active_days_list, key=lambda d: d["permtrack_cases"])
            mdata["totals"]["peak_day"] = {
                "date_str": peak_day["date_str"],
                "day": peak_day["day"],
                "cases": peak_day["permtrack_cases"],
                "mrp": peak_day["mrp"]
            }
            mdata["totals"]["lowest_day"] = {
                "date_str": lowest_day["date_str"],
                "day": lowest_day["day"],
                "cases": lowest_day["permtrack_cases"],
                "mrp": lowest_day["mrp"]
            }
        else:
            mdata["totals"]["peak_day"] = None
            mdata["totals"]["lowest_day"] = None

        # Reconciled operating days count & coverage percentage
        reconciled_count = sum(1 for d in mdata["days"] if not d["is_closed"] and d["godown_cases"] is not None)
        mdata["totals"]["reconciled_days"] = reconciled_count
        mdata["totals"]["coverage_pct"] = round((reconciled_count / op_days) * 100) if op_days > 0 else 0

        # Sort all brands with deep SKU metrics (untruncated full array + top 15)
        all_brands_sorted = sorted(mdata["brand_totals"].items(), key=lambda x: x[1]["cases"], reverse=True)
        mdata["brands_full"] = [
            {
                "name": k,
                "cases": round(v["cases"], 2),
                "bottles": v["bottles"],
                "mrp": round(v["mrp"], 2),
                "category": v["category"],
                "share_pct": round((v["cases"] / tot_cs) * 100, 1) if tot_cs > 0 else 0.0
            }
            for k, v in all_brands_sorted
        ]
        mdata["top_brands"] = mdata["brands_full"][:15]

        # Sort all parties with permit counts and MRP (untruncated full array + top 15)
        all_parties_sorted = sorted(mdata["party_totals"].items(), key=lambda x: x[1]["cases"], reverse=True)
        mdata["parties_full"] = [
            {
                "name": k,
                "cases": round(v["cases"], 2),
                "bottles": v["bottles"],
                "mrp": round(v["mrp"], 2),
                "permits": v["permits"],
                "share_pct": round((v["cases"] / tot_cs) * 100, 1) if tot_cs > 0 else 0.0
            }
            for k, v in all_parties_sorted
        ]
        mdata["top_parties"] = mdata["parties_full"][:15]

        # Retailer concentration Pareto
        all_party_cases = sorted([v["cases"] for v in mdata["party_totals"].values()], reverse=True)
        top5_sum = sum(all_party_cases[:5])
        top10_sum = sum(all_party_cases[:10])
        mdata["retailer_concentration"] = {
            "total_retailers": len(mdata["party_totals"]),
            "top5_cases": round(top5_sum, 2),
            "top5_share_pct": round((top5_sum / tot_cs) * 100, 1) if tot_cs > 0 else 0.0,
            "top10_cases": round(top10_sum, 2),
            "top10_share_pct": round((top10_sum / tot_cs) * 100, 1) if tot_cs > 0 else 0.0
        }

        # Pack size distribution
        sorted_sizes = sorted(mdata["size_totals"].items(), key=lambda x: x[1]["cases"], reverse=True)[:10]
        mdata["pack_sizes"] = [
            {
                "size": k,
                "cases": round(v["cases"], 2),
                "bottles": v["bottles"],
                "mrp": round(v["mrp"], 2),
                "share_pct": round((v["cases"] / tot_cs) * 100, 1) if tot_cs > 0 else 0.0
            }
            for k, v in sorted_sizes
        ]

        # Day of week averages
        for dname, dinfo in mdata["dow_totals"].items():
            act = dinfo["active_days"]
            dinfo["avg_cases"] = round(dinfo["cases"] / act, 2) if act > 0 else 0.0
            dinfo["avg_mrp"] = round(dinfo["mrp"] / act, 2) if act > 0 else 0.0
            dinfo["share_pct"] = round((dinfo["cases"] / tot_cs) * 100, 1) if tot_cs > 0 else 0.0

        mdata["day_of_week"] = mdata["dow_totals"]

        mdata.pop("brand_totals", None)
        mdata.pop("party_totals", None)
        mdata.pop("size_totals", None)
        mdata.pop("dow_totals", None)

        result_months.append(mdata)

    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    # Return in reverse chronological order for recent months first
    return JSONResponse(content={"months": list(reversed(result_months))}, headers=no_cache_headers)

GODOWN_RECON_FILE = "godown_reconciliation.json"

@app.get("/api/godown/reconciliation")
async def get_godown_reconciliation(request: Request, date_key: str = None):
    """
    Returns saved physical godown counts for reconciliation across devices with normalized YYYYMMDD keys.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
    
    config_dir = automation_utils.get_data_dir()
    recon_data = load_normalized_godown_recon(config_dir)
            
    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    if date_key:
        clean_key = normalize_recon_date_key(date_key)
        item = recon_data.get(clean_key) or recon_data.get(date_key.replace(".json", "").strip(), {})
        return JSONResponse(content={"date_key": clean_key, "data": item}, headers=no_cache_headers)
        
    return JSONResponse(content=recon_data, headers=no_cache_headers)

@app.post("/api/godown/reconciliation")
async def save_godown_reconciliation(request: Request):
    """
    Saves or clears physical godown count for a specific date dataset using normalized 8-digit YYYYMMDD keys.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
        
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})
        
    raw_date_key = str(body.get("date_key", "")).strip()
    date_key = normalize_recon_date_key(raw_date_key)
    val = body.get("godown_cases")
    
    if not date_key:
        return JSONResponse(status_code=400, content={"error": "Missing date_key"})
        
    config_dir = automation_utils.get_data_dir()
    os.makedirs(config_dir, exist_ok=True)
    filepath = os.path.join(config_dir, GODOWN_RECON_FILE)
    recon_data = load_normalized_godown_recon(config_dir)
            
    if val is None or str(val).strip() == "":
        recon_data.pop(date_key, None)
        if raw_date_key != date_key:
            recon_data.pop(raw_date_key, None)
    else:
        try:
            val_float = float(val)
            recon_data[date_key] = {
                "godown_cases": val_float,
                "updated_at": get_now_ist().strftime("%d-%b-%Y %I:%M %p"),
                "updated_by": user.get("name") or user.get("username") or "Supervisor"
            }
            if raw_date_key != date_key:
                recon_data.pop(raw_date_key, None)
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

@app.get("/api/analytics/movement")
async def get_movement_analytics(
    request: Request,
    mode: str = "day",
    date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Unified multi-horizon (Day / Week / Month / Custom Range) product and sales movement engine.
    Calculates exact bottle-to-case volumes, MRPs, brand SKUs, pack formats, party sales,
    and period-over-period trend deltas with zero mathematical mutation.
    """
    user = auth.get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})

    config_dir = automation_utils.get_data_dir()
    recon_data = load_normalized_godown_recon(config_dir)
    sku_rates = get_cached_sku_rates(config_dir)

    # 1. Index all latest backups by date
    backup_files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
    backup_files = [f for f in backup_files if "latest.json" not in f]

    by_date: Dict[str, Dict[str, Any]] = {}
    for filepath in backup_files:
        basename = os.path.basename(filepath)
        ts = basename.replace("backup_permits_", "").replace(".json", "")
        date_key = ts.split("_")[0]
        if not date_key.isdigit() or len(date_key) != 8 or date_key < "20260101":
            continue
        try:
            mtime = os.path.getmtime(filepath)
        except Exception:
            mtime = 0

        ts_val = ts
        if date_key not in by_date or ts_val > by_date[date_key].get("ts", "") or (ts_val == by_date[date_key].get("ts", "") and mtime > by_date[date_key]["mtime"]):
            by_date[date_key] = {"filepath": filepath, "filename": basename, "mtime": mtime, "ts": ts_val}

    sorted_available_dates = sorted(by_date.keys())
    latest_avail_key = sorted_available_dates[-1] if sorted_available_dates else get_now_ist().strftime("%Y%m%d")

    # 2. Determine target anchor and horizon ranges
    mode = (mode or "day").lower().strip()
    if mode not in ("day", "week", "month", "range"):
        mode = "day"

    anchor_dt = parse_flexible_date(date)
    if not anchor_dt:
        anchor_dt = parse_flexible_date(latest_avail_key) or get_now_ist()

    if mode == "day":
        h_start_dt = anchor_dt
        h_end_dt = anchor_dt
        display_label = h_start_dt.strftime("%d-%b-%Y")
        anchor_key = anchor_dt.strftime("%Y%m%d")
        prior_op_key = find_prev_operating_date(sorted_available_dates, anchor_key, by_date)
        if prior_op_key:
            p_start_dt = parse_flexible_date(prior_op_key) or (h_start_dt - timedelta(days=1))
            p_end_dt = p_start_dt
        else:
            p_end_dt = h_start_dt - timedelta(days=1)
            p_start_dt = p_end_dt
        prev_display_label = p_start_dt.strftime("%d-%b-%Y")
    elif mode == "week":
        # 7-day rolling period ending on anchor_dt
        h_end_dt = anchor_dt
        h_start_dt = h_end_dt - timedelta(days=6)
        p_end_dt = h_start_dt - timedelta(days=1)
        p_start_dt = p_end_dt - timedelta(days=6)
        display_label = f"{h_start_dt.strftime('%d-%b')} – {h_end_dt.strftime('%d-%b-%Y')} (7D)"
        prev_display_label = f"{p_start_dt.strftime('%d-%b')} – {p_end_dt.strftime('%d-%b-%Y')}"
    elif mode == "month":
        h_start_dt = anchor_dt.replace(day=1)
        next_m = (h_start_dt.replace(day=28) + timedelta(days=4)).replace(day=1)
        h_end_dt = next_m - timedelta(days=1)
        last_day_of_month = h_end_dt.day

        anchor_ym = anchor_dt.strftime("%Y%m")
        latest_ym = latest_avail_key[:6]
        prev_m_end = h_start_dt - timedelta(days=1)
        prev_m_start = prev_m_end.replace(day=1)

        is_partial = False
        elapsed_days = last_day_of_month
        if anchor_ym >= latest_ym:
            latest_day = int(latest_avail_key[6:8])
            if latest_day < last_day_of_month:
                is_partial = True
                elapsed_days = min(latest_day, anchor_dt.day)

        if is_partial:
            p_start_dt = prev_m_start
            p_end_dt = min(prev_m_end, prev_m_start + timedelta(days=elapsed_days - 1))
            display_label = h_start_dt.strftime("%B %Y")
            prev_display_label = f"vs {p_start_dt.day}–{p_end_dt.day} {p_start_dt.strftime('%b')}"
        else:
            p_start_dt = prev_m_start
            p_end_dt = prev_m_end
            display_label = h_start_dt.strftime("%B %Y")
            prev_display_label = p_start_dt.strftime("%B %Y")
    else:  # range
        parsed_s = parse_flexible_date(start_date)
        parsed_e = parse_flexible_date(end_date)
        if not parsed_s or not parsed_e:
            parsed_e = anchor_dt
            parsed_s = parsed_e - timedelta(days=6)
        if parsed_s > parsed_e:
            parsed_s, parsed_e = parsed_e, parsed_s
        h_start_dt = parsed_s
        h_end_dt = parsed_e
        span = (h_end_dt.date() - h_start_dt.date()).days + 1
        p_end_dt = h_start_dt - timedelta(days=1)
        p_start_dt = p_end_dt - timedelta(days=max(0, span - 1))
        display_label = f"{h_start_dt.strftime('%d-%b-%Y')} – {h_end_dt.strftime('%d-%b-%Y')}"
        prev_display_label = f"{p_start_dt.strftime('%d-%b-%Y')} – {p_end_dt.strftime('%d-%b-%Y')}"

    start_key = h_start_dt.strftime("%Y%m%d")
    end_key = h_end_dt.strftime("%Y%m%d")
    prev_start_key = p_start_dt.strftime("%Y%m%d")
    prev_end_key = p_end_dt.strftime("%Y%m%d")
    month_start_key = anchor_dt.strftime("%Y%m01")
    anchor_key = anchor_dt.strftime("%Y%m%d")
    c30_start_key = (h_end_dt - timedelta(days=29)).strftime("%Y%m%d")
    c14_start_key = (h_end_dt - timedelta(days=13)).strftime("%Y%m%d")

    # 3. Deduplicate completed dispatches across all backups
    completed_in_horizon: List[Tuple[Dict[str, Any], str]] = []
    completed_in_prev: List[Tuple[Dict[str, Any], str]] = []
    completed_in_mtd: List[Tuple[Dict[str, Any], str]] = []
    party_cadence_map: Dict[str, Dict[str, Any]] = {}
    unique_completed_pkeys = set()

    for f_date_key, finfo in by_date.items():
        records = get_cached_backup_records(finfo["filepath"])
        for raw_rec in records:
            if str(raw_rec.get("Status") or "").strip().upper() != "COMPLETED":
                continue
            tp = str(raw_rec.get("Transit Pass") or "").strip().upper()
            if not tp.startswith("TP"):
                continue
            pname = str(raw_rec.get("Product Name") or "").upper()
            if "VERIFIED DISPATCH BALANCE" in pname:
                continue
            pkey = get_unique_permit_key(raw_rec)
            if pkey in unique_completed_pkeys:
                continue
            unique_completed_pkeys.add(pkey)
            eff_k = get_record_effective_date_key(raw_rec, default_date_key=f_date_key)
            rec = dict(raw_rec)
            if start_key <= eff_k <= end_key:
                completed_in_horizon.append((rec, eff_k))
            elif prev_start_key <= eff_k <= prev_end_key:
                completed_in_prev.append((rec, eff_k))

            if month_start_key <= eff_k <= anchor_key:
                completed_in_mtd.append((rec, eff_k))

            if c30_start_key <= eff_k <= end_key:
                pt_name = rec.get("Retailer Name") or rec.get("Licensee Name") or "Unknown Licensee"
                if pt_name not in party_cadence_map:
                    party_cadence_map[pt_name] = {"days": set(), "last_order": ""}
                party_cadence_map[pt_name]["days"].add(eff_k)
                if eff_k > party_cadence_map[pt_name]["last_order"]:
                    party_cadence_map[pt_name]["last_order"] = eff_k

    # Calculate Month-to-Date (MTD) totals
    mtd_tot_cases = 0.0
    mtd_tot_mrp = 0.0
    mtd_days_set = set()
    mtd_permits_set = set()

    for rec, eff_k in completed_in_mtd:
        c = float(rec.get("Cases") or 0)
        b = int(rec.get("Bottles") or 0)
        pack_size = str(rec.get("Pack Size") or rec.get("Size") or "Unknown")
        bpc = automation_utils.get_bottles_per_case(rec.get("Size"), pack_size=pack_size)
        eq = (b / bpc) if bpc > 0 else 0.0
        tot_eq = c + eq
        curr_mrp = float(rec.get("Total MRP") or 0)
        if curr_mrp <= 0:
            p_name = normalize_brand_key(rec.get("Product Name"))
            sz = normalize_size(rec.get("Size"))
            rate = sku_rates.get(f"{p_name}_{sz}") or sku_rates.get(p_name, 0.0)
            if rate > 0 and c > 0:
                curr_mrp = round(c * rate, 2)
        mtd_tot_cases += tot_eq
        mtd_tot_mrp += curr_mrp
        mtd_days_set.add(eff_k)
        p_id = rec.get("Permit Number") or rec.get("Transit Pass") or rec.get("Indent Number")
        if p_id:
            mtd_permits_set.add(p_id)

    # Backfill missing MRPs using SKU rates lookup
    for rec, _ in completed_in_horizon:
        curr_mrp = float(rec.get("Total MRP") or 0)
        if curr_mrp <= 0:
            p_name = normalize_brand_key(rec.get("Product Name"))
            sz = normalize_size(rec.get("Size"))
            rate = sku_rates.get(f"{p_name}_{sz}") or sku_rates.get(p_name, 0.0)
            cs = float(rec.get("Cases") or 0)
            if rate > 0 and cs > 0:
                rec["Total MRP"] = round(cs * rate, 2)
                rec["MRP_Estimated"] = True

    # 4. Handle Pending indents in the current horizon (Fix 42: in-memory cache)
    pending_in_horizon: List[Dict[str, Any]] = []
    target_recon_date_key = end_key if end_key in by_date else (
        max([k for k in sorted_available_dates if k <= end_key], default=latest_avail_key)
    )
    if target_recon_date_key in by_date:
        pending_in_horizon = get_cached_reconciled_pending(target_recon_date_key, config_dir, by_date)

    # 5. Build daily series across all calendar days in [start_key, end_key]
    cur_date = h_start_dt.date()
    end_date_obj = h_end_dt.date()
    daily_series_map: Dict[str, Dict[str, Any]] = {}
    while cur_date <= end_date_obj:
        dk = cur_date.strftime("%Y%m%d")
        daily_series_map[dk] = {
            "date_key": dk,
            "date_str": cur_date.strftime("%d-%b-%Y"),
            "day": cur_date.strftime("%A"),
            "cases": 0.0,
            "cases_only": 0.0,
            "bottles_only": 0,
            "beer_cases": 0.0,
            "imfl_cases": 0.0,
            "cs_cases": 0.0,
            "mrp": 0.0,
            "beer_mrp": 0.0,
            "imfl_mrp": 0.0,
            "cs_mrp": 0.0,
            "permits_count": 0,
            "pending_count": 0,
            "godown_cases": recon_data.get(dk, {}).get("godown_cases"),
            "difference": None,
            "is_closed": True
        }
        cur_date += timedelta(days=1)

    # 6. Aggregate completed dispatches
    summary_tot_cases = 0.0
    summary_cases_only = 0.0
    summary_bottles_only = 0
    summary_dispatched_cs_eq = 0.0
    summary_mrp = 0.0
    summary_bl = 0.0
    summary_lpl = 0.0

    cat_breakdown = {
        "BEER": {"cases": 0.0, "cases_only": 0.0, "bottles": 0, "pending_cases": 0.0, "mrp": 0.0, "pending_mrp": 0.0, "bulk_litres": 0.0, "lpl": 0.0, "permits": 0},
        "IMFL": {"cases": 0.0, "cases_only": 0.0, "bottles": 0, "pending_cases": 0.0, "mrp": 0.0, "pending_mrp": 0.0, "bulk_litres": 0.0, "lpl": 0.0, "permits": 0},
        "CS":   {"cases": 0.0, "cases_only": 0.0, "bottles": 0, "pending_cases": 0.0, "mrp": 0.0, "pending_mrp": 0.0, "bulk_litres": 0.0, "lpl": 0.0, "permits": 0}
    }

    brand_map: Dict[str, Dict[str, Any]] = {}
    pack_map: Dict[str, Dict[str, Any]] = {}
    party_map: Dict[str, Dict[str, Any]] = {}
    permits_set = set()

    for rec, eff_k in completed_in_horizon:
        c = float(rec.get("Cases") or 0)
        b = int(rec.get("Bottles") or 0)
        pack_size = str(rec.get("Pack Size") or rec.get("Size") or "Unknown")
        bpc = automation_utils.get_bottles_per_case(rec.get("Size"), pack_size=pack_size)
        eq = (b / bpc) if bpc > 0 else 0.0
        tot_eq = c + eq
        mrp_val = float(rec.get("Total MRP") or 0)
        bl_val = float(rec.get("Bulk Litres") or 0)
        lpl_val = float(rec.get("LPL") or 0)
        cat = get_product_category(rec)
        b_name = rec.get("Product Name") or "Unknown Brand"
        p_name = rec.get("Retailer Name") or rec.get("Licensee Name") or "Unknown Licensee"
        dist = rec.get("District") or rec.get("Destination District") or ""

        summary_tot_cases += tot_eq
        summary_cases_only += c
        summary_bottles_only += b
        summary_dispatched_cs_eq += eq
        summary_mrp += mrp_val
        summary_bl += bl_val
        summary_lpl += lpl_val

        p_id = rec.get("Permit Number") or rec.get("Transit Pass") or rec.get("Indent Number")
        if p_id:
            permits_set.add(p_id)

        # Update daily series
        if eff_k in daily_series_map:
            ds = daily_series_map[eff_k]
            ds["cases"] = round(ds["cases"] + tot_eq, 2)
            ds["cases_only"] = round(ds["cases_only"] + c, 2)
            ds["bottles_only"] += b
            ds["mrp"] = round(ds["mrp"] + mrp_val, 2)
            ds["permits_count"] += 1
            ds["is_closed"] = False
            if cat == "BEER":
                ds["beer_cases"] = round(ds["beer_cases"] + tot_eq, 2)
                ds["beer_mrp"] = round(ds["beer_mrp"] + mrp_val, 2)
            elif cat == "CS":
                ds["cs_cases"] = round(ds["cs_cases"] + tot_eq, 2)
                ds["cs_mrp"] = round(ds["cs_mrp"] + mrp_val, 2)
            else:
                ds["imfl_cases"] = round(ds["imfl_cases"] + tot_eq, 2)
                ds["imfl_mrp"] = round(ds["imfl_mrp"] + mrp_val, 2)

        # Update category breakdown
        if cat in cat_breakdown:
            cb = cat_breakdown[cat]
            cb["cases"] += tot_eq
            cb["cases_only"] += c
            cb["bottles"] += b
            cb["mrp"] += mrp_val
            cb["bulk_litres"] += bl_val
            cb["lpl"] += lpl_val
            cb["permits"] += 1

        # Update brand map
        if b_name not in brand_map:
            brand_map[b_name] = {
                "name": b_name,
                "category": cat,
                "dispatched_cases": 0.0,
                "cases_only": 0.0,
                "bottles": 0,
                "pending_cases": 0.0,
                "pending_bottles": 0,
                "total_mrp": 0.0,
                "bulk_litres": 0.0,
                "lpl": 0.0,
                "pack_breakdown": {},
                "top_buyers_dict": {},
                "daily_cases": {dk: 0.0 for dk in daily_series_map.keys()}
            }
        bm = brand_map[b_name]
        bm["dispatched_cases"] += tot_eq
        bm["cases_only"] += c
        bm["bottles"] += b
        bm["total_mrp"] += mrp_val
        bm["bulk_litres"] += bl_val
        bm["lpl"] += lpl_val
        if eff_k in bm["daily_cases"]:
            bm["daily_cases"][eff_k] += tot_eq

        # Pack breakdown under brand
        s_clean = f"{pack_size} ML" if pack_size.isdigit() else pack_size
        if s_clean not in bm["pack_breakdown"]:
            bm["pack_breakdown"][s_clean] = {"cases": 0.0, "bottles": 0, "mrp": 0.0}
        bm["pack_breakdown"][s_clean]["cases"] += tot_eq
        bm["pack_breakdown"][s_clean]["bottles"] += b
        bm["pack_breakdown"][s_clean]["mrp"] += mrp_val

        # Top buyers under brand
        if p_name not in bm["top_buyers_dict"]:
            bm["top_buyers_dict"][p_name] = {"cases": 0.0, "mrp": 0.0}
        bm["top_buyers_dict"][p_name]["cases"] += tot_eq
        bm["top_buyers_dict"][p_name]["mrp"] += mrp_val

        # Global pack size tracking (Fix 22: key by (s_clean, cat))
        pack_key = (s_clean, cat)
        if pack_key not in pack_map:
            pack_map[pack_key] = {"size": s_clean, "category": cat, "cases": 0.0, "bottles": 0, "mrp": 0.0}
        pack_map[pack_key]["cases"] += tot_eq
        pack_map[pack_key]["bottles"] += b
        pack_map[pack_key]["mrp"] += mrp_val

        # Global party / retailer tracking
        if p_name not in party_map:
            party_map[p_name] = {
                "name": p_name,
                "district": dist,
                "dispatched_cases": 0.0,
                "pending_cases": 0.0,
                "beer_cases": 0.0,
                "imfl_cases": 0.0,
                "cs_cases": 0.0,
                "mrp": 0.0,
                "indent_count": 0,
                "dispatched_permits": 0,
                "pending_permits": 0,
                "active_days_set": set(),
                "last_order_date": eff_k,
                "brands_dict": {}
            }
        pm = party_map[p_name]
        pm["dispatched_cases"] += tot_eq
        pm["mrp"] += mrp_val
        pm["dispatched_permits"] += 1
        pm["indent_count"] += 1
        pm["active_days_set"].add(eff_k)
        if not pm["district"] and dist:
            pm["district"] = dist
        if eff_k > pm["last_order_date"]:
            pm["last_order_date"] = eff_k
        if cat == "BEER":
            pm["beer_cases"] += tot_eq
        elif cat == "CS":
            pm["cs_cases"] += tot_eq
        else:
            pm["imfl_cases"] += tot_eq
        if b_name not in pm["brands_dict"]:
            pm["brands_dict"][b_name] = 0.0
        pm["brands_dict"][b_name] += tot_eq

    # 7. Aggregate pending indents
    summary_pending_cases = 0.0
    summary_pending_bottles = 0
    summary_pending_mrp = 0.0
    pending_permits_set = set()
    pending_pick_dict: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for prec in pending_in_horizon:
        c = float(prec.get("Cases") or 0)
        b = int(prec.get("Bottles") or 0)
        pack_size = str(prec.get("Pack Size") or prec.get("Size") or "Unknown")
        bpc = automation_utils.get_bottles_per_case(prec.get("Size"), pack_size=pack_size)
        eq = (b / bpc) if bpc > 0 else 0.0
        tot_eq = c + eq
        mrp_val = float(prec.get("Total MRP") or 0)
        cat = get_product_category(prec)
        b_name = prec.get("Product Name") or "Unknown Brand"
        p_name = prec.get("Retailer Name") or prec.get("Licensee Name") or "Unknown Licensee"
        dist = prec.get("District") or prec.get("Destination District") or ""

        summary_pending_cases += tot_eq
        summary_pending_bottles += b
        summary_pending_mrp += mrp_val

        p_id = prec.get("Permit Number") or prec.get("Indent Number")
        if p_id:
            pending_permits_set.add(p_id)

        if cat in cat_breakdown:
            cat_breakdown[cat]["pending_cases"] += tot_eq
            cat_breakdown[cat]["pending_mrp"] += mrp_val

        # Update brand pending
        if b_name not in brand_map:
            brand_map[b_name] = {
                "name": b_name,
                "category": cat,
                "dispatched_cases": 0.0,
                "cases_only": 0.0,
                "bottles": 0,
                "pending_cases": 0.0,
                "pending_bottles": 0,
                "total_mrp": 0.0,
                "bulk_litres": 0.0,
                "lpl": 0.0,
                "pack_breakdown": {},
                "top_buyers_dict": {},
                "daily_cases": {dk: 0.0 for dk in daily_series_map.keys()}
            }
        brand_map[b_name]["pending_cases"] += tot_eq
        brand_map[b_name]["pending_bottles"] += b

        # Update party pending
        if p_name not in party_map:
            party_map[p_name] = {
                "name": p_name,
                "district": dist,
                "dispatched_cases": 0.0,
                "pending_cases": 0.0,
                "beer_cases": 0.0,
                "imfl_cases": 0.0,
                "cs_cases": 0.0,
                "mrp": 0.0,
                "indent_count": 0,
                "dispatched_permits": 0,
                "pending_permits": 0,
                "active_days_set": set(),
                "last_order_date": "",
                "brands_dict": {}
            }
        party_map[p_name]["pending_cases"] += tot_eq
        party_map[p_name]["pending_permits"] += 1
        party_map[p_name]["indent_count"] += 1

        # Warehouse pick-list aggregation
        s_clean = f"{pack_size} ML" if pack_size.isdigit() else pack_size
        pick_k = (b_name, s_clean, cat)
        if pick_k not in pending_pick_dict:
            pending_pick_dict[pick_k] = {
                "brand_name": b_name,
                "pack_size": s_clean,
                "category": cat,
                "cases": 0.0,
                "bottles": 0,
                "total_cases_eq": 0.0,
                "permits_count": 0,
                "licensees_set": set()
            }
        pp = pending_pick_dict[pick_k]
        pp["cases"] += c
        pp["bottles"] += b
        pp["total_cases_eq"] += tot_eq
        pp["permits_count"] += 1
        pp["licensees_set"].add(p_name)

    # Convert pending pick-list to sorted list
    pending_pick_list = []
    for (b_name, s_clean, cat), pinfo in pending_pick_dict.items():
        pending_pick_list.append({
            "brand_name": b_name,
            "pack_size": s_clean,
            "category": cat,
            "cases": round(pinfo["cases"], 2),
            "bottles": pinfo["bottles"],
            "total_cases_eq": round(pinfo["total_cases_eq"], 2),
            "permits_count": pinfo["permits_count"],
            "licensees": sorted(list(pinfo["licensees_set"]))
        })
    pending_pick_list.sort(key=lambda x: x["total_cases_eq"], reverse=True)

    # 8. Compute active days and daily velocity
    daily_series = sorted(daily_series_map.values(), key=lambda d: d["date_key"])
    active_days_count = sum(1 for d in daily_series if not d["is_closed"])
    effective_days = max(1, active_days_count)

    # Update godown variance per day
    for d in daily_series:
        if d["godown_cases"] is not None:
            try:
                diff_val = float(d["godown_cases"]) - d["cases"]
                d["difference"] = round(diff_val, 2)
            except Exception:
                d["difference"] = None

    # Totals for physical godown
    godown_cases_sum = 0.0
    has_godown_entries = False
    for d in daily_series:
        if d["godown_cases"] is not None:
            has_godown_entries = True
            godown_cases_sum += float(d["godown_cases"])

    net_godown_difference = round(godown_cases_sum - summary_tot_cases, 2) if has_godown_entries else None

    # Finalize category breakdown
    for cat_k, cinfo in cat_breakdown.items():
        cinfo["cases"] = round(cinfo["cases"], 2)
        cinfo["cases_only"] = round(cinfo["cases_only"], 2)
        cinfo["pending_cases"] = round(cinfo["pending_cases"], 2)
        cinfo["mrp"] = round(cinfo["mrp"], 2)
        cinfo["pending_mrp"] = round(cinfo["pending_mrp"], 2)
        cinfo["bulk_litres"] = round(cinfo["bulk_litres"], 2)
        cinfo["lpl"] = round(cinfo["lpl"], 2)
        cinfo["share_pct"] = round((cinfo["cases"] / summary_tot_cases) * 100, 1) if summary_tot_cases > 0 else 0.0
        cinfo["velocity_per_day"] = round(cinfo["cases"] / effective_days, 1) if effective_days > 0 else 0.0

    # Finalize brands_full
    brands_full = []
    for b_name, binfo in brand_map.items():
        c_eq = round(binfo["dispatched_cases"], 2)
        p_eq = round(binfo["pending_cases"], 2)
        top_buyers_list = [
            {"name": k, "cases": round(v["cases"], 2), "mrp": round(v["mrp"], 2)}
            for k, v in sorted(binfo["top_buyers_dict"].items(), key=lambda x: x[1]["cases"], reverse=True)[:5]
        ]
        pack_bd_formatted = {
            k: {"cases": round(v["cases"], 2), "bottles": v["bottles"], "mrp": round(v["mrp"], 2)}
            for k, v in binfo["pack_breakdown"].items()
        }
        sparkline = [round(binfo["daily_cases"][d["date_key"]], 1) for d in daily_series]
        brands_full.append({
            "name": b_name,
            "category": binfo["category"],
            "dispatched_cases": c_eq,
            "cases_only": round(binfo["cases_only"], 2),
            "bottles": binfo["bottles"],
            "pending_cases": p_eq,
            "pending_bottles": binfo["pending_bottles"],
            "total_mrp": round(binfo["total_mrp"], 2),
            "bulk_litres": round(binfo["bulk_litres"], 2),
            "lpl": round(binfo["lpl"], 2),
            "velocity_per_day": round(c_eq / effective_days, 1) if effective_days > 0 else 0.0,
            "share_pct": round((c_eq / summary_tot_cases) * 100, 1) if summary_tot_cases > 0 else 0.0,
            "pack_breakdown": pack_bd_formatted,
            "top_buyers": top_buyers_list,
            "daily_sparkline": sparkline
        })
    brands_full.sort(key=lambda x: (x["dispatched_cases"], x["pending_cases"]), reverse=True)

    # Finalize pack_sizes_full (Fix 22: keyed by (size, category))
    pack_sizes_full = []
    for (s_clean, pcat), sinfo in pack_map.items():
        scs = round(sinfo["cases"], 2)
        pack_sizes_full.append({
            "size": sinfo["size"],
            "pack_size": sinfo["size"],
            "category": sinfo["category"],
            "cases": scs,
            "bottles": sinfo["bottles"],
            "mrp": round(sinfo["mrp"], 2),
            "share_pct": round((scs / summary_tot_cases) * 100, 1) if summary_tot_cases > 0 else 0.0
        })
    pack_sizes_full.sort(key=lambda x: x["cases"], reverse=True)

    # Finalize parties_full (Fix 21: 30-day lookback cadence)
    parties_full = []
    for p_name, pinfo in party_map.items():
        pcs = round(pinfo["dispatched_cases"], 2)
        p_pending = round(pinfo["pending_cases"], 2)
        top_brands_bought = [
            {"name": k, "cases": round(v, 2)}
            for k, v in sorted(pinfo["brands_dict"].items(), key=lambda x: x[1], reverse=True)[:4]
        ]
        cad_info = party_cadence_map.get(p_name, {"days": set(), "last_order": ""})
        act_cnt = len(cad_info["days"])
        last_ord_key = cad_info["last_order"] or pinfo.get("last_order_date", "")

        if not last_ord_key or act_cnt == 0:
            cadence = "dormant"
        elif last_ord_key < c14_start_key:
            cadence = "dormant"
        elif act_cnt >= 4:
            cadence = "regular"
        else:
            cadence = "active"

        last_ord_str = ""
        if last_ord_key:
            try:
                last_ord_str = datetime.strptime(last_ord_key, "%Y%m%d").strftime("%d-%b-%Y")
            except Exception:
                last_ord_str = last_ord_key

        parties_full.append({
            "name": p_name,
            "district": pinfo["district"] or "ASSAM",
            "dispatched_cases": pcs,
            "pending_cases": p_pending,
            "beer_cases": round(pinfo["beer_cases"], 2),
            "imfl_cases": round(pinfo["imfl_cases"], 2),
            "cs_cases": round(pinfo["cs_cases"], 2),
            "mrp": round(pinfo["mrp"], 2),
            "indent_count": pinfo["indent_count"],
            "dispatched_permits": pinfo["dispatched_permits"],
            "pending_permits": pinfo["pending_permits"],
            "active_days": act_cnt,
            "last_order_date": last_ord_str,
            "cadence_status": cadence,
            "brands_bought": top_brands_bought
        })
    parties_full.sort(key=lambda x: (x["dispatched_cases"], x["pending_cases"]), reverse=True)

    # 9. Compute Previous Period Summary and Delta Badges
    prev_tot_cases = 0.0
    prev_tot_mrp = 0.0
    prev_permits_set = set()
    prev_parties_set = set()

    for prec, _ in completed_in_prev:
        c = float(prec.get("Cases") or 0)
        b = int(prec.get("Bottles") or 0)
        pack_size = str(prec.get("Pack Size") or prec.get("Size") or "Unknown")
        bpc = automation_utils.get_bottles_per_case(prec.get("Size"), pack_size=pack_size)
        eq = (b / bpc) if bpc > 0 else 0.0
        tot_eq = c + eq
        mrp_val = float(prec.get("Total MRP") or 0)
        prev_tot_cases += tot_eq
        prev_tot_mrp += mrp_val
        p_id = prec.get("Permit Number") or prec.get("Transit Pass") or prec.get("Indent Number")
        if p_id:
            prev_permits_set.add(p_id)
        pt_name = prec.get("Retailer Name") or prec.get("Licensee Name")
        if pt_name:
            prev_parties_set.add(pt_name)

    prev_tot_cases = round(prev_tot_cases, 2)
    prev_tot_mrp = round(prev_tot_mrp, 2)
    # Fix 10: return None (null in JSON) if previous period value is 0
    delta_cases_pct = round(((summary_tot_cases - prev_tot_cases) / prev_tot_cases) * 100, 1) if prev_tot_cases > 0 else None
    delta_mrp_pct = round(((summary_mrp - prev_tot_mrp) / prev_tot_mrp) * 100, 1) if prev_tot_mrp > 0 else None
    delta_permits_pct = round(((len(permits_set) - len(prev_permits_set)) / len(prev_permits_set)) * 100, 1) if len(prev_permits_set) > 0 else None

    # 10. Compile raw permit items for ledger
    all_permits_raw = [r for r, _ in completed_in_horizon] + pending_in_horizon

    result_payload = {
        "horizon": {
            "mode": mode,
            "anchor_date": anchor_dt.strftime("%Y-%m-%d"),
            "start_date": h_start_dt.strftime("%Y-%m-%d"),
            "end_date": h_end_dt.strftime("%Y-%m-%d"),
            "start_date_key": start_key,
            "end_date_key": end_key,
            "display_label": display_label,
            "prev_start_date": p_start_dt.strftime("%Y-%m-%d"),
            "prev_end_date": p_end_dt.strftime("%Y-%m-%d"),
            "prev_display_label": prev_display_label,
            "available_dates": sorted_available_dates
        },
        "summary": {
            "total_cases": round(summary_tot_cases, 2),
            "cases_only": round(summary_cases_only, 2),
            "bottles_only": summary_bottles_only,
            "dispatched_cs_eq": round(summary_dispatched_cs_eq, 2),
            "pending_cases": round(summary_pending_cases, 2),
            "pending_bottles": summary_pending_bottles,
            "pending_permits_count": len(pending_permits_set),
            "permits_count": len(permits_set),
            "active_parties_count": len(party_map),
            "total_mrp": round(summary_mrp, 2),
            "pending_mrp": round(summary_pending_mrp, 2),
            "bulk_litres": round(summary_bl, 2),
            "lpl": round(summary_lpl, 2),
            "avg_case_price": round(summary_mrp / summary_tot_cases, 2) if summary_tot_cases > 0 else 0.0,
            "active_days": active_days_count,
            "total_days": len(daily_series),
            "cases_per_day": round(summary_tot_cases / effective_days, 1) if effective_days > 0 else 0.0,
            "mrp_per_day": round(summary_mrp / effective_days, 1) if effective_days > 0 else 0.0,
            "godown_cases": round(godown_cases_sum, 2) if has_godown_entries else None,
            "difference": net_godown_difference,
            "mtd_cases": round(mtd_tot_cases, 2),
            "mtd_mrp": round(mtd_tot_mrp, 2),
            "mtd_active_days": len(mtd_days_set),
            "mtd_permits_count": len(mtd_permits_set),
            "mtd_label": anchor_dt.strftime("%B %Y") if mode == "month" else (anchor_dt.strftime("%b %Y") + " MTD")
        },
        "previous_period_summary": {
            "total_cases": prev_tot_cases,
            "total_mrp": prev_tot_mrp,
            "permits_count": len(prev_permits_set),
            "active_parties_count": len(prev_parties_set),
            "delta_cases_pct": delta_cases_pct,
            "delta_mrp_pct": delta_mrp_pct,
            "delta_permits_pct": delta_permits_pct
        },
        "category_breakdown": cat_breakdown,
        "brands_full": brands_full,
        "pack_sizes_full": pack_sizes_full,
        "parties_full": parties_full,
        "daily_series": daily_series,
        "pending_pick_list": pending_pick_list,
        "permits": all_permits_raw
    }

    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    return JSONResponse(content=result_payload, headers=no_cache_headers)

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
        expected_secret = os.environ.get("WEBHOOK_SECRET") or os.environ.get("CRON_SECRET")
        if not expected_secret:
            cron_secret_file = os.path.join(automation_utils.get_data_dir(), ".cron_secret")
            if os.path.exists(cron_secret_file):
                try:
                    with open(cron_secret_file, "r") as cf:
                        k = cf.read().strip()
                        if k: expected_secret = k
                except Exception: pass
        if not expected_secret:
            return JSONResponse(status_code=503, content={"error": "Webhook secret not configured"})
        if secret != expected_secret:
            return JSONResponse(status_code=403, content={"error": "Invalid webhook secret authorization"})
        
        records = payload.get("records", [])
        date_str = payload.get("date")
        has_errors = bool(payload.get("has_errors", False))
        failed_bonds = [str(b).upper() for b in (payload.get("failed_bonds") or [])]
        
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
        
        # Load existing records for this date (if any) to guard against empty/failed or degraded runs
        ex_data = []
        existing_completed = []
        if os.path.exists(canonical_path):
            try:
                with open(canonical_path, "r") as ef:
                    ex_data = json.load(ef) or []
                for it in ex_data:
                    if str(it.get("Status", "")).upper() == "COMPLETED":
                        existing_completed.append(it)
            except Exception: pass

        # Guard against failed runs pushing empty records (or only carried-over records when all bonds failed)
        fresh_incoming = [it for it in records if not it.get("carried_over")]
        if len(fresh_incoming) == 0 and (has_errors or failed_bonds or len(existing_completed) > 0):
            err_msg = f"Rejected empty/failed scrape upload for {date_str} (failed_bonds={failed_bonds}, has_errors={has_errors}, existing_completed={len(existing_completed)})"
            print(f"🚨 {err_msg}")
            JOB_MANAGER.add_log(f"🚨 {err_msg}\n")
            JOB_MANAGER.mark_completed(success=False, error=err_msg)
            return JSONResponse(status_code=422, content={"status": "error", "error": err_msg})

        # Guard against degraded completed indents (e.g., partial modal extraction with fewer cases than already saved)
        existing_indent_cases = {}
        for it in existing_completed:
            iid = get_unique_indent_id(it)
            existing_indent_cases[iid] = existing_indent_cases.get(iid, 0.0) + float(it.get("Cases") or 0)

        incoming_indent_cases = {}
        for it in records:
            if str(it.get("Status", "")).upper() == "COMPLETED":
                iid = get_unique_indent_id(it)
                incoming_indent_cases[iid] = incoming_indent_cases.get(iid, 0.0) + float(it.get("Cases") or 0)

        degraded_indents = set()
        for iid, ex_c in existing_indent_cases.items():
            inc_c = incoming_indent_cases.get(iid, 0.0)
            if inc_c > 0 and inc_c < (ex_c - 0.01):
                degraded_indents.add(iid)

        protected_records = [
            it for it in records
            if not (str(it.get("Status", "")).upper() == "COMPLETED" and get_unique_indent_id(it) in degraded_indents)
        ]

        incoming_completed_indents = {get_unique_indent_id(it) for it in protected_records if str(it.get("Status", "")).upper() == "COMPLETED"}
        incoming_completed_bonds = {str(it.get("Bond Type", "")).upper() for it in protected_records if str(it.get("Status", "")).upper() == "COMPLETED" and str(it.get("Bond Type", "")).upper() not in failed_bonds}
        incoming_keys = {get_unique_permit_key(it) for it in protected_records}

        records_to_reconcile = list(protected_records)
        for ex in existing_completed:
            ex_bond = str(ex.get("Bond Type", "")).upper()
            ex_iid = get_unique_indent_id(ex)
            ex_key = get_unique_permit_key(ex)
            # Preserve existing completed if bond failed/missing, indent missing, or indent was degraded
            if ex_bond in failed_bonds or ex_bond not in incoming_completed_bonds or ex_iid not in incoming_completed_indents or ex_iid in degraded_indents:
                if ex_key not in incoming_keys:
                    records_to_reconcile.append(ex)
                    incoming_keys.add(ex_key)

        # If a specific bond failed in a partial run, also preserve existing fresh PENDING records for that bond (unless completed in current run)
        if failed_bonds and ex_data:
            for ex in ex_data:
                if str(ex.get("Status", "")).upper() == "PENDING" and not ex.get("carried_over"):
                    ex_bond = str(ex.get("Bond Type", "")).upper()
                    ex_iid = get_unique_indent_id(ex)
                    ex_key = get_unique_permit_key(ex)
                    if ex_bond in failed_bonds and ex_key not in incoming_keys and ex_iid not in incoming_completed_indents:
                        records_to_reconcile.append(ex)
                        incoming_keys.add(ex_key)
                
        # Reconcile merged records with 7-day backups
        reconciled_records = reconcile_permits(records_to_reconcile, target_dt, config_dir, lookback_days=7)
        
        # Partition target date records vs cross-date completed records
        # Completed records are strictly grouped by eff_k = get_record_effective_date_key(r)
        completed_by_date: Dict[str, List[Dict[str, Any]]] = {}
        pending_records: List[Dict[str, Any]] = []

        for r in reconciled_records:
            st = str(r.get("Status", "")).strip().upper()
            tp = str(r.get("Transit Pass", "")).strip().upper()
            is_comp = (st == "COMPLETED" or tp.startswith("TP"))
            
            if is_comp:
                r["Status"] = "COMPLETED"
                eff_k = get_record_effective_date_key(r, default_date_key=parsed_date)
                if not eff_k or len(eff_k) != 8:
                    eff_k = parsed_date
                completed_by_date.setdefault(eff_k, []).append(r)
            elif st == "PENDING":
                pending_records.append(r)

        # Global completed indent index: newly completed + all existing in config_dir
        all_completed_iids_global = {get_unique_indent_id(r) for recs in completed_by_date.values() for r in recs}
        for bf in glob.glob(os.path.join(config_dir, "backup_permits_*.json")):
            if "latest.json" in bf:
                continue
            try:
                with open(bf, "r", encoding="utf-8") as fp:
                    bdata = json.load(fp) or []
                for it in bdata:
                    if str(it.get("Status", "")).upper() == "COMPLETED" or str(it.get("Transit Pass", "")).upper().startswith("TP"):
                        all_completed_iids_global.add(get_unique_indent_id(it))
            except Exception:
                pass

        # Valid pending: drop any indent that is completed anywhere
        valid_pending = [r for r in pending_records if get_unique_indent_id(r) not in all_completed_iids_global]

        # For canonical_records (the target parsed_date file):
        # 1. Completed dispatches whose effective date strictly matches parsed_date
        target_completed = completed_by_date.get(parsed_date, [])
        # 2. Truly pending indents whose Application Date matches parsed_date
        canonical_pending = []
        for r in valid_pending:
            app_d = parse_date_str(r.get("Application Date") or r.get("Date"))
            app_k = app_d.strftime("%Y%m%d") if app_d else parsed_date
            if app_k == parsed_date:
                canonical_pending.append(r)

        canonical_records = clean_permit_records(canonical_pending + target_completed, config_dir=config_dir)
        LATEST_WEBHOOK_DATA = canonical_records
            
        with open(os.path.join(config_dir, canonical_filename), "w") as f:
            json.dump(canonical_records, f, indent=4)
        with open(os.path.join(config_dir, latest_filename), "w") as f:
            json.dump(canonical_records, f, indent=4)
            
        # Bidirectional cross-day attribution: for ANY other date where eff_k != parsed_date
        # (both eff_k < parsed_date like prior-day dispatches AND eff_k > parsed_date like permits applied earlier but approved on a later date)
        for o_date, o_recs in completed_by_date.items():
            if o_date == parsed_date:
                continue
            o_filename = f"backup_permits_{o_date}_000000.json"
            o_path = os.path.join(config_dir, o_filename)
            existing_o_data = []
            if os.path.exists(o_path):
                try:
                    with open(o_path, "r", encoding="utf-8") as of:
                        existing_o_data = json.load(of) or []
                except Exception:
                    existing_o_data = []
            
            o_keys = {get_unique_permit_key(it) for it in existing_o_data}
            # Purge any stale pending entries for indents that are now completed!
            existing_o_data = [
                it for it in existing_o_data
                if not (str(it.get("Status", "")).upper() == "PENDING" and get_unique_indent_id(it) in all_completed_iids_global)
            ]
            updated = False
            for nr in o_recs:
                nr_key = get_unique_permit_key(nr)
                if nr_key not in o_keys:
                    existing_o_data.append(nr)
                    o_keys.add(nr_key)
                    updated = True
                    
            if updated or any(str(it.get("Status", "")).upper() == "PENDING" and get_unique_indent_id(it) in all_completed_iids_global for it in existing_o_data):
                cleaned_o = clean_permit_records(existing_o_data, config_dir=config_dir)
                with open(o_path, "w", encoding="utf-8") as of:
                    json.dump(cleaned_o, of, indent=4)
                print(f"🔄 Cross-day sync: Updated {o_filename} with {len(o_recs)} crossover dispatches (eff_k={o_date}) & purged completed pending")

        # Global purge of stale pending indents across ALL backup files:
        # If an indent was completed in this run, ensure NO backup file still lists it as PENDING!
        if all_completed_iids_global:
            for bf in glob.glob(os.path.join(config_dir, "backup_permits_*.json")):
                if "latest.json" in bf or os.path.basename(bf) == canonical_filename:
                    continue
                try:
                    with open(bf, "r", encoding="utf-8") as fp:
                        bdata = json.load(fp) or []
                    has_stale = any(str(it.get("Status", "")).upper() == "PENDING" and get_unique_indent_id(it) in all_completed_iids_global for it in bdata)
                    if has_stale:
                        bdata_purged = [it for it in bdata if not (str(it.get("Status", "")).upper() == "PENDING" and get_unique_indent_id(it) in all_completed_iids_global)]
                        with open(bf, "w", encoding="utf-8") as fp:
                            json.dump(bdata_purged, fp, indent=4)
                        print(f"🧹 Purged stale pending indents from {os.path.basename(bf)}")
                except Exception as e_purge:
                    print(f"⚠️ Error purging stale pending from {bf}: {e_purge}")
            
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
    
    valid_keys = set()
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
    if not valid_keys:
        return JSONResponse(status_code=503, content={"error": "Cron secret not configured"})
    
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

@app.post("/api/admin/sync-seed-data")
@app.get("/api/admin/sync-seed-data")
async def admin_sync_seed_data(request: Request):
    """
    Manually triggers bundled data sync into active runtime DATA_DIR.
    """
    user = auth.get_current_user(request)
    secret = request.query_params.get("secret") or request.headers.get("x-cron-secret")
    expected_secret = (os.environ.get("WEBHOOK_SECRET") or os.environ.get("CRON_SECRET") or "").strip()
    if not expected_secret:
        cron_secret_file = os.path.join(automation_utils.get_data_dir(), ".cron_secret")
        if os.path.exists(cron_secret_file):
            try:
                with open(cron_secret_file, "r") as cf:
                    k = cf.read().strip()
                    if k: expected_secret = k
            except Exception: pass
    if not user and not expected_secret:
        return JSONResponse(status_code=503, content={"error": "Admin sync secret not configured"})
    if not user and secret != expected_secret:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
    force = request.query_params.get("force", "").lower() in ["true", "1", "yes"]
    res = sync_bundled_data(force=force)
    return JSONResponse(content=res)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
