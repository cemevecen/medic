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
# ÖZEL CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    .main-header {
        background: linear-gradient(135deg, #1A3A5C 0%, #0078D4 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.5rem;
    }
    .main-header h1 { color: white; margin: 0; font-size: 2rem; }
    .main-header p  { color: #cce4ff; margin: 0.3rem 0 0; font-size: 1rem; }

    .alarm-red    { background:#fdecea; border-left:5px solid #C0392B; padding:12px 16px; border-radius:6px; }
    .alarm-yellow { background:#fef9e7; border-left:5px solid #F39C12; padding:12px 16px; border-radius:6px; }
    .alarm-green  { background:#eafaf1; border-left:5px solid #27AE60; padding:12px 16px; border-radius:6px; }
    .alarm-unknown{ background:#f4f4f4; border-left:5px solid #95a5a6; padding:12px 16px; border-radius:6px; }

    .metric-card {
        background: #f5f8fa;
        border: 1px solid #dce3ea;
        border-radius: 10px;
        padding: 14px 18px;
        text-align: center;
    }
    .metric-card h3 { margin:0; font-size:1.6rem; color:#1A3A5C; }
    .metric-card p  { margin:0; font-size:0.8rem; color:#7f8c8d; }

    .step-badge {
        display:inline-block;
        background:#0078D4;
        color:white;
        border-radius:50%;
        width:26px; height:26px;
        text-align:center; line-height:26px;
        font-weight:bold; font-size:0.85rem;
        margin-right:8px;
    }
    .stProgress > div > div { background-color: #0078D4 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# BAŞLIK
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="main-header">
        <h1>💊 Pharma-Guard AI</h1>
        <p>Yapay Zeka Destekli Akıllı İlaç Denetçisi &nbsp;|&nbsp;
           Gemini · LLaVA · Llama-3 · RAG (ChromaDB)</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# SIDEBAR — API DURUM PANELİ
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Sistem Durumu")

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    groq_key = os.getenv("GROQ_API_KEY", "")

    st.markdown(
        f"{'✅' if gemini_key else '❌'} **Gemini API** "
        f"{'Bağlı' if gemini_key else '— .env dosyasına ekleyin'}"
    )
    st.markdown(
        f"{'✅' if groq_key else '❌'} **Groq API (LLaVA + Llama-3)** "
        f"{'Bağlı' if groq_key else '— .env dosyasına ekleyin'}"
    )

    pdf_list = list_corpus_pdfs()
    st.markdown(f"📚 **RAG Corpus:** {len(pdf_list)} prospektüs")
    if pdf_list:
        with st.expander("Yüklü Prospektüsler", expanded=False):
            for f in pdf_list:
                st.markdown(f"- `{f}`")
    else:
        st.caption("Corpus boş. Sol panelden PDF yükleyin.")

    st.markdown("---")
    st.markdown("### 📖 Sistem Hakkında")
    st.caption(
        "Pharma-Guard AI, ilaç kutularının görselini veya ilaç adını alarak "
        "çoklu yapay zeka ajanı mimarisiyle güvenlik analizi yapar.\n\n"
        "**Ajanlar:**\n"
        "- 👁️ Vision Scanner (LLaVA)\n"
        "- 📚 RAG Specialist (ChromaDB)\n"
        "- 🔍 Fact-Checker\n"
        "- 🛡️ Safety Auditor (Llama-3)\n"
        "- 🏭 Corporate Analyst (Gemini)\n"
        "- 📝 Report Synthesizer (Gemini)\n"
    )
    st.markdown("---")
    st.caption("⚕️ Bu araç tıbbi tavsiye niteliği taşımaz.")

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
        st.markdown("#### 📥 Giriş Yöntemi")

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
        st.markdown("#### 📊 Analiz Sonuçları")

        if analyze_btn:
            # Session state'i temizle
            for k in ["analysis_result", "report_pdf"]:
                if k in st.session_state:
                    del st.session_state[k]

            progress_placeholder = st.empty()
            status_placeholder = st.empty()

            # Progress callback
            progress_bar = progress_placeholder.progress(0)
            steps = {
                1: "👁️ Vision Scanner çalışıyor...",
                2: "📚 RAG veritabanı taranıyor...",
                3: "🔍 Fact-Checker devreye giriyor...",
                4: "🛡️ Safety Auditor analiz yapıyor...",
                5: "🏭 Corporate Analyst araştırıyor...",
                6: "📝 Rapor sentezleniyor...",
                7: "✅ Analiz tamamlandı!",
            }

            def update_progress(step: int, msg: str):
                progress_bar.progress(step / 7)
                status_placeholder.info(msg)

            # Orkestratörü başlat ve çalıştır
            with st.spinner("Pharma-Guard ajanları devreye alınıyor..."):
                try:
                    from agents import PharmaGuardOrchestrator

                    # Orkestratör önbelleği (her seferinde yeniden başlatmak pahalı)
                    if "orchestrator" not in st.session_state:
                        st.session_state.orchestrator = PharmaGuardOrchestrator()

                    orch = st.session_state.orchestrator

                    result = orch.run(
                        image=image_obj,
                        drug_name_text=drug_name_input,
                        progress_callback=update_progress,
                    )

                    st.session_state.analysis_result = result

                    # PDF oluştur
                    drug_display = (
                        result["vision"].get("ticari_ad") or drug_name_input or "İlaç"
                    )
                    pdf_bytes = generate_pdf_report(
                        report_markdown=result["report"],
                        drug_name=drug_display,
                        alarm_level=result["alarm"],
                        avg_confidence=result["avg_confidence"],
                        vision_data=result["vision"],
                    )
                    st.session_state.report_pdf = pdf_bytes

                except Exception as e:
                    status_placeholder.error(f"❌ Analiz sırasında hata oluştu: {str(e)}")
                    st.exception(e)

            progress_placeholder.empty()
            status_placeholder.empty()

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

            # ── Metrik Kartları ──
            m1, m2, m3 = st.columns(3)
            with m1:
                confidence = result.get("avg_confidence", 0)
                conf_color = "#27AE60" if confidence >= 8 else "#F39C12" if confidence >= 5 else "#C0392B"
                st.markdown(
                    f'<div class="metric-card"><h3 style="color:{conf_color}">'
                    f'{confidence:.1f}<span style="font-size:1rem">/10</span></h3>'
                    f"<p>Güven Puanı</p></div>",
                    unsafe_allow_html=True,
                )
            with m2:
                rag_count = len(result.get("rag_results", []))
                st.markdown(
                    f'<div class="metric-card"><h3>{rag_count}</h3>'
                    f"<p>RAG Sonucu</p></div>",
                    unsafe_allow_html=True,
                )
            with m3:
                fc = result.get("fact_check", {})
                fc_ok = not fc.get("uyusmazlik", False)
                fc_icon = "✅" if fc_ok else "⛔"
                st.markdown(
                    f'<div class="metric-card"><h3>{fc_icon}</h3>'
                    f"<p>Fact-Check</p></div>",
                    unsafe_allow_html=True,
                )

            st.markdown("")

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
                        label="📥 PDF Raporu İndir",
                        data=st.session_state.report_pdf,
                        file_name=filename,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                    )

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
                <div style="text-align:center; padding:3rem 1rem; color:#95a5a6;">
                    <div style="font-size:3rem">💊</div>
                    <p>İlaç görseli yükleyin veya ilaç adını yazın,<br>
                    ardından <b>Analizi Başlat</b> butonuna tıklayın.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ═══════════════════════════════════════════════════════════════════════════
# SEKME 2: PROSPEKTÜS YÖNETİMİ
# ═══════════════════════════════════════════════════════════════════════════

with tab_corpus:
    st.markdown("### 📚 RAG Prospektüs Veritabanı")
    st.info(
        "RAG sisteminin doğru çalışması için ilaç prospektüslerini (PDF) buraya yükleyin. "
        "TİTCK veya FDA'nın resmi prospektüs belgelerini kullanmanız önerilir."
    )

    col_upload, col_list = st.columns([1, 1])

    with col_upload:
        st.markdown("#### Prospektüs Ekle")
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
            if "orchestrator" in st.session_state:
                with st.spinner("ChromaDB indeksi güncelleniyor..."):
                    st.session_state.orchestrator.rag_agent.rebuild_index()
                st.success("✅ RAG indeksi güncellendi!")

    with col_list:
        st.markdown("#### Mevcut Prospektüsler")
        pdfs = list_corpus_pdfs()
        if pdfs:
            for pdf in pdfs:
                st.markdown(f"📄 `{pdf}`")
        else:
            st.warning("Henüz prospektüs yüklenmedi.")

        if pdfs and st.button("🔄 İndeksi Yeniden Oluştur"):
            if "orchestrator" in st.session_state:
                with st.spinner("Lütfen bekleyin..."):
                    st.session_state.orchestrator.rag_agent.rebuild_index()
                st.success("✅ İndeks yeniden oluşturuldu!")
            else:
                st.warning("Lütfen önce bir analiz başlatın (Orkestratörü yüklemek için).")

    st.markdown("---")
    st.markdown("#### 💡 Nereden Prospektüs Bulabilirim?")
    st.markdown(
        """
        - **TİTCK (Türkiye İlaç ve Tıbbi Cihaz Kurumu):** titck.gov.tr → Ürün Bilgisi
        - **FDA (ABD):** drugs@FDA veya DailyMed veri tabanı
        - **EMA (Avrupa):** ema.europa.eu → Product information
        - İlaç kutusunun içindeki kağıt prospektüsü tarayarak PDF'e dönüştürebilirsiniz.
        """
    )

# ═══════════════════════════════════════════════════════════════════════════
# SEKME 3: HAKKINDA
# ═══════════════════════════════════════════════════════════════════════════

with tab_about:
    st.markdown("### ℹ️ Pharma-Guard AI Hakkında")

    st.markdown(
        """
        **Pharma-Guard AI**, görüntü işleme (Computer Vision) ve doğal dil işleme (NLP)
        teknolojilerini birleştirerek toplum sağlığına katkı sunmak amacıyla geliştirilmiş
        otonom bir **Çoklu Ajan Sistemi (Multi-Agent System)**'dir.

        #### 🤖 Ajan Mimarisi
        | Ajan | Model | Görev |
        |---|---|---|
        | 👁️ Vision Scanner | LLaVA (Groq) + Gemini Vision | İlaç görselinden OCR ve veri çıkarımı |
        | 📚 RAG Specialist | ChromaDB + Sentence-Transformers | Yerel prospektüs veritabanı araması |
        | 🔍 Fact-Checker | Kural Tabanlı | Veri tutarsızlığı tespiti |
        | 🛡️ Safety Auditor | Llama-3-70B (Groq) | Güvenlik ve yan etki analizi |
        | 🏭 Corporate Analyst | Gemini 2.0 Flash | Firma ve sertifika araştırması |
        | 📝 Report Synthesizer | Gemini 2.0 Flash | Nihai rapor sentezi |

        #### 🔄 İş Akışı
        1. Kullanıcı ilaç görseli veya adı girer
        2. Vision Scanner görselden yapılandırılmış veri çıkarır
        3. RAG Specialist yerel prospektüs veritabanını sorgular
        4. Fact-Checker veri tutarlılığını kontrol eder
        5. Safety Auditor güvenlik analizi yapar
        6. Corporate Analyst üretici firma raporlar
        7. Report Synthesizer tüm veriyi birleştirip rapor üretir
        8. Kullanıcıya Markdown + indirilebilir PDF sunulur

        #### ⚕️ Yasal Uyarı
        Bu sistem yalnızca **bilgilendirme amaçlıdır**. Sağlık kararları için
        mutlaka lisanslı bir hekim veya eczacıya başvurun.
        Pharma-Guard AI tıbbi tavsiye niteliği taşımaz.
        """
    )

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Geliştirici:** Yapay Zeka Uygulamaları Dersi Projesi")
        st.markdown("**Sürüm:** 1.0.0")
    with col2:
        st.markdown("**Lisans:** MIT")
        st.markdown("**GitHub:** [cemevecen/medic](https://github.com/cemevecen/medic)")
