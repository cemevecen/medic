"""
ECZANE FİYAT KARŞILAŞTIRMASI
pharmacy_prices.py: Türk eczanelerinden canlı fiyat çekme, karşılaştırma ve coğrafi filtreleme

Veri kaynakları:
- Simulated Turkish pharmacy data (can be replaced with real APIs)
- Geolocation-based filtering
- Price comparison engine
"""

import json
import math
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import random

# ─────────────────────────────────────────────
# MOCK PHARMACY DATA (Gerçek veriyle değiştirebilir)
# ─────────────────────────────────────────────

TURKISH_PHARMACIES = [
    # İstanbul Eczaneleri
    {
        "id": "eczane_001",
        "name": "Acibadem Eczanesi",
        "city": "İstanbul",
        "district": "Maslak",
        "latitude": 41.1056,
        "longitude": 29.0137,
        "phone": "+90 212 XXX XXXX",
        "working_hours": "09:00-22:00",
        "open_24h": False,
    },
    {
        "id": "eczane_002",
        "name": "Nöbetçi Eczanesi",
        "city": "İstanbul",
        "district": "Beşiktaş",
        "latitude": 41.0520,
        "longitude": 29.0087,
        "phone": "+90 212 XXX XXXX",
        "working_hours": "24 Saat Açık",
        "open_24h": True,
    },
    {
        "id": "eczane_003",
        "name": "Sağlık Eczanesi",
        "city": "İstanbul",
        "district": "Kadıköy",
        "latitude": 40.9942,
        "longitude": 29.0284,
        "phone": "+90 216 XXX XXXX",
        "working_hours": "08:00-21:00",
        "open_24h": False,
    },
    {
        "id": "eczane_004",
        "name": "Merkez Eczanesi",
        "city": "İstanbul",
        "district": "Şişli",
        "latitude": 41.0737,
        "longitude": 29.0213,
        "phone": "+90 212 XXX XXXX",
        "working_hours": "08:00-22:00",
        "open_24h": False,
    },
    # Ankara Eczaneleri
    {
        "id": "eczane_005",
        "name": "Altındağ Eczanesi",
        "city": "Ankara",
        "district": "Altındağ",
        "latitude": 39.9333,
        "longitude": 32.8654,
        "phone": "+90 312 XXX XXXX",
        "working_hours": "09:00-21:00",
        "open_24h": False,
    },
    {
        "id": "eczane_006",
        "name": "Çankaya Nöbetçi",
        "city": "Ankara",
        "district": "Çankaya",
        "latitude": 39.8869,
        "longitude": 32.8654,
        "phone": "+90 312 XXX XXXX",
        "working_hours": "24 Saat Açık",
        "open_24h": True,
    },
    # İzmir Eczaneleri
    {
        "id": "eczane_007",
        "name": "Alsancak Eczanesi",
        "city": "İzmir",
        "district": "Alsancak",
        "latitude": 38.4444,
        "longitude": 27.1408,
        "phone": "+90 232 XXX XXXX",
        "working_hours": "08:00-21:00",
        "open_24h": False,
    },
    {
        "id": "eczane_008",
        "name": "Bornova Eczanesi",
        "city": "İzmir",
        "district": "Bornova",
        "latitude": 38.4644,
        "longitude": 27.2164,
        "phone": "+90 232 XXX XXXX",
        "working_hours": "09:00-22:00",
        "open_24h": False,
    },
]


def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Haversine formülü ile iki konum arasındaki mesafeyi km cinsinden hesapla
    """
    R = 6371  # Dünya yarıçapı (km)

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return R * c


def _simulate_pharmacy_price(drug_name: str, pharmacy_id: str) -> Optional[Dict]:
    """
    Mock: Eczane için simüle edilmiş fiyat verisi oluştur
    Gerçek sistemde API çağrısı yapılacak
    """
    # Base price simulation
    base_price = 15.0 + (hash(drug_name) % 100)

    # Her eczane farklı fiyat sunabilir (±%20)
    price_variance = 0.8 + (hash(pharmacy_id + drug_name) % 40) / 100
    final_price = base_price * price_variance

    # Stok durumu
    in_stock = random.choice([True, True, True, False])  # %75 stokta olma ihtimali

    return {
        "pharmacy_id": pharmacy_id,
        "drug_name": drug_name,
        "price": round(final_price, 2),
        "currency": "TL",
        "in_stock": in_stock,
        "last_updated": datetime.now().isoformat(),
        "estimated_delivery": "30 dakika" if in_stock else "1-2 gün",
    }


def get_pharmacy_prices(
    drug_name: str,
    user_latitude: Optional[float] = None,
    user_longitude: Optional[float] = None,
    max_distance_km: float = 10.0,
    limit: int = 5,
) -> Dict:
    """
    İlaç adı ve konum bilgisine göre eczane fiyatlarını getir

    Args:
        drug_name: İlaç adı (ör: "Aspirin 500mg")
        user_latitude: Kullanıcı enlem koordinatı
        user_longitude: Kullanıcı boylam koordinatı
        max_distance_km: Maksimum arama mesafesi (km)
        limit: En fazla kaç eczane gösterilsin

    Returns:
        Dict: Fiyat bilgileri, mesafeler ve sıralama
    """

    if not drug_name or not drug_name.strip():
        return {
            "success": False,
            "error": "İlaç adı boş olamaz",
            "results": []
        }

    results = []

    # Tüm eczaneleri kontrol et
    for pharmacy in TURKISH_PHARMACIES:
        # Konum filtresi
        if user_latitude is not None and user_longitude is not None:
            distance = _calculate_distance(
                user_latitude,
                user_longitude,
                pharmacy["latitude"],
                pharmacy["longitude"]
            )

            # Maksimum mesafeyi aşarsa atla
            if distance > max_distance_km:
                continue
        else:
            distance = None

        # Fiyat bilgisi çek
        price_info = _simulate_pharmacy_price(drug_name, pharmacy["id"])

        # Sonuç oluştur
        result = {
            **pharmacy,
            **price_info,
            "distance_km": round(distance, 2) if distance else None,
            "is_nearby": (distance is not None and distance < 2) if distance else False,
        }

        results.append(result)

    # Fiyatla sırala (en ucuz önce)
    results.sort(key=lambda x: (not x["in_stock"], x["price"]))

    # Limitle
    results = results[:limit]

    if not results:
        return {
            "success": False,
            "error": f"Yakın eczanelerde '{drug_name}' bulunamadı",
            "results": []
        }

    return {
        "success": True,
        "drug_name": drug_name,
        "total_found": len(results),
        "cheapest_price": results[0]["price"],
        "cheapest_pharmacy": results[0]["name"],
        "price_range": {
            "min": round(results[0]["price"], 2),
            "max": round(results[-1]["price"], 2),
            "average": round(sum(r["price"] for r in results) / len(results), 2),
        },
        "results": results
    }


def filter_pharmacies_by_city(city: str) -> List[Dict]:
    """Şehre göre eczane listesi filtrele"""
    return [p for p in TURKISH_PHARMACIES if p["city"].lower() == city.lower()]


def filter_pharmacies_24h() -> List[Dict]:
    """Sadece 24 saat açık eczaneleri göster"""
    return [p for p in TURKISH_PHARMACIES if p["open_24h"]]


def get_nearby_pharmacies(
    latitude: float,
    longitude: float,
    radius_km: float = 2.0
) -> List[Dict]:
    """
    Verilen konuma yakın eczaneleri bul
    """
    nearby = []

    for pharmacy in TURKISH_PHARMACIES:
        distance = _calculate_distance(
            latitude,
            longitude,
            pharmacy["latitude"],
            pharmacy["longitude"]
        )

        if distance <= radius_km:
            nearby.append({
                **pharmacy,
                "distance_km": round(distance, 2)
            })

    # Mesafeye göre sırala
    nearby.sort(key=lambda x: x["distance_km"])
    return nearby


def price_comparison_summary(drug_name: str, prices: Dict) -> str:
    """Fiyat karşılaştırmasının Türkçe özeti oluştur"""

    if not prices["success"]:
        return f"❌ {prices.get('error', 'Veri bulunamadı')}"

    summary = f"""
📊 **{drug_name} — Fiyat Karşılaştırması**

💰 **Fiyat Aralığı:**
- En Ucuz: **{prices['price_range']['min']} TL** ({prices['cheapest_pharmacy']})
- En Pahalı: **{prices['price_range']['max']} TL**
- Ortalama: **{prices['price_range']['average']} TL**

📈 **Tasarruf:** {round(prices['price_range']['max'] - prices['price_range']['min'], 2)} TL farklı eczanelerde

🏪 **Toplam Eczane:** {prices['total_found']} adet
"""
    return summary.strip()


# Test
if __name__ == "__main__":
    # Test 1: Aspirin fiyatları
    result = get_pharmacy_prices(
        drug_name="Aspirin 500mg",
        user_latitude=41.0082,
        user_longitude=28.9784,  # İstanbul Taksim
        max_distance_km=15,
        limit=5
    )

    print("=== Test 1: Aspirin Fiyatları ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Test 2: Özeti
    print("\n" + price_comparison_summary("Aspirin 500mg", result))

    # Test 3: Ankara 24 saat eczaneleri
    eczanes_24h = filter_pharmacies_24h()
    print(f"\n=== 24 Saat Açık Eczaneler: {len(eczanes_24h)} adet ===")
    for eczane in eczanes_24h:
        print(f"  - {eczane['name']} ({eczane['city']}, {eczane['district']})")
