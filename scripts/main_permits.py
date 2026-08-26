import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(line_buffering=True)
    except: pass

import json
import time
import argparse
import requests
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# Add scripts directory to path to import helpers
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import automation_utils
from reconciler import reconcile_permits, get_reconciliation_summary

def parse_args():
    parser = argparse.ArgumentParser(description="Permit & Dispatch Scraper")
    parser.add_argument("--date", type=str, help="Target date in DD-MM-YYYY format (defaults to today)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Disable headless mode")
    parser.add_argument("--bond", type=str, choices=["IMFL", "CS", "BOTH"], default="BOTH", help="Which bond credentials to query")
    parser.add_argument("--lookback-days", type=int, default=7, help="Number of days to look back for pending permits (defaults to 7)")
    parser.add_argument("--allow-partial", action="store_true", default=False, help="Allow saving partial results even if extraction errors occurred")
    return parser.parse_args()

def set_date_input(driver, wait, elem_id, target_date):
    """Sets date input field directly via JS and falls back to UI datepicker if needed."""
    date_str_fmt1 = target_date.strftime("%d-%b-%Y")
    
    set_success = False
    try:
        elem = driver.find_element(By.ID, elem_id)
        driver.execute_script("arguments[0].removeAttribute('readonly')", elem)
        driver.execute_script("arguments[0].value = arguments[1];", elem, date_str_fmt1)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", elem)
        driver.execute_script("arguments[0].dispatchEvent(new Event('blur'));", elem)
        time.sleep(0.3)
        val = elem.get_attribute("value")
        if val and (date_str_fmt1 in val or target_date.strftime("%d") in val):
            set_success = True
    except Exception as e:
        print(f"   ⚠️ Direct date setting on #{elem_id} failed: {e}")
        
    if not set_success:
        try:
            elem = wait.until(EC.element_to_be_clickable((By.ID, elem_id)))
            driver.execute_script("arguments[0].click();", elem)
            time.sleep(0.5)
            select_date_ui(driver, wait, target_date)
        except Exception as e_ui:
            print(f"   ⚠️ UI datepicker selection on #{elem_id} failed: {e_ui}")

def select_date_ui(driver, wait, target_date):
    """Automates datepicker selection on calendar UI."""
    day_to_select = str(int(target_date.strftime('%d')))
    try:
        current_calendar_month_year = driver.find_element(By.CSS_SELECTOR, "div.datepicker-days .datepicker-switch").text
    except Exception as e:
        print("   ⚠️ Error reading datepicker view:", e)
        return

    target_month_year = target_date.strftime('%B %Y')
    while target_month_year != current_calendar_month_year:
        curr_dt_obj = datetime.strptime(current_calendar_month_year, '%B %Y')
        if target_date.year < curr_dt_obj.year or (target_date.year == curr_dt_obj.year and target_date.month < curr_dt_obj.month):
             driver.find_element(By.CSS_SELECTOR, "div.datepicker-days .prev").click()
        else:
             driver.find_element(By.CSS_SELECTOR, "div.datepicker-days .next").click()
        time.sleep(0.5)
        current_calendar_month_year = driver.find_element(By.CSS_SELECTOR, "div.datepicker-days .datepicker-switch").text

    day_element_xpath = f"//div[contains(@class,'datepicker-days')]//td[not(contains(@class, 'old')) and not(contains(@class, 'new')) and text()='{day_to_select}']"
    wait.until(EC.element_to_be_clickable((By.XPATH, day_element_xpath))).click()

def set_table_page_size_100(driver):
    """Selects 100 items per page from table length dropdown and verifies update."""
    try:
        try:
            driver.execute_script("""
                var s = document.querySelector('select[name*="length"], select[id*="length"]');
                if (s) {
                    s.value = '100';
                    s.dispatchEvent(new Event('change', { bubbles: true }));
                    if (window.jQuery && window.jQuery.fn.dataTable) {
                        try { jQuery('#my-table-sorter').DataTable().page.len(100).draw(); } catch(e){}
                    }
                }
            """)
            time.sleep(1.5)
        except: pass

        selectors = [
            "//select[contains(@name, 'length')]",
            "//select[contains(@id, 'length')]",
            "//div[contains(@class, 'length')]//select",
            "//select[option[@value='100']]",
            "//select[option[text()='100']]"
        ]
        select_elem = None
        for sel in selectors:
            elems = driver.find_elements(By.XPATH, sel)
            for el in elems:
                if el.is_displayed():
                    select_elem = el
                    break
            if select_elem:
                break
                
        if select_elem:
            sel_obj = Select(select_elem)
            try:
                sel_obj.select_by_value("100")
            except:
                try:
                    sel_obj.select_by_visible_text("100")
                except: pass
                
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", select_elem)
            time.sleep(2)
            print("   ✅ Set page size to 100 entries.")
            return True
        else:
            print("   ℹ️ Page length select dropdown not visible or already showing all entries.")
    except Exception as e:
        print(f"   ⚠️ Error setting page size to 100: {e}")
    return False

def select_status_dropdown(driver, wait, status_filter):
    """Selects target status ('Pass_Issued' or 'P') from status dropdown."""
    val = "Pass_Issued" if status_filter == "Pass Issued" else ("P" if status_filter == "Pending" else "all")
    print(f"   ⚙️ Selecting status filter: '{status_filter}' (value: '{val}')...")
    
    try:
        driver.execute_script(f"var s = document.getElementById('status'); if (s) {{ s.value = '{val}'; s.dispatchEvent(new Event('change')); }}")
        time.sleep(0.5)
    except: pass
    
    try:
        select_elem = driver.find_element(By.ID, "status")
        sel_obj = Select(select_elem)
        try:
            sel_obj.select_by_value(val)
        except:
            sel_obj.select_by_visible_text(status_filter)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", select_elem)
        print(f"   ✅ Selected Status: '{status_filter}'")
        return True
    except Exception as e:
        print(f"   ⚠️ Fallback status selection error: {e}")
        
    return False

def get_next_page_button(driver):
    """Finds next page button if available and active."""
    next_selectors = [
        "//li[contains(@class, 'next') and not(contains(@class, 'disabled'))]/a",
        "//a[contains(@class, 'next') and not(contains(@class, 'disabled'))]",
        "//button[contains(@class, 'next') and not(@disabled)]",
        "//*[@id='my-table-sorter_next' and not(contains(@class, 'disabled'))]/a",
        "//*[@id='my-table-sorter_next' and not(contains(@class, 'disabled'))]"
    ]
    for sel in next_selectors:
        elems = driver.find_elements(By.XPATH, sel)
        for el in elems:
            if el.is_displayed() and "disabled" not in el.get_attribute("class"):
                return el
    return None

def purge_all_modals(driver):
    """Purges all modal elements from the DOM to avoid stale modal leaks."""
    try:
        driver.execute_script("""
            if (window.$ && $.fn && $.fn.modal) {
                $('.modal').modal('hide');
            }
            document.querySelectorAll('.modal, .modal-backdrop, [class*="modal-backdrop"]').forEach(el => el.remove());
            document.body.classList.remove('modal-open');
        """)
        time.sleep(0.3)
    except: pass

def open_and_parse_strict_modal(driver, wait, indent_num, cols):
    """
    Purges old modals, clicks link_elem, waits for modal matching indent_num,
    and extracts individual brand lines AND the official bottom 'Total' row.
    Returns: (brand_lines, tot_cases, tot_bottles, success_bool)
    """
    purge_all_modals(driver)
    
    link_elem = None
    if len(cols) > 1:
        try: link_elem = cols[1].find_element(By.TAG_NAME, "a")
        except:
            try: link_elem = cols[2].find_element(By.TAG_NAME, "a")
            except:
                try: link_elem = cols[1]
                except: pass
                
    if not link_elem:
        return [], 0, 0, False
        
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_elem)
    except: pass
    
    modal_container = None
    for attempt in range(4):
        try:
            driver.execute_script("arguments[0].click();", link_elem)
            time.sleep(1.0 + (attempt * 0.5))
            
            for wait_step in range(8):
                all_modals = driver.find_elements(By.XPATH, "//div[contains(@class, 'modal') or contains(@class, 'popup')]")
                for m in reversed(all_modals):
                    try:
                        txt = m.get_attribute("innerText") or ""
                        if indent_num in txt or "Brand Code" in txt or "Retailer Name" in txt:
                            modal_container = m
                            break
                    except: pass
                if modal_container: break
                time.sleep(0.4)
                
            if modal_container: break
            purge_all_modals(driver)
            time.sleep(0.5)
        except Exception as e:
            print(f"   ⚠️ Retry {attempt+1} opening modal for {indent_num}: {e}")
            
    if not modal_container:
        print(f"   ⚠️ Warning: Could not find matching modal for indent {indent_num}")
        return [], 0, 0, False
        
    brand_lines = []
    official_cases = None
    official_bottles = None
    
    try:
        tables = modal_container.find_elements(By.XPATH, ".//table")
        if not tables:
            tables = driver.find_elements(By.XPATH, "//div[contains(@class, 'modal')]//table")
            
        if not tables:
            return brand_lines, 0, 0, True
            
        modal_table = tables[-1]
        rows = modal_table.find_elements(By.XPATH, ".//tr")
        
        col_name = 1
        col_size = 2
        col_cases = 3
        col_bottles = 4
        col_mrp = 6
        
        for r in rows[:3]:
            cells = r.find_elements(By.XPATH, ".//th | .//td")
            texts = [c.get_attribute("innerText").strip().lower() for c in cells]
            if any("brand" in t or "product" in t for t in texts):
                for idx, t in enumerate(texts):
                    if "brand" in t or "product" in t or "item" in t: col_name = idx
                    elif "size" in t or "pack" in t: col_size = idx
                    elif "cases" in t or ("case" in t and "rate" not in t): col_cases = idx
                    elif "bottles" in t or "bottle" in t: col_bottles = idx
                    elif "value" in t or "mrp" in t or "amount" in t: col_mrp = idx

        for r in rows:
            cols_r = r.find_elements(By.TAG_NAME, "td")
            if not cols_r: continue
            
            first_cell = cols_r[0].get_attribute("innerText").strip()
            row_text = " ".join([c.get_attribute("innerText").strip() for c in cols_r]).lower()
            
            # Read Total Row at bottom
            if "total" in first_cell.lower() or "total" in row_text:
                try:
                    c_str = cols_r[col_cases].get_attribute("innerText").strip().replace(',', '') if col_cases < len(cols_r) else ""
                    if c_str: official_cases = int(float(c_str))
                except: pass
                
                try:
                    b_str = cols_r[col_bottles].get_attribute("innerText").strip().replace(',', '') if col_bottles < len(cols_r) else ""
                    if b_str: official_bottles = int(float(b_str))
                except: pass
                continue
                
            if first_cell.lower() in ["brand code", "s.no", "sl.no", "#"]: continue
            
            prod_name = cols_r[col_name].get_attribute("innerText").strip() if col_name < len(cols_r) else ""
            if not prod_name or prod_name.lower() == "total": continue
            
            prod_size = cols_r[col_size].get_attribute("innerText").strip() if col_size < len(cols_r) else ""
            try: cases = int(float(cols_r[col_cases].get_attribute("innerText").strip().replace(',', '')))
            except: cases = 0
            try: bottles = int(float(cols_r[col_bottles].get_attribute("innerText").strip().replace(',', '')))
            except: bottles = 0
            try:
                mrp_str = cols_r[col_mrp].get_attribute("innerText").strip().replace(',', '') if col_mrp < len(cols_r) else ""
                total_mrp = float(mrp_str) if mrp_str else 0.0
            except: total_mrp = 0.0
            
            brand_lines.append({
                "Product Name": prod_name,
                "Size": prod_size,
                "Cases": cases,
                "Bottles": bottles,
                "Total MRP": total_mrp
            })
            
    except Exception as e:
        print(f"   ⚠️ Error parsing table for {indent_num}: {e}")
        
    calc_cases = sum(b["Cases"] for b in brand_lines)
    calc_bottles = sum(b["Bottles"] for b in brand_lines)
    
    tot_c = official_cases if official_cases is not None else calc_cases
    tot_b = official_bottles if official_bottles is not None else calc_bottles
    
    return brand_lines, tot_c, tot_b, True

def open_and_parse_form34(driver, wait, indent_num, cols):
    """
    Opens Form-34 from the 'Form 34' column (printer icon), switches to the Form-34 tab,
    extracts official Vehicle Number, Challan Date, Licensee Name, Category, exact Pack Size,
    Cases, Bottles, BL (Bulk Litres), and LPL, then closes the tab and returns to main window.
    Returns: (brand_lines, tot_cases, tot_bottles, vehicle_no, challan_date, licensee_name, success_bool)
    """
    form34_btn = None
    
    # Try finding Form 34 button in column 8 (or any column with print icon / form34 link)
    if len(cols) > 8:
        try:
            btns = cols[8].find_elements(By.XPATH, ".//a | .//button | .//i | .//span")
            if btns: form34_btn = btns[0]
        except: pass
        
    if not form34_btn:
        for idx in [8, 7, 9, 6]:
            if idx < len(cols):
                try:
                    btns = cols[idx].find_elements(By.XPATH, ".//a[contains(@href, 'form34') or contains(@onclick, 'form34')] | .//button | .//i[contains(@class, 'print')]")
                    if btns:
                        form34_btn = btns[0]
                        break
                except: pass

    if not form34_btn:
        return [], 0, 0, "", "", "", False

    main_window = driver.current_window_handle
    handles_before = driver.window_handles
    
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", form34_btn)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", form34_btn)
        time.sleep(1.5)
        
        handles_after = driver.window_handles
        form34_window = None
        for h in handles_after:
            if h not in handles_before:
                form34_window = h
                break
                
        if not form34_window and len(handles_after) > 1:
            form34_window = handles_after[-1]
            
        if form34_window and form34_window != main_window:
            driver.switch_to.window(form34_window)
            time.sleep(1.0)
        else:
            # Maybe opened in same tab or modal
            time.sleep(1.0)
            
        page_text = ""
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
        except: pass
        
        import re
        # 1. Extract Vehicle Number
        vehicle_no = ""
        m_veh = re.search(r'through\s+Vehicle\s+No\.?\s*([A-Za-z0-9]+)', page_text, re.IGNORECASE)
        if m_veh:
            vehicle_no = m_veh.group(1).strip()
        else:
            m_veh2 = re.search(r'Vehicle\s+No\.?\s*([A-Za-z0-9]+)', page_text, re.IGNORECASE)
            if m_veh2: vehicle_no = m_veh2.group(1).strip()
            
        # 2. Extract Challan Issue Date
        challan_date = ""
        m_ch = re.search(r'Vide\s+Challan\s+No\s*\d+\s*Dated\s*:\s*([0-9A-Za-z\-]+)', page_text, re.IGNORECASE)
        if m_ch:
            challan_date = m_ch.group(1).strip()
            
        # 3. Extract Licensee Name
        licensee_name = ""
        m_lic = re.search(r'Licensee\s*:\s*([^,\n\r]+)', page_text, re.IGNORECASE)
        if m_lic:
            licensee_name = m_lic.group(1).strip()
            
        # 4. Extract Brand Table Lines
        brand_lines = []
        official_cases = None
        official_bottles = None
        
        tables = driver.find_elements(By.XPATH, "//table")
        form_table = None
        for t in tables:
            t_text = t.text.lower()
            if "brand name" in t_text or ("cases" in t_text and "bottles" in t_text) or ("cases" in t_text and "size" in t_text):
                form_table = t
                break
        if not form_table and tables:
            form_table = tables[0]
            
        if form_table:
            rows = form_table.find_elements(By.XPATH, ".//tr")
            
            col_brand_no = 1
            col_brand_name = 2
            col_category = 3
            col_size = 4
            col_cases = 5
            col_bottles = 6
            col_bl = 7
            col_lpl = 8
            
            for r in rows[:3]:
                cells = r.find_elements(By.XPATH, ".//th | .//td")
                texts = [c.get_attribute("innerText").strip().lower() for c in cells]
                if any("brand" in t for t in texts):
                    for idx, t in enumerate(texts):
                        if "number" in t or ("no" in t and "s.no" not in t and "sl" not in t): col_brand_no = idx
                        elif "brand name" in t or "item" in t: col_brand_name = idx
                        elif "category" in t: col_category = idx
                        elif "size" in t or "pack" in t: col_size = idx
                        elif "cases" in t or "case" in t: col_cases = idx
                        elif "bottles" in t or "bottle" in t: col_bottles = idx
                        elif "bl" in t or "bulk" in t: col_bl = idx
                        elif "lpl" in t: col_lpl = idx

            for r in rows:
                cols_r = r.find_elements(By.TAG_NAME, "td")
                if not cols_r: continue
                first_cell = cols_r[0].get_attribute("innerText").strip()
                row_text = " ".join([c.get_attribute("innerText").strip() for c in cols_r]).lower()
                
                # Check Total Row
                if "total" in first_cell.lower() or "total" in row_text:
                    # In Form-34 total row: [0]=TOTAL, [1]=Cases, [2]=Bottles, [3]=BL, [4]=LPL
                    for c_idx, cell in enumerate(cols_r):
                        c_text = cell.get_attribute("innerText").strip().replace(',', '')
                        if c_idx == 1 and c_text.replace('.', '').isdigit():
                            try: official_cases = int(float(c_text))
                            except: pass
                        elif c_idx == 2 and c_text.replace('.', '').isdigit():
                            try: official_bottles = int(float(c_text))
                            except: pass
                    continue
                    
                if first_cell.lower() in ["s.no", "sl.no", "#", "brand number"]: continue
                
                # S.No should normally be a number or valid row
                prod_name = cols_r[col_brand_name].get_attribute("innerText").strip() if col_brand_name < len(cols_r) else ""
                if not prod_name or prod_name.lower() == "total": continue
                if "signature" in prod_name.lower() or "officer" in prod_name.lower() or "transport pass" in prod_name.lower():
                    continue
                
                category = cols_r[col_category].get_attribute("innerText").strip() if col_category < len(cols_r) else ""
                raw_size = cols_r[col_size].get_attribute("innerText").strip() if col_size < len(cols_r) else ""
                
                # raw_size e.g. "180/48" -> size is 180 ML
                size_ml = raw_size.split("/")[0].strip() if "/" in raw_size else raw_size
                
                try: cases = int(float(cols_r[col_cases].get_attribute("innerText").strip().replace(',', '')))
                except: cases = 0
                try: bottles = int(float(cols_r[col_bottles].get_attribute("innerText").strip().replace(',', '')))
                except: bottles = 0
                try: bl = float(cols_r[col_bl].get_attribute("innerText").strip().replace(',', '')) if col_bl < len(cols_r) else 0.0
                except: bl = 0.0
                try: lpl = float(cols_r[col_lpl].get_attribute("innerText").strip().replace(',', '')) if col_lpl < len(cols_r) else 0.0
                except: lpl = 0.0
                
                brand_lines.append({
                    "Product Name": prod_name,
                    "Category": category,
                    "Size": size_ml,
                    "Pack Size": raw_size,
                    "Cases": cases,
                    "Bottles": bottles,
                    "Bulk Litres": bl,
                    "LPL": lpl,
                    "Total MRP": 0.0
                })
                
        calc_cases = sum(b["Cases"] for b in brand_lines)
        calc_bottles = sum(b["Bottles"] for b in brand_lines)
        tot_c = official_cases if official_cases is not None else calc_cases
        tot_b = official_bottles if official_bottles is not None else calc_bottles
        
        # Close Form-34 window if it was opened in a new tab
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(main_window)
            
        # Guard: If 0 items were parsed from Form-34, signal fallback to modal
        if len(brand_lines) == 0:
            print(f"   ⚠️ Form-34 parsed 0 items for {indent_num}, falling back to modal...")
            return [], 0, 0, vehicle_no, challan_date, licensee_name, False
            
        return brand_lines, tot_c, tot_b, vehicle_no, challan_date, licensee_name, True
        
    except Exception as e_f34:
        print(f"   ⚠️ Error parsing Form-34 for {indent_num}: {e_f34}")
        try:
            if len(driver.window_handles) > 1 and driver.current_window_handle != main_window:
                driver.close()
                driver.switch_to.window(main_window)
        except: pass
        return [], 0, 0, "", "", "", False

def close_modal(driver):
    """Closes details modal popup safely."""
    purge_all_modals(driver)
    return True

def scrape_permits_from_stock_dispatch(driver, wait, target_date, bond_type, status_filter="Pending", lookback_days=7):
    """
    Scrapes permits from Stock Dispatch (Retailer Indent) page.
    For completed dispatches, extracts from Form-34 (with vehicle, challan date, licensee, BL/LPL).
    Includes DataTables total entry validation, retry queue for dropped items,
    and explicit extraction error tracking.
    Returns: (results, success_bool, extraction_errors_count)
    """
    if status_filter == "Pending" and lookback_days > 0:
        start_date = target_date - timedelta(days=lookback_days)
        end_date = target_date
        status_label = f"Pending Permits (Lookback {lookback_days}d: {start_date.strftime('%d-%b-%Y')} to {end_date.strftime('%d-%b-%Y')})"
    else:
        start_date = target_date
        end_date = target_date
        status_label = "Pending Permits" if status_filter == "Pending" else "Dispatched Permits (Pass Issued)"

    print(f"\n🔎 [{bond_type}] Scraping {status_label}...")
    results = []
    extraction_errors_count = 0
    scrape_success = True
    
    portal_url = driver.current_url
    dispatch_url = portal_url.split("/index.php")[0] + "/index.php/Retailer/Retailer/Indentlist?param=stockdispatch"
    automation_utils.navigate_to_url_with_retry(driver, dispatch_url)
    time.sleep(3)
    
    try:
        set_date_input(driver, wait, "datepicker", start_date)
        set_date_input(driver, wait, "datepicker1", end_date)
        
        select_status_dropdown(driver, wait, status_filter)
        
        search_btn = driver.find_element(By.XPATH, "//button[contains(., 'Search')] | //input[contains(@value, 'Search')] | //a[contains(., 'Search')] | //input[@type='submit']")
        driver.execute_script("arguments[0].click();", search_btn)
        time.sleep(4)
        
        set_table_page_size_100(driver)
        
        # Check DataTables Info text to know expected total records
        expected_total_entries = None
        try:
            info_elems = driver.find_elements(By.CSS_SELECTOR, "#my-table-sorter_info, .dataTables_info, div[id*='info']")
            for el in info_elems:
                txt = el.text.strip()
                import re
                m = re.search(r'of\s+([0-9,]+)\s+entries', txt, re.IGNORECASE)
                if m:
                    expected_total_entries = int(m.group(1).replace(',', ''))
                    print(f"   ℹ️ Portal reports total entries: {expected_total_entries}")
                    break
        except Exception as e_info:
            print(f"   ⚠️ Could not read DataTables info text: {e_info}")
            
        page_num = 1
        while True:
            table_body = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#my-table-sorter tbody, table.dataTable tbody, table tbody")))
            rows = table_body.find_elements(By.TAG_NAME, "tr")
            
            if not rows or "No results" in rows[0].text or rows[0].text.strip() == "":
                print(f"   ℹ️ No {status_filter.lower()} permits found on page {page_num}.")
                break
                
            num_rows = len(rows)
            print(f"   📊 Processing page {page_num}: {num_rows} rows found.")
            
            failed_modal_rows = []
            
            # Pass 1: Parse table rows on current page
            for i in range(num_rows):
                try:
                    purge_all_modals(driver)
                    
                    table_body = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#my-table-sorter tbody, table.dataTable tbody, table tbody")))
                    current_rows = table_body.find_elements(By.TAG_NAME, "tr")
                    if i >= len(current_rows):
                        break
                    row = current_rows[i]
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) < 5:
                        continue
                        
                    row_data = [c.get_attribute("innerText").strip() for c in cols]
                    
                    indent_num = row_data[1] if len(row_data) > 1 else ""
                    permit_num = row_data[2] if len(row_data) > 2 else ""
                    transit_pass = row_data[3] if len(row_data) > 3 else ""
                    retailer_name = row_data[4] if len(row_data) > 4 else ""
                    retailer_code = row_data[5] if len(row_data) > 5 else ""
                    created_on = row_data[7] if len(row_data) > 7 else target_date.strftime("%d-%b-%Y")
                    
                    if not indent_num and not permit_num:
                        continue
                        
                    print(f"   🔎 [{i+1}/{num_rows}] Extracting details for Indent: {indent_num} | Permit: {permit_num}...")
                    
                    brand_lines = []
                    tot_cases = 0
                    tot_bottles = 0
                    vehicle_no = ""
                    challan_date = ""
                    licensee_name = ""
                    extract_success = False
                    
                    # For completed permits, try Form-34 first for richest data
                    if status_filter == "Pass Issued":
                        try:
                            brand_lines, tot_cases, tot_bottles, vehicle_no, challan_date, licensee_name, extract_success = open_and_parse_form34(driver, wait, indent_num, cols)
                        except Exception as e_f34:
                            print(f"   ℹ️ Form-34 fallback to modal: {e_f34}")
                            extract_success = False
                            
                    # Fallback to standard modal if Form-34 was not applicable or failed
                    if not extract_success:
                        try:
                            brand_lines, tot_cases, tot_bottles, extract_success = open_and_parse_strict_modal(driver, wait, indent_num, cols)
                            purge_all_modals(driver)
                        except Exception as e_link:
                            print(f"   ⚠️ Exception opening modal for indent {indent_num}: {e_link}")
                            purge_all_modals(driver)
                            extract_success = False
                        
                    if not extract_success:
                        print(f"   ⏳ Queued row {i+1} (Indent: {indent_num}) for retry pass...")
                        failed_modal_rows.append({
                            "index": i,
                            "indent_num": indent_num,
                            "permit_num": permit_num,
                            "transit_pass": transit_pass,
                            "retailer_name": retailer_name,
                            "retailer_code": retailer_code,
                            "created_on": created_on
                        })
                        continue
                        
                    record_status = "PENDING" if status_filter == "Pending" else "COMPLETED"
                    
                    if brand_lines:
                        for line in brand_lines:
                            results.append({
                                "Date": target_date.strftime("%d-%b-%Y"),
                                "Bond Type": bond_type,
                                "Indent Number": indent_num,
                                "Permit Number": permit_num,
                                "Transit Pass": transit_pass,
                                "Vehicle Number": vehicle_no,
                                "Challan Date": challan_date,
                                "Licensee Name": licensee_name,
                                "Retailer Name": retailer_name,
                                "Retailer Code": retailer_code,
                                "Status": record_status,
                                "Product Name": line["Product Name"],
                                "Category": line.get("Category", ""),
                                "Size": line["Size"],
                                "Pack Size": line.get("Pack Size", ""),
                                "Cases": line["Cases"],
                                "Bottles": line["Bottles"],
                                "Bulk Litres": line.get("Bulk Litres", 0.0),
                                "LPL": line.get("LPL", 0.0),
                                "Total MRP": line.get("Total MRP", 0.0),
                                "Application Date": created_on,
                                "extraction_error": False
                            })
                    else:
                        results.append({
                            "Date": target_date.strftime("%d-%b-%Y"),
                            "Bond Type": bond_type,
                            "Indent Number": indent_num,
                            "Permit Number": permit_num,
                            "Transit Pass": transit_pass,
                            "Vehicle Number": vehicle_no,
                            "Challan Date": challan_date,
                            "Licensee Name": licensee_name,
                            "Retailer Name": retailer_name,
                            "Retailer Code": retailer_code,
                            "Status": record_status,
                            "Product Name": "",
                            "Category": "",
                            "Size": "",
                            "Pack Size": "",
                            "Cases": tot_cases,
                            "Bottles": tot_bottles,
                            "Bulk Litres": 0.0,
                            "LPL": 0.0,
                            "Total MRP": 0.0,
                            "Application Date": created_on,
                            "extraction_error": False
                        })
                except Exception as e_row:
                    print(f"   ⚠️ Error parsing row {i} on page {page_num}: {e_row}")
                    
            # Pass 2: Retry queue for dropped modals
            if failed_modal_rows:
                print(f"\n   ♻️ Retrying {len(failed_modal_rows)} queued dropped modals on page {page_num}...")
                time.sleep(2)
                for item in failed_modal_rows:
                    idx = item["index"]
                    indent_num = item["indent_num"]
                    try:
                        purge_all_modals(driver)
                        table_body = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#my-table-sorter tbody, table.dataTable tbody, table tbody")))
                        current_rows = table_body.find_elements(By.TAG_NAME, "tr")
                        if idx >= len(current_rows):
                            break
                        cols = current_rows[idx].find_elements(By.TAG_NAME, "td")
                        
                        brand_lines, tot_cases, tot_bottles, modal_success = open_and_parse_strict_modal(driver, wait, indent_num, cols)
                        purge_all_modals(driver)
                        
                        record_status = "PENDING" if status_filter == "Pending" else "COMPLETED"
                        
                        if modal_success and brand_lines:
                            print(f"   ✅ Successfully recovered modal for Indent: {indent_num} ({len(brand_lines)} brand lines)")
                            for line in brand_lines:
                                results.append({
                                    "Date": target_date.strftime("%d-%b-%Y"),
                                    "Bond Type": bond_type,
                                    "Indent Number": indent_num,
                                    "Permit Number": item["permit_num"],
                                    "Transit Pass": item["transit_pass"],
                                    "Vehicle Number": "",
                                    "Challan Date": "",
                                    "Licensee Name": "",
                                    "Retailer Name": item["retailer_name"],
                                    "Retailer Code": item["retailer_code"],
                                    "Status": record_status,
                                    "Product Name": line["Product Name"],
                                    "Category": line.get("Category", ""),
                                    "Size": line["Size"],
                                    "Pack Size": line.get("Pack Size", ""),
                                    "Cases": line["Cases"],
                                    "Bottles": line["Bottles"],
                                    "Bulk Litres": line.get("Bulk Litres", 0.0),
                                    "LPL": line.get("LPL", 0.0),
                                    "Total MRP": line.get("Total MRP", 0.0),
                                    "Application Date": item["created_on"],
                                    "extraction_error": False
                                })
                        elif modal_success:
                            results.append({
                                "Date": target_date.strftime("%d-%b-%Y"),
                                "Bond Type": bond_type,
                                "Indent Number": indent_num,
                                "Permit Number": item["permit_num"],
                                "Transit Pass": item["transit_pass"],
                                "Vehicle Number": "",
                                "Challan Date": "",
                                "Licensee Name": "",
                                "Retailer Name": item["retailer_name"],
                                "Retailer Code": item["retailer_code"],
                                "Status": record_status,
                                "Product Name": "",
                                "Category": "",
                                "Size": "",
                                "Pack Size": "",
                                "Cases": tot_cases,
                                "Bottles": tot_bottles,
                                "Bulk Litres": 0.0,
                                "LPL": 0.0,
                                "Total MRP": 0.0,
                                "Application Date": item["created_on"],
                                "extraction_error": False
                            })
                        else:
                            print(f"   ❌ [EXTRACTION ERROR] Modal failed after all retries for Indent: {indent_num}")
                            extraction_errors_count += 1
                            results.append({
                                "Date": target_date.strftime("%d-%b-%Y"),
                                "Bond Type": bond_type,
                                "Indent Number": indent_num,
                                "Permit Number": item["permit_num"],
                                "Transit Pass": item["transit_pass"],
                                "Vehicle Number": "",
                                "Challan Date": "",
                                "Licensee Name": "",
                                "Retailer Name": item["retailer_name"],
                                "Retailer Code": item["retailer_code"],
                                "Status": "EXTRACTION_FAILED",
                                "Product Name": "EXTRACTION_FAILED",
                                "Category": "",
                                "Size": "",
                                "Pack Size": "",
                                "Cases": 0,
                                "Bottles": 0,
                                "Bulk Litres": 0.0,
                                "LPL": 0.0,
                                "Total MRP": 0.0,
                                "Application Date": item["created_on"],
                                "extraction_error": True
                            })
                    except Exception as e_retry:
                        print(f"   ❌ Retry failed for {indent_num}: {e_retry}")
                        extraction_errors_count += 1
                        results.append({
                            "Date": target_date.strftime("%d-%b-%Y"),
                            "Bond Type": bond_type,
                            "Indent Number": indent_num,
                            "Permit Number": item["permit_num"],
                            "Transit Pass": item["transit_pass"],
                            "Vehicle Number": "",
                            "Challan Date": "",
                            "Licensee Name": "",
                            "Retailer Name": item["retailer_name"],
                            "Retailer Code": item["retailer_code"],
                            "Status": "EXTRACTION_FAILED",
                            "Product Name": "EXTRACTION_FAILED",
                            "Category": "",
                            "Size": "",
                            "Pack Size": "",
                            "Cases": 0,
                            "Bottles": 0,
                            "Bulk Litres": 0.0,
                            "LPL": 0.0,
                            "Total MRP": 0.0,
                            "Application Date": item["created_on"],
                            "extraction_error": True
                        })
                        
            next_btn = get_next_page_button(driver)
            if next_btn:
                page_num += 1
                print(f"➡️ Navigating to page {page_num}...")
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(3)
            else:
                print(f"   ✅ Reached final page ({page_num}) for {status_label}.")
                break
                
    except Exception as e:
        print(f"   ❌ Error scraping {status_label}: {e}")
        scrape_success = False
        
    return results, scrape_success, extraction_errors_count

def run_scraper_for_credentials(username, password, target_date, bond_type, headless, lookback_days=7):
    """Runs scraper for a single credential user."""
    print(f"\n🚀 Running scraper for {bond_type} ({username})...")
    
    driver = automation_utils.setup_driver(headless=headless)
    wait = WebDriverWait(driver, 15)
    
    pending_records = []
    completed_records = []
    overall_success = True
    total_extraction_errors = 0
    
    try:
        config = automation_utils.load_config()
        portal_url = config.get("portal_url", "https://stateexcise.assam.gov.in/index.php/site/login")
        
        login_success = False
        for attempt in range(5):
            print(f"🔐 Login attempt {attempt + 1}/5...")
            driver.get(portal_url)
            time.sleep(3)
            
            try:
                temp_user = driver.find_element(By.ID, "LoginForm_username")
                if not temp_user.is_displayed():
                    login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'header-login-btn') or contains(text(), 'Login')]")))
                    driver.execute_script("arguments[0].click();", login_btn)
                    time.sleep(2)
            except: pass

            try:
                wait.until(EC.presence_of_element_located((By.ID, "LoginForm_username"))).clear()
                driver.find_element(By.ID, "LoginForm_username").send_keys(username)
                pwd_box = driver.find_element(By.ID, "LoginForm_password")
                try: driver.execute_script("arguments[0].removeAttribute('readonly')", pwd_box)
                except: pass
                pwd_box.clear()
                pwd_box.send_keys(password)
                
                code = automation_utils.solve_captcha_ocr(driver)
                if code:
                    driver.find_element(By.ID, "LoginForm_verifyCode").send_keys(code)
                    
                driver.find_element(By.XPATH, "//button[contains(text(),'Login')]").click()
                time.sleep(5)
                
                if "Login" not in driver.title and len(driver.find_elements(By.ID, "LoginForm_username")) == 0:
                    print("✅ Login successful!")
                    login_success = True
                    break
                else:
                    print("⚠️ Login failed. Retrying...")
            except Exception as e:
                print(f"⚠️ Error during login: {e}")
                
        if not login_success:
            print(f"❌ Login failed for {bond_type} ({username}) after 5 attempts.")
            return [], [], False, 0
            
        p_recs, p_ok, p_errs = scrape_permits_from_stock_dispatch(driver, wait, target_date, bond_type, status_filter="Pending", lookback_days=lookback_days)
        c_recs, c_ok, c_errs = scrape_permits_from_stock_dispatch(driver, wait, target_date, bond_type, status_filter="Pass Issued", lookback_days=0)
        
        pending_records.extend(p_recs)
        completed_records.extend(c_recs)
        total_extraction_errors += (p_errs + c_errs)
        
        if not p_ok or not c_ok:
            overall_success = False
            
    except Exception as e:
        print(f"❌ General scraper execution failure: {e}")
        overall_success = False
    finally:
        driver.quit()
        
    return pending_records, completed_records, overall_success, total_extraction_errors

def main():
    args = parse_args()
    
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%d-%m-%Y")
        except ValueError:
            print("❌ Invalid date format. Use DD-MM-YYYY. Exiting.")
            sys.exit(1)
    else:
        target_date = datetime.now()
        
    date_str = target_date.strftime("%d-%b-%Y")
    print(f"📅 Scraper target date: {date_str} (Format: DD-MMM-YYYY) | Lookback: {args.lookback_days} days")
    
    config = automation_utils.load_config()
    imfl_user = config.get("IMFL_USERNAME")
    imfl_pass = config.get("IMFL_PASSWORD")
    cs_user = config.get("CS_USERNAME")
    cs_pass = config.get("CS_PASSWORD")
    
    all_pending = []
    all_completed = []
    has_errors = False
    total_extraction_errors = 0
    
    if args.bond in ["IMFL", "BOTH"]:
        if imfl_user and imfl_pass:
            p, c, ok, errs = run_scraper_for_credentials(imfl_user, imfl_pass, target_date, "IMFL", args.headless, lookback_days=args.lookback_days)
            all_pending.extend(p)
            all_completed.extend(c)
            total_extraction_errors += errs
            if not ok or errs > 0:
                has_errors = True
        else:
            print("⚠️ Skipping IMFL: Credentials not configured.")
            
    if args.bond in ["CS", "BOTH"]:
        if cs_user and cs_pass:
            p, c, ok, errs = run_scraper_for_credentials(cs_user, cs_pass, target_date, "CS", args.headless, lookback_days=args.lookback_days)
            all_pending.extend(p)
            all_completed.extend(c)
            total_extraction_errors += errs
            if not ok or errs > 0:
                has_errors = True
        else:
            print("⚠️ Skipping Country Spirit: Credentials not configured.")
            
    print(f"\n📊 Raw Scraped Summary for {date_str}:")
    print(f"   Pending Permits (brand lines): {len(all_pending)}")
    print(f"   Completed Dispatches (brand lines): {len(all_completed)}")
    if total_extraction_errors > 0:
        print(f"   ⚠️ Modal Extraction Errors: {total_extraction_errors}")
    
    raw_combined = all_pending + all_completed
    
    backup_dir = automation_utils.get_data_dir()
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp_file = f"backup_permits_{target_date.strftime('%Y%m%d')}_000000.json"
    latest_file = "backup_permits_latest.json"
    existing_target_path = os.path.join(backup_dir, timestamp_file)
    
    # Partial run guard: Prevent destroying good backup files on fatal error
    if has_errors and not args.allow_partial:
        if os.path.exists(existing_target_path) and len(raw_combined) == 0:
            print(f"\n🚨 Critical Warning: Current scrape failed with errors and produced 0 records.")
            print(f"   Preserving existing backup file: {existing_target_path} (use --allow-partial to overwrite).")
            sys.exit(1)
    
    print(f"\n🔄 Running 7-day cross-day reconciliation engine...")
    reconciled_records = reconcile_permits(raw_combined, target_date, backup_dir, lookback_days=args.lookback_days)
    recon_summary = get_reconciliation_summary(reconciled_records)
    
    print(f"\n📈 Reconciled Status for {date_str}:")
    print(f"   • Fresh Pending: {recon_summary['fresh_pending_lines']} lines")
    print(f"   • Carried Over Pending: {recon_summary['carried_over_pending_lines']} lines (1d: {recon_summary['aging_breakdown']['1_day']}, 2d: {recon_summary['aging_breakdown']['2_days']}, 3-7d: {recon_summary['aging_breakdown']['3_to_7_days']})")
    print(f"   • Total Active Pending Indents: {recon_summary['unique_pending_indents_count']}")
    print(f"   • Completed Dispatches: {recon_summary['unique_completed_indents_count']} indents")
    if recon_summary['fulfilled_carry_overs_count'] > 0:
        print(f"   • Fulfilled Carry-Overs Today: {recon_summary['fulfilled_carry_overs_count']} lines")
        
    try:
        with open(os.path.join(backup_dir, timestamp_file), "w") as f:
            json.dump(reconciled_records, f, indent=4)
        with open(os.path.join(backup_dir, latest_file), "w") as f:
            json.dump(reconciled_records, f, indent=4)
            
        print(f"💾 Reconciled data backed up locally to {backup_dir}.")
    except Exception as e:
        print(f"⚠️ Failed to save local backup files: {e}")
        
    fly_app_url = os.environ.get("FLY_APP_URL")
    webhook_secret = os.environ.get("WEBHOOK_SECRET")
    
    if fly_app_url and webhook_secret:
        print(f"\n📡 Pushing reconciled records to Fly.io dashboard ({fly_app_url})...")
        if not fly_app_url.startswith("http"):
            fly_app_url = f"https://{fly_app_url}"
        endpoint = f"{fly_app_url.rstrip('/')}/api/upload-results"
        
        try:
            resp = requests.post(endpoint, json={
                "secret": webhook_secret,
                "date": date_str,
                "records": reconciled_records
            }, timeout=30)
            if resp.status_code == 200:
                print(f"✅ Reconciled records pushed to dashboard successfully! Server response: {resp.json()}")
            else:
                print(f"⚠️ Webhook push returned status {resp.status_code}: {resp.text}")
        except Exception as e_webhook:
            print(f"⚠️ Webhook push failed: {e_webhook}")
            
    if has_errors and not args.allow_partial:
        print(f"\n⚠️ Scraper finished with extraction errors ({total_extraction_errors} errors).")
        sys.exit(1)
    else:
        print("\n🏁 Scraper process completed successfully.")

if __name__ == "__main__":
    main()
