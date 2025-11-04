import os, time, uuid, requests, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

COMPANY = "Ribbon Communications"
BASE = "https://ribboncommunications.com"
LIST_URL = f"{BASE}/company/media-center/press-releases"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------- CSV handling ----------
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
    print(f"✅ Added {len(df_new)} {COMPANY} press releases to {MASTER_FILE}")

# ---------- helpers ----------
def normalize_date(date_str):
    """Convert 'October 31, 2025' -> '2025-10-31'."""
    try:
        return datetime.strptime(date_str.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return date_str.strip()

def get_page(url):
    """Get a page with retry logic to avoid 403 on CI/CD."""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 403:
                print(f"⚠️ Attempt {attempt+1}: 403 Forbidden — retrying...")
                time.sleep(2)
                continue
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except requests.RequestException as e:
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    raise RuntimeError(f"❌ Unable to fetch {url}")

# ---------- main ----------
def main():
    cutoff = datetime(2025, 1, 1)
    page = 0
    rows = []
    seen_links = set()
    stop = False

    print(f"Fetching {COMPANY} press releases starting from {LIST_URL}")

    while not stop:
        url = f"{LIST_URL}?page={page}"
        print(f"🌐 Page {page}: {url}")
        soup = get_page(url)
        items = soup.select("div.mc-list-item-wrapper")

        if not items:
            print("⚠️ No more press releases found — stopping.")
            break

        for item in items:
            date_el = item.select_one("span.dates")
            link_el = item.select_one("a[href^='/company/media-center/press-releases/']")

            if not date_el or not link_el:
                continue

            date_str = normalize_date(date_el.get_text(strip=True))
            link = urljoin(BASE, link_el.get("href"))
            title = link_el.get_text(strip=True)
            if not title:
                # fallback: try reading parent h3 or sibling
                h3 = item.select_one("h3")
                title = h3.get_text(strip=True) if h3 else "(No title)"

            if link in seen_links:
                continue
            seen_links.add(link)

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                date_obj = None

            # Stop once we reach something older than 2025
            if date_obj and date_obj < cutoff:
                print(f"🛑 Reached {date_str} (<2025) — stopping pagination.")
                stop = True
                break

            if date_obj and date_obj >= cutoff:
                rows.append({
                    "id": str(uuid.uuid4()),
                    "company": COMPANY,
                    "title": title,
                    "link": link,
                    "date": date_str,
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                print(f"📰 {title}\n📅 {date_str}\n🔗 {link}\n")

            time.sleep(0.2)

        if stop:
            break
        page += 1
        time.sleep(0.7)

    df_new = pd.DataFrame(rows, columns=["id","company","title","link","date","fetched_at"])
    print(f"✅ Total kept (2025+): {len(df_new)}")
    save_to_master(df_new)

if __name__ == "__main__":
    main()
