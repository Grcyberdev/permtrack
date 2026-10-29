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

def get_record_effective_date_key(item: Dict[str, Any], default_date_key: Optional[str] = None) -> str:
    """
    Extracts the operational effective date (YYYYMMDD) for a permit record.
    Priority order:
    1. Challan Date (Form-34 physical stock dispatch date)
    2. Transit Pass embedded date (Assam Excise format: TP<wh_code 4 digits><DD><MM><YY><seq>)
    3. Record Date field
    4. default_date_key fallback
    """
    import re
    # 1. Challan Date (e.g. 16-Oct-2026, 16-10-2026, 2026-10-16)
    ch_raw = str(item.get("Challan Date") or "").strip()
    if ch_raw:
        dt = parse_date_str(ch_raw)
        if dt:
            return dt.strftime("%Y%m%d")

    # 2. Transit Pass embedded date (e.g. TP309716102600293 -> 16-10-2026 -> 20261016)
    tp_raw = str(item.get("Transit Pass") or "").strip()
    if tp_raw:
        m = re.match(r"^TP\d{4}(\d{2})(\d{2})(\d{2})", tp_raw)
        if m:
            dd, mm, yy = m.groups()
            try:
                dt = datetime(2000 + int(yy), int(mm), int(dd))
                return dt.strftime("%Y%m%d")
            except ValueError:
                pass

    # 3. Record Date field
    rec_date = str(item.get("Date") or "").strip()
    if rec_date:
        dt = parse_date_str(rec_date)
        if dt:
            return dt.strftime("%Y%m%d")

    return default_date_key or ""

def parse_effective_date(item: Dict[str, Any], default_dt: Optional[datetime] = None) -> Optional[datetime]:
    """Returns a datetime object representing the effective date of a permit record."""
    dkey = get_record_effective_date_key(item)
    if dkey and len(dkey) == 8 and dkey.isdigit():
        try:
            return datetime(int(dkey[:4]), int(dkey[4:6]), int(dkey[6:8]))
        except ValueError:
            pass
    return default_dt

def normalize_key(val: Any) -> str:
    """Normalizes string keys for consistent matching."""
    return str(val or "").strip().upper()

def normalize_size(size_val: Any) -> str:
    """Extracts base volume in ml from size string for unified SKU matching."""
    if not size_val:
        return ""
    import re
    digits = re.findall(r'\d+', str(size_val))
    return digits[0] if digits else str(size_val).strip()

def normalize_brand_key(name: Any) -> str:
    """Normalizes brand names by removing filler descriptors and non-alphanumeric chars."""
    if not name:
        return ""
    import re
    STOP_WORDS = {
        "PREMIUM", "SUPER", "STRONG", "LAGER", "BEER", "WHISKY", "WHISKEY", "RUM",
        "VODKA", "GIN", "BRANDY", "CAN", "BOTTLE", "DRAUGHT", "FINE", "DELUXE", "LUXURY",
        "SMOOTH", "CRAFT", "INDIA", "INDIAN", "SPECIAL", "SELECT", "RARE", "ML", "ORIGINAL"
    }
    raw = str(name).upper()
    tokens = [t for t in re.findall(r'[A-Za-z0-9]+', raw) if t not in STOP_WORDS]
    if not tokens:
        tokens = [t for t in re.findall(r'[A-Za-z0-9]+', raw)]
    return "".join(tokens)

def get_unique_permit_key(item: Dict[str, Any]) -> str:
    """Generates a composite unique key for an indent/permit row."""
    indent = normalize_key(item.get("Indent Number"))
    permit = normalize_key(item.get("Permit Number"))
    retailer_code = normalize_key(item.get("Retailer Code"))
    product = normalize_brand_key(item.get("Product Name"))
    size = normalize_size(item.get("Size"))
    
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
    
    # Pre-scan all completed indents and line keys in current_records
    for item in current_records:
        status = normalize_key(item.get("Status"))
        tp = item.get("Transit Pass")
        has_tp = bool(tp and str(tp).strip().upper().startswith("TP"))
        if status == "COMPLETED" or has_tp:
            current_completed_indents.add(get_unique_indent_id(item))
            current_completed_keys.add(get_unique_permit_key(item))
    
    for item in current_records:
        rec = dict(item)
        status = normalize_key(rec.get("Status"))
        line_key = get_unique_permit_key(rec)
        indent_id = get_unique_indent_id(rec)
        tp = rec.get("Transit Pass")
        has_tp = bool(tp and str(tp).strip().upper().startswith("TP"))
        
        # Ensure Date is set
        if not rec.get("Date"):
            rec["Date"] = target_date_str
            
        app_date_str = rec.get("Application Date")
        app_dt = parse_date_str(app_date_str) if app_date_str else None
        
        if status == "COMPLETED" or has_tp:
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
            # If this indent was already approved/dispatched today, it is NOT pending!
            if indent_id in current_completed_indents or line_key in current_completed_keys:
                continue
                
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
                
                product_name = normalize_key(item.get("Product Name"))
                # If the indent as a whole was completed today, or this specific line was completed, it is fulfilled!
                is_fulfilled = (indent_id in current_completed_indents) or (line_key in current_completed_keys)
                if is_fulfilled:
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
    
    # 5. Clean, sanitize, and deduplicate combined records
    combined_result = clean_permit_records(all_reconciled_pending + current_completed, config_dir=config_dir)
    return combined_result

def get_bpc_fallback(pack_size: Any, size: Any, category: Any) -> int:
    try:
        from automation_utils import get_bottles_per_case
        return get_bottles_per_case(pack_size, size, category)
    except Exception:
        return 12

def build_historical_sku_rates(config_dir: str) -> Dict[str, float]:
    """
    Builds a robust dictionary of known SKU MRP case rates from historical permit backups.
    Maps:
      1. f"{normalized_brand}_{normalized_size}" -> case_rate
      2. normalized_brand -> case_rate
    """
    rates: Dict[str, float] = {}
    if not config_dir or not os.path.exists(config_dir):
        return rates
        
    for p in glob.glob(os.path.join(config_dir, "backup_permits_*.json")):
        if "latest" in p:
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            for r in data:
                p_name = normalize_brand_key(r.get("Product Name"))
                size = normalize_size(r.get("Size"))
                try:
                    mrp = float(r.get("Total MRP") or 0)
                    cases = float(r.get("Cases") or 0)
                    bottles = float(r.get("Bottles") or 0)
                except (ValueError, TypeError):
                    continue
                if mrp > 0 and cases > 0 and bottles == 0 and p_name:
                    rate = mrp / cases
                    rates[f"{p_name}_{size}"] = rate
                    if p_name not in rates:
                        rates[p_name] = rate
        except Exception:
            pass
    return rates

def backfill_missing_mrps(records: List[Dict[str, Any]], sku_rates: Dict[str, float]) -> List[Dict[str, Any]]:
    """
    Backfills missing/zero Total MRP for records using known historical SKU rates.
    """
    if not sku_rates or not records:
        return records
        
    import re
    for r in records:
        try:
            cur_mrp = float(r.get("Total MRP") or 0)
            cases = float(r.get("Cases") or 0)
            bottles = float(r.get("Bottles") or 0)
        except (ValueError, TypeError):
            continue
            
        if cur_mrp <= 0 and (cases > 0 or bottles > 0):
            p_name = normalize_brand_key(r.get("Product Name"))
            size = normalize_size(r.get("Size"))
            
            rate = sku_rates.get(f"{p_name}_{size}") or sku_rates.get(p_name)
            if not rate:
                # Token similarity matching across known sku rates
                p_tokens = set(re.findall(r'[A-Z0-9]+', p_name))
                best_match = None
                best_sim = 0.0
                for known_k, known_rate in sku_rates.items():
                    k_name = known_k.rsplit("_", 1)[0] if "_" in known_k else known_k
                    k_tokens = set(re.findall(r'[A-Z0-9]+', k_name))
                    if p_tokens and k_tokens:
                        sim = len(p_tokens & k_tokens) / max(len(p_tokens), len(k_tokens))
                        if sim > 0.5 and sim > best_sim:
                            best_sim = sim
                            best_match = known_rate
                if best_match:
                    rate = best_match
                    
            if rate:
                bpc = get_bpc_fallback(r.get("Pack Size"), r.get("Size"), r.get("Category"))
                loose_eq = (bottles / bpc) if (bpc and bpc > 0) else 0.0
                r["Total MRP"] = round((cases + loose_eq) * rate, 2)
                
    return records

def clean_permit_records(records: List[Dict[str, Any]], config_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Cleans up permit records:
    1. Removes corrupted lines (Product Name starting with PER/IND, Cases > 2000, etc.)
    2. Deduplicates multiple lines within the same indent that represent the same SKU.
    3. Merges metadata (MRP, Licensee, Vehicle) across duplicate lines.
    """
    if not records:
        return []
        
    cleaned = []
    from collections import defaultdict
    indents_map = defaultdict(list)
    
    # Pre-identify all indents that have at least one COMPLETED line or Transit Pass
    completed_iids = {
        get_unique_indent_id(r) for r in records
        if normalize_key(r.get("Status")) == "COMPLETED" or (r.get("Transit Pass") and str(r.get("Transit Pass")).strip().upper().startswith("TP"))
    }
    
    for r in records:
        p_name = str(r.get("Product Name") or "").strip().upper()
        try: cases = float(r.get("Cases") or 0)
        except: cases = 0.0
        
        # Drop corrupted rows where main table columns were parsed as products
        if p_name.startswith("PER") or p_name.startswith("IND"):
            continue
        if cases > 2000:
            continue
            
        iid = get_unique_indent_id(r)
        status = normalize_key(r.get("Status"))
        
        # If this indent has already been completed, drop any lingering PENDING lines
        if status != "COMPLETED" and iid in completed_iids:
            continue
            
        indents_map[(iid, status)].append(r)
        
    for (iid, status), items in indents_map.items():
        if status != "COMPLETED":
            # If there are items with positive cases or product name, drop empty 0-case placeholders
            valid_items = [it for it in items if float(it.get("Cases") or 0) > 0 or float(it.get("Bottles") or 0) > 0 or it.get("Product Name")]
            items_to_use = valid_items if valid_items else items
            
            # For pending, deduplicate by unique key
            seen_keys = set()
            for it in items_to_use:
                k = get_unique_permit_key(it)
                if k not in seen_keys:
                    seen_keys.add(k)
                    cleaned.append(it)
            continue
            
        # For completed items, deduplicate by (normalized_brand, normalized_size)
        sku_groups = defaultdict(list)
        for it in items:
            b_key = normalize_brand_key(it.get("Product Name"))
            s_key = normalize_size(it.get("Size"))
            sku_groups[(b_key, s_key)].append(it)
            
        for (b_key, s_key), group in sku_groups.items():
            if len(group) == 1:
                cleaned.append(group[0])
            else:
                # Merge duplicate lines: pick the one with the most complete data
                best = dict(group[0])
                for other in group[1:]:
                    for fld in ["Total MRP", "Bulk Litres", "LPL", "Vehicle Number", "Challan Date", "Licensee Name", "Pack Size", "Category"]:
                        if not best.get(fld) and other.get(fld):
                            best[fld] = other[fld]
                        elif fld == "Total MRP" and (other.get(fld) or 0) > (best.get(fld) or 0):
                            best[fld] = other[fld]
                    best["Cases"] = max(best.get("Cases", 0), other.get("Cases", 0))
                    best["Bottles"] = max(best.get("Bottles", 0), other.get("Bottles", 0))
                cleaned.append(best)
                
    if config_dir:
        sku_rates = build_historical_sku_rates(config_dir)
        cleaned = backfill_missing_mrps(cleaned, sku_rates)
        
    return cleaned

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
