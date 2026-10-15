# getCienaPR2025.py
# Ciena blocks plain HTTP clients (403 Forbidden since ~May 2026), so this
# scraper loads the newsroom listing in headless Chromium via Playwright and
# reads the title, link and date directly from the listing (no detail-page hits).
import os
import re
import sys
import uuid
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlsplit, urlunsplit
from playwright.sync_api import sync_playwright

BASE = "https://www.ciena.com"
LIST_URL = f"{BASE}/about/newsroom/press-releases?year={{year}}"
COMPANY = "Ciena"
TITLE_SUFFIX = " - Ciena"   # matches the format of existing rows in the master CSV
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")
CUTOFF = datetime(2025, 1, 1)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def clean_url(u: str) -> str:
    """Strip query/hash to avoid duplicates."""
    p = urlsplit(u)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def years_to_scrape() -> list:
    """Current year, plus the previous year (catches late-December releases in January)."""
    now = datetime.now().year
    return [y for y in (now, now - 1) if y >= CUTOFF.year]


def fetch_listing_html(page, year: int) -> str:
    url = LIST_URL.format(year=year)
    resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    status = resp.status if resp else None
    if status != 200:
        raise RuntimeError(f"{url} returned HTTP {status}")
    page.wait_for_selector("li.pr-list__item", timeout=30000)
    return page.content()


def parse_listing(html: str, year: int) -> list:
    """Each item: <li class='pr-list__item'><a href=...> <p>DD</p><p>Mon</p> <p class='pr-link-text'>Title</p>"""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for li in soup.select("li.pr-list__item"):
        a = li.find("a", href=True)
        if not a:
            continue
        title_el = a.select_one(".pr-link-text")
        day_el = a.select_one(".cn-display-3")
        mon_el = a.select_one(".cn-subhead-3")
        if not (title_el and day_el and mon_el):
            continue
        title = " ".join(title_el.get_text(" ", strip=True).split())
        try:
            month = MONTHS[mon_el.get_text(strip=True)[:3].lower()]
            dt = datetime(year, month, int(day_el.get_text(strip=True)))
        except (KeyError, ValueError):
            print(f"⚠️ Could not parse date for: {title}")
            continue
        link = a["href"]
        link = clean_url(link if link.startswith("http") else urljoin(BASE, link))
        rows.append({"title": title, "link": link, "dt": dt})
    return rows


def load_master():
    if os.path.exists(MASTER_FILE):
        try:
            return pd.read_csv(MASTER_FILE, encoding="utf-8")
        except UnicodeDecodeError:
            # fallback if file was created or edited in Excel/Windows
            return pd.read_csv(MASTER_FILE, encoding="latin-1")
    return pd.DataFrame(columns=["id", "company", "title", "link", "date", "fetched_at"])


def norm_title(t: str) -> str:
    t = str(t or "").strip()
    if t.endswith(TITLE_SUFFIX):
        t = t[: -len(TITLE_SUFFIX)]
    return " ".join(t.split()).lower()


def save_to_master(df_new):
    master = load_master()
    if not master.empty:
        ciena = master[master["company"] == COMPANY]
        known_links = set(ciena["link"].dropna().map(clean_url))
        known_titles = set(ciena["title"].dropna().map(norm_title))
        mask = ~(df_new["link"].isin(known_links) | df_new["title"].map(norm_title).isin(known_titles))
        df_new = df_new[mask]
    if df_new.empty:
        print("ℹ️ No new Ciena press releases to add.")
        return
    updated = pd.concat([master, df_new], ignore_index=True) if not master.empty else df_new
    updated.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ Added {len(df_new)} {COMPANY} press releases to {MASTER_FILE}")


def main():
    items = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent=USER_AGENT, locale="en-US", viewport={"width": 1366, "height": 900})
        page = context.new_page()
        for year in years_to_scrape():
            print(f"Fetching list: {LIST_URL.format(year=year)}")
            try:
                found = parse_listing(fetch_listing_html(page, year), year)
            except Exception as e:
                print(f"❌ Ciena listing for {year} failed: {e}")
                continue
            print(f"  Found {len(found)} items for {year}")
            items.extend(found)
        browser.close()

    if not items:
        print("❌ No Ciena press releases retrieved — the site may be blocking the scraper.")
        sys.exit(1)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows, seen = [], set()
    for it in items:
        if it["dt"] < CUTOFF or it["link"] in seen:
            continue
        seen.add(it["link"])
        rows.append({
            "id": str(uuid.uuid4()),
            "company": COMPANY,
            "title": it["title"] + TITLE_SUFFIX,
            "link": it["link"],
            "date": it["dt"].strftime("%Y-%m-%d"),
            "fetched_at": now,
        })

    save_to_master(pd.DataFrame(rows))


if __name__ == "__main__":
    main()
