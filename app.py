"""
PHARMA-GUARD AI — Ana Streamlit Arayüzü
app.py: Modern tasarım, çoklu ajan orkestrasyon, PDF rapor.
"""

import os
import json
from pathlib import Path

import streamlit as st
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

from utils import (
    preprocess_image,
    load_image_from_upload,
    generate_pdf_report,
    save_uploaded_pdf,
    list_corpus_pdfs,
    ALARM_EMOJI,
    ALARM_MESSAGE,
)

# ─────────────────────────────────────────────
# SAYFA YAPISI
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Pharma-Guard AI",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
.block-container { padding-top:1.25rem !important; padding-bottom:3rem !important; max-width:1400px !important; }

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
  background: rgba(255,255,255,.04) !important;
  border-radius: 12px !important;
  border: 1px solid rgba(255,255,255,.1) !important;
}

/* ── Sekmeler — hap/pill stili ───────────────── */
.stTabs [data-baseweb="tab-list"] {
  gap: .3rem !important;
  background: var(--pg-surface) !important;
  padding: .3rem !important;
  border-radius: 14px !important;
  border: 1px solid var(--pg-line) !important;
  box-shadow: 0 1px 4px rgba(0,0,0,.06) !important;
}
/* aktif olmayan sekme */
button[data-baseweb="tab"] {
  border-radius: 10px !important;
  padding: .6rem 1.1rem !important;
  font-weight: 600 !important;
  font-size: .92rem !important;
  color: var(--pg-muted) !important;
  background: transparent !important;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
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

/* ── İç sekmeler ────────────────────────────── */
div[data-testid="stVerticalBlock"] .stTabs [data-baseweb="tab-list"] {
  background: var(--pg-canvas) !important;
}

/* ── Butonlar ───────────────────────────────── */
.stButton > button {
  border-radius: 12px !important; font-weight: 600 !important;
  padding: .55rem 1.25rem !important; border: 1px solid transparent !important;
  transition: transform .15s, box-shadow .15s !important;
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
  background: var(--pg-surface) !important;
  color: var(--pg-ink) !important;
  border-color: var(--pg-line) !important;
}
.stButton > button:disabled { opacity: .45 !important; }

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
}
.stTextInput label { color: var(--pg-ink) !important; }
.stRadio label     { color: var(--pg-ink) !important; }
.stFileUploader section {
  border-radius: 14px !important;
  border: 2px dashed var(--pg-line) !important;
  background: var(--pg-surface) !important;
}
/* Dosya yükleme butonu */
.stFileUploader section button {
  background: var(--pg-surface) !important;
  color: var(--pg-accent) !important;
  border: 1px solid var(--pg-accent) !important;
  border-radius: 10px !important;
}
.stAlert   { border-radius: 12px !important; }
.stProgress > div > div {
  background: linear-gradient(90deg, #0f766e, #14b8a6) !important;
  border-radius: 999px !important;
}
[data-testid="stStatus"] {
  border-radius: 14px !important;
  border: 1px solid var(--pg-line) !important;
  background: var(--pg-surface) !important;
}

/* ── Hero banner ────────────────────────────── */
.pg-hero {
  position: relative; overflow: hidden; border-radius: 20px;
  padding: 2rem 2.25rem; margin-bottom: 1.75rem;
  background: linear-gradient(135deg, #0f172a 0%, #134e4a 55%, #0f766e 100%);
  box-shadow: 0 20px 50px -12px rgba(15,23,42,.35);
}
.pg-hero::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.04'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
}
.pg-hero-inner { position: relative; z-index: 1; }
.pg-hero h1 { margin:0; font-size:clamp(1.65rem,3vw,2.1rem); font-weight:700; letter-spacing:-.03em; color:#fff !important; }
.pg-hero p  { margin:.6rem 0 0; font-size:1rem; color:rgba(226,232,240,.88) !important; line-height:1.5; }
.pg-hero-tags { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:1rem; }
.pg-hero-tags span {
  font-size:.75rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em;
  padding:.3rem .7rem; border-radius:999px;
  background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.2); color:#e2e8f0 !important;
}

/* ── Bölüm başlıkları ───────────────────────── */
.pg-section {
  font-size:1rem; font-weight:700; color:var(--pg-ink);
  margin:0 0 1rem; display:flex; align-items:center; gap:.5rem;
}
.pg-section-icon {
  width:2rem; height:2rem; border-radius:10px;
  background:var(--pg-accent-soft);
  display:inline-flex; align-items:center; justify-content:center; font-size:1rem;
}

/* ── Metrik kartları ────────────────────────── */
.metric-card {
  background:var(--pg-surface); border:1px solid var(--pg-line);
  border-radius:14px; padding:1.1rem 1rem; text-align:center;
  box-shadow:0 2px 8px rgba(0,0,0,.04);
}
.metric-card h3 { margin:0; font-size:1.5rem; font-weight:700; color:var(--pg-ink); }
.metric-card p  { margin:.3rem 0 0; font-size:.8rem; color:var(--pg-muted); }

/* ── Alarm bantları ─────────────────────────── */
.alarm-red {
  background:linear-gradient(90deg,#fef2f2,#fff7f7);
  border:1px solid #fecaca; border-left:4px solid #dc2626;
  padding:14px 18px; border-radius:12px;
}
.alarm-red, .alarm-red b, .alarm-red strong { color:#7f1d1d !important; }

.alarm-yellow {
  background:linear-gradient(90deg,#fffbeb,#fffef5);
  border:1px solid #fde68a; border-left:4px solid #d97706;
  padding:14px 18px; border-radius:12px;
}
.alarm-yellow, .alarm-yellow b, .alarm-yellow strong { color:#78350f !important; }

.alarm-green {
  background:linear-gradient(90deg,#ecfdf5,#f0fdf9);
  border:1px solid #a7f3d0; border-left:4px solid #059669;
  padding:14px 18px; border-radius:12px;
}
.alarm-green, .alarm-green b, .alarm-green strong { color:#064e3b !important; }

.alarm-unknown {
  background:var(--pg-surface); border:1px solid var(--pg-line);
  border-left:4px solid #64748b; padding:14px 18px; border-radius:12px;
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
  text-align:center; padding:3.5rem 1.5rem;
  background:var(--pg-surface); border:1.5px dashed var(--pg-line);
  border-radius:16px; color:var(--pg-muted);
}
.pg-empty .pg-empty-icon { font-size:2.75rem; line-height:1; margin-bottom:1rem; }
.pg-empty p { margin:0; font-size:1rem; line-height:1.6; color:var(--pg-muted) !important; }

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
  padding:.25rem 0 .35rem; border-bottom:1px solid var(--pg-line);
}
.pg-step-num { display:inline-block; min-width:2.75rem; font-weight:700; color:var(--pg-accent); }

/* ── Hakkında kartı ─────────────────────────── */
.pg-about-card {
  background:var(--pg-surface); border:1px solid var(--pg-line);
  border-radius:16px; padding:1.5rem 1.75rem;
  box-shadow:0 2px 12px rgba(0,0,0,.05);
  color:var(--pg-ink);
}
.pg-about-card table { width:100%; border-collapse:collapse; margin-top:.75rem; }
.pg-about-card th, .pg-about-card td {
  border-bottom:1px solid var(--pg-line); padding:.65rem .5rem; text-align:left; font-size:.9rem;
  color:var(--pg-ink) !important;
}
.pg-about-card th { color:var(--pg-muted) !important; font-weight:700; font-size:.75rem; text-transform:uppercase; letter-spacing:.04em; }

code, .stMarkdown code {
  font-size:.84em;
  background:var(--pg-line) !important;
  color:var(--pg-ink) !important;
  padding:.15rem .4rem; border-radius:6px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
gemini_key = os.getenv("GEMINI_API_KEY", "")
groq_key   = os.getenv("GROQ_API_KEY", "")
pdf_list   = list_corpus_pdfs()

with st.sidebar:
    st.markdown("### Kontrol paneli")
    g_cls  = "ok"  if gemini_key else "bad"
    gr_cls = "ok"  if groq_key   else "bad"
    st.markdown(
        f'<div class="pg-status-pill {g_cls}">{"●" if gemini_key else "○"} Gemini API — {"aktif" if gemini_key else "eksik"}</div><br>'
        f'<div class="pg-status-pill {gr_cls}">{"●" if groq_key else "○"} Groq — {"aktif" if groq_key else "eksik"}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown(f"📚 **RAG:** {len(pdf_list)} prospektüs")
    if pdf_list:
        with st.expander("Yüklü dosyalar"):
            for f in pdf_list:
                st.caption(f"📄 {f}")
    else:
        st.caption("Corpus boş — Prospektüs sekmesinden PDF ekleyin.")
    st.markdown("---")
    st.markdown("**Ajanlar**")
    st.caption("Vision · RAG · Fact-check · Safety · Corporate · Rapor — orkestrasyon otomatik.")
    st.markdown("---")
    # Versiyon + manuel cache temizleme
    try:
        from agents import PHARMA_GUARD_VERSION as _pgv
    except Exception:
        _pgv = "?"
    st.caption(f"v{_pgv} · Bilgilendirme amaçlıdır; tıbbi karar için hekime danışın.")
    if st.button("🔄 Önbelleği Temizle", use_container_width=True, key="clear_cache_btn"):
        for k in ("orchestrator", "pg_version", "analysis_result", "report_pdf"):
            st.session_state.pop(k, None)
        st.success("✅ Temizlendi — bir sonraki analizde yeniden başlatılır.")
        st.rerun()

# ─────────────────────────────────────────────
# HERO BANNER
# ─────────────────────────────────────────────
st.markdown("""
<div class="pg-hero">
  <div class="pg-hero-inner">
    <h1>💊 Pharma-Guard AI</h1>
    <p>Akıllı ilaç denetimi: görüntü ve metinle çoklu ajan analizi,
       yerel prospektüs (RAG) doğrulaması ve tek tıkla PDF raporu.</p>
    <div class="pg-hero-tags">
      <span>Gemini</span><span>Groq · LLaVA</span><span>ChromaDB</span><span>Fact-check</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# ANA SEKMELER
# ─────────────────────────────────────────────
tab_analyze, tab_corpus, tab_about = st.tabs(
    ["🔬 İlaç Analizi", "📚 Prospektüs Yönetimi", "ℹ️ Hakkında"]
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
            ["🖼️ Görsel Yükle", "📄 PDF Prospektüs", "✏️ İlaç Adı Yaz"],
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
                st.info("💡 Kutunun ön yüzünü tam karşıdan çekin.\n"
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
                st.success(f"📄 **{up_pdf.name}** yüklendi ({len(pdf_bytes_input)//1024} KB)")
                st.info(
                    "💡 Gemini bu PDF'i okuyarak ilaç bilgilerini (etken madde, dozaj, "
                    "endikasyon, yan etkiler) otomatik çıkaracak."
                )

        else:
            drug_name_input = st.text_input(
                "İlaç adını girin",
                placeholder="örn: Augmentin 1000 mg, Parol 500 mg…",
            )

        st.markdown("---")
        if not gemini_key: st.warning("⚠️ GEMINI_API_KEY eksik — Streamlit Secrets'a ekleyin.")
        if not groq_key:   st.warning("⚠️ GROQ_API_KEY eksik — Streamlit Secrets'a ekleyin.")

        has_input = (
            image_obj is not None
            or (drug_name_input and drug_name_input.strip())
            or pdf_bytes_input is not None
        )
        can_run = bool(has_input and gemini_key and groq_key)
        run_btn = st.button("🚀 Analizi Başlat", type="primary",
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

                result = st.session_state.orchestrator.run(
                    image=image_obj,
                    drug_name_text=drug_name_input,
                    pdf_bytes=pdf_bytes_input,
                    pdf_filename=pdf_name_input,
                    progress_callback=_prog,
                )
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
                stat_ph.error(f"❌ Hata: {e}")
                st.exception(e)

            prog_ph.empty()
            stat_ph.empty()

        if "analysis_result" in st.session_state:
            res   = st.session_state.analysis_result
            alarm = res.get("alarm", "BİLİNMİYOR")
            emoji = ALARM_EMOJI.get(alarm, "⚪")
            msg   = ALARM_MESSAGE.get(alarm, "")
            css   = {"KIRMIZI":"alarm-red","SARI":"alarm-yellow","YEŞİL":"alarm-green"}.get(alarm,"alarm-unknown")

            st.markdown(f'<div class="{css}"><b>{emoji} {alarm}</b> — {msg}</div>',
                        unsafe_allow_html=True)
            st.markdown("")

            m1, m2, m3 = st.columns(3)
            conf = res.get("avg_confidence", 0)
            cc   = "#059669" if conf >= 8 else "#d97706" if conf >= 5 else "#dc2626"
            with m1:
                st.markdown(
                    f'<div class="metric-card"><h3 style="color:{cc}">'
                    f'{conf:.1f}<span style="font-size:.9rem;font-weight:400">/10</span></h3>'
                    f'<p>Güven Puanı</p></div>', unsafe_allow_html=True)
            with m2:
                rc = len(res.get("rag_results", []))
                st.markdown(f'<div class="metric-card"><h3>{rc}</h3><p>RAG Sonucu</p></div>',
                            unsafe_allow_html=True)
            with m3:
                fc         = res.get("fact_check", {})
                fc_ok      = not fc.get("uyusmazlik", False)
                corpus_bos = fc.get("corpus_bos", False)
                fc_icon    = "⚠️" if corpus_bos else ("✅" if fc_ok else "⛔")
                fc_label   = "Corpus Boş" if corpus_bos else "Fact-Check"
                st.markdown(
                    f'<div class="metric-card"><h3>{fc_icon}</h3>'
                    f'<p>{fc_label}</p></div>', unsafe_allow_html=True)

            if corpus_bos:
                st.info("ℹ️ **Corpus boş** — Fact-Check yapılamadı. "
                        "Daha güvenilir sonuçlar için Prospektüs sekmesinden PDF yükleyin.")
            elif not fc_ok:
                st.error("⛔ **VERİ UYUŞMAZLIĞI**\n\n" +
                         "\n".join(f"- {s}" for s in fc.get("sorunlar", [])))
            st.markdown("")

            rt1, rt2, rt3, rt4 = st.tabs(["📋 Rapor","🔬 Görsel","🛡️ Güvenlik","🏭 Firma"])

            with rt1:
                st.markdown(res.get("report", "Rapor oluşturulamadı."))
                if "report_pdf" in st.session_state:
                    dn = (res["vision"].get("ticari_ad") or drug_name_input or "ilac")
                    st.download_button("📥 PDF Raporu İndir",
                                       data=st.session_state.report_pdf,
                                       file_name=f"pharma_guard_{dn.replace(' ','_')}.pdf",
                                       mime="application/pdf", type="primary",
                                       use_container_width=True)

            with rt2:
                v = res.get("vision", {})
                for label, key in [("Ticari Ad","ticari_ad"),("Etken Madde","etken_madde"),
                                   ("Dozaj","dozaj"),("Form","form"),("Barkod","barkod"),
                                   ("Üretici","uretici"),("Notlar","notlar"),("Kaynak","kaynak")]:
                    val = v.get(key)
                    if val: st.markdown(f"**{label}:** {val}")
                osk = v.get("okunabilirlik_skoru")
                if osk: st.markdown(f"**Okunabilirlik:** {osk}/10")
                # PDF'e özgü alanlar
                if v.get("endikasyonlar"):
                    st.markdown(f"**Endikasyonlar:** {v['endikasyonlar']}")
                if v.get("prospektus_ozeti"):
                    st.info(f"📄 **Prospektüs Özeti:** {v['prospektus_ozeti']}")
                if v.get("pdf_metin_uzunlugu"):
                    st.caption(f"PDF metin uzunluğu: {v['pdf_metin_uzunlugu']:,} karakter")
                if "hata" in v: st.warning(v["hata"])
                st.markdown("---")
                st.markdown("**RAG eşleşmeleri**")
                for i, r in enumerate(res.get("rag_results", []), 1):
                    with st.expander(f"{i}. {r.get('kaynak','?')} · s.{r.get('sayfa','?')}"):
                        st.caption(r.get("metin",""))

            with rt3:
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
                    for it in (s.get("kontrendikasyonlar") or []): st.markdown(f"⛔ {it}")
                    for it in (s.get("ozel_uyarilar") or []):  st.markdown(f"⚠️ {it}")

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
        else:
            st.markdown("""
            <div class="pg-empty">
              <div class="pg-empty-icon">💊</div>
              <p>Görsel yükleyin veya ilaç adını yazın;<br>
                 ardından <strong>Analizi Başlat</strong> ile ajanları çalıştırın.</p>
            </div>
            """, unsafe_allow_html=True)

# ═════════════════════════════════════════════
# SEKME 2 — CORPUS
# ═════════════════════════════════════════════
with tab_corpus:
    st.markdown("""
    <div class="pg-about-card" style="margin-bottom:1.25rem">
      <strong>📚 RAG Prospektüs Veritabanı</strong><br><br>
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
            st.success(f"✅ {len(saved)} dosya kaydedildi.")
            if "orchestrator" in st.session_state:
                with st.spinner("ChromaDB güncelleniyor…"):
                    st.session_state.orchestrator.rag_agent.rebuild_index()
                st.success("✅ İndeks güncellendi!")

    with c2:
        st.markdown("#### Mevcut Dosyalar")
        pdfs = list_corpus_pdfs()
        if pdfs:
            for p in pdfs: st.markdown(f"📄 `{p}`")
            if st.button("🔄 İndeksi Yeniden Oluştur"):
                if "orchestrator" in st.session_state:
                    with st.spinner("Yeniden indeksleniyor…"):
                        st.session_state.orchestrator.rag_agent.rebuild_index()
                    st.success("✅ Tamamlandı!")
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
# SEKME 3 — HAKKINDA
# ═════════════════════════════════════════════
with tab_about:
    st.markdown("""
    <div class="pg-about-card">
      <strong style="font-size:1.1rem">Pharma-Guard AI</strong>
      <p style="margin:.5rem 0 1rem;color:#64748b">
        Görüntü işleme ve NLP'yi birleştiren otonom Çoklu Ajan Sistemi (MAS).
      </p>
      <table>
        <tr><th>#</th><th>Ajan</th><th>Model</th><th>Görev</th></tr>
        <tr><td>1</td><td>👁️ Vision Scanner</td><td>LLaVA (Groq) + Gemini Vision</td><td>Görselden OCR & JSON</td></tr>
        <tr><td>2</td><td>📚 RAG Specialist</td><td>ChromaDB + Sentence-T.</td><td>Prospektüs araması</td></tr>
        <tr><td>3</td><td>🔍 Fact-Checker</td><td>Kural tabanlı</td><td>Veri uyuşmazlığı tespiti</td></tr>
        <tr><td>4</td><td>🛡️ Safety Auditor</td><td>Llama-3-70B (Groq)</td><td>Güvenlik & yan etki</td></tr>
        <tr><td>5</td><td>🏭 Corporate Analyst</td><td>Gemini 2.0 Flash</td><td>Firma araştırması</td></tr>
        <tr><td>6</td><td>📝 Report Synthesizer</td><td>Gemini 2.0 Flash</td><td>Türkçe rapor sentezi</td></tr>
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
    st.markdown("**GitHub:** [cemevecen/medic](https://github.com/cemevecen/medic) &nbsp;|&nbsp; "
                "**Lisans:** MIT &nbsp;|&nbsp; **Sürüm:** 1.0.0")
    st.caption("⚕️ Bu araç tıbbi tavsiye niteliği taşımaz. Tanı ve tedavi için hekime başvurun.")
