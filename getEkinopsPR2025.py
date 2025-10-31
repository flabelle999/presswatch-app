import os, uuid, time, requests, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

COMPANY = "Ekinops"
BASE = "https://www.ekinops.com"
LIST_URL = f"{BASE}/news"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
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
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str.strip(), "%d %B %Y").strftime("%Y-%m-%d")
    except Exception:
        return date_str.strip()

def get_page(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

# ---------- main ----------
def main():
    cutoff = datetime(2025, 1, 1)
    offset = 0
    step = 16
    rows = []
    seen_links = set()

    print(f"Fetching Ekinops press releases starting from {LIST_URL}")

    while True:
        url = f"{LIST_URL}?start={offset}" if offset else LIST_URL
        print(f"🌐 Page {offset // step + 1}: {url}")
        soup = get_page(url)

        items = soup.select("div.sppb-article-info-wrap")
        if not items:
            print("⚠️ No more press releases found — stopping.")
            break

        stop = False
        for item in items:
            a = item.select_one("h3 a[itemprop='url']")
            date_el = item.select_one("div.sppb-article-meta span.sppb-meta-date[itemprop='datePublished']")

            if not a or not a.get("href"):
                continue

            link = urljoin(BASE, a["href"])
            if link in seen_links:
                continue
            seen_links.add(link)

            title = a.get_text(strip=True)
            date_str = normalize_date(date_el.get_text(strip=True) if date_el else "")

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                date_obj = None

            # Stop once we reach a date before 2025
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

            time.sleep(0.1)

        if stop:
            break
        offset += step
        time.sleep(0.7)

    df_new = pd.DataFrame(rows, columns=["id","company","title","link","date","fetched_at"])
    print(f"✅ Total kept (2025+): {len(df_new)}")
    save_to_master(df_new)

if __name__ == "__main__":
    main()
