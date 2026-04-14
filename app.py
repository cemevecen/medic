"""
WikiPharma — ana Streamlit arayüzü
Canlı: https://medicalsearch.streamlit.app/ · Kaynak: https://github.com/cemevecen/medic
"""

import os
import json
import html
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus, urlencode

import streamlit as st
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# ═════════════════════════════════════════════
# API Bilgilerini Kalıcı Olarak Kaydet/Yükle
# ═════════════════════════════════════════════
CONFIG_API_PATH = Path(__file__).parent / "config_api.json"

def load_api_config():
    """API bilgilerini config dosyasından yükle"""
    if CONFIG_API_PATH.exists():
        try:
            with open(CONFIG_API_PATH, "r") as f:
                config = json.load(f)
                for key, value in config.items():
                    if value and f"st_session_{key}" not in st.session_state:
                        st.session_state[key] = value
        except Exception:
            pass

# Uygulamayı başlatırken yapılandırmayı yükle
load_api_config()


def _pg_ilac_autocomplete_suggestion_html(query: str, candidate: str) -> str:
    """Yazılan kısım düz, tamamlayan kısım kalın; metin kaçışlı (XSS önlemi)."""
    q = (query or "").strip()
    c = candidate or ""
    esc = html.escape
    if not c:
        return ""
    if not q:
        return esc(c)
    if c.casefold().startswith(q.casefold()):
        pre, suf = c[: len(q)], c[len(q) :]
        return esc(pre) + (f"<strong>{esc(suf)}</strong>" if suf else "")
    q_cf = q.casefold()
    c_cf = c.casefold()
    idx = c_cf.find(q_cf)
    if idx >= 0:
        pre, mid, post = c[:idx], c[idx : idx + len(q)], c[idx + len(q) :]
        return esc(pre) + f"<strong>{esc(mid)}</strong>" + esc(post)
    return esc(c)


# Birleşik fiyat tablosu yok/boşsa: yalnızca gerçek ticari adlar (örnek/test/demo ibaresi yok)
_DRUG_SEED_POOL: tuple[str, ...] = (
    "PAROL 500 MG TABLET",
    "AUGMENTIN 1 G FILM TABLET",
    "NEXIUM 40 MG IV ENJEKSIYONLUK TOZ",
    "MAJEZIK 100 MG FILM TABLET",
    "MINOSET PLUS GRANUL",
    "BUSCOPAN 10 MG COATED TABLET",
    "VENTOLIN 100 MCG INHALER",
    "LANSOR 30 MG KAPSUL",
    "DRAMAMINE 50 MG TABLET",
    "CALPOL SUSPANSIYON 120 MG/5 ML",
)


def _pg_sample_10_unique_ilac_from_arsiv() -> list[str]:
    """Birleşik fiyat tablosundan 10 ilaç adı (rastgele); tablo yoksa havuzdan rastgele 10 ad."""
    import random

    try:
        from referans_ilac_fiyat import load_birlesik_ilac_fiyat_df

        df = load_birlesik_ilac_fiyat_df()
    except Exception:
        df = None
    if df is None or df.empty or "İlaç adı" not in df.columns:
        return list(random.sample(_DRUG_SEED_POOL, 10))
    col = df["İlaç adı"].astype(str).str.strip()
    col = col[col.str.len() > 1]
    uniq = col.drop_duplicates().tolist()
    if not uniq:
        return list(random.sample(_DRUG_SEED_POOL, 10))
    if len(uniq) < 10:
        return random.choices(uniq, k=10)
    return random.sample(uniq, 10)


def _pg_ensure_son_aranan_buffers() -> None:
    if "pg_recent_seeds" not in st.session_state:
        st.session_state.pg_recent_seeds = _pg_sample_10_unique_ilac_from_arsiv()
    if "pg_recent_user_chrono" not in st.session_state:
        st.session_state.pg_recent_user_chrono = []


def _pg_push_son_aranan_ilac(raw: object) -> None:
    """Başarılı analiz sonrası: en yeni üstte, en fazla 10; aynı ad tekrar aranırsa en üste taşınır."""
    name = str(raw or "").strip()
    if not name or name.casefold() in ("nan", "none", "—", "-", "ilaç"):
        return
    _pg_ensure_son_aranan_buffers()
    u: list[str] = st.session_state.pg_recent_user_chrono
    if name in u:
        u.remove(name)
    u.insert(0, name)
    while len(u) > 10:
        u.pop()


def _pg_render_son_aranan_ilaclar_panel() -> None:
    """10 satır: üstten alta gerçek aramalar (en yeni üstte), kalan satırlar rastgele arşiv adları; ibare yok."""
    _pg_ensure_son_aranan_buffers()
    seeds: list[str] = list(st.session_state.pg_recent_seeds or [])
    if len(seeds) < 10:
        seeds = (seeds + list(_DRUG_SEED_POOL))[:10]
    user: list[str] = list(st.session_state.pg_recent_user_chrono or [])
    rows_html: list[str] = []
    for i in range(10):
        if i < len(user):
            txt = user[i]
        else:
            j = i - len(user)
            txt = seeds[j] if j < len(seeds) else "—"
        rows_html.append(
            '<div class="pg-recent-row" role="listitem">'
            f'<span class="pg-recent-badge">{i + 1}</span>'
            f'<span class="pg-recent-name">{html.escape(txt)}</span>'
            "</div>"
        )
    st.markdown(
        '<div class="pg-recent-wrap">'
        '<div class="pg-recent-head">'
        '<p class="pg-recent-title">Son aranan ilaçlar</p>'
        "</div>"
        '<div class="pg-recent-list" role="list" aria-label="Son aranan ilaçlar">'
        + "".join(rows_html)
        + "</div></div>",
        unsafe_allow_html=True,
    )


def _dataframe_noneish_to_dash(df):
    """Eksik değerler ile metin olarak 'None' / 'nan' vb. görünen tüm hücreleri '-' yapar (Streamlit tablo)."""
    import pandas as pd

    out = df.copy()
    bad_tokens = frozenset(
        ("none", "nan", "<na>", "<nat>", "nat", "null", "undefined")
    )
    for c in out.columns:
        s = out[c]
        mask = pd.isna(s)
        try:
            t = s.astype(str).str.strip()
            mask = mask | t.str.casefold().isin(bad_tokens)
        except (TypeError, ValueError):
            pass
        if not mask.any():
            continue
        if pd.api.types.is_numeric_dtype(s) and not isinstance(s.dtype, pd.CategoricalDtype):
            v = s.astype(object)
            v.loc[mask] = "-"
            out[c] = v
        else:
            out.loc[mask, c] = "-"
    return out


@st.cache_data(show_spinner=False)
def _cached_ilac_fiyat_sekmesi_gosterim_df():
    """Fiyatlar sekmesi: gizlenen sütunlar + tire dönüşümü tek seferde (tekrarlayan iş yükünü keser)."""
    from referans_ilac_fiyat import load_birlesik_ilac_fiyat_df

    raw = load_birlesik_ilac_fiyat_df()
    if raw is None:
        return None
    cut = raw.drop(
        columns=[
            "GKF (€)",
            "Reçete.org fiyat (sayı)",
            "Reçete.org fiyat sütunu",
            "Reçete.org notları",
        ],
        errors="ignore",
    )
    return _dataframe_noneish_to_dash(cut)


# st.dataframe sabit yükseklik + iç kaydırma; satırlar tek tek DOM’a basılmaz (grid sanallaştırması).
_FIYAT_SEKMESI_DF_VIEWPORT_HEIGHT_PX = 640
# İlk sekme açılışında progress bar en az bu kadar saniye görünsün (çok hızlı cache için)
_PG_WARMUP_MIN_VISIBLE_SEC = 1.3


def _pg_warmup_progress(tab_key: str, steps: list[tuple[str, Callable[[], Any]]]) -> Any:
    """
    Fiyatlar / Firmalar / Özellikli / Fihrist ilk açılışında cache ısıtırken progress bar.
    Tüm Streamlit ve veri hataları yutulur; istisna sıçratmaz.
    """
    flag = f"pg_tab_warm_{tab_key}"
    if not steps:
        return None
    if st.session_state.get(flag):
        try:
            return steps[-1][1]()
        except Exception:
            return None
    t0 = time.perf_counter()
    prog = None
    try:
        try:
            prog = st.progress(0, text="Hazırlanıyor…")
        except TypeError:
            prog = st.progress(0)
    except Exception:
        prog = None
    n = len(steps)
    out: Any = None
    try:
        for i, (label, fn) in enumerate(steps):
            try:
                if prog is not None:
                    try:
                        prog.progress(min(i / max(n, 1), 0.92), text=label)
                    except TypeError:
                        prog.progress(min(i / max(n, 1), 0.92))
            except Exception:
                pass
            try:
                out = fn()
            except Exception:
                out = None
        try:
            if prog is not None:
                try:
                    prog.progress(1.0, text="Tamam")
                except TypeError:
                    prog.progress(1.0)
        except Exception:
            pass
    finally:
        try:
            elapsed = time.perf_counter() - t0
            rem = _PG_WARMUP_MIN_VISIBLE_SEC - elapsed
            if rem > 0:
                time.sleep(rem)
        except Exception:
            pass
        try:
            if prog is not None:
                prog.empty()
        except Exception:
            pass
        try:
            st.session_state[flag] = True
        except Exception:
            pass
    return out


@st.fragment
def _pg_fragment_ilac_fiyatlari():
    st.markdown(
        '<p class="pg-section">İlaç Bilgileri & Fiyatları</p>',
        unsafe_allow_html=True,
    )

    _rf_df = _pg_warmup_progress(
        "fiyatlar",
        [
            (
                "Birleşik kaynaklar yükleniyor…",
                lambda: __import__(
                    "referans_ilac_fiyat", fromlist=["load_birlesik_ilac_fiyat_df"]
                ).load_birlesik_ilac_fiyat_df(),
            ),
            ("Tablo hazırlanıyor…", lambda: _cached_ilac_fiyat_sekmesi_gosterim_df()),
        ],
    )
    if _rf_df is None:
        st.warning(
            "En az bir kaynak gerekir: `data/referans_bazli_ilac_fiyat_listesi.xlsx` ve/veya "
            "`data/ilac_fiyat_web_listesi.xlsx`."
        )
        return
    if _rf_df.empty:
        st.warning("Birleşik fiyat tablosu şu an boş.")
        return

    _rf_q = st.text_input(
        "Listede ara (ilaç, firma veya barkod; boş = tümü)",
        placeholder="örn: ABILIFY, PFİZER, 86995…",
        key="referans_fiyat_filter",
    )
    _rf_show = _rf_df
    if (_rf_q or "").strip():
        q = _rf_q.strip()
        _m = _rf_show["İlaç adı"].astype(str).str.contains(
            q, case=False, na=False, regex=False
        )
        _m = _m | _rf_show["Firma"].astype(str).str.contains(
            q, case=False, na=False, regex=False
        )
        if "Barkod" in _rf_show.columns:
            _m = _m | _rf_show["Barkod"].astype(str).str.contains(
                q, case=False, na=False, regex=False
            )
        _rf_show = _rf_show[_m]

    _n_total = len(_rf_show)
    if _n_total == 0:
        st.info("Aramanızla eşleşen satır yok.")
        return

    _rf_view = _rf_show.copy()
    if _n_total > 25_000:
        st.warning(
            f"**{_n_total}** satır yüklendi; tarayıcı yavaşlayabilir. "
            "Daha hızlı çalışmak için arama kutusu ile listeyi daraltın."
        )

    if "İlaç adı" in _rf_view.columns:
        _ilac_for_links: list[str] | None = ["İlaç adı"]
    else:
        _h = _ilac_name_columns_for_google_search(_rf_view)
        _ilac_for_links = _h if _h else None
    _rf_view, _rf_gcfg, _rf_gorder = _prep_df_google_links_for_streamlit(_rf_view, link_cols=_ilac_for_links)

    _col_cfg_all = {
        "Liste fiyatı (₺)": st.column_config.NumberColumn("Liste fiyatı (₺)", format="%.2f"),
        "Barkod": st.column_config.TextColumn("Barkod"),
    }
    _col_cfg = {k: v for k, v in _col_cfg_all.items() if k in _rf_view.columns}
    _col_cfg.update(_rf_gcfg)
    _df_kw: dict = dict(
        use_container_width=True,
        height=_FIYAT_SEKMESI_DF_VIEWPORT_HEIGHT_PX,
        hide_index=True,
    )
    if _col_cfg:
        _df_kw["column_config"] = _col_cfg
    if _rf_gorder is not None:
        _df_kw["column_order"] = _rf_gorder
    st.dataframe(_rf_view, **_df_kw)
    if _n_total > 12:
        st.caption(
            f"Toplam **{_n_total}** satır — tümünü görmek için **tablo kutusunun içinde** dikey kaydırın."
        )
    else:
        st.caption(f"Toplam **{_n_total}** satır.")


# Fihrist chip’leri: yalnızca tek harf (ilaç adının ilk karakterine göre gruplama; AL vb. yok)
_FIHRIST_NAV_KEYS = (
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "I",
    "J",
    "K",
    "L",
    "M",
    "N",
    "O",
    "P",
    "R",
    "S",
    "T",
    "U",
    "V",
    "W",
    "X",
    "Y",
    "Z",
)
_FIHRIST_TABLE_MAX = 180
# Firmalar sekmesi: fihrist A–Z + rakamla başlayan firmalar
_FIRMA_ILAC_NAV_KEYS = _FIHRIST_NAV_KEYS + ("0-9",)
_FIRMA_ILAC_PILLS_MAX = 72
# ilacrehberi.com fihrist düzenine paralel referans tablo (yerel XLSX ile birlikte kullanılabilir)
_FIHRIST_REF_GOOGLE_SHEETS = (
    "https://docs.google.com/spreadsheets/d/13Hd8k4zVylcRSGB9FJpTpFqBUJ7FGnytKxvAV-TIWaY/edit?gid=0#gid=0"
)
# Reçete / liste XLSX (export_ilacrehberi_recete_listeleri_xlsx.py) — referans eşleme tablosu
_OZELLIKLI_REF_GOOGLE_SHEETS = (
    "https://docs.google.com/spreadsheets/d/1GK1cJHpzL6VQwfxlWT2g9jZp-8nq1dmQtREh_RWRzIU/edit?gid=1046254751#gid=1046254751"
)
_OZELLIKLI_ILAC_LISTELERI_XLSX = "ilacrehberi_ilac_listeleri.xlsx"
_OZELLIKLI_SHEET_ORDER = (
    "Yesil_Receteli",
    "Kirmizi_Receteli",
    "Mor_Receteli",
    "Turuncu_Receteli",
    "Takibi_Zorunlu",
    "Recetesiz",
    "Geri_Cekilen",
)
_OZELLIKLI_SHEET_LABELS_TR = {
    "Yesil_Receteli": "Yeşil reçeteli",
    "Kirmizi_Receteli": "Kırmızı reçeteli",
    "Mor_Receteli": "Mor reçeteli",
    "Turuncu_Receteli": "Turuncu reçeteli",
    "Takibi_Zorunlu": "Takibi zorunlu reçeteli",
    "Recetesiz": "Reçetesiz satılan",
    "Geri_Cekilen": "Geri çekilen",
}


def _df_row_matches_substring(df, q: str):
    """Tüm sütunlarda büyük/küçük harf duyarsız alt dizgi araması (Fiyatlar sekmesiyle aynı mantık)."""
    import pandas as pd

    needle = (q or "").strip()
    if not needle:
        return pd.Series(True, index=df.index)
    m = pd.Series(False, index=df.index)
    for c in df.columns:
        m = m | df[c].astype(str).str.contains(needle, case=False, na=False, regex=False)
    return m


def _ozellikli_column_config_for_df(df):
    """Sayısal sütunlarda Fiyatlar sekmesine yakın grid biçimi; barkod metin sütunu."""
    import pandas as pd

    cfg: dict = {}
    for c in df.columns:
        name = str(c)
        s = df[c]
        u = name.upper().replace("İ", "I")
        if "BARKOD" in u.replace(" ", ""):
            cfg[name] = st.column_config.TextColumn(name)
            continue
        if pd.api.types.is_bool_dtype(s):
            continue
        if pd.api.types.is_numeric_dtype(s):
            if pd.api.types.is_integer_dtype(s):
                cfg[name] = st.column_config.NumberColumn(name, format="%d")
            else:
                cfg[name] = st.column_config.NumberColumn(name, format="%.2f")
    return cfg


def _resolve_ozellikli_ilac_xlsx_path() -> Path | None:
    """Sıra: MEDIC_OZELLIKLI_ILAC_XLSX, sonra Masaüstü/Desktop (yerel export), son paket data/."""
    raw_env = (os.environ.get("MEDIC_OZELLIKLI_ILAC_XLSX") or "").strip()
    if raw_env:
        p = Path(raw_env).expanduser()
        if p.is_file():
            return p.resolve()
    for root in (
        Path.home() / "Desktop",
        Path.home() / "Masaüstü",
        Path(__file__).resolve().parent / "data",
    ):
        p = root / _OZELLIKLI_ILAC_LISTELERI_XLSX
        if p.is_file():
            return p.resolve()
    return None


def _ozellikli_column_is_kt_kub(name: object) -> bool:
    """KT_KUB / 'KT KUB' / kt-kub vb. tek sütun anahtarı (harf dışı karakterler yok sayılır)."""
    key = "".join(ch for ch in str(name).strip().upper() if ch.isalnum())
    return key == "KTKUB"


@st.cache_data(show_spinner=False)
def _cached_ozellikli_ilac_listeleri(_cache_bust: int = 5) -> tuple[dict, Path] | None:
    """ilacrehberi_ilac_listeleri.xlsx — tüm sheet'ler; (sheet adı → DataFrame, dosya yolu)."""
    _ = _cache_bust
    import pandas as pd

    p = _resolve_ozellikli_ilac_xlsx_path()
    if not p:
        return None
    raw = pd.read_excel(p, sheet_name=None, engine="openpyxl")
    out: dict[str, pd.DataFrame] = {}
    for name, df in raw.items():
        if df is None or df.empty:
            out[str(name)] = df
            continue
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        _kt_kub_cols = [c for c in df.columns if _ozellikli_column_is_kt_kub(c)]
        if _kt_kub_cols:
            df = df.drop(columns=_kt_kub_cols, errors="ignore")
        df = df.dropna(how="all").reset_index(drop=True)
        out[str(name)] = df
    return (out, p) if out else None


def _pg_fragment_ozellikli_ilaclar():
    st.markdown(
        '<p class="pg-section">Özellikli ilaçlar</p>',
        unsafe_allow_html=True,
    )
    cached = _pg_warmup_progress(
        "ozellikli_ilaclar",
        [("Excel sayfaları okunuyor…", lambda: _cached_ozellikli_ilac_listeleri())],
    )
    if not cached:
        st.markdown(
            f"`{_OZELLIKLI_ILAC_LISTELERI_XLSX}` bulunamadı. Yerelde önce **Masaüstü / Desktop**, "
            f"yoksa **`data/`** içinde aranır. Tam yol: `MEDIC_OZELLIKLI_ILAC_XLSX`. "
            "Üretim: `scripts/export_ilacrehberi_recete_listeleri_xlsx.py` "
            "(`-o data/ilacrehberi_ilac_listeleri.xlsx`)."
        )
        return

    data, _ = cached

    seen = set(data.keys())
    ordered = [s for s in _OZELLIKLI_SHEET_ORDER if s in data]
    ordered += sorted(seen.difference(ordered))

    tab_labels = [
        f"{_OZELLIKLI_SHEET_LABELS_TR.get(s, s.replace('_', ' '))} ({len(data[s]) if data.get(s) is not None and not data[s].empty else 0})"
        for s in ordered
    ]
    tabs = st.tabs(tab_labels)
    for tab, sheet in zip(tabs, ordered):
        with tab:
            df = data.get(sheet)
            if df is None or df.empty:
                st.caption("Bu sayfada satır yok.")
                continue
            base = _dataframe_noneish_to_dash(df)
            _oz_q = st.text_input(
                "Listede ara (tüm sütunlarda; boş = tümü)",
                placeholder="örn: ABILIFY, PFİZER, 86995…",
                key=f"ozellikli_liste_filter_{sheet}",
            )
            show = base
            if (_oz_q or "").strip():
                show = base[_df_row_matches_substring(base, _oz_q)].reset_index(drop=True)
            ntot = len(show)
            if ntot == 0:
                st.info("Aramanızla eşleşen satır yok.")
                continue
            if ntot > 25_000:
                st.warning(
                    f"**{ntot}** satır yüklendi; tarayıcı yavaşlayabilir. "
                    "Daha hızlı çalışmak için arama kutusu ile listeyi daraltın."
                )
            show, _oz_gcfg, _oz_gorder = _prep_df_google_links_for_streamlit(show)
            _oz_col_cfg = _ozellikli_column_config_for_df(show)
            _oz_col_cfg.update(_oz_gcfg)
            _oz_df_kw: dict = dict(
                use_container_width=True,
                height=_FIYAT_SEKMESI_DF_VIEWPORT_HEIGHT_PX,
                hide_index=True,
            )
            if _oz_col_cfg:
                _oz_df_kw["column_config"] = _oz_col_cfg
            if _oz_gorder is not None:
                _oz_df_kw["column_order"] = _oz_gorder
            st.dataframe(show, **_oz_df_kw)
            if ntot > 12:
                st.caption(
                    f"Toplam **{ntot}** satır — tümünü görmek için **tablo kutusunun içinde** dikey kaydırın."
                )
            else:
                st.caption(f"Toplam **{ntot}** satır.")


@st.cache_data(show_spinner=False)
def _cached_ilacrehberi_fihrist_df(_cache_bust: int = 3):
    """Masaüstü veya data/ altındaki ilacrehberi_fihrist.xlsx (yalnızca grup + ad)."""
    _ = _cache_bust
    import pandas as pd

    roots = (
        Path(__file__).resolve().parent / "data",
        Path.home() / "Desktop",
    )
    for root in roots:
        p = root / "ilacrehberi_fihrist.xlsx"
        if not p.exists():
            continue
        try:
            df = pd.read_excel(p)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        cols = {str(c).strip().lower(): c for c in df.columns}
        def _pick(*names):
            for n in names:
                if n in cols:
                    return cols[n]
            return None

        c_grp = _pick("fihrist_grubu", "grup")
        c_ad = _pick("ilac_adi", "i̇laç adı", "ilac adi", "ad")
        if not c_ad:
            continue
        out = pd.DataFrame(
            {
                "fihrist_grubu": df[c_grp].astype(str) if c_grp else "",
                "ilac_adi": df[c_ad].astype(str).str.strip(),
            }
        )
        out = out[out["ilac_adi"].str.len() > 0].reset_index(drop=True)
        return out
    return None


def _google_search_url(query: str) -> str:
    """Harici arama; ilacrehberi.com’a yönlendirme kullanılmaz."""
    q = (query or "").strip()
    if not q:
        return "https://www.google.com/"
    return "https://www.google.com/search?q=" + quote_plus(q)


def _ascii_upper_tr(s: str) -> str:
    """Sütun adı eşlemesi: Türkçe harfleri ASCII’ye (İLAÇ → ILAC; REÇETELİ → RECETELI)."""
    u = str(s).strip().upper()
    for a, b in (
        ("İ", "I"),
        ("İ", "I"),
        ("Ç", "C"),
        ("Ğ", "G"),
        ("Ö", "O"),
        ("Ş", "S"),
        ("Ü", "U"),
        ("Â", "A"),
        ("Î", "I"),
        ("Û", "U"),
    ):
        u = u.replace(a, b)
    return u


def _ilac_name_columns_for_google_search(df) -> list[str]:
    """Ticari ürün adı sütunları (firma, etken madde, barkod, fiyat, tarih, URL alanları hariç)."""
    if df is None or df.empty or not len(df.columns):
        return []
    out: list[str] = []
    for c in df.columns:
        cs = str(c).strip()
        u = _ascii_upper_tr(cs)
        if u in ("DETAY_URL", "_UYARI", "ALAN", "BILGI"):
            continue
        if "DETAY" in u and "URL" in u.replace(" ", ""):
            continue
        if "ETKIN" in u and "MADDE" in u:
            continue
        if "FIRMA" in u.replace(" ", "") and "ADI" in u:
            continue
        if "BARKOD" in u.replace(" ", ""):
            continue
        if "FIYAT" in u or "GKF" in u:
            continue
        if "TARIH" in u or "TARIHI" in u:
            continue
        if "ILAC" in u:
            out.append(c)
            continue
        low = cs.casefold()
        if "ilac" in low and "adi" in low.replace("ı", "i"):
            out.append(c)
            continue
    if not out:
        for c in df.columns:
            u2 = _ascii_upper_tr(c).replace(" ", "")
            if ("RECETELI" in u2 or "RECETESIZ" in u2) and "AD" in u2:
                out.append(c)
                break
    seen: set[str] = set()
    dedup: list[str] = []
    for c in out:
        if c not in seen:
            dedup.append(c)
            seen.add(c)
    return dedup


def _google_search_cell_url(v) -> str:
    t = str(v).strip()
    if not t or t == "-" or t.casefold() in ("nan", "none", "<na>"):
        return "https://www.google.com/"
    return _google_search_url(t)


def _prep_df_google_links_for_streamlit(df, link_cols: list[str] | None = None):
    """
    İlaç adı sütunları metin olarak kalır; her biri için hemen sağında dar bir link sütunu
    (Streamlit LinkColumn — display_text yalnızca sabit/ikon/URL-regex; ayrı etiket sütunu desteklenmez).
    Dönüş: (df_yeni, link_column_config, column_order | None).
    """
    if df is None or df.empty:
        return df, {}, None
    cols = list(link_cols) if link_cols is not None else _ilac_name_columns_for_google_search(df)
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return df, {}, None
    out = df.copy()
    cfg: dict = {}
    col_to_ucol: dict[str, str] = {}
    for i, c in enumerate(cols):
        series = out[c].astype(str)
        ucol = f"_google_{i}"
        while ucol in out.columns:
            ucol = f"{ucol}_"
        out[ucol] = series.map(_google_search_cell_url)
        col_to_ucol[c] = ucol
        cfg[ucol] = st.column_config.LinkColumn(
            "↗",
            width="small",
            display_text=":material/open_in_new:",
            help=f"Google'da «{str(c)}» ile ara",
            validate=r"^https://",
        )
    orig = [x for x in df.columns]
    order: list[str] = []
    for col in orig:
        order.append(col)
        if col in col_to_ucol:
            order.append(col_to_ucol[col])
    for col in out.columns:
        if col not in order:
            order.append(col)
    return out, cfg, order


def _fihrist_md_link_label(text: str) -> str:
    """Markdown [etiket](url) için tablo hücresi / köşeli parantez kaçışı."""
    t = str(text).replace("\\", "\\\\").replace("|", "\\|")
    t = t.replace("[", "\\[").replace("]", "\\]")
    return t


def _fihrist_first_letter_mask(series, chip: str):
    """İlaç adının ilk karakteri `chip` ile eşleşen satırlar (ör. ALBACORT → A)."""
    import pandas as pd

    ch = (chip or "A").strip()
    if len(ch) != 1:
        ch = "A"
    s = series.astype(str).str.strip()
    ok = s.str.len() > 0
    first = s.str.slice(0, 1)
    return ok & (first.str.casefold() == ch.casefold())


def _firma_matches_nav_letter(firma: str, chip: str) -> bool:
    """Firma adının ilk karakteri fihrist harfi veya rakam grubu (0-9) ile eşleşir mi?"""
    import pandas as pd

    c = (chip or "A").strip()
    s = (firma or "").strip()
    if not s:
        return False
    if c == "0-9":
        return s[0].isdigit()
    if len(c) != 1:
        return False
    return bool(_fihrist_first_letter_mask(pd.Series([s]), c).iloc[0])


@st.cache_data(show_spinner=False)
def _cached_firma_ilac_arsiv(_cache_bust: int = 1) -> dict[str, list[dict[str, str]]]:
    """
    Birleşik fiyat tablosu + özellikli liste XLSX: firma → [{İlaç adı, Kaynak}, …].
    Kaynaklar birleşik fiyat ve liste sayfası adlarıdır.
    """
    _ = _cache_bust
    from collections import defaultdict

    from recete_haber import _pick_firma_column, _pick_name_column

    acc: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    try:
        from referans_ilac_fiyat import load_birlesik_ilac_fiyat_df

        pdf = load_birlesik_ilac_fiyat_df()
    except Exception:
        pdf = None
    if pdf is not None and not pdf.empty and "İlaç adı" in pdf.columns:
        fc = "Firma" if "Firma" in pdf.columns else None
        if fc:
            for _, r in pdf.iterrows():
                ad = str(r["İlaç adı"]).strip()
                fm = str(r[fc]).strip()
                if not ad or ad in ("-", "—") or ad.casefold() in ("nan", "none"):
                    continue
                if not fm or fm in ("-", "—") or fm.casefold() in ("nan", "none"):
                    continue
                acc[fm][ad].add("Fiyatlar")

    oz = _cached_ozellikli_ilac_listeleri()
    if oz:
        data, _ = oz
        for sheet, df in data.items():
            if df is None or df.empty:
                continue
            try:
                name_col = _pick_name_column(df)
                firma_col = _pick_firma_column(df, name_col)
            except Exception:
                continue
            if not firma_col:
                continue
            sk = _OZELLIKLI_SHEET_LABELS_TR.get(sheet, sheet.replace("_", " "))
            for _, r in df.iterrows():
                ad = str(r.get(name_col, "")).strip()
                fm = str(r.get(firma_col, "")).strip()
                if not ad or ad in ("-", "—") or ad.casefold() in ("nan", "none"):
                    continue
                if not fm or fm in ("-", "—") or fm.casefold() in ("nan", "none"):
                    continue
                acc[fm][ad].add(sk)

    out: dict[str, list[dict[str, str]]] = {}
    for fm, drugs in acc.items():
        rows: list[dict[str, str]] = []
        for ad in sorted(drugs.keys(), key=lambda x: x.casefold()):
            rows.append(
                {
                    "İlaç adı": ad,
                    "Kaynak": "; ".join(sorted(drugs[ad])),
                }
            )
        out[fm] = rows
    return out


@st.fragment
def _pg_fragment_ilac_firmalari():
    st.markdown(
        '<p class="pg-section">Firmalar</p>',
        unsafe_allow_html=True,
    )

    by_firma = _pg_warmup_progress(
        "firmalar",
        [
            (
                "Fiyat listesi yükleniyor…",
                lambda: __import__(
                    "referans_ilac_fiyat", fromlist=["load_birlesik_ilac_fiyat_df"]
                ).load_birlesik_ilac_fiyat_df(),
            ),
            ("Özellikli reçete listeleri…", lambda: _cached_ozellikli_ilac_listeleri()),
            ("Firma arşivi oluşturuluyor…", lambda: _cached_firma_ilac_arsiv()),
        ],
    )
    if not by_firma:
        st.warning(
            "Firma listesi oluşturulamadı. En az biri gerekir: birleşik fiyat kaynakları "
            f"(`referans_ilac_fiyat`) ve/veya `{_OZELLIKLI_ILAC_LISTELERI_XLSX}`."
        )
        return

    all_firms = sorted(by_firma.keys(), key=lambda x: x.casefold())
    st.text_input(
        "firma_ara",
        placeholder="örn: Abdi, Pfizer, Santa…",
        key="pg_firma_q",
        label_visibility="collapsed",
    )
    needle = (st.session_state.get("pg_firma_q") or "").strip()

    st.session_state.setdefault("pg_firma_letter", "A")
    _fl = str(st.session_state.get("pg_firma_letter") or "A").strip()
    if _fl not in _FIRMA_ILAC_NAV_KEYS:
        st.session_state.pg_firma_letter = "A"
    st.pills(
        "İlk harf",
        options=list(_FIRMA_ILAC_NAV_KEYS),
        selection_mode="single",
        key="pg_firma_letter",
        label_visibility="collapsed",
    )
    letter = str(st.session_state.get("pg_firma_letter") or "A").strip()
    if letter not in _FIRMA_ILAC_NAV_KEYS:
        letter = "A"

    if needle:
        cand = [f for f in all_firms if needle.casefold() in f.casefold()]
    else:
        cand = [f for f in all_firms if _firma_matches_nav_letter(f, letter)]

    if not cand:
        st.info("Bu filtreyle eşleşen firma yok; arama kutusu veya harf seçimini değiştirin.")
        return

    if len(cand) > _FIRMA_ILAC_PILLS_MAX:
        st.caption(
            f"**{len(cand)}** eşleşme var; chip listesi ilk **{_FIRMA_ILAC_PILLS_MAX}** firma ile sınırlı. "
            "Daraltmak için arama kutusunu kullanın."
        )
        cand = cand[:_FIRMA_ILAC_PILLS_MAX]

    import hashlib

    _firma_pick_key = (
        "pg_firma_pick_"
        + hashlib.sha1(f"{letter}\n{needle}".encode("utf-8")).hexdigest()[:16]
    )
    st.pills(
        "Firma",
        options=cand,
        selection_mode="single",
        key=_firma_pick_key,
        label_visibility="collapsed",
    )
    sel = str(st.session_state.get(_firma_pick_key) or "").strip()
    if not sel or sel not in by_firma:
        st.info("Yukarıdan bir **firma** chip’i seçin; ilaçlar tabloda listelenir.")
        return

    st.markdown(
        f'<h3 style="font-size:1.05rem;font-weight:700;margin:0.75rem 0 0.4rem">{html.escape(sel)}</h3>',
        unsafe_allow_html=True,
    )
    rows = by_firma[sel]
    import pandas as pd

    show = pd.DataFrame(rows)
    st.dataframe(
        show,
        use_container_width=True,
        height=min(520, 120 + min(len(show), 24) * 36),
        hide_index=True,
    )
    st.caption(f"**{len(show)}** ilaç adı (aynı ad farklı kaynaklarda birleştirildi).")


@st.fragment
def _pg_fragment_ilac_fihrist():
    st.markdown(
        '<p class="pg-section">Fihrist</p>',
        unsafe_allow_html=True,
    )
    df = _pg_warmup_progress(
        "fihrist",
        [("Fihrist dosyası okunuyor…", lambda: _cached_ilacrehberi_fihrist_df())],
    )
    if df is None or df.empty:
        st.warning(
            "`ilacrehberi_fihrist.xlsx` bulunamadı veya boş. "
            "Dosyayı `data/` veya Masaüstüne koyun; `scripts/export_ilacrehberi_fihrist_xlsx.py` ile üretebilirsiniz."
        )
        st.caption(
            f"Referans: [İlaç A-Z fihrist — Google Sheets]({_FIHRIST_REF_GOOGLE_SHEETS}) · "
            "[ilacrehberi.com — fihrist](https://www.ilacrehberi.com/ilac-fihrist/)"
        )
        return

    st.session_state.setdefault("pg_fihrist_pills", "A")
    _fp = str(st.session_state.get("pg_fihrist_pills") or "A").strip()
    if _fp not in _FIHRIST_NAV_KEYS:
        st.session_state.pg_fihrist_pills = "A"
    st.pills(
        "Fihrist harfi / grup",
        options=list(_FIHRIST_NAV_KEYS),
        selection_mode="single",
        key="pg_fihrist_pills",
        label_visibility="collapsed",
    )
    chip = str(st.session_state.get("pg_fihrist_pills") or "A").strip() or "A"
    if chip not in _FIHRIST_NAV_KEYS:
        chip = "A"

    st.markdown(
        f'<h2 class="pg-fihrist-title">İLAÇ A-Z FİHRİST<span class="pg-fihrist-letter">{html.escape(chip)}</span></h2>',
        unsafe_allow_html=True,
    )

    mask = _fihrist_first_letter_mask(df["ilac_adi"], chip)
    sub = df.loc[mask].copy()
    sub = sub.sort_values("ilac_adi", key=lambda s: s.astype(str).str.casefold()).reset_index(drop=True)
    names = sub["ilac_adi"].tolist()
    pick = None
    if names:
        pick = st.selectbox(
            "Listeden seçin",
            options=names,
            index=0,
            key=f"pg_fihrist_sel_{chip}",
        )
    else:
        st.info("Bu grup için kayıt yok; başka bir harf deneyin.")

    st.markdown(
        f'<p class="pg-fihrist-subhead">İLAÇ LİSTESİ [ {html.escape(chip)} ] — '
        f"ilk {min(_FIHRIST_TABLE_MAX, len(sub))} kayıt</p>",
        unsafe_allow_html=True,
    )

    show = sub.head(_FIHRIST_TABLE_MAX)
    # Markdown [metin](url) — unsafe HTML <a href> bazen CDN/sanitizer ile beklenmedik davranabiliyor.
    md_rows = [
        "| İlaç adı |",
        "| :-------- |",
    ]
    for _, row in show.iterrows():
        ad = str(row["ilac_adi"])
        u_ad = _google_search_url(ad)
        lab = _fihrist_md_link_label(ad)
        md_rows.append(f"| [{lab}]({u_ad}) |")
    st.markdown("\n".join(md_rows))
    if len(sub) > _FIHRIST_TABLE_MAX:
        st.caption(
            f"Toplam **{len(sub)}** satır; performans için yalnızca ilk {_FIHRIST_TABLE_MAX} gösteriliyor. "
            "Daraltmak için harf veya listeden arama kullanın."
        )
    if pick:
        st.caption(f"Seçili satır: **{pick}**")

    st.markdown(
        f"**Kaynaklar:** [İlaç A-Z fihrist — Google Sheets]({_FIHRIST_REF_GOOGLE_SHEETS}) · "
        "[ilacrehberi.com — fihrist](https://www.ilacrehberi.com/ilac-fihrist/) · "
        f"[Özellikli ilaç listeleri — Google Sheets]({_OZELLIKLI_REF_GOOGLE_SHEETS})"
    )


def _eczaneapi_key_optional() -> str:
    k = str(os.environ.get("ECZANEAPI_API_KEY") or os.environ.get("eczaneapi_api_key") or "").strip()
    if k:
        return k
    try:
        if hasattr(st, "secrets"):
            return str(
                st.secrets.get("ECZANEAPI_API_KEY")
                or st.secrets.get("eczaneapi_api_key")
                or ""
            ).strip()
    except Exception:
        pass
    return ""


@st.cache_data(ttl=300, show_spinner=False)
def _eczane_on_duty_count(city_slug: str, district_slug: str, api_key: str) -> int | None:
    """Bugünkü nöbetçi sayısı; iframe yüksekliği için. Anahtar yoksa None (istek yapılmaz)."""
    import requests

    if not (api_key or "").strip():
        return None
    params: dict[str, str] = {"city": (city_slug or "").strip().lower()}
    d = (district_slug or "").strip().lower()
    if d:
        params["district"] = d
    try:
        r = requests.get(
            "https://eczaneapi.com/api/v1/pharmacies/on-duty",
            headers={"X-API-Key": api_key.strip()},
            params=params,
            timeout=12,
        )
        if r.status_code != 200:
            return None
        j = r.json()
        if not j.get("success"):
            return None
        data = j.get("data")
        if not isinstance(data, dict):
            return None
        c = data.get("count")
        if isinstance(c, int):
            return max(0, c)
        ph = data.get("pharmacies")
        if isinstance(ph, list):
            return len(ph)
        return None
    except Exception:
        return None


def _pg_today_istanbul_dmy() -> str:
    """TR yerel gösterim için bugünün tarihi (API çağrısı yok)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y")


def _eczane_iframe_height_px(count: int | None, district_selected: bool) -> int:
    """İçerik için hedef yükseklik (px); iframe’de alt bilgi kırpması için dışarıda biraz eklenir."""
    if count == 0:
        return 288
    if count == 1:
        return 324
    if count == 2:
        return 396
    if count == 3:
        return 464
    if isinstance(count, int) and count > 3:
        return min(668, 252 + count * 52)
    if district_selected:
        return 332
    return 432


from typing import Optional

from eczane_widget_geo import load_turkey_geo_rows, pretty_label, slug_tr
from utils import (
    preprocess_image,
    load_image_from_upload,
    generate_pdf_report,
    save_uploaded_pdf,
    list_corpus_pdfs,
    delete_corpus_pdf,
    read_corpus_pdf_bytes,
    ALARM_EMOJI,
    ALARM_MESSAGE,
)


def _vision_for_display(res: dict) -> dict:
    """Ham vision oturum verisini kullanıcıya göstermeden önce eski şablonları süzer."""
    raw = res.get("vision") or {}
    try:
        from agents import vision_dict_for_ui

        return vision_dict_for_ui(raw)
    except Exception:
        out = dict(raw)
        for k in list(out.keys()):
            if isinstance(k, str) and k.strip().casefold() in (
                "notlar",
                "notes",
                "note",
                "kaynak",
                "source",
                "hata",
                "error",
            ):
                out.pop(k, None)
        return out


def _sanitize_gorsel_user_message(msg: Optional[str]) -> str:
    """Eski dağıtım / oturumdan kalan LLaVA–Groq şablon uyarılarını tek tipe çevirir."""
    if not msg:
        return ""
    low = str(msg).lower()
    if any(
        b in low
        for b in (
            "llava",
            "groq fallback",
            "görsel işlenemiyor",
            "gorsel islenemiyor",
            "metin girişi tercih",
            "metin girisi tercih",
        )
    ):
        return (
            "Bu uyarı **eski bir sürüm** çıktısından geliyor olabilir. Güncel akış: "
            "**Groq görüntü (Llama 4)** → **Gemini görüntü yedeği** → **OCR**. "
            "Kenar çubuğundan **Önbelleği Temizle** deyip **Analizi Başlat** ile yenileyin."
        )
    return str(msg)


def _gorsel_analiz_for_display_json(ga: dict) -> dict:
    """JSON panelinde eski oturum mesajlarını kullanıcıya uygun metne çevirir."""
    d = dict(ga)
    if "message" in d:
        d["message"] = _sanitize_gorsel_user_message(str(d.get("message") or ""))
    return d


def _render_fda_drug_detail(real_drug: dict, *, fresh: bool = True) -> None:
    """FDA / Wikidata özetini tablo olarak gösterir (oturumda kalan sonuç için de kullanılır)."""
    if fresh:
        st.success("Veriler bulundu ve Türkçeye çevrildi.")
    else:
        st.markdown("##### Son arşiv sonucu")

    rows = [
        ("İlaç Adı", real_drug.get("ticari_ad", "—")),
        ("Etken Madde", real_drug.get("etken_madde", "—")),
        ("Dozaj", real_drug.get("dozaj", "—")),
        ("Form", real_drug.get("form", "—")),
        ("Üretici", real_drug.get("uretici", "—")),
        ("Barkod", real_drug.get("barkod", "—")),
        ("Kaynak", real_drug.get("kaynak", "—")),
    ]
    md_lines = ["| Alan | Bilgi |", "| :----- | :---- |"]
    for label, raw_val in rows:
        val = str(raw_val if raw_val is not None else "—").strip() or "—"
        if label == "İlaç Adı" and val != "—":
            md_lines.append(
                f"| {_fihrist_md_link_label(label)} | "
                f"[{_fihrist_md_link_label(val)}]({_google_search_url(val)}) |"
            )
        else:
            md_lines.append(
                f"| {_fihrist_md_link_label(label)} | {_fihrist_md_link_label(val)} |"
            )
    st.markdown("\n".join(md_lines))


# ─────────────────────────────────────────────
# SAYFA YAPISI
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="WikiPharma",
    page_icon="static/favicon.png",
    layout="wide",
    initial_sidebar_state="auto",
)

# ─────────────────────────────────────────────
# VIEWPORT DETECTION
# ─────────────────────────────────────────────
st.markdown("""
<script>
function detectViewport() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  const isMobile = width < 640;
  const isTablet = width >= 640 && width < 1024;
  const isDesktop = width >= 1024;

  sessionStorage.setItem('viewport_width', width);
  sessionStorage.setItem('viewport_height', height);
  sessionStorage.setItem('is_mobile', isMobile);
  sessionStorage.setItem('is_tablet', isTablet);
  sessionStorage.setItem('is_desktop', isDesktop);
}

detectViewport();
window.addEventListener('resize', detectViewport);

if (window.parent.streamlit) {
  window.parent.streamlit.setComponentReady();
}
</script>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# GLOBAL CSS — tasarım sistemi + tema desteği
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* ── Design Tokens (Light) ──────────────────── */
:root,
[data-theme="light"],
[data-color-scheme="light"] {
  --pg-canvas:        #f0f4f8;
  --pg-surface:       #ffffff;
  --pg-line:          #e2e8f0;
  --pg-accent:        #0f766e;
  --pg-accent-soft:   rgba(15,118,110,0.10);
  --pg-glow:          rgba(15,118,110,0.18);
  --pg-ink:           #0f172a;
  --pg-muted:         #64748b;
  --pg-sidebar:       #0f172a;
  --pg-sidebar-muted: #94a3b8;
}

/* ── Design Tokens (Dark) ───────────────────── */
[data-theme="dark"],
[data-color-scheme="dark"] {
  --pg-canvas:        #0b0f14;
  --pg-surface:       #111827;
  --pg-line:          #1f2937;
  --pg-accent:        #14b8a6;
  --pg-accent-soft:   rgba(45,212,191,0.15);
  --pg-glow:          rgba(20,184,166,0.25);
  --pg-ink:           #f1f5f9;
  --pg-muted:         #94a3b8;
  --pg-sidebar:       #080c12;
  --pg-sidebar-muted: #64748b;
}

/* EczaneAPI widget iframe — alt “EczaneAPI…” satırı iframe içinde; üstünde opak beyaz maske */
/* Nöbetçi widget: sol sütunda il+ilçe satırı ile aynı genişlik */
.pg-eczane-widget-block {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}
.pg-eczane-widget-block iframe {
  position: relative;
  z-index: 0;
  width: 100% !important;
  max-width: 100% !important;
  margin: 0 !important;
  display: block;
  vertical-align: top;
}
.pg-eczane-footer-mask {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 64px;
  z-index: 4;
  pointer-events: none;
  border-bottom-left-radius: 12px;
  border-bottom-right-radius: 12px;
  /* Widget kartı açık renk; uygulama zemini değil — tam opak beyaza geç */
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0) 0%,
    rgba(255, 255, 255, 0) 14%,
    rgba(255, 255, 255, 0.88) 38%,
    #ffffff 62%,
    #ffffff 100%
  );
}

/* ── Zemin ──────────────────────────────────── */
.stApp {
  background: var(--pg-canvas) !important;
  background-image:
    radial-gradient(ellipse 120% 80% at 100% -20%, rgba(15,118,110,.07), transparent),
    radial-gradient(ellipse 80%  50% at   0% 100%, rgba(234,88,12,.04),  transparent) !important;
}
[data-testid="stHeader"] { background: transparent !important; }
.block-container {
  padding-top: clamp(0.75rem, 2vw, 1.25rem) !important;
  padding-bottom: clamp(2rem, 5vw, 3rem) !important;
  max-width:1400px !important;
}

/* ── Images responsive ───────────────────────── */
.stImage {
  max-width: 100% !important;
  height: auto !important;
}

.stImage img {
  max-width: 100% !important;
  height: auto !important;
  border-radius: 12px !important;
}

/* ── Sidebar — her zaman koyu ────────────────── */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%) !important;
  border-right: 1px solid rgba(255,255,255,.06) !important;
}
[data-testid="stSidebar"] * { color: #cbd5e1 !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] strong,
[data-testid="stSidebar"] b         { color: #f1f5f9 !important; }
[data-testid="stSidebar"] hr        { border-color: rgba(255,255,255,.08) !important; }
[data-testid="stSidebar"] .stExpander {
  background: linear-gradient(135deg, rgba(13,148,136,.08), rgba(15,118,110,.08)) !important;
  border-radius: 12px !important;
  border: 1px solid rgba(13,148,136,.25) !important;
}

/* Main content expander */
.stExpander {
  border-radius: 12px !important;
  border: 1px solid var(--pg-line) !important;
  background: var(--pg-surface) !important;
}

.stExpander > div > div > button {
  font-size: clamp(0.9rem, 2vw, 1rem) !important;
  padding: clamp(0.5rem, 2vw, 0.75rem) !important;
}

.stExpander > div > div > button p {
  font-size: clamp(0.9rem, 2vw, 1rem) !important;
}

/* Sidebar expander header — teal tema */
[data-testid="stSidebar"] .stExpander > button {
  color: #5eead4 !important;
  font-weight: 600 !important;
  font-size: clamp(0.85rem, 2vw, 1rem) !important;
}

/* Radio buttons responsive */
.stRadio > label {
  flex-direction: row !important;
  flex-wrap: wrap !important;
}

.stRadio > label > span:first-child {
  width: 100% !important;
  margin-bottom: 0.5rem !important;
}

@media (max-width: 640px) {
  .stRadio > label > div {
    flex-direction: column !important;
  }

  .stRadio > label > div > label {
    width: 100% !important;
    margin-bottom: 0.5rem !important;
    font-size: 0.9rem !important;
  }
}

[data-testid="stSidebar"] .stExpander > button:hover {
  color: #d1faf4 !important;
  background: rgba(13,148,136,.1) !important;
}

/* Sidebar expander içindeki butonlar — tutarlı tema */
[data-testid="stSidebar"] .stButton > button {
  background: linear-gradient(135deg, rgba(13,148,136,.2), rgba(15,118,110,.2)) !important;
  color: #5eead4 !important;
  border: 1px solid rgba(13,148,136,.4) !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
  transition: all .2s !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: linear-gradient(135deg, rgba(13,148,136,.35), rgba(15,118,110,.35)) !important;
  border-color: rgba(13,148,136,.7) !important;
  color: #d1faf4 !important;
  box-shadow: 0 4px 12px rgba(13,148,136,.15) !important;
}
[data-testid="stSidebar"] .stButton > button:active {
  background: linear-gradient(135deg, rgba(13,148,136,.45), rgba(15,118,110,.45)) !important;
}

/* Sidebar expander içindeki metin input'ları — teal tema */
[data-testid="stSidebar"] .stTextInput input {
  background: rgba(13,148,136,.08) !important;
  color: #e0f2f1 !important;
  border: 1px solid rgba(13,148,136,.3) !important;
  border-radius: 8px !important;
}

[data-testid="stSidebar"] .stTextInput input::placeholder {
  color: #80cbc4 !important;
}

[data-testid="stSidebar"] .stTextInput input:focus {
  background: rgba(13,148,136,.15) !important;
  color: #ffffff !important;
  border-color: #0d9488 !important;
  box-shadow: 0 0 0 2px rgba(13,148,136,.2) !important;
}

[data-testid="stSidebar"] .stTextInput label {
  color: #5eead4 !important;
  font-weight: 500 !important;
}

/* ── Sekmeler — hap/pill stili ───────────────── */
.stTabs [data-baseweb="tab-list"] {
  gap: .3rem !important;
  background: var(--pg-surface) !important;
  padding: .3rem !important;
  border-radius: 14px !important;
  border: 1px solid var(--pg-line) !important;
  box-shadow: 0 1px 4px rgba(0,0,0,.06) !important;
  flex-wrap: wrap !important;
  overflow-x: auto !important;
}
/* aktif olmayan sekme */
button[data-baseweb="tab"] {
  border-radius: 10px !important;
  padding: clamp(0.5rem, 2vw, 1.1rem) clamp(0.4rem, 3vw, 1.1rem) !important;
  font-weight: 600 !important;
  font-size: clamp(0.75rem, 2vw, 0.92rem) !important;
  color: var(--pg-muted) !important;
  background: transparent !important;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  white-space: nowrap !important;
  flex-shrink: 0 !important;
}
/* aktif sekme */
button[data-baseweb="tab"][aria-selected="true"] {
  background: var(--pg-accent) !important;
  color: #ffffff !important;
  border-radius: 10px !important;
}
/* tab alt çizgisini gizle */
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* Responsive tabs */
@media (max-width: 768px) {
  .stTabs [data-baseweb="tab-list"] {
    gap: 0.2rem !important;
    padding: 0.2rem !important;
  }
}
@media (max-width: 640px) {
  button[data-baseweb="tab"] {
    padding: 0.4rem 0.6rem !important;
    font-size: 0.75rem !important;
  }
}

/* ── İç sekmeler ────────────────────────────── */
div[data-testid="stVerticalBlock"] .stTabs [data-baseweb="tab-list"] {
  background: var(--pg-canvas) !important;
}

/* ── Butonlar ───────────────────────────────── */
.stButton > button {
  border-radius: 12px !important; font-weight: 600 !important;
  padding: 0.35rem 1rem !important;
  border: 1px solid transparent !important;
  transition: transform .15s, box-shadow .15s !important;
  font-size: 0.9rem !important;
  height: 38px !important; min-height: 38px !important;
}
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #0f766e, #0d9488) !important;
  color: #ffffff !important;
  box-shadow: 0 4px 14px var(--pg-glow) !important;
}
.stButton > button[kind="primary"]:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 6px 20px rgba(15,118,110,.3) !important;
}
.stButton > button[kind="secondary"] {
  background: linear-gradient(135deg, rgba(13,148,136,.1), rgba(15,118,110,.1)) !important;
  color: #5eead4 !important;
  border: 1px solid rgba(13,148,136,.3) !important;
}
.stButton > button[kind="secondary"]:hover {
  background: linear-gradient(135deg, rgba(13,148,136,.2), rgba(15,118,110,.2)) !important;
  border-color: rgba(13,148,136,.6) !important;
  color: #d1faf4 !important;
}
/* Varsayılan (secondary olmayan) butonlar — belirgin teal renk */
.stButton > button:not([kind="primary"]):not([kind="secondary"]) {
  background: linear-gradient(135deg, #0f766e, #0d9488) !important;
  color: #ffffff !important;
  border: none !important;
  font-weight: 700 !important;
  box-shadow: 0 4px 14px rgba(15,118,110,.3) !important;
}
.stButton > button:not([kind="primary"]):not([kind="secondary"]):hover {
  background: linear-gradient(135deg, #0d7a71, #0fa489) !important;
  border-color: transparent !important;
  color: #ffffff !important;
  box-shadow: 0 6px 20px rgba(15,118,110,.4) !important;
}
.stButton > button:not([kind="primary"]):not([kind="secondary"]):active {
  background: linear-gradient(135deg, #0d7a71, #0fa489) !important;
}
.stButton > button:disabled { opacity: .45 !important; }

/* Button ve Input alignment — responsive */
.stButton > button {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}

/* Responsive buttons for mobile */
@media (max-width: 640px) {
  .stButton > button {
    padding: 0.5rem 0.75rem !important;
    font-size: 0.85rem !important;
    min-height: 2.4rem !important;
  }
}

/* ── Download button ────────────────────────── */
.stDownloadButton > button {
  border-radius: 12px !important; font-weight: 600 !important;
  background: linear-gradient(135deg, #0f766e, #0d9488) !important;
  color: #ffffff !important; border: none !important;
}

/* ── Girişler ───────────────────────────────── */
.stTextInput input {
  border-radius: 12px !important;
  border-color: var(--pg-line) !important;
  background: var(--pg-surface) !important;
  color: var(--pg-ink) !important;
  min-height: clamp(2.4rem, 8vw, 2.75rem) !important;
  padding: clamp(0.5rem, 1.5vw, 0.625rem) clamp(0.75rem, 2vw, 1rem) !important;
  font-size: clamp(0.9rem, 2vw, 1rem) !important;
}
.stTextInput input::placeholder {
  color: var(--pg-sidebar-muted) !important;
}
.stTextInput input:focus {
  border-color: var(--pg-accent) !important;
  box-shadow: 0 0 0 2px rgba(15,118,110,.1) !important;
}
.stTextInput label { color: var(--pg-ink) !important; font-weight: 500 !important; font-size: clamp(0.85rem, 2vw, 1rem) !important; }
.stRadio label { color: var(--pg-ink) !important; font-size: clamp(0.85rem, 2vw, 1rem) !important; }

/* Analiz sol sütun: giriş / uyarı / buton — st.markdown("---") yerine ince çizgi + sıkı dikey boşluk */
hr.pg-hr-slim {
  border: 0;
  border-top: 1px solid var(--pg-line);
  margin: 0.15rem 0 0.3rem;
  opacity: 0.9;
}
.st-key-pg_tight_input_run {
  margin-top: -0.35rem !important;
  margin-bottom: -0.25rem !important;
}
.st-key-pg_tight_input_run [data-testid="stVerticalBlock"] > div[data-testid="element-container"] {
  margin-top: 0.12rem !important;
  margin-bottom: 0.12rem !important;
}
.st-key-pg_tight_input_run [data-testid="stAlert"] {
  margin-top: 0.2rem !important;
  margin-bottom: 0.2rem !important;
  padding-top: 0.55rem !important;
  padding-bottom: 0.55rem !important;
}
.st-key-pg_tight_input_run [data-testid="stButton"] {
  margin-top: 0.15rem !important;
  margin-bottom: 0.35rem !important;
}
/* Analizi Başlat ↔ Nöbetçi eczaneler: belirgin bölüm ayracı */
.pg-input-eczane-break {
  display: block;
  margin: 0.35rem 0 0.55rem 0;
  padding: 0.85rem 0 0.15rem 0;
  border-top: 2px solid rgba(15, 118, 110, 0.32);
  background: linear-gradient(
    180deg,
    rgba(15, 118, 110, 0.07) 0%,
    rgba(15, 118, 110, 0.02) 42%,
    transparent 100%
  );
  border-radius: 14px 14px 0 0;
}
[data-theme="dark"] .pg-input-eczane-break,
[data-color-scheme="dark"] .pg-input-eczane-break {
  border-top-color: rgba(45, 212, 191, 0.38);
  background: linear-gradient(
    180deg,
    rgba(45, 212, 191, 0.1) 0%,
    rgba(45, 212, 191, 0.03) 45%,
    transparent 100%
  );
}
/* Giriş widget’ı ile altındaki sıkı blok arası */
[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child
  [data-testid="element-container"]:has([data-testid="stTextInput"]) {
  margin-bottom: 0.1rem !important;
}
[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child
  [data-testid="element-container"]:has([data-testid="stFileUploader"]) {
  margin-bottom: 0.15rem !important;
}
[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child
  [data-testid="element-container"]:has([data-testid="stImage"]) {
  margin-bottom: 0.12rem !important;
}

/* Responsive inputs for mobile */
@media (max-width: 640px) {
  .stTextInput input {
    min-height: 2.4rem !important;
    padding: 0.5rem 0.75rem !important;
    font-size: 0.9rem !important;
  }
}

.stFileUploader section {
  border-radius: 14px !important;
  border: 2px dashed var(--pg-line) !important;
  background: var(--pg-surface) !important;
  padding: clamp(1rem, 3vw, 1.5rem) !important;
}
/* Dosya yükleme butonu */
.stFileUploader section button {
  background: var(--pg-surface) !important;
  color: var(--pg-accent) !important;
  border: 1px solid var(--pg-accent) !important;
  border-radius: 10px !important;
  font-size: clamp(0.85rem, 2vw, 1rem) !important;
  padding: clamp(0.4rem, 1.5vw, 0.6rem) clamp(0.8rem, 2vw, 1rem) !important;
}
.stAlert {
  border-radius: 12px !important;
  padding: clamp(0.8rem, 3vw, 1rem) !important;
  font-size: clamp(0.85rem, 1.5vw, 1rem) !important;
}
/*
 * Analiz adımları: st.progress kullanılmıyor (Base Web çift katman + boş etiket
 * alanı çift çizgi gibi görünüyordu). Tek parça çubuk: .pg-native-progress
 */
.pg-native-progress {
  width: 100%;
  margin: 0.1rem 0 0.35rem;
}
.pg-native-progress__track {
  width: 100%;
  height: clamp(0.45rem, 1.2vw, 0.55rem);
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.06);
}
.pg-native-progress__fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #0f766e, #14b8a6);
  transition: width 0.35s ease;
  min-width: 0;
}
[data-theme="dark"] .pg-native-progress__track,
[data-color-scheme="dark"] .pg-native-progress__track {
  background: #334155;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.25);
}
[data-testid="stStatus"] {
  border-radius: 14px !important;
  border: 1px solid var(--pg-line) !important;
  background: var(--pg-surface) !important;
  padding: clamp(0.8rem, 3vw, 1rem) !important;
}

/* Responsive columns — yığılma yalnızca ≤768 (1024’te %100 genişlik + satır = taşma) */
@media (max-width: 768px) {
  [data-testid="stHorizontalBlock"] {
    flex-direction: column !important;
    gap: 1rem !important;
  }

  [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    width: 100% !important;
  }
}

@media (max-width: 640px) {
  [data-testid="stHorizontalBlock"] {
    gap: 0.75rem !important;
  }

  .stFileUploader section {
    padding: 0.8rem !important;
  }

  /* Make all column layouts stack on mobile */
  [data-testid="stColumn"] {
    width: 100% !important;
    flex: 1 1 100% !important;
  }
}

/* ── Masthead: st.container(horizontal, key=pg_masthead) → sınıf st-key-pg_masthead (Streamlit ≥1.33) ─ */
[data-testid="stMain"] .st-key-pg_masthead,
.st-key-pg_masthead {
  position: relative;
  overflow: hidden;
  border-radius: 20px;
  margin-bottom: 1.75rem;
  padding: clamp(1.1rem, 4vw, 1.65rem) clamp(1rem, 3vw, 1.5rem) !important;
  background: linear-gradient(135deg, #0f172a 0%, #134e4a 55%, #0f766e 100%) !important;
  box-shadow: 0 20px 50px -12px rgba(15,23,42,.35);
  display: flex !important;
  flex-direction: row !important;
  align-items: center !important;
  gap: 0.75rem 1.25rem !important;
  flex-wrap: wrap !important;
  width: 100%;
  box-sizing: border-box;
}
[data-testid="stMain"] .st-key-pg_masthead::after,
.st-key-pg_masthead::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.04'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  border-radius: 20px;
}
[data-testid="stMain"] .st-key-pg_masthead > div,
.st-key-pg_masthead > div {
  position: relative;
  z-index: 1;
  background: transparent !important;
}
[data-testid="stMain"] .st-key-pg_masthead h1,
[data-testid="stMain"] .st-key-pg_masthead [data-testid="stMarkdownContainer"] h1,
.st-key-pg_masthead h1,
.st-key-pg_masthead [data-testid="stMarkdownContainer"] h1 {
  margin: 0 !important;
  transform: translateY(-8px);
  font-size: clamp(1.35rem, 4vw, 2rem) !important;
  font-weight: 700 !important;
  letter-spacing: -0.03em !important;
  color: #fff !important;
  border: none !important;
  padding: 0 !important;
}
[data-testid="stMain"] .st-key-pg_masthead label p,
[data-testid="stMain"] .st-key-pg_masthead [data-testid="stWidgetLabel"] p,
.st-key-pg_masthead label p,
.st-key-pg_masthead [data-testid="stWidgetLabel"] p {
  color: rgba(248, 250, 252, 0.95) !important;
}
[data-testid="stMain"] .st-key-pg_masthead div[role="radiogroup"],
.st-key-pg_masthead div[role="radiogroup"] {
  flex-wrap: wrap !important;
  justify-content: flex-end !important;
  gap: 0.35rem 0.5rem !important;
}
/* Chip içinde yalnızca metin — daire / native radio görünmez; tıklama label ile */
[data-testid="stMain"] .st-key-pg_masthead .stRadio label input[type="radio"],
.st-key-pg_masthead .stRadio label input[type="radio"] {
  position: absolute !important;
  opacity: 0 !important;
  width: 1px !important;
  height: 1px !important;
  margin: -1px !important;
  padding: 0 !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  clip-path: inset(50%) !important;
  white-space: nowrap !important;
  border: 0 !important;
  pointer-events: none !important;
}
[data-testid="stMain"] .st-key-pg_masthead label[data-baseweb="radio"] > div:first-of-type,
.st-key-pg_masthead label[data-baseweb="radio"] > div:first-of-type {
  display: none !important;
}
[data-testid="stMain"] .st-key-pg_masthead .stRadio label svg,
.st-key-pg_masthead .stRadio label svg {
  display: none !important;
}
[data-testid="stMain"] .st-key-pg_masthead label[data-baseweb="radio"],
.st-key-pg_masthead label[data-baseweb="radio"] {
  margin: 0 !important;
  padding: 0.4rem 1rem !important;
  border-radius: 999px !important;
  border: 1px solid rgba(255, 255, 255, 0.22) !important;
  background: rgba(255, 255, 255, 0.08) !important;
  gap: 0 !important;
  align-items: center !important;
}
[data-testid="stMain"] .st-key-pg_masthead .stRadio [data-testid="stMarkdownContainer"],
.st-key-pg_masthead .stRadio [data-testid="stMarkdownContainer"] {
  margin: 0 !important;
  padding: 0 !important;
}
[data-testid="stMain"] .st-key-pg_masthead label[data-baseweb="radio"]:has(input:checked),
.st-key-pg_masthead label[data-baseweb="radio"]:has(input:checked) {
  background: rgba(255, 255, 255, 0.95) !important;
  border-color: rgba(255, 255, 255, 0.95) !important;
}
[data-testid="stMain"] .st-key-pg_masthead label[data-baseweb="radio"]:has(input:checked) p,
.st-key-pg_masthead label[data-baseweb="radio"]:has(input:checked) p {
  color: #0f766e !important;
  font-weight: 600 !important;
}
@media (max-width: 640px) {
  [data-testid="stMain"] .st-key-pg_masthead,
  .st-key-pg_masthead {
    padding: 1rem 0.85rem !important;
    margin-bottom: 1.25rem;
  }
  [data-testid="stMain"] .st-key-pg_masthead div[role="radiogroup"],
  .st-key-pg_masthead div[role="radiogroup"] {
    justify-content: flex-start !important;
  }
}
[data-testid="stMain"] .st-key-pg_masthead .stRadio label,
.st-key-pg_masthead .stRadio label {
  color: rgba(248, 250, 252, 0.95) !important;
}
[data-testid="stMain"] .st-key-pg_masthead .stRadio label:has(input:checked),
[data-testid="stMain"] .st-key-pg_masthead label:has(input:checked),
.st-key-pg_masthead .stRadio label:has(input:checked),
.st-key-pg_masthead label:has(input:checked) {
  background: rgba(255, 255, 255, 0.95) !important;
  border-radius: 999px !important;
}
[data-testid="stMain"] .st-key-pg_masthead .stRadio label:has(input:checked) p,
[data-testid="stMain"] .st-key-pg_masthead label:has(input:checked) p,
.st-key-pg_masthead .stRadio label:has(input:checked) p,
.st-key-pg_masthead label:has(input:checked) p {
  color: #0f766e !important;
  font-weight: 600 !important;
}
[data-testid="stMain"] .st-key-pg_masthead .stRadio [data-testid="stMarkdownContainer"] p,
.st-key-pg_masthead .stRadio [data-testid="stMarkdownContainer"] p {
  color: rgba(248, 250, 252, 0.95) !important;
}
[data-testid="stMain"] .st-key-pg_masthead .stRadio label:has(input:checked) [data-testid="stMarkdownContainer"] p,
.st-key-pg_masthead .stRadio label:has(input:checked) [data-testid="stMarkdownContainer"] p {
  color: #0f766e !important;
  font-weight: 600 !important;
}

/* ── Bölüm başlıkları ───────────────────────── */
.pg-section {
  font-size: clamp(0.9rem, 2vw, 1rem); font-weight:700; color:var(--pg-ink);
  margin:0 0 1rem; display:flex; align-items:center; gap: clamp(0.3rem, 1vw, 0.5rem);
}
.pg-section-icon {
  width: clamp(1.5rem, 5vw, 2rem); height: clamp(1.5rem, 5vw, 2rem); border-radius:10px;
  background:var(--pg-accent-soft);
  display:inline-flex; align-items:center; justify-content:center; font-size: clamp(0.9rem, 2vw, 1rem);
}

/* İlaç adı canlı öneriler (fiyat arşivi) */
.pg-ac-line {
  font-size: 0.94rem;
  line-height: 1.45;
  padding: 0.28rem 0.15rem 0.28rem 0;
  margin: 0;
  color: var(--pg-ink);
}
.pg-ac-line strong { font-weight: 700; }

/* ── Metrik kartları (eşit kutu, teal tema, referans ‘elevated card’ hissi) ─ */
.metric-card {
  box-sizing: border-box;
  width: 100%;
  min-height: clamp(11.25rem, 32vw, 14.25rem);
  padding: clamp(1rem, 3.2vw, 1.35rem) clamp(0.85rem, 2.8vw, 1.15rem);
  text-align: center;
  border-radius: clamp(16px, 2.4vw, 22px);
  background: linear-gradient(168deg, #ffffff 0%, #f8fafc 48%, #f1f5f9 100%);
  border: 1px solid rgba(15, 118, 110, 0.14);
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.05),
    0 14px 32px -10px rgba(15, 118, 110, 0.14),
    inset 0 1px 0 rgba(255, 255, 255, 0.85);
  position: relative;
  overflow-x: hidden;
  overflow-y: visible;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  gap: clamp(0.3rem, 1.2vw, 0.55rem);
}
.metric-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #0f766e, #14b8a6, #5eead4);
  opacity: 0.92;
  pointer-events: none;
}
.metric-card__value {
  margin: 0.2rem 0 0 0;
  padding: 0 0.15rem;
  font-size: clamp(1.05rem, 3.8vw, 1.55rem) !important;
  font-weight: 700;
  line-height: 1.2;
  color: var(--pg-ink);
  word-break: break-word;
  overflow-wrap: anywhere;
  max-width: 100%;
}
.metric-card__suffix {
  font-size: clamp(0.72rem, 2.4vw, 0.92rem);
  font-weight: 500;
  opacity: 0.82;
}
.metric-card__label {
  margin: 0;
  padding: 0 0.2rem;
  font-size: clamp(0.68rem, 1.9vw, 0.82rem);
  font-weight: 600;
  color: var(--pg-muted);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  line-height: 1.3;
  max-width: 100%;
}
.metric-card__detail {
  margin: 0;
  padding: 0 0.25rem;
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: clamp(0.66rem, 1.75vw, 0.84rem);
  line-height: 1.45;
  color: var(--pg-muted);
  word-break: break-word;
  overflow-wrap: anywhere;
  hyphens: auto;
  max-width: 100%;
  min-height: 0;
}
[data-theme="dark"] .metric-card,
[data-color-scheme="dark"] .metric-card {
  background: linear-gradient(168deg, #1e293b 0%, #151f2e 55%, #0f172a 100%);
  border-color: rgba(45, 212, 191, 0.22);
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.35),
    0 14px 36px -12px rgba(20, 184, 166, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}
@media (max-width: 640px) {
  .metric-card {
    min-height: clamp(10.5rem, 52vw, 13rem);
    padding: 0.95rem 0.75rem;
  }
}

/* Üç metrik satırı: sütunlar aynı yükseklikte, kart sütunu doldurur */
[data-testid="stHorizontalBlock"]:has(.metric-card) {
  align-items: stretch !important;
}
[data-testid="stHorizontalBlock"]:has(.metric-card) > div[data-testid="stColumn"] {
  display: flex !important;
  flex-direction: column !important;
}
[data-testid="stHorizontalBlock"]:has(.metric-card) > div[data-testid="stColumn"] > div {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  width: 100% !important;
  display: flex !important;
  flex-direction: column !important;
}
[data-testid="stHorizontalBlock"]:has(.metric-card) [data-testid="stVerticalBlock"] {
  flex: 1 1 auto !important;
  width: 100% !important;
  display: flex !important;
  flex-direction: column !important;
}
[data-testid="stHorizontalBlock"]:has(.metric-card) .metric-card {
  flex: 1 1 auto;
  height: 100%;
  min-height: clamp(11.25rem, 32vw, 14.25rem);
}

/* ── Alarm bantları ─────────────────────────── */
.alarm-red {
  background:linear-gradient(90deg,#fef2f2,#fff7f7);
  border:1px solid #fecaca; border-left:4px solid #dc2626;
  padding: clamp(0.8rem, 3vw, 1.1rem) clamp(1rem, 3vw, 1.1rem); border-radius:12px;
  font-size: clamp(0.9rem, 1.5vw, 1rem);
}
.alarm-red, .alarm-red b, .alarm-red strong { color:#7f1d1d !important; }

.alarm-yellow {
  background:linear-gradient(90deg,#fffbeb,#fffef5);
  border:1px solid #fde68a; border-left:4px solid #d97706;
  padding: clamp(0.8rem, 3vw, 1.1rem) clamp(1rem, 3vw, 1.1rem); border-radius:12px;
  font-size: clamp(0.9rem, 1.5vw, 1rem);
}
.alarm-yellow, .alarm-yellow b, .alarm-yellow strong { color:#78350f !important; }

.alarm-green {
  background:linear-gradient(90deg,#ecfdf5,#f0fdf9);
  border:1px solid #a7f3d0; border-left:4px solid #059669;
  padding: clamp(0.8rem, 3vw, 1.1rem) clamp(1rem, 3vw, 1.1rem); border-radius:12px;
  font-size: clamp(0.9rem, 1.5vw, 1rem);
}
.alarm-green, .alarm-green b, .alarm-green strong { color:#064e3b !important; }

.alarm-unknown {
  background:var(--pg-surface); border:1px solid var(--pg-line);
  border-left:4px solid #64748b; padding: clamp(0.8rem, 3vw, 1.1rem) clamp(1rem, 3vw, 1.1rem); border-radius:12px;
  font-size: clamp(0.9rem, 1.5vw, 1rem);
}
.alarm-unknown, .alarm-unknown b, .alarm-unknown strong { color:var(--pg-ink) !important; }

/* ── Koyu temada alarm bantları ─────────────── */
[data-theme="dark"] .alarm-red, [data-color-scheme="dark"] .alarm-red {
  background:rgba(127,29,29,.4) !important; border-color:rgba(248,113,113,.5) !important;
  border-left-color:#f87171 !important;
}
[data-theme="dark"] .alarm-red, [data-theme="dark"] .alarm-red b, [data-theme="dark"] .alarm-red strong,
[data-color-scheme="dark"] .alarm-red, [data-color-scheme="dark"] .alarm-red b, [data-color-scheme="dark"] .alarm-red strong { color:#fecaca !important; }
[data-theme="dark"] .alarm-yellow, [data-color-scheme="dark"] .alarm-yellow {
  background:rgba(120,53,15,.4) !important; border-color:rgba(251,191,36,.45) !important;
  border-left-color:#fbbf24 !important;
}
[data-theme="dark"] .alarm-yellow, [data-theme="dark"] .alarm-yellow b, [data-theme="dark"] .alarm-yellow strong,
[data-color-scheme="dark"] .alarm-yellow, [data-color-scheme="dark"] .alarm-yellow b, [data-color-scheme="dark"] .alarm-yellow strong { color:#fef3c7 !important; }
[data-theme="dark"] .alarm-green, [data-color-scheme="dark"] .alarm-green {
  background:rgba(6,78,59,.4) !important; border-color:rgba(52,211,153,.45) !important;
  border-left-color:#34d399 !important;
}
[data-theme="dark"] .alarm-green, [data-theme="dark"] .alarm-green b, [data-theme="dark"] .alarm-green strong,
[data-color-scheme="dark"] .alarm-green, [data-color-scheme="dark"] .alarm-green b, [data-color-scheme="dark"] .alarm-green strong { color:#d1fae5 !important; }

/* ── Boş durum ──────────────────────────────── */
.pg-empty {
  text-align:center; padding: clamp(2rem, 5vw, 3.5rem) clamp(1rem, 3vw, 1.5rem);
  background:var(--pg-surface); border:1.5px dashed var(--pg-line);
  border-radius:16px; color:var(--pg-muted);
}
.pg-empty .pg-empty-icon { font-size: clamp(2rem, 6vw, 2.75rem); line-height:1; margin-bottom:1rem; }
.pg-empty p { margin:0; font-size: clamp(0.9rem, 2vw, 1rem); line-height:1.6; color:var(--pg-muted) !important; }

/* Son aranan ilaçlar — yalnızca gerçek aramalar; nötr kart */
.pg-recent-wrap {
  margin-top: clamp(0.85rem, 2.5vw, 1.25rem);
  margin-bottom: 1rem;
  padding: 0.85rem 0.9rem 0.9rem;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 16px;
  background: linear-gradient(165deg, #ffffff 0%, #f8fafc 48%, #f1f5f9 100%);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
}
.pg-recent-head {
  margin-bottom: 0.45rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}
.pg-recent-title {
  margin: 0;
  font-size: clamp(0.92rem, 1.9vw, 1.02rem);
  font-weight: 700;
  color: var(--pg-ink);
  letter-spacing: -0.01em;
}
.pg-recent-empty {
  margin: 0.35rem 0 0;
  font-size: clamp(0.8rem, 1.5vw, 0.9rem);
  line-height: 1.45;
  color: var(--pg-muted);
}
.pg-recent-list {
  display: flex;
  flex-direction: column;
  gap: 0.38rem;
}
.pg-recent-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 2.05rem;
  padding: 0.38rem 0.55rem 0.38rem 0.45rem;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  font-size: clamp(0.78rem, 1.45vw, 0.88rem);
  line-height: 1.35;
  font-weight: 500;
  color: var(--pg-ink);
  background: rgba(248, 250, 252, 0.9);
  transition: background 0.15s ease, border-color 0.15s ease;
}
.pg-recent-badge {
  flex: 0 0 auto;
  min-width: 1.5rem;
  height: 1.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  font-size: 0.72rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #64748b;
  background: rgba(148, 163, 184, 0.16);
}
.pg-recent-name {
  flex: 1 1 auto;
  min-width: 0;
  word-break: break-word;
  overflow-wrap: anywhere;
}
[data-theme="dark"] .pg-recent-wrap,
[data-color-scheme="dark"] .pg-recent-wrap {
  background: linear-gradient(165deg, #1e293b 0%, #172033 55%, #0f172a 100%);
  border-color: rgba(148, 163, 184, 0.25);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}
[data-theme="dark"] .pg-recent-head,
[data-color-scheme="dark"] .pg-recent-head {
  border-bottom-color: rgba(148, 163, 184, 0.2);
}
[data-theme="dark"] .pg-recent-empty,
[data-color-scheme="dark"] .pg-recent-empty {
  color: #94a3b8;
}
[data-theme="dark"] .pg-recent-row,
[data-color-scheme="dark"] .pg-recent-row {
  color: #e2e8f0;
  background: rgba(15, 23, 42, 0.55);
  border-color: rgba(148, 163, 184, 0.28);
}
[data-theme="dark"] .pg-recent-badge,
[data-color-scheme="dark"] .pg-recent-badge {
  color: #94a3b8;
  background: rgba(51, 65, 85, 0.85);
}

/* Fihrist */
.pg-fihrist-title {
  font-size: clamp(1.05rem, 2.5vw, 1.35rem);
  font-weight: 800;
  letter-spacing: 0.04em;
  color: var(--pg-ink);
  margin: 0 0 0.35rem 0;
}
.pg-fihrist-title span.pg-fihrist-letter {
  color: #1565c0;
  margin-left: 0.25rem;
}
.pg-fihrist-table-wrap {
  margin-top: 0.75rem;
  overflow-x: auto;
  border: 1px solid var(--pg-line);
  border-radius: 12px;
  background: var(--pg-surface);
}
.pg-fihrist-table-wrap table {
  width: 100%;
  border-collapse: collapse;
  font-size: clamp(0.82rem, 1.5vw, 0.92rem);
}
.pg-fihrist-table-wrap th {
  text-align: left;
  padding: 0.55rem 0.65rem;
  border-bottom: 2px solid #1565c0;
  color: #1565c0;
  font-weight: 700;
  white-space: nowrap;
}
.pg-fihrist-table-wrap td {
  padding: 0.45rem 0.65rem;
  border-bottom: 1px solid var(--pg-line);
  vertical-align: middle;
}
.pg-fh-doc {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.1rem;
  height: 1.65rem;
  padding: 0 0.35rem;
  margin-right: 0.25rem;
  border-radius: 4px;
  font-size: 0.68rem;
  font-weight: 700;
  text-decoration: none !important;
  background: linear-gradient(180deg, #1976d2, #0d47a1);
  color: #fff !important;
  border: 1px solid #0d47a1;
}
.pg-fh-doc:hover { filter: brightness(1.08); }
.pg-fihrist-table-wrap a.pg-fh-name {
  color: #1565c0;
  font-weight: 600;
  text-decoration: none;
}
.pg-fihrist-table-wrap a.pg-fh-name:hover { text-decoration: underline; }
.pg-fihrist-subhead {
  margin: 1rem 0 0.4rem 0;
  font-size: clamp(0.95rem, 2vw, 1.05rem);
  font-weight: 700;
  color: #1565c0;
}

/* Responsive empty state */
@media (max-width: 640px) {
  .pg-empty {
    padding: 2rem 1rem;
  }
}

/* ── Status pill (Hakkında / Sistem Durumu — primary buton ile aynı teal ton) */
.pg-status-pill {
  display: inline-flex; align-items: center; gap: 0.4rem;
  font-size: 0.84rem; font-weight: 600; padding: 0.42rem 0.9rem; border-radius: 12px; margin-bottom: 0.35rem;
  color: #ffffff !important;
  border: 1px solid transparent;
}
.pg-status-pill.ok {
  background: linear-gradient(135deg, #0f766e, #0d9488) !important;
  border-color: rgba(13, 148, 136, 0.55) !important;
  box-shadow: 0 4px 14px rgba(15, 118, 110, 0.28) !important;
}
.pg-status-pill.bad {
  background: linear-gradient(135deg, #991b1b, #dc2626) !important;
  border-color: rgba(248, 113, 113, 0.55) !important;
  color: #ffffff !important;
  box-shadow: 0 4px 14px rgba(220, 38, 38, 0.22) !important;
}

/* ── Adım satırı ────────────────────────────── */
.pg-step-line {
  font-size:.9rem; color:var(--pg-muted);
  padding:.25rem 0 .35rem; margin-top:-0.6rem;
}
.pg-step-num { display:inline-block; min-width:2.75rem; font-weight:700; color:var(--pg-accent); }

/* ── Hakkında kartı ─────────────────────────── */
.pg-about-card {
  background:var(--pg-surface); border:1px solid var(--pg-line);
  border-radius:16px; padding: clamp(1.25rem, 4vw, 1.75rem);
  box-shadow:0 2px 12px rgba(0,0,0,.05);
  color:var(--pg-ink);
}
.pg-about-card table { width:100%; border-collapse:collapse; margin-top:.75rem; }
.pg-about-card th, .pg-about-card td {
  border-bottom:1px solid var(--pg-line); padding: clamp(0.4rem, 2vw, 0.65rem); text-align:left; font-size: clamp(0.75rem, 1.5vw, 0.9rem);
  color:var(--pg-ink) !important;
}
.pg-about-card th { color:var(--pg-muted) !important; font-weight:700; font-size: clamp(0.65rem, 1.5vw, 0.75rem); text-transform:uppercase; letter-spacing:.04em; }

/* Responsive tables for mobile */
@media (max-width: 768px) {
  .pg-about-card {
    padding: 1rem;
  }
  .pg-about-card table {
    font-size: 0.75rem;
  }
  .pg-about-card th, .pg-about-card td {
    padding: 0.4rem 0.3rem;
    font-size: 0.75rem;
  }
}

@media (max-width: 640px) {
  .pg-about-card table {
    display: block;
    overflow-x: auto;
    white-space: nowrap;
  }
  .pg-about-card th, .pg-about-card td {
    padding: 0.3rem 0.2rem;
    font-size: 0.7rem;
  }
}

code, .stMarkdown code {
  font-size: clamp(0.75em, 1.5vw, 0.84em);
  background:var(--pg-line) !important;
  color:var(--pg-ink) !important;
  padding: clamp(0.1rem, 0.5vw, 0.15rem) clamp(0.3rem, 1vw, 0.4rem);
  border-radius:6px;
}

/* ── Markdown elements responsive ────────────── */
.stMarkdown h1 { font-size: clamp(1.5rem, 4vw, 2rem) !important; }
.stMarkdown h2 { font-size: clamp(1.3rem, 3.5vw, 1.8rem) !important; }
.stMarkdown h3 { font-size: clamp(1.1rem, 3vw, 1.5rem) !important; }
.stMarkdown h4 { font-size: clamp(1rem, 2.5vw, 1.3rem) !important; }
.stMarkdown h5 { font-size: clamp(0.95rem, 2vw, 1.1rem) !important; }
.stMarkdown p { font-size: clamp(0.9rem, 1.5vw, 1rem) !important; }

/* ── Divider responsive ──────────────────────── */
.stDivider {
  margin: clamp(1rem, 3vw, 1.5rem) 0 !important;
}

/* ── Caption responsive ──────────────────────– */
.stCaption {
  font-size: clamp(0.8rem, 1.5vw, 0.9rem) !important;
}

/* ── Responsive container ────────────────────── */
.block-container {
  padding-left: clamp(0.5rem, 3vw, 1.25rem) !important;
  padding-right: clamp(0.5rem, 3vw, 1.25rem) !important;
}

@media (max-width: 640px) {
  .block-container {
    padding-left: max(0.5rem, env(safe-area-inset-left)) !important;
    padding-right: max(0.5rem, env(safe-area-inset-right)) !important;
    padding-top: max(0.75rem, env(safe-area-inset-top)) !important;
    max-width: 100% !important;
  }
}

/* ── Mobil / taşma: yatay kaydırma, flex min-width ───────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
  max-width: 100vw !important;
  overflow-x: hidden !important;
}
[data-testid="stColumn"],
div[data-testid="element-container"] {
  min-width: 0 !important;
}
[data-testid="stMarkdownContainer"] table {
  display: block;
  width: max-content;
  max-width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
div[data-testid="stDataFrame"],
[data-testid="stDataFrame"] {
  width: 100% !important;
  max-width: 100% !important;
}
[data-testid="stMain"] div[data-testid="stDataFrame"] {
  min-width: 0 !important;
}
[data-testid="stPills"] {
  flex-wrap: wrap !important;
  gap: 0.35rem !important;
  row-gap: 0.45rem !important;
}
@media (max-width: 480px) {
  .st-key-pg_masthead label[data-baseweb="radio"] {
    padding: 0.32rem 0.55rem !important;
    font-size: 0.74rem !important;
  }
  .stTabs [data-baseweb="tab-list"] {
    -webkit-overflow-scrolling: touch;
    scroll-snap-type: x proximity;
  }
}

[data-theme="dark"] .pg-eczane-footer-mask,
[data-color-scheme="dark"] .pg-eczane-footer-mask {
  background: linear-gradient(
    180deg,
    rgba(17, 24, 39, 0) 0%,
    rgba(17, 24, 39, 0) 14%,
    rgba(17, 24, 39, 0.88) 38%,
    #111827 62%,
    #111827 100%
  );
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
gemini_key = os.getenv("GEMINI_API_KEY", "")
groq_key   = os.getenv("GROQ_API_KEY", "")
openai_env = bool(os.getenv("OPENAI_API_KEY", "").strip())


def _session_openai_compat_kwargs():
    """Kenar çubuğundan OpenAI-uyumlu ikinci API; boşsa yalnızca .env OPENAI_* kullanılır."""
    ak = (st.session_state.get("pg_alt_api_key") or "").strip()
    if not ak:
        return None
    out = {"api_key": ak}
    bu = (st.session_state.get("pg_alt_base_url") or "").strip()
    if bu:
        out["base_url"] = bu
    mo = (st.session_state.get("pg_alt_model") or "").strip()
    if mo:
        out["model"] = mo
    return out


def _get_responsive_columns(ratio_desktop: tuple, ratio_tablet: tuple = None, ratio_mobile: tuple = None) -> tuple:
    """
    Dynamically returns column ratios based on viewport width.

    Args:
        ratio_desktop: Column ratio for desktop (e.g., [1, 1.5])
        ratio_tablet: Column ratio for tablet - defaults to [1, 1]
        ratio_mobile: Column ratio for mobile - defaults to [1] (full width)

    Returns:
        Appropriate column ratio based on window width
    """
    # Detect viewport using CSS media queries simulation
    # For now, we'll use a heuristic based on Streamlit's container width
    try:
        # Try to get viewport width from JavaScript (if available)
        # For now, we'll assume desktop layout and let CSS handle responsiveness
        return ratio_desktop
    except:
        return ratio_desktop

# ─────────────────────────────────────────────
# MASTHEAD — yeşil şerit + sekmeler (Streamlit tabs yerine yatay radio)
# ─────────────────────────────────────────────
_PG_TAB_LABELS = (
    "Analiz",
    "FDA Arşivi",
    "Fiyatlar",
    "Firmalar",
    "Özellikli ilaçlar",
    "Fihrist",
    "Prospektüsler",
    "Hakkında",
)
with st.container(
    horizontal=True,
    horizontal_alignment="distribute",
    gap="medium",
    vertical_alignment="center",
    key="pg_masthead",
):
    st.markdown("<h1>WikiPharma</h1>", unsafe_allow_html=True)
    st.radio(
        "Bölüm",
        _PG_TAB_LABELS,
        horizontal=True,
        label_visibility="collapsed",
        key="pg_main_nav",
    )

# Eski sekme etiketleri (oturumda kalmış olabilir)
if str(st.session_state.get("pg_main_nav") or "").strip() == "İlaç firmaları":
    st.session_state.pg_main_nav = "Firmalar"
if str(st.session_state.get("pg_main_nav") or "").strip() == "Prospektüs Yönetimi":
    st.session_state.pg_main_nav = "Prospektüsler"
if str(st.session_state.get("pg_main_nav") or "").strip() == "İlaç Analizi":
    st.session_state.pg_main_nav = "Analiz"
if str(st.session_state.get("pg_main_nav") or "").strip() == "İlaç Fiyatları":
    st.session_state.pg_main_nav = "Fiyatlar"

_pg_nav = str(st.session_state.get("pg_main_nav") or _PG_TAB_LABELS[0]).strip()
if _pg_nav not in _PG_TAB_LABELS:
    _pg_nav = _PG_TAB_LABELS[0]
    st.session_state.pg_main_nav = _pg_nav

# ═════════════════════════════════════════════
# SEKME 1 — ANALİZ
# ═════════════════════════════════════════════
if _pg_nav == "Analiz":
    col_inputs, col_results = st.columns([1, 1.55], gap="large")

    with col_inputs:
        st.markdown(
            '<p class="pg-section">Giriş yöntemi</p>',
            unsafe_allow_html=True,
        )
        method = st.radio(
            "yöntem",
            ["ilaç adı", "görsel", "prospektüs"],
            horizontal=True,
            label_visibility="collapsed",
        )
        image_obj       = None
        drug_name_input = None
        pdf_bytes_input = None
        pdf_name_input  = "prospektus.pdf"

        if method == "görsel":
            up = st.file_uploader(
                "İlaç kutusunun fotoğrafını yükleyin",
                type=["jpg", "jpeg", "png", "webp", "bmp"],
                help="İlaç adı ve dozajın net okunabildiği bir fotoğraf.",
            )
            if up:
                image_obj = load_image_from_upload(up)
                st.image(image_obj, caption="Yüklenen görsel", use_container_width=True)
                image_obj = preprocess_image(image_obj)
                st.info(" Kutunun ön yüzünü tam karşıdan çekin.\n"
                        "İlaç adı ve mg değeri görünür olmalı.")

        elif method == "prospektüs":
            up_pdf = st.file_uploader(
                "İlaç prospektüsünü PDF olarak yükleyin",
                type=["pdf"],
                help="TİTCK / FDA / EMA onaylı prospektüs PDF'i — metin tabanlı olmalı.",
            )
            if up_pdf:
                pdf_bytes_input = up_pdf.read()
                pdf_name_input  = up_pdf.name
                st.success(f" **{up_pdf.name}** yüklendi ({len(pdf_bytes_input)//1024} KB)")
                st.info(
                    " PDF metni önce **Groq** ile yapılandırılır; gerekirse **Gemini** yedeği denenir. "
                    "Etken madde, dozaj ve özet otomatik çıkarılır."
                )

        else:
            # Öneri → düğme: aynı run'da text_input key'ine yazmak StreamlitAPIException verir;
            # seçimi pending'de tutup metin kutusundan *önce* uygula.
            _pending_pick = st.session_state.pop("pg_drug_name_pending", None)
            if _pending_pick is not None:
                _ps = str(_pending_pick).strip()
                if _ps:
                    st.session_state.pg_drug_name_input = _ps
                    st.session_state.pg_ac_pick_nonce = (
                        int(st.session_state.get("pg_ac_pick_nonce", 0)) + 1
                    )

            # Metin kutusu form dışında: her tuşta yeniden çalışır; öneriler anında güncellenir.
            drug_name_input = st.text_input(
                "İlaç adını girin",
                placeholder="örn: Augmentin 1000 mg, Parol 500 mg…",
                key="pg_drug_name_input",
            )
            _q_ac = (drug_name_input or "").strip()
            if len(_q_ac) >= 2:
                try:
                    from referans_ilac_fiyat import search_unique_ilac_adi_candidates

                    _ac_cands = search_unique_ilac_adi_candidates(_q_ac, limit=12)
                except Exception:
                    _ac_cands = []
                    st.caption("Öneriler hesaplanırken hata oluştu.")
                else:
                    if not _ac_cands:
                        st.caption("Bu metinle eşleşen ilaç adı listede bulunamadı.")
                    else:
                        st.session_state.setdefault("pg_ac_pick_nonce", 0)
                        _pick_nonce = int(st.session_state.pg_ac_pick_nonce)
                        with st.container(border=True):
                            for _i, _cand in enumerate(_ac_cands):
                                _ac_l, _ac_r = st.columns([5.2, 0.85], gap="small")
                                with _ac_l:
                                    st.markdown(
                                        f'<div class="pg-ac-line">{_pg_ilac_autocomplete_suggestion_html(_q_ac, _cand)}</div>',
                                        unsafe_allow_html=True,
                                    )
                                with _ac_r:
                                    if st.button(
                                        "→",
                                        key=f"pg_ac_pick_{_pick_nonce}_{_i}",
                                        help="Metin kutusuna bu ilaç adını yaz",
                                        use_container_width=True,
                                    ):
                                        st.session_state.pg_drug_name_pending = _cand
                                        st.rerun()

        with st.container(key="pg_tight_input_run"):
            st.markdown(
                '<hr class="pg-hr-slim" aria-hidden="true"/>',
                unsafe_allow_html=True,
            )
            if not gemini_key:
                st.warning(" GEMINI_API_KEY eksik — Streamlit Secrets'a ekleyin.")
            if not groq_key:
                st.warning(" GROQ_API_KEY eksik — Streamlit Secrets'a ekleyin.")

            if method == "ilaç adı":
                has_input = bool(drug_name_input and drug_name_input.strip())
                can_run = bool(has_input and gemini_key and groq_key)
                run_btn = st.button(
                    " Analizi Başlat",
                    type="primary",
                    disabled=not can_run,
                    use_container_width=True,
                )
            else:
                has_input = (
                    image_obj is not None
                    or (drug_name_input and drug_name_input.strip())
                    or pdf_bytes_input is not None
                )
                can_run = bool(has_input and gemini_key and groq_key)
                run_btn = st.button(
                    " Analizi Başlat",
                    type="primary",
                    disabled=not can_run,
                    use_container_width=True,
                )

        st.markdown(
            '<div class="pg-input-eczane-break" role="separator" '
            'aria-label="Nöbetçi eczaneler bölümü"></div>',
            unsafe_allow_html=True,
        )

        _ecz_today = _pg_today_istanbul_dmy()
        st.markdown(
            '<p class="pg-section" style="margin-bottom:0.35rem">Nöbetçi eczaneler '
            f'<span style="font-weight:500;color:#64748b;font-size:0.92em">· {_ecz_today}</span></p>',
            unsafe_allow_html=True,
        )

        _geo_rows = load_turkey_geo_rows()
        _city_slugs = [r[1] for r in _geo_rows]
        _city_label = {r[1]: r[0] for r in _geo_rows}
        _city_counties = {r[1]: r[2] for r in _geo_rows}
        _ci0 = _city_slugs.index("ankara") if "ankara" in _city_slugs else 0

        _c1, _c2 = st.columns(2)
        with _c1:
            _w_city = st.selectbox(
                "İl seçin",
                options=_city_slugs,
                index=_ci0,
                format_func=lambda s: _city_label.get(s, s),
                key="eczane_widget_city",
            )
        _counties_raw = _city_counties.get(_w_city) or []
        _dist_slugs = [""] + [slug_tr(co) for co in _counties_raw]
        _dist_label: dict[str, str] = {"": "Tüm ilçeler"}
        for _co in _counties_raw:
            _dist_label[slug_tr(_co)] = pretty_label(_co)
        with _c2:
            _w_dist = st.selectbox(
                "İlçe seçin",
                options=_dist_slugs,
                index=0,
                format_func=lambda s: _dist_label.get(s, s),
                key=f"eczane_widget_district__{_w_city}",
            )

        _params: dict[str, str] = {"city": str(_w_city).strip().lower()}
        if str(_w_dist or "").strip():
            _params["district"] = str(_w_dist).strip().lower()
        _widget_src = "https://eczaneapi.com/widget?" + urlencode(_params)

        _dist_sel = bool(str(_w_dist or "").strip())
        _duty_n = _eczane_on_duty_count(
            _w_city, str(_w_dist or ""), _eczaneapi_key_optional()
        )
        _iframe_h = _eczane_iframe_height_px(_duty_n, _dist_sel)
        # iframe üstünde HTML maskesi güvenilir değil; alt bilgi satırını görünür alanın dışına taşı
        _ft = 34 if _duty_n == 1 else 48
        _iframe_vis = max(210, _iframe_h - _ft)

        st.markdown(
            '<div class="pg-eczane-widget-block" style="margin-top:0.5rem;position:relative;'
            'border-radius:12px;overflow:hidden;">'
            f'<iframe src="{html.escape(_widget_src)}" width="100%" height="{_iframe_vis}" '
            'frameborder="0" style="border:none;border-radius:12px;" '
            'title="Nöbetçi Eczaneler"></iframe>'
            '<div class="pg-eczane-footer-mask" aria-hidden="true"></div>'
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")
        if st.button(
            " Önbelleği Temizle",
            type="primary",
            use_container_width=True,
            key="clear_cache_btn",
        ):
            for k in ("orchestrator", "pg_version", "analysis_result", "report_pdf"):
                st.session_state.pop(k, None)
            st.success(" Temizlendi — bir sonraki analizde yeniden başlatılır.")
            st.rerun()

    with col_results:
        st.markdown(
            '<p class="pg-section">Analiz sonuçları</p>',
            unsafe_allow_html=True,
        )

        if run_btn:
            for k in ("analysis_result", "report_pdf"):
                st.session_state.pop(k, None)

            prog_ph = st.empty()
            stat_ph = st.empty()

            def _pg_render_progress_bar(pct: float) -> None:
                p = max(0.0, min(1.0, float(pct)))
                prog_ph.markdown(
                    (
                        '<div class="pg-native-progress" role="progressbar" '
                        'aria-valuemin="0" aria-valuemax="100" '
                        f'aria-valuenow="{int(round(p * 100))}">'
                        '<div class="pg-native-progress__track">'
                        f'<div class="pg-native-progress__fill" style="width:{p * 100:.1f}%"></div>'
                        "</div></div>"
                    ),
                    unsafe_allow_html=True,
                )

            _pg_render_progress_bar(0.0)

            def _prog(step: int, msg: str):
                _pg_render_progress_bar(step / 7.0)
                stat_ph.markdown(
                    f'<div class="pg-step-line">'
                    f'<span class="pg-step-num">Adım {step}/7</span> {msg}</div>',
                    unsafe_allow_html=True,
                )

            try:
                from agents import PharmaGuardOrchestrator, PHARMA_GUARD_VERSION
                # Versiyon değişince eski orchestrator'ı zorla yeniden başlat
                if (
                    "orchestrator" not in st.session_state
                    or st.session_state.get("pg_version") != PHARMA_GUARD_VERSION
                ):
                    with st.spinner("Ajanlar başlatılıyor…"):
                        st.session_state.orchestrator = PharmaGuardOrchestrator()
                        st.session_state.pg_version = PHARMA_GUARD_VERSION

                # Test veri kontrol et
                test_vision = st.session_state.get("test_drug_data")

                result = st.session_state.orchestrator.run(
                    image=image_obj,
                    drug_name_text=drug_name_input,
                    pdf_bytes=pdf_bytes_input,
                    pdf_filename=pdf_name_input,
                    progress_callback=_prog,
                    openai_compat=_session_openai_compat_kwargs(),
                    test_vision_data=test_vision,
                )
                st.session_state.analysis_result = result

                drug_display = result["vision"].get("ticari_ad") or drug_name_input or "İlaç"
                _pg_push_son_aranan_ilac(drug_display)
                st.session_state.report_pdf = generate_pdf_report(
                    report_markdown=result["report"],
                    drug_name=drug_display,
                    alarm_level=result["alarm"],
                    avg_confidence=result["avg_confidence"],
                    vision_data=result["vision"],
                    similar_drugs_bundle=result.get("similar_drugs"),
                    fiyat_liste=result.get("fiyat_liste"),
                )
            except Exception as e:
                stat_ph.error(f"Hata: {e}")
                st.exception(e)

            prog_ph.empty()
            stat_ph.empty()

        if "analysis_result" in st.session_state:
            try:
                from agents import vision_output_has_legacy_user_facing_copy
            except Exception:
                vision_output_has_legacy_user_facing_copy = lambda _v: False
            if vision_output_has_legacy_user_facing_copy(
                st.session_state["analysis_result"].get("vision")
            ):
                st.session_state.pop("analysis_result", None)
                st.session_state.pop("report_pdf", None)
                st.warning(
                    "Önbellekteki sonuç **eski uygulama sürümündendi** ve kaldırıldı. "
                    "**Analizi Başlat** ile yeniden çalıştırın."
                )
                st.rerun()
            res = st.session_state.analysis_result
            alarm = res.get("alarm", "BİLİNMİYOR")
            mark = ALARM_EMOJI.get(alarm, "[?]")
            msg = ALARM_MESSAGE.get(alarm, "")
            css = {"KIRMIZI": "alarm-red", "SARI": "alarm-yellow", "YEŞİL": "alarm-green"}.get(
                alarm, "alarm-unknown"
            )

            st.markdown(f'<div class="{css}"><b>{mark} {alarm}</b> — {msg}</div>',
                        unsafe_allow_html=True)
            st.markdown("")

            m1, m2, m3 = st.columns(3)
            conf = float(res.get("avg_confidence") or 0)
            cc = "#059669" if conf >= 8 else "#d97706" if conf >= 5 else "#dc2626"
            conf_band = "Yüksek" if conf >= 8 else "Orta" if conf >= 5 else "Düşük"
            with m1:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<h3 class="metric-card__value" style="color:{cc}">{conf:.1f}'
                    f'<span class="metric-card__suffix">/10</span></h3>'
                    f'<p class="metric-card__label">Güven Puanı</p>'
                    f'<p class="metric-card__detail">{html.escape(conf_band)} güven bandı.</p>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with m2:
                rag = res.get("rag_results") or []
                rc = len(rag)
                if rag:
                    k0 = str(rag[0].get("kaynak") or "—").strip() or "—"
                    k0_short = html.escape(k0[:36]) + ("…" if len(k0) > 36 else "")
                    detail_inner = k0_short
                else:
                    detail_inner = (
                        "<strong>Kayıtlı prospektüs araması</strong><br>"
                        "Henüz eşleşen parça yok — corpus veya sorgu genişletilebilir."
                    )
                st.markdown(
                    f'<div class="metric-card">'
                    f'<h3 class="metric-card__value">{rc}</h3>'
                    f'<p class="metric-card__label">RAG kayıt sayısı</p>'
                    f'<p class="metric-card__detail">{detail_inner}</p>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with m3:
                fc = res.get("fact_check") or {}
                fc_ok = not fc.get("uyusmazlik", False)
                corpus_bos = fc.get("corpus_bos", False)
                fc_label = "Genel Bilgi" if corpus_bos else "Fact-Check"
                if corpus_bos:
                    main_txt = "Genel mod"
                    fc_col = "#64748b"
                    fc_detail = html.escape(
                        "Yerel prospektüs bulunamadı; görsel/metin ile üretilen özet kaynaklarla "
                        "sınırlı doğrulama."
                    )
                elif not fc_ok:
                    n_issues = len(fc.get("sorunlar") or [])
                    main_txt = "Uyumsuzluk" if n_issues else "Dikkat"
                    fc_col = "#dc2626"
                    fc_detail = (
                        html.escape(f"{n_issues} tutarsızlık tespit edildi.")
                        if n_issues
                        else html.escape(str(fc.get("mesaj") or "Fact-check uyarısı.")[:120])
                    )
                else:
                    main_txt = "Uyumlu"
                    fc_col = "#059669"
                    fc_detail = html.escape(
                        str(fc.get("mesaj") or "Görsel / RAG özetleri birbiriyle çelişmiyor.")[:140]
                    )
                st.markdown(
                    f'<div class="metric-card">'
                    f'<h3 class="metric-card__value" style="color:{fc_col}">{html.escape(main_txt)}</h3>'
                    f'<p class="metric-card__label">{html.escape(fc_label)}</p>'
                    f'<p class="metric-card__detail">{fc_detail}</p>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

            if corpus_bos:
                st.info("Prospektüs veritabanı boş ama Genel İlaç Bilgisi ile doğrulama yapıldı. "
                        "Daha güvenilir sonuçlar için Prospektüsler sekmesinden PDF yükleyin.")
            elif not fc_ok:
                st.error(" **VERİ UYUŞMAZLIĞI**\n\n" +
                         "\n".join(f"- {s}" for s in fc.get("sorunlar", [])))

            _fl = res.get("fiyat_liste") or {}
            if _fl.get("eslesti") and (_fl.get("satirlar") or []):
                import pandas as pd

                st.markdown("#### Liste fiyatı")
                _fdf = pd.DataFrame(_fl["satirlar"])
                _fdf = _dataframe_noneish_to_dash(_fdf)
                _fdf, _fdf_gcfg, _fdf_gorder = _prep_df_google_links_for_streamlit(_fdf)
                _fdf_kw: dict = dict(use_container_width=True, hide_index=True)
                _cfg = {}
                if "Liste fiyatı (₺)" in _fdf.columns:
                    _cfg["Liste fiyatı (₺)"] = st.column_config.NumberColumn(
                        "Liste fiyatı (₺)", format="%.2f"
                    )
                if "GKF (€)" in _fdf.columns:
                    _cfg["GKF (€)"] = st.column_config.NumberColumn("GKF (€)", format="%.4f")
                _cfg.update(_fdf_gcfg)
                if _cfg:
                    _fdf_kw["column_config"] = _cfg
                if _fdf_gorder is not None:
                    _fdf_kw["column_order"] = _fdf_gorder
                st.dataframe(_fdf, **_fdf_kw)

            st.markdown("")

            vsum = _vision_for_display(res)
            bd = vsum.get("barkod_detay")
            if isinstance(bd, dict):
                if bd.get("tespit_edildi"):
                    st.success(
                        f"Barkod bulundu: **{bd.get('deger', '—')}** "
                        f"({bd.get('format', '—')})"
                    )
                    if bd.get("gorsel_celiski"):
                        st.warning(
                            "Görsel model ile barkod okuması uyuşmuyor; kimlik sinyali "
                            "düşük güvenli kabul edin."
                        )
                else:
                    st.caption("Barkod tespit edilemedi — analiz normal şekilde sürdü.")
            qr = vsum.get("qr_kod_detay")
            if isinstance(qr, dict):
                if qr.get("tespit_edildi"):
                    st.success(
                        f"QR kod bulundu ({qr.get('format', '—')}): "
                        f"`{qr.get('deger', '—')[:200]}{'…' if len(str(qr.get('deger') or '')) > 200 else ''}`"
                    )
                else:
                    st.caption("QR kod tespit edilemedi — analiz normal şekilde sürdü.")

            ga = vsum.get("gorsel_analiz")
            if isinstance(ga, dict) and ga.get("message"):
                msg_show = _sanitize_gorsel_user_message(str(ga.get("message") or ""))
                sts = ga.get("image_analysis_status")
                if sts == "failed":
                    if any(
                        x in msg_show
                        for x in (
                            "otomatik güvenilir",
                            "eski bir sürüm",
                            "Önbelleği Temizle",
                        )
                    ):
                        st.info(msg_show)
                    else:
                        st.warning(msg_show)
                elif sts == "ocr_recovered":
                    st.success(msg_show)
                elif sts == "partial_success":
                    st.info(msg_show)
                elif ga.get("success"):
                    st.caption(msg_show)
                ext = ga.get("extracted_text") or ""
                if ext and sts in ("ocr_recovered", "partial_success", "failed"):
                    with st.expander("OCR / çıkarılan metin özeti", expanded=(sts == "failed")):
                        st.text(ext[:4000])
                if ga.get("error_code") and sts != "full_success":
                    st.caption(f"Teknik kod: `{ga['error_code']}`")

            st.markdown("")

            rt1, rt2, rt3, rt4 = st.tabs(
                ["Rapor", " Riskler", " Firma", " Benzer / Muadil"]
            )

            with rt1:
                try:
                    from agents import _strip_confidence_meta_junk
                except Exception:
                    _strip_confidence_meta_junk = lambda x: x
                st.markdown(
                    _strip_confidence_meta_junk(
                        res.get("report", "Rapor oluşturulamadı.")
                    )
                )
                if "report_pdf" in st.session_state:
                    dn = (res["vision"].get("ticari_ad") or drug_name_input or "ilac")
                    st.download_button("PDF Raporu İndir",
                                       data=st.session_state.report_pdf,
                                       file_name=f"pharma_guard_{dn.replace(' ','_')}.pdf",
                                       mime="application/pdf", type="primary",
                                       use_container_width=True)

                # Teknik Detaylar (collapsed by default)
                with st.expander("Teknik Detaylar", expanded=False):
                    v_raw = res.get("vision") or {}
                    v = _vision_for_display(res)
                    try:
                        from agents import vision_output_has_legacy_user_facing_copy

                        if vision_output_has_legacy_user_facing_copy(v_raw):
                            st.caption(
                                "Önceki uygulama sürümünden kalan şablon satırları gizlendi. "
                                "Tam tutarlı sonuç için **Önbelleği Temizle** → **Analizi Başlat**."
                            )
                    except Exception:
                        pass
                    pv = v.get("pharma_guard_scan_version")
                    if pv:
                        st.caption(f"Görsel pipeline sürümü: `{pv}`")
                    ga_tab = v.get("gorsel_analiz")
                    if isinstance(ga_tab, dict) and str(ga_tab.get("message") or "").strip():
                        st.markdown("**Durum özeti**")
                        st.markdown(str(_sanitize_gorsel_user_message(str(ga_tab.get("message") or ""))))
                    n_extra = str(v.get("notlar") or "").strip()
                    k_extra = str(v.get("kaynak") or "").strip()
                    for label, key in [
                        ("Ticari Ad", "ticari_ad"),
                        ("Etken Madde", "etken_madde"),
                        ("Dozaj", "dozaj"),
                        ("Form", "form"),
                        ("Barkod", "barkod"),
                        ("Üretici", "uretici"),
                    ]:
                        val = v.get(key)
                        if val:
                            st.markdown(f"**{label}:** {val}")
                    osk = v.get("okunabilirlik_skoru")
                    if osk: st.markdown(f"**Okunabilirlik:** {osk}/10")
                    # PDF'e özgü alanlar
                    if v.get("endikasyonlar"):
                        st.markdown(f"**Endikasyonlar:** {v['endikasyonlar']}")
                    if v.get("prospektus_ozeti"):
                        st.info(f" **Prospektüs Özeti:** {v['prospektus_ozeti']}")
                    if v.get("pdf_metin_uzunlugu"):
                        st.caption(f"PDF metin uzunluğu: {v['pdf_metin_uzunlugu']:,} karakter")
                    err_v = str(v.get("hata") or "").strip()
                    if err_v:
                        st.warning(_sanitize_gorsel_user_message(err_v))
                    gax = v.get("gorsel_analiz")
                    if isinstance(gax, dict):
                        with st.expander("Görsel analiz teknik özeti (JSON)", expanded=False):
                            st.json(_gorsel_analiz_for_display_json(gax))
                    bdet = v.get("barkod_detay")
                    if isinstance(bdet, dict):
                        with st.expander("Barkod taraması (makine)", expanded=False):
                            st.json(bdet)
                        if v.get("barkod_gorsel_okuma"):
                            st.caption(f"Görsel model barkod okuması: {v['barkod_gorsel_okuma']}")
                    qdet = v.get("qr_kod_detay")
                    if isinstance(qdet, dict):
                        with st.expander("QR kod taraması (makine)", expanded=False):
                            st.json(qdet)
                    st.markdown("---")
                    st.markdown("**RAG eşleşmeleri**")
                    for i, r in enumerate(res.get("rag_results", []), 1):
                        k_src = str(r.get("kaynak") or "").strip() or "Kaynak belirtilmedi"
                        s_src = str(r.get("sayfa") or "").strip() or "—"
                        met_raw = str(r.get("metin") or "").strip() or "(Metin yok)"
                        with st.expander(f"{i}. {k_src} · s.{s_src}"):
                            st.caption(met_raw[:2000])

            with rt2:
                s = res.get("safety", {})
                if "hata" in s:
                    st.error(s["hata"])
                elif s:
                    alv = s.get("alarm_seviyesi","BİLİNMİYOR")
                    st.markdown(f"**Alarm:** {ALARM_EMOJI.get(alv, '[?]')} {alv}")
                    st.markdown(f"**Gerekçe:** {s.get('alarm_gerekce','—')}")
                    st.markdown(f"**Güven:** {s.get('guven_puani','?')}/10")
                    for tur, liste in (s.get("yan_etkiler") or {}).items():
                        if liste:
                            st.markdown(f"**Yan etkiler — {tur}:**")
                            for it in liste: st.markdown(f"  - {it}")
                    for it in (s.get("etkilesimler") or []):
                        st.markdown(f"- {it}")
                    for it in (s.get("kontrendikasyonlar") or []):
                        st.markdown(f"- {it}")
                    for it in (s.get("ozel_uyarilar") or []):
                        st.markdown(f"- {it}")

            with rt3:
                c = res.get("corporate", {})
                if c:
                    if "hata" in c: st.warning(c["hata"])
                    for label, key in [("Firma","firma_adi"),("Ülke","ulke"),
                                       ("TİTCK","titck_durumu")]:
                        val = c.get(key)
                        if val: st.markdown(f"**{label}:** {val}")
                    gp = c.get("guven_puani")
                    if gp: st.markdown(f"**Güven:** {gp}/10")
                    if c.get("sertifikalar"):
                        st.markdown(f"**Sertifikalar:** {', '.join(c['sertifikalar'])}")
                    if c.get("genel_degerlendirme"):
                        st.info(c["genel_degerlendirme"])

            with rt4:
                sim = res.get("similar_drugs") or {}
                st.markdown("### Benzer İlaçlar / Muadil Alternatifler")
                if sim.get("uyari"):
                    st.warning(str(sim["uyari"]))
                if sim.get("fiyat_entegrasyonu_notu"):
                    st.info(str(sim["fiyat_entegrasyonu_notu"]))
                rows = sim.get("oneriler") or []
                if not rows:
                    if sim.get("bos_aciklama"):
                        st.info(str(sim["bos_aciklama"]))
                    else:
                        st.info(
                            "Bu sorgu için otomatik benzer / muadil önerisi üretilemedi. "
                            "Muadil seçimi için eczacı veya hekime danışın."
                        )
                    st.markdown(
                        "**Resmi doğrulama için:** "
                        "[TİTCK](https://titck.gov.tr) · "
                        "[İlaç bilgi kartı / kamuoyu duyuruları](https://titck.gov.tr/mmi_kamuoyu) · "
                        "Reçeteli ürünlerde mutlaka sağlık mesleği mensubu onayı gerekir."
                    )
                for i, row in enumerate(rows, 1):
                    if not isinstance(row, dict):
                        continue
                    _ksrc = str(row.get("kaynak") or "").strip()
                    _hide_src = _ksrc.casefold() in (
                        "",
                        "—",
                        "-",
                        "yerel_katalog",
                        "model_onerisi",
                    )
                    with st.container(border=True):
                        _title = f"**{i}. {row.get('ticari_ad', '—')}**"
                        if _ksrc and not _hide_src:
                            _title += f" (`{html.escape(_ksrc)}`)"
                        st.markdown(_title)
                        st.markdown(
                            f"- **Etken madde:** {row.get('etken_madde', '—')}\n"
                            f"- **Dozaj:** {row.get('dozaj', '—')}\n"
                            f"- **Form:** {row.get('form', '—')}\n"
                            f"- **Benzerlik:** {row.get('benzerlik_aciklamasi', '—')}"
                        )
        else:
            st.markdown("""
            <div class="pg-empty">
              <div class="pg-empty-icon"></div>
              <p>Görsel yükleyin veya ilaç adını yazın;<br>
                 ardından <strong>Analizi Başlat</strong> ile ajanları çalıştırın.</p>
            </div>
            """, unsafe_allow_html=True)

        # Son aranan: boş karşılama metninin altında; sonuç varken veya analiz çalışırken gizli
        if "analysis_result" not in st.session_state and not run_btn:
            _pg_render_son_aranan_ilaclar_panel()


# SEKME 2 — FDA ARŞİVİ (Gerçek İlaç Verisi)
# ═════════════════════════════════════════════
elif _pg_nav == "FDA Arşivi":
    st.markdown(
        '<p class="pg-section">FDA Arşivi — Gerçek İlaç Bilgisi</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Bilgi edinmek istediğiniz ilacı Amerikan Gıda ve İlaç Dairesi arşivinde sorgulayabilirsiniz. "
        "Onayı bulunmayan ilaçlar arşiv sonuçlarında yer bulamayabilir."
    )

    col1, col2 = st.columns([3, 2], gap="small", vertical_alignment="bottom")

    with col1:
        drug_search = st.text_input(
            "İlaç adını girin",
            placeholder="örn: Augmentin, Parol, Aspirin, Dikloron…",
            key="drug_search_input",
        )

    with col2:
        fetch_clicked = st.button(
            " Arşiv'de Ara",
            type="primary",
            use_container_width=True,
            key="fetch_real_data_btn",
        )

    if fetch_clicked:
        if drug_search.strip():
            with st.spinner(f"'{drug_search.strip()}' FDA arşivinde aranıyor…"):
                try:
                    from real_drug_data import fetch_drug_info

                    real_drug = fetch_drug_info(drug_search.strip())
                    if real_drug:
                        st.session_state["test_drug_data"] = real_drug
                        _render_fda_drug_detail(real_drug, fresh=True)
                    else:
                        st.warning(
                            f"'{drug_search.strip()}' için veriler bulunamadı. Başka bir isimle deneyin."
                        )
                        st.info(
                            "**İpucu:** Ticari isim (örn: Augmentin) veya etken madde adı "
                            "(örn: Amoxicillin) yazabilirsiniz."
                        )
                        if st.session_state.get("test_drug_data"):
                            st.markdown("---")
                            _render_fda_drug_detail(st.session_state["test_drug_data"], fresh=False)
                except ImportError:
                    st.error("real_drug_data modülü bulunamadı")
                except Exception as e:
                    st.error(f"Hata: {str(e)}")
        else:
            st.warning("Aramak için önce ilaç adı girin.")
            if st.session_state.get("test_drug_data"):
                st.markdown("---")
                _render_fda_drug_detail(st.session_state["test_drug_data"], fresh=False)
    elif st.session_state.get("test_drug_data"):
        _render_fda_drug_detail(st.session_state["test_drug_data"], fresh=False)
        st.divider()
        st.info("Yeni kayıt için ilaç adını yazıp **Arşiv'de Ara** düğmesine basın.")
    else:
        st.markdown(
            '<div class="pg-empty" style="margin-top:0.5rem">'
            '<p style="margin:0;color:#64748b;font-size:0.95rem">'
            "İlaç adını yazın ve <strong>Arşiv'de Ara</strong> ile OpenFDA / Wikidata üzerinden "
            "kayıt sorgulayın. Sonuçlar Türkçeye uyarlanır."
            "</p></div>",
            unsafe_allow_html=True,
        )

# ═════════════════════════════════════════════
# SEKME 3 — FİYATLAR (birleşik liste)
# ═════════════════════════════════════════════
elif _pg_nav == "Fiyatlar":
    _pg_fragment_ilac_fiyatlari()

# ═════════════════════════════════════════════
# SEKME 3a — FİRMALAR (birleşik fiyat + özellikli listeler)
# ═════════════════════════════════════════════
elif _pg_nav == "Firmalar":
    _pg_fragment_ilac_firmalari()

# ═════════════════════════════════════════════
# SEKME 3b — ÖZELLİKLİ İLAÇ LİSTELERİ (yerel XLSX)
# ═════════════════════════════════════════════
elif _pg_nav == "Özellikli ilaçlar":
    _pg_fragment_ozellikli_ilaclar()

# ═════════════════════════════════════════════
# SEKME 3c — İLAÇ FİHRİST (yerel XLSX)
# ═════════════════════════════════════════════
elif _pg_nav == "Fihrist":
    _pg_fragment_ilac_fihrist()

# ═════════════════════════════════════════════
# SEKME 4 — PROSPEKTÜSLER (CORPUS)
# ═════════════════════════════════════════════
elif _pg_nav == "Prospektüsler":
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### Prospektüs Ekle")
        ups = st.file_uploader("PDF yükle (çoklu seçim)", type=["pdf"],
                               accept_multiple_files=True, key="corpus_uploader")
        if st.button(
            "Kaydet ve İndeksi Güncelle",
            type="primary",
            disabled=not ups,
            use_container_width=True,
        ):
            saved = [save_uploaded_pdf(f) for f in ups]
            st.success(f" {len(saved)} dosya kaydedildi.")
            if "orchestrator" in st.session_state:
                with st.spinner("ChromaDB güncelleniyor…"):
                    st.session_state.orchestrator.rag_agent.rebuild_index()
                st.success(" İndeks güncellendi!")

    with c2:
        st.markdown("#### Mevcut Dosyalar")
        _corpus_notice = st.session_state.pop("_corpus_post_delete_notice", None)
        if _corpus_notice:
            st.warning(_corpus_notice)
        pdfs = list_corpus_pdfs()
        if pdfs:
            for i, p in enumerate(pdfs):
                r1, r2, r3 = st.columns([3, 1, 1], vertical_alignment="center")
                with r1:
                    st.markdown(f"`{p}`")
                with r2:
                    _pdf_bytes = read_corpus_pdf_bytes(p)
                    if _pdf_bytes:
                        st.download_button(
                            "İndir",
                            data=_pdf_bytes,
                            file_name=p,
                            mime="application/pdf",
                            key=f"corpus_pdf_dl_{i}",
                            help="Bu prospektüsü bilgisayarınıza indirin.",
                        )
                    else:
                        st.caption("—")
                with r3:
                    if st.button(
                        "Sil",
                        key=f"corpus_pdf_del_{i}",
                        help="Bu PDF’yi diskten kaldırır (geri alınamaz).",
                    ):
                        if delete_corpus_pdf(p):
                            if "orchestrator" in st.session_state:
                                with st.spinner("İndeks güncelleniyor…"):
                                    st.session_state.orchestrator.rag_agent.rebuild_index()
                            else:
                                st.session_state["_corpus_post_delete_notice"] = (
                                    "Dosya silindi. Chroma indeksini güncellemek için "
                                    "Analiz sekmesinde bir analiz başlatıp burada "
                                    "«İndeksi Yeniden Oluştur» düğmesine basın."
                                )
                            st.rerun()
                        else:
                            st.error("Dosya silinemedi.")
            if st.button(
                " İndeksi Yeniden Oluştur",
                type="primary",
                use_container_width=True,
            ):
                if "orchestrator" in st.session_state:
                    with st.spinner("Yeniden indeksleniyor…"):
                        st.session_state.orchestrator.rag_agent.rebuild_index()
                    st.success(" Tamamlandı!")
                else:
                    st.info("Önce bir analiz başlatın.")
        else:
            st.warning("Henüz prospektüs yüklenmedi.")

    st.markdown("---")
    st.markdown("**Kaynak önerileri:** "
                "[TİTCK](https://titck.gov.tr) · "
                "[FDA DailyMed](https://dailymed.nlm.nih.gov) · "
                "[EMA](https://www.ema.europa.eu)")

# ═════════════════════════════════════════════
# SEKME 5 — HAKKINDA
# ═════════════════════════════════════════════
elif _pg_nav == "Hakkında":
    pdf_list = list_corpus_pdfs()
    try:
        from agents import PHARMA_GUARD_VERSION as _pgv_about
    except Exception:
        _pgv_about = "?"
    st.markdown(f"""
    <div class="pg-about-card">
      <strong style="font-size:1.1rem">WikiPharma</strong>
      <p style="margin:.5rem 0 1rem;color:#64748b">
        Görüntü işleme ve NLP'yi birleştiren otonom Çoklu Ajan Sistemi (MAS). Uygulama sürümü: <strong>v{_pgv_about}</strong><br>
        <span style="font-size:0.9rem">Canlı: <a href="https://medicalsearch.streamlit.app/" target="_blank" rel="noopener noreferrer">medicalsearch.streamlit.app</a>
        · Kaynak: <a href="https://github.com/cemevecen/medic" target="_blank" rel="noopener noreferrer">github.com/cemevecen/medic</a>
        · İlaç A–Z fihrist (referans): <a href="{_FIHRIST_REF_GOOGLE_SHEETS}" target="_blank" rel="noopener noreferrer">Google Sheets</a>
        · Özellikli ilaç listeleri (referans): <a href="{_OZELLIKLI_REF_GOOGLE_SHEETS}" target="_blank" rel="noopener noreferrer">Google Sheets</a></span>
      </p>
      <table>
        <tr><th>#</th><th>Ajan</th><th>Teknoloji</th><th>Görev</th></tr>
        <tr><td>1</td><td>Vision Scanner</td><td>Groq görüntü (Llama&nbsp;4 Scout zinciri) → Gemini görüntü yedeği → Tesseract OCR → Groq metin</td><td>Kutu görseli / PDF metni → yapılandırılmış JSON</td></tr>
        <tr><td>2</td><td>RAG Specialist</td><td>ChromaDB + LangChain + HuggingFace çok dilli embedding</td><td>Yerel prospektüs semantik arama</td></tr>
        <tr><td>3</td><td>Fact-Checker</td><td>Kural tabanlı Python</td><td>Görsel–RAG tutarlılığı</td></tr>
        <tr><td>4</td><td>Safety Auditor</td><td>Groq (Llama&nbsp;3.3 / 3.1 model zinciri, JSON modu)</td><td>Yan etki, etkileşim, alarm seviyesi</td></tr>
        <tr><td>5</td><td>Corporate Analyst</td><td>Groq (aynı metin zinciri)</td><td>Firma / TİTCK özeti (Gemini kullanılmaz)</td></tr>
        <tr><td>6</td><td>Report Synthesizer</td><td>Önce Groq; Groq düşerse Gemini model zinciri</td><td>Türkçe Markdown rapor</td></tr>
      </table>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="pg-about-card" style="margin-top:.75rem">
      <strong style="font-size:1.05rem">3. Teknoloji katmanları (motor odası)</strong>
      <p style="margin:.4rem 0 .75rem;color:#64748b;font-size:0.92rem">
        Eski taslaklardaki <strong>LLaVA</strong> veya yalnızca <strong>Gemini 2.0 orkestra</strong> ifadeleri güncel değildir:
        Groq’ta LLaVA kapatılmıştır; görüntü için Llama&nbsp;4 + yedek Gemini kullanılır. PDF için önce Groq, isteğe bağlı OpenAI-uyumlu API, sonra Gemini.
      </p>
      <table>
        <tr><th>Kategori</th><th>Teknoloji / kütüphane</th><th>Projedeki rolü</th></tr>
        <tr><td>Orkestrasyon</td><td>Python + Streamlit + <code>PharmaGuardOrchestrator</code></td><td>Ajan sırası, paralel güvenlik/firma, oturum ve ilerleme çubuğu</td></tr>
        <tr><td>Görüntü &amp; kutu</td><td>Groq vision (Llama&nbsp;4), Gemini vision, PIL, pyzbar, Tesseract</td><td>Kutu metni / barkod; Groq yetmezse Gemini görüntü</td></tr>
        <tr><td>Hızlı metin &amp; JSON</td><td>Groq Chat Completions; isteğe bağlı OpenAI-uyumlu API</td><td>PDF alan çıkarımı, OCR yapılandırma, güvenlik, firma</td></tr>
        <tr><td>RAG (hafıza)</td><td>ChromaDB, LangChain Community, <code>sentence-transformers</code> MiniLM</td><td>Yerel PDF indeksi ve sorgu</td></tr>
        <tr><td>Rapor çıktısı</td><td>ReportLab (+ Türkçe font arama, <code>utils</code>)</td><td>İndirilebilir PDF</td></tr>
        <tr><td>Yedek dil modelleri</td><td>Google Gemini (model zinciri, <code>gemini_models.py</code>)</td><td>Görüntü/PDF/rapor yedeği; kota sınırlarına dikkat</td></tr>
      </table>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")

    st.markdown("""
    <div class="pg-about-card" style="margin-top:.75rem">
      <strong>Güvenlik Mekanizmaları</strong>
      <table>
        <tr><th>Mekanizma</th><th>Açıklama</th></tr>
        <tr><td>Halüsinasyon Engeli</td><td>Etken madde–prospektüs uyuşmazlığında rapor bloklanır</td></tr>
        <tr><td>VERİ UYUŞMAZLIĞI</td><td>1 mg dozaj farkı bile alarm tetikler</td></tr>
        <tr><td>Güven Puanı</td><td>Her bilgi 1-10 arası; &lt;8 ise uyarı eklenir</td></tr>
        <tr><td>Görüntü Kalite Kontrolü</td><td>Okunabilirlik &lt;5 ise kullanıcı uyarılır</td></tr>
        <tr><td>KIRMIZI / SARI / YEŞİL</td><td>Kritik riskler kırmızı alarm ile işaretlenir</td></tr>
      </table>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")
    st.markdown("### API Ayarları")

    # ─────────────────────────────────────────────
    # ITS (İLAÇ TAKIP SİSTEMİ) API
    # ─────────────────────────────────────────────
    with st.expander("ITS API - İlaç Takip Sistemi", expanded=False):
        st.caption(
            "Sağlık Bakanlığı'nın resmi İlaç Takip Sistemi.\n\n"
            "**Kaynak:** https://its.gov.tr/\n\n"
            "Gerçek ilaç fiyatları, onay durumları ve uyarı listeleri."
        )

        its_key = st.text_input(
            "ITS API Key",
            type="password",
            key="its_api_key",
            placeholder="ITS anahtarı…",
            help="Sağlık Bakanlığı'ndan temin edilir"
        )

        if its_key:
            st.session_state["its_api_key"] = its_key
            st.success("ITS API key kaydedildi")

    with st.expander("İsteğe bağlı: OpenAI-uyumlu API (PDF analiz için yedek)", expanded=False):
        st.caption(
            "PDF prospektüsü analiz sırası: **Groq → OpenAI-uyumlu API → Gemini**\n\n"
            "OpenAI, OpenRouter, Together AI vb. OpenAI-uyumlu API'ler kullanabilirsiniz."
        )
        st.text_input(
            "API anahtarı",
            type="password",
            key="pg_alt_api_key",
            placeholder="sk-… veya OpenRouter anahtarı",
            help="Gerekli değil; boş bırakılırsa Groq ve Gemini kullanılır."
        )
        st.text_input(
            "Base URL (opsiyonel)",
            key="pg_alt_base_url",
            placeholder="https://api.openai.com/v1 (varsayılan) veya https://openrouter.ai/api/v1",
            help="Boş bırakılırsa OpenAI varsayılanı kullanılır."
        )
        st.text_input(
            "Model adı (opsiyonel)",
            key="pg_alt_model",
            placeholder="gpt-4o-mini (varsayılan)",
            help="Boş bırakılırsa gpt-4o-mini kullanılır."
        )

    # ─────────────────────────────────────────────
    # KONTROL PANELİ VE SİSTEM BİLGİSİ
    # ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Sistem Durumu")

    # API Kontrol paneli
    g_cls  = "ok"  if gemini_key else "bad"
    gr_cls = "ok"  if groq_key   else "bad"
    oa_sess = bool((st.session_state.get("pg_alt_api_key") or "").strip())
    oa_cls = "ok" if (openai_env or oa_sess) else "bad"

    st.markdown(
        f'<div class="pg-status-pill {g_cls}">Gemini API — {"aktif" if gemini_key else "eksik"}</div><br>'
        f'<div class="pg-status-pill {gr_cls}">Groq — {"aktif" if groq_key else "eksik"}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown(f" **RAG Prospektüs:** {len(pdf_list)} dosya")
    if pdf_list:
        with st.expander("Yüklü PDF dosyaları"):
            for f in pdf_list:
                st.caption(f" {f}")
    else:
        st.caption("Corpus boş — Prospektüsler sekmesinden PDF ekleyin.")

    st.markdown("---")
    st.markdown("**Ajanlar (Orkestrasyon)**")
    st.caption("Vision Scanner · RAG Specialist · Fact-Checker · Safety Auditor · Corporate Analyst · Report Synthesizer")

    st.markdown("---")
    st.markdown(
        "**Canlı:** [medicalsearch.streamlit.app](https://medicalsearch.streamlit.app/) &nbsp;|&nbsp; "
        "**GitHub:** [cemevecen/medic](https://github.com/cemevecen/medic) &nbsp;|&nbsp; "
        f"**İlaç fihrist (referans):** [Google Sheets]({_FIHRIST_REF_GOOGLE_SHEETS}) &nbsp;|&nbsp; "
        f"**Özellikli listeler (referans):** [Google Sheets]({_OZELLIKLI_REF_GOOGLE_SHEETS}) &nbsp;|&nbsp; "
        "**Lisans:** MIT &nbsp;|&nbsp; **Uygulama sürümü:** v"
        + str(_pgv_about)
    )
    st.caption("Bu araç tıbbi tavsiye niteliği taşımaz. Tanı ve tedavi için hekime başvurun.")
