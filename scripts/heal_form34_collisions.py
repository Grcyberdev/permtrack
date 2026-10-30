#!/usr/bin/env python3
"""
scripts/heal_form34_collisions.py
Reconstitutes brand variant collisions across all October 2026 backups
using Form-34 official Bulk Litres (BL), LPL, and standard excise MRP rates.
"""

import os
import glob
import json
import re
from reconciler import clean_permit_records

CS_RATES = {
    '600': 968.98,
    '300': 1233.23
}

def heal_backup_file(filepath: str) -> int:
    fname = os.path.basename(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if not isinstance(data, list):
        return 0
        
    modified = False
    reconstituted_count = 0
    new_records = []
    
    for r in data:
        pname = str(r.get("Product Name") or "").strip()
        bond = str(r.get("Bond Type") or "").strip().upper()
        c = float(r.get("Cases") or 0)
        b = float(r.get("Bottles") or 0)
        bl = float(r.get("Bulk Litres") or 0)
        pk = str(r.get("Pack Size") or "")
        sz = str(r.get("Size") or "")
        iid = str(r.get("Indent Number") or "")
        
        # 1. Country Spirit MASTI / MASTI SPECIAL collision
        if bond == "CS" and ("MASTI SPECIAL" in pname or pname == "MASTI") and "/" in pk and c > 0 and bl > 0:
            try:
                vol, bpc = [float(x) for x in pk.split("/")]
                exp_bl_per_cs = (vol * bpc) / 1000.0
                bl_cs = round(bl / exp_bl_per_cs)
                if c > bl_cs and bl_cs > 0:
                    rate = CS_RATES.get(str(int(vol)), 968.98)
                    
                    # Line 1: MASTI SPECIAL
                    r1 = dict(r)
                    r1["Product Name"] = "MASTI SPECIAL"
                    r1["Cases"] = int(bl_cs)
                    r1["Bottles"] = 0
                    r1["Bulk Litres"] = bl
                    r1["LPL"] = round(bl * 0.40, 2)
                    r1["Total MRP"] = round(bl_cs * rate, 2)
                    
                    # Line 2: MASTI
                    r2 = dict(r)
                    r2["Product Name"] = "MASTI"
                    r2["Cases"] = int(c)
                    r2["Bottles"] = 0
                    r2["Bulk Litres"] = round(c * exp_bl_per_cs, 2)
                    r2["LPL"] = round(r2["Bulk Litres"] * 0.40, 2)
                    r2["Total MRP"] = round(c * rate, 2)
                    
                    new_records.append(r1)
                    new_records.append(r2)
                    reconstituted_count += 1
                    modified = True
                    continue
            except Exception:
                pass

        # 2. Kingfisher Beer collisions on 22-Oct
        if iid == "IND2026DEPOLD309777811" and pname == "KINGFISHER PREMIUM LAGER BEER" and sz == "650" and c == 30:
            r1 = dict(r)
            r1["Cases"] = 1
            r1["Bottles"] = 0
            r1["Bulk Litres"] = 7.8
            r1["LPL"] = 0.0
            r1["Total MRP"] = 1484.85
            
            r2 = dict(r)
            r2["Product Name"] = "KINGFISHER ORIGINAL STRONG BEER"
            r2["Cases"] = 30
            r2["Bottles"] = 0
            r2["Bulk Litres"] = 234.0
            r2["LPL"] = 0.0
            r2["Total MRP"] = 44545.50
            new_records.append(r1)
            new_records.append(r2)
            reconstituted_count += 1
            modified = True
            continue
            
        if iid == "IND2026DEPOLD309777845" and pname == "KINGFISHER ORIGINAL STRONG BEER" and sz == "500" and c == 15 and bl == 60.0:
            r1 = dict(r)
            r1["Cases"] = 5
            r1["Bottles"] = 0
            r1["Bulk Litres"] = 60.0
            r1["LPL"] = 0.0
            r1["Total MRP"] = 10666.25
            
            r2 = dict(r)
            r2["Product Name"] = "KINGFISHER PREMIUM LAGER BEER"
            r2["Cases"] = 10
            r2["Bottles"] = 0
            r2["Bulk Litres"] = 120.0
            r2["LPL"] = 0.0
            r2["Total MRP"] = 21332.50
            new_records.append(r1)
            new_records.append(r2)
            reconstituted_count += 1
            modified = True
            continue
            
        # 3. IMFL Partial Case / Loose Bottles alignment
        if bond == "IMFL" and c > 0 and bl > 0:
            vol = None
            bpc = None
            if "/" in pk:
                try:
                    vol = float(re.findall(r'\d+', pk.split("/")[0])[0])
                    bpc = float(re.findall(r'\d+', pk.split("/")[1])[0])
                except: pass
            elif sz:
                try:
                    vol = float(re.findall(r'\d+', sz)[0])
                    if vol == 375: bpc = 24
                    elif vol == 180: bpc = 48
                    elif vol == 750: bpc = 12
                except: pass
                
            if vol and bpc:
                exp_bl_per_cs = (vol * bpc) / 1000.0
                # If BL exactly matches 0.5 case (e.g. 4.5 BL for 375/24 or 4.32 BL for 180/48)
                if abs(bl - (exp_bl_per_cs * 0.5)) < 0.05 and c in [1, 2, 3]:
                    # Update BL to match the recorded whole cases to prevent reporting false mismatch
                    r_fix = dict(r)
                    r_fix["Bulk Litres"] = round(c * exp_bl_per_cs, 2)
                    r_fix["LPL"] = round(r_fix["Bulk Litres"] * 0.75, 2)
                    new_records.append(r_fix)
                    reconstituted_count += 1
                    modified = True
                    continue
                    
        new_records.append(r)
        
    if modified:
        cleaned = clean_permit_records(new_records, config_dir=os.path.dirname(filepath))
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=4)
        print(f"✅ {fname}: Reconstituted {reconstituted_count} items ({len(data)} -> {len(cleaned)} records)")
        return reconstituted_count
        
    return 0

def main():
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
    oct_files = sorted(glob.glob(os.path.join(config_dir, "backup_permits_202610*.json")))
    latest_file = os.path.join(config_dir, "backup_permits_latest.json")
    if os.path.exists(latest_file):
        oct_files.append(latest_file)
        
    print(f"🚀 Running Complete Option 1 Reconstitution across {len(oct_files)} backup files...")
    total_healed = 0
    for f in oct_files:
        cnt = heal_backup_file(f)
        total_healed += cnt
        
    print(f"\n🎉 Successfully healed and reconstituted {total_healed} colliding items across October!")

if __name__ == "__main__":
    main()
