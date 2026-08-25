
import argparse
import sys
import os
import shutil
import glob
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import requests
import urllib.parse
import json
try:
    from PIL import Image, ImageOps, ImageFilter
    import ddddocr
except ImportError as e:
    # Fallback if dependencies aren't installed yet
    print(f"⚠️ Warning: OCR dependencies check failed: {e}")
    Image = None
    ddddocr = None

# CRITICAL: Global Timeout for Slow Server/Network
# This must affect urllib3 inside Selenium and requests
import socket
import time
socket.setdefaulttimeout(600) 



def reset_tor_identity():
    """
    Sends a signal to Tor ControlPort to request a new identity (IP rotation).
    """
    import socket
    try:
        print("🧅 Requesting new Tor identity (IP rotation)...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 9051))
        s.send(b'AUTHENTICATE ""\r\n')
        response = s.recv(1024)
        if b"250" in response:
            s.send(b'SIGNAL NEWNYM\r\n')
            response = s.recv(1024)
            if b"250" in response:
                print("✅ Tor identity reset successful.")
                time.sleep(3) # Wait for circuit to establish
                return True
        print(f"⚠️ Tor control port response: {response}")
    except Exception as e:
        print(f"⚠️ Failed to reset Tor identity: {e}")
    return False

def navigate_to_url_with_retry(driver, url, max_retries=10, wait_time=10):
    """
    Navigates to a URL with retry logic to handle transient network errors
    like ERR_CONNECTION_RESET.
    """
    from selenium.common.exceptions import WebDriverException
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"   🚀 Navigating to {url} (Attempt {attempt}/{max_retries})...")
            driver.get(url)
            
            # CRITICAL: Check if we landed on a Chrome Error Page
            # Selenium driver.get() returns successful even if it's an internal error page.
            try:
                page_src = driver.page_source
                if "Copyright 2017 The Chromium Authors" in page_src or "ERR_" in page_src or "This site can’t be reached" in page_src:
                     print(f"   ⚠️ Chrome Error Page Detected (Validation Failed).")
                     raise WebDriverException("Chrome Error Page Detected (Chromium Authors / ERR_ / Site Unreachable)")
            except Exception as valid_e:
                # If we raised above, re-raise to trigger retry
                if "Chrome Error Page" in str(valid_e): raise valid_e
                # Otherwise, maybe page_source failed? iterate code.
                pass

            return True

        except WebDriverException as e:
            error_msg = str(e).lower()
            # Added "socks_connection_failed" and "socks_server_responded" to the retry list
            if "connection_reset" in error_msg or "err_connection_closed" in error_msg or "timeout" in error_msg or "chrome error page" in error_msg or "socks_connection_failed" in error_msg or "socks_server_responded" in error_msg:
                print(f"   ⚠️ Navigation failed: {e}")
                
                # Request a new Tor IP before retrying
                if os.environ.get("USE_TOR_PROXY") == "true":
                    reset_tor_identity()
                
                if attempt < max_retries:
                    print(f"   ♻️ Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    # Refresh driver might help if stuck?
                    try: driver.refresh()
                    except: pass
                else:
                    print("   ❌ Max navigation retries reached.")
                    raise e
            else:
                # If it's a different error, raise immediately
                raise e
    return False 

# --- CONFIGURATION ---
CHROME_DRIVER_VERSION = "114.0.5735.90" # Example default

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def get_data_dir():
    """
    Resolves the persistent data storage directory.
    Priority:
    1. DATA_DIR environment variable
    2. /data directory (if exists and writable, e.g. Fly.io persistent volume)
    3. <project_root>/config (local development default)
    """
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)
        return os.path.abspath(env_dir)
    if os.path.exists("/data") and os.access("/data", os.W_OK):
        return "/data"
    
    # Fallback to local config directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_dir = os.path.join(project_root, "config")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def get_bottles_per_case(size_val):
    """
    Standard bottle-to-case pack size converter matching Assam excise rules.
    650ml / 750ml / 1000ml -> 12 b/cs
    375ml / 500ml -> 24 b/cs
    180ml / 200ml -> 48 b/cs
    <180ml (60ml / 90ml) -> 96 b/cs
    """
    if not size_val:
        return 12
    import re
    digits = re.findall(r'\d+', str(size_val))
    if not digits:
        return 12
    try:
        s = int(digits[0])
        if s >= 600:
            return 12
        if s >= 350:
            return 24
        if s >= 180:
            return 48
        if s > 0:
            return 96
    except:
        pass
    return 12

def parse_arguments():
    """
    Parses common arguments for the liquor bond automation scripts.
    """
    parser = argparse.ArgumentParser(description="Liquor Bond Automation Script")
    
    parser.add_argument("--day", type=str, help="Specific day to generate report for (e.g., '18').")
    parser.add_argument("--auto", action="store_true", help="Run in auto-mode (New Rows/Today) without asking.")
    parser.add_argument("--cleanup", action="store_true", help="Run cleanup mode without asking.")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Run browser in headless mode (default).")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Disable headless mode and show the browser (for debugging).")
    parser.add_argument("--start_date", type=str, help="Start date (DD-MM-YYYY).")
    parser.add_argument("--end_date", type=str, help="End date (DD-MM-YYYY).")
    parser.add_argument("--daily", action="store_true", help="Force report generation for the entire day (ignoring 'new rows' logic).")
    parser.add_argument("--yesterday", action="store_true", help="Generate report for the previous day.")
    parser.add_argument("--no-telegram", action="store_true", help="Disable sending Telegram reports.")
    
    return parser.parse_args()

def load_config():
    """
    Loads configuration credentials with priority:
    1. Environment Variables (GitHub Secrets / Production / .env)
    2. config/config.json (Local Development fallback)
    Ignores placeholder template values.
    """
    config = {}
    
    # 1. Try Config File first (as base)
    CONFIG_POSSIBLE = [
        os.path.join(get_data_dir(), "config.json"),
        "../config/config.json", 
        "./config/config.json", 
        "config/config.json"
    ]
    config_file_path = next((p for p in CONFIG_POSSIBLE if os.path.exists(p)), None)
    
    if config_file_path:
        try:
            with open(config_file_path, "r") as f:
                file_config = json.load(f)
            # Filter out template placeholders
            for k, v in file_config.items():
                if isinstance(v, str) and not v.startswith("YOUR_") and v.strip() != "":
                    config[k] = v
            print(f"✅ Loaded local config from: {config_file_path}")
        except Exception as e:
            print(f"⚠️ Error reading config file: {e}")

    # Special Handling for PORTAL_URL
    portal_env = os.environ.get("PORTAL_URL") or os.environ.get("portal_url")
    if portal_env:
        config["portal_url"] = portal_env
        masked_val = portal_env[:8] + "..." if portal_env else "EMPTY"
        print(f"🔐 Using Environment Variable for: portal_url (Value: {masked_val})")

    # Handle other variables (Direct mapping)
    env_vars = [
        "IMFL_USERNAME", "IMFL_PASSWORD", 
        "CS_USERNAME", "CS_PASSWORD", 
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", 
        "SCRAPER_API_KEY", "USE_TOR_PROXY"
    ]
    
    for var in env_vars:
        env_val = os.environ.get(var)
        if env_val and not env_val.startswith("YOUR_") and env_val.strip() != "":
            config[var] = env_val
            if "PASSWORD" in var or "TOKEN" in var or "KEY" in var:
                masked_val = env_val[:2] + "****" if len(env_val) > 2 else "****"
                print(f"🔐 Using Environment Variable for: {var} (Value: {masked_val})")
            else:
                print(f"🔐 Using Environment Variable for: {var} (Value: {env_val})")
        else:
            if var not in config and var not in ["USE_TOR_PROXY", "SCRAPER_API_KEY"]:
                # Suppress noisy warning for optional vars
                pass
            
    return config

def setup_driver(headless=False):
    """
    Initializes and returns a Selenium WebDriver.
    Includes Retry Logic for slow servers.
    """
    # Load config to check for Proxy
    config = load_config()
    
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    
    # DIRECT CONNECTION (No Proxies Required for GCP)
    # The Google Cloud Server IP is fully unblocked natively.
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions") # Speed up
    chrome_options.add_argument("--dns-prefetch-disable") # Speed up
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
    chrome_options.add_argument("--ignore-certificate-errors")

    # SCRAPER_API_KEY CONFIGURATION
    proxy_options = None
    wire_webdriver = None
    scraper_api_key = config.get("SCRAPER_API_KEY")
    if scraper_api_key:
        print("🕵️‍♂️ SCAPER API DETECTED: Routing traffic through ScraperAPI Proxy Tunnel.")
        try:
            from seleniumwire import webdriver as wire_webdriver
        except ImportError:
            print("⚠️ seleniumwire not installed. Falling back to standard selenium (ScraperAPI proxy disabled).")
            wire_webdriver = None
        if wire_webdriver:
            proxy_options = {
                'proxy': {
                    'http': f'http://scraperapi.country_code=in:{scraper_api_key}@proxy-server.scraperapi.com:8001',
                    'https': f'http://scraperapi.country_code=in:{scraper_api_key}@proxy-server.scraperapi.com:8001',
                    'no_proxy': 'localhost,127.0.0.1'
                }
            }

    # TOR PROXY CONFIGURATION (Fallback only if ScraperAPI is not active)
    elif config.get("USE_TOR_PROXY") == "true":
        print("🧅 TOR PROXY ENABLED: Configuring Chrome to use SOCKS5 127.0.0.1:9050")
        chrome_options.add_argument("--proxy-server=socks5://127.0.0.1:9050")
        # Ensure DNS resolution happens through the proxy to prevent leaks/failures
        # CRITICAL: Force remote DNS resolution
        chrome_options.add_argument("--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1")
        # CRITICAL: Bypass proxy for localhost to allow ChromeDriver to talk to Chrome!
        chrome_options.add_argument("--proxy-bypass-list=<-loopback>")
    
    # PAGE LOAD STRATEGY: Eager (Waits for DOM only, ignores slow images/styles)
    # This is critical for slow portals to avoid timeouts
    chrome_options.page_load_strategy = 'eager'
    
    # chrome_options.add_argument("--remote-debugging-port=9222") # REMOVED: Fixed port causes collisions on local runs
    
    # Use unique user-data-dir to prevent profile locking/crashing
    import tempfile
    user_data_dir = tempfile.mkdtemp()
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

    # Crash prevention
    chrome_options.add_argument("--no-zygote")

    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")

    # Suppress logging
    chrome_options.add_argument("--log-level=0") # Changed from 3 to 0
    
    # Try finding system chrome first (Oracle Cloud / Linux)
    # Priority: Chromium (Default on Ubuntu) -> Google Chrome
    possible_bins = ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]
    found_bin = None
    for b in possible_bins:
        if shutil.which(b): 
            found_bin = b
            break
            
    if found_bin and headless: # Only force binary on server/headless
        chrome_options.binary_location = found_bin
        print(f"🔧 Using Chrome Binary: {found_bin}")

    # Aggressive Speed & Timeout Optimizations for Low-Resource Server
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-client-side-phishing-detection")
    chrome_options.add_argument("--disable-default-apps")

    # (ScraperAPI configuration cleaned up from here to remove duplication)

    # RETRY LOGIC (For slow free-tier servers)
    import socket
    socket.setdefaulttimeout(600) # 10 Minutes Timeout for Server
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"   🚀 Launching Chrome (Attempt {attempt}/{max_retries})...")
            
            # AGGRESSIVE CLEANUP: Kill any stuck chrome processes from previous attempts
            if sys.platform == "linux":
                try:
                    import subprocess
                    subprocess.run(["pkill", "-f", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    subprocess.run(["pkill", "-f", "chromium"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except: pass

            # 0. CI/CD Environment (Github Actions) - Use WebDriverManager with native Selenium Manager fallback
            # Github Actions sets 'CI' env var. We want standard manager there.
            if os.environ.get('CI'):
                print("      🌍 CI Environment detected (Github Actions). Using WebDriverManager...")
                
                try:
                    # If proxy_options exist, wire_webdriver injects them. Otherwise it works exactly like standard selenium.
                    if proxy_options:
                         driver = wire_webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options, seleniumwire_options=proxy_options)
                    else:
                         driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
                except Exception as manager_err:
                    print(f"      ⚠️ WebDriverManager failed on CI ({manager_err}). Falling back to native Selenium Manager...")
                    if proxy_options:
                         driver = wire_webdriver.Chrome(options=chrome_options, seleniumwire_options=proxy_options)
                    else:
                         driver = webdriver.Chrome(options=chrome_options)
                
                # CRITICAL: INCREASE TIMEOUTS FOR TOR / CI
                driver.set_page_load_timeout(600)
                driver.set_script_timeout(600)
                try:
                    driver.command_executor.set_timeout(600)
                except: pass
                
                return driver

            # 1. Try System Driver (Ubuntu/Server - Best Stability)
            # We check both standard Ubuntu and GitHub Actions pre-installed paths
            possible_driver_paths = ["/usr/bin/chromedriver", "/usr/local/bin/chromedriver"]
            system_driver_path = next((p for p in possible_driver_paths if os.path.exists(p)), None)
            if sys.platform == "linux" and system_driver_path:
                try:
                    print(f"      🔧 Using Hardcoded System Driver: {system_driver_path}")
                    # CRITICAL: Snap Chromium needs no-sandbox in some envs
                    chrome_options.add_argument("--no-sandbox")
                    chrome_options.add_argument("--disable-dev-shm-usage")
                    
                    service = Service(executable_path=system_driver_path)
                    
                    # TIMEOUT FIX + ScraperAPI Logic
                    if proxy_options:
                        driver = wire_webdriver.Chrome(service=service, options=chrome_options, seleniumwire_options=proxy_options)
                    else:
                        driver = webdriver.Chrome(service=service, options=chrome_options)

                    driver.set_page_load_timeout(600) 
                    driver.set_script_timeout(600)
                    
                    # FORCE Selenium HTTP Timeout to 600s (default is 120s)
                    # This prevents 'Read timed out' during heavy commands
                    try:
                        driver.command_executor.set_timeout(600)
                    except: pass
                    
                    driver.implicitly_wait(30)
                    return driver
                except Exception as sys_err:
                     print(f"      ⚠️ System Driver failed: {sys_err}. This should not happen on Server.")
                     raise sys_err # Don't fall back, fail fast to debug

            # 2. Fallback to WebDriverManager (Mac/Local Only) with native Selenium Manager fallback
            print("      ⚠️ Linux System Driver not found/used. Using WebDriverManager (Mac/Local)...")
            try:
                if proxy_options:
                    driver = wire_webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options, seleniumwire_options=proxy_options)
                else:
                    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            except Exception as manager_err:
                print(f"      ⚠️ WebDriverManager failed ({manager_err}). Falling back to native Selenium Manager...")
                if proxy_options:
                    driver = wire_webdriver.Chrome(options=chrome_options, seleniumwire_options=proxy_options)
                else:
                    driver = webdriver.Chrome(options=chrome_options)
                
            driver.set_page_load_timeout(600)
            driver.set_script_timeout(600)
            try:
                if hasattr(driver, 'command_executor') and hasattr(driver.command_executor, '_client_config'):
                    driver.command_executor._client_config.timeout = 600
            except: pass
            return driver
            
        except Exception as e:
            print(f"      ❌ Attempt {attempt} failed: {e}")
            print("      ♻️ Retrying in 10s...")
            import time
            time.sleep(10) # Wait before retrying
            
    # If all retries fail
    print("❌ Failed to initialize Chrome Driver after multiple attempts.")
    sys.exit(1)

def solve_captcha_ocr(driver, captcha_element_id="loginCaptcha"):
    """
    Attempts to solve the captcha using OCR.
    Returns the solved text if it's strictly 5 or 6 digits.
    Returns None otherwise.
    Cleans up debug images automatically.
    """
    try:
        import ddddocr
    except ImportError:
        ddddocr = None

    if not ddddocr:
        print("⚠️ ddddocr not installed. Will fallback to manual entry.")
        has_ddddocr = False
    else:
        has_ddddocr = True

    screenshot_path = "captcha_temp.png"
    
    try:
        # Strategy: Find element -> Screenshot element -> OCR
        # Robust Wait for slow servers (required for page_load_strategy='none')
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # Updated Selector based on User Screenshot: <img id="loginCaptcha" ...>
        try:
            wait = WebDriverWait(driver, 30) # Wait up to 30s for captcha to appear
            captcha_img = wait.until(EC.presence_of_element_located((By.ID, captcha_element_id)))
        except:
            # Fallback patterns
            try:
                captcha_img = driver.find_element(By.XPATH, "//img[contains(@src, 'captcha')]")
            except:
                 print("⚠️ Could not locate Captcha Image element (id='loginCaptcha' or src='captcha') for OCR.")
                 return None

        # Save screenshot of the element
        # Custom Logic for safer screenshotting 
        # Strategy: 1. Try Element Screenshot (Best for Local/Mac) -> 2. Fallback to Full Page Crop (Best for Headless/Linux)
        
        try:
            captcha_img.screenshot(screenshot_path)
            # Verify file size/validity
            if not os.path.exists(screenshot_path) or os.path.getsize(screenshot_path) < 100:
                raise Exception("Screenshot file missing or too small")
        except Exception as e_ss:
            print(f"   ⚠️ Element screenshot failed: {e_ss}. Using Full Page Crop fallback...")
            
            full_screenshot_path = "full_page_debug.png"
            driver.save_screenshot(full_screenshot_path)
            
            image = Image.open(full_screenshot_path)
            
            # Use fixed crop if element location failed
            try:
                location = captcha_img.location
                size = captcha_img.size
                # Add padding to crop
                left = location['x'] - 5
                top = location['y'] - 5
                right = location['x'] + size['width'] + 5
                bottom = location['y'] + size['height'] + 5
                image = image.crop((left, int(top), int(right), int(bottom)))
            except:
                print("   ⚠️ Dynamic crop failed. Using fixed fallback box.")
                image = image.crop((700, 300, 900, 400)) # Guess coordinates
            image.save(screenshot_path)
            
            # Clean up full page
            try: os.remove(full_screenshot_path) 
            except: pass
        
        if not has_ddddocr:
            print(f"   🖼️  Captcha saved to: {os.path.abspath(screenshot_path)}")
            try:
                import subprocess
                subprocess.run(["open", screenshot_path])
            except: pass
            manual_code = input("   ⌨️  Please enter the CAPTCHA code shown in the image (or blank to retry): ")
            return manual_code.strip() if manual_code.strip() else None

        # Process image with ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        with open(screenshot_path, 'rb') as f:
            image_bytes = f.read()
        
        final_text = ocr.classification(image_bytes)
        
        if final_text and len(final_text) in [5, 6]:
             print(f"🤖 ddddocr Final Decision: '{final_text}'")
             return final_text
        else:
             print(f"   -> ddddocr returned invalid candidate: '{final_text}'. OCR failed safely.")
             return None

    except Exception as e:
        print(f"⚠️ OCR Failed: {e}")
        return None
    
    finally:
        # CLEANUP: Remove temp and debug images
        try:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
            for f in glob.glob("captcha_debug_*.png"):
                os.remove(f)
        except Exception as cleanup_err:
             print(f"   ⚠️ Cleanup warning: {cleanup_err}")

def manual_login_fallback(driver, username, password):
    """
    Handles login with manual fallback if OCR fails or is not used.
    """
    pass # Logic will be in the main scripts for flow control

def send_telegram_message(message, bot_token, chat_id):
    """
    Sends a message via Telegram Bot API.
    Supports single or multiple comma-separated Chat IDs.
    Automatically splits long messages that exceed Telegram's 4096 character limit.
    
    Args:
        message (str): The text message to send.
        bot_token (str): The API token for the bot (from @BotFather).
        chat_id (str): The Chat ID(s) to send the message to. Can be comma-separated.
    
    Returns:
        bool: True if successful for ALL recipients, False if ANY fail.
    """
    if not bot_token or not chat_id:
        print("⚠️ Telegram configuration missing (Bot Token or Chat ID). Skipping message send.")
        return False

    # Handle multiple Chat IDs
    chat_ids = [cid.strip() for cid in str(chat_id).split(',') if cid.strip()]
    
    # Split message into chunks (max 4000 chars to safely be under the 4096 limit)
    chunks = []
    current_chunk = ""
    for line in message.split('\n'):
        if len(current_chunk) + len(line) + 1 > 4000:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = line
            else:
                # very long single line fallback
                while len(line) > 4000:
                    chunks.append(line[:4000])
                    line = line[4000:]
                current_chunk = line
        else:
            if current_chunk:
                current_chunk += '\n' + line
            else:
                current_chunk = line
    if current_chunk:
        chunks.append(current_chunk)

    overall_success = True
    
    for cid in chat_ids:
        print(f"📱 Sending Telegram message to Chat ID {cid} (in {len(chunks)} parts)...")
        
        for idx, chunk in enumerate(chunks, 1):
            try:
                # Use POST request for better handling of long text and special characters
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": cid,
                    "text": chunk,
                    "parse_mode": "Markdown"
                }
                
                response = requests.post(url, json=payload, timeout=20)
                
                if response.status_code == 200:
                    if len(chunks) > 1:
                        print(f"✅ Telegram message (part {idx}/{len(chunks)}) sent successfully to {cid}!")
                    else:
                        print(f"✅ Telegram message sent successfully to {cid}!")
                else:
                    print(f"❌ Telegram API Failed for {cid}: Status {response.status_code}, Response: {response.text}")
                    overall_success = False
                    
                # Small delay between chunks to avoid rate limiting
                if len(chunks) > 1 and idx < len(chunks):
                    import time
                    time.sleep(1)
                    
            except Exception as e:
                print(f"❌ Error sending Telegram message to {cid}: {e}")
                overall_success = False
            
    return overall_success

def save_cookies(driver, filepath):
    """
    Saves the current session cookies to a JSON file.
    """
    try:
        cookies = driver.get_cookies()
        with open(filepath, 'w') as f:
            json.dump(cookies, f, indent=4)
        print(f"🍪 Cookies saved to {filepath}")
    except Exception as e:
        print(f"⚠️ Failed to save cookies: {e}")

def load_cookies(driver, filepath, domain):
    """
    Loads cookies from a JSON file and adds them to the driver.
    Requires the driver to be on the correct domain (page loaded) first.
    """
    if not os.path.exists(filepath):
        return False
        
    try:
        with open(filepath, 'r') as f:
            cookies = json.load(f)
            
        # Add cookies
        for cookie in cookies:
            try:
                # Selenium requires strict domain matching or no domain for localhost/IP
                # We can strip domain to be safe or trust the cookie file
                if 'expiry' in cookie:
                    del cookie['expiry'] # Avoid expiry issues? Or keep it? keeping it is better usually.
                
                # Check domain match if strictly enforced? For now, we trust.
                driver.add_cookie(cookie)
            except Exception as e:
                # Some cookies might fail (e.g. wrong domain), just skip
                pass
        
        print(f"🍪 Cookies loaded from {filepath}")
        return True
    except Exception as e:
        print(f"⚠️ Failed to load cookies: {e}")
        return False

def generate_whatsapp_reports(data_rows, incoming_checkpoint, report_header):
    """
    Generates a list of formatted WhatsApp report strings with detailed liquor bifurcation (one per truck).
    Args:
        data_rows: List of rows [Date, Supplier, Truck, LiquorTypesStr, Quantity, ...]
        incoming_checkpoint: Dict { Date: { Truck: { LiquorName: { SizeSuffix: Qty } } } }
        report_header: Full header string (e.g. "Liqour Endorsements - 18 Oct")
    Returns:
        List of strings containing the reports.
    """
    if not data_rows:
        return []

    # Mapping for display in report
    # Maps the stored suffix (from SIZE_SUFFIX_MAPPING) to User Preferred Display
    REPORT_SIZE_MAPPING = {
        "Can": "Can (AP)",
        "Bottle": "Bottle (BS)",
        "375ml": "Half (PP)",
        "750ml": "Full (QQ)",
        "180ml": "Quarter (NN)",
        "Full": "Full (JM/QM)",
        "Quarter": "Quarter (CP/CR/CQ)",
        "Pint": "Pint (UP)",
        "Stubby": "Stubby (GP)",
        "Keg": "Keg (TT)",
    }
    
    # Also handle the raw codes if they linger (just in case)
    RAW_CODE_MAPPING = {
        "AP": "Can (AP)",
        "BS": "Bottle (BS)",
        "PP": "Half (PP)",
        "QQ": "Full (QQ)",
        "NN": "Quarter (NN)",
        "JM": "Full (JM/QM)",
        "QM": "Full (JM/QM)",
        "CP": "Quarter (CP/CR/CQ)",
        "CR": "Quarter (CP/CR/CQ)",
        "CQ": "Quarter (CP/CR/CQ)",
        "UP": "Pint (UP)",
        "GP": "Stubby (GP)",
        "TT": "Keg (TT)",
    }
    
    # Helper to clean text for markdown
    def clean_md(t):
        if not t: return ""
        # Replace backticks with single quotes to prevent markdown code block errors
        # Replace &amp; with &
        return str(t).replace("`", "'").replace("&amp;", "&")

    # Helper for date normalization
    from datetime import datetime
    def norm(d):
        if not d: return ""
        try: 
            return datetime.strptime(d, '%d-%b-%Y').strftime('%Y-%m-%d')
        except: 
            try: return datetime.strptime(d, '%Y-%m-%d').strftime('%Y-%m-%d')
            except: 
                # Try simple strip
                return d.strip()

    # Helper to clean/shorten/resolve the supplier name
    def get_clean_short_supplier(supplier):
        if not supplier:
            return ""
        import re
        
        # 1. Strip parentheses/volume details
        clean_val = re.sub(r'\(.*?\)', '', supplier).strip()
        clean_val = " ".join(clean_val.split())
        
        # Brand-to-Supplier Mapping
        BRAND_TO_SUPPLIER_MAPPING = {
            "He Man 9000": "Rhino",
            "He Man 9000 Bottle": "Rhino",
            "Budweiser": "Anheuser Busch",
            "Budweiser Magnum": "Anheuser Busch",
            "Corona": "Anheuser Busch",
            "Hoegaarden": "Anheuser Busch",
            "Hoegaarden Witbier": "Anheuser Busch",
            "Tuborg": "Carlsberg",
            "Carlsberg": "Carlsberg",
            "Kingfisher": "Sunit",
            "Kingfisher Lager": "Sunit",
            "Kingfisher Original Strong": "Sunit",
            "Kingfisher Strong": "Sunit",
            "Royal Stag": "Pernod Ricard",
            "Blenders Pride": "Pernod Ricard",
            "Imperial Blue": "Pernod Ricard",
            "100 Pipers": "Pernod Ricard",
            "McDowell's": "United Spirits",
            "Celebration Rum": "United Spirits",
            "Signature": "United Spirits",
            "Royal Challenge": "United Spirits",
            "Old Monk": "Mohan Meakin",
            "Sterling Reserve": "Allied Blenders",
            # Country Spirit Brands -> Suppliers
            "Masti": "Pragati",
            "Masti Special": "Pragati",
            "Masti No. 1": "Pragati",
            "Rhino Tango": "Rhino",
            "Rhino No 1": "Rhino",
            "Rhino Whiskey": "Rhino",
        }
        
        # Check if clean_val matches a brand name to resolve to its supplier
        for brand, sup in BRAND_TO_SUPPLIER_MAPPING.items():
            if brand.lower() in clean_val.lower():
                return sup
                
        # 2. Try standard get_short_supplier_name if imported/available
        try:
            from liquor_data import get_short_supplier_name
            short_name = get_short_supplier_name(supplier)
            if short_name and short_name != supplier:
                return short_name
        except Exception:
            pass
            
        # 3. Clean up the unmapped name by stripping common suffixes (avoiding '...')
        cleaned = clean_val
        suffixes = [
            r'\bPVT\.?\s*LTD\.?\b',
            r'\bLTD\.?\b',
            r'\bPVT\.?\b',
            r'\bLLP\b',
            r'\bPRIVATE\b',
            r'\bLIMITED\b',
            r'\bINDIA\b',
            r'\bCO\.?\b',
            r'\bCOMPANY\b',
            r'\bDISTILLERY\b',
            r'\bDISTILLERIES\b',
            r'\bBREWERIES\b',
            r'\bBREWERY\b',
            r'\bMANUFACTURERS\b',
            r'\bINDUSTRIES\b',
        ]
        for pattern in suffixes:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
        
        cleaned = " ".join(cleaned.split()).rstrip(",- ").strip()
        return cleaned

    reports = []

    for idx, row in enumerate(data_rows, 1):
        # row structure: [Date, Supplier, Truck, LiquorTypes, Quantity, Status, DateArrived, DateCompleted, TelegramSupplier (Optional)]
        date_raw = row[0]
        truck_val = clean_md(row[2])
        qty_val = row[4]
        
        # Try to find detailed data in checkpoint
        detailed_data = None
        
        # 1. Direct lookup
        if date_raw in incoming_checkpoint and truck_val in incoming_checkpoint[date_raw]:
             detailed_data = incoming_checkpoint[date_raw][truck_val]
        else:
             # 2. Normalized Date Search
             target_norm = norm(date_raw)
             for cp_date in incoming_checkpoint:
                 if norm(cp_date) == target_norm:
                     if truck_val in incoming_checkpoint[cp_date]:
                         detailed_data = incoming_checkpoint[cp_date][truck_val]
                         break
                         
        # Determine Supplier Display Name
        # If the row has index 8 (from a direct scrape), use it.
        # If it doesn't (from a Cumulative Sheet Export), check the Checkpoint for "_TelegramSupplier"
        telegram_supplier = None
        if len(row) > 9:
            telegram_supplier = row[9]
        elif len(row) == 9:
            telegram_supplier = row[8]
        
        if not telegram_supplier and detailed_data and "_TelegramSupplier" in detailed_data:
            telegram_supplier = detailed_data["_TelegramSupplier"]
            
        supplier_val = clean_md(telegram_supplier if telegram_supplier else row[1])
        
        # Layout requirements for mobile:
        # Supplier name, then immediately Truck Number, Cases, slight spacing, then Details.
        
        # Clean and shorten the supplier name for the header, keep full mapped name for the body
        short_supplier = get_clean_short_supplier(supplier_val)
        
        line = f"📅 *Date:* {clean_md(date_raw)}\n"
        if supplier_val:
            line += f"🏢 *Supplier:* {supplier_val}\n"
        line += f"🚛 *Truck:* `{truck_val}`\n"
        line += f"📦 *Total Cases:* {qty_val}\n"
        
        if detailed_data:
            # User requested 1 consistent order. Alphabetical sort on liquor names prevents random jumping.
            sorted_liquors = sorted([item for item in detailed_data.items() if item[0] != '_TelegramSupplier'], key=lambda x: x[0])
            
            line += "\nDetails:\n"
            
            detail_lines = []
            for liquor_name, size_dict in sorted_liquors:
                # Sort sizes intuitively based on generic volume sizes
                size_priority = {
                    "Quarter": 1, "NN": 1, "CP": 1, "CR": 1, "CQ": 1, "180ml": 1,
                    "Half": 2, "PP": 2, "375ml": 2,
                    "Pint": 3, "UP": 3,
                    "Stubby": 4, "GP": 4,
                    "Full": 5, "QQ": 5, "JM": 5, "QM": 5, "750ml": 5,
                    "Bottle": 6, "BS": 6,
                    "Can": 7, "AP": 7,
                    "Keg": 8, "TT": 8
                }
                
                parts = []
                for suffix, q in sorted(size_dict.items(), key=lambda x: size_priority.get(x[0], 99)):
                    # Map suffix to display format
                    display_suffix = REPORT_SIZE_MAPPING.get(suffix, suffix)
                    # If suffix matches raw code, map it too
                    if suffix in RAW_CODE_MAPPING:
                        display_suffix = RAW_CODE_MAPPING[suffix]
                        
                    parts.append(f"{display_suffix}: {q}")
                
                parts_str = ", ".join(parts)
                # Bullet point brand, indent sizes below it
                detail_lines.append(f"• *{clean_md(liquor_name)}*\n  ↳ {parts_str}")
                
            line += "\n".join(detail_lines)
        else:
            # Fallback to old string if detailed data missing
            liquor_val = row[3]
            line += f"\nDetails:\n• *{liquor_val}*"
            
        # Check if we are doing a Country Spirit endorsement
        is_cs = report_header and ("Country Spirit" in report_header or "CS" in report_header)
        prefix = "CS: " if is_cs else ""

        # Gather unique brand names from detailed checkpoint data or row types
        brands_list = []
        if detailed_data:
            brands_list = sorted([k for k in detailed_data.keys() if k != '_TelegramSupplier'])
        else:
            raw_types = row[3] if len(row) > 3 else ""
            if raw_types:
                brands_list = [b.strip() for b in raw_types.split(',') if b.strip()]

        cleaned_brands = []
        for b in brands_list:
            cb = b
            for suffix in ["Bottle", "Can", "Pint", "Half", "Quarter", "Stubby", "Keg"]:
                if cb.endswith(" " + suffix):
                    cb = cb[:-len(suffix)-1].strip()
                elif cb.endswith(suffix):
                    cb = cb[:-len(suffix)].strip()
            cleaned_brands.append(cb)

        seen_b = set()
        uniq_b = []
        for cb in cleaned_brands:
            if cb not in seen_b:
                seen_b.add(cb)
                # Omit brand name if it's already redundant with supplier name or 'CS'
                if cb.lower() not in short_supplier.lower() and short_supplier.lower() not in cb.lower():
                    uniq_b.append(cb)

        # Apply a length budget for brand listing to prevent shabbiness
        brands_part = ""
        if uniq_b:
            char_budget = 35
            current_brands = []
            current_len = 0
            for brand in uniq_b:
                brand_len = len(brand)
                added_len = brand_len + (2 if current_brands else 0)
                if current_len + added_len <= char_budget:
                    current_brands.append(brand)
                    current_len += added_len
                else:
                    current_brands.append("...")
                    break
            
            if current_brands:
                if current_brands[-1] == "...":
                    brands_part = ", ".join(current_brands[:-1]) + ", ..."
                else:
                    brands_part = ", ".join(current_brands)

        # Build dynamic title info
        display_header = report_header
        if short_supplier or qty_val is not None:
            parts = []
            if short_supplier:
                parts.append(f"{prefix}{short_supplier}")
            if qty_val is not None:
                parts.append(f"({qty_val} Cases)")
            
            display_header = " ".join(parts)
            if brands_part:
                display_header += f" - {brands_part}"

        final_text = []
        if display_header:
            final_text.append(f"🥃 *{clean_md(display_header)}*")
        else:
            final_text.append("═══ ❖ ═══")
            
        final_text.append(line)
        final_text.append("═══ ❖ ═══")
        
        reports.append("\n\n".join(final_text))
        
    return reports


def get_bifurcation_string(date_raw, truck_val, incoming_checkpoint):
    """
    Returns a structured single-line string breakdown of liquor quantities from the checkpoint data.
    E.g. "Kingfisher (Can: 1400); Royal Stag (Full: 120, Half: 100)"
    """
    if not incoming_checkpoint:
        return ""

    # Mapping for display in report
    REPORT_SIZE_MAPPING = {
        "Can": "Can",
        "Bottle": "Bottle",
        "375ml": "Half",
        "750ml": "Full",
        "180ml": "Quarter",
        "Full": "Full",
        "Quarter": "Quarter",
        "Pint": "Pint",
        "Stubby": "Stubby",
        "Keg": "Keg",
    }
    RAW_CODE_MAPPING = {
        "AP": "Can",
        "BS": "Bottle",
        "PP": "Half",
        "QQ": "Full",
        "NN": "Quarter",
        "JM": "Full",
        "QM": "Full",
        "CP": "Quarter",
        "CR": "Quarter",
        "CQ": "Quarter",
        "UP": "Pint",
        "GP": "Stubby",
        "TT": "Keg",
    }

    # Helper for date normalization
    from datetime import datetime
    def norm(d):
        if not d: return ""
        try: 
            return datetime.strptime(d, '%d-%b-%Y').strftime('%Y-%m-%d')
        except: 
            try: return datetime.strptime(d, '%Y-%m-%d').strftime('%Y-%m-%d')
            except: return d.strip()

    # Try to find detailed data in checkpoint
    detailed_data = None
    if date_raw in incoming_checkpoint and truck_val in incoming_checkpoint[date_raw]:
         detailed_data = incoming_checkpoint[date_raw][truck_val]
    else:
         target_norm = norm(date_raw)
         for cp_date in incoming_checkpoint:
             if norm(cp_date) == target_norm:
                 if truck_val in incoming_checkpoint[cp_date]:
                     detailed_data = incoming_checkpoint[cp_date][truck_val]
                     break

    if not detailed_data:
        return ""

    sorted_liquors = sorted([item for item in detailed_data.items() if item[0] != '_TelegramSupplier'], key=lambda x: x[0])
    
    from liquor_data import get_short_name

    parts_list = []
    for liquor_name, size_dict in sorted_liquors:
        mapped_name = get_short_name(liquor_name)
        size_priority = {
            "Quarter": 1, "NN": 1, "CP": 1, "CR": 1, "CQ": 1, "180ml": 1,
            "Half": 2, "PP": 2, "375ml": 2,
            "Pint": 3, "UP": 3,
            "Stubby": 4, "GP": 4,
            "Full": 5, "QQ": 5, "JM": 5, "QM": 5, "750ml": 5,
            "Bottle": 6, "BS": 6,
            "Can": 7, "AP": 7,
            "Keg": 8, "TT": 8
        }
        
        size_parts = []
        for suffix, q in sorted(size_dict.items(), key=lambda x: size_priority.get(x[0], 99)):
            display_suffix = REPORT_SIZE_MAPPING.get(suffix, suffix)
            if suffix in RAW_CODE_MAPPING:
                display_suffix = RAW_CODE_MAPPING[suffix]
            size_parts.append(f"{display_suffix}: {q}")
        
        size_str = ", ".join(size_parts)
        parts_list.append(f"{mapped_name} ({size_str})")
        
    return "; ".join(parts_list)


def subtract_checkpoint_details(new_details, old_details):
    """
    Subtracts the old checkpoint details from the new checkpoint details
    to isolate only the new items and quantities for the second permit.
    """
    diff_details = {}
    if not new_details:
        return diff_details

    for liquor, sizes in new_details.items():
        if liquor == "_TelegramSupplier":
            continue
        old_sizes = old_details.get(liquor, {})
        diff_sizes = {}
        for size, qty in sizes.items():
            old_qty = old_sizes.get(size, 0)
            diff_qty = qty - old_qty
            if diff_qty > 0:
                diff_sizes[size] = diff_qty
        if diff_sizes:
            diff_details[liquor] = diff_sizes

    if "_TelegramSupplier" in new_details:
        diff_details["_TelegramSupplier"] = new_details["_TelegramSupplier"]
    elif "_TelegramSupplier" in old_details:
        diff_details["_TelegramSupplier"] = old_details["_TelegramSupplier"]

    return diff_details


def get_checkpoint_details(checkpoint, date_raw, truck_val):
    """
    Safely retrieves detailed information from the checkpoint for a given date
    and truck, checking for both direct raw-date match and normalized date match.
    """
    if not checkpoint:
        return {}
    if date_raw in checkpoint and truck_val in checkpoint[date_raw]:
        return checkpoint[date_raw][truck_val]
    
    from datetime import datetime
    def norm(d):
        if not d: return ""
        try: 
            return datetime.strptime(d, '%d-%b-%Y').strftime('%Y-%m-%d')
        except: 
            try: return datetime.strptime(d, '%Y-%m-%d').strftime('%Y-%m-%d')
            except: return d.strip()
            
    target_norm = norm(date_raw)
    for cp_date in checkpoint:
        if norm(cp_date) == target_norm:
            if truck_val in checkpoint[cp_date]:
                return checkpoint[cp_date][truck_val]
    return {}
