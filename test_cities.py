import requests
import json

with open("config_api.json", "r") as f:
    config = json.load(f)

endpoint1 = config["rapidapi_endpoint_1"]
key1 = config["rapidapi_key_1"]
host1 = endpoint1.split("//")[1].split("/")[0]
headers = {"x-rapidapi-key": key1, "x-rapidapi-host": host1}

# Çeşitli şehirler test et
cities = ["Ankara", "Istanbul", "İstanbul", "Izmir", "İzmir", "Mersin", "Bursa"]

print("🌍 Şehirler Test")
print("=" * 60)

for city in cities:
    try:
        r = requests.get(
            endpoint1,
            params={"city_name": city},
            headers=headers,
            timeout=5
        )
        results = r.json() if isinstance(r.json(), list) else r.json().get("result", [])
        print(f"{city:15} → {len(results):3} eczane")
    except Exception as e:
        print(f"{city:15} → ERROR: {str(e)[:30]}")

