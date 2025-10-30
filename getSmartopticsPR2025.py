import os, re, time, uuid, requests, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

COMPANY = "Smartoptics"
BASE = "https://smartoptics.com"
LIST_URL = f"{BASE}/investor-relations/press-releases/"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# -------------------------------------------------
# CSV handling
# -------------------------------------------------
def load_master():
    if os.path.exists(MASTER_FILE):
        try:
            return pd.read_csv(MASTER_FILE, encoding="utf-8")
        except UnicodeDecodeError:
            return pd.read_csv(MASTER_FILE, encoding="latin-1")
    return pd.DataFrame(columns=["id","company","title","link","date","fetched_at"])

def save_to_master(df_new):
    if df_new.empty:
        print("ℹ️ No new press releases to add."); return
    master = load_master()
    if master.empty:
        updated = df_new
    else:
        merged = pd.merge(df_new, master[["company","title"]],
                          on=["company","title"], how="left", indicator=True)
        only_new = merged[merged["_merge"]=="left_only"].drop(columns="_merge")
        updated = pd.concat([master, only_new[df_new.columns]], ignore_index=True)
    updated.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ Added {len(df_new)} Smartoptics press releases to {MASTER_FILE}")

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def get_page(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def normalize_date(s):
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception:
        return s.strip()

def extract_title(link_url):
    """Fetch the title text from the actual press release page."""
    try:
        r = requests.get(link_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return "(No title)"
        s = BeautifulSoup(r.text, "html.parser")
        h = s.find(["h1","h2","title"])
        if h:
            return h.get_text(" ", strip=True)
    except Exception:
        pass
    return "(No title)"

# -------------------------------------------------
# Main logic
# -------------------------------------------------
def main():
    cutoff = datetime(2025, 1, 1)
    page_num = 1
    rows = []
    stop = False

    print(f"Fetching Smartoptics press releases starting at {LIST_URL}")

    while not stop:
        url = LIST_URL if page_num == 1 else f"{LIST_URL}page/{page_num}/"
        print(f"🌐 Page {page_num}: {url}")
        soup = get_page(url)

        cards = soup.select("a.gt-listing-item-overlay-link")
        dates = [d.get_text(strip=True) for d in soup.select("div.gt-listing-item-date")]

        if not cards:
            print("⚠️ No more items found — stopping.")
            break

        for i, a in enumerate(cards):
            link = a.get("href")
            if not link:
                continue
            link = urljoin(BASE, link)
            date_raw = dates[i] if i < len(dates) else ""
            date_str = normalize_date(date_raw)
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                date_obj = None

            if date_obj and date_obj < cutoff:
                stop = True
                print(f"🛑 Reached {date_str} (<2025) — stopping pagination.")
                break

            title = extract_title(link)
            rows.append({
                "id": str(uuid.uuid4()),
                "company": COMPANY,
                "title": title,
                "link": link,
                "date": date_str,
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            print(f"📰 {title}\n📅 {date_str}\n🔗 {link}\n")
            time.sleep(0.3)

        page_num += 1
        time.sleep(1)

    df_new = pd.DataFrame(rows, columns=["id","company","title","link","date","fetched_at"])
    print(f"✅ Total kept (2025+): {len(df_new)}")
    save_to_master(df_new)

if __name__ == "__main__":
    main()
