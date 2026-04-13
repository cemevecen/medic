"""
Birleşik ilaç fiyat tabloları: referans GKF (€) xlsx + web liste (₺) xlsx.
Ortak alanlar: ilaç adı, firma, fiyat (farklı para birimleri ayrı sütunlarda).
Tekrarlayan ilaç adları (normalize edilmiş) tek satırda birleştirilir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

REFERANS_PATH = Path(__file__).parent / "data" / "referans_bazli_ilac_fiyat_listesi.xlsx"
WEB_PATH = Path(__file__).parent / "data" / "ilac_fiyat_web_listesi.xlsx"
_REFERANS_SKIPROWS = 4


def _norm_key(s: object) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    t = str(s).strip()
    return " ".join(t.casefold().split())


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
    ref = _read_referans()
    web = _read_web()
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
        return _ensure_unique_norm(w)

    if web is None:
        r = ref.drop(columns=["_k"]).copy()
        r["Liste fiyatı (₺)"] = np.nan
        r["Barkod"] = np.nan
        r["Liste tarihi"] = np.nan
        cols = ["İlaç adı", "Firma", "GKF (€)", "Liste fiyatı (₺)", "Barkod", "Liste tarihi"]
        r = r[cols]
        return _ensure_unique_norm(r)

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
    return _ensure_unique_norm(out)


@st.cache_data(show_spinner=False)
def load_referans_fiyat_df() -> Optional[pd.DataFrame]:
    """Geriye dönük uyumluluk: birleşik tablonun yalnızca GKF dolu satırları (3 sütun)."""
    full = load_birlesik_ilac_fiyat_df()
    if full is None:
        return None
    sub = full[full["GKF (€)"].notna()].copy()
    return sub[["İlaç adı", "Firma", "GKF (€)"]].reset_index(drop=True)
