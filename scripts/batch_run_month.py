import os
import sys
import argparse
import subprocess
from datetime import datetime, timedelta

def parse_args():
    parser = argparse.ArgumentParser(description="Batch Scraper for Month to Date")
    parser.add_argument("--start-date", type=str, help="Start date in DD-MM-YYYY format (defaults to 1st of current month)")
    parser.add_argument("--end-date", type=str, help="End date in DD-MM-YYYY format (defaults to today)")
    parser.add_argument("--bond", type=str, choices=["IMFL", "CS", "BOTH"], default="BOTH", help="Bond credentials to query")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Disable headless mode")
    parser.add_argument("--lookback-days", type=int, default=7, help="Lookback window for pending permits")
    return parser.parse_args()

def main():
    args = parse_args()
    
    today = datetime.now()
    
    if args.start_date:
        start_dt = datetime.strptime(args.start_date, "%d-%m-%Y")
    else:
        # 1st of current month
        start_dt = datetime(today.year, today.month, 1)
        
    if args.end_date:
        end_dt = datetime.strptime(args.end_date, "%d-%m-%Y")
    else:
        end_dt = today
        
    if start_dt > end_dt:
        print("❌ Error: start-date must be before or equal to end-date.")
        sys.exit(1)
        
    # Generate dates list
    current_dt = start_dt
    date_list = []
    while current_dt <= end_dt:
        date_list.append(current_dt)
        current_dt += timedelta(days=1)
        
    total_days = len(date_list)
    print(f"🚀 Starting Batch Monthly Scraper:")
    print(f"   • Range: {start_dt.strftime('%d-%b-%Y')} ➡️ {end_dt.strftime('%d-%b-%Y')} ({total_days} days)")
    print(f"   • Bond Credentials: {args.bond}")
    print(f"   • Headless Mode: {args.headless}")
    print(f"   • Lookback: {args.lookback_days} days per run")
    print("═" * 65)
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script_path = os.path.join(project_root, "scripts", "main_permits.py")
    python_exe = sys.executable
    
    successful_days = []
    failed_days = []
    
    for idx, dt in enumerate(date_list, start=1):
        d_str = dt.strftime("%d-%m-%Y")
        d_disp = dt.strftime("%d-%b-%Y")
        
        print(f"\n[{idx}/{total_days}] 📅 Processing Date: {d_disp} ({d_str})...")
        print("─" * 50)
        
        cmd = [
            python_exe, "-u", script_path,
            "--date", d_str,
            "--bond", args.bond,
            "--lookback-days", str(args.lookback_days)
        ]
        if not args.headless:
            cmd.append("--no-headless")
            
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            
            res = subprocess.run(cmd, cwd=project_root, env=env)
            if res.returncode == 0:
                print(f"✅ Successfully scraped and reconciled: {d_disp}")
                successful_days.append(d_disp)
            else:
                print(f"⚠️ Warning: Scraper exited with code {res.returncode} for date {d_disp}")
                failed_days.append(d_disp)
        except Exception as e:
            print(f"❌ Error running scraper for {d_disp}: {e}")
            failed_days.append(d_disp)
            
    print("\n" + "═" * 65)
    print(f"🏁 Batch Run Completed Summary:")
    print(f"   • Total Days Target: {total_days}")
    print(f"   • Successful Days: {len(successful_days)} ({', '.join(successful_days) if successful_days else 'None'})")
    if failed_days:
        print(f"   • Failed Days: {len(failed_days)} ({', '.join(failed_days)})")
    print("═" * 65)

if __name__ == "__main__":
    main()
