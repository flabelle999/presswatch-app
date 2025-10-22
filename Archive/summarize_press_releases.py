import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import subprocess
import time

CSV_FILE = "press_releases_sample_new.csv"
MODEL_NAME = "llama3"


def check_ollama_running():
    """Verify that the Ollama service is running locally."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            print("✅ Ollama is running.")
            return True
    except Exception as e:
        print("❌ Ollama not running or unreachable:", e)
    return False


def get_pr_text(url):
    """Fetch and clean the full text content from a press release URL."""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.extract()

        text = " ".join(soup.stripped_strings)
        return text[:30000]
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return ""

def query_ollama(prompt, model=MODEL_NAME):
    """Send a prompt to the local Ollama model and return its plain text output (UTF-8 safe)."""
    try:
        print(f"\n🧠 Querying Ollama model '{model}'...")
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt.encode("utf-8"),
            capture_output=True,
            text=False,
            timeout=600   # increased from 180 to 600 seconds
        )
        if result.returncode == 0:
            output = result.stdout.decode("utf-8", errors="ignore").strip()
            if output:
                print("✅ Ollama returned:", output[:200], "...\n")
            else:
                print("⚠️ Ollama returned empty output.")
            return output
        else:
            print("⚠️ Ollama error:", result.stderr.decode('utf-8', errors='ignore'))
    except subprocess.TimeoutExpired:
        print("⏰ Ollama response timed out — try increasing timeout or truncating input.")
    except Exception as e:
        print(f"⚠️ Failed to query Ollama: {e}")
    return ""

def generate_summary_and_impact(pr_text, company):
    """Two-pass approach: summarize first, then analyze impact (robust)."""
    if not pr_text.strip():
        return "", ""

    # ---- 1. First pass: concise summary ----
    summary_prompt = f"""
Summarize the following press release in about 5 concise sentences.

Press release:
{pr_text}
"""
    summary = query_ollama(summary_prompt)

    # If Ollama timed out or returned nothing, fall back to a shortened version
    if not summary.strip():
        short_text = pr_text[:8000]
        print("⚠️ Summary was empty — retrying with truncated input.")
        summary_prompt = f"Summarize this text in 5 sentences:\n\n{short_text}"
        summary = query_ollama(summary_prompt)

    # ---- 2. Second pass: impact analysis using the summary ----
    impact_prompt = f"""
The following is a summarized version of a press release from {company}:

{summary}

Based on this summary, analyze how this announcement could impact Zhone Technologies —
competitively, strategically, or technologically.
Write 3–5 thoughtful sentences focusing on relevance, risks, or opportunities for Zhone.
"""
    impact = query_ollama(impact_prompt)

    return summary, impact

def main():
    if not os.path.exists(CSV_FILE):
        print(f"❌ CSV file {CSV_FILE} not found.")
        return

    if not check_ollama_running():
        print("⚠️ Please start Ollama with 'ollama serve' before running this script.")
        return

    df = pd.read_csv(CSV_FILE)

    # --- Clean only the relevant text columns ---
    if "summary_ai" not in df.columns:
        df["summary_ai"] = ""
    if "impact_for_zhone" not in df.columns:
        df["impact_for_zhone"] = ""

    # Replace 'nan', 'NaN', None, or single spaces with real empty strings
    for col in ["summary_ai", "impact_for_zhone"]:
        df[col] = (
            df[col]
            .astype(str)
            .replace(["nan", "NaN", " ", "None"], "")
        )

    # --- Main loop ---
    for idx, row in df.iterrows():
        # Skip if summary already exists and is non-empty after cleaning
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

        # Save progress after each PR
        df.to_csv(CSV_FILE, index=False)
        print("✅ Updated row and saved CSV.")

    print("\n🎯 All done. Summaries and impacts populated.")


if __name__ == "__main__":
    main()
