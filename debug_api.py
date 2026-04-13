import requests
import json

# Config yükle
with open("config_api.json", "r") as f:
    config = json.load(f)

key = config["rapidapi_key_1"]

print("=" * 70)
print("🔬 API 1 GERÇEK TEST - Doğrudan HTTP isteği")
print("=" * 70)

url = "https://nobetci-eczaneler-turkiye1.p.rapidapi.com/pharmacies"
headers = {
    "x-rapidapi-key": key,
    "x-rapidapi-host": "nobetci-eczaneler-turkiye1.p.rapidapi.com"
}

# Test 1: Başlık parametresi olmadan
print("\n1️⃣ Parametresiz sorgu:")
r = requests.get(url, headers=headers, timeout=5)
print(f"   Status: {r.status_code}")
print(f"   Response: {r.text[:200]}")

# Test 2: city_name parametresiyle
print("\n2️⃣ city_name='Ankara':")
r = requests.get(url, params={"city_name": "Ankara"}, headers=headers, timeout=5)
print(f"   Status: {r.status_code}")
data = r.json() if r.status_code == 200 else None
if isinstance(data, dict):
    print(f"   Keys: {list(data.keys())}")
    print(f"   Result count: {len(data.get('result', []))}")
    if data.get('result'):
        print(f"   First item: {str(data['result'][0])[:150]}")
elif isinstance(data, list):
    print(f"   Array count: {len(data)}")
    if data:
        print(f"   First item: {str(data[0])[:150]}")
else:
    print(f"   Response: {str(data)[:200]}")

# Test 3: sadece city (parametresi olmadan)
print("\n3️⃣ city='Ankara':")
r = requests.get(url, params={"city": "Ankara"}, headers=headers, timeout=5)
print(f"   Status: {r.status_code}")
data = r.json() if r.status_code == 200 else None
print(f"   Data type: {type(data).__name__}")
if isinstance(data, dict) and 'result' in data:
    print(f"   Result count: {len(data.get('result', []))}")

print("\n" + "=" * 70)
print("🔬 API 2 GERÇEK TEST")
print("=" * 70)

key2 = config["rapidapi_key_2"]
url2 = "https://nobetci-eczane-listesi-api-her-saat-otomatik-guncellenir.p.rapidapi.com/pharmacies/Ankara/Cankaya"
headers2 = {
    "x-rapidapi-key": key2,
    "x-rapidapi-host": "nobetci-eczane-listesi-api-her-saat-otomatik-guncellenir.p.rapidapi.com"
}

print(f"\n1️⃣ URL: {url2}")
r = requests.get(url2, headers=headers2, timeout=5)
print(f"   Status: {r.status_code}")
print(f"   Content-Type: {r.headers.get('content-type')}")
print(f"   Response preview: {r.text[:300]}")

if r.status_code == 200:
    try:
        data = r.json()
        print(f"   JSON type: {type(data).__name__}")
        if isinstance(data, dict):
            print(f"   Keys: {list(data.keys())}")
        elif isinstance(data, list):
            print(f"   Array length: {len(data)}")
    except:
        print(f"   JSON decode failed")

