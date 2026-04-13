"""
recete.org haber sayfasındaki HTML tablolarını okur (URL veya yerel yedek dosya).
İlaç adı normalize anahtarı ile tekil satırlar üretir.
"""

from __future__ import annotations

import io
import re
from html import unescape
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
from lxml import html as lxml_html

RECETE_HABER_URL = "http://www.recete.org/haberler/06102004.htm"
RECETE_LOCAL_HTML = Path(__file__).parent / "data" / "recete_haber_06102004.html"
REQUEST_TIMEOUT_S = 20


def _norm_key(s: object) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    t = str(s).strip()
    return " ".join(t.casefold().split())


def _parse_priceish(x: object) -> float:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return np.nan
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    s = str(x).strip()
    if not s or s.casefold() in ("nan", "-", "—", "–"):
        return np.nan
    s = s.replace(" ", "")
    if not re.fullmatch(r"[\d.,]+", s):
        s = re.sub(r"[^\d.\-]", "", s)
        if not s or s in (".", "-"):
            return np.nan
        try:
            return float(s)
        except ValueError:
            return np.nan
    # Yalnız rakam + . ve ,
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(",") == 1 and s.count(".") >= 1:
        s = s.replace(".", "").replace(",", ".")
    elif "," not in s and s.count(".") > 1:
        s = s.replace(".", "")
    elif "," not in s:
        pass
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cols = []
    for c in df.columns:
        if isinstance(c, tuple):
            cols.append(re.sub(r"\s+", " ", " ".join(str(x) for x in c if str(x) != "nan")).strip())
        else:
            cols.append(re.sub(r"\s+", " ", str(c).strip()))
    df.columns = cols
    return df


def _clean_table(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = _flatten_columns(df)
    df = df.dropna(axis=1, how="all").dropna(how="all")
    return df


def _pick_name_column(df: pd.DataFrame) -> str:
    best_c, best_score = df.columns[0], -1.0
    for c in df.columns:
        s = df[c].astype(str).str.strip()
        s = s.replace({"nan": ""})
        score = (s.str.len() >= 4).mean()
        cl = str(c).casefold()
        for kw in ("etken", "ilaç", "ilac", "ticari", "ürün", "urun", "adı", "adi", "preparat"):
            if kw in cl:
                score += 0.25
        if score > best_score:
            best_score = score
            best_c = c
    return best_c


def _pick_firma_column(df: pd.DataFrame, name_col: str) -> Optional[str]:
    for c in df.columns:
        if c == name_col:
            continue
        cl = str(c).casefold()
        if any(k in cl for k in ("firma", "üretici", "uretici", "laboratuvar", "sanayi", "şirket", "sirket")):
            return c
    return None


def _table_to_long(df: pd.DataFrame) -> list[dict]:
    df = _clean_table(df)
    if df.shape[1] < 1 or len(df) < 1:
        return []
    name_col = _pick_name_column(df)
    firma_col = _pick_firma_column(df, name_col)
    rows: list[dict] = []
    for _, r in df.iterrows():
        raw_name = r.get(name_col)
        k = _norm_key(raw_name)
        if len(k) < 3:
            continue
        ad = str(raw_name).strip()
        firma = ""
        if firma_col is not None:
            firma = str(r.get(firma_col, "")).strip()
            if firma.casefold() in ("nan", "none"):
                firma = ""
        price_vals: list[tuple[str, float]] = []
        text_parts: list[str] = []
        for c in df.columns:
            if c == name_col or c == firma_col:
                continue
            v = r[c]
            if pd.isna(v) or str(v).strip() == "" or str(v).strip().casefold() == "nan":
                continue
            p = _parse_priceish(v)
            if pd.notna(p) and p != 0.0:
                price_vals.append((str(c).strip(), p))
            else:
                t = str(v).strip()
                if len(t) > 1:
                    text_parts.append(f"{c}: {t}")
        rows.append(
            {
                "_k": k,
                "_ad": ad,
                "_firma": firma,
                "_prices": price_vals,
                "_text": text_parts,
            }
        )
    return rows


def _aggregate_recete_rows(all_rows: list[dict]) -> pd.DataFrame:
    if not all_rows:
        return pd.DataFrame()
    by_k: dict[str, dict] = {}
    for row in all_rows:
        k = row["_k"]
        if k not in by_k:
            by_k[k] = {
                "_ad": row["_ad"],
                "_firma": set(),
                "_prices": [],
                "_text": [],
            }
        b = by_k[k]
        if len(row["_ad"]) > len(b["_ad"]):
            b["_ad"] = row["_ad"]
        if row["_firma"]:
            b["_firma"].add(row["_firma"])
        b["_prices"].extend(row["_prices"])
        b["_text"].extend(row["_text"])

    out_rows = []
    for k, b in by_k.items():
        prices = b["_prices"]
        p1 = np.nan
        p1_label = ""
        if prices:
            # İlk anlamlı fiyat sütunu (çoğunlukla perakende / fiyat)
            pref = ("perakende", "fiyat", "piyasa", "kdv", "satış", "satis", "tl")
            ranked = sorted(
                prices,
                key=lambda x: (-any(p in x[0].casefold() for p in pref), -abs(x[1])),
            )
            p1_label, p1 = ranked[0]
        firma = " / ".join(sorted(b["_firma"])) if b["_firma"] else ""
        notes = " | ".join(dict.fromkeys(b["_text"]))
        out_rows.append(
            {
                "_k": k,
                "_ad_recete": b["_ad"],
                "_firma_recete": firma,
                "Reçete.org fiyat (sayı)": p1,
                "Reçete.org fiyat sütunu": p1_label,
                "Reçete.org notları": notes,
            }
        )
    return pd.DataFrame(out_rows)


def _load_recete_html() -> Optional[str]:
    if RECETE_LOCAL_HTML.exists():
        for enc in ("utf-8", "windows-1254", "latin-1"):
            try:
                return RECETE_LOCAL_HTML.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
    try:
        r = requests.get(
            RECETE_HABER_URL,
            timeout=REQUEST_TIMEOUT_S,
            headers={"User-Agent": "Mozilla/5.0 (compatible; medic-bot/1.0)"},
        )
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except (OSError, requests.RequestException):
        return None


def _cell_text(el) -> str:
    t = "".join(el.itertext())
    return unescape(re.sub(r"\s+", " ", t).strip())


def _html_tables_to_dfs(page_html: str) -> list[pd.DataFrame]:
    """pandas.read_html virgüllü ondalıkları bozduğu için lxml ile metin korunur."""
    root = lxml_html.fromstring(page_html.encode("utf-8", errors="replace"))
    out: list[pd.DataFrame] = []
    for table in root.xpath("//table"):
        rows: list[list[str]] = []
        for tr in table.xpath(".//tr"):
            cells = tr.xpath("./th|./td")
            if not cells:
                continue
            rows.append([_cell_text(c) for c in cells])
        if not rows:
            continue
        header, body = rows[0], rows[1:]
        if not body:
            continue
        df = pd.DataFrame(body, columns=[str(h).strip() or f"Col{i}" for i, h in enumerate(header)])
        out.append(df)
    return out


def read_recete_haber_df() -> Optional[pd.DataFrame]:
    page_html = _load_recete_html()
    if not page_html:
        return None
    tables = _html_tables_to_dfs(page_html)
    if not tables:
        try:
            tables = pd.read_html(io.StringIO(page_html), displayed_only=False)
        except (ValueError, ImportError):
            return None

    all_rows: list[dict] = []
    for tbl in tables:
        if not isinstance(tbl, pd.DataFrame):
            continue
        all_rows.extend(_table_to_long(tbl))
    agg = _aggregate_recete_rows(all_rows)
    if agg.empty:
        return None
    agg = agg.drop_duplicates(subset=["_k"], keep="first")
    return agg


def _merge_two_firma(a: object, b: object) -> str:
    sa = str(a).strip() if pd.notna(a) and str(a).strip().casefold() != "nan" else ""
    sb = str(b).strip() if pd.notna(b) and str(b).strip().casefold() != "nan" else ""
    if not sa:
        return sb
    if not sb:
        return sa
    if sa.casefold() == sb.casefold():
        return sa
    return f"{sa} | {sb}"


def merge_recete_into(
    base: pd.DataFrame,
    recete: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """base: İlaç adı, Firma, GKF, … — recete ile normalize ada göre outer join; tekrar yok."""
    if recete is None or recete.empty:
        out = base.copy()
        out["Reçete.org fiyat (sayı)"] = np.nan
        out["Reçete.org fiyat sütunu"] = np.nan
        out["Reçete.org notları"] = np.nan
        return out

    b = base.copy()
    b["_k"] = b["İlaç adı"].map(_norm_key)
    m = pd.merge(b, recete, on="_k", how="outer")

    ad_ref = m["İlaç adı"] if "İlaç adı" in m.columns else pd.Series(np.nan, index=m.index)
    ad_rec = m["_ad_recete"] if "_ad_recete" in m.columns else pd.Series(np.nan, index=m.index)
    mask = ad_ref.notna() & (ad_ref.astype(str).str.strip().str.len() > 0)
    ad = ad_ref.where(mask, ad_rec).fillna(ad_rec)

    firma_b = m["Firma"].fillna("").astype(str).str.strip() if "Firma" in m.columns else pd.Series("", index=m.index)
    firma_r = m["_firma_recete"].fillna("").astype(str).str.strip() if "_firma_recete" in m.columns else pd.Series("", index=m.index)
    firma = [_merge_two_firma(a, b) for a, b in zip(firma_b, firma_r)]

    def _col(name: str) -> pd.Series:
        if name not in m.columns:
            return pd.Series(np.nan, index=m.index)
        return m[name]

    out = pd.DataFrame(
        {
            "İlaç adı": ad.astype(str).str.strip(),
            "Firma": firma,
            "GKF (€)": _col("GKF (€)"),
            "Liste fiyatı (₺)": _col("Liste fiyatı (₺)"),
            "Barkod": _col("Barkod"),
            "Liste tarihi": _col("Liste tarihi"),
            "Reçete.org fiyat (sayı)": _col("Reçete.org fiyat (sayı)"),
            "Reçete.org fiyat sütunu": _col("Reçete.org fiyat sütunu"),
            "Reçete.org notları": _col("Reçete.org notları"),
        }
    )
    out = out[out["İlaç adı"].str.len() > 0]
    out["Barkod"] = out["Barkod"].replace("", np.nan)
    for c in ("Reçete.org fiyat sütunu", "Reçete.org notları"):
        if c in out.columns:
            out.loc[out[c].astype(str).str.strip() == "", c] = np.nan
    return out


def recete_source_hint() -> str:
    if RECETE_LOCAL_HTML.exists():
        return f"yerel yedek `{RECETE_LOCAL_HTML.name}`"
    return f"URL `{RECETE_HABER_URL}`"
