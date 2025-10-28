# getCienaPR2025.py
import os
import re
import json
import uuid
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit, urlunsplit
from datetime import datetime

BASE = "https://www.ciena.com"
LIST_URL = f"{BASE}/about/newsroom/press-releases/"
COMPANY = "Ciena"
MASTER_FILE = os.path.join(os.path.dirname(__file__), "press_releases_master.csv")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}

MONTHS = ("January","February","March","April","May","June",
          "July","August","September","October","November","December")
DATE_RE = re.compile(rf"({'|'.join(MONTHS)})\s+\d{{1,2}},\s+\d{{4}}", re.I)

def normalize_date(s: str) -> str:
    s = (s or "").strip()
    # Try ISO first
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    m = DATE_RE.search(s)
    if m:
        return datetime.strptime(m.group(0), "%B %d, %Y").strftime("%Y-%m-%d")
    return s

def clean_url(u: str) -> str:
    """Strip query/hash to avoid duplicates."""
    p = urlsplit(u)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))

def get_press_release_links() -> list:
    r = requests.get(LIST_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    # Grab all newsroom PR links (don’t require .html)
    anchors = soup.select("a[href*='/about/newsroom/press-releases/']")
    links = []
    for a in anchors:
        href = a.get("href") or ""
        if "/about/newsroom/press-releases/" in href:
            # skip the listing root itself
            if href.rstrip("/").endswith("/about/newsroom/press-releases"):
                continue
            full = href if href.startswith("http") else urljoin(BASE, href)
            links.append(clean_url(full))
    # de-dupe preserving order
    seen, out = set(), []
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def extract_date_from_detail(url: str) -> str:
    try:
        rr = requests.get(url, headers=HEADERS, timeout=20)
        rr.raise_for_status()
        s = BeautifulSoup(rr.text, "html.parser")

        # 1) <time> tag
        t = s.find("time")
        if t:
            if t.get("datetime"):
                d = normalize_date(t["datetime"])
                if re.match(r"\d{4}-\d{2}-\d{2}", d): return d
            txt = t.get_text(" ", strip=True)
            d = normalize_date(txt)
            if re.match(r"\d{4}-\d{2}-\d{2}", d): return d

        # 2) meta tags
        for attrs in (
            {"property": "article:published_time"},
            {"name": "pubdate"},
            {"name": "publishdate"},
            {"name": "date"},
            {"name": "DC.date.issued"},
        ):
            m = s.find("meta", attrs=attrs)
            if m and m.get("content"):
                d = normalize_date(m["content"])
                if re.match(r"\d{4}-\d{2}-\d{2}", d): return d

        # 3) JSON-LD
        for sc in s.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(sc.string or "")
                objs = data if isinstance(data, list) else [data]
                for obj in objs:
                    if isinstance(obj, dict):
                        for key in ("datePublished", "dateCreated", "dateModified"):
                            if obj.get(key):
                                d = normalize_date(str(obj[key]))
                                if re.match(r"\d{4}-\d{2}-\d{2}", d): return d
            except Exception:
                pass

        # 4) visible text fallback
        text = s.get_text(" ", strip=True)
        m = DATE_RE.search(text)
        if m:
            return normalize_date(m.group(0))
    except Exception:
        pass
    return ""

def extract_title_from_detail(url: str) -> str:
    try:
        rr = requests.get(url, headers=HEADERS, timeout=20)
        rr.raise_for_status()
        s = BeautifulSoup(rr.text, "html.parser")
        h = s.find(["h1","h2","title"])
        if h:
            return h.get_text(" ", strip=True)
    except Exception:
        pass
    return "(No title)"

def load_master():
    if os.path.exists(MASTER_FILE):
        try:
            return pd.read_csv(MASTER_FILE, encoding="utf-8")
        except UnicodeDecodeError:
            # fallback if file was created or edited in Excel/Windows
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
        merged = pd.merge(df_new, master[["company", "title"]],
                          on=["company", "title"], how="left", indicator=True)
        only_new = merged[merged["_merge"] == "left_only"].drop(columns="_merge")
        updated = pd.concat([master, only_new[df_new.columns]], ignore_index=True)
    updated.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")
    print(f"✅ Added {len(df_new)} {COMPANY} press releases to {MASTER_FILE}")

def main():
    cutoff = datetime(2025, 1, 1)
    print(f"Fetching list: {LIST_URL}")
    links = get_press_release_links()
    print(f"Found {len(links)} candidate links\n")

    rows = []
    for url in links:
        date_str = extract_date_from_detail(url)
        title = extract_title_from_detail(url)

        # Parse date and filter 2025+
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            dt = None

        if dt and dt >= cutoff:
            rows.append({
                "id": str(uuid.uuid4()),
                "company": COMPANY,
                "title": title,
                "link": url,
                "date": date_str,
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            print(f"📰 {title}\n📅 {date_str}\n🔗 {url}\n")
        else:
            print(f"⏩ Skipping {title} ({date_str or 'no date'}) — before 2025 or undated\n")

        time.sleep(0.3)

    if rows:
        df_new = pd.DataFrame(rows)
        save_to_master(df_new)
    else:
        print("No press releases fetched after Jan 1 2025.")

if __name__ == "__main__":
    main()
