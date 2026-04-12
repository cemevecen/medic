"""
İTS (İlaç Takip Sistemi) API Entegrasyonu

Sağlık Bakanlığı'nın resmi İlaç Takip Sistemi üzerinden:
- Ilaç bilgileri (ticari ad, etken madde, fiyat, onay durumu)
- Barkod taraması
- Uyarı ve geri çekme listeleri

Kaynak: https://its.gov.tr/
"""

import requests
from typing import Dict, List, Optional
import json
from datetime import datetime


class ITSAPI:
    """İTS API istemcisi"""

    # ITS Resmi Endpoint
    BASE_URL = "https://api.its.gov.tr"

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: İTS API anahtarı (Sağlık Bakanlığı'ndan temin edilir)
        """
        self.api_key = api_key
        self.session = requests.Session()

    def search_medicine(self, query: str, limit: int = 10) -> Dict:
        """
        İlaç ara (ticari ad, etken madde, barkod)

        Args:
            query: Arama terimi (ilaç adı, etken madde, vs.)
            limit: Maksimum sonuç sayısı

        Returns:
            {
                "success": bool,
                "total": int,
                "data": [
                    {
                        "id": str,
                        "trade_name": "Ticari Ad",
                        "active_ingredient": "Etken Madde",
                        "dosage": "Doz",
                        "form": "Form",
                        "barcode": "8699282...",
                        "manufacturer": "Üretici",
                        "price_tl": 123.45,
                        "approval_status": "Approved/Warning/Recalled",
                        "approval_date": "2024-01-01",
                        "last_updated": "2024-04-12"
                    }
                ],
                "error": str
            }
        """
        return {
            "success": False,
            "error": "ITS API bağlantısı şu anda yapılandırılmadı. Sağlık Bakanlığı API key gereklidir.",
            "info": "API key almak için: https://its.gov.tr/ adresinden başvuru yapınız."
        }

    def get_medicine_by_barcode(self, barcode: str) -> Dict:
        """
        Barkod ile ilaç bilgisi

        Args:
            barcode: 12-13 haneli ilaç barkodu

        Returns:
            İlaç bilgileri dict'i
        """
        return {
            "success": False,
            "error": "ITS API bağlantısı yapılandırılmadı"
        }

    def get_recalled_medicines(self) -> Dict:
        """
        Geri çekilen (resmi uyarı) ilaçlar listesi

        Returns:
            {
                "success": bool,
                "total": int,
                "data": [
                    {
                        "trade_name": "İlaç Adı",
                        "reason": "Geri çekim nedeni",
                        "recall_date": "2024-04-10",
                        "status": "Active/Resolved"
                    }
                ]
            }
        """
        return {
            "success": False,
            "error": "ITS API bağlantısı yapılandırılmadı"
        }

    def get_price_history(self, trade_name: str) -> Dict:
        """
        İlacın fiyat geçmişi

        Args:
            trade_name: İlaç ticari adı

        Returns:
            Fiyat geçmişi
        """
        return {
            "success": False,
            "error": "ITS API bağlantısı yapılandırılmadı"
        }

    def configure_api_key(self, api_key: str) -> bool:
        """
        API key'i yapılandır ve test et

        Returns:
            Bağlantı başarılı ise True
        """
        self.api_key = api_key

        try:
            # Test connection
            headers = {"Authorization": f"Bearer {api_key}"}
            response = self.session.get(
                f"{self.base_url}/health",
                headers=headers,
                timeout=5
            )

            return response.status_code == 200

        except Exception as e:
            print(f"API test hatası: {str(e)}")
            return False


# Singleton instance
_its_api = None

def init_its_api(api_key: Optional[str] = None) -> ITSAPI:
    """İTS API'yi başlat"""
    global _its_api
    _its_api = ITSAPI(api_key=api_key)
    return _its_api

def search_medicine(query: str, limit: int = 10) -> Dict:
    """İlaç ara"""
    if _its_api is None:
        init_its_api()
    return _its_api.search_medicine(query, limit)

def get_recalled_medicines() -> Dict:
    """Geri çekilen ilaçlar"""
    if _its_api is None:
        init_its_api()
    return _its_api.get_recalled_medicines()


# ═════════════════════════════════════════════
# DEMO VERİSİ (API key olmadan test için)
# ═════════════════════════════════════════════

DEMO_MEDICINES = [
    {
        "id": "its_001",
        "trade_name": "Aspirin 500mg",
        "active_ingredient": "Asetilsalisilik Asit",
        "dosage": "500mg",
        "form": "Tablet",
        "barcode": "8699282001234",
        "manufacturer": "Bayer Türk",
        "price_tl": 2.45,
        "approval_status": "Approved",
        "approval_date": "1990-05-15",
        "last_updated": "2024-03-20",
        "usage": "Ağrı, ateş, enflamasyon"
    },
    {
        "id": "its_002",
        "trade_name": "Parol 500mg",
        "active_ingredient": "Parasetamol",
        "dosage": "500mg",
        "form": "Tablet",
        "barcode": "8699282004567",
        "manufacturer": "Atabay",
        "price_tl": 1.89,
        "approval_status": "Approved",
        "approval_date": "1992-01-10",
        "last_updated": "2024-03-22",
        "usage": "Ağrı, ateş"
    },
    {
        "id": "its_003",
        "trade_name": "Augmentin 500/125",
        "active_ingredient": "Amoksisilin/Klavulanik Asit",
        "dosage": "500/125mg",
        "form": "Tablet",
        "barcode": "8699282007890",
        "manufacturer": "GSK",
        "price_tl": 12.50,
        "approval_status": "Approved",
        "approval_date": "1988-06-20",
        "last_updated": "2024-04-01",
        "usage": "Enfeksiyon tedavisi (antibiyotik)"
    },
    {
        "id": "its_004",
        "trade_name": "İbuprofen 400mg",
        "active_ingredient": "İbuprofen",
        "dosage": "400mg",
        "form": "Tablet",
        "barcode": "8699282012345",
        "manufacturer": "Roche",
        "price_tl": 3.25,
        "approval_status": "Approved",
        "approval_date": "1995-03-15",
        "last_updated": "2024-03-28",
        "usage": "Ağrı, ateş, enflamasyon"
    }
]

RECALLED_MEDICINES = [
    {
        "trade_name": "Örnek İlaç A",
        "reason": "Bilinmeyen kontaminasyon",
        "recall_date": "2024-03-15",
        "status": "Active",
        "details": "Üretim hatası sebebiyle geri çekilmiştir"
    }
]


def get_demo_medicines(query: str) -> Dict:
    """Demo veri - ITS API key olmadan test için"""

    query_lower = query.lower().strip()

    results = [
        med for med in DEMO_MEDICINES
        if query_lower in med["trade_name"].lower()
        or query_lower in med["active_ingredient"].lower()
        or query_lower in med.get("usage", "").lower()
    ]

    return {
        "success": len(results) > 0,
        "total": len(results),
        "data": results,
        "source": "DEMO (Test Verisi)",
        "note": "Bu veriler örnek amaçlıdır. Gerçek API integrasyonu için ITS API key gereklidir."
    }
