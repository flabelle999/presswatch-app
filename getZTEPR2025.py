import os
import time
import uuid
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------- CONFIG ----------
BASE_URL = "https://www.zte.com.cn"
START_URL = f"{BASE_URL}/global/about/news.html"
COMPANY = "ZTE"
MASTER_FILE = "press_releases_master.csv"
CUTOFF = datetime(2025, 1, 1)
# ----------------------------


def setup_driver():
    """Set up headless Chrome for both local + GitHub environments."""
    chrome_opts = Options()
    chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    chrome_opts.add_argument("--window-size=1920,1080")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--lang=en-US")
    chrome_opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=chrome_opts)
    return driver


def normalize_date(date_str):
    """Convert Chinese/English date formats to YYYY-MM-DD."""
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%b %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return date_str.strip()


def load_master():
    if not os.path.exists(MASTER_FILE):
        return pd.DataFrame(columns=["id", "company", "title", "link", "date", "fetched_at"])
    try:
        return pd.read_csv(MASTER_FILE, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(MASTER_FILE, encoding="latin1")


def save_to_master(df_new):
    master = load_master()
    if df_new.empty:
        print("ℹ️ No new press releases to add.")
        return
    merged = pd.merge(df_new, master[["company", "title"]], on=["company", "title"], how="left", indicator=True)
    new_rows = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])
    if new_rows.empty:
        print("ℹ️ No new unique rows to add.")
        return
    master = pd.concat([master, new_rows], ignore_index=True)
    master.to_csv(MASTER_FILE, index=False, encoding="utf-8")
    print(f"✅ Added {len(new_rows)} {COMPANY} press releases to {MASTER_FILE}")


def main():
    print(f"Fetching {COMPANY} press releases starting from {START_URL}")
    driver = setup_driver()
    driver.get(START_URL)
    time.sleep(4)

    all_rows = []
    page = 1
    stop = False

    while not stop:
        print(f"🌐 Page {page}: {driver.current_url}")

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.link-wrap"))
            )
        except Exception:
            print("⚠️ Could not detect news items — stopping.")
            break

        soup = BeautifulSoup(driver.page_source, "html.parser")
        cards = soup.select("dd.item-txt")

        if not cards:
            print("⚠️ No press releases found on this page — stopping.")
            break

        for card in cards:
            date_tag = card.find("span", class_="date")
            title_tag = card.find("h4", class_="ellipsis-3")
            link_tag = card.find_parent("a", class_="link-wrap")

            if not (date_tag and title_tag and link_tag):
                continue

            title = title_tag.get_text(strip=True)
            date_str = normalize_date(date_tag.get_text(strip=True))
            link_raw = link_tag.get("href", "").strip()
            link_full = link_raw if link_raw.startswith("http") else f"{BASE_URL}{link_raw}"

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                continue

            if date_obj < CUTOFF:
                print(f"🛑 Reached {date_str} (<2025) — stopping pagination.")
                stop = True
                break

            all_rows.append({
                "id": str(uuid.uuid4()),
                "company": COMPANY,
                "title": title,
                "link": link_full,
                "date": date_str,
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

            print(f"📰 {title}\n📅 {date_str}\n🔗 {link_full}\n")

        if stop:
            break

        # Check if there's a next page (based on ?page=)
        next_page = f"{BASE_URL}/global/about/news.html?page={page + 1}&layout=thumbs"
        driver.get(next_page)
        time.sleep(4)
        page += 1

    driver.quit()

    df = pd.DataFrame(all_rows)
    print(f"✅ Total kept (2025+): {len(df)}")
    save_to_master(df)


if __name__ == "__main__":
    main()
