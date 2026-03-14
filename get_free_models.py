import requests
import json
import os
from dotenv import load_dotenv

load_dotenv('.env')
api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    print("No API key found")
    exit(1)

headers = {"Authorization": f"Bearer {api_key}"}
resp = requests.get("https://openrouter.ai/api/v1/models", headers=headers)

if resp.status_code != 200:
    print(f"Error fetching models: {resp.status_code} {resp.text}")
    exit(1)

models = resp.json().get("data", [])
free_models = []
for m in models:
    pricing = m.get("pricing", {})
    # OpenRouter free models typically have 0 or "0" for pricing
    if str(pricing.get("prompt")) == "0" and str(pricing.get("completion")) == "0":
        if "free" in m["id"].lower():
            free_models.append(m["id"])

print("Found Free Models:")
for m in free_models:
    print(m)
