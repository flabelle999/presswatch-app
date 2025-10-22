import re
import json
import time
import uuid
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import os

BASE = "https://zhone.com"
LIST_URL = f"{BASE}/company/news/news-releases/"
COMPANY = "Zhone Technologies"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
)
DATE_RE = re.compile(rf"({'|'.join(MONTHS)})\s+\d{{1,2}},\s+\d{{4}}", re.I)

MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")

# -------------------------------------------------------------
# Utility functions
# -------------------------------------------------------------
def normalize_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str.strip()


def extract_date(soup: BeautifulSoup) -> str:
    t = soup.find("time")
    if t:
        if t.get("datetime"):
            return normalize_date(t["datetime"])
        txt = t.get_text(" ", strip=True)
        if DATE_RE.search(txt):
            return normalize_date(DATE_RE.search(txt).group(0))

    meta_props = [
        ("property", "article:published_time"),
        ("property", "og:published_time"),
        ("name", "pubdate"),
        ("name", "publishdate"),
        ("name", "date"),
    ]
    for attr, val in meta_props:
        m = soup.find("meta", attrs={attr: val})
        if m and m.get("content"):
            c = m["content"].strip()
            m2 = DATE_RE.search(c)
            return normalize_date(m2.group(0) if m2 else c)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                data = [data]
            for obj in data:
                for key in ("datePublished", "dateCreated", "dateModified"):
                    if isinstance(obj, dict) and key in obj:
                        val = str(obj[key])
                        m2 = DATE_RE.search(val)
                        return normalize_date(m2.group(0) if m2 else val)
        except Exception:
            pass

    containers = [
        soup.find("main"),
        soup.find("article"),
        soup.find("div", class_=re.compile(r"(content|entry|article)", re.I)),
        soup,
    ]
    seen = set()
    for c in containers:
        if not c or id(c) in seen:
            continue
        seen.add(id(c))
        text = " ".join(
            p.get_text(" ", strip=True)
            for p in c.find_all(["p", "div", "span"])[:30]
        )
        m = DATE_RE.search(text)
        if m:
            return normalize_date(m.group(0))

    return "(No date found)"


def extract_title(soup: BeautifulSoup) -> str:
    h = soup.find(["h1", "h2"])
    if h:
        return h.get_text(" ", strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return "(No title found)"


def get_press_release_links(list_url: str):
    r = requests.get(list_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    s = BeautifulSoup(r.text, "html.parser")

    anchors = s.select("div.secondary-card__large.text-white a.empty-link")
    links = []
    for a in anchors:
        href = a.get("href")
        if href:
            links.append(urljoin(BASE, href))
    return list(dict.fromkeys(links))

# -------------------------------------------------------------
# CSV management
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
# Main scraping logic
# -------------------------------------------------------------
def main():
    cutoff = datetime(2025, 1, 1)
    print(f"Fetching list: {LIST_URL}")
    links = get_press_release_links(LIST_URL)
    print(f"Found {len(links)} press release links\n")

    rows = []

    for url in links:
        try:
            html = requests.get(url, headers=HEADERS, timeout=20).text
            page = BeautifulSoup(html, "html.parser")
            title = extract_title(page)
            date_str = extract_date(page)
            date_obj = None
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                pass

            # Only include PRs after Jan 1 2025
            if date_obj and date_obj >= cutoff:
                row = {
                    "id": str(uuid.uuid4()),
                    "company": COMPANY,
                    "title": title,
                    "link": url,
                    "date": date_str,
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                rows.append(row)
                print(f"📰 {title}\n📅 {date_str}\n🔗 {url}\n")
            else:
                print(f"⏩ Skipping {title} ({date_str}) — before 2025\n")

            time.sleep(0.8)
        except Exception as e:
            print(f"⚠️ Error on {url}: {e}\n")

    if rows:
        df_new = pd.DataFrame(rows)
        save_to_master(df_new)
    else:
        print("No press releases fetched after Jan 1 2025.")

if __name__ == "__main__":
    main()
