"""
Görsel analiz ön işleme, OCR kurtarma ve tanılama (WikiPharma).
Streamlit / ajanlar tarafından kullanılır; Groq görüntü çağrılarından bağımsız yardımcılar.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

logger = logging.getLogger("pharma_guard.image")

# Groq görüntü modelleri — önce env, sonra varsayılan sıra
_DEFAULT_VISION_MODELS: Tuple[str, ...] = (
    "meta-llama/llama-4-scout-17b-16e-instruct",
)

_MAX_VISION_SIDE = 1280
# Groq: base64 görüntü isteği üst sınırı ~4MB; ham JPEG + base64 genişlemesi için güvenli tavan
_MAX_RAW_JPEG_BYTES = 2_800_000


def groq_vision_model_chain() -> List[str]:
    import os

    raw = (os.getenv("GROQ_VISION_MODEL_PRIORITY") or "").strip()
    if raw:
        seen: set = set()
        out: List[str] = []
        for m in raw.split(","):
            m = m.strip()
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out
    return list(_DEFAULT_VISION_MODELS)


def classify_groq_vision_error(exc: BaseException) -> str:
    """Groq görüntü hatası için makine-okunur kod."""
    s = f"{type(exc).__name__}: {exc!s}".lower()
    if "timeout" in s or "timed out" in s:
        return "timeout"
    if "429" in s or "rate" in s:
        return "rate_limit"
    if "400" in s or "invalid" in s or "malformed" in s or "payload" in s:
        return "invalid_payload"
    if "413" in s or "too large" in s or "length" in s:
        return "payload_too_large"
    if "do not have access" in s or "does not exist" in s or "model_not_found" in s:
        return "model_not_found"
    if "404" in s or "not found" in s:
        return "model_unavailable"
    if "decommission" in s or "deprecated" in s or "no longer supported" in s:
        return "model_decommissioned"
    if "connection" in s or "connect" in s:
        return "network"
    return "unknown"


def prepare_multimodal_inputs(pil_image: Image.Image) -> Dict[str, Any]:
    """
    EXIF düzeltme, RGB, boyut sınırı, LLaVA + OCR için iki varyant üretir.
    """
    meta: Dict[str, Any] = {}
    try:
        img = ImageOps.exif_transpose(pil_image)
    except Exception as e:
        logger.warning("exif_transpose_atlandi: %s", e)
        img = pil_image.copy()

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    elif img.mode == "RGBA":
        img = img.convert("RGB")

    w, h = img.size
    meta["upload_size"] = (w, h)
    if max(w, h) > _MAX_VISION_SIDE:
        r = _MAX_VISION_SIDE / max(w, h)
        img = img.resize((max(1, int(w * r)), max(1, int(h * r))), Image.Resampling.LANCZOS)
    meta["normalized_size"] = img.size

    vision_rgb = img.copy()
    vision_retry = ImageEnhance.Sharpness(
        ImageEnhance.Contrast(img.copy()).enhance(1.15)
    ).enhance(1.35)
    vision_retry = vision_retry.filter(
        ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=2)
    )

    gray = ImageOps.grayscale(img)
    ocr_img = ImageOps.autocontrast(gray, cutoff=1)
    ocr_img = ImageEnhance.Sharpness(ocr_img).enhance(1.5)
    if max(ocr_img.size) < 1200:
        ocr_img = ocr_img.resize(
            (int(ocr_img.width * 1.35), int(ocr_img.height * 1.35)),
            Image.Resampling.LANCZOS,
        )
    meta["ocr_size"] = ocr_img.size

    return {
        "vision_rgb": vision_rgb,
        "vision_retry": vision_retry,
        "ocr_image": ocr_img,
        "meta": meta,
    }


def _jpeg_under_size_limit(rgb: Image.Image, quality: int = 85) -> Tuple[str, int]:
    """Base64 JPEG; Groq ~4MB base64 sınırı için ham JPEG boyutunu sınırlar."""
    q = quality
    raw = b""
    for _ in range(8):
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=q, optimize=True)
        raw = buf.getvalue()
        b64 = base64.b64encode(raw).decode("ascii")
        if len(raw) <= _MAX_RAW_JPEG_BYTES and len(b64) <= 3_900_000:
            return b64, len(raw)
        q = max(45, q - 10)
    b64 = base64.b64encode(raw).decode("ascii")
    return b64, len(raw)


def encode_image_for_groq_vision(rgb: Image.Image) -> Tuple[str, int]:
    """data:image/jpeg;base64,... için base64 ve ham JPEG bayt uzunluğu."""
    b64, nbytes = _jpeg_under_size_limit(rgb.convert("RGB"))
    return b64, nbytes


def ocr_extract_text(ocr_image: Image.Image) -> Tuple[str, Optional[str]]:
    """
    Tesseract OCR. Kurulu değilse boş metin + hata kodu.
    """
    try:
        import pytesseract
    except Exception as e:
        logger.warning("pytesseract_yok: %s", e)
        return "", "pytesseract_missing"

    try:
        txt = pytesseract.image_to_string(ocr_image, lang="tur+eng", config="--psm 6")
        txt = (txt or "").strip()
        logger.info("ocr_tamamlandi len=%s", len(txt))
        return txt, None if txt else "ocr_empty"
    except Exception as e:
        logger.warning("ocr_hata: %s", e)
        return "", f"ocr_failed:{e!s}"


def heuristic_medicine_line(ocr_text: str) -> Tuple[str, str]:
    """
    OCR satırlarından olası ilaç adı satırı seçer.
    Dönüş: (ticari_ad_tahmini, aciklama)
    """
    lines = [ln.strip() for ln in ocr_text.splitlines() if len(ln.strip()) > 2]
    if not lines:
        return "", "satir_yok"

    scored: List[Tuple[int, str]] = []
    for ln in lines:
        low = ln.lower()
        score = 0
        if re.search(r"\d", ln):
            score += 3
        if re.search(r"\b(mg|mcg|g|ml|µg|ug)\b", low, re.I):
            score += 5
        if any(k in low for k in ("tablet", "kapsül", "kapsul", "film", "ampul", "surup", "şurup")):
            score += 4
        if 8 <= len(ln) <= 80:
            score += 2
        scored.append((score, ln))
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1] if scored[0][0] > 0 else max(lines, key=len)
    return best, "ocr_heuristic_line"


def build_gorsel_analiz_envelope(
    *,
    success: bool,
    status: str,
    source: Optional[str],
    extracted_text: str,
    identified_medicine: str,
    dosage: str,
    message: str,
    error_code: Optional[str],
) -> Dict[str, Any]:
    return {
        "success": success,
        "image_analysis_status": status,
        "source": source,
        "extracted_text": (extracted_text or "")[:8000],
        "identified_medicine": identified_medicine or "",
        "dosage": dosage or "",
        "message": message,
        "error_code": error_code,
    }


def structure_ocr_with_groq_text_model(
    client: Any,
    ocr_text: str,
    text_model_chain: List[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    OCR metninden yapılandırılmış ilaç alanları — saf metin modeli (görüntü yok).
    """
    if not ocr_text or len(ocr_text.strip()) < 4:
        return None, "ocr_too_short"

    prompt = f"""Aşağıdaki metin bir ilaç kutusundan OCR ile okunmuştur; hatalı karakterler olabilir.

Metin:
---
{ocr_text[:7500]}
---

Görev: Bu metinden mümkün olduğunca çok alanı doldur. Emin olmadığın alan için null kullan.
SADECE geçerli bir JSON nesnesi döndür (şema):

{{
  "ticari_ad": "string veya null",
  "etken_madde": "string veya null",
  "dozaj": "string veya null",
  "form": "string veya null",
  "barkod": "string veya null",
  "uretici": "string veya null",
  "okunabilirlik_skoru": 1-10 arası sayı (OCR kalitesine göre),
  "notlar": "kısa not"
}}
"""
    last = None
    for mid in text_model_chain:
        try:
            r = client.chat.completions.create(
                model=mid,
                messages=[
                    {"role": "system", "content": "Sen ilaç kutusu metin ayrıştırıcısısın. Sadece JSON döndür."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=900,
                temperature=0.05,
                response_format={"type": "json_object"},
            )
            raw = r.choices[0].message.content or ""
            cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
            data = json.loads(cleaned)
            if isinstance(data, dict):
                data["kaynak"] = f"OCR + Groq metin ({mid})"
                return data, None
        except Exception as e:
            last = f"{mid}:{e!s}"
            continue
    return None, last or "groq_text_structure_failed"
