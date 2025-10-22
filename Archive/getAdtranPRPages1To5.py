import re
import time
import uuid
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode
from datetime import datetime
import os

BASE = "https://www.adtran.com"
LIST_URL = f"{BASE}/en/newsroom/press-releases"
COMPANY = "Adtran"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
)
DATE_RE = re.compile(rf"({'|'.join(MONTHS)})\s+\d{{1,2}},\s+\d{{4}}", re.I)


# -------------------------------------------------------------
# Utility
# -------------------------------------------------------------
def normalize_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str.strip()


def title_from_url(url: str) -> str:
    """Derive a readable title from the press release URL."""
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"^\d{8}-", "", slug)  # remove leading date if present
    title = slug.replace("-", " ").strip().capitalize()
    return title


# -------------------------------------------------------------
# Pagination scraping logic
# -------------------------------------------------------------
def get_page_path_id():
    """Fetch the first page and extract the pagePathId value used for pagination."""
    r = requests.get(LIST_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    # Look for 'pagePathId=' in pagination links
    link = soup.find("a", href=re.compile("pagePathId="))
    if link and "pagePathId=" in link["href"]:
        match = re.search(r"pagePathId=([a-f0-9-]+)", link["href"])
        if match:
            return match.group(1)
    return None


def get_press_release_links(page_path_id: str, pages: int = 5):
    """Fetch all PR links from the first N pages."""
    all_links = []
    for page_num in range(1, pages + 1):
        params = {
            "Year": "All years",
            "pagePathId": page_path_id,
            "Page": str(page_num),
        }
        url = f"{LIST_URL}?{urlencode(params)}"
        print(f"🌐 Fetching page {page_num}: {url}")
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        anchors = soup.select("a[href*='/en/newsroom/press-releases/']")
        links = []
        for a in anchors:
            href = a.get("href")
            if href and not href.endswith(".pdf") and not href.endswith("#"):
                links.append(urljoin(BASE, href))
        print(f"  → Found {len(links)} links on page {page_num}")
        all_links.extend(links)
        time.sleep(0.5)

    # Deduplicate
    all_links = list(dict.fromkeys(all_links))
    print(f"✅ Total unique press releases collected: {len(all_links)}\n")
    return all_links


def extract_date(soup):
    t = soup.find("time")
    if t:
        txt = t.get_text(" ", strip=True)
        if DATE_RE.search(txt):
            return normalize_date(DATE_RE.search(txt).group(0))
        if t.get("datetime"):
            return normalize_date(t["datetime"])
    m = soup.find("meta", attrs={"property": "article:published_time"})
    if m and m.get("content"):
        val = m["content"]
        if DATE_RE.search(val):
            return normalize_date(DATE_RE.search(val).group(0))
    m2 = DATE_RE.search(soup.get_text(" ", strip=True))
    if m2:
        return normalize_date(m2.group(0))
    return "(No date found)"


# -------------------------------------------------------------
# Master CSV handling
# -------------------------------------------------------------
def load_master():
    if os.path.exists(MASTER_FILE):
        return pd.read_csv(MASTER_FILE)
    else:
        return pd.DataFrame(columns=["id", "company", "title", "link", "date", "fetched_at"])


def save_to_master(new_rows):
    if new_rows.empty:
        print("ℹ️ No new press releases to add.")
        return
    master = load_master()
    merged = pd.merge(
        new_rows,
        master[["company", "title"]],
        on=["company", "title"],
        how="left",
        indicator=True
    )
    only_new = merged[merged["_merge"] == "left_only"].drop(columns="_merge")
    if only_new.empty:
        print("ℹ️ No new unique entries found.")
        return
    updated = pd.concat([master, only_new], ignore_index=True)
    updated.to_csv(MASTER_FILE, index=False)
    print(f"✅ Added {len(only_new)} new press releases to {MASTER_FILE}")


# -------------------------------------------------------------
# Main
# -------------------------------------------------------------
def main():
    print(f"Fetching base page: {LIST_URL}")
    page_path_id = get_page_path_id()
    if not page_path_id:
        print("⚠️ Could not find pagePathId. Defaulting to known value (c2cacce7-1693-49a1-bd90-11ddf725f522).")
        page_path_id = "c2cacce7-1693-49a1-bd90-11ddf725f522"

    links = get_press_release_links(page_path_id, pages=5)

    rows = []
    for url in links:
        try:
            html = requests.get(url, headers=HEADERS, timeout=20).text
            page = BeautifulSoup(html, "html.parser")
            date = extract_date(page)
            title = title_from_url(url)
            rows.append({
                "id": str(uuid.uuid4()),
                "company": COMPANY,
                "title": title,
                "link": url,
                "date": date,
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            print(f"📰 {title}\n📅 {date}\n🔗 {url}\n")
            time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Error on {url}: {e}\n")

    if rows:
        df_new = pd.DataFrame(rows)
        save_to_master(df_new)
    else:
        print("No press releases fetched.")


if __name__ == "__main__":
    main()
