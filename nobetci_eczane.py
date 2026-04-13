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


def get_districts_for_city(il: str) -> List[str]:
    """Belirli il için mevcut ilçeleri döndür (demo + gerçek veri)"""
    # İl adını normalize et
    il_normalized = (
        il.replace("İ", "i").replace("Ş", "s").replace("Ç", "c")
          .replace("Ğ", "g").replace("Ü", "u").replace("Ö", "o")
          .lower()
    )

    districts = set()

    # Demo veriden ilçeleri al
    if il_normalized in DEMO_PHARMACIES:
        for pharmacy in DEMO_PHARMACIES[il_normalized]:
            district = pharmacy.get("district", "").strip()
            if district:
                districts.add(district)

    # Fallback: benzer anahtarları ara
    if not districts:
        for key, values in DEMO_PHARMACIES.items():
            if il_normalized.startswith(key[:3]) or key.startswith(il_normalized[:3]):
                for pharmacy in values:
                    district = pharmacy.get("district", "").strip()
                    if district:
                        districts.add(district)
                break

    return sorted(list(districts)) if districts else []


class NobetciEczaneAPI:
    """Nöbetçi Eczane API istemcisi"""

    # CollectAPI endpoint
    COLLECTAPI_BASE = "https://api.collectapi.com/health"

    def __init__(self, api_key: Optional[str] = None, source: str = "collectapi",
                 rapidapi_endpoint_1: Optional[str] = None, rapidapi_key_1: Optional[str] = None,
                 rapidapi_endpoint_2: Optional[str] = None, rapidapi_key_2: Optional[str] = None):
        """
        Args:
            api_key: API anahtarı (CollectAPI için)
            source: Veri kaynağı ("collectapi")
            rapidapi_endpoint_1: RapidAPI 1 endpoint URL
            rapidapi_key_1: RapidAPI 1 API key
            rapidapi_endpoint_2: RapidAPI 2 endpoint URL
            rapidapi_key_2: RapidAPI 2 API key
        """
        self.api_key = api_key
        self.source = source
        self.rapidapi_endpoint_1 = rapidapi_endpoint_1
        self.rapidapi_key_1 = rapidapi_key_1
        self.rapidapi_endpoint_2 = rapidapi_endpoint_2
        self.rapidapi_key_2 = rapidapi_key_2
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
            # Öncelik sırası: RapidAPI 1 → RapidAPI 2 → CollectAPI

            if self.rapidapi_endpoint_1 and self.rapidapi_key_1:
                result = self._get_rapidapi_1(il, ilce)
                if result.get("success"):
                    return result

            if self.rapidapi_endpoint_2 and self.rapidapi_key_2:
                result = self._get_rapidapi_2(il, ilce)
                if result.get("success"):
                    return result

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

    def _get_rapidapi_1(self, il: str, ilce: Optional[str] = None) -> Dict:
        """RapidAPI 1: Nöbetçi Eczaneler - Türkiye"""
        try:
            # Parametreleri hazırla
            params = {"city_name": il}
            if ilce:
                params["district_name"] = ilce

            headers = {
                "x-rapidapi-key": self.rapidapi_key_1,
                "x-rapidapi-host": self._extract_host_from_url(self.rapidapi_endpoint_1),
                "content-type": "application/json"
            }

            response = self.session.get(
                self.rapidapi_endpoint_1,
                params=params,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                # RapidAPI 1 yanıtını standartlaştır
                pharmacies = []
                results = data if isinstance(data, list) else data.get("result", [])

                for item in results:
                    pharmacies.append({
                        "name": item.get("name", item.get("pharmacy_name", "")),
                        "address": item.get("address", item.get("location", "")),
                        "phone": item.get("phone", item.get("phone_number", "")),
                        "city": il,
                        "district": item.get("district", item.get("district_name", ilce or "")),
                        "loc": item.get("loc", item.get("location_coordinates", ""))
                    })

                return {
                    "success": len(pharmacies) > 0,
                    "total": len(pharmacies),
                    "data": pharmacies,
                    "source": "RapidAPI 1"
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "source": "RapidAPI 1"
                }

        except requests.exceptions.Timeout:
            return {"success": False, "error": "RapidAPI 1 zaman aşımı", "source": "RapidAPI 1"}
        except Exception as e:
            return {"success": False, "error": f"RapidAPI 1 hatası: {str(e)}", "source": "RapidAPI 1"}

    def _get_rapidapi_2(self, il: str, ilce: Optional[str] = None) -> Dict:
        """RapidAPI 2: Nöbetçi Eczane Listesi"""
        try:
            # URL'deki placeholder'ları değiştir
            url = self.rapidapi_endpoint_2.replace("{city}", il.lower()).replace("{district}", ilce.lower() if ilce else "")

            headers = {
                "x-rapidapi-key": self.rapidapi_key_2,
                "x-rapidapi-host": self._extract_host_from_url(self.rapidapi_endpoint_2),
                "content-type": "application/json"
            }

            response = self.session.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()

                # RapidAPI 2 yanıtını standartlaştır
                pharmacies = []
                results = data if isinstance(data, list) else data.get("result", data.get("data", []))

                for item in results:
                    pharmacies.append({
                        "name": item.get("name", item.get("pharmacy_name", "")),
                        "address": item.get("address", item.get("location", "")),
                        "phone": item.get("phone", item.get("phone_number", "")),
                        "city": il,
                        "district": item.get("district", ilce or ""),
                        "loc": item.get("loc", item.get("location_coordinates", ""))
                    })

                return {
                    "success": len(pharmacies) > 0,
                    "total": len(pharmacies),
                    "data": pharmacies,
                    "source": "RapidAPI 2"
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "source": "RapidAPI 2"
                }

        except requests.exceptions.Timeout:
            return {"success": False, "error": "RapidAPI 2 zaman aşımı", "source": "RapidAPI 2"}
        except Exception as e:
            return {"success": False, "error": f"RapidAPI 2 hatası: {str(e)}", "source": "RapidAPI 2"}

    def _extract_host_from_url(self, url: str) -> str:
        """URL'den host adını çıkar"""
        if not url:
            return ""
        # https://example.com/path → example.com
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc

    def _get_collectapi(self, il: str, ilce: Optional[str] = None) -> Dict:
        """CollectAPI üzerinden nöbetçi eczaneler"""

        url = f"{self.COLLECTAPI_BASE}/dutyPharmacy"

        # CollectAPI parametreleri: il, ilce
        params = {"il": il}
        if ilce:
            params["ilce"] = ilce

        headers = {
            "content-type": "application/json",
        }

        if self.api_key:
            headers["authorization"] = f"apikey {self.api_key}"
        else:
            return {"success": False, "error": "API key ayarlanmamış"}

        try:
            response = self.session.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if data.get("success"):
                    # CollectAPI yanıtını standardize et
                    pharmacies = []
                    for item in data.get("result", []):
                        pharmacies.append({
                            "name": item.get("name", ""),
                            "address": item.get("address", ""),
                            "phone": item.get("phone", ""),
                            "city": il,
                            "district": item.get("dist", ""),
                            "loc": item.get("loc", "")
                        })

                    return {
                        "success": True,
                        "total": len(pharmacies),
                        "data": pharmacies,
                        "source": "CollectAPI"
                    }
                else:
                    error_msg = data.get("message", data.get("error", "Bilinmeyen API hatası"))
                    return {
                        "success": False,
                        "error": f"API: {error_msg}"
                    }
            else:
                error_detail = response.text[:200] if response.text else "Yanıt yok"
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {error_detail}"
                }

        except requests.exceptions.Timeout:
            return {"success": False, "error": "Zaman aşımı (API yanıt vermiyor)"}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Bağlantı hatası: {str(e)}"}


# Singleton instance
_api = None

def init_nobetci_api(api_key: Optional[str] = None, source: str = "collectapi",
                     rapidapi_endpoint_1: Optional[str] = None, rapidapi_key_1: Optional[str] = None,
                     rapidapi_endpoint_2: Optional[str] = None, rapidapi_key_2: Optional[str] = None):
    """Nöbetçi Eczane API'yi başlat"""
    global _api
    _api = NobetciEczaneAPI(
        api_key=api_key,
        source=source,
        rapidapi_endpoint_1=rapidapi_endpoint_1,
        rapidapi_key_1=rapidapi_key_1,
        rapidapi_endpoint_2=rapidapi_endpoint_2,
        rapidapi_key_2=rapidapi_key_2
    )

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

    # Session state'den RapidAPI bilgilerini al (varsa)
    try:
        import streamlit as st
        rapidapi_endpoint_1 = st.session_state.get("rapidapi_endpoint_1")
        rapidapi_key_1 = st.session_state.get("rapidapi_key_1")
        rapidapi_endpoint_2 = st.session_state.get("rapidapi_endpoint_2")
        rapidapi_key_2 = st.session_state.get("rapidapi_key_2")
        collectapi_api_key = st.session_state.get("collectapi_api_key")
    except:
        rapidapi_endpoint_1 = None
        rapidapi_key_1 = None
        rapidapi_endpoint_2 = None
        rapidapi_key_2 = None
        collectapi_api_key = None

    # Eğer API key varsa gerçek API'yi dene
    # Öncelik: RapidAPI > CollectAPI
    if _api is None:
        # İlk kez çağrılıyorsa API'yi başlat
        init_nobetci_api(
            api_key=collectapi_api_key,
            rapidapi_endpoint_1=rapidapi_endpoint_1,
            rapidapi_key_1=rapidapi_key_1,
            rapidapi_endpoint_2=rapidapi_endpoint_2,
            rapidapi_key_2=rapidapi_key_2
        )
    else:
        # Mevcut API'ye RapidAPI bilgilerini güncelle
        _api.rapidapi_endpoint_1 = rapidapi_endpoint_1
        _api.rapidapi_key_1 = rapidapi_key_1
        _api.rapidapi_endpoint_2 = rapidapi_endpoint_2
        _api.rapidapi_key_2 = rapidapi_key_2
        _api.api_key = collectapi_api_key

    if _api is not None and (
        (_api.rapidapi_endpoint_1 and _api.rapidapi_key_1) or
        (_api.rapidapi_endpoint_2 and _api.rapidapi_key_2) or
        _api.api_key
    ):
        result = _api.get_nobetci_eczaneler(il, ilce)

        if result.get("success"):
            return result
        # API başarısız olursa, demo veriye dön

    # Demo veriye bak
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

    # Demo veri de bulunamadı
    return {
        "success": False,
        "total": 0,
        "data": [],
        "error": f"'{il}' için eczane bulunamadı. API key gerekebilir.",
        "source": "CollectAPI (error)"
    }

def format_pharmacy_result(pharmacy: Dict) -> str:
    """Eczane sonucunu formatla"""
    name = pharmacy.get("name", "Bilinmeyen")
    address = pharmacy.get("address", "Adres bilinmiyor")
    phone = pharmacy.get("phone", "—")
    city = pharmacy.get("city", "")
    district = pharmacy.get("district", "")

    location = f"{city}" if not district else f"{city}/{district}"

    return f"**{name}** ({location})\n📍 {address}\n📞 {phone}"
