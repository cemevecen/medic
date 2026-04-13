#!/usr/bin/env python3
"""EczaneAPI'yi test et"""

import requests
import json

api_key = "eczane_api_588b13b6e3e05fab1e25a88be0ae775f59995fe01a80979a"
base_url = "https://eczaneapi.com/api/v1"

print("=" * 80)
print("🧪 ECZANEAPI TEST")
print("=" * 80)

headers = {"X-API-Key": api_key}

# Test 1: Ankara/Çankaya
print("\n📍 Ankara/Çankaya test ediliyor...")
try:
    response = requests.get(
        f"{base_url}/pharmacies/on-duty",
        params={"city": "ankara", "district": "çankaya"},
        headers=headers,
        timeout=10
    )

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            pharmacies = data.get("data", {}).get("pharmacies", [])
            count = data.get("data", {}).get("count", 0)
            print(f"✓ {count} eczane bulundu")

            if pharmacies:
                print("\nİlk 3 eczane:")
                for i, p in enumerate(pharmacies[:3], 1):
                    print(f"  {i}. {p.get('name')}")
                    print(f"     Tel: {p.get('phone')}")
                    print(f"     Adres: {p.get('address')[:60]}...")
                    if p.get('location'):
                        print(f"     Konum: {p['location']}")
        else:
            print(f"❌ API Error: {data.get('error')}")
    else:
        print(f"❌ HTTP {response.status_code}")
        print(f"Response: {response.text[:200]}")

except Exception as e:
    print(f"❌ Hata: {str(e)}")

# Test 2: İstanbul (tam il)
print("\n" + "=" * 80)
print("📍 İstanbul test ediliyor (ilçe yok)...")
try:
    response = requests.get(
        f"{base_url}/pharmacies/on-duty",
        params={"city": "istanbul"},
        headers=headers,
        timeout=10
    )

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            count = data.get("data", {}).get("count", 0)
            print(f"✓ {count} eczane bulundu (İstanbul)")
        else:
            print(f"❌ API Error: {data.get('error')}")
    else:
        print(f"❌ HTTP {response.status_code}")

except Exception as e:
    print(f"❌ Hata: {str(e)}")

# Test 3: Şehirler listesi
print("\n" + "=" * 80)
print("📍 Şehirler listesi alınıyor...")
try:
    response = requests.get(
        f"{base_url}/cities",
        headers=headers,
        timeout=10
    )

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            cities = data.get("data", [])
            print(f"✓ {len(cities)} şehir bulundu")
            print("\nİlk 5 şehir:")
            for city in cities[:5]:
                print(f"  • {city.get('name')} (slug: {city.get('slug')})")
        else:
            print(f"❌ API Error: {data.get('error')}")
    else:
        print(f"❌ HTTP {response.status_code}")

except Exception as e:
    print(f"❌ Hata: {str(e)}")

print("\n" + "=" * 80)
