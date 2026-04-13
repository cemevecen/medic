import requests
import json

with open("config_api.json") as f:
    config = json.load(f)

key = config["rapidapi_key_1"]  # Aynı key

print("=" * 70)
print("🧪 API 3: Eczanem Test")
print("=" * 70)

url = "https://eczanem.p.rapidapi.com/eczane"
headers = {
    "x-rapidapi-key": key,
    "x-rapidapi-host": "eczanem.p.rapidapi.com"
}

# Test 1: il parametresiyle
print("\n1️⃣ Ankara'daki eczaneler:")
r = requests.get(url, params={"il": "Ankara"}, headers=headers, timeout=5)
print(f"   Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    if isinstance(data, dict):
        print(f"   Keys: {list(data.keys())}")
        result = data.get("data", data.get("result", []))
    else:
        result = data
    
    if isinstance(result, list):
        print(f"   Total: {len(result)}")
        if result:
            print(f"   First: {result[0]}")

# Test 2: il + ilce parametresiyle
print("\n2️⃣ Ankara/Çankaya:")
r = requests.get(url, params={"il": "Ankara", "ilce": "Çankaya"}, headers=headers, timeout=5)
print(f"   Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    if isinstance(data, dict):
        result = data.get("data", data.get("result", []))
    else:
        result = data
    
    if isinstance(result, list):
        print(f"   Total: {len(result)}")
        if result:
            item = result[0]
            print(f"   Fields: {list(item.keys()) if isinstance(item, dict) else 'N/A'}")
            print(f"   Sample: {str(item)[:200]}")

