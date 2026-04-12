"""
Benzer ilaç / muadil öneri katmanı.

- Yerel JSON kataloğu: data/alternatives_catalog.json (genişletilebilir)
- Katalog yetersizse isteğe bağlı Groq ile kısa JSON öneri (fiyat iddiası yok)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "alternatives_catalog.json"


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    t = str(s).lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _enrich_vision_for_similar(vision: Dict[str, Any]) -> Dict[str, Any]:
    """
    Üst düzey vision alanları boşsa gorsel_analiz / OCR özetinden kimlik doldurur;
    benzer ilaç eşlemesi ve Groq genişletmesinin çalışması için.
    """
    v = dict(vision) if isinstance(vision, dict) else {}
    ga = v.get("gorsel_analiz") if isinstance(v.get("gorsel_analiz"), dict) else {}

    if not str(v.get("ticari_ad") or "").strip():
        idm = str(ga.get("identified_medicine") or "").strip()
        if idm:
            v["ticari_ad"] = idm
    if not str(v.get("dozaj") or "").strip():
        dga = str(ga.get("dosage") or "").strip()
        if dga:
            v["dozaj"] = dga

    if not str(v.get("ticari_ad") or "").strip():
        ext = str(ga.get("extracted_text") or "").strip()
        if ext:
            for ln in ext.splitlines():
                ln = ln.strip()
                if 4 <= len(ln) <= 100 and re.search(r"[A-Za-zğüşıöçĞÜŞİÖÇâ]", ln):
                    v["ticari_ad"] = ln
                    break
    return v


def _dozaj_numbers(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return re.findall(r"\d+(?:[.,]\d+)?", str(s))


def _form_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    ta, tb = _norm(a), _norm(b)
    if ta == tb:
        return True
    for token in ("tablet", "film", "kapsül", "kapsul", "şurup", "surup", "ampul", "injeksiyon"):
        if token in ta and token in tb:
            return True
    return False


def load_alternatives_catalog() -> List[Dict[str, Any]]:
    if not _CATALOG_PATH.exists():
        return []
    try:
        data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _score_row(vision: Dict[str, Any], row: Dict[str, Any]) -> float:
    ve = _norm(vision.get("etken_madde"))
    re_ = _norm(row.get("etken_madde"))
    score = 0.0
    if ve and re_:
        if ve == re_:
            score += 80
        elif ve in re_ or re_ in ve:
            score += 55
        else:
            v_tokens = set(re.findall(r"[a-zğüşıöçâ]{3,}", ve))
            r_tokens = set(re.findall(r"[a-zğüşıöçâ]{3,}", re_))
            if v_tokens and r_tokens and (v_tokens & r_tokens):
                score += 35

    vd = vision.get("dozaj")
    rd = row.get("dozaj")
    vn = _dozaj_numbers(vd)
    rn = _dozaj_numbers(rd)
    if vn and rn and bool(set(vn) & set(rn)):
        score += 25

    if _form_match(str(vision.get("form") or ""), str(row.get("form") or "")):
        score += 12

    vt = _norm(vision.get("ticari_ad"))
    rt = _norm(row.get("ticari_ad"))
    if vt and rt and vt != rt:
        if len(vt) >= 4 and (vt in rt or rt in vt):
            score += 38
        elif len(vt) >= 4 and len(rt) >= 4:
            vw = set(re.findall(r"[a-zğüşıöçâ]{4,}", vt))
            rw = set(re.findall(r"[a-zğüşıöçâ]{4,}", rt))
            inter = vw & rw
            if inter:
                score += 16 + min(14, 6 * len(inter))

    return score


def match_catalog(vision: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    catalog = load_alternatives_catalog()
    if not catalog:
        return []
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in catalog:
        if not isinstance(row, dict):
            continue
        s = _score_row(vision, row)
        if s < 22:
            continue
        out = {
            "ticari_ad": row.get("ticari_ad"),
            "etken_madde": row.get("etken_madde"),
            "dozaj": row.get("dozaj"),
            "form": row.get("form"),
            "benzerlik_aciklamasi": row.get("benzerlik_aciklamasi") or row.get("eslestirme_notu") or "",
            "kaynak": "yerel_katalog",
        }
        scored.append((s, out))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def groq_expand_alternatives(
    client: Any,
    vision: Dict[str, Any],
    model_ids: List[str],
) -> List[Dict[str, Any]]:
    """Katalog dışı kısa öneriler — JSON zorunlu; fiyat / ucuzluk yasak."""
    if client is None or not model_ids:
        return []
    etken = vision.get("etken_madde") or ""
    ticari = vision.get("ticari_ad") or ""
    dozaj = vision.get("dozaj") or ""
    form = vision.get("form") or ""
    if not (etken or ticari):
        return []

    prompt = f"""Aşağıdaki ilaç için en fazla 5 muadil veya yakın alternatif öner.
SADECE geçerli bir JSON nesnesi döndür; kök anahtar: "alternatifler" (dizi).

Girdi ilaç:
- ticari_ad: {ticari}
- etken_madde: {etken}
- dozaj: {dozaj}
- form: {form}

Kurallar:
- alternatifler içindeki her öğe: ticari_ad, etken_madde, dozaj, form, benzerlik_aciklamasi
- benzerlik_aciklamasi: kısa tıbbi gerekçe (aynı etken, benzer form, dozaj yakınlığı vb.)
- Türkiye'de bilinen ticari adları tercih et; emin değilsen alternatifler: [] döndür.
- Fiyat, ucuzluk, geri ödeme, indirim veya eczane ismi YAZMA.
- Uydurma riski çok yüksekse alternatifler: [] döndür; eminsen en fazla 5 geçerli öneri ver.

Çıktı şeması:
{{"alternatifler": [{{"ticari_ad":"...","etken_madde":"...","dozaj":"...","form":"...","benzerlik_aciklamasi":"..."}}]}}
"""
    last_err = None
    for mid in model_ids:
        try:
            r = client.chat.completions.create(
                model=mid,
                messages=[
                    {"role": "system", "content": "Sen klinik farmakoloji asistanısın. Sadece JSON dizi döndür."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1200,
                temperature=0.15,
                response_format={"type": "json_object"},
            )
            raw = r.choices[0].message.content or ""
            cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                m = re.search(r"\{[\s\S]*\}", cleaned)
                if not m:
                    continue
                parsed = json.loads(m.group())

            rows: List[Dict[str, Any]] = []
            if isinstance(parsed, list):
                rows = [x for x in parsed if isinstance(x, dict)]
            elif isinstance(parsed, dict):
                for key in ("alternatifler", "oneriler", "items", "sonuclar"):
                    v = parsed.get(key)
                    if isinstance(v, list):
                        rows = [x for x in v if isinstance(x, dict)]
                        break
            out: List[Dict[str, Any]] = []
            for item in rows[:5]:
                out.append(
                    {
                        "ticari_ad": item.get("ticari_ad"),
                        "etken_madde": item.get("etken_madde"),
                        "dozaj": item.get("dozaj"),
                        "form": item.get("form"),
                        "benzerlik_aciklamasi": item.get("benzerlik_aciklamasi") or "",
                        "kaynak": "model_onerisi",
                    }
                )
            if out:
                return out
        except Exception as e:
            last_err = e
            continue
    return []


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in rows:
        key = _norm(r.get("ticari_ad")) + "|" + _norm(r.get("etken_madde")) + "|" + _norm(r.get("dozaj"))
        if key in seen or not r.get("ticari_ad"):
            continue
        seen.add(key)
        out.append(r)
    return out


def build_similar_drugs_bundle(
    vision: Dict[str, Any],
    groq_client: Any,
    groq_model_chain: List[str],
) -> Dict[str, Any]:
    """
    Benzer ilaç bölümü için yapılandırılmış sonuç.
    """
    vis = _enrich_vision_for_similar(vision)
    catalog = load_alternatives_catalog()
    catalog_hits = match_catalog(vis, limit=8)
    model_hits: List[Dict[str, Any]] = []
    if len(catalog_hits) < 3 and groq_client is not None:
        model_hits = groq_expand_alternatives(groq_client, vis, groq_model_chain)

    merged = _dedupe_rows(catalog_hits + model_hits)[:8]

    bos = ""
    if not merged:
        if not (_norm(vis.get("ticari_ad")) or _norm(vis.get("etken_madde"))):
            bos = (
                "İlaç **ticari adı** veya **etken maddesi** çıkarılamadığı için benzer ürün araması "
                "yapılamadı. Daha net bir kutu fotoğrafı veya **İlaç Adı ile** giriş deneyin."
            )
        elif not catalog:
            bos = (
                "Muadil öneri listesi henüz kullanılamıyor. "
                "Eşdeğer ürün için eczacınıza veya hekiminize danışın."
            )
        else:
            bos = (
                "Bu ilaç için listede yeterince yakın bir eşleşme bulunamadı; "
                "ek model önerisi de üretilemedi. Eşdeğer / muadil için resmi kaynaklar ve "
                "sağlık mesleği mensubu onayı esastır."
            )

    return {
        "oneriler": merged,
        "bos_aciklama": bos,
        "fiyat_entegrasyonu_notu": (
            "Güncel satış fiyatı, indirim veya geri ödeme bilgisi bu sürümde entegre değildir; "
            "resmi fiyat ve ödeme koşulları için eczane, SGK veya ilaç firması kaynakları kullanılmalıdır."
        ),
        "uyari": (
            "Benzer / muadil seçimi tedavi güvenliği açısından eczacı veya hekim onayı gerektirir; "
            "bu liste bilgilendirme amaçlıdır."
        ),
    }
