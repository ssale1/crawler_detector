# filename: crawler_detector.py
import csv
import os
import time
import re
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
import pandas as pd
from rapidfuzz import fuzz  # fuzzy matching (optional)

# selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

import urllib.robotparser as robotparser

USER_AGENT = "IllegalPostDetectorBot/1.0 (+https://example.com/contact) (Respect robots.txt)"
HEADERS = {"User-Agent": USER_AGENT}
OUTPUT_XLSX = "results.xlsx"
SCREENSHOT_DIR = "screenshots"
MAX_WORKERS = 4
REQUEST_TIMEOUT = 15
RATE_LIMIT_SECONDS = 1.0  # per-request delay per-domain (simple)
KEYWORDS = [
    "불법유통", "해킹 DB", "계정판매", "계정 매매",
    "개인정보", "유출", "DB", "해킹", "010인증"
]
FUZZY_THRESHOLD = 80  # rapidfuzz 비율 임계값

os.makedirs(SCREENSHOT_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# UTIL: robots 체크
def allowed_by_robots(url, user_agent=USER_AGENT):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception as e:
        logging.warning(f"robots.txt check failed for {robots_url}: {e}")
        return True  

# UTIL: 키워드 매칭
def find_keywords_in_text(text, keywords=KEYWORDS):
    found = set()
    if not text:
        return list(found)

    text_lower = text.lower()

    # exact match
    for kw in keywords:
        if kw.lower() in text_lower:
            found.add(kw)

    # fuzzy match
    for kw in keywords:
        score = fuzz.partial_ratio(kw.lower(), text_lower)
        if score >= FUZZY_THRESHOLD:
            found.add(kw)

    return list(found)


# FETCH: 정적 페이지
def fetch_static(url, session):
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        return resp.status_code, resp.text
    except Exception as e:
        logging.error(f"requests fetch failed: {url} -> {e}")
        return None, None


# FETCH: 동적 페이지 (selenium)
def create_headless_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(f"user-agent={USER_AGENT}")
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
    return driver


def fetch_dynamic(url, driver, wait_seconds=2):
    try:
        driver.get(url)
        time.sleep(wait_seconds)
        html = driver.page_source
        return 200, html
    except Exception as e:
        logging.error(f"Selenium fetch failed for {url} -> {e}")
        return None, None


def save_screenshot(driver, out_path):
    try:
        driver.save_screenshot(out_path)
        return out_path
    except Exception as e:
        logging.warning(f"save_screenshot failed: {e}")
        return None


# PARSE: 게시글 링크 추출 (danceforum 패턴 강화)
def extract_post_links_from_listing(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = (a.get_text() or "").strip()
        if not href:
            continue

        full = urljoin(base_url, href)

        if (
            re.search(r"(view|read|post|board|bbs|article|entry|/s\?q=)", href, re.I)
            or "/article/" in href
            or "/product/" in href
            or re.search(r"/\d+/?$", href) 
            or re.search(r"/page/\d+", href)
        ):
            links.append((full, text))
            continue

        
        if 5 < len(text) < 200:
            links.append((full, text))

    seen = set()
    out = []
    for u, t in links:
        if u not in seen:
            out.append((u, t))
            seen.add(u)

    return out


# 페이지 검사: 본문 추출 및 키워드 확인
def analyze_post(url, session, use_selenium=False, driver=None):
    if not allowed_by_robots(url):
        logging.info(f"Blocked by robots.txt: {url}")
        return {"url": url, "allowed_by_robots": False}

    if use_selenium and driver:
        status, html = fetch_dynamic(url, driver)
    else:
        status, html = fetch_static(url, session)

    if html is None:
        return {"url": url, "http_status": status, "content": None}

    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")[:200]

    # 본문 추출
    body_text = ""
    selectors = ["article", ".post-content", ".content", "#content", ".main-content", ".board-view"]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            body_text = el.get_text(separator=" ", strip=True)
            break

    if not body_text:
        body_text = soup.get_text(separator=" ", strip=True)

    matches = find_keywords_in_text(body_text)

    # snippet
    snippet = ""
    if matches:
        for m in matches:
            idx = body_text.lower().find(m.lower())
            if idx >= 0:
                start = max(0, idx - 80)
                end = min(len(body_text), idx + 80)
                snippet = body_text[start:end]
                break

    return {
        "url": url,
        "http_status": status,
        "title": title,
        "content_snippet": snippet,
        "matched_keywords": matches,
        "full_text_sample": body_text[:300]
    }


# 사이트 한 개 처리
def process_site(site_info, session, driver=None):
    base = site_info.get("base_url")
    listings = site_info.get("listing_paths", ["/"])
    site_results = []

    for path in listings:
        list_url = urljoin(base, path)
        logging.info(f"Fetching listing: {list_url}")

        if not allowed_by_robots(list_url):
            logging.info(f"robots blocked listing: {list_url}")
            continue

        use_selenium = site_info.get("use_selenium", False)
        if use_selenium and driver:
            status, html = fetch_dynamic(list_url, driver)
        else:
            status, html = fetch_static(list_url, session)

        if html is None:
            continue

        post_links = extract_post_links_from_listing(html, base)
        logging.info(f"Found {len(post_links)} candidate links on {list_url}")

        for post_url, post_text in post_links:
            time.sleep(RATE_LIMIT_SECONDS)

            analysis = analyze_post(post_url, session, use_selenium=use_selenium, driver=driver)

            if analysis.get("matched_keywords"):
                screenshot_path = None
                if use_selenium and driver:
                    fname = os.path.join(SCREENSHOT_DIR, f"{int(time.time())}_{os.path.basename(urlparse(post_url).path) or 'post'}.png")
                    try:
                        driver.get(post_url)
                        time.sleep(1)
                        driver.save_screenshot(fname)
                        screenshot_path = fname
                    except Exception as e:
                        logging.warning(f"Screenshot fail: {e}")

                site_results.append({
                    "source_site": base,
                    "page_url": list_url,
                    "post_title": analysis.get("title") or post_text,
                    "post_url": post_url,
                    "matched_keywords": ",".join(analysis.get("matched_keywords", [])),
                    "snippet": analysis.get("content_snippet"),
                    "screenshot_path": screenshot_path,
                    "http_status": analysis.get("http_status"),
                    "timestamp": datetime.utcnow().isoformat()
                })

    return site_results


# READ targets.csv
def load_targets(csv_path="targets.csv"):
    targets = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            base = r.get("base_url")
            paths = r.get("listing_paths", "/")
            use_js = r.get("use_selenium", "0") in ("1", "true", "True")
            listings = [p.strip() for p in paths.split(";") if p.strip()]
            if not listings:
                listings = ["/"]
            targets.append({"base_url": base, "listing_paths": listings, "use_selenium": use_js})
    return targets


def main():
    session = requests.Session()
    targets = load_targets("targets.csv")
    all_results = []

    driver = None
    if any(t.get("use_selenium") for t in targets):
        driver = create_headless_driver()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = {exe.submit(process_site, t, session, driver): t for t in targets}
        for fut in as_completed(futures):
            site = futures[fut]
            try:
                res = fut.result()
                if res:
                    all_results.extend(res)
            except Exception as e:
                logging.exception(f"Error processing site {site}: {e}")

    if driver:
        driver.quit()

    if not all_results:
        logging.info("No matches found.")
    else:
        df = pd.DataFrame(all_results)
        df.to_excel(OUTPUT_XLSX, index=False)
        logging.info(f"Wrote {len(df)} matches to {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()
