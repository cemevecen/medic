"""
Nöbetçi Eczane Sistemi Entegrasyonu

Türkiye'deki nöbetçi (gece/hafta sonu açık) eczaneleri bulur ve yakın olanları gösterir.

Kaynaklar:
- CollectAPI: https://collectapi.com/tr/api/health/nobetci-eczane-api
- Eczaneler.ORG: https://eczaneler.org/nobetci-eczane-api-docs
- RapidAPI/NosyAPI: https://rapidapi.com/nosyapi/api/nobetci-eczane-api-turkiye/
"""

import requests
from typing import Dict, List, Optional, Tuple
import json


class NobetciEczaneAPI:
    """Nöbetçi Eczane API istemcisi"""

    # CollectAPI (Free tier) endpoint
    COLLECTAPI_BASE = "https://api.collectapi.com/health"

    def __init__(self, api_key: Optional[str] = None, source: str = "collectapi"):
        """
        Args:
            api_key: API anahtarı (CollectAPI veya Eczaneler.ORG için)
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
                "data": [
                    {
                        "name": "Eczane Adı",
                        "address": "Adres",
                        "phone": "Telefon",
                        "city": "İl",
                        "district": "İlçe",
                        "latitude": 40.123,
                        "longitude": 29.456
                    },
                    ...
                ],
                "error": str (error varsa)
            }
        """
        try:
            if self.source == "collectapi":
                return self._get_collectapi(il, ilce)
            elif self.source == "eczaneler_org":
                return self._get_eczaneler_org(il, ilce)
            elif self.source == "rapidapi":
                return self._get_rapidapi(il, ilce)
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

        # CollectAPI endpoint
        url = f"{self.collectapi_base}/dutyPharmacy"

        params = {"city": il}
        if ilce:
            params["district"] = ilce

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"apikey {self.api_key}" if self.api_key else ""
        }

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
                    "error": f"HTTP {response.status_code}"
                }

        except requests.exceptions.Timeout:
            return {"success": False, "error": "İstek zaman aşımı"}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Ağ hatası: {str(e)}"}

    def _get_eczaneler_org(self, il: str, ilce: Optional[str] = None) -> Dict:
        """Eczaneler.ORG API üzerinden nöbetçi eczaneler"""

        if not self.api_key:
            return {
                "success": False,
                "error": "Eczaneler.ORG için API key gerekli"
            }

        url = "https://api.eczaneler.org/v1/pharmacies/on-duty"

        params = {"city": il}
        if ilce:
            params["district"] = ilce

        headers = {
            "X-Api-Key": self.api_key,
            "Accept": "application/json"
        }

        try:
            response = self.session.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "total": len(data.get("data", [])),
                    "data": data.get("data", []),
                    "source": "Eczaneler.ORG"
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                }

        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Ağ hatası: {str(e)}"}

    def _get_rapidapi(self, il: str, ilce: Optional[str] = None) -> Dict:
        """RapidAPI/NosyAPI üzerinden nöbetçi eczaneler"""

        if not self.api_key:
            return {
                "success": False,
                "error": "RapidAPI/NosyAPI için API key gerekli"
            }

        url = "https://nobetci-eczane-api-turkiye.p.rapidapi.com/data"

        querystring = {"il": il}
        if ilce:
            querystring["ilce"] = ilce

        headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "nobetci-eczane-api-turkiye.p.rapidapi.com"
        }

        try:
            response = self.session.get(url, params=querystring, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "total": len(data),
                    "data": data,
                    "source": "RapidAPI/NosyAPI"
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                }

        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Ağ hatası: {str(e)}"}

    def nearby_pharmacies(self, lat: float, lon: float, radius_km: float = 5) -> Dict:
        """
        Belirli koordinatlara yakın nöbetçi eczaneleri bulur

        Args:
            lat: Enlem
            lon: Boylam
            radius_km: Arama yarıçapı (km)
        """
        # Not: Bu fonksiyon API tarafından desteklenmeyebilir
        # Clientside distance hesaplaması gerekebilir
        return {
            "success": False,
            "error": "GPS bazlı arama şu anda desteklenmiyor. İl/ilçe seçimi kullanın."
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


# Singleton instance
_api = None

def init_nobetci_api(api_key: Optional[str] = None, source: str = "collectapi"):
    """Nöbetçi Eczane API'yi başlat"""
    global _api
    _api = NobetciEczaneAPI(api_key=api_key, source=source)

def get_nobetci_eczaneler(il: str, ilce: Optional[str] = None) -> Dict:
    """Nöbetçi eczaneleri getir"""
    if _api is None:
        init_nobetci_api()
    return _api.get_nobetci_eczaneler(il, ilce)
