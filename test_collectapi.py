#!/usr/bin/env python3
"""CollectAPI'yi test et - Kehribar'ı bulabilir mi?"""

import requests
import json
from pathlib import Path

# Config yükle
CONFIG_PATH = Path(__file__).parent / "config_api.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

api_key = config.get("collectapi_api_key")

print("=" * 80)
print("🔍 COLLECTAPI TEST - KEHRIBAR ARAYIŞI")
print("=" * 80)

if not api_key:
    print("\n❌ CollectAPI key tanımlanmadı")
    exit(1)

print(f"\nAPI Key: {'*' * 20}...")

# Test cities
test_cities = ["Ankara", "İstanbul", "İzmir"]

for city in test_cities:
    print(f"\n{'='*80}")
    print(f"📍 {city} test ediliyor...")
    print("-" * 80)

    url = "https://api.collectapi.com/health/dutyPharmacy"
    params = {"il": city}
    headers = {"Authorization": f"apikey {api_key}"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            if data.get("success"):
                pharmacies = data.get("result", [])
                print(f"✓ {len(pharmacies)} eczane bulundu")

                # Kehribar'ı ara
                for pharmacy in pharmacies[:5]:  # İlk 5'i göster
                    name = pharmacy.get("name", "N/A")
                    address = pharmacy.get("address", "N/A")

                    print(f"\n  • {name}")
                    print(f"    Adres: {address[:70]}...")

                    if "kehribar" in name.lower() or "kehribar" in address.lower():
                        print("    ⭐ KEHRIBAR BULUNDU!")
            else:
                print(f"❌ API Error: {data.get('message')}")
        else:
            print(f"❌ HTTP {response.status_code}: {response.text[:200]}")

    except Exception as e:
        print(f"❌ Hata: {str(e)}")
