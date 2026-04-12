# 💊 Pharma-Guard AI

> **Yapay Zeka Destekli Akıllı İlaç Denetçisi**  
> Görüntü işleme ve NLP teknolojilerini birleştiren otonom Çoklu Ajan Sistemi (Multi-Agent System)

[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Gemini](https://img.shields.io/badge/Gemini_2.0-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![Groq](https://img.shields.io/badge/Groq_LLaVA%20%2B%20Llama3-F55036?style=for-the-badge)](https://groq.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-8B5CF6?style=for-the-badge)](https://www.trychroma.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

---

## 🎯 Proje Vizyonu

Pharma-Guard AI; ilaç kutularının fotoğrafını veya ilaç adını alarak **5 otonom yapay zeka ajanı** aracılığıyla kapsamlı bir güvenlik ve kimlik analizi yapan, **RAG (Retrieval-Augmented Generation)** teknolojisiyle yerel prospektüs veritabanından gerçek zamanlı doğrulama gerçekleştiren bir sistemdir.

Sistem sadece bir bilgi arama motoru değil; **halüsinasyon engeli**, **veri uyuşmazlığı alarmı** ve **güven puanı** mekanizmalarıyla kendi verisini denetleyen profesyonel bir asistan mimarisidir.

---

## 🤖 Ajan Mimarisi

| # | Ajan | Model | Görev |
|---|------|-------|-------|
| 1 | 👁️ **Vision Scanner** | LLaVA v1.5 (Groq) → Gemini Vision (fallback) | Görselden OCR — ticari ad, etken madde, dozaj, form, barkod |
| 2 | 📚 **RAG Specialist** | ChromaDB + Multilingual Sentence Transformers | Yerel PDF prospektüs veritabanında semantik arama |
| 3 | 🔍 **Fact-Checker** | Kural Tabanlı | Dozaj ve etken madde uyuşmazlığı tespiti |
| 4 | 🛡️ **Safety Auditor** | Llama-3-70B (Groq) | Yan etki, etkileşim, kontrendikasyon analizi |
| 5 | 🏭 **Corporate Analyst** | Gemini 2.0 Flash | Üretici firma, sertifika ve menşe bilgisi |
| 6 | 📝 **Report Synthesizer** | Gemini 2.0 Flash | Tüm ajan çıktılarını birleştirip Türkçe rapor üretimi |

---

## 🔄 İş Akışı

```
Kullanıcı (Görsel / İlaç Adı)
        │
        ▼
┌─────────────────┐
│ Vision Scanner  │ ──── Görsel → JSON (ticari ad, etken, dozaj...)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ RAG Specialist  │ ──── ChromaDB → Prospektüs pasajları
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Fact-Checker   │ ──── VERİ UYUŞMAZLIĞI? → BLOK / DEVAM
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────────┐
│ Safety │ │  Corporate   │
│Auditor │ │  Analyst     │
└────┬───┘ └──────┬───────┘
     │             │
     └──────┬──────┘
            ▼
  ┌──────────────────┐
  │ Report Synthesizer│ ──── Markdown + PDF Rapor
  └──────────────────┘
```

---

## 🛠️ Teknoloji Yığını

| Katman | Teknoloji | Rol |
|--------|-----------|-----|
| Ana Orkestra | Gemini 2.0 Flash | Karar mekanizması ve rapor sentezi |
| Görüntü İşleme | LLaVA v1.5 (Groq) | İlaç kutusu OCR ve form tanıma |
| Hızlı Analiz | Llama-3-70B (Groq) | JSON yapılandırma ve güvenlik analizi |
| Bilgi Kaynağı | ChromaDB + LangChain | RAG vektör veritabanı |
| Embedding | sentence-transformers (multilingual) | Semantik arama |
| Arayüz | Streamlit | Kullanıcı paneli |
| Raporlama | ReportLab | İndirilebilir PDF çıktısı |

---

## 📁 Dosya Yapısı

```
medic/
├── app.py              # Streamlit arayüzü (ana giriş noktası)
├── agents.py           # 5 ajan + Fact-Checker + Orkestratör
├── utils.py            # Görüntü işleme, PDF rapor, yardımcı fonksiyonlar
├── requirements.txt    # Python bağımlılıkları
├── .env.example        # API anahtarı şablonu
└── data/
    └── corpus/         # RAG için PDF prospektüsler (buraya ekleyin)
```

---

## 🚀 Kurulum ve Çalıştırma

### 1. Repoyu Klonlayın

```bash
git clone https://github.com/cemevecen/medic.git
cd medic
```

### 2. Bağımlılıkları Yükleyin

```bash
pip install -r requirements.txt
```

### 3. API Anahtarlarını Ayarlayın

```bash
cp .env.example .env
```

`.env` dosyasını açıp anahtarları doldurun:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

| Anahtar | Nereden Alınır |
|---------|---------------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `GROQ_API_KEY` | [Groq Console](https://console.groq.com/keys) |

### 4. Prospektüs Ekleyin (Opsiyonel ama Önerilir)

`data/corpus/` klasörüne ilaç PDF prospektüslerini ekleyin. İlk çalıştırmada ChromaDB indeksi otomatik oluşturulur.

> **Kaynak önerileri:** TİTCK (titck.gov.tr), FDA DailyMed, EMA

### 5. Uygulamayı Başlatın

```bash
streamlit run app.py
```

---

## ☁️ Streamlit Cloud Deployment

1. GitHub reposunu Streamlit Cloud'a bağlayın
2. **Main file path:** `app.py`
3. **Settings → Secrets** bölümüne ekleyin:

```toml
GEMINI_API_KEY = "your_gemini_api_key"
GROQ_API_KEY = "your_groq_api_key"
```

---

## 🔒 Güvenlik Mekanizmaları

| Mekanizma | Açıklama |
|-----------|----------|
| **Halüsinasyon Engeli** | Etken madde ile prospektüs verisi eşleşmezse rapor bloklanır |
| **VERİ UYUŞMAZLIĞI Alarmı** | 1 mg dozaj farkı bile alarm tetikler |
| **Güven Puanı** | Her bilgi parçası 1-10 arası puanlanır; ortalama < 8 ise uyarı eklenir |
| **Görüntü Kalite Kontrolü** | Okunabilirlik skoru < 5 ise kullanıcı daha net fotoğraf çekmesi için uyarılır |
| **KIRMIZI/SARI/YEŞİL Alarm** | Hamilelik, ölümcül etkileşim gibi kritik riskler kırmızı alarm ile işaretlenir |

---

## 📊 Örnek Çıktı Raporu

```
## 1. İlaç Kimlik Özeti
Ticari Ad: Augmentin 1000 mg  [Güven: 9/10]
Etken Madde: Amoksisilin + Klavulanik Asit

## 2. Kullanım Amacı (Endikasyonlar)
Bakteriyel enfeksiyonların tedavisinde kullanılır...

## 3. Kritik Uyarılar ve Yan Etkiler
🔴 Penisilin alerjisi olanlarda KESİNLİKLE kullanılmaz!

## 4. Etken Madde ve Üretici Detayları
Üretici: GlaxoSmithKline | TİTCK Onaylı ✓

## 5. RAG Kaynakça
- augmentin_prospektus.pdf (s.3): "...amoksisilin trihidrat..."
```

---

## ⚕️ Yasal Uyarı

> Bu sistem **yalnızca bilgilendirme amaçlıdır**. Tanı, tedavi veya ilaç değişikliği kararları için mutlaka lisanslı bir hekim veya eczacıya başvurun. Pharma-Guard AI'ın sunduğu bilgiler **tıbbi tavsiye niteliği taşımaz**.

---

## 📄 Lisans

MIT License — Detaylar için [LICENSE](LICENSE) dosyasına bakın.
