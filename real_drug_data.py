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


def _is_garbage_text(text: str, min_length: int = 20) -> bool:
    """
    Metni analiz et ve çöp veri olup olmadığını belirle.
    - Çok fazla tekrar eden sözcük
    - Anormal uzunluk
    - Makul içerik yok
    """
    if not text or len(text) < min_length:
        return False

    # Sözcükleri böl
    words = text.lower().split()
    if not words:
        return False

    # Tekrarlanan sözcüklerin yüzdesini kontrol et
    word_counts = {}
    for word in words:
        # Virgül ve nokta olmadan say
        clean_word = word.strip('.,!?;:')
        if clean_word and len(clean_word) > 2:
            word_counts[clean_word] = word_counts.get(clean_word, 0) + 1

    if not word_counts:
        return False

    # Eğer bir sözcük %30'dan fazla tekrarlanıyorsa, muhtemelen çöptür
    max_repeat_ratio = max(word_counts.values()) / len(words) if words else 0
    if max_repeat_ratio > 0.3:
        logger.warning(f"Tekrar eden metin tespit edildi: {text[:50]}...")
        return True

    return False


def _safe_extract_text(text_or_list, max_length: int = 300) -> str:
    """
    OpenFDA'dan metin çıkart, çöp veriler hariç, makul uzunlukta
    """
    if not text_or_list:
        return ""

    # Liste ise ilk elemanı al
    text = text_or_list[0] if isinstance(text_or_list, list) else text_or_list

    if not isinstance(text, str):
        return ""

    text = text.strip()

    # Çöp veri kontrolü
    if _is_garbage_text(text):
        return ""

    # İlk cümleyi al
    sentences = re.split(r'[.!?]\s+', text)
    if sentences:
        result = sentences[0].strip()
        if result and not _is_garbage_text(result, min_length=10):
            return result[:max_length]

    # Eğer cümle bulunamazsa, ilk max_length karakteri döndür
    if not _is_garbage_text(text, min_length=10):
        return text[:max_length]

    return ""


def _clean_drug_name(name: str) -> str:
    """İlaç adını normalize et (dosajları ayır vb)"""
    # "augmentin 1000mg" -> "augmentin"
    if not name:
        return ""

    cleaned = name.lower().strip()

    # Ortak Türkçe ve uluslararası ilaç adı varyasyonları
    variations = {
        "dikloron": "diclofenac",
        "diklofenak": "diclofenac",
        "voltaren": "diclofenac",
        "aspirin": "aspirin",
        "ibuprofen": "ibuprofen",
        "parol": "acetaminophen",  # Türkçe paracetamol → US acetaminophen
        "parasetamol": "acetaminophen",
        "paracetamol": "acetaminophen",
        "augmentin": "amoxicillin",
        "amoksisilin": "amoxicillin",
        "penisilin": "penicillin",
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
        # Çöp veri ve tekrarlayan metinler temizle
        active_ingredient = ""
        if "active_ingredient" in drug:
            ingredients = []
            for ing in drug.get("active_ingredient", []):
                ing_text = ""
                if isinstance(ing, str):
                    # "Amoxicillin trihydrate 500 mg" formatı
                    ing_text = ing.strip()
                elif isinstance(ing, dict):
                    # {"name": "...", "strength": "..."} formatı
                    if "name" in ing:
                        name = ing["name"]
                        strength = ing.get("strength", "")
                        ing_text = f"{name}{' ' + strength if strength else ''}".strip()

                # Çöp veri kontrolü - eğer çöpse eklemeden geç
                if ing_text and not _is_garbage_text(ing_text, min_length=5):
                    ingredients.append(ing_text[:150])

            if ingredients:
                active_ingredient = " + ".join(ingredients[:3])  # Max 3 etken madde

        # ============ DOZAJ ============
        # Dosage_and_administration genellikle uzun metin; ilk cümleyi al
        # Çöp veri ve tekrarlayan metinler temizle
        dosage = "Bilgi mevcut değil"
        if "dosage_and_administration" in drug:
            dos_text = _safe_extract_text(drug.get("dosage_and_administration"), max_length=200)
            if dos_text:
                dosage = dos_text

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

    # Wikidata'dan dene (Türkçe ve uluslararası kaynaklar)
    result = fetch_drug_from_wikidata(drug_name)
    if result and result.get("ticari_ad"):
        logger.info(f"✓ Wikidata'dan bulundu: {result['ticari_ad']}")
        return _translate_drug_data(result)

    # OpenFDA'dan dene (ABD FDA veritabanı)
    result = fetch_drug_from_openfda(drug_name)
    if result and result.get("ticari_ad"):
        logger.info(f"✓ OpenFDA'dan bulundu: {result['ticari_ad']}")
        return _translate_drug_data(result)

    # Türkçe ilaç adı varyasyonu varsa, canonical form ile yeniden dene
    clean_name = _clean_drug_name(drug_name)
    if clean_name != drug_name.lower().strip() and clean_name not in drug_name.lower():
        logger.info(f"Canonical form ile yeniden aranıyor: {clean_name}")
        result = fetch_drug_from_openfda(clean_name)
        if result and result.get("ticari_ad"):
            logger.info(f"✓ OpenFDA'dan canonical form ile bulundu: {result['ticari_ad']}")
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
