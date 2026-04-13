#!/usr/bin/env python3
"""CollectAPI'yi doğrudan NobetciEczaneAPI sınıfı ile test et"""

import json
from pathlib import Path
from nobetci_eczane import NobetciEczaneAPI

# Config yükle
CONFIG_PATH = Path(__file__).parent / "config_api.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

collectapi_key = config.get("collectapi_api_key")

print("=" * 80)
print("🧪 COLLECTAPI DIRECT TEST")
print("=" * 80)

print(f"\nAPI Key: {collectapi_key[:20]}..." if collectapi_key else "❌ No key")

# API oluştur
api = NobetciEczaneAPI(api_key=collectapi_key)

# Test yap
print("\n📍 Ankara/Çankaya test ediliyor...")
result = api._get_collectapi("Ankara", "Çankaya")

print(f"Success: {result.get('success')}")
print(f"Error: {result.get('error')}")
print(f"Source: {result.get('source')}")
print(f"Total: {result.get('total')}")

if result.get('data'):
    print(f"\nİlk 3 eczane:")
    for i, pharmacy in enumerate(result.get('data')[:3], 1):
        print(f"  {i}. {pharmacy['name']}")
        print(f"     Adres: {pharmacy['address'][:60]}...")
