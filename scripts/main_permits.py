import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(line_buffering=True)
    except: pass

import json
import time
import argparse
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# Add scripts directory to path to import helpers
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import automation_utils

def parse_args():
    parser = argparse.ArgumentParser(description="Permit & Dispatch Scraper")
    parser.add_argument("--date", type=str, help="Target date in DD-MM-YYYY format (defaults to today)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Disable headless mode")
    parser.add_argument("--bond", type=str, choices=["IMFL", "CS", "BOTH"], default="BOTH", help="Which bond credentials to query")
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
    """Selects 100 items per page from table length dropdown."""
    try:
        try:
            driver.execute_script("var s = document.querySelector('select[name*=\"length\"]'); if (s) { s.value = '100'; s.dispatchEvent(new Event('change')); }")
            time.sleep(1)
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
                sel_obj.select_by_visible_text("100")
                
            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", select_elem)
            print("   ✅ Set page size to 100 entries.")
            time.sleep(2)
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
        return [], 0, 0
        
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_elem)
    except: pass
    
    modal_container = None
    for attempt in range(3):
        try:
            driver.execute_script("arguments[0].click();", link_elem)
            time.sleep(1.0)
            
            for wait_step in range(6):
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
            time.sleep(0.3)
        except Exception as e:
            print(f"   ⚠️ Retry {attempt+1} opening modal for {indent_num}: {e}")
            
    if not modal_container:
        print(f"   ⚠️ Warning: Could not find matching modal for indent {indent_num}")
        return [], 0, 0
        
    brand_lines = []
    official_cases = None
    official_bottles = None
    
    try:
        tables = modal_container.find_elements(By.XPATH, ".//table")
        if not tables:
            tables = driver.find_elements(By.XPATH, "//div[contains(@class, 'modal')]//table")
            
        if not tables:
            return brand_lines, 0, 0
            
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
            cols = r.find_elements(By.TAG_NAME, "td")
            if not cols: continue
            
            first_cell = cols[0].get_attribute("innerText").strip()
            row_text = " ".join([c.get_attribute("innerText").strip() for c in cols]).lower()
            
            # Read Total Row at bottom
            if "total" in first_cell.lower() or "total" in row_text:
                try:
                    c_str = cols[col_cases].get_attribute("innerText").strip().replace(',', '') if col_cases < len(cols) else ""
                    if c_str: official_cases = int(float(c_str))
                except: pass
                
                try:
                    b_str = cols[col_bottles].get_attribute("innerText").strip().replace(',', '') if col_bottles < len(cols) else ""
                    if b_str: official_bottles = int(float(b_str))
                except: pass
                continue
                
            if first_cell.lower() in ["brand code", "s.no", "sl.no", "#"]: continue
            
            prod_name = cols[col_name].get_attribute("innerText").strip() if col_name < len(cols) else ""
            if not prod_name or prod_name.lower() == "total": continue
            
            prod_size = cols[col_size].get_attribute("innerText").strip() if col_size < len(cols) else ""
            try: cases = int(float(cols[col_cases].get_attribute("innerText").strip().replace(',', '')))
            except: cases = 0
            try: bottles = int(float(cols[col_bottles].get_attribute("innerText").strip().replace(',', '')))
            except: bottles = 0
            try:
                mrp_str = cols[col_mrp].get_attribute("innerText").strip().replace(',', '') if col_mrp < len(cols) else ""
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
    
    return brand_lines, tot_c, tot_b

def close_modal(driver):
    """Closes details modal popup safely."""
    purge_all_modals(driver)
    return True

def scrape_permits_from_stock_dispatch(driver, wait, target_date, bond_type, status_filter="Pending"):
    """
    Scrapes permits from Stock Dispatch (Retailer Indent) page for specific target date.
    Sets start and end date to target_date, status to status_filter, selects 100 entries per page,
    and iterates across all pages.
    """
    status_label = "Pending Permits" if status_filter == "Pending" else "Dispatched Permits (Pass Issued)"
    print(f"\n🔎 [{bond_type}] Scraping {status_label} for {target_date.strftime('%d-%b-%Y')}...")
    results = []
    
    portal_url = driver.current_url
    dispatch_url = portal_url.split("/index.php")[0] + "/index.php/Retailer/Retailer/Indentlist?param=stockdispatch"
    automation_utils.navigate_to_url_with_retry(driver, dispatch_url)
    time.sleep(3)
    
    try:
        set_date_input(driver, wait, "datepicker", target_date)
        set_date_input(driver, wait, "datepicker1", target_date)
        
        select_status_dropdown(driver, wait, status_filter)
        
        search_btn = driver.find_element(By.XPATH, "//button[contains(., 'Search')] | //input[contains(@value, 'Search')] | //a[contains(., 'Search')] | //input[@type='submit']")
        driver.execute_script("arguments[0].click();", search_btn)
        time.sleep(4)
        
        set_table_page_size_100(driver)
        
        page_num = 1
        while True:
            table_body = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#my-table-sorter tbody, table.dataTable tbody, table tbody")))
            rows = table_body.find_elements(By.TAG_NAME, "tr")
            
            if not rows or "No results" in rows[0].text or rows[0].text.strip() == "":
                print(f"   ℹ️ No {status_filter.lower()} permits found on page {page_num}.")
                break
                
            num_rows = len(rows)
            print(f"   📊 Processing page {page_num}: {num_rows} rows found.")
            
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
                    
                    try:
                        brand_lines, tot_cases, tot_bottles = open_and_parse_strict_modal(driver, wait, indent_num, cols)
                        purge_all_modals(driver)
                    except Exception as e_link:
                        print(f"   ⚠️ Could not open modal for indent {indent_num}: {e_link}")
                        purge_all_modals(driver)
                        
                    record_status = "PENDING" if status_filter == "Pending" else "COMPLETED"
                    
                    if brand_lines:
                        for line in brand_lines:
                            results.append({
                                "Date": target_date.strftime("%d-%b-%Y"),
                                "Bond Type": bond_type,
                                "Indent Number": indent_num,
                                "Permit Number": permit_num,
                                "Transit Pass": transit_pass,
                                "Vehicle Number": "",
                                "Retailer Name": retailer_name,
                                "Retailer Code": retailer_code,
                                "Status": record_status,
                                "Product Name": line["Product Name"],
                                "Size": line["Size"],
                                "Cases": line["Cases"],
                                "Bottles": line["Bottles"],
                                "Total MRP": line["Total MRP"],
                                "Application Date": created_on
                            })
                    else:
                        results.append({
                            "Date": target_date.strftime("%d-%b-%Y"),
                            "Bond Type": bond_type,
                            "Indent Number": indent_num,
                            "Permit Number": permit_num,
                            "Transit Pass": transit_pass,
                            "Vehicle Number": "",
                            "Retailer Name": retailer_name,
                            "Retailer Code": retailer_code,
                            "Status": record_status,
                            "Product Name": "",
                            "Size": "",
                            "Cases": tot_cases,
                            "Bottles": tot_bottles,
                            "Total MRP": 0.0,
                            "Application Date": created_on
                        })
                except Exception as e_row:
                    print(f"   ⚠️ Error parsing row {i} on page {page_num}: {e_row}")
                    
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
        
    return results

def run_scraper_for_credentials(username, password, target_date, bond_type, headless):
    """Runs scraper for a single credential user."""
    print(f"\n🚀 Running scraper for {bond_type} ({username})...")
    
    driver = automation_utils.setup_driver(headless=headless)
    wait = WebDriverWait(driver, 15)
    
    pending_records = []
    completed_records = []
    
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
            return [], []
            
        pending_records = scrape_permits_from_stock_dispatch(driver, wait, target_date, bond_type, status_filter="Pending")
        completed_records = scrape_permits_from_stock_dispatch(driver, wait, target_date, bond_type, status_filter="Pass Issued")
        
    except Exception as e:
        print(f"❌ General scraper execution failure: {e}")
    finally:
        driver.quit()
        
    return pending_records, completed_records

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
    print(f"📅 Scraper target date: {date_str} (Format: DD-MMM-YYYY)")
    
    config = automation_utils.load_config()
    imfl_user = config.get("IMFL_USERNAME")
    imfl_pass = config.get("IMFL_PASSWORD")
    cs_user = config.get("CS_USERNAME")
    cs_pass = config.get("CS_PASSWORD")
    
    all_pending = []
    all_completed = []
    
    if args.bond in ["IMFL", "BOTH"]:
        if imfl_user and imfl_pass:
            p, c = run_scraper_for_credentials(imfl_user, imfl_pass, target_date, "IMFL", args.headless)
            all_pending.extend(p)
            all_completed.extend(c)
        else:
            print("⚠️ Skipping IMFL: Credentials not configured.")
            
    if args.bond in ["CS", "BOTH"]:
        if cs_user and cs_pass:
            p, c = run_scraper_for_credentials(cs_user, cs_pass, target_date, "CS", args.headless)
            all_pending.extend(p)
            all_completed.extend(c)
        else:
            print("⚠️ Skipping Country Spirit: Credentials not configured.")
            
    print(f"\n📊 Scraping Summary for {date_str}:")
    print(f"   Pending Permits (brand lines): {len(all_pending)}")
    print(f"   Completed Dispatches (brand lines): {len(all_completed)}")
    
    combined_records = all_pending + all_completed
    
    if not combined_records:
        print(f"ℹ️ Note: 0 permit records found on portal for target date {date_str}.")
    
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp_file = f"backup_permits_{target_date.strftime('%Y%m%d')}_000000.json"
    latest_file = "backup_permits_latest.json"
    
    try:
        with open(os.path.join(backup_dir, timestamp_file), "w") as f:
            json.dump(combined_records, f, indent=4)
        with open(os.path.join(backup_dir, latest_file), "w") as f:
            json.dump(combined_records, f, indent=4)
            
        print(f"💾 Scraped data backed up locally to config/ directory.")
    except Exception as e:
        print(f"⚠️ Failed to save local backup files: {e}")
        
    fly_app_url = os.environ.get("FLY_APP_URL")
    webhook_secret = os.environ.get("WEBHOOK_SECRET")
    
    if fly_app_url and webhook_secret:
        print(f"\n📡 Pushing scraped records to Fly.io dashboard ({fly_app_url})...")
        if not fly_app_url.startswith("http"):
            fly_app_url = f"https://{fly_app_url}"
        endpoint = f"{fly_app_url.rstrip('/')}/api/upload-results"
        
        try:
            resp = requests.post(endpoint, json={
                "secret": webhook_secret,
                "date": date_str,
                "records": combined_records
            }, timeout=30)
            if resp.status_code == 200:
                print(f"✅ Scraped records pushed to dashboard successfully! Server response: {resp.json()}")
            else:
                print(f"⚠️ Webhook push returned status {resp.status_code}: {resp.text}")
        except Exception as e_webhook:
            print(f"⚠️ Webhook push failed: {e_webhook}")
            
    print("\n🏁 Scraper process completed.")

if __name__ == "__main__":
    main()
