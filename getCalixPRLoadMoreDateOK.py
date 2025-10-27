import os, uuid, pandas as pd, time, re, requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from urllib.parse import urljoin

COMPANY = "Calix"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")
BASE = "https://www.calix.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ---------- CSV helpers ----------
def load_master():
    if os.path.exists(MASTER_FILE):
        try:
            return pd.read_csv(MASTER_FILE, encoding="utf-8")
        except UnicodeDecodeError:
            return pd.read_csv(MASTER_FILE, encoding="latin-1")
    return pd.DataFrame(columns=["id","company","title","link","date","fetched_at"])

def save_to_master(df_new):
    if df_new.empty:
        print("ℹ️ No new press releases to add.")
        return
    master = load_master()
    if master.empty:
        updated = df_new
    else:
        merged = pd.merge(df_new, master[["company","title"]],
                          on=["company","title"], how="left", indicator=True)
        only_new = merged[merged["_merge"]=="left_only"].drop(columns="_merge")
        updated = pd.concat([master, only_new[df_new.columns]], ignore_index=True)
    updated.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ Added {len(df_new)} Calix press releases to {MASTER_FILE}")

# ---------- date helpers ----------
def normalize_date(date_str):
    if not date_str:
        return ""
    date_str = date_str.strip().replace("Sept", "Sep")
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return date_str.strip()

def fetch_date_from_detail(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return ""
        s = BeautifulSoup(r.text, "html.parser")

        for span in s.find_all("span", class_=re.compile("absolute-to-relative", re.I)):
            text = span.get_text(" ", strip=True)
            m = re.search(r"([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})", text)
            if m:
                return normalize_date(m.group(1))

        text = s.get_text(" ", strip=True)
        m = re.search(r"([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})", text)
        if m:
            return normalize_date(m.group(1))
    except Exception:
        pass
    return ""

# ---------- main ----------
def main():
    cutoff = datetime(2025, 1, 1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Loading https://www.calix.com/press-release.html ...")
        page.goto("https://www.calix.com/press-release.html", timeout=90000)

        try:
            page.wait_for_selector("div.cmp-card", timeout=20000)
        except PlaywrightTimeout:
            print("⚠️ No press release cards detected after waiting 20s.")
        else:
            click_count = 0
            while True:
                anchors = page.query_selector_all("a[href^='/press-release/20']")
                hrefs = [a.get_attribute("href") for a in anchors if a.get_attribute("href")]
                valid_hrefs = [h for h in hrefs if re.search(r"/press-release/20\d{2}/", h)]
                if not valid_hrefs:
                    break

                last_years = []
                for h in valid_hrefs[-10:]:  # check last 10 links only
                    m = re.search(r"/press-release/(20\d{2})/", h)
                    if m:
                        last_years.append(int(m.group(1)))

                # stop only if we have 10 valid links and all ≤ 2024
                if last_years and len(last_years) >= 3 and all(y <= 2024 for y in last_years):
                    print("🛑 Detected only 2024-or-earlier links among latest results — stop loading more.")
                    break

                btn = page.query_selector("button:has-text('Load more')")
                if not btn:
                    break
                btn.click()
                click_count += 1
                print(f"🔁 Clicked 'Load more' ({click_count}) ...")
                page.wait_for_timeout(2000)

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.cmp-card")
    rows = []

    for c in cards:
        a = c.select_one("a[href^='/press-release/']")
        if not a:
            continue
        link = urljoin(BASE, a.get("href"))
        title = a.get_text(strip=True)

        date_str = fetch_date_from_detail(link)

        # Filter only 2025+
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            date_obj = None

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
        else:
            print(f"⏩ Skipping {title} ({date_str or 'no date'}) — before 2025\n")
        time.sleep(0.3)

    df_new = pd.DataFrame(rows, columns=["id","company","title","link","date","fetched_at"])
    print(f"✅ Total kept (2025+): {len(df_new)}")
    save_to_master(df_new)

if __name__ == "__main__":
    main()
