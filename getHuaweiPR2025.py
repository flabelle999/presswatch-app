import os, uuid, time, json, requests, pandas as pd
from datetime import datetime

COMPANY = "Huawei"
BASE_URL = "https://www.huawei.com"
API_URL = f"{BASE_URL}/service/portalapplication/v1/dynamic/news"
LIST_PAGE = f"{BASE_URL}/en/news"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": BASE_URL,
    "Referer": LIST_PAGE,
}

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

# ---------- Utilities ----------
def normalize_date(date_str):
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return date_str.strip()

def get_content_id():
    """Fetch the dynamic contentId from Huawei news page."""
    print("🔍 Detecting contentId from Huawei news page...")
    r = requests.get(LIST_PAGE, headers=HEADERS, timeout=20)
    r.raise_for_status()
    # Look for a 32-character hex-like ID in JS configs (common pattern)
    import re
    match = re.search(r'"contentId"\s*:\s*"([a-f0-9]{32})"', r.text)
    if match:
        cid = match.group(1)
        print(f"✅ Found contentId: {cid}")
        return cid
    print("⚠️ Could not detect contentId automatically, using fallback.")
    return "ffa9314a50e34730a7a944fa03092fee"  # fallback known working ID

# ---------- Main ----------
def main():
    cutoff = datetime(2025, 1, 1)
    rows, page, stop = [], 1, False
    content_id = get_content_id()

    print(f"Fetching {COMPANY} press releases via API...")

    while not stop:
        payload = {
            "contentId": content_id,
            "keyword": "",
            "pageNum": page,
            "pageSize": 12,
            "catalogLabelList": [],
            "filterLabelList": []
        }

        print(f"📄 Page {page}")
        r = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload), timeout=20)
        if r.status_code != 200:
            print(f"⚠️ HTTP {r.status_code} — stopping.")
            break

        data = r.json()
        if not data.get("data") or not data["data"].get("results"):
            print("⚠️ No more data — stopping.")
            break

        for item in data["data"]["results"]:
            title = item.get("title", "").strip()
            date_str = normalize_date(item.get("releaseFormatTime", "").strip())
            link_raw = item.get("pageUrl", "").strip()

            if not title or not link_raw or not date_str:
                continue

            full_link = link_raw if link_raw.startswith("http") else f"https://{link_raw}"

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except Exception:
                date_obj = None

            if date_obj and date_obj < cutoff:
                print(f"🛑 Reached {date_str} (<2025) — stopping pagination.")
                stop = True
                break

            if date_obj and date_obj >= cutoff:
                rows.append({
                    "id": str(uuid.uuid4()),
                    "company": COMPANY,
                    "title": title,
                    "link": full_link,
                    "date": date_str,
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                print(f"📰 {title}\n📅 {date_str}\n🔗 {full_link}\n")

        if stop:
            break
        page += 1
        time.sleep(0.7)

    df_new = pd.DataFrame(rows, columns=["id","company","title","link","date","fetched_at"])
    print(f"✅ Total kept (2025+): {len(df_new)}")
    save_to_master(df_new)

if __name__ == "__main__":
    main()
