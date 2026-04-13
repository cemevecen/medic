"""
PHARMA-GUARD AI — Ana Streamlit Arayüzü
app.py: Modern tasarım, çoklu ajan orkestrasyon, PDF rapor.
"""

import os
import json
import html
from pathlib import Path

import streamlit as st
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

from typing import Optional

from utils import (
    preprocess_image,
    load_image_from_upload,
    generate_pdf_report,
    save_uploaded_pdf,
    list_corpus_pdfs,
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
  padding: clamp(0.5rem, 1.5vw, 0.75rem) clamp(1rem, 3vw, 1.25rem) !important;
  border: 1px solid transparent !important;
  transition: transform .15s, box-shadow .15s !important;
  font-size: clamp(0.85rem, 2vw, 1rem) !important;
  min-height: clamp(2.4rem, 8vw, 2.75rem) !important;
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
.stProgress > div > div {
  background: linear-gradient(90deg, #0f766e, #14b8a6) !important;
  border-radius: 999px !important;
  height: clamp(0.4rem, 1vw, 0.5rem) !important;
}
[data-testid="stStatus"] {
  border-radius: 14px !important;
  border: 1px solid var(--pg-line) !important;
  background: var(--pg-surface) !important;
  padding: clamp(0.8rem, 3vw, 1rem) !important;
}

/* Responsive columns for tablet and mobile */
@media (max-width: 1024px) {
  [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    width: 100% !important;
    flex-basis: auto !important;
  }
}

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

/* ── Hero banner ────────────────────────────── */
.pg-hero {
  position: relative; overflow: hidden; border-radius: 20px;
  padding: clamp(1.25rem, 5vw, 2.25rem); margin-bottom: 1.75rem;
  background: linear-gradient(135deg, #0f172a 0%, #134e4a 55%, #0f766e 100%);
  box-shadow: 0 20px 50px -12px rgba(15,23,42,.35);
}
.pg-hero::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.04'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
}
.pg-hero-inner {
  position: relative; z-index: 1;
  display: flex; align-items: center; justify-content: space-between; gap: 1.5rem;
  flex-wrap: wrap;
}
.pg-hero-left { flex: 1; min-width: 200px; }
.pg-hero h1 { margin:0; font-size:clamp(1.4rem, 4vw, 2.1rem); font-weight:700; letter-spacing:-.03em; color:#fff !important; }
.pg-hero p  { margin:.5rem 0 0; font-size: clamp(0.85rem, 2vw, 0.95rem); color:rgba(226,232,240,.85) !important; line-height:1.55; max-width:520px; }
.pg-hero-right {
  display: flex; flex-direction: column; align-items: flex-end; gap: .35rem;
  flex-shrink: 0;
}
.pg-hero-badge {
  font-size: clamp(0.65rem, 1.5vw, 0.7rem); font-weight:700; text-transform:uppercase; letter-spacing:.07em;
  padding:.25rem .65rem; border-radius:999px;
  background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.18);
  color:rgba(226,232,240,.9) !important; white-space:nowrap;
}

/* Responsive hero on mobile */
@media (max-width: 640px) {
  .pg-hero {
    padding: 1.25rem 1rem;
    margin-bottom: 1.25rem;
  }
  .pg-hero-inner {
    flex-direction: column;
    align-items: flex-start;
    gap: 1rem;
  }
  .pg-hero-right {
    align-items: flex-start;
    width: 100%;
  }
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

/* ── Metrik kartları ────────────────────────── */
.metric-card {
  background:var(--pg-surface); border:1px solid var(--pg-line);
  border-radius:14px; padding: clamp(0.8rem, 3vw, 1.1rem); text-align:center;
  box-shadow:0 2px 8px rgba(0,0,0,.04);
}
.metric-card h3 { margin:0; font-size: clamp(1.2rem, 4vw, 1.5rem); font-weight:700; color:var(--pg-ink); }
.metric-card p  { margin:.3rem 0 0; font-size: clamp(0.7rem, 1.5vw, 0.8rem); color:var(--pg-muted); }

/* Responsive metric cards */
@media (max-width: 768px) {
  .metric-card {
    padding: 0.8rem;
  }
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

/* Responsive empty state */
@media (max-width: 640px) {
  .pg-empty {
    padding: 2rem 1rem;
  }
}

/* ── Status pill (sidebar — her zaman açık bg) */
.pg-status-pill {
  display:inline-flex; align-items:center; gap:.4rem;
  font-size:.84rem; padding:.4rem .75rem; border-radius:10px; margin-bottom:.3rem;
  background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.12);
  color:#e2e8f0 !important;
}
.pg-status-pill.ok  { border-color:rgba(45,212,191,.4) !important; background:rgba(45,212,191,.12) !important; }
.pg-status-pill.bad { border-color:rgba(248,113,113,.4) !important; background:rgba(248,113,113,.1) !important; }

/* ── Adım satırı ────────────────────────────── */
.pg-step-line {
  font-size:.9rem; color:var(--pg-muted);
  padding:.25rem 0 .35rem;
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
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
    padding-top: 0.75rem !important;
    max-width: 100% !important;
  }

  /* Sidebar responsiveness */
  [data-testid="stSidebar"] {
    width: 100vw !important;
    position: fixed !important;
    left: -100vw !important;
    transition: left 0.3s ease !important;
    z-index: 999 !important;
    height: 100vh !important;
  }

  [data-testid="stSidebar"].open {
    left: 0 !important;
  }
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
gemini_key = os.getenv("GEMINI_API_KEY", "")
groq_key   = os.getenv("GROQ_API_KEY", "")
openai_env = bool(os.getenv("OPENAI_API_KEY", "").strip())
pdf_list   = list_corpus_pdfs()


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
# HERO BANNER
# ─────────────────────────────────────────────
st.markdown("""
<div class="pg-hero">
  <div class="pg-hero-inner">
    <h1>WikiPharma</h1>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ANA SEKMELER
# ─────────────────────────────────────────────
tab_analyze, tab_fda, tab_nobetci, tab_its, tab_corpus, tab_about = st.tabs(
    ["🔬 İlaç Analizi", "🔍 FDA Arşivi", "🏪 Nöbetçi Eczaneler", "💊 İlaç Fiyatları", "📄 Prospektüs Yönetimi", "ℹ️ Hakkında"]
)

# ═════════════════════════════════════════════
# SEKME 1 — ANALİZ
# ═════════════════════════════════════════════
with tab_analyze:
    col_in, col_out = st.columns([1, 1.5], gap="large")

    with col_in:
        st.markdown(
            '<p class="pg-section"><span class="pg-section-icon">📥</span>Giriş yöntemi</p>',
            unsafe_allow_html=True,
        )
        method = st.radio(
            "yöntem",
            [" İlaç Adı ile", " Görsel ile", " Prospektüs PDF ile"],
            horizontal=True,
            label_visibility="collapsed",
        )
        image_obj       = None
        drug_name_input = None
        pdf_bytes_input = None
        pdf_name_input  = "prospektus.pdf"

        if "Görsel" in method:
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

        elif "PDF" in method:
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
            drug_name_input = st.text_input(
                "İlaç adını girin",
                placeholder="örn: Augmentin 1000 mg, Parol 500 mg…",
            )

        st.markdown("---")
        if not gemini_key: st.warning(" GEMINI_API_KEY eksik — Streamlit Secrets'a ekleyin.")
        if not groq_key:   st.warning(" GROQ_API_KEY eksik — Streamlit Secrets'a ekleyin.")

        has_input = (
            image_obj is not None
            or (drug_name_input and drug_name_input.strip())
            or pdf_bytes_input is not None
        )
        can_run = bool(has_input and gemini_key and groq_key)
        run_btn = st.button(" Analizi Başlat", type="primary",
                            disabled=not can_run, use_container_width=True)

    with col_out:
        st.markdown(
            '<p class="pg-section"><span class="pg-section-icon">📊</span>Analiz sonuçları</p>',
            unsafe_allow_html=True,
        )

        if run_btn:
            for k in ("analysis_result", "report_pdf"):
                st.session_state.pop(k, None)

            prog_ph  = st.empty()
            stat_ph  = st.empty()
            prog_bar = prog_ph.progress(0)

            def _prog(step: int, msg: str):
                prog_bar.progress(step / 7)
                stat_ph.markdown(
                    f'<div class="pg-step-line">'
                    f'<span class="pg-step-num">Adım {step}/7</span>{msg}</div>',
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
                st.session_state.report_pdf = generate_pdf_report(
                    report_markdown=result["report"],
                    drug_name=drug_display,
                    alarm_level=result["alarm"],
                    avg_confidence=result["avg_confidence"],
                    vision_data=result["vision"],
                    similar_drugs_bundle=result.get("similar_drugs"),
                )
            except Exception as e:
                stat_ph.error(f"❌ Hata: {e}")
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
            emoji = ALARM_EMOJI.get(alarm, "⚪")
            msg   = ALARM_MESSAGE.get(alarm, "")
            css   = {"KIRMIZI":"alarm-red","SARI":"alarm-yellow","YEŞİL":"alarm-green"}.get(alarm,"alarm-unknown")

            st.markdown(f'<div class="{css}"><b>{emoji} {alarm}</b> — {msg}</div>',
                        unsafe_allow_html=True)
            st.markdown("")

            m1, m2, m3 = st.columns(3)
            conf = float(res.get("avg_confidence") or 0)
            cc = "#059669" if conf >= 8 else "#d97706" if conf >= 5 else "#dc2626"
            conf_band = "Yüksek" if conf >= 8 else "Orta" if conf >= 5 else "Düşük"
            with m1:
                st.markdown(
                    f'<div class="metric-card"><h3 style="color:{cc}">'
                    f'{conf:.1f}<span style="font-size:.9rem;font-weight:400">/10</span></h3>'
                    f'<p>Güven Puanı</p>'
                    f'<p style="margin:.35rem 0 0;font-size:0.82rem;color:#64748b;line-height:1.35">'
                    f"{html.escape(conf_band)} güven bandı — rapor ve ajan çıktılarının birleşik özeti."
                    f"</p></div>",
                    unsafe_allow_html=True,
                )
            with m2:
                rag = res.get("rag_results") or []
                rc = len(rag)
                if rag:
                    k0 = str(rag[0].get("kaynak") or "—").strip() or "—"
                    k0_short = html.escape(k0[:36]) + ("…" if len(k0) > 36 else "")
                    r2 = "İlk eşleşen kaynak özeti"
                    r3 = k0_short
                else:
                    r2 = "Kayıtlı prospektüs araması"
                    r3 = "Henüz eşleşen parça yok — corpus veya sorgu genişletilebilir."
                st.markdown(
                    f'<div class="metric-card"><h3>{rc}</h3>'
                    f'<p>RAG kayıt sayısı</p>'
                    f'<p style="margin:.35rem 0 0;font-size:0.82rem;color:#64748b;line-height:1.35">'
                    f"<strong>{html.escape(r2)}</strong><br>{r3}</p></div>",
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
                    detail = (
                        "Yerel prospektüs bulunamadı; görsel/metin ile üretilen özet kaynaklarla "
                        "sınırlı doğrulama."
                    )
                elif not fc_ok:
                    n_issues = len(fc.get("sorunlar") or [])
                    main_txt = "Uyumsuzluk" if n_issues else "Dikkat"
                    fc_col = "#dc2626"
                    detail = (
                        f"{n_issues} tutarsızlık tespit edildi."
                        if n_issues
                        else html.escape(str(fc.get("mesaj") or "Fact-check uyarısı.")[:120])
                    )
                else:
                    main_txt = "Uyumlu"
                    fc_col = "#059669"
                    detail = html.escape(
                        str(fc.get("mesaj") or "Görsel / RAG özetleri birbiriyle çelişmiyor.")[:140]
                    )
                st.markdown(
                    f'<div class="metric-card"><h3 style="color:{fc_col};font-size:1.35rem;font-weight:700">'
                    f"{html.escape(main_txt)}</h3>"
                    f'<p style="margin:.15rem 0 0">{html.escape(fc_label)}</p>'
                    f'<p style="margin:.35rem 0 0;font-size:0.82rem;color:#64748b;line-height:1.4">'
                    f"{detail}</p></div>",
                    unsafe_allow_html=True,
                )

            if corpus_bos:
                st.info("Prospektüs veritabanı boş ama Genel İlaç Bilgisi ile doğrulama yapıldı. "
                        "Daha güvenilir sonuçlar için Prospektüs sekmesinden PDF yükleyin.")
            elif not fc_ok:
                st.error(" **VERİ UYUŞMAZLIĞI**\n\n" +
                         "\n".join(f"- {s}" for s in fc.get("sorunlar", [])))
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
                ["📋 Rapor", " Riskler", " Firma", " Benzer / Muadil"]
            )

            with rt1:
                st.markdown(res.get("report", "Rapor oluşturulamadı."))
                if "report_pdf" in st.session_state:
                    dn = (res["vision"].get("ticari_ad") or drug_name_input or "ilac")
                    st.download_button("📥 PDF Raporu İndir",
                                       data=st.session_state.report_pdf,
                                       file_name=f"pharma_guard_{dn.replace(' ','_')}.pdf",
                                       mime="application/pdf", type="primary",
                                       use_container_width=True)

                # Teknik Detaylar (collapsed by default)
                with st.expander("🔧 Teknik Detaylar", expanded=False):
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
                    st.markdown(f"**Alarm:** {ALARM_EMOJI.get(alv,'⚪')} {alv}")
                    st.markdown(f"**Gerekçe:** {s.get('alarm_gerekce','—')}")
                    st.markdown(f"**Güven:** {s.get('guven_puani','?')}/10")
                    for tur, liste in (s.get("yan_etkiler") or {}).items():
                        if liste:
                            st.markdown(f"**Yan etkiler — {tur}:**")
                            for it in liste: st.markdown(f"  - {it}")
                    for it in (s.get("etkilesimler") or []):   st.markdown(f"⚡ {it}")
                    for it in (s.get("kontrendikasyonlar") or []): st.markdown(f" {it}")
                    for it in (s.get("ozel_uyarilar") or []):  st.markdown(f" {it}")

            with rt4:
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

            with rt5:
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
                    st.markdown(
                        f"**{i}. {row.get('ticari_ad', '—')}** "
                        f"(`{row.get('kaynak', '—')}`)"
                    )
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

    # Kontrol paneli — Önbellek temizleme
    st.markdown("---")
    if st.button(" Önbelleği Temizle", use_container_width=True, key="clear_cache_btn"):
        for k in ("orchestrator", "pg_version", "analysis_result", "report_pdf"):
            st.session_state.pop(k, None)
        st.success(" Temizlendi — bir sonraki analizde yeniden başlatılır.")
        st.rerun()

# ═════════════════════════════════════════════
# SEKME 3 — NÖBETÇİ ECZANELER
# ═════════════════════════════════════════════
with tab_nobetci:
    st.markdown(
        '<p class="pg-section"><span class="pg-section-icon">🏪</span>Nöbetçi Eczaneler</p>',
        unsafe_allow_html=True,
    )
    st.caption("Türkiye'nin herhangi bir yerindeki nöbetçi (açık) eczaneleri bulun.")

    col_city, col_district, col_btn = st.columns([2, 2, 1], gap="small")

    with col_city:
        from nobetci_eczane import get_cities_list

        cities_list = get_cities_list()
        selected_city_nobetci = st.selectbox(
            "İl Seçin",
            options=cities_list,
            index=0,
            key="nobetci_city_select"
        )

    with col_district:
        selected_district_nobetci = st.text_input(
            "İlçe (İsteğe Bağlı)",
            placeholder="örn: Çankaya, Maslak…",
            key="nobetci_district_input"
        )

    with col_btn:
        search_nobetci_btn = st.button("🔍 Ara", use_container_width=True, key="nobetci_search_btn")

    # Arama yap
    if search_nobetci_btn and selected_city_nobetci:
        with st.spinner(f"'{selected_city_nobetci}' ilinde nöbetçi eczaneler aranıyor…"):
            try:
                from nobetci_eczane import get_nobetci_eczaneler, format_pharmacy_result, init_nobetci_api

                # Session state'ten API key'i al (varsa)
                api_key = st.session_state.get("collectapi_api_key")
                if api_key:
                    init_nobetci_api(api_key=api_key, source="collectapi")

                result = get_nobetci_eczaneler(
                    il=selected_city_nobetci.strip(),
                    ilce=selected_district_nobetci.strip() if selected_district_nobetci else None
                )

                if result.get("success"):
                    st.success(f"✓ {result['total']} nöbetçi eczane bulundu!")

                    if result.get("data"):
                        st.markdown("---")
                        st.markdown("### 🏪 Nöbetçi Eczaneler Listesi")

                        for idx, pharmacy in enumerate(result["data"][:20], 1):
                            col_num, col_info = st.columns([0.5, 11])

                            with col_num:
                                st.caption(f"**{idx}**")

                            with col_info:
                                st.markdown(format_pharmacy_result(pharmacy))

                        st.divider()
                    else:
                        st.warning("Eczane verisi alınamadı.")

                else:
                    st.warning(f"⚠️ {result.get('error', 'Veri bulunamadı')}")
                    st.info("💡 **İpucu:** İl adını tam yazın (örn: Ankara, İstanbul, Adana)")

            except ImportError as e:
                st.error(f"❌ nobetci_eczane modülü bulunamadı: {str(e)}")
            except Exception as e:
                st.error(f"❌ Hata: {str(e)}")
    elif search_nobetci_btn:
        st.info("Lütfen bir il adı girin")

# ═════════════════════════════════════════════
# SEKME 4 — İTS (İLAÇ FİYATLARI VE BİLGİLERİ)
# ═════════════════════════════════════════════
with tab_its:
    st.markdown(
        '<p class="pg-section"><span class="pg-section-icon">💊</span>İlaç Bilgileri & Fiyatları</p>',
        unsafe_allow_html=True,
    )
    st.caption("Sağlık Bakanlığı İlaç Takip Sistemi (ITS) üzerinden ilaç fiyatları, onay durumları ve güvenlik uyarılarını görüntüleyin.")

    col_search_its, col_btn_its = st.columns([4, 1], gap="small")

    with col_search_its:
        drug_search_its = st.text_input(
            "İlaç adı veya etken madde yazın",
            placeholder="örn: Aspirin, Parasetamol, Amoksisilin…",
            key="its_search_input"
        )

    with col_btn_its:
        search_its_btn = st.button("🔍 Ara", use_container_width=True, key="its_search_btn")

    # Arama yap
    if search_its_btn and drug_search_its:
        with st.spinner(f"'{drug_search_its}' için ilaç bilgileri aranıyor…"):
            try:
                from its_api import get_demo_medicines, init_its_api

                # Session state'ten API key'i al (varsa)
                its_api_key = st.session_state.get("its_api_key")
                if its_api_key:
                    init_its_api(api_key=its_api_key)
                    # Gelecekte gerçek API'ye geçecek

                # Şu anda demo verisi kullanıyoruz (API key yapılandırıldığında canlı API'ye geçer)
                result = get_demo_medicines(drug_search_its)

                if result.get("success"):
                    st.success(f"✓ {result['total']} ilaç bulundu!")

                    if result.get("data"):
                        st.markdown("---")
                        st.markdown("### 💊 Ilaç Bilgileri")

                        for idx, medicine in enumerate(result["data"], 1):
                            with st.expander(f"**{idx}. {medicine['trade_name']}** — {medicine.get('manufacturer', 'Bilinmeyen')}"):
                                col_left, col_right = st.columns([1, 1])

                                with col_left:
                                    st.markdown("**Temel Bilgiler**")
                                    st.markdown(f"**Etken Madde:** {medicine['active_ingredient']}")
                                    st.markdown(f"**Doz:** {medicine['dosage']}")
                                    st.markdown(f"**Form:** {medicine['form']}")
                                    st.markdown(f"**Üretici:** {medicine.get('manufacturer', '—')}")

                                with col_right:
                                    st.markdown("**Fiyat & Onay**")
                                    st.markdown(f"**Fiyat:** ₺{medicine.get('price_tl', '—')}")

                                    status = medicine.get('approval_status', 'Unknown')
                                    if status == 'Approved':
                                        st.markdown(f"**Durum:** ✅ Onaylı")
                                    elif status == 'Warning':
                                        st.markdown(f"**Durum:** ⚠️ Uyarılı")
                                    elif status == 'Recalled':
                                        st.markdown(f"**Durum:** 🚫 Geri Çekildi")
                                    else:
                                        st.markdown(f"**Durum:** {status}")

                                if medicine.get('usage'):
                                    st.markdown(f"**Kullanım:** {medicine['usage']}")

                                if medicine.get('approval_date'):
                                    st.markdown(f"**Onay Tarihi:** {medicine['approval_date']}")

                        st.divider()
                        st.info(f"📊 **Veri Kaynağı:** {result.get('source', 'Bilinmeyen')}")
                        if "DEMO" in result.get('source', ''):
                            st.warning("⚠️ **Not:** Şu anda demo verisi kullanılıyor. Gerçek ITS API entegrasyonu için Sağlık Bakanlığı API key gereklidir.")

                    else:
                        st.warning("İlaç verisi alınamadı.")

                else:
                    st.info(f"❌ '{drug_search_its}' için sonuç bulunamadı.")
                    st.info("💡 **İpucu:** Ticari adı tam yazın (örn: Aspirin, Parol) veya etken madde adı kullanın (örn: Parasetamol)")

            except ImportError as e:
                st.error(f"❌ its_api modülü bulunamadı: {str(e)}")
            except Exception as e:
                st.error(f"❌ Hata: {str(e)}")

    elif search_its_btn:
        st.info("Lütfen bir ilaç adı girin")

    st.markdown("---")
    st.markdown("""
    <div class="pg-about-card">
      <strong>ℹ️ İTS (İlaç Takip Sistemi) Hakkında</strong><br><br>
      Sağlık Bakanlığı'nın resmi sistemidir. Türkiye'ye giren her ilaçı üretimden hasta eline kadar takip eder.
      <br><br>
      <strong>Şu anda gösterilen veriler örnek/demo amaçlıdır.</strong> Gerçek sistem integrasyon için ITS API key gereklidir.
      <br><br>
      <em>Kaynak: <a href="https://its.gov.tr/" target="_blank">its.gov.tr</a></em>
    </div>
    """, unsafe_allow_html=True)

# ═════════════════════════════════════════════
# SEKME 5 — PROSPEKTÜS YÖNETİMİ (CORPUS)
# ═════════════════════════════════════════════
with tab_corpus:
    st.markdown("""
    <div class="pg-about-card" style="margin-bottom:1.25rem">
      <strong> RAG Prospektüs Veritabanı</strong><br><br>
      RAG sisteminin doğru çalışması için TİTCK / FDA onaylı ilaç prospektüslerini (PDF)
      buraya yükleyin. Sistem ilk çalıştırmada ChromaDB indeksini otomatik oluşturur.
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("#### Prospektüs Ekle")
        ups = st.file_uploader("PDF yükle (çoklu seçim)", type=["pdf"],
                               accept_multiple_files=True, key="corpus_uploader")
        if st.button("📂 Kaydet ve İndeksi Güncelle", disabled=not ups):
            saved = [save_uploaded_pdf(f) for f in ups]
            st.success(f" {len(saved)} dosya kaydedildi.")
            if "orchestrator" in st.session_state:
                with st.spinner("ChromaDB güncelleniyor…"):
                    st.session_state.orchestrator.rag_agent.rebuild_index()
                st.success(" İndeks güncellendi!")

    with c2:
        st.markdown("#### Mevcut Dosyalar")
        pdfs = list_corpus_pdfs()
        if pdfs:
            for p in pdfs: st.markdown(f" `{p}`")
            if st.button(" İndeksi Yeniden Oluştur"):
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
# SEKME 2 — FDA ARŞİVİ (Gerçek İlaç Verisi)
# ═════════════════════════════════════════════
with tab_fda:
    st.markdown(
        '<p class="pg-section"><span class="pg-section-icon">🔍</span>FDA Arşivi — Gerçek İlaç Bilgisi</p>',
        unsafe_allow_html=True,
    )
    st.caption("Wikidata ve OpenFDA veritabanlarından gerçek ilaç bilgilerini çeker. Tüm veriler Türkçeye çevrilir.")

    col1, col2 = st.columns([3, 1], gap="small")

    with col1:
        drug_search = st.text_input(
            "İlaç adını girin",
            placeholder="örn: Augmentin, Parol, Aspirin, Dikloron…",
            key="drug_search_input",
            help="Ticari ad veya etken madde adını yazın"
        )

    with col2:
        fetch_clicked = st.button(" Arşiv'de Ara", use_container_width=True, key="fetch_real_data_btn")

    if fetch_clicked or drug_search:
        if drug_search.strip():
            with st.spinner(f"'{drug_search}' FDA arşivinde aranıyor…"):
                try:
                    from real_drug_data import fetch_drug_info
                    real_drug = fetch_drug_info(drug_search)
                    if real_drug:
                        st.session_state["test_drug_data"] = real_drug
                        st.success(f"✓ Veriler bulundu ve Türkçeye çevrildi!")

                        # Verilen bilgileri güzel tablo şeklinde göster
                        col_label, col_value = st.columns([1, 2])

                        with col_label:
                            st.markdown("**Alan**")
                        with col_value:
                            st.markdown("**Bilgi**")

                        st.divider()

                        drug_display = {
                            "İlaç Adı": real_drug.get("ticari_ad", "—"),
                            "Etken Madde": real_drug.get("etken_madde", "—"),
                            "Dozaj": real_drug.get("dozaj", "—"),
                            "Form": real_drug.get("form", "—"),
                            "Üretici": real_drug.get("uretici", "—"),
                            "Barkod": real_drug.get("barkod", "—"),
                            "Kaynak": real_drug.get("kaynak", "—"),
                        }

                        for key, value in drug_display.items():
                            col_k, col_v = st.columns([1, 2])
                            with col_k:
                                st.markdown(f"**{key}**")
                            with col_v:
                                st.caption(value)
                    else:
                        st.warning(f"⚠️ '{drug_search}' için veriler bulunamadı. Başka bir isimle deneyin.")
                        st.info("**İpucu:** Ticari isim (örn: Augmentin) veya etken madde adı (örn: Amoxicillin) yazabilirsiniz.")
                except ImportError:
                    st.error("❌ real_drug_data modülü bulunamadı")
                except Exception as e:
                    st.error(f"❌ Hata: {str(e)}")
        else:
            st.info("Araştırma yapmak için ilaç adını girin")

# ═════════════════════════════════════════════
# SEKME 5 — HAKKINDA
# ═════════════════════════════════════════════
with tab_about:
    try:
        from agents import PHARMA_GUARD_VERSION as _pgv_about
    except Exception:
        _pgv_about = "?"
    st.markdown(f"""
    <div class="pg-about-card">
      <strong style="font-size:1.1rem">WikiPharma</strong>
      <p style="margin:.5rem 0 1rem;color:#64748b">
        Görüntü işleme ve NLP'yi birleştiren otonom Çoklu Ajan Sistemi (MAS). Uygulama sürümü: <strong>v{_pgv_about}</strong>
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
      <strong>🔒 Güvenlik Mekanizmaları</strong>
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
    st.markdown("### ⚙️ API Ayarları")

    # ─────────────────────────────────────────────
    # NÖBETÇİ ECZANE API
    # ─────────────────────────────────────────────
    st.subheader("🏪 Nöbetçi Eczane API (CollectAPI)")

    collectapi_key_raw = st.text_input(
        "API Key",
        type="password",
        key="collectapi_key_raw",
        placeholder="Sadece kod kısmını yapıştır (örn: abc123xyz...)"
    )

    if collectapi_key_raw:
        # "api key xxxx" formatından sadece kodu çıkar ve session_state'e kaydet
        key_clean = collectapi_key_raw.strip()
        if key_clean.lower().startswith("api key"):
            key_clean = key_clean[7:].strip()

        st.session_state["collectapi_api_key"] = key_clean

        # API test et
        from nobetci_eczane import init_nobetci_api
        init_nobetci_api(api_key=key_clean, source="collectapi")

        # Ankara test
        from nobetci_eczane import get_nobetci_eczaneler
        test_result = get_nobetci_eczaneler("Ankara")

        # Gerçek API verisini kontrol et (demo değil)
        if test_result.get("source") == "CollectAPI":
            st.success(f"✓ API çalışıyor! {test_result.get('total')} eczane bulundu (Kaynak: CollectAPI)")
        else:
            error_msg = test_result.get("error", "Bilinmeyen hata")
            st.error(f"❌ API hatası: {error_msg}")

    # ─────────────────────────────────────────────
    # ITS (İLAÇ TAKIP SİSTEMİ) API
    # ─────────────────────────────────────────────
    with st.expander("💊 ITS API - İlaç Takip Sistemi", expanded=False):
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
            st.success("✓ ITS API key kaydedildi")

    with st.expander("⚙️ İsteğe bağlı: OpenAI-uyumlu API (PDF analiz için yedek)", expanded=False):
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
        f'<div class="pg-status-pill {g_cls}">{"●" if gemini_key else "○"} Gemini API — {"aktif" if gemini_key else "eksik"}</div><br>'
        f'<div class="pg-status-pill {gr_cls}">{"●" if groq_key else "○"} Groq — {"aktif" if groq_key else "eksik"}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown(f" **RAG Prospektüs:** {len(pdf_list)} dosya")
    if pdf_list:
        with st.expander("Yüklü PDF dosyaları"):
            for f in pdf_list:
                st.caption(f" {f}")
    else:
        st.caption("Corpus boş — Prospektüs Yönetimi sekmesinden PDF ekleyin.")

    st.markdown("---")
    st.markdown("**Ajanlar (Orkestrasyon)**")
    st.caption("Vision Scanner · RAG Specialist · Fact-Checker · Safety Auditor · Corporate Analyst · Report Synthesizer")

    st.markdown("---")
    st.markdown(
        "**GitHub:** [cemevecen/medic](https://github.com/cemevecen/medic) &nbsp;|&nbsp; "
        "**Lisans:** MIT &nbsp;|&nbsp; **Uygulama sürümü:** v"
        + str(_pgv_about)
    )
    st.caption("⚕ Bu araç tıbbi tavsiye niteliği taşımaz. Tanı ve tedavi için hekime başvurun.")
