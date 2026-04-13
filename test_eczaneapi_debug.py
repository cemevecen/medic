#!/usr/bin/env python3
"""EczaneAPI raw response debug"""

import requests
import json

api_key = "eczane_api_588b13b6e3e05fab1e25a88be0ae775f59995fe01a80979a"
base_url = "https://eczaneapi.com/api/v1"

headers = {"X-API-Key": api_key}

print("Testing: Ankara/Çankaya")
response = requests.get(
    f"{base_url}/pharmacies/on-duty",
    params={"city": "ankara", "district": "çankaya"},
    headers=headers,
    timeout=10
)

print(f"Status: {response.status_code}")
data = response.json()

print(f"\nData type: {type(data)}")
print(f"Data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")

print("\nFull response (first 1000 chars):")
print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
