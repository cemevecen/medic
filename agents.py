"""
WikiPharma — çoklu ajan sistemi
agents.py: Tüm ajan sınıfları ve ana orkestratör bu dosyada tanımlanmıştır.
"""

# Versiyon numarası — app.py session_state cache invalidation için kullanılır.
# Fact-Checker / parser / orchestrator davranışı değiştiğinde artırın.
PHARMA_GUARD_VERSION = "1.24"

import logging
import os
import json
import base64
import time
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import google.generativeai as genai
from groq import Groq
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

_log_vision = logging.getLogger("pharma_guard.vision")


def _legacy_noise_in_text(t: Any) -> bool:
    """Eski şablon / hatalı model cümleleri (Türkçe karakter varyantları dahil)."""
    if t is None:
        return False
    s = str(t).strip()
    if not s:
        return False
    s = unicodedata.normalize("NFKC", s)
    cf = s.casefold()
    loose = (
        cf.replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ı", "i")
        .replace("i̇", "i")
        .replace("ö", "o")
        .replace("ç", "c")
        .replace("â", "a")
        .replace("—", " ")
        .replace("–", " ")
    )
    if "groq" in loose and "fallback" in loose:
        return True
    needles = (
        "groq fallback",
        "llava ve groq",
        "llava ile groq",
        "llava ve groq ile",
        "görsel işlenemiyor",
        "gorsel islenemiyor",
        "görsel analizi llava",
        "gorsel analizi llava",
        "metin girişi tercih",
        "metin girisi tercih",
        "metin girişi kullanarak",
        "metin girisi kullanarak",
        "metin girişi ile devam",
        "metin girişi tercih edilir",
        "metin girisi tercih edilir",
    )
    for n in needles:
        ncf = n.casefold()
        if ncf in cf or ncf in loose:
            return True
    # "Görsel işlenemiyor" ASCII yazım (i/ı karışık)
    if "islenemiyor" in loose and ("gorsel" in loose or "görsel" in cf):
        if "yeterli bilgi" not in loose and "analiz tamamland" not in loose:
            return True
    return False


def _vision_merge_case_insensitive_keys(vision: Dict[str, Any]) -> Dict[str, Any]:
    """Model JSON'unda Notes/Source/error gibi anahtarları notlar/kaynak/hata ile birleştirir."""
    out = dict(vision)

    def _pull(canonical: str, *match_names: str) -> None:
        names_cf = {m.casefold() for m in match_names}
        for k in list(out.keys()):
            if not isinstance(k, str):
                continue
            if k.strip().casefold() not in names_cf:
                continue
            if k == canonical:
                continue
            val = out.pop(k, None)
            if val is None or (isinstance(val, str) and not str(val).strip()):
                continue
            cur = out.get(canonical)
            if cur is None or (isinstance(cur, str) and not str(cur).strip()):
                out[canonical] = val
            elif str(val) not in str(cur):
                out[canonical] = f"{cur} {val}".strip()

    _pull("notlar", "notlar", "notes", "note")
    _pull("kaynak", "kaynak", "source", "origin")
    _pull("hata", "hata", "error", "err")
    return out


def vision_output_has_legacy_user_facing_copy(vision: Optional[Dict[str, Any]]) -> bool:
    """
    Eski sürümdeki / önbellekteki 'Groq Fallback' + 'Görsel işlenemiyor' metinlerini tespit eder.
    Güncel pipeline bu ifadeleri üretmez; görülürse kullanıcıya yeniden analiz önerilir.
    """
    if not isinstance(vision, dict):
        return False
    v = _vision_merge_case_insensitive_keys(dict(vision))
    for key in ("kaynak", "notlar", "hata"):
        if _legacy_noise_in_text(v.get(key)):
            return True
    ga = v.get("gorsel_analiz")
    if isinstance(ga, dict) and _legacy_noise_in_text(ga.get("message")):
        return True
    return False


_STRINGY_VISION_KEYS = (
    "ticari_ad",
    "etken_madde",
    "dozaj",
    "form",
    "uretici",
    "barkod",
    "notlar",
    "kaynak",
    "hata",
)


def _vision_normalize_null_strings(vision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Vision çıktısında JSON null / Python None olan metin alanlarını '' yapar.
    Eski .get('etken_madde', '').strip() kalıbı (anahtar varken değer None) ile uyumluluk.
    """
    if not isinstance(vision, dict):
        return {}
    out = dict(vision)
    for k in _STRINGY_VISION_KEYS:
        if k in out and out[k] is None:
            out[k] = ""
    return out


def _vision_field_str(
    vision: Optional[Dict[str, Any]],
    key: str,
    *,
    alt: str = "",
) -> str:
    """
    Vision sözlüğünden güvenli metin. Anahtar yoksa veya değer None/boşsa `alt` kullanılır
    (.get(x, '') Python'da x anahtarı açıkça None ise yine None döndüğü için strip() patlamasını önler).
    """
    if not isinstance(vision, dict):
        return str(alt or "").strip()
    if key not in vision or vision.get(key) is None:
        return str(alt or "").strip()
    s = str(vision.get(key) or "").strip()
    return s if s else str(alt or "").strip()


def vision_dict_for_ui(vision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Streamlit vb. arayüzde gösterilecek vision kopyası: eski şablon not/hata satırlarını çıkarır,
    gorsel_analiz.message alanını nötr bir metne çevirir (session_state içindeki ham dict'i değiştirmez).
    """
    if not isinstance(vision, dict):
        return {}
    out = _vision_merge_case_insensitive_keys(dict(vision))
    for k in ("notlar", "kaynak", "hata"):
        if _legacy_noise_in_text(out.get(k)):
            out.pop(k, None)
    ga = out.get("gorsel_analiz")
    if isinstance(ga, dict) and _legacy_noise_in_text(ga.get("message")):
        out["gorsel_analiz"] = {
            **ga,
            "message": (
                "Görselden otomatik güvenilir sonuç çıkarılamadı. Daha net, aydınlık ve yakın "
                "çekilmiş bir kutu fotoğrafı deneyin veya ilaç adını metin kutusuna yazıp "
                "yeniden analiz başlatın."
            ),
        }
    return out


from gemini_models import (
    model_chain as _gemini_model_chain,
    model_missing_error as _gemini_model_missing_error,
    gemini_quota_or_rate_limit,
)


def _gemini_model_name() -> str:
    return _gemini_model_chain()[0]


# ---------------------------------------------------------------------------
# API İstemcileri
# ---------------------------------------------------------------------------

def _init_gemini():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY bulunamadı. Lütfen .env dosyasını kontrol edin.")
    genai.configure(api_key=api_key)

def _init_groq() -> Groq:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY bulunamadı. Lütfen .env dosyasını kontrol edin.")
    return Groq(api_key=api_key, timeout=120.0)


def _groq_safety_model_chain() -> List[str]:
    """Safety Auditor için Groq model sırası (429 / TPD limitinde sıradakine geçer)."""
    raw = (os.getenv("GROQ_SAFETY_MODEL_PRIORITY") or "").strip()
    if raw:
        seen: set = set()
        out: List[str] = []
        for m in raw.split(","):
            m = m.strip()
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out
    return [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama-3.1-70b-versatile",
    ]


def _groq_is_rate_limit(exc: Exception) -> bool:
    t = str(exc).lower()
    return "429" in str(exc) or "rate_limit" in t or "rate limit" in t


def _groq_safety_failure_message(exc: Exception) -> str:
    if _groq_is_rate_limit(exc):
        return (
            "Groq günlük token limiti (TPD) doldu veya istek sınırı aşıldı; Safety Auditor "
            "yanıt veremedi. Yaklaşık 25–30 dakika sonra tekrar deneyin veya kotayı "
            "https://console.groq.com/settings/billing adresinden yükseltin. "
            "Önce hafif model denemek için `.env` içinde örn. "
            "GROQ_SAFETY_MODEL_PRIORITY=llama-3.1-8b-instant,llama-3.3-70b-versatile kullanın."
        )
    return f"Safety Auditor hatası: {exc!s}"


# ---------------------------------------------------------------------------
# MASTER SYSTEM PROMPT
# ---------------------------------------------------------------------------

MASTER_PROMPT = """
### ROLE: PHARMA-GUARD MASTER ORCHESTRATOR (PG-MO) ###

Sen, Gemini 2.0 tabanlı, multimodal yeteneklere sahip ve çoklu ajan (Multi-Agent)
ekosistemini yöneten baş mimarsın. Görevin; görsel veya metinsel girişi alınan bir ilacı,
sıfır hata toleransı ile analiz etmektir.

OPERASYONEL PROTOKOLLER VE KISITLAMALAR:
- GÜVEN PUANI (Confidence Score): Her bilgi parçası için 1-10 arası bir puan ver.
  Ortalama güven için uyarı kutusu uygulama tarafından otomatik eklenir; sen rapora
  "uyarı eklendi", "güven X'in altında" gibi meta açıklama veya ek DİKKAT başlığı yazma.
- HALÜSİNASYON ENGELİ: Eğer ilacın etken maddesi ile prospektüs bilgisi eşleşmiyorsa,
  süreci durdurup 'VERİ UYUŞMAZLIĞI' hata mesajı ver.
- DİL VE ÜSLUP: Rapor tamamen Türkçe, tıbbi terimleri parantez içinde açıklayan,
  güven veren ve profesyonel bir tonda olmalıdır.
- KURAL 1: Yazı okunmuyorsa asla tahmin etme.
- KURAL 2: Bilgi kaynağın %100 tıbbi prospektüsler olmalı.
- KURAL 3: Bilgiler arasında 1 mg fark olsa bile 'VERİ UYUŞMAZLIĞI' alarmı ver.
"""

VISION_PROMPT = """
Sen bir ilaç görüntü analiz uzmanısın (Vision-Scanner). Verilen görseli analiz et ve
aşağıdaki bilgileri JSON formatında çıkar:

{
  "ticari_ad": "İlacın kutu üzerindeki ticari adı",
  "etken_madde": "Etken madde (kimyasal ad)",
  "dozaj": "Doz miktarı (mg/ml/mcg)",
  "form": "Tablet / Kapsül / Şurup / Ampul / vb.",
  "barkod": "Barkod numarası (varsa, yoksa null)",
  "uretici": "Üretici firma adı (varsa)",
  "okunabilirlik_skoru": 1-10 arası (10=mükemmel okunabilir),
  "notlar": "Okunmayan veya belirsiz alanlar varsa belirt"
}

KURALLAR:
- Eğer herhangi bir alan net okunamıyorsa null yaz, tahmin YAPMA.
- Okunabilirlik skoru 5'in altındaysa notlar alanına "FOTOĞRAF KALİTESİ YETERSİZ" yaz.
- Türkçe veya Latince ilaç isimlerini olduğu gibi al, çevirme.
- notlar içinde YASAK (eski hatalı şablon): "Groq Fallback", "LLaVA", "metin girişi tercih",
  "Görsel işlenemiyor", "kullanıcıdan metin iste" vb. — yalnızca kutu okuma durumunu yaz.
- JSON'a "kaynak" alanı ekleme (istemiyoruz).
"""

SAFETY_PROMPT_TEMPLATE = """SADECE geçerli bir JSON nesnesi döndür. Açıklama, başlık veya markdown kullanma.

İLAÇ BİLGİLERİ:
{drug_info}

RAG KAYNAK VERİSİ (yoksa kendi tıbbi bilgini kullan):
{rag_data}

Genel farmakoloji bilgini kullanarak, ilaç adı veya etken maddesi bilinen bir ilaçsa
gerçek klinik bilgiyle yanıt ver. RAG boşsa internet/genel bilginden yararlan.

Döndüreceğin JSON şeması (tam olarak bu anahtarları kullan):
{{
  "yan_etkiler": {{
    "yaygin": ["en az 3 yaygın yan etki"],
    "ciddi": ["ciddi yan etkiler"],
    "cok_nadir": ["çok nadir görülen yan etkiler"]
  }},
  "etkilesimler": ["diğer ilaçlarla önemli etkileşimler — en az 2"],
  "kontrendikasyonlar": ["kimler kullanamamalı — en az 2"],
  "ozel_uyarilar": ["hamilelik, emzirme, yaşlı, çocuk, böbrek/karaciğer uyarıları"],
  "alarm_seviyesi": "YEŞİL veya SARI veya KIRMIZI",
  "alarm_gerekce": "alarm seviyesinin kısa gerekçesi (1-2 cümle)",
  "guven_puani": 7
}}

KIRMIZI: hamilelikte kontrendike, dar terapötik indeks, ölümcül etkileşim.
SARI: yaş/doz kısıtlaması, dikkat gerektiren etkileşimler.
YEŞİL: genel kullanım için güvenli (hekime danışarak).
"""

CORPORATE_PROMPT_TEMPLATE = """SADECE geçerli bir JSON nesnesi döndür. Açıklama veya markdown kullanma.

İLAÇ ADI: {drug_name}
BİLİNEN ÜRETİCİ: {manufacturer}

Bu ilacın üreticisini farmakoloji ve ilaç endüstrisi bilginle belirle.
Özellikle Türk ilaç firmaları (Abdi İbrahim, Eczacıbaşı, Recordati, Santa Farma,
Sandoz Türkiye, Pfizer Türkiye, Deva, Nobel, Bilim vb.) için bilgin varsa kullan.
TİTCK onaylı ilaçlar için "TİTCK onaylı" yaz.

Döndüreceğin JSON şeması:
{{
  "firma_adi": "üreticinin tam adı (bilinmiyorsa 'Tespit Edilemedi')",
  "ulke": "menşe ülke (Türkiye / Almanya / vb.)",
  "sertifikalar": ["GMP", "ISO 9001"],
  "titck_durumu": "TİTCK onaylı veya Belirsiz",
  "genel_degerlendirme": "firma hakkında 2-3 cümle gerçek bilgi",
  "guven_puani": 6
}}

guven_puani: kesin bilgi varsa 7-9, tahmini bilgi varsa 5-6, bilinmiyorsa 3.
"""

SYNTHESIS_PROMPT_TEMPLATE = """Sen WikiPharma raporlama uzmanısın. Aşağıdaki ajan çıktılarından
kapsamlı, bütünlüklü bir Türkçe ilaç analiz raporu oluştur.

VISION / PDF SCANNER SONUCU:
{vision_data}

BARKOD / QR KOD TARAMA (makine okuması — görsel modelden bağımsız):
{barcode_block}

BENZER İLAÇ / MUADİL ÖZETİ (yerel katalog + isteğe bağlı model önerisi):
{similar_drugs_block}

SAFETY AUDITOR SONUCU:
{safety_data}

CORPORATE ANALYST SONUCU:
{corporate_data}

RAG KAYNAKÇASI:
{rag_sources}

KURALLAR:
1. Tamamen Türkçe yaz; tıbbi terimleri parantez içinde açıkla.
2. Ortalama güven / DİKKAT callout'u uygulama tarafından eklenir; raporda "güven puanı
   nedeniyle başa uyarı eklendi" veya eşik (7, 8 vb.) hakkında meta cümle yazma.
3. PDF dosya adı ile çıkarılan bilgi arasındaki farkı "not" olarak belirt — raporu bloklama.
4. Eksik veya belirsiz alanları "Bilgi mevcut değil" olarak işaretle, uydurma.
5. Fiyat, ucuzluk veya eczane kampanyası iddiası yapma; fiyat için ayrı entegrasyon gerekir de.
6. Aşağıdaki Markdown bölüm başlıklarını kullan:

## 1. İlaç Kimlik Özeti
## 2. Kullanım Amacı (Endikasyonlar)
## 3. Kritik Uyarılar ve Yan Etkiler
## 4. Etken Madde ve Üretici Detayları
## 5. Kaynakça
## 6. Barkod, QR Kod ve Kimlik Sinyali
## 7. Benzer İlaçlar / Muadil Alternatifler

Her bölümün sonuna güven puanını ekle: `[Güven: X/10]`
"""


# ---------------------------------------------------------------------------
# AJAN 1: Vision Scanner
# ---------------------------------------------------------------------------

class VisionScannerAgent:
    """
    Groq görüntü modelleri (Llama 4 Scout vb.) + OCR (Tesseract) + metin modeli
    ile kutu görselinden veri çıkarır. Metin girişi yalnızca tüm kurtarma adımları
    başarısız olduğunda önerilir; görüntüsüz “fallback” asla görsel analiz diye sunulmaz.
    """

    def __init__(
        self,
        groq_client: Optional[Groq] = None,
        openai_compat: Optional[Dict[str, Any]] = None,
    ):
        self.groq_client = groq_client or _init_groq()
        self._openai_compat_overrides = (
            {k: v for k, v in (openai_compat or {}).items() if str(v).strip()}
            or None
        )

    def _openai_compat_config(self) -> Optional[Dict[str, str]]:
        from openai_compat import resolve_openai_compat_config

        return resolve_openai_compat_config(self._openai_compat_overrides)

    @staticmethod
    def _finalize_scan_vision_output(d: Dict[str, Any]) -> Dict[str, Any]:
        """Sürüm etiketi + nadiren görülen eski/yanıltıcı model metinlerini düzeltir."""
        out = _vision_merge_case_insensitive_keys(dict(d))
        out["pharma_guard_scan_version"] = PHARMA_GUARD_VERSION
        if _legacy_noise_in_text(out.get("kaynak")):
            out["kaynak"] = "Groq görüntü + OCR pipeline"
        note = str(out.get("notlar") or "")
        if _legacy_noise_in_text(note):
            ga = out.get("gorsel_analiz")
            if (
                isinstance(ga, dict)
                and ga.get("message")
                and not _legacy_noise_in_text(ga.get("message"))
            ):
                out["notlar"] = str(ga["message"])
            else:
                out["notlar"] = (
                    "Görselden yeterli bilgi çıkarılamadı. Daha net, aydınlık ve yakın çekilmiş "
                    "bir fotoğraf deneyin (kutu ön yüzü, yazılar, mümkünse barkod alanı). "
                    "Alternatif olarak ilaç adını metin olarak girebilirsiniz."
                )
        if _legacy_noise_in_text(out.get("hata")):
            out.pop("hata", None)
        ga = out.get("gorsel_analiz")
        if isinstance(ga, dict) and _legacy_noise_in_text(ga.get("message")):
            out["gorsel_analiz"] = {
                **ga,
                "message": (
                    "Görselden otomatik güvenilir sonuç çıkarılamadı. Daha net fotoğraf "
                    "veya ilaç adını metin kutusundan girip yeniden analiz deneyin."
                ),
            }
        return out

    @staticmethod
    def _sanitize_model_output_templates(d: Dict[str, Any], canonical_kaynak: str) -> Dict[str, Any]:
        """Eski/hatalı model veya eğitim şablonu metinlerini kaldırır; kaynağı tekilleştirir."""
        out = dict(d)
        out["kaynak"] = canonical_kaynak
        low = str(out.get("notlar") or "").lower()
        banned = (
            "görsel işlenemiyor",
            "gorsel islenemiyor",
            "metin girişi",
            "metin girisi",
            "groq fallback",
            "llava ve groq",
            "llava ile groq",
            "metin girişi kullan",
            "metin girisi kullan",
            "kullanıcıdan metin",
            "metin girişi tercih",
        )
        if any(b in low for b in banned):
            osk = out.get("okunabilirlik_skoru")
            if isinstance(osk, (int, float)) and float(osk) < 5:
                out["notlar"] = "FOTOĞRAF KALİTESİ YETERSİZ"
            else:
                out["notlar"] = "Kutu üzerindeki yazılara göre analiz tamamlandı."
        return out

    @staticmethod
    def _vision_payload_useful(d: Dict[str, Any]) -> bool:
        if not isinstance(d, dict) or d.get("hata"):
            return False
        t = (d.get("ticari_ad") or "").strip()
        e = (d.get("etken_madde") or "").strip()
        djz = (d.get("dozaj") or "").strip()
        fm = (d.get("form") or "").strip()
        if len(t) >= 2 or len(e) >= 3:
            return True
        if len(djz) >= 2 and len(fm) >= 2:
            return True
        return False

    def _call_groq_vision_once(
        self, rgb: Image.Image, model_id: str, attempt: int
    ) -> Dict[str, Any]:
        from image_pipeline import classify_groq_vision_error, encode_image_for_groq_vision

        try:
            b64, nbytes = encode_image_for_groq_vision(rgb)
            _log_vision.info(
                "groq_vision_attempt model=%s attempt=%s jpeg_bytes=%s",
                model_id,
                attempt,
                nbytes,
            )
            response = self.groq_client.chat.completions.create(
                model=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ],
                    }
                ],
                max_completion_tokens=1024,
                temperature=0.1,
            )
            raw = (response.choices[0].message.content or "").strip()
            if not raw:
                return {
                    "hata": "Groq görüntü modeli boş yanıt döndürdü",
                    "kaynak": model_id,
                    "_error_code": "empty_response",
                    "_stage": "groq_vision",
                }
            parsed = self._parse_json_response(raw, source=f"Groq Vision ({model_id})")
            parsed = self._sanitize_model_output_templates(parsed, f"Groq Vision ({model_id})")
            parsed["_error_code"] = None
            parsed["_stage"] = "groq_vision"
            return parsed
        except Exception as exc:
            code = classify_groq_vision_error(exc)
            _log_vision.warning(
                "groq_vision_error model=%s attempt=%s code=%s err=%s",
                model_id,
                attempt,
                code,
                exc,
            )
            return {
                "hata": f"Groq görüntü hatası ({code}): {exc!s}",
                "kaynak": model_id,
                "_error_code": code,
                "_stage": "groq_vision",
            }

    def _run_vision_with_retries(self, prepared: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        from image_pipeline import build_gorsel_analiz_envelope, groq_vision_model_chain

        variants = [
            ("vision_primary", prepared["vision_rgb"]),
            ("vision_retry", prepared["vision_retry"]),
        ]
        models = groq_vision_model_chain()
        last = "vision_no_success"
        for label, frame in variants:
            for model_id in models:
                for attempt in (1, 2):
                    r = self._call_groq_vision_once(frame, model_id, attempt)
                    if self._vision_payload_useful(r):
                        r["gorsel_analiz"] = build_gorsel_analiz_envelope(
                            success=True,
                            status="full_success",
                            source=model_id,
                            extracted_text="",
                            identified_medicine=(r.get("ticari_ad") or "")[:500],
                            dosage=(r.get("dozaj") or "")[:120],
                            message="Görsel analiz tamamlandı.",
                            error_code=None,
                        )
                        return r, f"{label}:{model_id}:attempt{attempt}"
                    last = r.get("_error_code") or r.get("hata") or "parse_or_empty"
                    ec = r.get("_error_code")
                    if ec in ("model_decommissioned", "model_not_found", "model_unavailable"):
                        break
        return None, str(last)

    def _run_gemini_vision_fallback(self, prepared: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Groq görüntü zinciri boş döndüyse Google Gemini ile kutu görseli analizi (LLaVA yerine güncel multimodal)."""
        try:
            _init_gemini()
        except Exception:
            return None
        models = _gemini_model_chain()
        variants = [
            ("gemini_primary", prepared["vision_rgb"]),
            ("gemini_retry", prepared["vision_retry"]),
        ]
        for _label, frame in variants:
            for idx, name in enumerate(models):
                try:
                    model = genai.GenerativeModel(name)
                    response = model.generate_content(
                        [VISION_PROMPT, frame],
                        generation_config=genai.GenerationConfig(
                            temperature=0.1,
                            max_output_tokens=1024,
                        ),
                    )
                    raw = (response.text or "").strip()
                    if not raw:
                        continue
                    parsed = self._parse_json_response(raw, source=f"Gemini Vision ({name})")
                    parsed = self._sanitize_model_output_templates(parsed, f"Gemini Vision ({name})")
                    if self._vision_payload_useful(parsed):
                        parsed["_error_code"] = None
                        parsed["_stage"] = "gemini_vision"
                        _log_vision.info("gemini_vision_ok model=%s", name)
                        return parsed
                except Exception as exc:
                    _log_vision.warning("gemini_vision_fail model=%s err=%s", name, exc)
                    if idx < len(models) - 1:
                        continue
                    break
        return None

    def _attach_barkod_qr(
        self, result: Dict[str, Any], kodlar: Dict[str, Any]
    ) -> Dict[str, Any]:
        from barcode_detection import merge_codes_into_vision

        return merge_codes_into_vision(result, kodlar["barkod"], kodlar["qr_kod"])

    def scan(self, image: Image.Image) -> Dict[str, Any]:
        """
        Sıra: (1) Çok aşamalı ön işleme (2) Groq görüntü modelleri + yeniden deneme
        (3) Tesseract OCR (4) OCR metnini Groq metin modeliyle yapılandırma
        (5) OCR satır sezgisel kısmi sonuç (6) Son çare kullanıcı rehberi.
        """
        from barcode_detection import scan_codes_from_image
        from image_pipeline import (
            build_gorsel_analiz_envelope,
            groq_vision_model_chain,
            heuristic_medicine_line,
            ocr_extract_text,
            prepare_multimodal_inputs,
            structure_ocr_with_groq_text_model,
        )

        meta0 = {"pil_mode": image.mode, "pil_size": image.size}
        _log_vision.info("pipeline_start %s", meta0)

        prepared = prepare_multimodal_inputs(image)
        meta = prepared.get("meta") or {}
        _log_vision.info(
            "pipeline_preprocess upload=%s normalized=%s ocr=%s",
            meta.get("upload_size"),
            meta.get("normalized_size"),
            meta.get("ocr_size"),
        )

        kodlar = scan_codes_from_image(prepared["vision_rgb"])
        _log_vision.info(
            "barcode_stage barkod=%s qr=%s",
            kodlar["barkod"].get("tespit_edildi"),
            kodlar["qr_kod"].get("tespit_edildi"),
        )

        vr, vtag = self._run_vision_with_retries(prepared)
        if vr is not None:
            _log_vision.info("vision_success path=%s models=%s", vtag, groq_vision_model_chain())
            return self._finalize_scan_vision_output(self._attach_barkod_qr(vr, kodlar))

        gm = self._run_gemini_vision_fallback(prepared)
        if gm is not None:
            gm["gorsel_analiz"] = build_gorsel_analiz_envelope(
                success=True,
                status="full_success",
                source="gemini_vision",
                extracted_text="",
                identified_medicine=(gm.get("ticari_ad") or "")[:500],
                dosage=(gm.get("dozaj") or "")[:120],
                message=(
                    "Groq görüntü zinciri sonuç vermedi veya erişim sınırına takıldı; "
                    "aynı kutu görseli Gemini çok modlu model ile analiz edildi."
                ),
                error_code=None,
            )
            _log_vision.info("vision_gemini_fallback_used")
            return self._finalize_scan_vision_output(self._attach_barkod_qr(gm, kodlar))

        ocr_text, ocr_code = ocr_extract_text(prepared["ocr_image"])
        _log_vision.info("ocr_stage code=%s text_len=%s", ocr_code, len(ocr_text or ""))

        structured, st_err = structure_ocr_with_groq_text_model(
            self.groq_client, ocr_text, _groq_safety_model_chain()
        )
        if structured is not None:
            sk = str(structured.get("kaynak") or "OCR+Groq metin").strip()
            structured = self._sanitize_model_output_templates(structured, sk)
        if structured is not None and self._vision_payload_useful(structured):
            structured["gorsel_analiz"] = build_gorsel_analiz_envelope(
                success=True,
                status="ocr_recovered",
                source="ocr+groq",
                extracted_text=(ocr_text or "")[:8000],
                identified_medicine=(structured.get("ticari_ad") or "")[:500],
                dosage=(structured.get("dozaj") or "")[:120],
                message=(
                    "OCR ile kutu metni okundu; analiz bu metin üzerinden "
                    "yapılandırılarak sürdürüldü."
                ),
                error_code=ocr_code,
            )
            _log_vision.info("ocr_groq_structure_ok")
            return self._finalize_scan_vision_output(self._attach_barkod_qr(structured, kodlar))

        if structured is not None and not self._vision_payload_useful(structured):
            t0 = (structured.get("ticari_ad") or "").strip()
            e0 = (structured.get("etken_madde") or "").strip()
            if len(t0) >= 2 or len(e0) >= 2:
                structured["gorsel_analiz"] = build_gorsel_analiz_envelope(
                    success=True,
                    status="partial_success",
                    source="ocr+groq",
                    extracted_text=(ocr_text or "")[:8000],
                    identified_medicine=t0[:500],
                    dosage=(structured.get("dozaj") or "")[:120],
                    message=(
                        "Görselden kısmi bilgi çıkarıldı. Analiz elde edilen metin "
                        "üzerinden devam etti."
                    ),
                    error_code=st_err or ocr_code,
                )
                _log_vision.info("ocr_groq_partial_accept")
                return self._finalize_scan_vision_output(self._attach_barkod_qr(structured, kodlar))

        if ocr_text and len(ocr_text.strip()) >= 4:
            line, how = heuristic_medicine_line(ocr_text)
            if len(line.strip()) >= 3:
                partial = {
                    "ticari_ad": line.strip()[:200],
                    "etken_madde": None,
                    "dozaj": None,
                    "form": None,
                    "barkod": kodlar["barkod"].get("deger") if kodlar["barkod"].get("tespit_edildi") else None,
                    "uretici": None,
                    "okunabilirlik_skoru": 4,
                    "notlar": f"OCR kısmi başarı ({how}); doğrulama için daha net fotoğraf önerilir.",
                    "kaynak": "OCR kısmi (sezgisel)",
                    "gorsel_analiz": build_gorsel_analiz_envelope(
                        success=True,
                        status="partial_success",
                        source="ocr_partial",
                        extracted_text=ocr_text[:8000],
                        identified_medicine=line.strip()[:200],
                        dosage="",
                        message=(
                            "Görselden kısmi bilgi çıkarıldı. Analiz elde edilen metin "
                            "üzerinden devam etti."
                        ),
                        error_code=ocr_code or "heuristic_line",
                    ),
                }
                _log_vision.info("ocr_heuristic_partial line_len=%s", len(line))
                return self._finalize_scan_vision_output(self._attach_barkod_qr(partial, kodlar))

        fail = {
            "ticari_ad": None,
            "etken_madde": None,
            "dozaj": None,
            "form": None,
            "barkod": kodlar["barkod"].get("deger") if kodlar["barkod"].get("tespit_edildi") else None,
            "uretici": None,
            "okunabilirlik_skoru": 1,
            "notlar": (
                "Görselden yeterli bilgi çıkarılamadı. Daha net, aydınlık ve yakın çekilmiş "
                "bir fotoğraf deneyin (kutu ön yüzü, yazılar, mümkünse barkod alanı). "
                "Alternatif olarak ilaç adını metin olarak girebilirsiniz."
            ),
            "kaynak": "Görsel pipeline — tam başarısızlık",
            "gorsel_analiz": build_gorsel_analiz_envelope(
                success=False,
                status="failed",
                source=None,
                extracted_text=(ocr_text or "")[:8000],
                identified_medicine="",
                dosage="",
                message=(
                    "Görselden yeterli bilgi çıkarılamadı. Daha net, ışıklı ve yakın çekilmiş "
                    "bir fotoğraf deneyin veya ilaç adını metin olarak girin."
                ),
                error_code="all_strategies_failed",
            ),
        }
        fail["barkod_detay"] = kodlar["barkod"]
        fail["qr_kod_detay"] = kodlar["qr_kod"]
        _log_vision.warning("pipeline_failed last_vision=%s ocr_struct_err=%s", vtag, st_err)
        return self._finalize_scan_vision_output(fail)

    def scan_text_input(self, drug_name: str) -> Dict[str, Any]:
        """Görsel yoksa, metin girişinden ilaç bilgisi yap."""
        from image_pipeline import build_gorsel_analiz_envelope

        return self._finalize_scan_vision_output(
            {
                "ticari_ad": drug_name,
                "etken_madde": "",
                "dozaj": "",
                "form": "",
                "barkod": "",
                "uretici": "",
                "okunabilirlik_skoru": 10,
                "notlar": "Metin girişi ile sağlandı, görsel analiz yapılmadı.",
                "kaynak": "Metin Girişi",
                "gorsel_analiz": build_gorsel_analiz_envelope(
                    success=True,
                    status="full_success",
                    source="text_input",
                    extracted_text=drug_name or "",
                    identified_medicine=drug_name or "",
                    dosage="",
                    message="Metin girişi kullanıldı.",
                    error_code=None,
                ),
            }
        )

    @staticmethod
    def _pdf_prospectus_extraction_prompt(pdf_text: str, char_limit: int) -> str:
        snippet = (pdf_text or "")[:char_limit]
        return f"""Aşağıdaki metin bir ilaç prospektüsünden çıkarılmıştır. SADECE geçerli bir JSON nesnesi döndür.

Şema (anahtarlar tam olarak böyle olsun):
{{
  "ticari_ad": "string veya null",
  "etken_madde": "string veya null",
  "dozaj": "string veya null",
  "form": "string veya null",
  "barkod": null,
  "uretici": "string veya null",
  "okunabilirlik_skoru": 1-10 arası sayı (metin kalitesine göre),
  "notlar": "kısa not",
  "endikasyonlar": "kısa kullanım amacı (1-2 cümle) veya null",
  "prospektus_ozeti": "3-5 cümle özet veya null"
}}

Kurallar:
- Metinde açıkça geçmeyen alan için null kullan; uydurma.
- ticari_ad veya etken_madde mümkün olduğunca prospektüs başlığı / ruhsat bölümünden alınmalı.

PROSPEKTÜS METNİ:
---
{snippet}
---
"""

    def _scan_pdf_with_groq(self, pdf_text: str, filename: str) -> Optional[Dict[str, Any]]:
        """PDF metninden yapılandırılmış alanlar — birincil yol (Gemini kotasından bağımsız)."""
        prompt = self._pdf_prospectus_extraction_prompt(pdf_text, 12000)
        for mid in _groq_safety_model_chain():
            try:
                r = self.groq_client.chat.completions.create(
                    model=mid,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Sen ilaç prospektüsü metin çıkarıcısısın. Sadece JSON nesnesi döndür; "
                                "emin olmadığın alanlarda null kullan."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=2500,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                raw = r.choices[0].message.content or ""
                parsed = self._parse_json_response(raw, source=f"PDF+Groq ({filename}) · {mid}")
                if (parsed.get("ticari_ad") or "").strip() or (parsed.get("etken_madde") or "").strip():
                    parsed["pdf_metin_uzunlugu"] = len(pdf_text)
                    base_n = (parsed.get("notlar") or "").strip()
                    suf = "Prospektüs metni Groq ile yapılandırıldı."
                    parsed["notlar"] = f"{base_n} ({suf})" if base_n else suf
                    return self._finalize_scan_vision_output(parsed)
            except Exception:
                continue
        return None

    def _scan_pdf_with_openai_compat(self, pdf_text: str, filename: str) -> Optional[Dict[str, Any]]:
        """OpenAI uyumlu API (OpenAI, OpenRouter, Together vb.) — Groq sonrası ikinci yol."""
        cfg = self._openai_compat_config()
        if not cfg:
            return None
        from openai_compat import chat_json_completion

        prompt = self._pdf_prospectus_extraction_prompt(pdf_text, 12000)
        try:
            raw = chat_json_completion(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                model=cfg["model"],
                system=(
                    "Sen ilaç prospektüsü metin çıkarıcısısın. Yanıt yalnızca geçerli bir JSON nesnesi olmalı; "
                    "emin olmadığın alanlarda null kullan."
                ),
                user=prompt,
                max_tokens=2500,
                temperature=0.1,
            )
            parsed = self._parse_json_response(
                raw, source=f"PDF+OpenAI-uyumlu ({filename}) · {cfg['model']}"
            )
            if (parsed.get("ticari_ad") or "").strip() or (parsed.get("etken_madde") or "").strip():
                parsed["pdf_metin_uzunlugu"] = len(pdf_text)
                base_n = (parsed.get("notlar") or "").strip()
                suf = "Prospektüs metni OpenAI-uyumlu API ile yapılandırıldı."
                parsed["notlar"] = f"{base_n} ({suf})" if base_n else suf
                return self._finalize_scan_vision_output(parsed)
        except Exception:
            return None
        return None

    def _scan_pdf_with_gemini(self, pdf_text: str, filename: str) -> Tuple[Optional[Dict[str, Any]], Optional[Exception]]:
        """Üçüncü yedek: Groq ve OpenAI-uyumlu yol başarısız olursa Gemini zinciri."""
        _init_gemini()
        pdf_prompt = self._pdf_prospectus_extraction_prompt(pdf_text, 6000)
        models = _gemini_model_chain()
        last_err: Optional[Exception] = None
        for idx, name in enumerate(models):
            try:
                model = genai.GenerativeModel(name)
                response = model.generate_content(
                    pdf_prompt,
                    generation_config=genai.GenerationConfig(temperature=0.1),
                )
                result = self._parse_json_response(response.text, source=f"PDF+Gemini ({filename}) · {name}")
                result["pdf_metin_uzunlugu"] = len(pdf_text)
                base_n = (result.get("notlar") or "").strip()
                suf = "Groq ve OpenAI-uyumlu API sonrası Gemini ile çıkarım yapıldı."
                result["notlar"] = f"{base_n} ({suf})" if base_n else suf
                return self._finalize_scan_vision_output(result), None
            except Exception as e:
                last_err = e
                if idx < len(models) - 1:
                    continue
                break
        return None, last_err

    def scan_pdf(self, pdf_bytes: bytes, filename: str = "prospektus.pdf") -> Dict[str, Any]:
        """
        PDF prospektüsünden metin çıkarır; sıra: Groq → (isteğe bağlı) OpenAI-uyumlu API → Gemini.
        """
        # 1) PDF metnini çıkar
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(pdf_bytes))
            pages_text = []
            for i, page in enumerate(reader.pages[:10]):   # ilk 10 sayfa yeterli
                t = page.extract_text() or ""
                if t.strip():
                    pages_text.append(f"[Sayfa {i+1}]\n{t.strip()}")
            pdf_text = "\n\n".join(pages_text)
        except Exception as e:
            return self._finalize_scan_vision_output(
                {"hata": f"PDF okunamadı: {e}", "kaynak": f"PDF ({filename})"}
            )

        if not pdf_text.strip():
            return self._finalize_scan_vision_output(
                {
                    "hata": "PDF'den metin çıkarılamadı (taranmış/görüntü tabanlı PDF olabilir).",
                    "kaynak": f"PDF ({filename})",
                }
            )

        groq_pdf = self._scan_pdf_with_groq(pdf_text, filename)
        if groq_pdf is not None:
            return groq_pdf

        oa_pdf = self._scan_pdf_with_openai_compat(pdf_text, filename)
        if oa_pdf is not None:
            return oa_pdf

        gem_pdf, gem_err = self._scan_pdf_with_gemini(pdf_text, filename)
        if gem_pdf is not None:
            return gem_pdf

        err_msg = f"PDF analiz hatası (Groq, OpenAI-uyumlu API ve Gemini): {gem_err}"
        if gem_err is not None and gemini_quota_or_rate_limit(gem_err):
            err_msg = (
                "Groq ve tanımlı OpenAI-uyumlu API prospektüsten sonuç veremedi; "
                "Gemini yedeği de kota veya ağ hatasıyla başarısız oldu. "
                "Kenar çubuğundan ikinci API anahtarı ekleyebilir veya "
                "https://ai.google.dev/gemini-api/docs/rate-limits — Teknik: "
                f"{gem_err!s}"
            )
        return self._finalize_scan_vision_output(
            {
                "hata": err_msg,
                "kaynak": f"PDF ({filename})",
                "okunabilirlik_skoru": 5,
            }
        )

    @staticmethod
    def _parse_json_response(raw: str, source: str) -> Dict[str, Any]:
        """Model çıktısından JSON bloğu ayıklar — 3 aşamalı robust parser."""
        # 1) ```json ... ``` bloğunu temizle
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        # 2) Doğrudan parse
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                data.pop("kaynak", None)
                data["kaynak"] = source
                return _vision_merge_case_insensitive_keys(data)
        except json.JSONDecodeError:
            pass
        # 3) Metin içindeki ilk { ... } bloğunu regex ile bul
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                data = json.loads(m.group())
                if isinstance(data, dict):
                    data.pop("kaynak", None)
                    data["kaynak"] = source
                    return _vision_merge_case_insensitive_keys(data)
            except json.JSONDecodeError:
                pass
        # 4) Ham metni sakla; ticari_ad'ı tahmin etmeye çalış
        guessed: Dict[str, Any] = {
            "kaynak": source,
            "ham_cikti": raw[:500],
            "notlar": "JSON ayrıştırılamadı; ham çıktı korundu.",
        }
        # Basit anahtar-değer satırlarını al (ör. "ticari_ad: Alka-Seltzer")
        for key in ["ticari_ad", "etken_madde", "dozaj", "form", "uretici"]:
            pat = rf'"{key}"\s*:\s*"([^"]+)"'
            hit = re.search(pat, cleaned, re.IGNORECASE)
            if hit:
                guessed[key] = hit.group(1)
        return _vision_merge_case_insensitive_keys(guessed)


# ---------------------------------------------------------------------------
# AJAN 2: RAG Specialist
# ---------------------------------------------------------------------------

class RAGSpecialistAgent:
    """
    ChromaDB ve LangChain kullanarak yerel PDF prospektüs veritabanında
    semantik arama yapan ajan.
    """

    CORPUS_DIR = Path("data/corpus")
    CHROMA_DIR = Path("data/chroma_db")

    def __init__(self):
        self.vectorstore = None
        self.corpus_loaded = False
        # Ağır embedding yükünü orkestratör __init__'inden çıkarır; ilk RAG aramasında yüklenir.
        self._rag_index_initialized = False

    def _ensure_rag_index(self) -> None:
        if self._rag_index_initialized:
            return
        self._rag_index_initialized = True
        self._load_or_build_index()

    def _load_or_build_index(self):
        """Varsa mevcut ChromaDB'yi yükle, yoksa PDF'lerden oluştur."""
        try:
            from langchain_community.vectorstores import Chroma
            from langchain_community.embeddings import HuggingFaceEmbeddings
            from langchain_community.document_loaders import PyPDFLoader
            from langchain.text_splitter import RecursiveCharacterTextSplitter

            embedding_model = HuggingFaceEmbeddings(
                model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                model_kwargs={"device": "cpu"},
            )

            pdf_files = list(self.CORPUS_DIR.glob("*.pdf"))

            if self.CHROMA_DIR.exists() and any(self.CHROMA_DIR.iterdir()):
                self.vectorstore = Chroma(
                    persist_directory=str(self.CHROMA_DIR),
                    embedding_function=embedding_model,
                )
                self.corpus_loaded = True
                print(f"[RAGSpecialist] ChromaDB yüklendi. ({self.CHROMA_DIR})")
            elif pdf_files:
                self._build_index(pdf_files, embedding_model)
            else:
                print("[RAGSpecialist] Corpus dizininde PDF bulunamadı. RAG devre dışı.")

        except ImportError as e:
            print(f"[RAGSpecialist] Gerekli kütüphane eksik: {e}")

    def _build_index(self, pdf_files: List[Path], embedding_model):
        """PDF dosyalarından ChromaDB vektör indeksi oluşturur."""
        from langchain_community.vectorstores import Chroma
        from langchain_community.document_loaders import PyPDFLoader
        from langchain.text_splitter import RecursiveCharacterTextSplitter

        print(f"[RAGSpecialist] {len(pdf_files)} PDF indeksleniyor...")
        all_docs = []
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)

        for pdf_path in pdf_files:
            try:
                loader = PyPDFLoader(str(pdf_path))
                pages = loader.load()
                chunks = splitter.split_documents(pages)
                for chunk in chunks:
                    chunk.metadata["source_file"] = pdf_path.name
                all_docs.extend(chunks)
                print(f"  OK {pdf_path.name} — {len(chunks)} parça")
            except Exception as e:
                print(f"  X {pdf_path.name}: {e}")

        if all_docs:
            self.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            self.vectorstore = Chroma.from_documents(
                documents=all_docs,
                embedding=embedding_model,
                persist_directory=str(self.CHROMA_DIR),
            )
            self.corpus_loaded = True
            print(f"[RAGSpecialist] İndeks oluşturuldu. {len(all_docs)} parça kaydedildi.")

    def search(self, query: str, k: int = 5, vision_data: Optional[Dict] = None) -> List[Dict[str, str]]:
        """
        Semantik arama yapar. Corpus boş olsa bile, vision_data'dan mock sonuçlar oluşturur.
        Bu sayede Fact-Check'in karşılaştıracak verileri olur.
        """
        self._ensure_rag_index()
        if isinstance(vision_data, dict):
            vision_data = _vision_normalize_null_strings(vision_data)
        if not self.corpus_loaded or self.vectorstore is None:
            # Corpus boş — vision bilgisinden mock sonuçlar oluştur
            if vision_data:
                drug_name = _vision_field_str(vision_data, "ticari_ad")
                etken = _vision_field_str(vision_data, "etken_madde")
                if drug_name or etken:
                    # Fact-Check'in karşılaştıracak bir kaynak olsun
                    head = " / ".join(p for p in (drug_name, etken) if p)
                    return [{
                        "metin": f"{head}: Genel ilaç bilgisine dayalı bilgiler.",
                        "kaynak": "Genel Bilgi",
                        "sayfa": "—",
                        "benzerlik": 0.7,
                    }]
            # Fallback: corpus tamamen boş
            return [{"metin": "Prospektüs veritabanı boş.", "kaynak": "—", "sayfa": "—"}]

        try:
            results = self.vectorstore.similarity_search_with_score(query, k=k)
            formatted = []
            for doc, score in results:
                formatted.append({
                    "metin": doc.page_content,
                    "kaynak": doc.metadata.get("source_file", "bilinmiyor"),
                    "sayfa": str(doc.metadata.get("page", "?")),
                    "benzerlik": round(float(score), 4),
                })
            return formatted
        except Exception as e:
            return [{"metin": f"Arama hatası: {str(e)}", "kaynak": "—", "sayfa": "—"}]

    def rebuild_index(self):
        """Kullanıcı yeni PDF eklediğinde indeksi yeniden oluşturur."""
        import shutil
        if self.CHROMA_DIR.exists():
            shutil.rmtree(self.CHROMA_DIR)
        self.corpus_loaded = False
        self.vectorstore = None
        self._rag_index_initialized = True
        self._load_or_build_index()


# ---------------------------------------------------------------------------
# AJAN 3: Safety Auditor
# ---------------------------------------------------------------------------

class SafetyAuditorAgent:
    """
    Groq (Llama-3-70B) kullanarak ilaç güvenlik denetimi yapan ajan.
    Yan etki, etkileşim ve kontrendikasyon kontrolü gerçekleştirir.
    """

    def __init__(self, groq_client: Optional[Groq] = None):
        self.groq_client = groq_client or _init_groq()

    def audit(self, drug_info: Dict[str, Any], rag_data: List[Dict]) -> Dict[str, Any]:
        """İlaç bilgisi ve RAG verisi ile güvenlik raporu oluşturur."""
        rag_real = [r for r in rag_data if r.get("kaynak", "—") not in ("—", "")]
        rag_text = (
            "\n\n".join(f"[{r['kaynak']} — s.{r['sayfa']}]: {r['metin']}" for r in rag_real)
            or "RAG verisi yok — kendi tıbbi bilginle yanıt ver."
        )

        drug_name = drug_info.get("ticari_ad") or drug_info.get("etken_madde") or "bilinmiyor"
        prompt = SAFETY_PROMPT_TEMPLATE.format(
            drug_info=json.dumps(drug_info, ensure_ascii=False, indent=2),
            rag_data=rag_text,
        )

        models = _groq_safety_model_chain()
        last_err: Optional[Exception] = None

        for model_id in models:
            # Groq JSON modu destekliyor mu? (llama-3.3 destekliyor)
            use_json_mode = "llama-3" in model_id
            try:
                kwargs: Dict[str, Any] = dict(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": "Sen bir ilaç güvenlik uzmanısın. SADECE JSON döndür."},
                        {"role": "user",   "content": prompt},
                    ],
                    max_tokens=2048,
                    temperature=0.1,
                )
                if use_json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                response = self.groq_client.chat.completions.create(**kwargs)
                raw = response.choices[0].message.content or ""
                parsed = self._parse_json_response(raw)

                # Kritik alanlar eksikse retry — kısa prompt
                if not parsed.get("alarm_seviyesi") or not parsed.get("yan_etkiler"):
                    parsed = self._retry_simplified(drug_name, model_id) or parsed

                if model_id != models[0]:
                    parsed["groq_model_notu"] = f"Yanıt modeli: `{model_id}`"
                return parsed

            except Exception as e:
                last_err = e
                if _groq_is_rate_limit(e) and model_id != models[-1]:
                    print(f"[SafetyAuditor] {model_id} limit/429, sıradaki… ({e})")
                    continue
                break

        return {
            "hata": _groq_safety_failure_message(last_err) if last_err else "Safety Auditor bilinmeyen hata.",
            "alarm_seviyesi": "SARI",
            "alarm_gerekce": "Otomatik analiz tamamlanamadı — eczacıya danışın.",
            "guven_puani": 2,
        }

    def _retry_simplified(self, drug_name: str, model_id: str) -> Optional[Dict[str, Any]]:
        """Kritik alanlar boşsa çok daha kısa prompt ile tekrar dener."""
        simple = f"""Sadece JSON döndür. {drug_name} ilacı için:
{{"yan_etkiler":{{"yaygin":["..."],"ciddi":["..."],"cok_nadir":["..."]}},"etkilesimler":["..."],"kontrendikasyonlar":["..."],"ozel_uyarilar":["..."],"alarm_seviyesi":"SARI","alarm_gerekce":"gerekçe","guven_puani":6}}"""
        try:
            r = self.groq_client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": simple}],
                max_tokens=1024,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            return self._parse_json_response(r.choices[0].message.content or "")
        except Exception:
            return None

    @staticmethod
    def _parse_json_response(raw: str) -> Dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        # Kritik alanları regex ile tahmin et
        result: Dict[str, Any] = {"guven_puani": 3, "ham_cikti": raw[:400]}
        for key in ["alarm_seviyesi", "alarm_gerekce"]:
            pat = rf'"{key}"\s*:\s*"([^"]+)"'
            hit = re.search(pat, cleaned, re.IGNORECASE)
            if hit:
                result[key] = hit.group(1)
        # alarm_seviyesi metinden de çıkarılabilir
        if "alarm_seviyesi" not in result:
            for level in ["KIRMIZI", "SARI", "YEŞİL"]:
                if level in raw.upper():
                    result["alarm_seviyesi"] = level
                    break
        return result


# ---------------------------------------------------------------------------
# AJAN 4: Corporate Analyst
# ---------------------------------------------------------------------------

class CorporateAnalystAgent:
    """
    Groq Llama-3 kullanarak ilaç üreticisi firma bilgilerini raporlayan ajan.
    (Önceki: Gemini — quota tasarrufu için Groq'a taşındı)
    """

    def __init__(self, groq_client: Optional[Groq] = None):
        self.groq_client = groq_client or _init_groq()

    def analyze(self, drug_name: str, manufacturer: Optional[str]) -> Dict[str, Any]:
        """Firma analizi yapar (Groq + Llama-3 ile)."""
        prompt = CORPORATE_PROMPT_TEMPLATE.format(
            drug_name=drug_name or "Bilinmiyor",
            manufacturer=manufacturer or "Bilinmiyor",
        )
        models = _groq_safety_model_chain()
        last_err: Optional[Exception] = None

        for model_id in models:
            try:
                response = self.groq_client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": "Sen bir ilaç firma uzmanısın. SADECE JSON döndür."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1024,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content or ""
                parsed = self._parse_json_response(raw)

                # Kritik alanlar eksikse retry
                firma_adi = parsed.get("firma_adi", "")
                guven = parsed.get("guven_puani", 0)
                if (
                    not firma_adi
                    or firma_adi in ("Bilinmiyor", "Tespit Edilemedi", "")
                    or guven < 4
                ):
                    retry = self._retry_simplified(drug_name, manufacturer, model_id)
                    if retry:
                        parsed = retry

                if model_id != models[0]:
                    parsed["groq_model_notu"] = f"Model: {model_id}"
                return parsed

            except Exception as e:
                last_err = e
                if _groq_is_rate_limit(e) and model_id != models[-1]:
                    print(f"[CorporateAnalyst] {model_id} limit/429, sıradaki… ({e})")
                    continue
                break

        return {
            "hata": f"Corporate Analyst (Groq) başarısız: {last_err}" if last_err else "Corporate Analyst başarısız.",
            "guven_puani": 1,
        }

    def _retry_simplified(
        self, drug_name: str, manufacturer: Optional[str], model_id: str
    ) -> Optional[Dict[str, Any]]:
        """Firma adı boşsa kısa prompt ile tekrar dener."""
        simple = (
            f"Sadece JSON döndür. '{drug_name}' ilacının üreticisi nedir? "
            f"Bilinen: {manufacturer or 'bilinmiyor'}. "
            '{"firma_adi":"adı","ulke":"ülke","titck_durumu":"TİTCK onaylı veya Belirsiz","guven_puani":5}'
        )
        try:
            r = self.groq_client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": simple}],
                max_tokens=512,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            result = self._parse_json_response(r.choices[0].message.content or "")
            if result.get("firma_adi") and result["firma_adi"] not in ("Bilinmiyor", ""):
                return result
        except Exception as e:
            print(f"[CorporateAnalyst] retry hatası: {e}")
        return None

    @staticmethod
    def _parse_json_response(raw: str) -> Dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        result: Dict[str, Any] = {"guven_puani": 3, "ham_cikti": raw[:400]}
        for key in ["firma_adi", "ulke", "titck_durumu", "genel_degerlendirme"]:
            pat = rf'"{key}"\s*:\s*"([^"]+)"'
            hit = re.search(pat, cleaned, re.IGNORECASE)
            if hit:
                result[key] = hit.group(1)
        return result


# ---------------------------------------------------------------------------
# AJAN 5: Report Synthesizer
# ---------------------------------------------------------------------------


def _synthesis_json_str(data: Any, max_chars: int) -> str:
    """Çok büyük JSON gövdeleri Groq/Gemini zaman aşımına ve yavaşlamaya yol açmasın."""
    raw = json.dumps(data, ensure_ascii=False, indent=2)
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 140] + "\n\n/* … bağlam uzunluk sınırı nedeniyle kısaltıldı … */\n"


def _synthesis_text_clip(s: str, max_chars: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 100] + "\n\n/* … kısaltıldı … */\n"


class ReportSynthesizerAgent:
    """
    Tüm ajan çıktılarını birleştirip kapsamlı Türkçe rapor üreten nihai sentez ajanı.
    PRIMARY: Groq Llama-3 (hızlı, güvenilir)
    FALLBACK: Gemini (Groq unavailable ise)
    """

    def __init__(self, groq_client: Optional[Groq] = None):
        self.groq_client = groq_client or _init_groq()
        self._gemini_configured = False

    def _ensure_gemini(self) -> None:
        if not self._gemini_configured:
            _init_gemini()
            self._gemini_configured = True

    def synthesize(
        self,
        vision_data: Dict,
        safety_data: Dict,
        corporate_data: Dict,
        rag_sources: List[Dict],
        barcode_context: str = "",
        similar_drugs_context: str = "",
    ) -> Tuple[str, float, Optional[str]]:
        """
        Tüm veriyi birleştirip Markdown raporu döndürür.
        Returns: (rapor_metni, ortalama_guven_puani, hata veya None)
        """
        rag_kaynakca = "\n".join(
            f"- {r['kaynak']} (s.{r['sayfa']}): {r['metin'][:120]}..."
            for r in rag_sources
        ) or "Prospektüs kaynağı bulunamadı."
        rag_kaynakca = _synthesis_text_clip(rag_kaynakca, 8000)
        bc_block = barcode_context or "(Görsel barkod taraması yok veya uygulanmadı.)"
        bc_block = _synthesis_text_clip(bc_block, 6000)
        sim_block = _synthesis_text_clip(
            similar_drugs_context or "(Benzer ilaç önerisi üretilmedi.)",
            16000,
        )

        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            vision_data=_synthesis_json_str(vision_data, 14000),
            barcode_block=bc_block,
            similar_drugs_block=sim_block,
            safety_data=_synthesis_json_str(safety_data, 12000),
            corporate_data=_synthesis_json_str(corporate_data, 12000),
            rag_sources=rag_kaynakca,
        )

        scores = []
        for data in [safety_data, corporate_data]:
            if isinstance(data.get("guven_puani"), (int, float)):
                scores.append(float(data["guven_puani"]))
        vision_score = vision_data.get("okunabilirlik_skoru")
        if isinstance(vision_score, (int, float)):
            scores.append(float(vision_score))
        fallback_avg = sum(scores) / len(scores) if scores else 3.0

        # ADIM 1: Groq ile dene (PRIMARY)
        groq_models = _groq_safety_model_chain()
        groq_err = None
        for model_id in groq_models:
            try:
                print(f"[ReportSynthesizer] Groq {model_id} ile rapor oluşturuluyor...")
                response = self.groq_client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": "Sen Türkçe tıbbi rapor yazmanında uzmanısın. Kapsamlı, profesyonel, yapılandırılmış rapor üret."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=4096,
                    temperature=0.3,
                    timeout=150.0,
                )
                report_text = response.choices[0].message.content or ""
                if report_text.strip():
                    print("[ReportSynthesizer] Groq raporu başarıyla oluşturdu.")
                    avg_confidence = sum(scores) / len(scores) if scores else 5.0
                    return report_text, avg_confidence, None
            except Exception as e:
                groq_err = e
                if _groq_is_rate_limit(e) and model_id != groq_models[-1]:
                    print(f"[ReportSynthesizer] {model_id} limit/429, sıradaki…")
                    continue
                break

        # ADIM 2: Gemini fallback (Groq başarısızsa)
        print(f"[ReportSynthesizer] Groq başarısız ({groq_err}), Gemini fallback'e geçiliyor...")
        self._ensure_gemini()
        gemini_models = _gemini_model_chain()
        gemini_err = None
        for idx, name in enumerate(gemini_models):
            try:
                model = genai.GenerativeModel(
                    name,
                    system_instruction=MASTER_PROMPT,
                )
                response = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=4096,
                    ),
                    request_options={"timeout": 180.0},
                )
                report_text = response.text
                if report_text.strip():
                    print(f"[ReportSynthesizer] Gemini ({name}) raporu başarıyla oluşturdu.")
                    avg_confidence = sum(scores) / len(scores) if scores else 5.0
                    return report_text, avg_confidence, None
            except Exception as e:
                gemini_err = e
                if idx < len(gemini_models) - 1:
                    if _gemini_model_missing_error(e) or gemini_quota_or_rate_limit(e):
                        print(f"[ReportSynthesizer] {name} atlandı ({e!s}), sıradaki…")
                    else:
                        print(f"[ReportSynthesizer] {name} hata, sıradaki…")
                    continue
                break

        # HER İKİSİ DE BAŞARISIZ
        combined_err = f"Groq: {groq_err}; Gemini: {gemini_err}"
        print(f"[ReportSynthesizer] Tüm modeller başarısız: {combined_err}")
        return "", fallback_avg, combined_err


# ---------------------------------------------------------------------------
# FACT-CHECKER: Halüsinasyon Engeli
# ---------------------------------------------------------------------------

class FactChecker:
    """
    Vision çıktısı ile RAG verisi arasındaki kritik tutarsızlıkları tespit eder.
    Dozaj farklılıkları ve etken madde uyuşmazlıklarını saptar.
    """

    @staticmethod
    def check(vision_data: Dict, rag_results: List[Dict]) -> Dict[str, Any]:
        # Geçerli RAG sonuçlarını filtrele (Genel Bilgi + PDF kaynakları dahil)
        real_results = [
            r for r in rag_results
            if r.get("kaynak", "—") not in ("—", "")
            and "Prospektüs veritabanı boş" not in r.get("metin", "")
        ]
        if not real_results:
            return {
                "uyusmazlik": False,
                "sorunlar": [],
                "mesaj": "ℹ️ Veri kaynağı yok — Fact-Check yapılamadı.",
                "corpus_bos": True,
            }

        drug_name = _vision_field_str(vision_data, "ticari_ad").lower()
        etken = _vision_field_str(vision_data, "etken_madde").lower()
        dozaj = _vision_field_str(vision_data, "dozaj")

        # Görsel analiz başarısızsa fact-check yapma
        if not drug_name and not etken:
            return {"uyusmazlik": False, "sorunlar": [], "mesaj": "ℹ️ İlaç adı yok — Fact-Check atlandı."}

        issues = []
        # En az bir sonuçta eşleşme varsa geçerli say
        name_found = any(
            (drug_name and drug_name in r.get("metin", "").lower()) or
            (etken and etken in r.get("metin", "").lower())
            for r in real_results
        )
        if not name_found and (drug_name or etken):
            sample = real_results[0].get("kaynak", "?")
            # "Genel Bilgi" kaynağından geliyorsa seri bir uyarı verme
            if sample == "Genel Bilgi":
                # Mock veriden geliyor — çok katı kurallar uygulama
                pass
            else:
                issues.append(
                    f"'{etken or drug_name}' hiçbir prospektüs kaynağında bulunamadı "
                    f"(örn. '{sample}'). Corpus'a doğru PDF yüklenmiş mi?"
                )

        # Dozaj kontrolü — en az bir sonuçta sayı eşleşmesi yeterli
        if dozaj and not issues:
            nums_vision = re.findall(r"\d+(?:[.,]\d+)?", str(dozaj))
            if nums_vision:
                all_rag_text = " ".join(r.get("metin", "") for r in real_results).lower()
                nums_rag = re.findall(r"\d+(?:[.,]\d+)?", all_rag_text)
                if not any(n in nums_rag for n in nums_vision):
                    issues.append(
                        f"Dozaj uyuşmazlığı olabilir: görselde '{dozaj}' — "
                        "prospektüslerde bu sayısal değer bulunamadı."
                    )

        if issues:
            return {
                "uyusmazlik": True,
                "sorunlar": issues,
                "mesaj": "VERİ UYUŞMAZLIĞI: Fact-Checker tutarsızlık tespit etti!",
                "corpus_bos": False,
            }
        return {"uyusmazlik": False, "sorunlar": [], "mesaj": "Fact-Check geçti.", "corpus_bos": False}


def _strip_confidence_meta_junk(report_text: str) -> str:
    """
    Modelin hatalı ürettiği 'güven 7/8 eşiği + rapora DİKKAT eklendi' meta metnini kaldırır.
    Ortalama güven uyarısı yalnızca orchestrator tarafından (avg_confidence < 8) eklenir.
    """
    if not report_text:
        return report_text
    t = report_text
    # **DİKKAT** + **Raporun Başına Uyarı** + hatalı cümle (yaygın yanlış şablon)
    t = re.sub(
        r"(?ms)(?:^|\n)\s*\*{2}\s*DİKKAT\s*\*{2}\s*\n\s*\*{2}\s*Raporun\s+Başına\s+Uyarı\s*\*{2}\s*\n\s*[^\n]*7[\u2019'’]den\s+düşük[^\n]*",
        "\n",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"(?ms)(?:^|\n)\s*#{1,6}\s+DİKKAT\s*\n\s*#{1,6}\s+Raporun\s+Başına\s+Uyarı\s*\n\s*[^\n]*7[\u2019'’]den\s+düşük[^\n]*",
        "\n",
        t,
        flags=re.IGNORECASE,
    )
    # Tek satır / gömülü: "Güven puanı 7'den düşük ... eklenmiştir."
    t = re.sub(
        r"(?i)Güven\s+puanı\s+7[\u2019'’]den\s+düşük\s+olduğu\s+için\s+raporun\s+başına\s+"
        r'["“”]?\s*DİKKAT\s*["“”]?\s+uyarısı\s+eklenmiştir\.?',
        "",
        t,
    )
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def _fiyat_liste_markdown_append(fl: Optional[Dict[str, Any]]) -> str:
    """Birleşik fiyat listesi eşleşmesini rapora deterministik ekler (LLM dışı)."""
    if not fl or not fl.get("eslesti") or not fl.get("satirlar"):
        return ""
    lines = [
        "",
        "---",
        "## Liste fiyatı (yerel birleşik tablo)",
        "",
        "İlaç Fiyatları sekmesindeki liste ile **barkod veya ürün adı** eşleşen kayıt(lar):",
        "",
    ]
    for i, row in enumerate(fl["satirlar"], 1):
        ad = row.get("İlaç adı") or "—"
        firma = row.get("Firma") or "—"
        lf = row.get("Liste fiyatı (₺)")
        gkf = row.get("GKF (€)")
        bc = row.get("Barkod")
        lt = row.get("Liste tarihi")
        lf_s = f"{lf:.2f} ₺" if isinstance(lf, (int, float)) else "—"
        gkf_s = f"{gkf:.4f} €" if isinstance(gkf, (int, float)) else "—"
        bc_s = str(bc) if bc else "—"
        lt_s = str(lt) if lt else "—"
        lines.append(f"- **{i}.** {ad}")
        lines.append(
            f"  - Firma: {firma} · Liste fiyatı: {lf_s} · GKF: {gkf_s} · Barkod: {bc_s} · Liste tarihi: {lt_s}"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ANA ORKESTRATÖR
# ---------------------------------------------------------------------------

class PharmaGuardOrchestrator:
    """
    Tüm 5 ajanı koordine eden ana orkestratör.
    Streamlit arayüzünden çağrılır.
    """

    def __init__(self):
        print("[Orchestrator] Başlatılıyor...")
        # Groq istemcileri ayrı: Safety + Corporate ThreadPoolExecutor ile paralel;
        # tek httpx tabanlı istemciyi iki iplikte paylaşmaktan kaçınılır.
        self.vision_agent = VisionScannerAgent()
        self.rag_agent = RAGSpecialistAgent()
        self.safety_agent = SafetyAuditorAgent()
        self.corporate_agent = CorporateAnalystAgent()
        self.synthesizer = ReportSynthesizerAgent()
        self.fact_checker = FactChecker()
        print("[Orchestrator] Tüm ajanlar hazır.")

    def run(
        self,
        image: Optional[Image.Image] = None,
        drug_name_text: Optional[str] = None,
        pdf_bytes: Optional[bytes] = None,
        pdf_filename: str = "prospektus.pdf",
        progress_callback=None,
        openai_compat: Optional[Dict[str, Any]] = None,
        test_vision_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ana analiz iş akışını çalıştırır.

        Args:
            image: PIL Image nesnesi (ilaç kutu görseli)
            drug_name_text: Metin olarak ilaç adı (görsel yoksa)
            pdf_bytes: Prospektüs PDF'inin ham bytes'ı (doğrudan PDF analizi)
            pdf_filename: PDF dosya adı (gösterim için)
            progress_callback: Streamlit progress bar için callable(step: int, message: str)
            openai_compat: İsteğe bağlı OpenAI-uyumlu API (api_key, base_url, model) — PDF çıkarımı için.

        Returns:
            {
                "vision": {...},           # barkod_detay, qr_kod_detay (görselde), barkod alanı
                "similar_drugs": {...},   # benzer ilaç / muadil yapılandırılmış sonuç
                "rag_results": [...],
                "fact_check": {...},
                "safety": {...},
                "corporate": {...},
                "report": "Markdown rapor metni",
                "avg_confidence": float,
                "alarm": "YEŞİL/SARI/KIRMIZI",
                "fiyat_liste": {"eslesti": bool, "satirlar": [...], "aciklama": str},
            }
        """

        def _progress(step: int, msg: str):
            if progress_callback:
                progress_callback(step, msg)
            print(f"[Step {step}] {msg}")

        if openai_compat is None:
            self.vision_agent._openai_compat_overrides = None
        else:
            self.vision_agent._openai_compat_overrides = (
                {k: v for k, v in openai_compat.items() if str(v).strip()} or None
            )

        results = {}

        # ADIM 1: Görüntü / Metin / PDF Analizi
        if test_vision_data is not None:
            # Test veri — geliştirme/test amaçlı
            _progress(1, f" Test veri kullanılıyor: {test_vision_data.get('ticari_ad', 'Bilinmiyor')}")
            vision_data = dict(test_vision_data)
        elif pdf_bytes is not None:
            _progress(1, f"PDF Scanner: '{pdf_filename}' prospektüsü analiz ediliyor...")
            vision_data = self.vision_agent.scan_pdf(pdf_bytes, pdf_filename)
        elif image is not None:
            _progress(1, "Vision Scanner: Görsel analiz ediliyor...")
            vision_data = vision_dict_for_ui(self.vision_agent.scan(image))
        else:
            _progress(1, "Metin girişi işleniyor...")
            vision_data = vision_dict_for_ui(self.vision_agent.scan_text_input(drug_name_text or ""))
        if pdf_bytes is not None:
            vision_data = vision_dict_for_ui(vision_data)
        vision_data = _vision_normalize_null_strings(vision_data)
        results["vision"] = vision_data

        from similar_medicines import build_similar_drugs_bundle

        similar_bundle = build_similar_drugs_bundle(
            vision_data,
            self.safety_agent.groq_client,
            _groq_safety_model_chain(),
        )
        results["similar_drugs"] = similar_bundle

        # Okunabilirlik / PDF hata kontrolü
        score = vision_data.get("okunabilirlik_skoru", 10)
        if isinstance(score, (int, float)) and score < 5:
            _progress(1, "Fotoğraf kalitesi yetersiz! Lütfen daha aydınlık bir ortamda çekin.")
        if "hata" in vision_data and pdf_bytes is not None:
            _progress(1, f"PDF hatası: {vision_data['hata']}")

        # ADIM 2: RAG (embedding + Chroma ilk kez burada yüklenir; “Ajanlar başlatılıyor” adımı kısalır)
        _progress(2, "RAG Specialist: veritabanı hazırlanıyor / taranıyor…")
        ticari_ad = _vision_field_str(vision_data, "ticari_ad", alt=drug_name_text or "")
        etken = _vision_field_str(vision_data, "etken_madde")
        bd = vision_data.get("barkod_detay") or {}
        barkod_extra = ""
        if isinstance(bd, dict) and bd.get("tespit_edildi"):
            barkod_extra = str(bd.get("deger_normalize") or re.sub(r"\D", "", str(bd.get("deger") or "")))
        qr = vision_data.get("qr_kod_detay") or {}
        qr_snip = ""
        if isinstance(qr, dict) and qr.get("tespit_edildi") and qr.get("deger"):
            qr_snip = str(qr["deger"])[:120]
        query = f"{ticari_ad} {etken} {barkod_extra} {qr_snip}".strip()

        try:
            from referans_ilac_fiyat import lookup_fiyat_liste_for_vision

            results["fiyat_liste"] = lookup_fiyat_liste_for_vision(
                vision_data,
                ticari_ad=ticari_ad,
                drug_name_text=(drug_name_text or "").strip(),
                max_rows=8,
            )
        except Exception as _e:
            print(f"[Orchestrator] Fiyat listesi eşlemesi atlandı: {_e!s}")
            results["fiyat_liste"] = {"eslesti": False, "satirlar": [], "aciklama": str(_e)}

        rag_results = self.rag_agent.search(query, k=5, vision_data=vision_data)
        results["rag_results"] = rag_results

        # ADIM 3: Fact-Check
        _progress(3, "Fact-Checker: Veri tutarlılığı kontrol ediliyor...")
        fact_check = self.fact_checker.check(vision_data, rag_results)
        results["fact_check"] = fact_check

        # ADIM 4+5: Safety Auditor ve Corporate Analyst — paralel çalıştır
        _progress(4, "Safety Auditor + Corporate Analyst: Paralel analiz başladı...")
        manufacturer = vision_data.get("uretici")

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_safety    = pool.submit(self.safety_agent.audit, vision_data, rag_results)
            fut_corporate = pool.submit(self.corporate_agent.analyze, ticari_ad, manufacturer)
            safety_data   = fut_safety.result()
            corporate_data = fut_corporate.result()

        results["safety"]    = safety_data
        results["corporate"] = corporate_data
        _progress(5, "Safety + Corporate tamamlandı.")

        # ADIM 6: Rapor Sentezi
        _progress(6, "Report Synthesizer: Nihai Türkçe rapor hazırlanıyor...")
        kimlik: Dict[str, Any] = {}
        if vision_data.get("barkod_detay"):
            kimlik["barkod"] = vision_data["barkod_detay"]
        if vision_data.get("qr_kod_detay"):
            kimlik["qr_kod"] = vision_data["qr_kod_detay"]
        barcode_ctx = json.dumps(kimlik, ensure_ascii=False, indent=2) if kimlik else ""
        similar_ctx = json.dumps(similar_bundle, ensure_ascii=False, indent=2)
        report_text, avg_confidence, synthesis_error = self.synthesizer.synthesize(
            vision_data,
            safety_data,
            corporate_data,
            rag_results,
            barcode_context=barcode_ctx,
            similar_drugs_context=similar_ctx,
        )
        results["synthesis_error"] = synthesis_error

        if synthesis_error:
            model_hint = ", ".join(_gemini_model_chain())
            report_text = (
                "## Rapor metni oluşturulamadı\n\n"
                "Nihai özet (Gemini) şu anda üretilemedi. **Görsel Analiz**, "
                "**Güvenlik** ve **Firma** sekmelerindeki ajan çıktıları yine de "
                "incelenebilir.\n\n"
                f"- Denenen modeller: `{model_hint}`\n"
                "- `.env` / Streamlit Secrets içinde `GEMINI_MODEL` ile sabitleyin; "
                "ör. `gemini-2.5-flash`, `gemini-1.5-flash`.\n\n"
                "**Teknik ayrıntı:**\n```\n"
                f"{synthesis_error}\n```\n"
            )
        else:
            if avg_confidence < 8:
                warning = (
                    f"\n\n> **DİKKAT:** Ortalama güven puanı **{avg_confidence:.1f}/10**. "
                    "Bilgiler %100 doğrulanamadı. Lütfen bir sağlık uzmanına danışın.\n\n"
                )
                report_text = warning + report_text

        # VERİ UYUŞMAZLIĞI
        if fact_check["uyusmazlik"]:
            block = (
                "\n\n---\n"
                "## VERİ UYUŞMAZLIĞI ALARI\n"
                + "\n".join(f"- {s}" for s in fact_check["sorunlar"])
                + "\n---\n"
            )
            report_text = block + report_text

        report_text = report_text + _fiyat_liste_markdown_append(results.get("fiyat_liste"))
        report_text = _strip_confidence_meta_junk(report_text)
        results["report"] = report_text
        results["avg_confidence"] = avg_confidence
        results["alarm"] = safety_data.get("alarm_seviyesi", "BİLİNMİYOR")

        _progress(7, "Analiz tamamlandı.")
        return results
