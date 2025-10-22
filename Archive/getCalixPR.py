import os, re, uuid, time, requests, pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

COMPANY   = "Calix"
BASE      = "https://www.calix.com"
LIST_URL  = f"{BASE}/press-release.html"
MASTER_CSV= os.path.join(os.path.dirname(__file__), "press_releases_master.csv")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/122.0 Safari/537.36")
}

# ---------- helpers ----------
MONTHS = ("January","February","March","April","May","June",
          "July","August","September","October","November","December")
DATE_RE = re.compile(rf"({'|'.join(MONTHS)})\s+\d{{1,2}},\s+\d{{4}}", re.I)

def normalize_date(s: str) -> str:
    s = (s or "").strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    # allow extracting "Month DD, YYYY" inside a longer string
    m = DATE_RE.search(s)
    if m:
        try:
            return datetime.strptime(m.group(0), "%B %d, %Y").strftime("%Y-%m-%d")
        except Exception:
            pass
    return s

def title_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1].replace(".html", "")
    return slug.replace("-", " ").strip().capitalize()

def load_master():
    if os.path.exists(MASTER_CSV):
        return pd.read_csv(MASTER_CSV)
    return pd.DataFrame(columns=["id","company","title","link","date","fetched_at"])

def save_to_master(df_new):
    if df_new.empty:
        print("ℹ️ No new press releases to add."); return
    master = load_master()
    merged = pd.merge(df_new, master[["company","title"]], on=["company","title"], how="left", indicator=True)
    only_new = merged[merged["_merge"]=="left_only"].drop(columns="_merge")
    if only_new.empty:
        print("ℹ️ No new unique entries found."); return
    updated = pd.concat([master, only_new[df_new.columns]], ignore_index=True)
    updated.to_csv(MASTER_CSV, index=False)
    print(f"✅ Added {len(only_new)} new Calix press releases to {MASTER_CSV}")

# ---------- robust date extraction from PR detail ----------
def fetch_date_from_detail(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        s = BeautifulSoup(r.text, "html.parser")

        # 1) <time>
        t = s.find("time")
        if t:
            if t.get("datetime"): return normalize_date(t["datetime"])
            txt = t.get_text(" ", strip=True)
            d = normalize_date(txt)
            if d: return d

        # 2) Meta possibilities
        for attrs in (
            {"property":"article:published_time"},
            {"name":"publicationDate"},
            {"name":"pubdate"},
            {"name":"publishdate"},
            {"name":"date"},
        ):
            m = s.find("meta", attrs=attrs)
            if m and m.get("content"):
                d = normalize_date(m["content"])
                if d: return d

        # 3) JSON-LD
        for script in s.find_all("script", type="application/ld+json"):
            try:
                import json
                data = json.loads(script.string or "")
                if isinstance(data, dict): data = [data]
                for obj in data:
                    if isinstance(obj, dict):
                        for k in ("datePublished","dateCreated","dateModified"):
                            if obj.get(k):
                                d = normalize_date(str(obj[k]))
                                if d: return d
            except Exception:
                pass

        # 4) Fallback: search visible text
        txt = s.get_text(" ", strip=True)
        d = normalize_date(txt)
        return d or "(No date found)"
    except Exception:
        return "(No date found)"

# ---------- main ----------
def main():
    print(f"Fetching page: {LIST_URL}")
    r = requests.get(LIST_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Capture every PR card/link on the page
    anchors = soup.select("a[href^='/press-release/'], a[href*='/press-release/']")
    print(f"Found {len(anchors)} candidate links on listing page\n")

    rows = []
    seen = set()
    for a in anchors:
        href = a.get("href") or ""
        if not href.startswith("/press-release/"): 
            continue
        link = urljoin(BASE, href)
        if link in seen: 
            continue
        seen.add(link)

        # Title visible on card, else from URL
        title = (a.get_text(strip=True) or "").strip() or title_from_url(link)

        # Try to read date from the card's info area
        card = a.find_parent("div", class_=re.compile(r"cmp-card"))
        date_text = ""
        if card:
            # Calix often uses this container; keep a few variants for safety
            info = card.select_one(".cmp-card_info, .cmp-card__info, .cmp-card-info, time, .date")
            if info:
                date_text = info.get_text(" ", strip=True)
                # e.g. "Oct 20, 2025 | 4 min read"
                if "|" in date_text:
                    date_text = date_text.split("|", 1)[0].strip()

        date = normalize_date(date_text) if date_text else ""
        if not date or date == date_text:  # missing/unparsed → fetch from detail page
            date = fetch_date_from_detail(link)
            # tiny politeness delay to avoid hammering
            time.sleep(0.25)

        print(f"📰 {title}\n📅 {date}\n🔗 {link}\n")

        rows.append({
            "id": str(uuid.uuid4()),
            "company": COMPANY,
            "title": title,
            "link": link,
            "date": date,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        time.sleep(0.1)

    df_new = pd.DataFrame(rows)
    if not df_new.empty:
        save_to_master(df_new)
    else:
        print("No press releases fetched.")

if __name__ == "__main__":
    main()
