#!/usr/bin/env python3
"""API 1 raw yanıtını debug et - Kehribar eczanesi bulunabilir mi?"""

import requests
import json
from pathlib import Path

# Config yükle
CONFIG_PATH = Path(__file__).parent / "config_api.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

endpoint = config.get("rapidapi_endpoint_1")
api_key = config.get("rapidapi_key_1")

print("=" * 80)
print("🔍 API 1 RAW YANITI DEBUG")
print("=" * 80)
print(f"\nEndpoint: {endpoint}")
print(f"Key: {'*' * 20}...")

headers = {
    "x-rapidapi-key": api_key,
    "x-rapidapi-host": endpoint.split("//")[1].split("/")[0],
}

print(f"\nHosts: {headers['x-rapidapi-host']}")

try:
    response = requests.get(endpoint, headers=headers, timeout=10)
    print(f"\n✓ Status: {response.status_code}")

    data = response.json()

    # Yanıt yapısını kontrol et
    if isinstance(data, dict):
        print(f"\nYanıt tipi: Dictionary")
        print(f"Ana anahtarlar: {list(data.keys())}")

        if "data" in data:
            pharmacies = data["data"]
            print(f"\n📊 Toplam eczane: {len(pharmacies)}")
            print("\n🏥 Tüm Eczaneler:")
            print("-" * 80)
            for i, pharmacy in enumerate(pharmacies, 1):
                name = pharmacy.get("name", "N/A")
                city = pharmacy.get("city", "N/A")
                if isinstance(city, dict):
                    city = city.get("name", "N/A")
                district = pharmacy.get("district", "N/A")
                if isinstance(district, dict):
                    district = district.get("name", "N/A")
                address = pharmacy.get("address", "N/A")

                print(f"\n{i}. {name}")
                print(f"   Şehir: {city}")
                print(f"   İlçe: {district}")
                print(f"   Adres: {address[:60]}..." if len(str(address)) > 60 else f"   Adres: {address}")

                # Kehribar'ı ara
                if "kehribar" in name.lower() or "kehribar" in address.lower():
                    print("   ⭐ KEHRIBAR ECZANESI BULUNDU!")
        else:
            print("\n❌ 'data' anahtarı bulunamadı")
            print(f"Yanıt: {json.dumps(data, indent=2)[:500]}")
    elif isinstance(data, list):
        print(f"\nYanıt tipi: List")
        print(f"Toplam eczane: {len(data)}")

except Exception as e:
    print(f"\n❌ Hata: {str(e)}")
