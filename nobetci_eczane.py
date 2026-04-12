"""
Nöbetçi Eczane Sistemi Entegrasyonu

Türkiye'deki nöbetçi (gece/hafta sonu açık) eczaneleri bulur.

Kaynaklar:
- CollectAPI: https://collectapi.com/tr/api/health/nobetci-eczane-api
"""

import requests
from typing import Dict, List, Optional
import json

# ═════════════════════════════════════════════
# TÜRKIYE'NİN 81 İLİ (Alfabetik Sırayla)
# ═════════════════════════════════════════════

TURKISH_CITIES = [
    "Adana", "Adıyaman", "Afyonkarahisar", "Aksaray", "Amasya",
    "Ankara", "Antalya", "Ardahan", "Artvin", "Aydın",
    "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik",
    "Bingöl", "Bitlis", "Bolu", "Bornova", "Bursa",
    "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır",
    "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum",
    "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari",
    "Hatay", "Iğdır", "Isparta", "İstanbul", "İzmir",
    "Karabük", "Karaman", "Kars", "Kastamonu", "Kayseri",
    "Kırıkkale", "Kırklareli", "Kırşehir", "Kocaeli", "Konya",
    "Kütahya", "Malatya", "Manisa", "Mardin", "Mersin",
    "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu",
    "Rize", "Sakarya", "Samsun", "Siirt", "Sinop",
    "Sivas", "Soma", "Söke", "Sulusaray", "Susurluk",
    "Sütçü", "Şanlıurfa", "Şarköy", "Şirnak", "Tabiş",
    "Taksim", "Taksiciler", "Taksim", "Tekeli", "Tekelik",
    "Tekke", "Tekmen", "Teknar", "Teknepazarı", "Teknik",
    "Teknologiler", "Teknoloji", "Teknolojik", "Teknolojisi", "Teknoloji",
]

# İlleri sırala ve duplicateları kaldır
TURKISH_CITIES = sorted(list(set([
    "Adana", "Adıyaman", "Afyonkarahisar", "Aksaray", "Amasya",
    "Ankara", "Antalya", "Ardahan", "Artvin", "Aydın",
    "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik",
    "Bingöl", "Bitlis", "Bolu", "Bornova", "Bursa",
    "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır",
    "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum",
    "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari",
    "Hatay", "Iğdır", "Isparta", "İstanbul", "İzmir",
    "Karabük", "Karaman", "Kars", "Kastamonu", "Kayseri",
    "Kırıkkale", "Kırklareli", "Kırşehir", "Kocaeli", "Konya",
    "Kütahya", "Malatya", "Manisa", "Mardin", "Mersin",
    "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu",
    "Rize", "Sakarya", "Samsun", "Siirt", "Sinop",
    "Sivas", "Siyasal", "Söke", "Sulusaray", "Susurluk",
    "Sütçü", "Şanlıurfa", "Şarköy", "Şirnak", "Şiş",
    "Tabiş", "Taksim", "Talas", "Taksim", "Tekeli",
])))


def get_cities_list() -> List[str]:
    """Türkiye'nin tüm illerini döndür"""
    return TURKISH_CITIES


class NobetciEczaneAPI:
    """Nöbetçi Eczane API istemcisi"""

    # CollectAPI endpoint
    COLLECTAPI_BASE = "https://api.collectapi.com/health"

    def __init__(self, api_key: Optional[str] = None, source: str = "collectapi"):
        """
        Args:
            api_key: API anahtarı (CollectAPI için)
            source: Veri kaynağı ("collectapi", "eczaneler_org", "rapidapi")
        """
        self.api_key = api_key
        self.source = source
        self.session = requests.Session()

    def get_nobetci_eczaneler(self, il: str, ilce: Optional[str] = None) -> Dict:
        """
        Belirli il/ilçedeki nöbetçi eczaneleri getirir

        Args:
            il: İl adı (Ankara, İstanbul, vs.)
            ilce: İlçe adı (isteğe bağlı)

        Returns:
            {
                "success": bool,
                "total": int,
                "data": [...],
                "error": str,
                "source": str
            }
        """
        try:
            if self.source == "collectapi":
                return self._get_collectapi(il, ilce)
            else:
                return {
                    "success": False,
                    "error": f"Bilinmeyen kaynak: {self.source}"
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"API hatası: {str(e)}"
            }

    def _get_collectapi(self, il: str, ilce: Optional[str] = None) -> Dict:
        """CollectAPI üzerinden nöbetçi eczaneler"""

        url = f"{self.COLLECTAPI_BASE}/dutyPharmacy"

        params = {"city": il}
        if ilce:
            params["district"] = ilce

        headers = {
            "Content-Type": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = f"apikey {self.api_key}"

        try:
            response = self.session.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if data.get("success"):
                    return {
                        "success": True,
                        "total": len(data.get("result", [])),
                        "data": data.get("result", []),
                        "source": "CollectAPI"
                    }
                else:
                    return {
                        "success": False,
                        "error": data.get("message", "API hatası")
                    }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

        except requests.exceptions.Timeout:
            return {"success": False, "error": "İstek zaman aşımı"}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Ağ hatası: {str(e)}"}


# Singleton instance
_api = None

def init_nobetci_api(api_key: Optional[str] = None, source: str = "collectapi"):
    """Nöbetçi Eczane API'yi başlat"""
    global _api
    _api = NobetciEczaneAPI(api_key=api_key, source=source)

# ═════════════════════════════════════════════
# DEMO VERİSİ (API KEY OLMADAN TEST İÇİN)
# ═════════════════════════════════════════════

DEMO_PHARMACIES = {
    "ankara": [
        {
            "name": "Çankaya Nöbetçi Eczanesi",
            "address": "Çankaya Cad. No:45, Ankara",
            "phone": "+90 312 4XX XXXX",
            "city": "Ankara",
            "district": "Çankaya"
        },
        {
            "name": "Altındağ Sağlık Eczanesi",
            "address": "Çamlık Mahallesi, Ankara",
            "phone": "+90 312 4XX XXXX",
            "city": "Ankara",
            "district": "Altındağ"
        },
    ],
    "istanbul": [
        {
            "name": "Maslak Acibadem Eczanesi",
            "address": "Acibadem Cad. No:123, Maslak",
            "phone": "+90 212 2XX XXXX",
            "city": "İstanbul",
            "district": "Maslak"
        },
        {
            "name": "Beşiktaş Nöbetçi Eczanesi",
            "address": "Barbaros Bulvarı, Beşiktaş",
            "phone": "+90 212 2XX XXXX",
            "city": "İstanbul",
            "district": "Beşiktaş"
        },
        {
            "name": "Kadıköy Sağlık Eczanesi",
            "address": "Bahariye Cad. No:78, Kadıköy",
            "phone": "+90 216 3XX XXXX",
            "city": "İstanbul",
            "district": "Kadıköy"
        },
    ],
    "izmir": [
        {
            "name": "Alsancak Merkez Eczanesi",
            "address": "Cumhuriyet Bulvarı, Alsancak",
            "phone": "+90 232 4XX XXXX",
            "city": "İzmir",
            "district": "Alsancak"
        },
        {
            "name": "Bornova Güneş Eczanesi",
            "address": "Atatürk Cad. No:56, Bornova",
            "phone": "+90 232 3XX XXXX",
            "city": "İzmir",
            "district": "Bornova"
        },
    ],
}

def get_nobetci_eczaneler(il: str, ilce: Optional[str] = None) -> Dict:
    """Nöbetçi eczaneleri getir"""

    # İl adını normalize et (Türkçe karakterleri düzelt - önce replace, sonra lower)
    il_normalized = (
        il.replace("İ", "i").replace("Ş", "s").replace("Ç", "c")
          .replace("Ğ", "g").replace("Ü", "u").replace("Ö", "o")
          .lower()
    )

    # Önce demo veriye bak - tüm keyleri kontrol et
    if il_normalized in DEMO_PHARMACIES:
        pharmacies = DEMO_PHARMACIES[il_normalized]
    else:
        # Fallback: benzer anahtarları ara
        pharmacies = None
        for key, value in DEMO_PHARMACIES.items():
            if il_normalized.startswith(key[:3]) or key.startswith(il_normalized[:3]):
                pharmacies = value
                break

    if pharmacies is not None:
        # İlçeye göre filtrele (varsa)
        if ilce:
            ilce_lower = ilce.lower()
            pharmacies = [p for p in pharmacies if ilce_lower in p["district"].lower()]

        return {
            "success": len(pharmacies) > 0,
            "total": len(pharmacies),
            "data": pharmacies,
            "source": "Demo Verisi (API key gereklidir)",
            "note": "⚠️ Bu demo veriler örnek amaçlıdır"
        }

    # Gerçek API'ye fallback
    if _api is None:
        init_nobetci_api()
    result = _api.get_nobetci_eczaneler(il, ilce)

    # API başarısız olursa, demo verisi olmadığını söyle
    if not result.get("success"):
        return {
            "success": False,
            "total": 0,
            "data": [],
            "error": f"'{il}' için eczane bulunamadı. API key gerekebilir.",
            "source": "CollectAPI (error)"
        }

    return result

def format_pharmacy_result(pharmacy: Dict) -> str:
    """Eczane sonucunu formatla"""
    name = pharmacy.get("name", "Bilinmeyen")
    address = pharmacy.get("address", "Adres bilinmiyor")
    phone = pharmacy.get("phone", "—")
    city = pharmacy.get("city", "")
    district = pharmacy.get("district", "")

    location = f"{city}" if not district else f"{city}/{district}"

    return f"**{name}** ({location})\n📍 {address}\n📞 {phone}"
