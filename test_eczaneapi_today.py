#!/usr/bin/env python3
"""EczaneAPI - Bugün'ün nöbetçileri"""

import requests
import json
from datetime import date

api_key = "eczane_api_588b13b6e3e05fab1e25a88be0ae775f59995fe01a80979a"
base_url = "https://eczaneapi.com/api/v1"

headers = {"X-API-Key": api_key}

today = str(date.today())  # 2026-04-13

print("=" * 80)
print(f"🧪 ECZANEAPI - BUGÜN ({today})")
print("=" * 80)

# Test: Ankara/Çankaya - Bugün
print(f"\n📍 Ankara/Çankaya ({today})")
response = requests.get(
    f"{base_url}/pharmacies/on-duty",
    params={
        "city": "ankara",
        "district": "çankaya",
        "date": today
    },
    headers=headers,
    timeout=10
)

if response.status_code == 200:
    data = response.json()

    if data.get("success") and data.get("data"):
        # data bir array, ilk element bugünün nöbetçileri
        today_data = data["data"][0] if isinstance(data["data"], list) else data["data"]

        day_label = today_data.get("day", "")
        count = today_data.get("count", 0)
        date_str = today_data.get("date", "")
        pharmacies = today_data.get("pharmacies", [])

        print(f"Gün: {day_label} ({date_str})")
        print(f"✓ {count} eczane bulundu")

        if pharmacies:
            print("\nİlk 3 eczane:")
            for i, p in enumerate(pharmacies[:3], 1):
                print(f"  {i}. {p.get('name')}")
                print(f"     Tel: {p.get('phone')}")
                print(f"     Adres: {p.get('address')[:60]}...")
                print(f"     Koordinat: {p.get('location')}")
                print(f"     Verified: {p.get('duty', {}).get('isVerified')}")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text[:300])

# Test 2: İstanbul - Bugün
print("\n" + "=" * 80)
print(f"📍 İstanbul ({today})")
response = requests.get(
    f"{base_url}/pharmacies/on-duty",
    params={
        "city": "istanbul",
        "date": today
    },
    headers=headers,
    timeout=10
)

if response.status_code == 200:
    data = response.json()
    if data.get("success") and data.get("data"):
        today_data = data["data"][0] if isinstance(data["data"], list) else data["data"]
        count = today_data.get("count", 0)
        print(f"✓ {count} eczane bulundu (İstanbul)")
else:
    print(f"❌ Error: {response.status_code}")
