"""
Gerçek ilaç verilerini çeken veri kaynağı
Wikidata, TITCK ve açık veritabanlarından gerçek bilgiler
"""

import requests
import json
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def fetch_drug_from_wikidata(drug_name: str) -> Optional[Dict[str, Any]]:
    """
    Wikidata'dan gerçek ilaç bilgilerini çeker.
    Açık kaynak, API kısıtlaması yok.

    Args:
        drug_name: İlaç adı (Türkçe veya İngilizce)

    Returns:
        İlaç bilgileri dictionary'si veya None
    """
    try:
        # SPARQL sorgusu — Wikidata'da ilaç ara
        query = f"""
        SELECT ?drug ?drugLabel ?activeIngredientLabel ?dosageLabel ?manufacturerLabel ?barcodeValue
        WHERE {{
          ?drug wdt:P31 wd:Q12140.  # İlaç (medicine instance)
          ?drug rdfs:label ?drugLabel.
          FILTER((LANG(?drugLabel)) = "tr" || (LANG(?drugLabel)) = "en")
          FILTER(CONTAINS(?drugLabel, "{drug_name}"))

          OPTIONAL {{ ?drug wdt:P3781 ?activeIngredientLabel. }}
          OPTIONAL {{ ?drug wdt:P2246 ?dosageLabel. }}
          OPTIONAL {{ ?drug wdt:P176 ?manufacturerLabel. }}
          OPTIONAL {{ ?drug wdt:P682 ?barcodeValue. }}
        }}
        LIMIT 5
        """

        url = "https://query.wikidata.org/sparql"
        headers = {"Accept": "application/json"}
        params = {
            "query": query,
            "format": "json"
        }

        response = requests.get(url, headers=headers, params=params, timeout=5)
        response.raise_for_status()

        results = response.json()

        if results.get("results", {}).get("bindings"):
            binding = results["results"]["bindings"][0]

            drug_data = {
                "ticari_ad": binding.get("drugLabel", {}).get("value", ""),
                "etken_madde": binding.get("activeIngredientLabel", {}).get("value", ""),
                "dozaj": binding.get("dosageLabel", {}).get("value", ""),
                "uretici": binding.get("manufacturerLabel", {}).get("value", ""),
                "barkod": binding.get("barcodeValue", {}).get("value", ""),
                "kaynak": "Wikidata",
                "wikidata_url": binding.get("drug", {}).get("value", "")
            }

            return drug_data

    except requests.exceptions.Timeout:
        logger.warning(f"Wikidata sorgusu timeout — {drug_name}")
    except Exception as e:
        logger.warning(f"Wikidata hatası ({drug_name}): {e}")

    return None


def fetch_drug_from_openfda(drug_name: str) -> Optional[Dict[str, Any]]:
    """
    OpenFDA API'sinden gerçek ilaç bilgileri çeker.
    FDA'nın açık ilaç veritabanı.

    Args:
        drug_name: İlaç adı (İngilizce)

    Returns:
        İlaç bilgileri dictionary'si veya None
    """
    try:
        url = "https://api.fda.gov/drug/label.json"
        params = {
            "search": f"openfda.brand_name:{drug_name}",
            "limit": 1
        }

        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()

        results = response.json()

        if results.get("results"):
            drug = results["results"][0]

            drug_data = {
                "ticari_ad": ", ".join(drug.get("openfda", {}).get("brand_name", [""])[:1]),
                "etken_madde": ", ".join(drug.get("active_ingredient", [""])[:3]),
                "dosaj": "; ".join(drug.get("dosage_and_administration", [""])[:2]) or "Bilgi mevcut değil",
                "form": ", ".join(drug.get("route", [""])[:1]) or "Bilgi mevcut değil",
                "uretici": ", ".join(drug.get("openfda", {}).get("manufacturer_name", [""])[:1]) or "Bilgi mevcut değil",
                "kaynak": "OpenFDA (FDA)",
                "url": f"https://www.fda.gov"
            }

            return drug_data

    except Exception as e:
        logger.warning(f"OpenFDA hatası ({drug_name}): {e}")

    return None


def fetch_drug_info(drug_name: str) -> Optional[Dict[str, Any]]:
    """
    Gerçek ilaç bilgisi çeker. Birden fazla kaynaktan dener.

    Args:
        drug_name: İlaç adı

    Returns:
        İlaç bilgileri veya None
    """
    logger.info(f"Gerçek ilaç verisi aranıyor: {drug_name}")

    # İlk olarak Wikidata'dan dene (Türkçe desteği daha iyi)
    result = fetch_drug_from_wikidata(drug_name)
    if result and result.get("ticari_ad"):
        logger.info(f"Wikidata'dan bulundu: {result['ticari_ad']}")
        return result

    # OpenFDA'dan dene (İngilizce)
    result = fetch_drug_from_openfda(drug_name)
    if result and result.get("ticari_ad"):
        logger.info(f"OpenFDA'dan bulundu: {result['ticari_ad']}")
        return result

    logger.warning(f"Gerçek veri bulunamadı: {drug_name}")
    return None


if __name__ == "__main__":
    # Test — Augmentin için gerçek veri çek
    drug_data = fetch_drug_info("Augmentin")
    if drug_data:
        print("Bulundu!")
        print(json.dumps(drug_data, indent=2, ensure_ascii=False))
    else:
        print("Bulunamadı")
