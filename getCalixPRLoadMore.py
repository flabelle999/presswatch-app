import os, uuid, pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from urllib.parse import urljoin

COMPANY = "Calix"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")
BASE = "https://www.calix.com"

# ---------- CSV helpers ----------
def load_master():
    if os.path.exists(MASTER_FILE):
        return pd.read_csv(MASTER_FILE)
    return pd.DataFrame(columns=["id","company","title","link","date","fetched_at"])

def save_to_master(df_new):
    if df_new.empty:
        print("ℹ️ No new press releases to add."); return
    master = load_master()
    if master.empty:
        updated = df_new
    else:
        merged = pd.merge(df_new, master[["company","title"]], on=["company","title"], how="left", indicator=True)
        only_new = merged[merged["_merge"]=="left_only"].drop(columns="_merge")
        updated = pd.concat([master, only_new[df_new.columns]], ignore_index=True)
    updated.to_csv(MASTER_FILE, index=False)
    print(f"✅ Added {len(df_new)} Calix press releases to {MASTER_FILE}")

# ---------- main ----------
def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Loading https://www.calix.com/press-release.html ...")
        page.goto("https://www.calix.com/press-release.html", timeout=90000)

        # wait until at least one press release card appears
        try:
            page.wait_for_selector("div.cmp-card", timeout=20000)
        except PlaywrightTimeout:
            print("⚠️ No press release cards detected after waiting 20s.")
        else:
            # click "Load more" until it disappears
            while True:
                btn = page.query_selector("button:has-text('Load more')")
                if not btn:
                    break
                btn.click()
                # small delay for new cards to render
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
        info = c.select_one(".cmp-card_info")
        date = ""
        if info:
            txt = info.get_text(strip=True)
            date = txt.split("|")[0].strip()
        rows.append({
            "id": str(uuid.uuid4()),
            "company": COMPANY,
            "title": title,
            "link": link,
            "date": date,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    df_new = pd.DataFrame(rows, columns=["id","company","title","link","date","fetched_at"])
    print(f"✅ Total collected: {len(df_new)}")
    for _, r in df_new.iterrows():
        print(f"📰 {r.title}\n📅 {r.date}\n🔗 {r.link}\n")

    save_to_master(df_new)

if __name__ == "__main__":
    main()
