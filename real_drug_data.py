"""
Gerçek ilaç verilerini çeken veri kaynağı
Wikidata, OpenFDA ve açık veritabanlarından gerçek bilgiler
Turkish translation support through Groq API
"""

import requests
import json
from typing import Optional, Dict, Any
import logging
import re
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

logger = logging.getLogger(__name__)


def _clean_drug_name(name: str) -> str:
    """İlaç adını normalize et (dosajları ayır vb)"""
    # "augmentin 1000mg" -> "augmentin"
    if not name:
        return ""

    cleaned = name.lower().strip()

    # Ortak Türkçe ilaç adı varyasyonları
    variations = {
        "dikloron": "diclofenac",
        "diklofenak": "diclofenac",
        "voltaren": "diclofenac",
        "aspirin": "aspirin",
        "ibuprofen": "ibuprofen",
        "parol": "paracetamol",
        "parasetamol": "paracetamol",
        "augmentin": "amoxicillin",
    }

    # Eğer bilinen varyasyon varsa yönlendir
    for variant, canonical in variations.items():
        if variant in cleaned:
            logger.info(f"Varyasyon tespit edildi: {cleaned} → {canonical}")
            return canonical

    # Normal çıkarma: ilk kelimeyi al
    match = re.match(r'^([a-z]+)', cleaned)
    return match.group(1) if match else cleaned


def fetch_drug_from_wikidata(drug_name: str) -> Optional[Dict[str, Any]]:
    """
    Wikidata'dan gerçek ilaç bilgilerini çeker. Birden fazla arama stratejisi dener.

    Args:
        drug_name: İlaç adı

    Returns:
        İlaç bilgileri veya None
    """
    try:
        clean_name = _clean_drug_name(drug_name)

        # Deneme sırası: tam ad, kısaltma, temel adı
        search_terms = [clean_name, drug_name.lower().strip(), drug_name]

        for search_term in search_terms:
            if not search_term or len(search_term) < 2:
                continue

            logger.info(f"Wikidata'da '{search_term}' aranıyor...")

            # Wikidata Search API
            search_url = "https://www.wikidata.org/w/api.php"
            search_params = {
                "action": "wbsearchentities",
                "search": search_term,
                "language": "en",
                "format": "json",
                "type": "item"
            }

            try:
                search_response = requests.get(search_url, params=search_params, timeout=5)
                search_response.raise_for_status()
                search_results = search_response.json()

                if search_results.get("search"):
                    logger.info(f"Wikidata'da '{search_term}' bulundu!")
                    break
            except requests.exceptions.Timeout:
                logger.warning(f"Wikidata timeout — {search_term}")
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f"Wikidata isteği hatası ({search_term}): {e}")
                continue
        else:
            # Hiçbir arama sonuç vermedi
            logger.info(f"Wikidata'da herhangi bir sonuç bulunamadı: {drug_name}")
            return None

        if not search_results.get("search"):
            logger.info(f"Wikidata'da '{clean_name}' bulunamadı")
            return None

        item_id = search_results["search"][0]["id"]
        label = search_results["search"][0]["label"]

        logger.info(f"Wikidata'da bulundu: {item_id} - {label}")

        # Detaylarını çek (entity data)
        entity_url = f"https://www.wikidata.org/wiki/Special:EntityData/{item_id}.json"
        entity_response = requests.get(entity_url, timeout=5)
        entity_response.raise_for_status()
        entity_data = entity_response.json()

        entity = entity_data["entities"][item_id]
        claims = entity.get("claims", {})

        # Etken madde (P2064 = active substance)
        etken_madde = ""
        if "P2064" in claims:
            try:
                etken_id = claims["P2064"][0]["mainsnak"]["datavalue"]["value"]["id"]
                etken_entity = entity_data["entities"].get(etken_id, {})
                etken_madde = etken_entity.get("labels", {}).get("en", {}).get("value", "")
            except:
                pass

        # Üretici (P176 = manufacturer)
        uretici = ""
        if "P176" in claims:
            try:
                uretici_id = claims["P176"][0]["mainsnak"]["datavalue"]["value"]["id"]
                uretici_entity = entity_data["entities"].get(uretici_id, {})
                uretici = uretici_entity.get("labels", {}).get("en", {}).get("value", "")
            except:
                pass

        drug_data = {
            "ticari_ad": label,
            "etken_madde": etken_madde or "Bilgi mevcut değil",
            "dozaj": "Bilgi mevcut değil",
            "form": "Bilgi mevcut değil",
            "uretici": uretici or "Bilgi mevcut değil",
            "barkod": "Bilgi mevcut değil",
            "kaynak": "Wikidata",
            "wikidata_url": f"https://www.wikidata.org/wiki/{item_id}"
        }

        return drug_data

    except requests.exceptions.Timeout:
        logger.warning(f"Wikidata timeout — {drug_name}")
    except Exception as e:
        logger.warning(f"Wikidata hatası ({drug_name}): {e}")

    return None


def fetch_drug_from_openfda(drug_name: str) -> Optional[Dict[str, Any]]:
    """
    OpenFDA API'sinden gerçek ilaç bilgileri çeker (geliştirilmiş parser).
    Birden fazla arama stratejisi dener: brand name, active ingredient, vb.
    """
    try:
        clean_name = _clean_drug_name(drug_name)

        # Deneme sırası: brand name, active ingredient, genel arama
        search_queries = [
            f"openfda.brand_name:{clean_name}",  # Brand name araması
            f"openfda.active_ingredient:{clean_name}",  # Etken madde araması
            f"brand_name:{drug_name.lower().strip()}",  # Tam ad araması
        ]

        url = "https://api.fda.gov/drug/label.json"

        for query in search_queries:
            logger.info(f"OpenFDA'da '{query}' aranıyor...")

            try:
                params = {"search": query, "limit": 1}
                response = requests.get(url, params=params, timeout=5)
                response.raise_for_status()
                results = response.json()

                if results.get("results"):
                    logger.info(f"OpenFDA'da '{query}' bulundu!")
                    break
            except requests.exceptions.Timeout:
                logger.warning(f"OpenFDA timeout — {query}")
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f"OpenFDA isteği hatası ({query}): {e}")
                continue
        else:
            # Hiçbir arama sonuç vermedi
            logger.info(f"OpenFDA'da herhangi bir sonuç bulunamadı: {drug_name}")
            return None

        if not results.get("results"):
            logger.info(f"OpenFDA'da '{clean_name}' bulunamadı")
            return None

        drug = results["results"][0]
        openfda_data = drug.get("openfda", {})

        # ============ ETKEN MADDE ============
        # OpenFDA'da "active_ingredient" çoğu zaman liste şeklinde:
        # ["ingredient1 strength1", "ingredient2 strength2"] veya
        # [{"name": "...", "strength": "..."}, ...]
        active_ingredient = ""
        if "active_ingredient" in drug:
            ingredients = []
            for ing in drug.get("active_ingredient", []):
                if isinstance(ing, str):
                    # "Amoxicillin trihydrate 500 mg" formatı
                    ingredients.append(ing)
                elif isinstance(ing, dict):
                    # {"name": "...", "strength": "..."} formatı
                    if "name" in ing:
                        name = ing["name"]
                        strength = ing.get("strength", "")
                        ingredients.append(f"{name}{' ' + strength if strength else ''}")
            active_ingredient = " + ".join(ingredients)

        # ============ DOZAJ ============
        # Dosage_and_administration genellikle uzun metin; ilk cümleyi al
        dosage = "Bilgi mevcut değil"
        if "dosage_and_administration" in drug:
            dos_list = drug.get("dosage_and_administration", [])
            if dos_list:
                full_text = dos_list[0]
                # İlk cümleyi bul (nokta, ünlem veya soru işareti kadar)
                sentences = re.split(r'[.!?]', full_text)
                if sentences:
                    dosage = sentences[0].strip()[:150]  # İlk 150 char
                    if not dosage:
                        dosage = full_text[:150]

        # ============ FORM ============
        form = ", ".join(openfda_data.get("route", [])) if openfda_data.get("route") else "Bilgi mevcut değil"

        # ============ ÜRETICI ============
        uretici = ""
        if "manufacturer_name" in openfda_data:
            manu_list = openfda_data.get("manufacturer_name", [])
            if manu_list:
                # GSK, Pfizer vb. ana üreticileri al
                uretici = manu_list[0]

        # ============ BARKOD ============
        barkod = "Bilgi mevcut değil"
        # OpenFDA'da barkod bilgisi nadiren vardır; UPC alanında olabilir
        if "upc" in openfda_data:
            barkod = openfda_data["upc"][0] if openfda_data["upc"] else barkod

        # ============ BRAND NAME ============
        brand_name = ""
        if "brand_name" in openfda_data:
            bn_list = openfda_data.get("brand_name", [])
            if bn_list:
                brand_name = bn_list[0]

        drug_data = {
            "ticari_ad": brand_name or clean_name.upper(),
            "etken_madde": active_ingredient or "Bilgi mevcut değil",
            "dozaj": dosage,
            "form": form,
            "uretici": uretici or "Bilgi mevcut değil",
            "barkod": barkod,
            "kaynak": "OpenFDA (FDA)",
        }

        logger.info(f"✓ OpenFDA'dan bulundu: {brand_name}")
        return drug_data

    except requests.exceptions.Timeout:
        logger.warning(f"OpenFDA timeout — {drug_name}")
    except Exception as e:
        logger.warning(f"OpenFDA hatası ({drug_name}): {e}")

    return None


def _translate_to_turkish(text: str) -> str:
    """
    Groq API kullanarak İngilizce metni Türkçeye çevir.

    Args:
        text: Çevrilecek İngilizce metin

    Returns:
        Türkçe çevrilmiş metin
    """
    if not text or not text.strip():
        return text

    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY bulunamadı, çeviri yapılamayacak")
            return text

        client = Groq(api_key=api_key, timeout=120.0)

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "user",
                    "content": f"Bu tıbbi İngilizce metni kısaca ve doğru bir şekilde Türkçeye çevir. Sadece çeviriyi yaz, ek açıklama yapma:\n\n{text}"
                }
            ],
            max_completion_tokens=500,
            temperature=0.3,
        )

        translated = (response.choices[0].message.content or "").strip()
        if translated:
            logger.info(f"✓ Çeviri tamamlandı: {text[:50]}... → {translated[:50]}...")
            return translated
        else:
            logger.warning(f"Çeviri boş sonuç döndü: {text[:50]}")
            return text

    except Exception as e:
        logger.warning(f"Çeviri hatası: {e}")
        return text


def _translate_drug_data(drug_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    İlaç verilerini Türkçeye çevir.
    Eğer kaynak zaten Türkçe ise (Wikidata gibi), çevirme.

    Args:
        drug_data: İlaç bilgileri

    Returns:
        Türkçeye çevrilmiş ilaç bilgileri
    """
    if not drug_data:
        return drug_data

    # Eğer kaynak zaten Türkçe ise (örn: Wikidata), çevirme
    kaynak = drug_data.get("kaynak", "").lower()
    if "wikidata" in kaynak or "türkçe" in kaynak:
        logger.info("Kaynak zaten Türkçe, çeviri atlanıyor")
        return drug_data

    translated = dict(drug_data)

    # Çevrilecek alanlar
    fields_to_translate = ["etken_madde", "dozaj", "form", "uretici"]

    for field in fields_to_translate:
        if field in translated and translated[field] != "Bilgi mevcut değil":
            original = translated[field]
            translated[field] = _translate_to_turkish(original)

    logger.info(f"✓ İlaç verisi Türkçeye çevrildi: {drug_data.get('ticari_ad')}")
    return translated


def fetch_drug_info(drug_name: str) -> Optional[Dict[str, Any]]:
    """
    Gerçek ilaç bilgisi çeker. Birden fazla kaynaktan dener.
    Sonuçları Türkçeye çevir.

    Args:
        drug_name: İlaç adı (örn: "augmentin 1000mg", "parol")

    Returns:
        Türkçeye çevrilmiş ilaç bilgileri veya None
    """
    if not drug_name or not drug_name.strip():
        return None

    logger.info(f"Gerçek ilaç verisi aranıyor: '{drug_name}'")

    # Wikidata'dan dene
    result = fetch_drug_from_wikidata(drug_name)
    if result and result.get("ticari_ad"):
        logger.info(f"✓ Wikidata'dan bulundu: {result['ticari_ad']}")
        return _translate_drug_data(result)

    # OpenFDA'dan dene (İngilizce)
    result = fetch_drug_from_openfda(drug_name)
    if result and result.get("ticari_ad"):
        logger.info(f"✓ OpenFDA'dan bulundu: {result['ticari_ad']}")
        return _translate_drug_data(result)

    logger.warning(f"✗ Gerçek veri bulunamadı: {drug_name}")
    return None


if __name__ == "__main__":
    # Test
    for test_drug in ["augmentin", "amoxil", "parol"]:
        print(f"\nTest: {test_drug}")
        data = fetch_drug_info(test_drug)
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("Bulunamadı")
