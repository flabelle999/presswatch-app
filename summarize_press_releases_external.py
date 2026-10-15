import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import json
import chardet

CSV_FILE = "press_releases_master.csv"
# llama-3.3-70b-versatile was retired by Groq on 2026-08-16 — see console.groq.com/docs/deprecations
MODEL_NAME = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)


def _html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    return " ".join(soup.stripped_strings)[:30000]


def _fetch_with_browser(url):
    """Fallback for sites that block plain HTTP clients (e.g. ciena.com returns 403)."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, args=["--disable-blink-features=AutomationControlled"])
            page = browser.new_context(user_agent=BROWSER_UA, locale="en-US").new_page()
            resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            html = page.content()
            status = resp.status if resp else None
            browser.close()
        if status and status >= 400:
            print(f"❌ Browser fetch of {url} returned HTTP {status}")
            return ""
        return _html_to_text(html)
    except Exception as e:
        print(f"❌ Browser fetch failed for {url}: {e}")
        return ""


def get_pr_text(url):
    """Fetch and clean the full text content from a press release URL.
    Tries plain requests first (fast; required for nokia.com, which blocks headless
    browsers), then falls back to headless Chromium (required for ciena.com)."""
    try:
        response = requests.get(url, timeout=15, headers={"User-Agent": BROWSER_UA})
        response.raise_for_status()
        return _html_to_text(response.text)
    except Exception as e:
        print(f"⚠️ Plain fetch failed for {url}: {e} — retrying with headless browser")
        return _fetch_with_browser(url)


def query_groq(prompt, model=MODEL_NAME):
    """Send a prompt to Groq Cloud API and return its response text."""
    try:
        if not GROQ_API_KEY or GROQ_API_KEY == "your_api_key_here":
            print("❌ Missing GROQ_API_KEY. Please set it as an environment variable.")
            return ""

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500,
        }
        # gpt-oss is a reasoning model: keep reasoning low so the answer isn't truncated
        if model.startswith("openai/gpt-oss"):
            data["reasoning_effort"] = "low"
        r = requests.post(GROQ_URL, headers=headers, json=data, timeout=60)
        result = r.json()

        if "choices" in result:
            reply = (result["choices"][0]["message"].get("content") or "").strip()
            print(f"✅ Groq returned: {reply[:200]}...\n")
            return reply
        else:
            print("⚠️ Unexpected Groq response:")
            print(json.dumps(result, indent=2))
            return ""
    except Exception as e:
        print(f"⚠️ Groq request failed: {e}")
        return ""


def generate_summary_and_impact(pr_text, company):
    """Two-pass approach: summarize first, then analyze impact."""
    if not pr_text.strip():
        return "", ""

    # ---- 1. First pass: concise summary ----
    summary_prompt = f"""
Summarize the following press release in one sentence.  Do not start the response by Here is the press release in 3 sentences.  Start with the summary directly.

Press release:
{pr_text}
"""
    summary = query_groq(summary_prompt)

    if not summary.strip():
        short_text = pr_text[:8000]
        print("⚠️ Summary was empty — retrying with truncated input.")
        summary_prompt = f"Summarize this text in one sentence:\n\n{short_text}"
        summary = query_groq(summary_prompt)

    # ---- 2. Second pass: impact analysis using the summary ----
    impact_prompt = f"""
The following is a summarized version of a press release from {company}:

{summary}

Based on this summary, analyze how this announcement could impact Zhone Technologies —
respond with a single sentence.
"""
    impact = query_groq(impact_prompt)

    return summary, impact


def main():
    if not os.path.exists(CSV_FILE):
        print(f"❌ CSV file {CSV_FILE} not found.")
        return

    # --- Detect encoding automatically ---
    with open(CSV_FILE, "rb") as f:
        raw_data = f.read(4096)
        result = chardet.detect(raw_data)
        encoding = result["encoding"] or "utf-8"
        print(f"🔎 Detected encoding: {encoding}")

    try:
        df = pd.read_csv(CSV_FILE, encoding=encoding)
    except Exception as e:
        print(f"⚠️ Failed to read CSV with {encoding}: {e}")
        print("➡️ Retrying with 'latin1' as last resort (very permissive).")
        df = pd.read_csv(CSV_FILE, encoding="latin1")

    if "summary_ai" not in df.columns:
        df["summary_ai"] = ""
    if "impact_for_zhone" not in df.columns:
        df["impact_for_zhone"] = ""

    for col in ["summary_ai", "impact_for_zhone"]:
        df[col] = (
            df[col]
            .astype(str)
            .replace(["nan", "NaN", " ", "None"], "")
        )

    for idx, row in df.iterrows():
        if str(row.get("summary_ai", "")).strip():
            continue

        company = str(row.get("company", ""))
        title = str(row.get("title", ""))
        link = str(row.get("link", ""))
        date = str(row.get("date", ""))

        print(f"\n📰 Processing {company} - {title}")

        text = get_pr_text(link)
        if not text:
            print("⚠️ Skipping (no text found)")
            continue

        summary, impact = generate_summary_and_impact(text, company)

        df.at[idx, "summary_ai"] = str(summary)
        df.at[idx, "impact_for_zhone"] = str(impact)

        df.to_csv(CSV_FILE, index=False)
        print("✅ Updated row and saved CSV.")

    print("\n🎯 All done. Summaries and impacts populated.")


if __name__ == "__main__":
    main()
