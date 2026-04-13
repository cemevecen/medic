"""
Birleşik ilaç fiyat tabloları: referans GKF (€) xlsx + web liste (₺) xlsx + recete.org haber HTML tabloları.
Ortak alanlar: ilaç adı, firma, fiyat (farklı para birimleri ayrı sütunlarda).
Katı _k birleşiminden sonra, gevşek isim anahtarı ile aynı ürünün web verisi olmayan kopya satırları silinir.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

REFERANS_PATH = Path(__file__).parent / "data" / "referans_bazli_ilac_fiyat_listesi.xlsx"
WEB_PATH = Path(__file__).parent / "data" / "ilac_fiyat_web_listesi.xlsx"
_REFERANS_SKIPROWS = 4

# Ticari ad ↔ liste "İlaç adı" eşlemesi: ~%70–75 benzerlik (SequenceMatcher oranı)
FIYAT_ISIM_BENZERLIK_ESIK = 0.72


def _fiyat_baslik_benzerligi(liste_basligi: object, aday: object) -> float:
    """Liste satırı başlığı ile analiz adayı arasında 0..1 benzerlik (gevşek anahtar + difflib)."""
    t_liste = _norm_key_loose(liste_basligi)
    t_aday = _norm_key_loose(aday)
    if not t_liste or not t_aday:
        return 0.0
    if t_liste == t_aday:
        return 1.0
    raw_l = str(liste_basligi or "").strip().casefold()
    raw_a = str(aday or "").strip().casefold()
    if raw_l and raw_a and raw_l == raw_a:
        return 1.0
    r1 = SequenceMatcher(None, t_liste, t_aday).ratio()
    if len(raw_l) >= 3 and len(raw_a) >= 3:
        r2 = SequenceMatcher(None, raw_l, raw_a).ratio()
        return max(r1, r2)
    return r1


def _norm_key(s: object) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    t = str(s).strip()
    return " ".join(t.casefold().split())


def _norm_key_loose(s: object) -> str:
    """
    Aynı ürünün farklı yazımlarını (TABLET / TB., SOLUSYON / SOL. vb.) tek anahtarda toplar.
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    t = str(s).strip().casefold()
    t = re.sub(
        r"\btablet\s*\(\s*(\d+)\s*(?:film\s+kapli\s+)?tablet\s*\)",
        r" \1 tablet ",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"\(\s*(\d+)\s*(?:film\s+kapli\s+)?(?:tablet|tb\.?|film\s+tablet|film\s+kapli\s+tablet)\s*\)",
        r" \1 tablet ",
        t,
        flags=re.I,
    )
    t = re.sub(
        r"\(\s*(\d+)\s*(?:film\s+kapli\s+)?kapsul\s*\)",
        r" \1 kapsul ",
        t,
        flags=re.I,
    )
    t = re.sub(r"\([^)]{0,200}\)", " ", t)
    t = re.sub(r"[\[\]]", " ", t)
    t = t.replace("/", " ")
    t = re.sub(r"\.", " ", t)
    t = re.sub(r"[,;]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    repls = (
        (r"\bfilm\s+kapli\b", " "),
        (r"\bfilm\s+tablet\b", " tablet "),
        (r"\bftb\b", " tablet "),
        (r"\bfkb\b", " tablet "),
        (r"\btablet\b", " tablet "),
        (r"\btb\b", " tablet "),
        (r"\bkapsul\b", " kapsul "),
        (r"\bkaps\b", " kapsul "),
        (r"\bkap\b", " kapsul "),
        (r"\bsolusyon\b", " solusyon "),
        (r"\bsolasyon\b", " solusyon "),
        (r"\bsol\b", " solusyon "),
        (r"\boral\b", " oral "),
        (r"\binj\b", " injeksiyon "),
        (r"\binjeksiyon\b", " injeksiyon "),
        (r"\bdraje\b", " draje "),
        (r"\bsprey\b", " sprey "),
        (r"\bflk\b", " flakon "),
        (r"\bflakon\b", " flakon "),
    )
    for pat, rep in repls:
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r"(tablet\s*)+", " tablet ", t)
    t = re.sub(r"(kapsul\s*)+", " kapsul ", t)
    t = re.sub(r"(solusyon\s*)+", " solusyon ", t)
    t = re.sub(r"(oral\s*)+", " oral ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _row_has_web_signal(row: pd.Series) -> bool:
    """Web listesinden liste fiyatı veya barkod (gerçek satır) var mı."""
    if "Liste fiyatı (₺)" in row.index:
        v = row["Liste fiyatı (₺)"]
        if pd.notna(v):
            try:
                if float(v) != 0.0:
                    return True
            except (TypeError, ValueError):
                if str(v).strip():
                    return True
    if "Barkod" in row.index:
        b = row["Barkod"]
        if pd.notna(b):
            bs = str(b).strip().lower()
            if bs and bs not in ("none", "nan", "-", "nat", "<na>"):
                return True
    return False


def _row_has_any_price_signal(row: pd.Series) -> bool:
    """GKF, liste fiyatı veya barkod — web yoksa referans satırını tutmak için."""
    for col in ("GKF (€)", "Liste fiyatı (₺)"):
        if col not in row.index:
            continue
        v = row[col]
        if pd.isna(v):
            continue
        try:
            if float(v) != 0.0:
                return True
        except (TypeError, ValueError):
            if str(v).strip():
                return True
    if "Barkod" in row.index:
        b = row["Barkod"]
        if pd.notna(b):
            bs = str(b).strip().lower()
            if bs and bs not in ("none", "nan", "-", "nat", "<na>"):
                return True
    return False


def _drop_loose_dupes_unpriced(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gevşek ada göre gruplar.
    Grupta en az birinde web (liste ₺ / barkod) varsa, web verisi olmayan kopyaları siler.
    Aksi halde GKF vb. herhangi bir fiyat sinyali varsa ona göre; yoksa tek satır bırakır.
    """
    if df is None or len(df) < 2:
        return df
    work = df.copy()
    work["_nk_loose"] = work["İlaç adı"].map(_norm_key_loose)
    drop_idx: list[object] = []
    for key, grp in work.groupby("_nk_loose", sort=False):
        if not key or len(grp) < 2:
            continue
        web_f = grp.apply(_row_has_web_signal, axis=1)
        if web_f.any():
            drop_idx.extend(grp.index[~web_f].tolist())
            continue
        any_f = grp.apply(_row_has_any_price_signal, axis=1)
        if any_f.any():
            drop_idx.extend(grp.index[~any_f].tolist())
        else:
            drop_idx.extend(list(grp.index[1:]))
    out = work.drop(index=drop_idx, errors="ignore")
    return out.drop(columns=["_nk_loose"], errors="ignore")


def _require_liste_fiyat(df: pd.DataFrame) -> pd.DataFrame:
    """Liste fiyatı (₺) yok veya 0 olan satırları çıkarır."""
    if df is None or df.empty or "Liste fiyatı (₺)" not in df.columns:
        return df
    p = pd.to_numeric(df["Liste fiyatı (₺)"], errors="coerce")
    keep = p.notna() & (p != 0.0)
    return df.loc[keep].reset_index(drop=True)


def _join_unique_firms(s: pd.Series) -> str:
    xs = sorted(
        {
            str(v).strip()
            for v in s
            if str(v).strip() and str(v).strip().casefold() not in ("nan", "none")
        }
    )
    return " / ".join(xs) if xs else ""


def _read_referans() -> Optional[pd.DataFrame]:
    if not REFERANS_PATH.exists():
        return None
    df = pd.read_excel(
        REFERANS_PATH,
        sheet_name=0,
        skiprows=_REFERANS_SKIPROWS,
        engine="openpyxl",
    )
    df.columns = [str(c).strip() for c in df.columns]
    if len(df.columns) < 3:
        return None
    c0, c1, c2 = df.columns[0], df.columns[1], df.columns[2]
    out = df.rename(columns={c0: "İlaç adı", c1: "Firma", c2: "GKF (€)"})[
        ["İlaç adı", "Firma", "GKF (€)"]
    ].copy()
    out["İlaç adı"] = out["İlaç adı"].astype(str).str.strip()
    out["Firma"] = out["Firma"].astype(str).str.strip()
    out = out[out["İlaç adı"].str.len() > 0]
    out["GKF (€)"] = pd.to_numeric(out["GKF (€)"], errors="coerce")
    out["_k"] = out["İlaç adı"].map(_norm_key)
    out = out[out["_k"].str.len() > 0]
    dedup = out.groupby("_k", as_index=False).agg(
        **{
            "İlaç adı": ("İlaç adı", "first"),
            "Firma": ("Firma", _join_unique_firms),
            "GKF (€)": ("GKF (€)", "first"),
        }
    )
    return dedup


def _read_web() -> Optional[pd.DataFrame]:
    if not WEB_PATH.exists():
        return None
    xl = pd.ExcelFile(WEB_PATH, engine="openpyxl")
    sheet = "WEBLISTE" if "WEBLISTE" in xl.sheet_names else xl.sheet_names[0]
    df = pd.read_excel(WEB_PATH, sheet_name=sheet, header=0, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    need = {"ILAC ADI", "FIYATI", "FIRMA"}
    if not need.issubset(set(df.columns)):
        return None
    out = pd.DataFrame(
        {
            "Barkod": df["BARKODU"].astype(str).str.strip() if "BARKODU" in df.columns else "",
            "İlaç adı (web)": df["ILAC ADI"].astype(str).str.strip(),
            "Firma (web)": df["FIRMA"].astype(str).str.strip() if "FIRMA" in df.columns else "",
            "Liste fiyatı (₺)": pd.to_numeric(df["FIYATI"], errors="coerce"),
        }
    )
    if "TARIH" in df.columns:
        ts = pd.to_datetime(df["TARIH"], errors="coerce")
        out["Liste tarihi"] = ts.dt.strftime("%Y-%m-%d")
        out.loc[ts.isna(), "Liste tarihi"] = np.nan
    else:
        out["Liste tarihi"] = np.nan
    out = out[out["İlaç adı (web)"].str.len() > 0]
    out["_k"] = out["İlaç adı (web)"].map(_norm_key)
    out = out[out["_k"].str.len() > 0]
    if out["Liste tarihi"].notna().any():
        out["_ts"] = pd.to_datetime(out["Liste tarihi"], errors="coerce")
        out = out.sort_values("_ts", na_position="first")
        out = out.drop_duplicates(subset=["_k"], keep="last")
        out = out.drop(columns=["_ts"], errors="ignore")
    else:
        out = out.drop_duplicates(subset=["_k"], keep="first")
    return out


def _ensure_unique_norm(out: pd.DataFrame) -> pd.DataFrame:
    out = out.copy()
    out["_nk"] = out["İlaç adı"].map(_norm_key)
    out = out.drop_duplicates(subset=["_nk"], keep="first").drop(columns=["_nk"])
    return out.sort_values("İlaç adı", key=lambda s: s.str.casefold()).reset_index(drop=True)


def _merge_ref_web(ref: Optional[pd.DataFrame], web: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if ref is None and web is None:
        return None
    if ref is None:
        w = web.drop(columns=["_k"], errors="ignore").rename(
            columns={"İlaç adı (web)": "İlaç adı", "Firma (web)": "Firma"}
        )
        w["GKF (€)"] = np.nan
        w["Firma"] = w["Firma"].replace("", np.nan)
        cols = ["İlaç adı", "Firma", "GKF (€)", "Liste fiyatı (₺)", "Barkod", "Liste tarihi"]
        for c in cols:
            if c not in w.columns:
                w[c] = np.nan
        w = w[cols]
        w["Barkod"] = w["Barkod"].replace("", np.nan)
        return w
    if web is None:
        r = ref.drop(columns=["_k"]).copy()
        r["Liste fiyatı (₺)"] = np.nan
        r["Barkod"] = np.nan
        r["Liste tarihi"] = np.nan
        cols = ["İlaç adı", "Firma", "GKF (€)", "Liste fiyatı (₺)", "Barkod", "Liste tarihi"]
        r = r[cols]
        return r
    m = pd.merge(
        ref.rename(columns={"İlaç adı": "_ad_ref", "Firma": "_firma_ref"}),
        web.rename(
            columns={
                "İlaç adı (web)": "_ad_web",
                "Firma (web)": "_firma_web",
            }
        ),
        on="_k",
        how="outer",
    )
    ad = m["_ad_ref"].where(
        m["_ad_ref"].notna() & (m["_ad_ref"].astype(str).str.strip().str.len() > 0),
        m["_ad_web"],
    )
    ad = ad.fillna(m["_ad_web"])
    firma = [_merge_firma(a, b) for a, b in zip(m["_firma_ref"], m["_firma_web"])]
    out = pd.DataFrame(
        {
            "İlaç adı": ad.astype(str).str.strip(),
            "Firma": firma,
            "GKF (€)": m["GKF (€)"],
            "Liste fiyatı (₺)": m["Liste fiyatı (₺)"],
            "Barkod": m["Barkod"],
            "Liste tarihi": m["Liste tarihi"],
        }
    )
    out = out[out["İlaç adı"].str.len() > 0]
    out["Barkod"] = out["Barkod"].replace("", np.nan)
    return out


def _merge_firma(ref_f: object, web_f: object) -> str:
    r = str(ref_f).strip() if pd.notna(ref_f) and str(ref_f).strip().casefold() != "nan" else ""
    w = str(web_f).strip() if pd.notna(web_f) and str(web_f).strip().casefold() != "nan" else ""
    if not r:
        return w
    if not w:
        return r
    if r.casefold() == w.casefold():
        return r
    return f"{r} | {w}"


@st.cache_data(show_spinner=False)
def load_birlesik_ilac_fiyat_df() -> Optional[pd.DataFrame]:
    from recete_haber import merge_recete_into, read_recete_haber_df

    ref = _read_referans()
    web = _read_web()
    recete = read_recete_haber_df()

    base = _merge_ref_web(ref, web)
    if base is None:
        if recete is None or recete.empty:
            return None
        fr = recete["_firma_recete"].astype(str).str.strip()
        fr = fr.replace("", np.nan)
        base = pd.DataFrame(
            {
                "İlaç adı": recete["_ad_recete"].astype(str).str.strip(),
                "Firma": fr,
                "GKF (€)": np.nan,
                "Liste fiyatı (₺)": np.nan,
                "Barkod": np.nan,
                "Liste tarihi": np.nan,
            }
        )

    out = merge_recete_into(base, recete)
    out = _drop_loose_dupes_unpriced(out)
    out = _require_liste_fiyat(out)
    return _ensure_unique_norm(out)


@st.cache_data(show_spinner=False)
def load_referans_fiyat_df() -> Optional[pd.DataFrame]:
    """Geriye dönük uyumluluk: birleşik tablonun yalnızca GKF dolu satırları (3 sütun)."""
    full = load_birlesik_ilac_fiyat_df()
    if full is None:
        return None
    sub = full[full["GKF (€)"].notna()].copy()
    return sub[["İlaç adı", "Firma", "GKF (€)"]].reset_index(drop=True)


def _serialize_fiyat_tablo_row(row: pd.Series) -> Dict[str, Any]:
    """JSON / UI için tek satır (NaN → None)."""
    out: Dict[str, Any] = {}
    for col in ("İlaç adı", "Firma", "GKF (€)", "Liste fiyatı (₺)", "Barkod", "Liste tarihi"):
        if col not in row.index:
            continue
        v = row[col]
        if pd.isna(v):
            out[col] = None
        elif col in ("GKF (€)", "Liste fiyatı (₺)"):
            try:
                fv = float(v)
                if fv != fv:  # NaN
                    out[col] = None
                elif col == "GKF (€)":
                    out[col] = round(fv, 4)
                else:
                    out[col] = round(fv, 2)
            except (TypeError, ValueError):
                out[col] = str(v).strip() or None
        else:
            s = str(v).strip()
            out[col] = s if s and s.casefold() not in ("nan", "none", "<na>") else None
    return out


def lookup_fiyat_liste_for_vision(
    vision_data: Dict[str, Any],
    ticari_ad: str = "",
    drug_name_text: str = "",
    max_rows: int = 8,
) -> Dict[str, Any]:
    """
    Analiz çıktısındaki ilaç ile `load_birlesik_ilac_fiyat_df` (İlaç Fiyatları sekmesi) eşlemesi.

    Yalnızca **ticari_ad** (ve metin girişi) ile liste **İlaç adı** karşılaştırılır; barkod eşleştirmede
    kullanılmaz. Benzerlik oranı en az ~%72 (FIYAT_ISIM_BENZERLIK_ESIK) olan satırlar alınır; en yüksek
    skor önce. Eşleşen satırda barkod, liste fiyatı ve GKF tablodan ek bilgi olarak gelir.
    """
    # vision_data: barkod eşleştirmede kullanılmıyor (çağrı imzası uyumluluk için duruyor).
    _ = vision_data

    df = load_birlesik_ilac_fiyat_df()
    if df is None or df.empty:
        return {"eslesti": False, "satirlar": [], "aciklama": "Fiyat tablosu yok veya boş."}

    names: List[str] = []
    for s in (ticari_ad, drug_name_text):
        s = (s or "").strip()
        if s and all(x.casefold() != s.casefold() for x in names):
            names.append(s)

    if not names:
        return {"eslesti": False, "satirlar": [], "aciklama": ""}

    titles = df["İlaç adı"].astype(str)

    def _best_score(title: str) -> float:
        return max(_fiyat_baslik_benzerligi(title, n) for n in names)

    best_scores = titles.map(_best_score)
    mask = best_scores >= FIYAT_ISIM_BENZERLIK_ESIK
    if not mask.any():
        return {"eslesti": False, "satirlar": [], "aciklama": ""}

    sub = df.loc[mask].copy()
    sub["_score"] = best_scores[mask]
    sub = sub.sort_values("_score", ascending=False).head(int(max_rows))
    sub = sub.drop(columns=["_score"], errors="ignore")

    satirlar = [_serialize_fiyat_tablo_row(sub.iloc[i]) for i in range(len(sub))]
    return {"eslesti": True, "satirlar": satirlar, "aciklama": ""}


def search_unique_ilac_adi_candidates(query: str, limit: int = 40) -> List[str]:
    """
    İlaç Fiyatları birleşik tablosundaki benzersiz 'İlaç adı' değerlerinde alt dizgi araması.
    En az 2 karakter; önce başı eşleşenler, sonra içerenler, alfabetik.
    """
    q = (query or "").strip()
    if len(q) < 2:
        return []
    df = load_birlesik_ilac_fiyat_df()
    if df is None or df.empty or "İlaç adı" not in df.columns:
        return []
    col = df["İlaç adı"].astype(str).str.strip()
    col = col[col.str.len() > 0]
    try:
        mask = col.str.contains(re.escape(q), case=False, na=False, regex=True)
    except re.error:
        return []
    hit = col[mask].drop_duplicates().tolist()
    if not hit:
        return []
    qcf = q.casefold()
    starts = [x for x in hit if str(x).strip().casefold().startswith(qcf)]
    seen = set(starts)
    rest = [x for x in hit if x not in seen]
    starts_sorted = sorted(starts, key=lambda x: str(x).casefold())
    rest_sorted = sorted(rest, key=lambda x: str(x).casefold())
    return (starts_sorted + rest_sorted)[: int(limit)]
