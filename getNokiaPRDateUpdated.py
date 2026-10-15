# getNokiaPRDateUpdated.py
# Previous version read only https://www.nokia.com/newsroom/telco-networks/, a curated
# category page that listed just a handful of releases per year, so most Nokia press
# releases never reached PressWatch.
#
# This version reads Nokia's newsroom feed (the JSON endpoint behind the "Load more"
# button on the newsroom page), which returns every release newest-first with its tags,
# publish date and URL. Only items tagged "Press releases" are kept.
# Note: Nokia's CDN (Akamai) blocks headless browsers, so plain requests is used here.
import os
import re
import sys
import json
import uuid
import html
import time
import requests
import pandas as pd
from datetime import datetime

COMPANY = "Nokia"
BASE = "https://www.nokia.com"
LIST_URL = f"{BASE}/newsroom/?h=1&t=press%20releases&match=1"
FEED_URL = f"{BASE}/newsroom/services/getheadlines.php"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")
CUTOFF = datetime(2025, 1, 1)
BATCH = 30
MAX_BATCHES = 40          # safety stop (~1,200 releases)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# -------------------------------------------------------------
# Fetching
# -------------------------------------------------------------
def get_feed_params(session):
    """Read the newsroom page once to get the feed parameters (page id, newsroom id)."""
    r = session.get(LIST_URL, timeout=30)
    r.raise_for_status()
    page_html = r.text
    pageid = re.search(r"pageid=(\d+)", page_html)
    child = re.search(r"var child_ids\s*=\s*'([^']*)'", page_html)
    if not pageid or not child:
        raise RuntimeError("Could not find feed parameters on the Nokia newsroom page (layout changed?)")
    return pageid.group(1), child.group(1)


def fetch_batch(session, offset, pageid, child_ids):
    params = {
        "archive": 1, "type": 1, "releases": "[]",
        "releases_offset": offset, "releases_batch_count": BATCH,
        "pageid": pageid, "child_ids": child_ids, "newsroom_lang": "en-us",
        "limit_datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "preview": "", "umbrella": 0,
    }
    r = session.get(FEED_URL, params=params, timeout=30,
                    headers={"Referer": LIST_URL, "X-Requested-With": "XMLHttpRequest"})
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        data = [v for k, v in data.items() if k != "error"]
    return [d for d in (data or []) if isinstance(d, dict)]


def is_press_release(item):
    return "press releases" in str(item.get("tag_names", "")).lower()


def parse_date(item):
    for key, fmt in (("publishdate", "%Y-%m-%d %H:%M:%S"), ("date", "%d %b %Y")):
        try:
            return datetime.strptime(str(item.get(key, "")).strip(), fmt)
        except ValueError:
            continue
    return None


def collect_press_releases():
    session = requests.Session()
    session.headers.update(HEADERS)
    pageid, child_ids = get_feed_params(session)

    rows, seen = [], set()
    for n in range(MAX_BATCHES):
        offset = n * BATCH
        batch = fetch_batch(session, offset, pageid, child_ids)
        if not batch:
            break
        dates = [d for d in (parse_date(i) for i in batch) if d]
        for item in batch:
            dt = parse_date(item)
            link = (item.get("shareurl") or item.get("caseurl") or "").strip()
            if not dt or dt < CUTOFF or not link or link in seen or not is_press_release(item):
                continue
            seen.add(link)
            rows.append({
                "title": " ".join(html.unescape(str(item.get("title", ""))).split()),
                "link": link,
                "dt": dt,
            })
        print(f"  batch offset {offset}: {len(batch)} items, oldest {min(dates).date() if dates else '?'}")
        if dates and max(dates) < CUTOFF:
            break
        time.sleep(0.5)
    return rows


# -------------------------------------------------------------
# Master CSV
# -------------------------------------------------------------
def load_master():
    if os.path.exists(MASTER_FILE):
        try:
            return pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(MASTER_FILE, encoding="latin-1")
    return pd.DataFrame(columns=["id", "company", "title", "link", "date", "fetched_at"])


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def norm_link(u):
    return str(u or "").split("?")[0].split("#")[0].rstrip("/").lower()


def save_to_master(df_new):
    master = load_master()
    if not master.empty:
        nokia = master[master["company"] == COMPANY]
        known_links = set(nokia["link"].dropna().map(norm_link))
        known_titles = set(nokia["title"].dropna().map(norm_title))
        mask = ~(df_new["link"].map(norm_link).isin(known_links) |
                 df_new["title"].map(norm_title).isin(known_titles))
        df_new = df_new[mask]
    if df_new.empty:
        print("ℹ️ No new Nokia press releases to add.")
        return
    updated = pd.concat([master, df_new], ignore_index=True) if not master.empty else df_new
    updated.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ Added {len(df_new)} new Nokia press releases to {MASTER_FILE}")
    for _, r in df_new.sort_values("date").iterrows():
        print(f"   📰 {r['date']}  {r['title']}")


# -------------------------------------------------------------
# Main
# -------------------------------------------------------------
def main():
    print(f"Fetching Nokia newsroom feed (press releases since {CUTOFF.date()})")
    try:
        items = collect_press_releases()
    except Exception as e:
        print(f"❌ Nokia scrape failed: {e}")
        sys.exit(1)

    if not items:
        print("❌ No Nokia press releases retrieved — the site may be blocking the scraper.")
        sys.exit(1)

    print(f"Found {len(items)} Nokia press releases since {CUTOFF.date()}")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_new = pd.DataFrame([{
        "id": str(uuid.uuid4()),
        "company": COMPANY,
        "title": it["title"],
        "link": it["link"],
        "date": it["dt"].strftime("%Y-%m-%d"),
        "fetched_at": now,
    } for it in items])
    save_to_master(df_new)


if __name__ == "__main__":
    main()
