"""
PHARMA-GUARD AI — Ana Streamlit Arayüzü
app.py: Kullanıcı paneli, dosya yükleme ve rapor görüntüleme.
"""

import os
import json
import time
from io import BytesIO
from pathlib import Path

import streamlit as st
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# Yerel modüller
from utils import (
    preprocess_image,
    load_image_from_upload,
    generate_pdf_report,
    save_uploaded_pdf,
    list_corpus_pdfs,
    ALARM_EMOJI,
    ALARM_MESSAGE,
)


def pg_section(title: str, icon: str) -> None:
    """Bölüm başlığı (özel CSS ile)."""
    st.markdown(
        f'<p class="pg-section"><span class="pg-section-icon">{icon}</span>{title}</p>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# SAYFA YAPILANDIRMASI
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Pharma-Guard AI",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# TASARIM — tipografi + Streamlit bileşenleri + kartlar
# ---------------------------------------------------------------------------

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
    :root {
      --pg-ink: #0c1222;
      --pg-muted: #5c6578;
      --pg-line: #e2e6ef;
      --pg-surface: #ffffff;
      --pg-canvas: #f0f2f7;
      --pg-accent: #0f766e;
      --pg-accent-soft: #ccfbf1;
      --pg-warm: #ea580c;
      --pg-sidebar: #0f172a;
      --pg-sidebar-muted: #94a3b8;
      --pg-glow: rgba(15, 118, 110, 0.12);
    }

    html, body, .stApp, [data-testid="stAppViewContainer"] {
      font-family: "Instrument Sans", system-ui, sans-serif !important;
      color: var(--pg-ink);
    }

    .stApp {
      background: var(--pg-canvas) !important;
      background-image:
        radial-gradient(ellipse 120% 80% at 100% -20%, rgba(15, 118, 110, 0.08), transparent),
        radial-gradient(ellipse 80% 50% at 0% 100%, rgba(234, 88, 12, 0.05), transparent) !important;
    }

    [data-testid="stHeader"] {
      background: transparent !important;
    }

    .block-container {
      padding-top: 1.25rem !important;
      padding-bottom: 3rem !important;
      max-width: 1400px !important;
    }

    /* Sekmeler — hap şeklinde */
    .stTabs [data-baseweb="tab-list"] {
      gap: 0.35rem;
      background: var(--pg-surface);
      padding: 0.35rem;
      border-radius: 14px;
      border: 1px solid var(--pg-line);
      box-shadow: 0 1px 3px rgba(12, 18, 34, 0.06);
    }
    .stTabs [data-baseweb="tab"] {
      border-radius: 10px !important;
      padding: 0.65rem 1.1rem !important;
      font-weight: 600 !important;
      font-size: 0.95rem !important;
    }
    .stTabs [aria-selected="true"] {
      background: var(--pg-accent) !important;
      color: #fff !important;
    }

    /* İç sekmeler */
    div[data-testid="stVerticalBlock"] > div > .stTabs [data-baseweb="tab-list"] {
      background: #f8fafc;
    }

    /* Butonlar */
    .stButton > button {
      border-radius: 12px !important;
      font-weight: 600 !important;
      padding: 0.55rem 1.25rem !important;
      border: none !important;
      transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }
    .stButton > button[kind="primary"] {
      background: linear-gradient(135deg, #0f766e 0%, #0d9488 100%) !important;
      box-shadow: 0 4px 14px var(--pg-glow) !important;
    }
    .stButton > button[kind="primary"]:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(15, 118, 110, 0.25) !important;
    }
    .stButton > button:disabled {
      opacity: 0.45 !important;
    }

    /* Girişler */
    .stTextInput input, .stRadio label, [data-baseweb="select"] {
      font-family: "Instrument Sans", sans-serif !important;
    }
    .stTextInput input {
      border-radius: 12px !important;
      border-color: var(--pg-line) !important;
    }
    .stFileUploader section {
      border-radius: 14px !important;
      border: 2px dashed #cbd5e1 !important;
      background: #fafbfc !important;
    }

    /* Uyarı kutuları — yumuşak köşe */
    .stAlert {
      border-radius: 12px !important;
    }

    /* Progress */
    .stProgress > div > div {
      background: linear-gradient(90deg, #0f766e, #14b8a6) !important;
      border-radius: 999px !important;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
      background: linear-gradient(180deg, var(--pg-sidebar) 0%, #1e293b 100%) !important;
      border-right: 1px solid rgba(255,255,255,0.06) !important;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li,
    [data-testid="stSidebar"] .stCaption {
      color: var(--pg-sidebar-muted) !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] strong {
      color: #f1f5f9 !important;
    }
    [data-testid="stSidebar"] hr {
      border-color: rgba(255,255,255,0.08) !important;
    }
    [data-testid="stSidebar"] .stExpander {
      background: rgba(255,255,255,0.04) !important;
      border-radius: 12px !important;
      border: 1px solid rgba(255,255,255,0.08) !important;
    }

    /* Hero */
    .pg-hero {
      position: relative;
      overflow: hidden;
      border-radius: 20px;
      padding: 2rem 2.25rem;
      margin-bottom: 1.75rem;
      background: linear-gradient(135deg, #0f172a 0%, #134e4a 55%, #0f766e 100%);
      color: #f8fafc;
      box-shadow: 0 20px 50px -12px rgba(15, 23, 42, 0.35);
    }
    .pg-hero::after {
      content: "";
      position: absolute;
      inset: 0;
      background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.04'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
      opacity: 0.9;
      pointer-events: none;
    }
    .pg-hero-inner { position: relative; z-index: 1; }
    .pg-hero h1 {
      margin: 0;
      font-size: clamp(1.65rem, 3vw, 2.15rem);
      font-weight: 700;
      letter-spacing: -0.03em;
      color: #fff !important;
    }
    .pg-hero p {
      margin: 0.65rem 0 0;
      font-size: 1.02rem;
      color: rgba(226, 232, 240, 0.88) !important;
      max-width: 52rem;
      line-height: 1.5;
    }
    .pg-hero-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 1.1rem;
    }
    .pg-hero-tags span {
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 0.35rem 0.75rem;
      border-radius: 999px;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.18);
      color: #e2e8f0 !important;
    }

    /* Bölüm başlıkları */
    .pg-section {
      font-size: 1rem;
      font-weight: 700;
      color: var(--pg-ink);
      margin: 0 0 1rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      letter-spacing: -0.02em;
    }
    .pg-section-icon {
      width: 2rem;
      height: 2rem;
      border-radius: 10px;
      background: var(--pg-accent-soft);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 1rem;
    }

    /* Kart yüzeyi (ana alan panelleri) */
    .pg-panel {
      background: var(--pg-surface);
      border: 1px solid var(--pg-line);
      border-radius: 16px;
      padding: 1.35rem 1.5rem;
      box-shadow: 0 1px 2px rgba(12, 18, 34, 0.04);
    }

    .alarm-red {
      background: linear-gradient(90deg, #fef2f2, #fff7f7);
      border: 1px solid #fecaca;
      border-left: 4px solid #dc2626;
      padding: 14px 18px;
      border-radius: 12px;
      color: #7f1d1d;
    }
    .alarm-yellow {
      background: linear-gradient(90deg, #fffbeb, #fffef5);
      border: 1px solid #fde68a;
      border-left: 4px solid #d97706;
      padding: 14px 18px;
      border-radius: 12px;
      color: #78350f;
    }
    .alarm-green {
      background: linear-gradient(90deg, #ecfdf5, #f0fdf9);
      border: 1px solid #a7f3d0;
      border-left: 4px solid #059669;
      padding: 14px 18px;
      border-radius: 12px;
      color: #064e3b;
    }
    .alarm-unknown {
      background: #f8fafc;
      border: 1px solid var(--pg-line);
      border-left: 4px solid #64748b;
      padding: 14px 18px;
      border-radius: 12px;
      color: #475569 !important;
    }
    .alarm-unknown b,
    .alarm-unknown strong {
      color: #0f172a !important;
    }

    /* Koyu temada Streamlit’in açık zemin + beyaz metin kalıtımını kır */
    .alarm-red,
    .alarm-red b,
    .alarm-red strong {
      color: #7f1d1d !important;
    }
    .alarm-yellow,
    .alarm-yellow b,
    .alarm-yellow strong {
      color: #78350f !important;
    }
    .alarm-green,
    .alarm-green b,
    .alarm-green strong {
      color: #064e3b !important;
    }

    .metric-card {
      background: var(--pg-surface);
      border: 1px solid var(--pg-line);
      border-radius: 14px;
      padding: 1.1rem 1rem;
      text-align: center;
      box-shadow: 0 2px 8px rgba(12, 18, 34, 0.04);
    }
    .metric-card h3 { margin: 0; font-size: 1.55rem; font-weight: 700; color: var(--pg-ink); }
    .metric-card p  { margin: 0.35rem 0 0; font-size: 0.8rem; color: var(--pg-muted); font-weight: 500; }

    .pg-empty {
      text-align: center;
      padding: 3.5rem 1.5rem;
      background: var(--pg-surface);
      border: 1px dashed #cbd5e1;
      border-radius: 16px;
      color: var(--pg-muted);
    }
    .pg-empty .pg-empty-icon {
      font-size: 2.75rem;
      line-height: 1;
      margin-bottom: 1rem;
      filter: grayscale(0.2);
    }
    .pg-empty p { margin: 0; font-size: 1.05rem; line-height: 1.6; }

    .pg-status-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.85rem;
      padding: 0.45rem 0.75rem;
      border-radius: 10px;
      margin-bottom: 0.35rem;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.1);
      color: #e2e8f0 !important;
    }
    .pg-status-pill.ok { border-color: rgba(45, 212, 191, 0.35); background: rgba(45, 212, 191, 0.1); }
    .pg-status-pill.bad { border-color: rgba(248, 113, 113, 0.35); background: rgba(248, 113, 113, 0.08); }

    .pg-about-card {
      background: var(--pg-surface);
      border: 1px solid var(--pg-line);
      border-radius: 16px;
      padding: 1.5rem 1.75rem;
      box-shadow: 0 2px 12px rgba(12, 18, 34, 0.05);
    }
    .pg-about-card table { width: 100%; border-collapse: collapse; margin-top: 0.75rem; }
    .pg-about-card th, .pg-about-card td {
      border-bottom: 1px solid var(--pg-line);
      padding: 0.65rem 0.5rem;
      text-align: left;
      font-size: 0.92rem;
    }
    .pg-about-card th { color: var(--pg-muted); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }

    code, .stMarkdown code {
      font-family: "JetBrains Mono", monospace !important;
      font-size: 0.85em;
      background: #f1f5f9 !important;
      padding: 0.15rem 0.4rem;
      border-radius: 6px;
    }

    /* Analiz adım satırı */
    .pg-step-line {
      font-size: 0.9rem;
      color: #475569;
      padding: 0.25rem 0 0.35rem;
      border-bottom: 1px solid #e2e8f0;
    }
    .pg-step-num {
      display: inline-block;
      min-width: 2.75rem;
      font-weight: 700;
      color: #0f766e;
      font-variant-numeric: tabular-nums;
    }

    /* Streamlit status kutusu */
    [data-testid="stStatus"] {
      border-radius: 14px !important;
      border: 1px solid var(--pg-line) !important;
    }

    /* Koyu tema (sistem / Streamlit) uyumu */
    [data-theme="dark"] .stApp {
      background: #0b0f14 !important;
      background-image:
        radial-gradient(ellipse 100% 80% at 100% 0%, rgba(20, 184, 166, 0.12), transparent),
        radial-gradient(ellipse 80% 60% at 0% 100%, rgba(251, 146, 60, 0.08), transparent) !important;
    }
    [data-theme="dark"] .metric-card {
      background: #111827 !important;
      border-color: #1f2937 !important;
      box-shadow: none !important;
    }
    [data-theme="dark"] .metric-card h3 { color: #f1f5f9 !important; }
    [data-theme="dark"] .metric-card p { color: #94a3b8 !important; }
    [data-theme="dark"] .pg-step-line { color: #cbd5e1; border-bottom-color: #1f2937; }
    [data-theme="dark"] .pg-step-num { color: #2dd4bf; }
    [data-theme="dark"] .pg-empty {
      background: #111827 !important;
      border-color: #334155 !important;
      color: #94a3b8 !important;
    }
    [data-theme="dark"] .stTabs [data-baseweb="tab-list"] {
      background: #111827 !important;
      border-color: #1f2937 !important;
    }
    [data-theme="dark"] .stFileUploader section {
      background: #0f172a !important;
      border-color: #334155 !important;
    }

    /* --- Koyu tema: alarm bantları (yüksek kontrast) --- */
    [data-theme="dark"] .alarm-red,
    [data-color-scheme="dark"] .alarm-red {
      background: rgba(127, 29, 29, 0.45) !important;
      border: 1px solid rgba(248, 113, 113, 0.5) !important;
      border-left: 4px solid #f87171 !important;
      color: #fecaca !important;
    }
    [data-theme="dark"] .alarm-red b,
    [data-theme="dark"] .alarm-red strong,
    [data-color-scheme="dark"] .alarm-red b,
    [data-color-scheme="dark"] .alarm-red strong {
      color: #fff7ed !important;
    }

    [data-theme="dark"] .alarm-yellow,
    [data-color-scheme="dark"] .alarm-yellow {
      background: rgba(120, 53, 15, 0.45) !important;
      border: 1px solid rgba(251, 191, 36, 0.45) !important;
      border-left: 4px solid #fbbf24 !important;
      color: #fef3c7 !important;
    }
    [data-theme="dark"] .alarm-yellow b,
    [data-theme="dark"] .alarm-yellow strong,
    [data-color-scheme="dark"] .alarm-yellow b,
    [data-color-scheme="dark"] .alarm-yellow strong {
      color: #fffbeb !important;
    }

    [data-theme="dark"] .alarm-green,
    [data-color-scheme="dark"] .alarm-green {
      background: rgba(6, 78, 59, 0.45) !important;
      border: 1px solid rgba(52, 211, 153, 0.45) !important;
      border-left: 4px solid #34d399 !important;
      color: #d1fae5 !important;
    }
    [data-theme="dark"] .alarm-green b,
    [data-theme="dark"] .alarm-green strong,
    [data-color-scheme="dark"] .alarm-green b,
    [data-color-scheme="dark"] .alarm-green strong {
      color: #ecfdf5 !important;
    }

    [data-theme="dark"] .alarm-unknown,
    [data-color-scheme="dark"] .alarm-unknown {
      background: #1e293b !important;
      border: 1px solid #475569 !important;
      border-left: 4px solid #94a3b8 !important;
      color: #e2e8f0 !important;
    }
    [data-theme="dark"] .alarm-unknown b,
    [data-theme="dark"] .alarm-unknown strong,
    [data-color-scheme="dark"] .alarm-unknown b,
    [data-color-scheme="dark"] .alarm-unknown strong {
      color: #f8fafc !important;
    }

    [data-theme="dark"] .pg-section,
    [data-color-scheme="dark"] .pg-section {
      color: #f1f5f9 !important;
    }
    [data-theme="dark"] .pg-section-icon,
    [data-color-scheme="dark"] .pg-section-icon {
      background: rgba(45, 212, 191, 0.18) !important;
    }

    [data-theme="dark"] div[data-testid="stVerticalBlock"] > div > .stTabs [data-baseweb="tab-list"],
    [data-color-scheme="dark"] div[data-testid="stVerticalBlock"] > div > .stTabs [data-baseweb="tab-list"] {
      background: #0f172a !important;
      border-color: #334155 !important;
    }

    [data-theme="dark"] .stTabs [data-baseweb="tab"][aria-selected="false"],
    [data-color-scheme="dark"] .stTabs [data-baseweb="tab"][aria-selected="false"] {
      color: #94a3b8 !important;
    }

    [data-theme="dark"] .stButton > button[kind="primary"],
    [data-color-scheme="dark"] .stButton > button[kind="primary"] {
      background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%) !important;
      color: #f8fafc !important;
    }
    [data-theme="dark"] .stButton > button[kind="secondary"],
    [data-color-scheme="dark"] .stButton > button[kind="secondary"] {
      background: #1e293b !important;
      color: #e2e8f0 !important;
      border: 1px solid #475569 !important;
    }

    [data-theme="dark"] code,
    [data-theme="dark"] .stMarkdown code,
    [data-color-scheme="dark"] code,
    [data-color-scheme="dark"] .stMarkdown code {
      background: #1e293b !important;
      color: #e2e8f0 !important;
    }

    [data-theme="dark"] .pg-about-card,
    [data-color-scheme="dark"] .pg-about-card {
      background: #111827 !important;
      border-color: #334155 !important;
      color: #cbd5e1 !important;
    }
    [data-theme="dark"] .pg-about-card th,
    [data-color-scheme="dark"] .pg-about-card th {
      color: #94a3b8 !important;
    }
    [data-theme="dark"] .pg-about-card td,
    [data-color-scheme="dark"] .pg-about-card td {
      border-bottom-color: #334155 !important;
      color: #e2e8f0 !important;
    }

    [data-theme="dark"] [data-testid="stStatus"],
    [data-color-scheme="dark"] [data-testid="stStatus"] {
      background: #111827 !important;
      border-color: #334155 !important;
    }

    [data-theme="dark"] .stRadio label,
    [data-color-scheme="dark"] .stRadio label {
      color: #e2e8f0 !important;
    }
    [data-theme="dark"] .stTextInput label,
    [data-color-scheme="dark"] .stTextInput label {
      color: #cbd5e1 !important;
    }
    [data-theme="dark"] .stTextInput input,
    [data-color-scheme="dark"] .stTextInput input {
      background: #0f172a !important;
      color: #f1f5f9 !important;
      border-color: #334155 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# BAŞLIK
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="pg-hero">
      <div class="pg-hero-inner">
        <h1>Pharma-Guard AI</h1>
        <p>Akıllı ilaç denetimi: görüntü ve metinle çoklu ajan analizi,
           yerel prospektüs (RAG) doğrulaması ve tek tıkla PDF raporu.</p>
        <div class="pg-hero-tags">
          <span>Gemini</span>
          <span>Groq · LLaVA</span>
          <span>ChromaDB</span>
          <span>Fact-check</span>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# SIDEBAR — API DURUM PANELİ
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div style="padding:0.25rem 0 1rem;">
          <div style="font-size:1.65rem;line-height:1;">💊</div>
          <div style="font-weight:700;font-size:1.1rem;color:#f8fafc;letter-spacing:-0.02em;">
            Pharma-Guard
          </div>
          <div style="font-size:0.78rem;color:#94a3b8;margin-top:0.2rem;">Kontrol paneli</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### Bağlantılar")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    groq_key = os.getenv("GROQ_API_KEY", "")

    g_cls = "ok" if gemini_key else "bad"
    q_cls = "ok" if groq_key else "bad"
    st.markdown(
        f'<div class="pg-status-pill {g_cls}">{"●" if gemini_key else "○"} Gemini API — '
        f'{"aktif" if gemini_key else ".env / Secrets"}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="pg-status-pill {q_cls}">{"●" if groq_key else "○"} Groq — '
        f'{"aktif" if groq_key else ".env / Secrets"}</div>',
        unsafe_allow_html=True,
    )

    pdf_list = list_corpus_pdfs()
    st.markdown(
        f'<div class="pg-status-pill ok" style="margin-top:0.6rem;">📚 RAG: '
        f"{len(pdf_list)} prospektüs</div>",
        unsafe_allow_html=True,
    )
    if pdf_list:
        with st.expander("Dosya listesi", expanded=False):
            for f in pdf_list:
                st.markdown(f"- `{f}`")
    else:
        st.caption("Corpus boş — Prospektüs sekmesinden PDF ekleyin.")

    st.markdown("---")
    st.markdown("##### Ajanlar")
    st.caption(
        "Vision · RAG · Fact-check · Safety · Corporate · Rapor — "
        "orkestrasyon otomatik."
    )
    st.markdown("---")
    st.caption("Bilgilendirme amaçlıdır; tıbbi karar için hekime danışın.")

# ---------------------------------------------------------------------------
# ANA SEKMELER
# ---------------------------------------------------------------------------

tab_analyze, tab_corpus, tab_about = st.tabs(
    ["🔬 İlaç Analizi", "📚 Prospektüs Yönetimi", "ℹ️ Hakkında"]
)

# ═══════════════════════════════════════════════════════════════════════════
# SEKME 1: İLAÇ ANALİZİ
# ═══════════════════════════════════════════════════════════════════════════

with tab_analyze:
    col_input, col_result = st.columns([1, 1.4], gap="large")

    # ── Giriş Bölümü ──────────────────────────────────────────────────────
    with col_input:
        pg_section("Giriş yöntemi", "📥")

        input_method = st.radio(
            "Nasıl analiz etmek istiyorsunuz?",
            ["🖼️ İlaç Görseli Yükle", "✏️ İlaç Adı Yaz"],
            horizontal=True,
            label_visibility="collapsed",
        )

        image_obj = None
        drug_name_input = None

        if "Görsel" in input_method:
            uploaded_img = st.file_uploader(
                "İlaç kutusunun fotoğrafını yükleyin",
                type=["jpg", "jpeg", "png", "webp", "bmp"],
                help="Net çekilmiş, ilaç adı ve dozajın okunabildiği bir fotoğraf yükleyin.",
            )
            if uploaded_img:
                image_obj = load_image_from_upload(uploaded_img)
                st.image(image_obj, caption="Yüklenen görsel", use_container_width=True)
                image_obj = preprocess_image(image_obj)

                st.info(
                    "💡 **İpuçları:**\n"
                    "- Kutunun ön yüzünü tam karşıdan çekin.\n"
                    "- İlaç adı ve mg değerinin görünür olduğundan emin olun.\n"
                    "- Düşük ışıkta çekilen fotoğraflar analiz kalitesini düşürür."
                )
        else:
            drug_name_input = st.text_input(
                "İlaç adını girin",
                placeholder="örn: Augmentin 1000 mg, Parol 500 mg...",
            )
            st.caption(
                "Görsel yoksa, girilen ilaç adıyla prospektüs veritabanında "
                "arama yapılır ve rapor hazırlanır."
            )

        st.markdown("---")

        # Analiz Butonu
        can_analyze = bool(image_obj is not None or (drug_name_input and drug_name_input.strip()))
        if not (gemini_key and groq_key):
            st.warning("⚠️ Analiz için GEMINI_API_KEY ve GROQ_API_KEY gereklidir.")
            can_analyze = False

        analyze_btn = st.button(
            "🚀 Analizi Başlat",
            type="primary",
            disabled=not can_analyze,
            use_container_width=True,
        )

    # ── Sonuç Bölümü ──────────────────────────────────────────────────────
    with col_result:
        pg_section("Analiz sonuçları", "📊")

        if analyze_btn:
            for k in ("analysis_result", "report_pdf"):
                st.session_state.pop(k, None)

            from agents import PharmaGuardOrchestrator

            # Eski oturum önbelleği (farklı Gemini model sürümü) temizliği
            for _old in (
                "orchestrator",
                "pharma_orchestrator_v2",
                "pharma_orchestrator_v3",
                "pharma_orchestrator_v4",
                "pharma_orchestrator_v5",
            ):
                if _old in st.session_state:
                    del st.session_state[_old]

            _orch_key = "pharma_orchestrator_v6"
            if _orch_key not in st.session_state:
                st.session_state[_orch_key] = PharmaGuardOrchestrator()

            def _run_pipeline(progress_bar, step_log, status_ui):
                def update_progress(step: int, msg: str):
                    progress_bar.progress(step / 7)
                    step_log.markdown(
                        f'<p class="pg-step-line"><span class="pg-step-num">{step}/7</span>{msg}</p>',
                        unsafe_allow_html=True,
                    )
                    if status_ui is not None:
                        label = msg if len(msg) < 72 else msg[:69] + "…"
                        status_ui.update(label=label, state="running")

                return st.session_state[_orch_key].run(
                    image=image_obj,
                    drug_name_text=drug_name_input,
                    progress_callback=update_progress,
                )

            try:
                if hasattr(st, "status"):
                    with st.status("Pipeline: Vision → RAG → Fact-check → Güvenlik → Firma → Rapor", expanded=True) as pg_status:
                        prog = st.progress(0)
                        log = st.empty()
                        result = _run_pipeline(prog, log, pg_status)
                        prog.progress(1.0)
                        pg_status.update(
                            label="Tamamlandı — sonuçlar aşağıda",
                            state="complete",
                            expanded=False,
                        )
                else:
                    prog_ph = st.empty()
                    log_ph = st.empty()
                    prog = prog_ph.progress(0)
                    log = log_ph.empty()
                    with st.spinner("Ajanlar sırayla çalışıyor…"):
                        result = _run_pipeline(prog, log, None)
                    prog_ph.empty()
                    log_ph.empty()

                st.session_state.analysis_result = result
                drug_display = result["vision"].get("ticari_ad") or drug_name_input or "İlaç"
                st.session_state.report_pdf = generate_pdf_report(
                    report_markdown=result["report"],
                    drug_name=drug_display,
                    alarm_level=result["alarm"],
                    avg_confidence=result["avg_confidence"],
                    vision_data=result["vision"],
                )
            except Exception as e:
                st.error(f"Analiz durdu: {e!s}")
                st.exception(e)

        # Sonuçları göster
        if "analysis_result" in st.session_state:
            result = st.session_state.analysis_result

            # ── Alarm Bandı ──
            alarm = result.get("alarm", "BİLİNMİYOR")
            emoji = ALARM_EMOJI.get(alarm, "⚪")
            msg = ALARM_MESSAGE.get(alarm, "")
            alarm_css = {
                "KIRMIZI": "alarm-red",
                "SARI": "alarm-yellow",
                "YEŞİL": "alarm-green",
            }.get(alarm, "alarm-unknown")

            st.markdown(
                f'<div class="{alarm_css}"><b>{emoji} {alarm}</b> — {msg}</div>',
                unsafe_allow_html=True,
            )
            st.markdown("")

            # ── Metrik kartları + sentez durumu ──
            synth_err = result.get("synthesis_error")
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                confidence = result.get("avg_confidence", 0)
                conf_color = "#059669" if confidence >= 8 else "#d97706" if confidence >= 5 else "#dc2626"
                st.markdown(
                    f'<div class="metric-card"><h3 style="color:{conf_color}">'
                    f'{confidence:.1f}<span style="font-size:1rem">/10</span></h3>'
                    f"<p>Güven (ajan ort.)</p></div>",
                    unsafe_allow_html=True,
                )
            with m2:
                rag_count = len(result.get("rag_results", []))
                st.markdown(
                    f'<div class="metric-card"><h3>{rag_count}</h3>'
                    f"<p>RAG pasajları</p></div>",
                    unsafe_allow_html=True,
                )
            with m3:
                fc = result.get("fact_check", {})
                fc_ok = not fc.get("uyusmazlik", False)
                fc_icon = "✅" if fc_ok else "⛔"
                st.markdown(
                    f'<div class="metric-card"><h3>{fc_icon}</h3>'
                    f"<p>Fact-check</p></div>",
                    unsafe_allow_html=True,
                )
            with m4:
                rep_ok = not synth_err
                rep_icon = "✅" if rep_ok else "⚠️"
                rep_sub = "Özet rapor" if rep_ok else "Sentez hatası"
                st.markdown(
                    f'<div class="metric-card"><h3>{rep_icon}</h3>'
                    f"<p>{rep_sub}</p></div>",
                    unsafe_allow_html=True,
                )

            if synth_err:
                st.caption(
                    "Güven puanı Gemini özetine dahil edilmedi; Vision / Safety / Corporate "
                    "çıktılarından hesaplandı."
                )
            st.markdown("")

            if synth_err:
                st.error(
                    "**Özet rapor üretilemedi** (Gemini). Diğer ajanlar tamamlandı — "
                    "bilgiler **Görsel Analiz**, **Güvenlik** ve **Firma** sekmelerinde. "
                    "`.env` veya Secrets’ta örn. `GEMINI_MODEL=gemini-2.5-flash` veya `gemini-1.5-flash` deneyin."
                )
                with st.expander("Teknik ayrıntı", expanded=False):
                    st.code(synth_err)

            # ── Fact-Check Uyarısı ──
            if not fc_ok:
                st.error(
                    "⛔ **VERİ UYUŞMAZLIĞI TESPİT EDİLDİ**\n\n"
                    + "\n".join(f"- {s}" for s in fc.get("sorunlar", []))
                )

            # ── Detay Sekmeleri ──
            rt1, rt2, rt3, rt4 = st.tabs(
                ["📋 Rapor", "🔬 Görsel Analiz", "🛡️ Güvenlik", "🏭 Firma"]
            )

            with rt1:
                st.markdown(result.get("report", "Rapor oluşturulamadı."))
                if "report_pdf" in st.session_state:
                    drug_display = (
                        result["vision"].get("ticari_ad") or drug_name_input or "ilac"
                    )
                    filename = f"pharma_guard_{drug_display.replace(' ', '_')}.pdf"
                    st.download_button(
                        label="📥 PDF indir (mevcut metinle)",
                        data=st.session_state.report_pdf,
                        file_name=filename,
                        mime="application/pdf",
                        type="secondary" if synth_err else "primary",
                        use_container_width=True,
                    )
                    if synth_err:
                        st.caption("PDF, hata açıklaması ve mevcut ajan çıktılarını içerir.")

            with rt2:
                st.markdown("**Vision Scanner Çıktısı**")
                vision = result.get("vision", {})
                if vision:
                    fields = [
                        ("Ticari Ad", vision.get("ticari_ad")),
                        ("Etken Madde", vision.get("etken_madde")),
                        ("Dozaj", vision.get("dozaj")),
                        ("Form", vision.get("form")),
                        ("Barkod", vision.get("barkod")),
                        ("Üretici", vision.get("uretici")),
                        ("Okunabilirlik", f"{vision.get('okunabilirlik_skoru', '?')}/10"),
                        ("Notlar", vision.get("notlar")),
                        ("Kaynak", vision.get("kaynak")),
                    ]
                    for label, value in fields:
                        if value is not None:
                            st.markdown(f"**{label}:** {value}")
                    if "hata" in vision:
                        st.warning(f"Hata: {vision['hata']}")
                else:
                    st.info("Görsel analiz verisi yok.")

                st.markdown("---")
                st.markdown("**RAG Arama Sonuçları**")
                for i, r in enumerate(result.get("rag_results", []), 1):
                    with st.expander(f"Sonuç {i} — {r.get('kaynak', '?')} (s. {r.get('sayfa', '?')})"):
                        st.caption(r.get("metin", ""))

            with rt3:
                safety = result.get("safety", {})
                if safety:
                    if "hata" in safety:
                        st.error(f"Safety Auditor hatası: {safety['hata']}")
                    else:
                        alarm_sev = safety.get("alarm_seviyesi", "BİLİNMİYOR")
                        st.markdown(
                            f"**Alarm Seviyesi:** {ALARM_EMOJI.get(alarm_sev, '⚪')} {alarm_sev}"
                        )
                        st.markdown(f"**Gerekçe:** {safety.get('alarm_gerekce', '—')}")
                        st.markdown(f"**Güven Puanı:** {safety.get('guven_puani', '?')}/10")

                        yd = safety.get("yan_etkiler", {})
                        if yd:
                            st.markdown("#### Yan Etkiler")
                            for tur, liste in yd.items():
                                if liste:
                                    st.markdown(f"**{tur.capitalize()}:**")
                                    for item in liste:
                                        st.markdown(f"  - {item}")

                        etkilesim = safety.get("etkilesimler", [])
                        if etkilesim:
                            st.markdown("#### İlaç Etkileşimleri")
                            for item in etkilesim:
                                st.markdown(f"- {item}")

                        kontra = safety.get("kontrendikasyonlar", [])
                        if kontra:
                            st.markdown("#### Kontrendikasyonlar (Kimler Kullanamaz)")
                            for item in kontra:
                                st.markdown(f"- ⛔ {item}")

                        ozel = safety.get("ozel_uyarilar", [])
                        if ozel:
                            st.markdown("#### Özel Uyarılar")
                            for item in ozel:
                                st.markdown(f"- ⚠️ {item}")
                else:
                    st.info("Güvenlik verisi yok.")

            with rt4:
                corp = result.get("corporate", {})
                if corp:
                    if "hata" in corp:
                        st.warning(f"Corporate Analyst uyarısı: {corp['hata']}")
                    fields = [
                        ("Firma Adı", corp.get("firma_adi")),
                        ("Ülke", corp.get("ulke")),
                        ("TİTCK Durumu", corp.get("titck_durumu")),
                        ("Güven Puanı", f"{corp.get('guven_puani', '?')}/10"),
                    ]
                    for label, value in fields:
                        if value:
                            st.markdown(f"**{label}:** {value}")
                    sertifikalar = corp.get("sertifikalar", [])
                    if sertifikalar:
                        st.markdown(f"**Sertifikalar:** {', '.join(sertifikalar)}")
                    if corp.get("genel_degerlendirme"):
                        st.info(corp["genel_degerlendirme"])
                else:
                    st.info("Firma verisi yok.")
        else:
            st.markdown(
                """
                <div class="pg-empty">
                    <div class="pg-empty-icon">💊</div>
                    <p>Görsel yükleyin veya ilaç adını yazın; ardından
                    <strong>Analizi Başlat</strong> ile ajanları çalıştırın.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ═══════════════════════════════════════════════════════════════════════════
# SEKME 2: PROSPEKTÜS YÖNETİMİ
# ═══════════════════════════════════════════════════════════════════════════

with tab_corpus:
    pg_section("RAG prospektüs veritabanı", "📚")
    st.markdown(
        """
        <div style="background:linear-gradient(90deg,#ecfeff,#f0fdfa);border:1px solid #99f6e4;
        border-radius:14px;padding:1rem 1.2rem;margin-bottom:1.25rem;color:#115e59;font-size:0.95rem;">
        PDF prospektüsleri burada toplanır. Mümkünse <strong>TİTCK</strong> veya
        <strong>FDA / EMA</strong> kaynaklı resmi belgeleri kullanın.
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_upload, col_list = st.columns([1, 1])

    with col_upload:
        pg_section("Prospektüs ekle", "➕")
        uploaded_pdfs = st.file_uploader(
            "PDF prospektüs yükle (çoklu seçim desteklenir)",
            type=["pdf"],
            accept_multiple_files=True,
            key="corpus_uploader",
        )

        if st.button("📂 Seçilen PDF'leri Kaydet", disabled=not uploaded_pdfs):
            saved = []
            for f in uploaded_pdfs:
                path = save_uploaded_pdf(f)
                saved.append(f.name)
            st.success(f"✅ {len(saved)} dosya kaydedildi: {', '.join(saved)}")

            # İndeksi yeniden oluştur
            if "pharma_orchestrator_v6" in st.session_state:
                with st.spinner("ChromaDB indeksi güncelleniyor..."):
                    st.session_state.pharma_orchestrator_v6.rag_agent.rebuild_index()
                st.success("✅ RAG indeksi güncellendi!")

    with col_list:
        pg_section("Mevcut dosyalar", "📄")
        pdfs = list_corpus_pdfs()
        if pdfs:
            for pdf in pdfs:
                st.markdown(f"📄 `{pdf}`")
        else:
            st.warning("Henüz prospektüs yüklenmedi.")

        if pdfs and st.button("🔄 İndeksi Yeniden Oluştur"):
            if "pharma_orchestrator_v6" in st.session_state:
                with st.spinner("Lütfen bekleyin..."):
                    st.session_state.pharma_orchestrator_v6.rag_agent.rebuild_index()
                st.success("✅ İndeks yeniden oluşturuldu!")
            else:
                st.warning("Önce İlaç Analizi sekmesinde bir kez analiz başlatın.")

    st.markdown("---")
    pg_section("Kaynak önerileri", "💡")
    st.markdown(
        """
        <div class="pg-about-card" style="margin-top:0.5rem;">
        <ul style="margin:0;padding-left:1.2rem;color:#475569;line-height:1.75;">
        <li><strong>TİTCK:</strong> titck.gov.tr → Ürün bilgisi</li>
        <li><strong>FDA:</strong> drugs@FDA, DailyMed</li>
        <li><strong>EMA:</strong> ema.europa.eu → Ürün bilgisi</li>
        <li>Kutu içi prospektüsü tarayıp PDF olarak da ekleyebilirsiniz.</li>
        </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════════════════
# SEKME 3: HAKKINDA
# ═══════════════════════════════════════════════════════════════════════════

with tab_about:
    pg_section("Pharma-Guard AI", "ℹ️")
    st.markdown(
        """
        <div class="pg-about-card">
        <p style="margin:0 0 1rem;font-size:1.05rem;line-height:1.65;color:#334155;">
        <strong>Pharma-Guard AI</strong>, görüntü işleme ve NLP'yi birleştiren,
        otonom bir <strong>çoklu ajan</strong> mimarisidir. Amaç; prospektüsle
        desteklenen, tutarlılık kontrollü bilgilendirme özetleri üretmektir.
        </p>

        <h4 style="margin:1.25rem 0 0.5rem;font-size:0.95rem;color:#0f766e;">Ajan mimarisi</h4>
        <table>
        <thead><tr><th>Ajan</th><th>Model</th><th>Görev</th></tr></thead>
        <tbody>
        <tr><td>👁️ Vision</td><td>LLaVA (Groq) + Gemini Vision</td><td>OCR, kutu verisi</td></tr>
        <tr><td>📚 RAG</td><td>ChromaDB + ST</td><td>Yerel PDF arama</td></tr>
        <tr><td>🔍 Fact-check</td><td>Kural tabanlı</td><td>Tutarsızlık</td></tr>
        <tr><td>🛡️ Safety</td><td>Llama-3-70B</td><td>Yan etki / risk</td></tr>
        <tr><td>🏭 Corporate</td><td>Gemini</td><td>Firma / menşe</td></tr>
        <tr><td>📝 Rapor</td><td>Gemini</td><td>Özet + Markdown</td></tr>
        </tbody>
        </table>

        <h4 style="margin:1.25rem 0 0.5rem;font-size:0.95rem;color:#0f766e;">İş akışı</h4>
        <ol style="margin:0;padding-left:1.2rem;color:#475569;line-height:1.8;">
        <li>Görsel veya ilaç adı</li>
        <li>Vision → RAG → Fact-check</li>
        <li>Paralel: Safety + Corporate</li>
        <li>Rapor sentezi ve PDF</li>
        </ol>

        <div style="margin-top:1.25rem;padding:1rem;border-radius:12px;background:#fff7ed;
        border:1px solid #fed7aa;color:#9a3412;font-size:0.92rem;">
        <strong>⚕️ Yasal:</strong> Yalnızca bilgilendirme amaçlıdır. Tanı ve tedavi için
        hekim veya eczacıya başvurun; çıktı tıbbi tavsiye değildir.
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<div class="pg-about-card"><p style="margin:0;color:#64748b;font-size:0.9rem;">'
            "<strong style='color:#0f172a'>Sürüm</strong> 1.0.0 · Proje</p></div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            '<div class="pg-about-card"><p style="margin:0;color:#64748b;font-size:0.9rem;">'
            "<strong style='color:#0f172a'>MIT</strong> · "
            '<a href="https://github.com/cemevecen/medic" target="_blank" rel="noopener">GitHub</a>'
            "</p></div>",
            unsafe_allow_html=True,
        )
