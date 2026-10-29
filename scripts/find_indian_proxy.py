#!/usr/bin/env python3
"""
Dynamic Indian Proxy Discovery & Pre-Flight Validator
Finds and verifies working Indian SOCKS5 & HTTP proxies that can reach the Assam Excise portal.
"""

import sys
import os
import time
import ssl
import subprocess
import urllib.request
import concurrent.futures

PORTAL_URL = "https://stateexcise.assam.gov.in/index.php/site/login"

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/IN/data.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=8000&country=IN",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=8000&country=IN&ssl=all&anonymity=all",
]

# High-reliability Indian seed proxies (Oracle Cloud Mumbai / DigitalOcean BLR)
PRIORITY_SEEDS = [
    "socks5://140.238.243.61:1080",
    "socks5://144.24.111.128:1088",
    "http://139.59.0.200:3128",
    "http://150.107.253.62:1111",
    "http://103.137.85.29:83",
    "http://103.177.235.194:84",
    "http://103.41.97.225:83",
    "http://103.135.70.9:8080",
    "http://103.148.39.10:84",
    "http://203.192.217.6:8080",
]

def check_direct_connectivity():
    print("🔍 Testing direct connectivity to Assam Excise portal...")
    req = urllib.request.Request(
        PORTAL_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    ctx = ssl._create_unverified_context()
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            if resp.status == 200:
                print(f"✅ Direct connection to portal succeeded ({time.time() - t0:.2f}s)! No proxy needed.")
                return True
    except Exception as e:
        print(f"⚠️ Direct connection timed out / dropped: {e}")
    return False

def fetch_candidate_proxies():
    candidates = []
    seen = set()
    print("📥 Fetching public Indian proxy candidates...")
    ctx = ssl._create_unverified_context()

    for src in PROXY_SOURCES:
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6, context=ctx) as r:
                text = r.read().decode("utf-8", errors="ignore")
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    cleaned = line.replace("https://", "").split()[0].split(",")[0]
                    if not (cleaned.startswith("http://") or cleaned.startswith("socks4://") or cleaned.startswith("socks5://")):
                        cleaned = f"http://{cleaned}"
                    
                    if cleaned not in seen:
                        seen.add(cleaned)
                        candidates.append(cleaned)
        except Exception as e:
            print(f"   ⚠️ Source {src} fetch warning: {e}")

    print(f"📊 Collected {len(candidates)} Indian proxy candidates to test.")
    return candidates

def verify_single_proxy(proxy_url):
    """
    Verifies a proxy by fetching the Assam Excise portal login page.
    Uses curl for native support of both SOCKS5 and HTTP proxies.
    """
    t0 = time.time()
    cmd = [
        "curl", "-k", "-s", "-L",
        "--connect-timeout", "4",
        "-m", "7",
        "--proxy", proxy_url,
        PORTAL_URL
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        elapsed = time.time() - t0
        body = res.stdout.lower()
        if "assam" in body or "excise" in body or "logincaptcha" in body or "loginform" in body:
            return (proxy_url, elapsed)
    except Exception:
        pass

    # Fallback to urllib if proxy is HTTP and curl failed
    if proxy_url.startswith("http://"):
        try:
            handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            ctx = ssl._create_unverified_context()
            opener = urllib.request.build_opener(handler)
            req = urllib.request.Request(
                PORTAL_URL,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            t0 = time.time()
            with opener.open(req, timeout=6) as resp:
                elapsed = time.time() - t0
                if resp.status == 200:
                    body = resp.read(1024).decode("utf-8", errors="ignore").lower()
                    if "assam" in body or "excise" in body or "login" in body:
                        return (proxy_url, elapsed)
        except Exception:
            pass

    return None

def find_working_indian_proxy(max_candidates=120, max_workers=35):
    candidates = fetch_candidate_proxies()
    
    # Prioritize seeds
    ordered_candidates = [p for p in PRIORITY_SEEDS if p in candidates] + [p for p in PRIORITY_SEEDS if p not in candidates]
    ordered_candidates += [p for p in candidates if p not in PRIORITY_SEEDS]

    test_batch = ordered_candidates[:max_candidates]
    print(f"⚡ Concurrently testing {len(test_batch)} Indian proxies against portal (timeout=7s)...")
    
    verified = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(verify_single_proxy, p): p for p in test_batch}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                proxy_url, latency = res
                print(f"   🎯 Live Indian Proxy verified: {proxy_url} (latency: {latency:.2f}s)")
                verified.append(res)
                if len(verified) >= 3:
                    break

    if verified:
        verified.sort(key=lambda x: x[1])
        best_proxy, best_time = verified[0]
        print(f"🏆 Best Indian proxy selected: {best_proxy} (latency: {best_time:.2f}s)")
        return best_proxy

    print("⚠️ No verified live proxies found in this batch.")
    return None

def main():
    github_env = os.environ.get("GITHUB_ENV")

    # 1. Test direct connectivity first (if unblocked, use direct for max performance)
    if check_direct_connectivity():
        if github_env:
            with open(github_env, "a") as f:
                f.write("USE_INDIAN_PROXY=false\n")
                f.write("USE_TOR_PROXY=false\n")
        print("ℹ️ Configured workflow for direct connection.")
        return 0

    # 2. Find verified live Indian proxy
    proxy = find_working_indian_proxy()
    if proxy:
        if github_env:
            with open(github_env, "a") as f:
                f.write(f"INDIAN_PROXY={proxy}\n")
                f.write("USE_INDIAN_PROXY=true\n")
                f.write("USE_TOR_PROXY=false\n")
        print(f"✅ Successfully exported Indian proxy: {proxy}")
        return 0
    else:
        print("❌ Failed to find a live Indian proxy. Workflow will fail cleanly.")
        if github_env:
            with open(github_env, "a") as f:
                f.write("USE_INDIAN_PROXY=false\n")
                f.write("USE_TOR_PROXY=false\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
