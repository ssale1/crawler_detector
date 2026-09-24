# filename: crawler_detector.py
import csv
import os
import time
import re
import logging
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit
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
DEFAULT_MAX_PAGES = 10
KEYWORDS = [
    "네이버 해킹", "해킹 DB", "계정 판매", "계정 매매",
    "개인정보", "유출", "해킹", "010인증", "게임 해킹"
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

    # 그누보드처럼 wr_id를 사용하는 게시판에서는 메뉴/페이지 링크를 제외하고
    # 실제 게시물 링크만 남긴다.
    if any("wr_id=" in u for u, _ in links):
        links = [(u, t) for u, t in links if "wr_id=" in u]

    seen = set()
    out = []
    for u, t in links:
        if u not in seen:
            out.append((u, t))
            seen.add(u)

    return out


def build_page_url(list_url, page_number):
    """쿼리스트링의 page 값을 유지/교체해 게시판 페이지 URL을 만든다."""
    if page_number <= 1:
        return list_url

    parsed = urlsplit(list_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page_number)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


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
    max_pages = site_info.get("max_pages", DEFAULT_MAX_PAGES)
    site_results = []
    seen_post_urls = set()

    for path in listings:
        list_url = urljoin(base, path)
        use_selenium = site_info.get("use_selenium", False)

        for page_number in range(1, max_pages + 1):
            page_url = build_page_url(list_url, page_number)
            logging.info(f"Fetching listing page {page_number}/{max_pages}: {page_url}")

            if not allowed_by_robots(page_url):
                logging.info(f"robots blocked listing: {page_url}")
                break

            if use_selenium and driver:
                status, html = fetch_dynamic(page_url, driver)
            else:
                status, html = fetch_static(page_url, session)

            if html is None:
                logging.warning(f"Stopping pagination after fetch failure: {page_url}")
                break

            post_links = extract_post_links_from_listing(html, base)
            new_post_links = [item for item in post_links if item[0] not in seen_post_urls]
            logging.info(
                f"Found {len(post_links)} posts ({len(new_post_links)} new) on {page_url}"
            )

            if not new_post_links:
                logging.info(f"No new posts; stopping pagination at page {page_number}")
                break

            for post_url, post_text in new_post_links:
                seen_post_urls.add(post_url)
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
                        "page_url": page_url,
                        "page_number": page_number,
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
            try:
                max_pages = max(1, int(r.get("max_pages") or DEFAULT_MAX_PAGES))
            except ValueError:
                max_pages = DEFAULT_MAX_PAGES
            listings = [p.strip() for p in paths.split(";") if p.strip()]
            if not listings:
                listings = ["/"]
            targets.append({
                "base_url": base,
                "listing_paths": listings,
                "use_selenium": use_js,
                "max_pages": max_pages,
            })
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
        output_path = OUTPUT_XLSX
        try:
            df.to_excel(output_path, index=False)
        except PermissionError:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name, ext = os.path.splitext(OUTPUT_XLSX)
            output_path = f"{name}_{stamp}{ext}"
            df.to_excel(output_path, index=False)
            logging.warning(
                f"{OUTPUT_XLSX} is open or locked; wrote results to {output_path} instead"
            )
        logging.info(f"Wrote {len(df)} matches to {output_path}")


if __name__ == "__main__":
    main()
