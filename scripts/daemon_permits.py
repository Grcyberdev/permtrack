#!/usr/bin/env python3
"""
PermTrack Live Daemon - 5-Minute Persistent Excise Portal Synchronization.

Key architectural features:
1. Persistent Session: Keeps Chrome open and authenticated. Does NOT login/logout on every cycle.
2. 5-Minute Refresh: Refreshes the Stock Dispatch page every 5 minutes (default 300s).
   Because the interval is under the portal's PHP session timeout (15-20 min), the session never expires.
3. Auto-Relogin Watchdog: If the portal kicks the user out (302 redirect to /site/login),
   the daemon catches it gracefully, solves the captcha via ddddocr, re-authenticates, and resumes without crashing.
4. Fast Incremental Scrape: Retains an in-memory verified cache of all completed passes.
   Already-scraped passes are skipped in milliseconds; only newly issued passes trigger Form-34 extraction.
5. Direct Live Upload: Posts verified payloads directly to the Fly.io portal (/api/upload-results).
"""

import os
import sys
import time
import signal
import argparse
import traceback
from datetime import datetime, timedelta, timezone

# Ensure scripts dir is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import automation_utils
from main_permits import (
    open_and_parse_strict_modal,
    open_and_parse_form34,
    scrape_permits_from_stock_dispatch,
    load_completed_cache,
    ensure_active_proxy,
    upload_results_to_server
)
from reconciler import (
    clean_permit_records,
    get_unique_indent_id,
    get_record_effective_date_key,
    reconcile_permits,
    get_unique_permit_key,
    get_reconciliation_summary
)

IST = timezone(timedelta(hours=5, minutes=30))

class PermTrackDaemon:
    def __init__(self, interval=300, bond="BOTH", headless=True, lookback_days=7):
        self.interval = interval
        self.bond = bond
        self.headless = headless
        self.lookback_days = lookback_days
        self.running = True
        self.drivers = {}  # { "IMFL": driver, "CS": driver }
        self.completed_cache = {}
        
        # Register graceful termination
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame):
        print("\n🛑 PermTrack Daemon stopping gracefully...")
        self.running = False
        self._cleanup_drivers()
        sys.exit(0)

    def _cleanup_drivers(self):
        for bond, driver in list(self.drivers.items()):
            try:
                print(f"🧹 Closing Chrome session for {bond}...")
                driver.quit()
            except Exception:
                pass
        self.drivers.clear()

    def _ensure_session(self, bond_type, username, password):
        """
        Ensures an active, authenticated Chrome browser session exists for the given bond.
        If browser is not started, starts it and logs in.
        If session expired (redirected to login), re-authenticates automatically.
        """
        driver = self.drivers.get(bond_type)
        config = automation_utils.load_config()
        portal_url = config.get("portal_url", "https://stateexcise.assam.gov.in/index.php/site/login")
        
        # 1. Start browser if not running
        if not driver:
            print(f"🚀 Starting persistent Chrome browser for {bond_type}...")
            ensure_active_proxy()
            driver = automation_utils.setup_driver(headless=self.headless)
            self.drivers[bond_type] = driver
            
            print(f"🔑 Initial login for {bond_type} ({username})...")
            ok = automation_utils.login_to_portal(driver, portal_url, username, password, max_retries=15)
            if not ok:
                print(f"❌ Failed initial login for {bond_type}.")
                try: driver.quit()
                except: pass
                self.drivers.pop(bond_type, None)
                return None
            return driver

        # 2. Check if browser is still healthy and not kicked out
        try:
            curr_url = driver.current_url.lower()
            # If kicked out to login page
            if "site/login" in curr_url or "login" in curr_url:
                print(f"⚠️ [Session Watchdog] Portal session timed out or kicked out for {bond_type}. Re-authenticating...")
                ok = automation_utils.login_to_portal(driver, portal_url, username, password, max_retries=12)
                if not ok:
                    print(f"❌ Re-authentication failed for {bond_type}. Will retry next cycle.")
                    return None
                print(f"✅ Successfully re-authenticated {bond_type} session!")
            return driver
        except Exception as e_check:
            print(f"⚠️ Browser instance error for {bond_type}: {e_check}. Restarting Chrome...")
            try: driver.quit()
            except: pass
            self.drivers.pop(bond_type, None)
            return self._ensure_session(bond_type, username, password)

    def run_single_cycle(self):
        """Executes a single fast incremental scrape cycle across configured bonds."""
        now_ist = datetime.now(IST)
        date_str = now_ist.strftime("%d-%b-%Y")
        cycle_start = time.time()
        print(f"\n" + "="*70)
        print(f"⚡ [PermTrack Daemon] Starting sync tick at {now_ist.strftime('%H:%M:%S IST')} for date: {date_str}")
        print("="*70)
        
        config = automation_utils.load_config()
        imfl_user = config.get("IMFL_USERNAME")
        imfl_pass = config.get("IMFL_PASSWORD")
        cs_user = config.get("CS_USERNAME")
        cs_pass = config.get("CS_PASSWORD")
        
        # Pre-load existing cache on first run if empty
        if not self.completed_cache:
            self.completed_cache = load_completed_cache(now_ist, lookback_days=self.lookback_days)
            print(f"📦 Daemon in-memory cache initialized with {len(self.completed_cache)} completed indent keys.")
            
        bonds_to_run = []
        if self.bond in ["IMFL", "BOTH"] and imfl_user and imfl_pass:
            bonds_to_run.append(("IMFL", imfl_user, imfl_pass))
        if self.bond in ["CS", "BOTH"] and cs_user and cs_pass:
            bonds_to_run.append(("CS", cs_user, cs_pass))
            
        all_pending = []
        all_completed = []
        cycle_errors = 0
        
        from selenium.webdriver.support.ui import WebDriverWait
        
        for bond_type, username, password in bonds_to_run:
            driver = self._ensure_session(bond_type, username, password)
            if not driver:
                print(f"⚠️ Skipping {bond_type} in this tick (session unavailable).")
                continue
                
            wait = WebDriverWait(driver, 15)
            try:
                # 1. Scrape Pending Indents (lookback 7 days)
                p_recs, p_ok, p_errs = scrape_permits_from_stock_dispatch(
                    driver, wait, now_ist, bond_type, status_filter="Pending",
                    lookback_days=self.lookback_days, completed_cache=self.completed_cache
                )
                all_pending.extend(p_recs)
                cycle_errors += p_errs
                
                # 2. Scrape Completed Dispatches (incremental with cache)
                c_recs, c_ok, c_errs = scrape_permits_from_stock_dispatch(
                    driver, wait, now_ist, bond_type, status_filter="Pass Issued",
                    lookback_days=2, completed_cache=self.completed_cache
                )
                all_completed.extend(c_recs)
                cycle_errors += c_errs
                
            except Exception as e_scrape:
                print(f"❌ Error during {bond_type} scrape in daemon: {e_scrape}")
                traceback.print_exc()
                cycle_errors += 1
                
        cycle_duration = time.time() - cycle_start
        print(f"\n📊 Cycle Results: {len(all_pending)} pending SKUs, {len(all_completed)} completed SKUs (errors: {cycle_errors}) in {cycle_duration:.1f}s")
        
        # 3. Clean, Monotonically Merge, Reconcile, and Upload results if any records were obtained
        if all_pending or all_completed:
            backup_dir = automation_utils.get_data_dir()
            os.makedirs(backup_dir, exist_ok=True)
            timestamp_file = f"backup_permits_{now_ist.strftime('%Y%m%d')}_000000.json"
            canonical_path = os.path.join(backup_dir, timestamp_file)
            latest_path = os.path.join(backup_dir, "backup_permits_latest.json")

            # Intelligently preserve verified completed dispatches from earlier backups.
            # If any indent in existing_completed is degraded (fewer cases) or suffered extraction errors in current run,
            # or was omitted due to lookback/pagination, restore the verified lines from earlier backup.
            existing_completed = []
            if os.path.exists(canonical_path):
                try:
                    import json
                    with open(canonical_path, "r", encoding="utf-8") as f:
                        existing_data = json.load(f) or []
                    for item in existing_data:
                        if str(item.get("Status", "")).upper() == "COMPLETED":
                            existing_completed.append(item)
                    if existing_completed:
                        print(f"📦 Found existing backup for {date_str} with {len(existing_completed)} completed dispatch lines.")
                except Exception as e_read:
                    print(f"⚠️ Could not read existing backup {canonical_path}: {e_read}")

            existing_indent_cases = {}
            for ex in existing_completed:
                iid = get_unique_indent_id(ex)
                existing_indent_cases[iid] = existing_indent_cases.get(iid, 0.0) + float(ex.get("Cases") or 0)

            current_indent_cases = {}
            current_indent_has_valid_skus = set()
            for c in all_completed:
                pname = str(c.get("Product Name") or "").strip().upper()
                is_err = bool(c.get("extraction_error")) or (pname in ["EXTRACTION_FAILED", "UNKNOWN"]) or (not pname and float(c.get("Cases") or 0) == 0 and int(c.get("Bottles") or 0) == 0 and float(c.get("Total MRP") or 0) == 0)
                if not is_err:
                    iid = get_unique_indent_id(c)
                    current_indent_cases[iid] = current_indent_cases.get(iid, 0.0) + float(c.get("Cases") or 0)
                    if float(c.get("Cases") or 0) > 0 or int(c.get("Bottles") or 0) > 0 or float(c.get("Total MRP") or 0) > 0:
                        current_indent_has_valid_skus.add(iid)

            degraded_or_missing_indents = set()
            for iid, ex_c in existing_indent_cases.items():
                inc_c = current_indent_cases.get(iid, 0.0)
                if iid not in current_indent_has_valid_skus or inc_c < (ex_c - 0.01):
                    degraded_or_missing_indents.add(iid)

            # Prune any failed/degraded placeholder lines from all_completed
            all_completed = [
                c for c in all_completed
                if not (
                    get_unique_indent_id(c) in degraded_or_missing_indents
                    or bool(c.get("extraction_error"))
                    or str(c.get("Product Name") or "").strip().upper() in ["EXTRACTION_FAILED", "UNKNOWN"]
                    or (not str(c.get("Product Name") or "").strip() and float(c.get("Cases") or 0) == 0 and int(c.get("Bottles") or 0) == 0 and float(c.get("Total MRP") or 0) == 0)
                )
            ]

            current_completed_keys = {get_unique_permit_key(c) for c in all_completed}
            preserved_completed = []
            for ex_item in existing_completed:
                ex_iid = get_unique_indent_id(ex_item)
                ex_key = get_unique_permit_key(ex_item)
                if ex_iid in degraded_or_missing_indents or ex_key not in current_completed_keys:
                    if ex_key not in current_completed_keys:
                        preserved_completed.append(ex_item)
                        current_completed_keys.add(ex_key)

            if preserved_completed:
                print(f"🛡️ Preserved {len(preserved_completed)} completed dispatch lines from earlier backup to prevent data loss.")
                all_completed.extend(preserved_completed)

            raw_combined = all_pending + all_completed
            # Pass config_dir to clean_permit_records so historical MRPs are backfilled
            cleaned_records = clean_permit_records(raw_combined, config_dir=backup_dir)

            print(f"\n🔄 Running 7-day cross-day reconciliation engine in daemon...")
            reconciled_records = reconcile_permits(raw_combined, now_ist, backup_dir, lookback_days=self.lookback_days)

            target_date_key = now_ist.strftime("%Y%m%d")
            target_records_to_save = [
                r for r in reconciled_records
                if str(r.get("Status", "")).upper() == "PENDING" or get_record_effective_date_key(r, default_date_key=target_date_key) == target_date_key
            ]

            import json
            with open(canonical_path, "w", encoding="utf-8") as f:
                json.dump(target_records_to_save, f, indent=4)
            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump(target_records_to_save, f, indent=4)

            # Cross-day attribution for completed dispatches belonging to other dates
            try:
                cross_date_completed = {}
                for r in all_completed:
                    if str(r.get("Status", "")).upper() == "COMPLETED" or str(r.get("Transit Pass", "")).upper().startswith("TP"):
                        eff_k = get_record_effective_date_key(r, default_date_key=target_date_key)
                        if eff_k and eff_k != target_date_key:
                            cross_date_completed.setdefault(eff_k, []).append(r)

                for p_date, p_recs in cross_date_completed.items():
                    p_filename = f"backup_permits_{p_date}_000000.json"
                    p_path = os.path.join(backup_dir, p_filename)
                    p_data = []
                    if os.path.exists(p_path):
                        try:
                            with open(p_path, "r", encoding="utf-8") as pf:
                                p_data = json.load(pf) or []
                        except Exception:
                            p_data = []
                    p_keys = {get_unique_permit_key(it) for it in p_data}
                    p_completed_iids = {get_unique_indent_id(it) for it in p_recs}
                    p_data = [it for it in p_data if not (str(it.get("Status", "")).upper() == "PENDING" and get_unique_indent_id(it) in p_completed_iids)]
                    p_updated = False
                    for nr in p_recs:
                        nr_key = get_unique_permit_key(nr)
                        if nr_key not in p_keys:
                            p_data.append(nr)
                            p_keys.add(nr_key)
                            p_updated = True
                    if p_updated:
                        cleaned_p = clean_permit_records(p_data, config_dir=backup_dir)
                        with open(p_path, "w", encoding="utf-8") as pf:
                            json.dump(cleaned_p, pf, indent=4)
                        print(f"🔄 Cross-day sync: Updated {p_filename} with {len(p_recs)} crossover dispatches (eff_k={p_date}).")
            except Exception as e_cross:
                print(f"⚠️ Cross-day backfill error in daemon: {e_cross}")

            # Update self.completed_cache with newly scraped completed indents after each cycle
            for r in all_completed:
                if str(r.get("Status", "")).upper() == "COMPLETED" and r.get("Product Name") and not r.get("extraction_error"):
                    ind = (r.get("Indent Number") or "").strip()
                    pmt = (r.get("Permit Number") or "").strip()
                    if ind:
                        if ind not in self.completed_cache:
                            self.completed_cache[ind] = []
                        if not any(get_unique_permit_key(x) == get_unique_permit_key(r) for x in self.completed_cache[ind]):
                            self.completed_cache[ind].append(r)
                    if pmt:
                        if pmt not in self.completed_cache:
                            self.completed_cache[pmt] = []
                        if not any(get_unique_permit_key(x) == get_unique_permit_key(r) for x in self.completed_cache[pmt]):
                            self.completed_cache[pmt].append(r)

            # Upload to Fly.io portal
            try:
                print("📡 Pushing live incremental updates to PermTrack portal...")
                upload_results_to_server(reconciled_records, target_date=now_ist, has_errors=(cycle_errors > 0))
            except Exception as e_up:
                print(f"⚠️ Live upload warning: {e_up}")

        print(f"💤 Sleeping for {self.interval} seconds (next cycle at {(datetime.now(IST) + timedelta(seconds=self.interval)).strftime('%H:%M:%S IST')})...")

    def start(self):
        """Main loop that executes cycles every `interval` seconds."""
        print("="*70)
        print(f"🌟 PermTrack 5-Minute Live Daemon Started")
        print(f"   Polling Interval : {self.interval} seconds (5 mins)")
        print(f"   Bond Credentials : {self.bond}")
        print(f"   Headless Mode    : {self.headless}")
        print(f"   Lookback Days    : {self.lookback_days}")
        print("="*70)
        
        while self.running:
            try:
                self.run_single_cycle()
            except Exception as e:
                print(f"🚨 Unexpected daemon cycle error: {e}")
                traceback.print_exc()
                
            # Sleep in 1-second chunks so Ctrl+C responds immediately
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

def main():
    parser = argparse.ArgumentParser(description="PermTrack 5-Minute Persistent Live Scraper Daemon")
    parser.add_argument("--interval", type=int, default=300, help="Polling interval in seconds (default: 300 = 5 mins)")
    parser.add_argument("--bond", choices=["IMFL", "CS", "BOTH"], default="BOTH", help="Bond credentials to run (default: BOTH)")
    parser.add_argument("--no-headless", action="store_true", help="Run Chrome in visible GUI mode (default: headless)")
    parser.add_argument("--lookback-days", type=int, default=7, help="Lookback days for pending permits (default: 7)")
    args = parser.parse_args()

    daemon = PermTrackDaemon(
        interval=args.interval,
        bond=args.bond,
        headless=not args.no_headless,
        lookback_days=args.lookback_days
    )
    daemon.start()

if __name__ == "__main__":
    main()
