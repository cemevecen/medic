"""
Kutu görselinden doğrusal barkod ve QR kod çözümlemesi (pyzbar + PIL ön işleme).
Sistemde libzbar (Linux: libzbar0) yoksa güvenli biçimde devre dışı kalır.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def _digits_only(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", str(value))


def preprocess_variants(pil_image: Image.Image) -> List[Image.Image]:
    """Kontrast / ölçek / keskinlik varyantları — decode başarısını artırmak için."""
    variants: List[Image.Image] = []
    rgb = pil_image.convert("RGB") if pil_image.mode != "RGB" else pil_image.copy()
    variants.append(rgb)

    gray = ImageOps.grayscale(rgb)
    variants.append(ImageOps.autocontrast(gray, cutoff=2).convert("RGB"))
    variants.append(gray.convert("RGB"))

    w, h = rgb.size
    if max(w, h) < 900:
        scale = 900 / max(w, h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        enlarged = rgb.resize((nw, nh), Image.Resampling.LANCZOS)
        variants.append(enlarged)
        eg = ImageOps.grayscale(enlarged)
        variants.append(ImageOps.autocontrast(eg, cutoff=2).convert("RGB"))

    sharp = ImageEnhance.Sharpness(rgb).enhance(1.6)
    variants.append(sharp.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3)))

    seen: set = set()
    out: List[Image.Image] = []
    for im in variants:
        key = im.tobytes()[:2048] + str(im.size).encode()
        if key not in seen:
            seen.add(key)
            out.append(im)
    return out


def _is_qr_symbol(fmt: str) -> bool:
    return "QR" in str(fmt).upper()


def _empty_linear() -> Dict[str, Any]:
    return {
        "tespit_edildi": False,
        "deger": None,
        "format": None,
        "mesaj": "Barkod tespit edilemedi",
        "kütüphane": "yok",
        "ham_liste": [],
    }


def _empty_qr() -> Dict[str, Any]:
    return {
        "tespit_edildi": False,
        "deger": None,
        "format": None,
        "mesaj": "QR kod tespit edilemedi",
        "ham_liste": [],
    }


def _collect_decodes(pil_image: Image.Image) -> Tuple[List[Dict[str, Any]], str]:
    """
    pyzbar ile tüm kodları toplar.
    Dönüş: (ham liste, kütüphane_durumu)
    """
    if pil_image is None:
        return [], "yok"

    try:
        from pyzbar.pyzbar import decode as zbar_decode
    except Exception as exc:
        return [], f"pyzbar_yüklenemedi: {exc!s}"

    raw_list: List[Dict[str, Any]] = []
    seen: set = set()
    for im in preprocess_variants(pil_image):
        try:
            for obj in zbar_decode(im):
                raw = obj.data
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1", errors="replace")
                text = text.strip()
                if not text:
                    continue
                sym = str(getattr(obj, "type", None) or "UNKNOWN")
                key = (text, sym)
                if key in seen:
                    continue
                seen.add(key)
                raw_list.append(
                    {
                        "deger": text,
                        "format": sym,
                        "ham_bayt_uzunlugu": len(raw),
                    }
                )
        except Exception:
            continue
    return raw_list, "pyzbar"


def _pick_best_linear(decodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    linear = [d for d in decodes if not _is_qr_symbol(d["format"])]
    if not linear:
        return None
    digit_rich = sorted(
        linear,
        key=lambda d: (len(_digits_only(d["deger"])), len(d["deger"])),
        reverse=True,
    )
    best = dict(digit_rich[0])
    digits = _digits_only(best["deger"])
    best["deger_normalize"] = digits if len(digits) >= 8 else (digits or best["deger"])
    return best


def _pick_best_qr(decodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    qrs = [d for d in decodes if _is_qr_symbol(d["format"])]
    if not qrs:
        return None

    def score(d: Dict[str, Any]) -> Tuple[int, int]:
        t = d.get("deger") or ""
        s = 0
        low = t.lower()
        if low.startswith("http://") or low.startswith("https://"):
            s += 5000
        return (s + len(t), len(t))

    best = dict(max(qrs, key=score))
    return best


def scan_codes_from_image(pil_image: Image.Image) -> Dict[str, Any]:
    """
    Doğrusal barkod ve QR kod taraması.
    Dönüş: {"barkod": {...}, "qr_kod": {...}, "kütüphane": str}
    """
    raw, lib = _collect_decodes(pil_image)

    if lib.startswith("pyzbar_yüklenemedi"):
        err = {
            "barkod": {
                **_empty_linear(),
                "mesaj": "Barkod tespit edilemedi (pyzbar / zbar kurulu değil)",
                "kütüphane": lib,
            },
            "qr_kod": {**_empty_qr(), "mesaj": "QR kod tespit edilemedi (pyzbar / zbar kurulu değil)"},
            "kütüphane": lib,
        }
        return err

    if pil_image is None:
        return {"barkod": _empty_linear(), "qr_kod": _empty_qr(), "kütüphane": "yok"}

    best_lin = _pick_best_linear(raw)
    best_qr = _pick_best_qr(raw)

    barkod: Dict[str, Any]
    if best_lin:
        barkod = {
            "tespit_edildi": True,
            "deger": best_lin["deger"],
            "deger_normalize": best_lin.get("deger_normalize"),
            "format": best_lin.get("format"),
            "mesaj": "Barkod bulundu",
            "kütüphane": lib,
            "ham_liste": [d for d in raw if not _is_qr_symbol(d["format"])][:5],
        }
    else:
        barkod = {
            **_empty_linear(),
            "mesaj": "Barkod tespit edilemedi",
            "kütüphane": lib,
            "ham_liste": [d for d in raw if not _is_qr_symbol(d["format"])][:5],
        }

    qr: Dict[str, Any]
    if best_qr:
        qr = {
            "tespit_edildi": True,
            "deger": best_qr["deger"],
            "format": best_qr.get("format"),
            "mesaj": "QR kod bulundu",
            "ham_liste": [d for d in raw if _is_qr_symbol(d["format"])][:5],
        }
    else:
        qr = {
            **_empty_qr(),
            "mesaj": "QR kod tespit edilemedi",
            "ham_liste": [d for d in raw if _is_qr_symbol(d["format"])][:5],
        }

    return {"barkod": barkod, "qr_kod": qr, "kütüphane": lib}


def scan_barcodes_from_image(pil_image: Image.Image) -> Dict[str, Any]:
    """Geriye dönük: yalnızca doğrusal barkod sonucu (dict, eski şema)."""
    return dict(scan_codes_from_image(pil_image)["barkod"])


def merge_barcode_into_vision(vision: Dict[str, Any], barkod_detay: Dict[str, Any]) -> Dict[str, Any]:
    """
    Doğrusal barkod sonucunu vision sözlüğüne işler; görsel OCR barkodu ile çelişkiyi işaretler.
    """
    vision = dict(vision)
    vision["barkod_detay"] = dict(barkod_detay)

    if not barkod_detay.get("tespit_edildi"):
        return vision

    dec_raw = barkod_detay.get("deger") or ""
    dec_n = barkod_detay.get("deger_normalize") or _digits_only(dec_raw) or dec_raw
    ocr_b = vision.get("barkod")
    ocr_n = _digits_only(ocr_b) if ocr_b else ""

    vision["barkod_detay"]["gorsel_celiski"] = False
    if ocr_n and dec_n and ocr_n != dec_n:
        vision["barkod_detay"]["gorsel_celiski"] = True
        vision["barkod_detay"]["mesaj"] = (
            "Barkod bulundu — görsel model ile okunan barkod farklı; düşük güven / uyumsuzluk."
        )
        vision["barkod_gorsel_okuma"] = str(ocr_b)
        vision["barkod"] = dec_raw
        score = vision.get("okunabilirlik_skoru")
        if isinstance(score, (int, float)):
            vision["okunabilirlik_skoru"] = min(float(score), 6.0)
    else:
        if not ocr_b or not ocr_n:
            vision["barkod"] = dec_raw
        elif ocr_n == dec_n:
            vision["barkod"] = dec_raw

    return vision


def merge_codes_into_vision(
    vision: Dict[str, Any],
    barkod_detay: Dict[str, Any],
    qr_detay: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Barkod + QR sonuçlarını vision'a yazar (QR, barkod OCR çelişkisine karışmaz)."""
    vision = merge_barcode_into_vision(vision, barkod_detay)
    vision["qr_kod_detay"] = dict(qr_detay or _empty_qr())
    return vision
