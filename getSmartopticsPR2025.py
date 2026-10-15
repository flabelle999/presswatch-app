# getSmartopticsPR2025.py
# Smartoptics redesigned its press release listing (late 2025). Each release is now a
# <div class="listing-post ..."> with <time class="listing-item-date" datetime="YYYY-MM-DD">
# and <h5 class="listing-item-title"><a href=".../cision-post/...">Title</a></h5>.
# Title and date are read straight from the listing (no detail-page requests).
import os, re, sys, time, uuid, html, requests, pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

COMPANY = "Smartoptics"
BASE = "https://smartoptics.com"
LIST_URL = f"{BASE}/investor-relations/press-releases/"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")
CUTOFF = datetime(2025, 1, 1)
MAX_PAGES = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# -------------------------------------------------
# CSV handling
# -------------------------------------------------
def load_master():
    if os.path.exists(MASTER_FILE):
        try:
            return pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(MASTER_FILE, encoding="latin-1")
    return pd.DataFrame(columns=["id", "company", "title", "link", "date", "fetched_at"])


def norm_title(t):
    t = re.sub(r"\s*\|\s*Smartoptics\s*$", "", str(t or ""))   # older rows end with " | Smartoptics"
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def norm_link(u):
    """Compare on the release slug: older rows use /gt_cision_post/<slug>/, new ones /cision-post/<slug>/."""
    path = str(u or "").split("?")[0].split("#")[0].rstrip("/").lower()
    return path.rsplit("/", 1)[-1]


def save_to_master(df_new):
    master = load_master()
    if not master.empty:
        so = master[master["company"] == COMPANY]
        known_links = set(so["link"].dropna().map(norm_link))
        known_titles = set(so["title"].dropna().map(norm_title))
        mask = ~(df_new["link"].map(norm_link).isin(known_links) |
                 df_new["title"].map(norm_title).isin(known_titles))
        df_new = df_new[mask]
    if df_new.empty:
        print("ℹ️ No new Smartoptics press releases to add.")
        return
    updated = pd.concat([master, df_new], ignore_index=True) if not master.empty else df_new
    updated.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ Added {len(df_new)} Smartoptics press releases to {MASTER_FILE}")
    for _, r in df_new.sort_values("date").iterrows():
        print(f"   📰 {r['date']}  {r['title']}")

# -------------------------------------------------
# Scraping
# -------------------------------------------------
def parse_page(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    items = []
    for post in soup.select("div.listing-post"):
        a = post.select_one(".listing-item-title a[href]")
        t = post.select_one("time.listing-item-date")
        if not a or not t:
            continue
        raw_date = (t.get("datetime") or t.get_text(strip=True)).strip()[:10]
        try:
            dt = datetime.strptime(raw_date, "%Y-%m-%d")
        except ValueError:
            print(f"⚠️ Could not parse date '{raw_date}' for {a.get_text(strip=True)}")
            continue
        items.append({
            "title": " ".join(html.unescape(a.get_text(" ", strip=True)).split()),
            "link": urljoin(BASE, a["href"]),
            "dt": dt,
        })
    return items


def main():
    print(f"Fetching Smartoptics press releases starting at {LIST_URL}")
    session = requests.Session()
    session.headers.update(HEADERS)
    rows, seen = [], set()

    for page_num in range(1, MAX_PAGES + 1):
        url = LIST_URL if page_num == 1 else f"{LIST_URL}page/{page_num}/"
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                break
            r.raise_for_status()
        except Exception as e:
            print(f"❌ Page {page_num} failed: {e}")
            break
        items = parse_page(r.text)
        print(f"🌐 Page {page_num}: {len(items)} items")
        if not items:
            break
        for it in items:
            if it["dt"] >= CUTOFF and it["link"] not in seen:
                seen.add(it["link"])
                rows.append(it)
        if max(i["dt"] for i in items) < CUTOFF:
            break
        time.sleep(1)

    if not rows:
        print("❌ No Smartoptics press releases retrieved — page layout may have changed again.")
        sys.exit(1)

    print(f"✅ Total kept (2025+): {len(rows)}")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_new = pd.DataFrame([{
        "id": str(uuid.uuid4()),
        "company": COMPANY,
        "title": it["title"],
        "link": it["link"],
        "date": it["dt"].strftime("%Y-%m-%d"),
        "fetched_at": now,
    } for it in rows])
    save_to_master(df_new)


if __name__ == "__main__":
    main()
