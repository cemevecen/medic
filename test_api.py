#!/usr/bin/env python3
"""API'leri test et ve kontrol et"""

import json
import sys
from pathlib import Path

# Config'i yükle
CONFIG_PATH = Path(__file__).parent / "config_api.json"
if not CONFIG_PATH.exists():
    print("❌ config_api.json bulunamadı")
    sys.exit(1)

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

rapidapi_endpoint_1 = config.get("rapidapi_endpoint_1", "").strip()
rapidapi_key_1 = config.get("rapidapi_key_1", "").strip()
rapidapi_endpoint_2 = config.get("rapidapi_endpoint_2", "").strip()
rapidapi_key_2 = config.get("rapidapi_key_2", "").strip()
rapidapi_endpoint_3 = config.get("rapidapi_endpoint_3", "").strip()
rapidapi_key_3 = config.get("rapidapi_key_3", "").strip()
collectapi_key = config.get("collectapi_api_key", "").strip()

print("=" * 60)
print("🧪 API TEST")
print("=" * 60)

# RapidAPI 1 test
print("\n📌 API 1: Nöbetçi Eczaneler - Türkiye")
print(f"   Endpoint: {rapidapi_endpoint_1[:50]}...")
print(f"   Key: {'*' * 20}...")

if rapidapi_endpoint_1 and rapidapi_key_1:
    import requests
    try:
        # Test: Ankara/Çankaya
        params = {"city_name": "Ankara", "district_name": "Çankaya"}
        headers = {
            "x-rapidapi-key": rapidapi_key_1,
            "x-rapidapi-host": rapidapi_endpoint_1.split("//")[1].split("/")[0],
        }

        response = requests.get(
            rapidapi_endpoint_1,
            params=params,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            results = data if isinstance(data, list) else data.get("result", [])
            print(f"   ✓ Çalışıyor! {len(results)} eczane bulundu (Ankara/Çankaya)")
            if results and len(results) > 0:
                print(f"     → İlk: {results[0].get('name', 'N/A')}")
        else:
            print(f"   ❌ HTTP {response.status_code}: {response.text[:100]}")
    except Exception as e:
        print(f"   ❌ Hata: {str(e)}")
else:
    print("   ⚠️  Endpoint veya key yok")

# RapidAPI 2 test
print("\n📌 API 2: Nöbetçi Eczane Listesi")
print(f"   Endpoint: {rapidapi_endpoint_2[:50]}...")
print(f"   Key: {'*' * 20}...")

if rapidapi_endpoint_2 and rapidapi_key_2:
    import requests
    try:
        # Test: Mersin/Anamur
        url = rapidapi_endpoint_2.replace("{city}", "mersin").replace("{district}", "anamur")
        headers = {
            "x-rapidapi-key": rapidapi_key_2,
            "x-rapidapi-host": rapidapi_endpoint_2.split("//")[1].split("/")[0],
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            results = data if isinstance(data, list) else data.get("result", data.get("data", []))
            print(f"   ✓ Çalışıyor! {len(results)} eczane bulundu (Mersin/Anamur)")
            if results and len(results) > 0:
                print(f"     → İlk: {results[0].get('name', 'N/A')}")
        else:
            print(f"   ❌ HTTP {response.status_code}: {response.text[:100]}")
    except Exception as e:
        print(f"   ❌ Hata: {str(e)}")
else:
    print("   ⚠️  Endpoint veya key yok")

# Integration test
print("\n📌 Integration Test (nobetci_eczane.py)")
try:
    from nobetci_eczane import init_nobetci_api, get_nobetci_eczaneler

    # API'yi init et
    init_nobetci_api(
        api_key=collectapi_key,
        rapidapi_endpoint_1=rapidapi_endpoint_1,
        rapidapi_key_1=rapidapi_key_1,
        rapidapi_endpoint_2=rapidapi_endpoint_2,
        rapidapi_key_2=rapidapi_key_2,
        rapidapi_endpoint_3=rapidapi_endpoint_3,
        rapidapi_key_3=rapidapi_key_3,
    )

    # Test 1: Ankara
    result = get_nobetci_eczaneler("Ankara", "Çankaya")
    if result.get("success"):
        print(f"   ✓ Ankara/Çankaya: {result.get('total')} eczane (Kaynak: {result.get('source')})")
    else:
        print(f"   ❌ Ankara/Çankaya: {result.get('error')}")

    # Test 2: Mersin
    result = get_nobetci_eczaneler("Mersin", "Anamur")
    if result.get("success"):
        print(f"   ✓ Mersin/Anamur: {result.get('total')} eczane (Kaynak: {result.get('source')})")
    else:
        print(f"   ❌ Mersin/Anamur: {result.get('error')}")

    # Test 3: Demo data fallback
    result = get_nobetci_eczaneler("İstanbul", "Maslak")
    if result.get("success"):
        print(f"   ✓ İstanbul/Maslak: {result.get('total')} eczane (Kaynak: {result.get('source')})")
    else:
        print(f"   ❌ İstanbul/Maslak: {result.get('error')}")

except Exception as e:
    import traceback
    print(f"   ❌ Integration hatası: {str(e)}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("✅ Test tamamlandı")
print("=" * 60)
