import requests
import pandas as pd
import uuid
import os
import time
from bs4 import BeautifulSoup
from datetime import datetime

COMPANY = "Nokia"
BASE = "https://www.nokia.com"
LIST_URL = f"{BASE}/newsroom/telco-networks/"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}

# -------------------------------------------------------------
# Utilities
# -------------------------------------------------------------
def normalize_date(date_str):
    """Normalize date formats like '20Mar2025|09:00 AMEurope/Amsterdam' to 'YYYY-MM-DD'."""
    if not date_str or date_str == "(No date)":
        return date_str

    # Extract only the date portion before the first "|" or time zone info
    raw = date_str.split("|")[0].strip()

    # Handle formats like 20Mar2025 or 5Feb2025
    try:
        dt = datetime.strptime(raw, "%d%b%Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Handle other formats (fallbacks)
    for fmt in ("%B %d, %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            continue

    return raw.strip()


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
    print(f"✅ Added {len(only_new)} new Nokia press releases to {MASTER_FILE}")

# -------------------------------------------------------------
# Main
# -------------------------------------------------------------
def main():
    print(f"Fetching list: {LIST_URL}")
    r = requests.get(LIST_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Each PR is in <a class="td_headlines headline_a" href="...">
    cards = soup.select("a.td_headlines.headline_a")
    print(f"Found {len(cards)} Nokia press releases\n")

    rows = []
    for a in cards:
        link = a.get("href")
        if not link:
            continue
        link = link if link.startswith("http") else BASE + link

        # Extract title and date
        title_el = a.select_one(".pp_headline, h3")
        date_el = a.select_one(".pp-item-date-city-wrapper, .pp_date")
        title = title_el.get_text(strip=True) if title_el else "(No title)"
        date_str = date_el.get_text(strip=True) if date_el else "(No date)"
        date = normalize_date(date_str)

        rows.append({
            "id": str(uuid.uuid4()),
            "company": COMPANY,
            "title": title,
            "link": link,
            "date": date,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        print(f"📰 {title}\n📅 {date}\n🔗 {link}\n")
        time.sleep(0.2)

    if rows:
        df_new = pd.DataFrame(rows)
        save_to_master(df_new)
    else:
        print("No press releases fetched.")

if __name__ == "__main__":
    main()
