import os
import sys
import json
import glob
import asyncio
import argparse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Add scripts directory to path to import helpers
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(PROJECT_ROOT, "scripts"))

from pdf_report import generate_report_pdf

app = FastAPI(title="PermTrack - Assam Excise Revenue Tracker")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Permit Tracker Dashboard</h1><p>Static index.html not found.</p>"

@app.get("/api/today-permits")
async def get_today_permits(filename: str = None):
    """
    Returns latest scraped permits or specified backup file.
    """
    global LATEST_WEBHOOK_DATA
    config_dir = os.path.join(PROJECT_ROOT, "config")
    
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
            backup_files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
            backup_files = [f for f in backup_files if "latest.json" not in f]
            
            if not backup_files:
                fallback = os.path.join(config_dir, "backup_permits_latest.json")
                if os.path.exists(fallback):
                    latest_backup = fallback
                else:
                    return JSONResponse(content={"date": None, "pending": [], "completed": []})
            else:
                backup_files.sort(key=os.path.getmtime, reverse=True)
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
            
    pending = []
    completed = []
    target_date = None
    
    for item in data:
        if not target_date:
            target_date = item.get("Date")
        
        status = item.get("Status", "").upper()
        if status == "PENDING":
            pending.append(item)
        elif status == "COMPLETED":
            completed.append(item)
            
    return JSONResponse(content={
        "date": target_date,
        "filename": latest_backup_name,
        "pending": pending,
        "completed": completed
    })

@app.get("/api/download-pdf")
async def download_pdf_report(filename: str = None):
    """
    Retrieves selected permit JSON file and returns PDF report.
    """
    config_dir = os.path.join(PROJECT_ROOT, "config")
    
    if filename:
        filename = os.path.basename(filename)
        target_path = os.path.join(config_dir, filename)
        if not os.path.exists(target_path) or not filename.startswith("backup_permits_"):
            return JSONResponse(status_code=404, content={"error": "Backup file not found"})
        latest_backup = target_path
    else:
        backup_files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
        backup_files = [f for f in backup_files if "latest.json" not in f]
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
            backup_files.sort(key=os.path.getmtime, reverse=True)
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
async def get_backups():
    """
    Returns deduplicated, hierarchically sorted list of available date backups.
    """
    from datetime import datetime, timedelta
    config_dir = os.path.join(PROJECT_ROOT, "config")
    backup_files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
    backup_files = [f for f in backup_files if "latest.json" not in f]
    
    by_date = {}
    today_str = datetime.now().strftime("%Y%m%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    
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
            dt = datetime(int(year), int(month), int(day))
            formatted_date = dt.strftime("%d-%b-%Y")
        except:
            formatted_date = f"{day}-{month}-{year}"
            
        if date_key == today_str:
            display_name = f"Today ({formatted_date})"
        elif date_key == yesterday_str:
            display_name = f"Yesterday ({formatted_date})"
        else:
            display_name = formatted_date
            
        results.append({
            "filename": item["filename"],
            "display": display_name,
            "date_key": date_key
        })
        
    return JSONResponse(content=results)

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
            
        LATEST_WEBHOOK_DATA = records
        
        config_dir = os.path.join(PROJECT_ROOT, "config")
        os.makedirs(config_dir, exist_ok=True)
        
        from datetime import datetime
        parsed_date = None
        for item in records:
            d = item.get("Date")
            if d:
                try:
                    dt = datetime.strptime(d, "%d-%b-%Y")
                    parsed_date = dt.strftime("%Y%m%d")
                    break
                except: pass
        if not parsed_date:
            parsed_date = datetime.now().strftime("%Y%m%d")
            
        canonical_filename = f"backup_permits_{parsed_date}_000000.json"
        latest_filename = "backup_permits_latest.json"
        
        with open(os.path.join(config_dir, canonical_filename), "w") as f:
            json.dump(records, f, indent=4)
        with open(os.path.join(config_dir, latest_filename), "w") as f:
            json.dump(records, f, indent=4)
            
        # Clean up any extra timestamp files for the same target date
        for old_f in glob.glob(os.path.join(config_dir, f"backup_permits_{parsed_date}_*.json")):
            if os.path.basename(old_f) != canonical_filename:
                try: os.remove(old_f)
                except: pass
                
        print(f"📥 Received {len(records)} scraped records via webhook for date {date_str} -> saved to {canonical_filename}")
        return JSONResponse(content={
            "status": "success",
            "message": f"Saved {len(records)} records for date {date_str}",
            "filename": canonical_filename
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to save uploaded records: {str(e)}"})

@app.post("/api/trigger-run")
async def trigger_github_run(request: Request):
    """
    Triggers GitHub Actions repository_dispatch event to run permit scraper in cloud.
    """
    try:
        body = await request.json()
        date_val = body.get("date", "").strip()
        bond_val = body.get("bond", "BOTH")
        
        gh_token = os.environ.get("GITHUB_TOKEN")
        gh_repo = os.environ.get("GITHUB_REPO")
        
        if not gh_token or not gh_repo:
            return JSONResponse(content={
                "status": "local_fallback",
                "message": "GitHub Actions secrets not configured. Falling back to local execution."
            })
            
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
                "bond": bond_val
            }
        }
        
        res = requests.post(dispatch_url, headers=headers, json=payload, timeout=10)
        if res.status_code in [204, 200]:
            return JSONResponse(content={
                "status": "success",
                "message": "🚀 Triggered GitHub Action scraper workflow successfully!"
            })
        else:
            return JSONResponse(status_code=res.status_code, content={
                "error": f"GitHub API error: {res.text}"
            })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.websocket("/ws/run")
async def websocket_run(websocket: WebSocket):
    await websocket.accept()
    print("🔌 Client connected to logs WebSocket.")
    
    running_process = None
    try:
        data = await websocket.receive_text()
        config = json.loads(data)
        
        target_date_val = config.get("date", "").strip()
        bond_type = config.get("bond", "BOTH")
        headless = config.get("headless", True)
        
        args_list = []
        if target_date_val:
            args_list.extend(["--date", target_date_val])
        if bond_type:
            args_list.extend(["--bond", bond_type])
        if not headless:
            args_list.append("--no-headless")
            
        script_path = os.path.join(PROJECT_ROOT, "scripts", "main_permits.py")
        if not os.path.exists(script_path):
            await websocket.send_text(f"❌ Error: Script not found at {script_path}\n")
            await websocket.close()
            return
            
        python_exe = sys.executable
        cmd = [python_exe, "-u", script_path] + args_list
        
        await websocket.send_text(f"🛠️ Starting Permit Scraper: {' '.join(cmd)}\n")
        await websocket.send_text("═" * 60 + "\n")
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        running_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=PROJECT_ROOT,
            env=env
        )
        
        while True:
            line = await running_process.stdout.readline()
            if not line:
                break
            decoded_line = line.decode("utf-8", errors="ignore")
            await websocket.send_text(decoded_line)
            await asyncio.sleep(0.001)
            
        returncode = await running_process.wait()
        
        await websocket.send_text("\n" + "═" * 60 + "\n")
        if returncode == 0:
            await websocket.send_text(f"🎉 SUCCESS: Scraper finished with exit code 0\n")
            await websocket.send_json({"status": "success", "code": 0})
        else:
            await websocket.send_text(f"❌ FAILURE: Scraper exited with code {returncode}\n")
            await websocket.send_json({"status": "failed", "code": returncode})
            
    except WebSocketDisconnect:
        print("🔌 Client disconnected from WebSocket.")
        if running_process:
            try:
                running_process.terminate()
                await asyncio.wait_for(running_process.wait(), timeout=5.0)
            except:
                try:
                    running_process.kill()
                    await running_process.wait()
                except: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)
