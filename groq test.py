import requests
import os
import json

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

prompt = "Provide an analysis of the impact of this press release on Zhone Tchnologies https://www.nokia.com/newsroom/nokia-launches-ftth-digital-twin-and-ai-powered-tools-to-boost-network-reliability/ in around 5 sentences"

url = "https://api.groq.com/openai/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
}
data = {
    "model": "llama-3.3-70b-versatile",
    "messages": [{"role": "user", "content": prompt}],
}

response = requests.post(url, headers=headers, json=data)

try:
    result = response.json()
    if "choices" in result:
        print(result["choices"][0]["message"]["content"])
    else:
        print("⚠️ Unexpected response from Groq:")
        print(json.dumps(result, indent=2))
except Exception as e:
    print("❌ Error:", e)
    print("Raw response:", response.text)
