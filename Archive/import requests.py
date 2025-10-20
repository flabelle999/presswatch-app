import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

BASE = "https://zhone.com"
LIST_URL = f"{BASE}/company/news/news-releases/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
)
DATE_RE = re.compile(rf"({'|'.join(MONTHS)})\s+\d{{1,2}},\s+\d{{4}}", re.I)


def normalize_date(date_str: str) -> str:
    """Convert 'May 5, 2025' -> '2025-05-05'."""
    try:
        dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str.strip()


def extract_date(soup: BeautifulSoup) -> str:
    """Try multiple strategies to extract the publication date."""
    # 1) <time> tag
    t = soup.find("time")
    if t:
        if t.get("datetime"):
            return normalize_date(t["datetime"])
        txt = t.get_text(" ", strip=True)
        if DATE_RE.search(txt):
            return normalize_date(DATE_RE.search(txt).group(0))

    # 2) Meta tags
    meta_props = [
        ("property", "article:published_time"),
        ("property", "og:published_time"),
        ("name", "pubdate"),
        ("name", "publishdate"),
        ("name", "date"),
    ]
    for attr, val in meta_props:
        m = soup.find("meta", attrs={attr: val})
        if m and m.get("content"):
            c = m["content"].strip()
            m2 = DATE_RE.search(c)
            return normalize_date(m2.group(0) if m2 else c)

    # 3) JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                data = [data]
            for obj in data:
                for key in ("datePublished", "dateCreated", "dateModified"):
                    if isinstance(obj, dict) and key in obj:
                        val = str(obj[key])
                        m2 = DATE_RE.search(val)
                        return normalize_date(m2.group(0) if m2 else val)
        except Exception:
            pass

    # 4) Text pattern in first paragraphs
    containers = [
        soup.find("main"),
        soup.find("article"),
        soup.find("div", class_=re.compile(r"(content|entry|article)", re.I)),
        soup,
    ]
    seen = set()
    for c in containers:
        if not c or id(c) in seen:
            continue
        seen.add(id(c))
        text = " ".join(
            p.get_text(" ", strip=True)
            for p in c.find_all(["p", "div", "span"])[:30]
        )
        m = DATE_RE.search(text)
        if m:
            return normalize_date(m.group(0))

    return "(No date found)"


def extract_title(soup: BeautifulSoup) -> str:
    """Extract the page title."""
    h = soup.find(["h1", "h2"])
    if h:
        return h.get_text(" ", strip=True)
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return "(No title found)"


def get_press_release_links(list_url: str):
    """Get all PR links from the main newsroom page."""
    r = requests.get(list_url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    s = BeautifulSoup(r.text, "html.parser")

    anchors = s.select("div.secondary-card__large.text-white a.empty-link")
    links = []
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        links.append(urljoin(BASE, href))
    return list(dict.fromkeys(links))  # deduplicate


def main():
    print(f"Fetching list: {LIST_URL}")
    links = get_press_release_links(LIST_URL)
    print(f"Found {len(links)} press release links\n")

    for url in links:
        try:
            html = requests.get(url, headers=HEADERS, timeout=20).text
            page = BeautifulSoup(html, "html.parser")
            title = extract_title(page)
            date = extract_date(page)

            print("📰", title)
            print("📅", date)
            print("🔗", url, "\n")
            time.sleep(0.8)  # be polite
        except Exception as e:
            print(f"⚠️ Error on {url}: {e}\n")


if __name__ == "__main__":
    main()
