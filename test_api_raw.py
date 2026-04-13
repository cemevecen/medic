import requests
import json

# Config yükle
with open("config_api.json", "r") as f:
    config = json.load(f)

endpoint1 = config["rapidapi_endpoint_1"]
key1 = config["rapidapi_key_1"]
host1 = endpoint1.split("//")[1].split("/")[0]

# API 1 - Farklı parametre isimleri dene
print("🔍 API 1 Test - Parametre Kombinasyonları")
print("=" * 60)

params_list = [
    {"city_name": "Ankara", "district_name": "Çankaya"},
    {"city": "Ankara", "district": "Çankaya"},
    {"il": "Ankara", "ilçe": "Çankaya"},
]

for params in params_list:
    try:
        headers = {"x-rapidapi-key": key1, "x-rapidapi-host": host1}
        r = requests.get(endpoint1, params=params, headers=headers, timeout=5)
        results = r.json() if r.status_code == 200 else None
        count = len(results) if isinstance(results, list) else (len(results.get("result", [])) if isinstance(results, dict) else 0)
        print(f"✓ {params} → {count} eczane (HTTP {r.status_code})")
    except Exception as e:
        print(f"✗ {params} → {str(e)[:50]}")

# API 2 - URL format test
print("\n🔍 API 2 Test - URL Format")
print("=" * 60)

endpoint2 = config["rapidapi_endpoint_2"]
key2 = config["rapidapi_key_2"]
host2 = endpoint2.split("//")[1].split("/")[0]

urls = [
    endpoint2.replace("{city}", "ankara").replace("{district}", "çankaya"),
    endpoint2.replace("{city}", "Ankara").replace("{district}", "Çankaya"),
    endpoint2.format(city="ankara", district="çankaya"),
]

for url in urls:
    try:
        headers = {"x-rapidapi-key": key2, "x-rapidapi-host": host2}
        r = requests.get(url, headers=headers, timeout=5)
        data = r.json() if r.status_code == 200 else None
        count = len(data) if isinstance(data, list) else (len(data.get("result", data.get("data", []))) if isinstance(data, dict) else 0)
        print(f"✓ {url.split('/')[-2:]}) → {count} eczane (HTTP {r.status_code})")
    except Exception as e:
        print(f"✗ {url[:50]}... → {str(e)[:30]}")

