import os
import glob
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional

def parse_date_str(date_str: Optional[str]) -> Optional[datetime]:
    """Parses various date string formats used in the system."""
    if not date_str:
        return None
    date_str = str(date_str).strip()
    
    formats = ["%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def normalize_key(val: Any) -> str:
    """Normalizes string keys for consistent matching."""
    return str(val or "").strip().upper()

def get_unique_permit_key(item: Dict[str, Any]) -> str:
    """Generates a composite unique key for an indent/permit row."""
    indent = normalize_key(item.get("Indent Number"))
    permit = normalize_key(item.get("Permit Number"))
    retailer_code = normalize_key(item.get("Retailer Code"))
    product = normalize_key(item.get("Product Name"))
    size = normalize_key(item.get("Size"))
    
    if indent and product:
        return f"{indent}::{product}::{size}"
    if indent:
        return f"{indent}::{retailer_code}"
    if permit and product:
        return f"{permit}::{product}::{size}"
    return f"{retailer_code}::{product}::{size}"

def get_unique_indent_id(item: Dict[str, Any]) -> str:
    """Returns primary indent identifier for higher-level permit tracking."""
    indent = normalize_key(item.get("Indent Number"))
    permit = normalize_key(item.get("Permit Number"))
    if indent:
        return indent
    if permit:
        return permit
    return f"{normalize_key(item.get('Retailer Code'))}_{normalize_key(item.get('Retailer Name'))}"

def load_historical_backups(config_dir: str, target_date: datetime, max_lookback_days: int = 7) -> List[Tuple[datetime, str, List[Dict[str, Any]]]]:
    """
    Loads backup files within the lookback window (target_date - max_lookback_days to target_date - 1 day).
    Returns list of tuples: (backup_date, filepath, records).
    """
    if not os.path.exists(config_dir):
        return []
        
    backup_files = glob.glob(os.path.join(config_dir, "backup_permits_*.json"))
    backup_files = [f for f in backup_files if "latest.json" not in f]
    
    historical = []
    target_date_only = target_date.date()
    min_date = target_date_only - timedelta(days=max_lookback_days)
    
    for filepath in backup_files:
        basename = os.path.basename(filepath)
        ts = basename.replace("backup_permits_", "").replace(".json", "")
        date_key = ts.split("_")[0]
        
        if not date_key.isdigit() or len(date_key) != 8:
            continue
            
        try:
            b_dt = datetime.strptime(date_key, "%Y%m%d")
            b_date_only = b_dt.date()
            
            # Must be strictly before target_date and >= min_date
            if min_date <= b_date_only < target_date_only:
                with open(filepath, "r", encoding="utf-8") as f:
                    records = json.load(f)
                historical.append((b_dt, filepath, records))
        except Exception as e:
            print(f"⚠️ Error reading historical backup {filepath}: {e}")
            continue
            
    # Sort chronological (oldest to newest)
    historical.sort(key=lambda x: x[0])
    return historical

def reconcile_permits(
    current_records: List[Dict[str, Any]],
    target_date_input: Any,
    config_dir: str,
    lookback_days: int = 7
) -> List[Dict[str, Any]]:
    """
    Reconciles permit records for target_date against past historical backups (up to lookback_days).
    
    1. Identifies today's Completed (Dispatched) records and Today's Fresh Pending records.
    2. Gathers historical unapproved Pending permits from past backups within lookback_days.
    3. Cross-checks historical Pending against today's Completed dispatches:
       - If found in Completed -> Marks as 'FULFILLED_TODAY'.
       - If NOT in Completed and not in today's pending -> Carries over with aging tags.
    4. Expires items older than lookback_days (>7 days).
    5. Merges and deduplicates everything cleanly.
    """
    if isinstance(target_date_input, str):
        target_dt = parse_date_str(target_date_input) or datetime.now()
    elif isinstance(target_date_input, datetime):
        target_dt = target_date_input
    else:
        target_dt = datetime.now()
        
    target_date_str = target_dt.strftime("%d-%b-%Y")
    target_date_only = target_dt.date()
    
    # 1. Process current records (from today's scrape or file)
    current_pending = []
    current_completed = []
    
    # Track existing indent IDs and line keys in current scrape
    current_pending_keys = set()
    current_completed_keys = set()
    current_completed_indents = set()
    
    for item in current_records:
        rec = dict(item)
        status = normalize_key(rec.get("Status"))
        line_key = get_unique_permit_key(rec)
        indent_id = get_unique_indent_id(rec)
        
        # Ensure Date is set
        if not rec.get("Date"):
            rec["Date"] = target_date_str
            
        app_date_str = rec.get("Application Date")
        app_dt = parse_date_str(app_date_str) if app_date_str else None
        
        if status == "COMPLETED":
            current_completed_keys.add(line_key)
            current_completed_indents.add(indent_id)
            rec["Status"] = "COMPLETED"
            rec["is_carried_over"] = False
            rec["aging_days"] = 0
            
            # Check if this completed pass originated from a prior day's application
            if app_dt and app_dt.date() < target_date_only:
                turnaround = (target_date_only - app_dt.date()).days
                rec["fulfilled_from_carry_over"] = True
                rec["turnaround_days"] = turnaround
                rec["carried_over_from"] = app_dt.strftime("%d-%b-%Y")
            else:
                rec["fulfilled_from_carry_over"] = False
                rec["turnaround_days"] = 0
                
            current_completed.append(rec)
            
        elif status == "PENDING":
            current_pending_keys.add(line_key)
            rec["Status"] = "PENDING"
            
            # Determine if this pending item was applied today or is from a multi-day portal lookback
            if app_dt:
                app_date_only = app_dt.date()
                aging = max(0, (target_date_only - app_date_only).days)
                if aging > 0:
                    rec["is_carried_over"] = True
                    rec["aging_days"] = aging
                    rec["carried_over_from"] = app_dt.strftime("%d-%b-%Y")
                else:
                    rec["is_carried_over"] = False
                    rec["aging_days"] = 0
                    rec["carried_over_from"] = None
            else:
                # Default to today if no application date
                rec["is_carried_over"] = False
                rec["aging_days"] = 0
                rec["carried_over_from"] = None
                
            current_pending.append(rec)
            
        else:
            # Other statuses pass through
            current_pending.append(rec)
            
    # 2. Check if any current completed records fulfilled previous applications
    for rec in current_completed:
        indent_id = get_unique_indent_id(rec)
        app_date_str = rec.get("Application Date")
        app_dt = parse_date_str(app_date_str) if app_date_str else None
        if app_dt and app_dt.date() < target_date_only:
            rec["fulfilled_from_carry_over"] = True
            rec["turnaround_days"] = (target_date_only - app_dt.date()).days

    # 3. Load historical backups within lookback_days
    historical_backups = load_historical_backups(config_dir, target_dt, max_lookback_days=lookback_days)
    
    # Store unresolved historical pending items mapped by line_key
    historical_pending_pool: Dict[str, Dict[str, Any]] = {}
    
    for b_dt, _, b_records in historical_backups:
        b_date_str = b_dt.strftime("%d-%b-%Y")
        b_date_only = b_dt.date()
        
        for item in b_records:
            status = normalize_key(item.get("Status"))
            if status == "PENDING":
                line_key = get_unique_permit_key(item)
                indent_id = get_unique_indent_id(item)
                
                # Check if it was already fulfilled today in completed dispatches
                if line_key in current_completed_keys or indent_id in current_completed_indents:
                    # Successfully fulfilled today!
                    if line_key in historical_pending_pool:
                        del historical_pending_pool[line_key]
                    continue
                    
                # Check if already present in today's pending list (e.g. from portal lookback)
                if line_key in current_pending_keys:
                    continue
                    
                app_date_str = item.get("Application Date") or item.get("Date") or b_date_str
                app_dt = parse_date_str(app_date_str) or b_dt
                app_date_only = app_dt.date()
                
                aging = (target_date_only - app_date_only).days
                
                # Expire if strictly > lookback_days
                if aging > lookback_days or aging < 0:
                    continue
                    
                carried_rec = dict(item)
                carried_rec["Date"] = target_date_str
                carried_rec["Status"] = "PENDING"
                carried_rec["is_carried_over"] = True
                carried_rec["aging_days"] = aging
                carried_rec["carried_over_from"] = app_dt.strftime("%d-%b-%Y")
                carried_rec["Application Date"] = app_dt.strftime("%d-%b-%Y")
                carried_rec["source"] = "backup_reconciled"
                
                historical_pending_pool[line_key] = carried_rec
                
            elif status == "COMPLETED":
                # If a permit was completed in an earlier day's backup, remove from historical pending pool
                line_key = get_unique_permit_key(item)
                if line_key in historical_pending_pool:
                    del historical_pending_pool[line_key]

    # 4. Combine current pending + carried over pending from backups
    all_reconciled_pending = list(current_pending)
    for carried_rec in historical_pending_pool.values():
        all_reconciled_pending.append(carried_rec)
        
    # Sort pending: fresh today first, then by aging descending
    all_reconciled_pending.sort(
        key=lambda x: (
            1 if x.get("is_carried_over", False) else 0,
            -(x.get("aging_days", 0)),
            x.get("Retailer Name", "")
        )
    )
    
    # 5. Return unified combined records: Pending + Completed
    combined_result = all_reconciled_pending + current_completed
    return combined_result

def get_reconciliation_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes a high-level summary metrics dict of reconciled records.
    """
    fresh_pending = 0
    carried_over_pending = 0
    aging_breakdown = {"1_day": 0, "2_days": 0, "3_to_7_days": 0}
    
    fresh_completed = 0
    fulfilled_carry_overs = 0
    
    unique_pending_indents = set()
    unique_completed_indents = set()
    
    for r in records:
        status = normalize_key(r.get("Status"))
        indent_id = get_unique_indent_id(r)
        
        if status == "PENDING":
            unique_pending_indents.add(indent_id)
            if r.get("is_carried_over", False):
                carried_over_pending += 1
                age = r.get("aging_days", 1)
                if age == 1:
                    aging_breakdown["1_day"] += 1
                elif age == 2:
                    aging_breakdown["2_days"] += 1
                else:
                    aging_breakdown["3_to_7_days"] += 1
            else:
                fresh_pending += 1
                
        elif status == "COMPLETED":
            unique_completed_indents.add(indent_id)
            if r.get("fulfilled_from_carry_over", False):
                fulfilled_carry_overs += 1
            else:
                fresh_completed += 1
                
    return {
        "total_pending_lines": fresh_pending + carried_over_pending,
        "fresh_pending_lines": fresh_pending,
        "carried_over_pending_lines": carried_over_pending,
        "unique_pending_indents_count": len(unique_pending_indents),
        "unique_completed_indents_count": len(unique_completed_indents),
        "fulfilled_carry_overs_count": fulfilled_carry_overs,
        "aging_breakdown": aging_breakdown
    }
