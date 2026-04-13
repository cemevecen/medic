# WikiPharma

> **Yapay zeka destekli ilaç kutusu analizi ve bilgi paneli** — görüntü / PDF / metin girişi, çoklu ajan orkestrasyonu ve yerel prospektüs (RAG) ile doğrulama.

[![Canlı uygulama](https://img.shields.io/badge/Canlı-medicalsearch.streamlit.app-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://medicalsearch.streamlit.app/)
[![Kaynak kod](https://img.shields.io/badge/GitHub-cemevecen%2Fmedic-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/cemevecen/medic)
[![Gemini](https://img.shields.io/badge/Gemini-Google_AI-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![Groq](https://img.shields.io/badge/Groq-Llama%20%2B%20JSON-F55036?style=for-the-badge)](https://groq.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-8B5CF6?style=for-the-badge)](https://www.trychroma.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**Bağlantılar:** [medicalsearch.streamlit.app](https://medicalsearch.streamlit.app/) · [github.com/cemevecen/medic](https://github.com/cemevecen/medic)

---

## Ne yapar?

WikiPharma; ilaç kutusu fotoğrafı, prospektüs PDF’i veya ilaç adı ile **kimlik, güvenlik ve tutarlılık** odaklı bir özet üretir. Yerel `data/corpus/` altındaki PDF’ler indekslenir; etken madde ve dozaj gibi alanlar **RAG + kural tabanlı Fact-Checker** ile karşılaştırılır. Bu bir tanı/tedavi aracı değildir; çıktılar bilgilendirme amaçlıdır.

---

## Arayüz sekmeleri

| Sekme | İçerik |
|--------|--------|
| **İlaç Analizi** | Görsel / PDF / metin → `PharmaGuardOrchestrator` ile ajan zinciri, Markdown rapor ve indirilebilir PDF. |
| **FDA Arşivi** | OpenFDA + Wikidata tabanlı gerçek kayıt sorgusu; özetler Groq ile Türkçeleştirilir. Onayı olmayan ürünler arşivde görünmeyebilir. |
| **İlaç Fiyatları** | Birleştirilmiş referans fiyat listesi (`referans_ilac_fiyat.py`, `data/*.xlsx`). |
| **Prospektüs Yönetimi** | PDF yükleme, ChromaDB indeks yenileme. |
| **Hakkında** | Güncel model zincirleri, API durumu, sürüm (`PHARMA_GUARD_VERSION`). |

---

## Çoklu ajan mimarisi (özet)

Uygulama içi **Hakkında** sekmesiyle uyumlu güncel tablo:

| # | Ajan | Teknoloji | Görev |
|---|------|-----------|--------|
| 1 | Vision Scanner | Groq görüntü (Llama 4 zinciri) → Gemini görüntü yedeği → Tesseract OCR → Groq metin | Kutu / PDF’ten yapılandırılmış JSON |
| 2 | RAG Specialist | ChromaDB + LangChain + HuggingFaceEmbeddings | Yerel prospektüs semantik arama |
| 3 | Fact-Checker | Kural tabanlı Python | Görsel–RAG tutarlılığı |
| 4 | Safety Auditor | Groq (Llama 3.3 / 3.1 zinciri, JSON) | Yan etki, etkileşim, alarm |
| 5 | Corporate Analyst | Groq (aynı metin zinciri) | Firma / menşe özeti |
| 6 | Report Synthesizer | Önce Groq; gerekirse Gemini | Türkçe Markdown rapor |

**Not:** Eski dokümantasyondaki yalnızca “LLaVA + Groq” veya “yalnızca Gemini 2.0 orkestra” anlatımları güncel değildir. Groq tarafında LLaVA kullanımı kapatılmıştır; görüntü için Llama 4 tabanlı modeller ve yedek Gemini kullanılır.

---

## Teknoloji katmanları

| Katman | Bileşen | Rol |
|--------|---------|-----|
| Arayüz | Streamlit (`app.py`) | Sekmeler, oturum, ilerleme, rapor indirme |
| Orkestrasyon | `PharmaGuardOrchestrator` (`agents.py`) | Ajan sırası, paralel güvenlik / firma, sürüm ile önbellek tutarlılığı |
| Görüntü | Groq vision, Gemini vision, PIL, pyzbar, Tesseract | OCR, barkod, QR |
| Metin / JSON | Groq Chat; isteğe bağlı OpenAI-uyumlu API | PDF alan çıkarımı, güvenlik, firma |
| RAG | ChromaDB, LangChain Community, `sentence-transformers` tabanlı embedding | Yerel indeks |
| Dış veri | `real_drug_data.py` (OpenFDA, Wikidata), `its_api.py`, `referans_ilac_fiyat.py` | Arşiv ve liste verileri |
| Rapor | ReportLab (`utils.py`) | PDF çıktı |

---

## Çalışma ve güvenlik ilkeleri

- **Fact-Checker:** Etken madde / dozaj ile RAG ve görsel çıktı çelişirse rapor bloklanabilir veya uyarı üretilir.
- **Dozaj duyarlılığı:** Küçük dozaj farkları bile “veri uyuşmazlığı” sinyali olarak işlenir.
- **Güven puanı ve alarm:** Çıktılar birleşik güven skoru ve KIRMIZI / SARI / YEŞİL alarm bandı ile özetlenir.
- **Sürüm senkronu:** `agents.py` içindeki `PHARMA_GUARD_VERSION` değiştiğinde, uygulama eski oturum sonuçlarını temizleyerek tutarsız metin gösterilmesini engeller.
- **Yasal:** Uygulama tıbbi tavsiye vermez; tanı ve tedavi için hekime başvurun.

---

## Kurulum (yerel)

```bash
git clone https://github.com/cemevecen/medic.git
cd medic
pip install -r requirements.txt
cp .env.example .env
# .env dosyasını düzenleyin
streamlit run app.py
```

### Ortam değişkenleri (`.env`)

| Değişken | Zorunlu | Açıklama |
|----------|---------|----------|
| `GEMINI_API_KEY` | Önerilir | Görüntü/PDF/rapor yedeği ve model zinciri |
| `GROQ_API_KEY` | Önerilir | Görüntü, metin, güvenlik, FDA metni Türkçeleştirme |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | Hayır | PDF/metin için Groq sonrası OpenAI-uyumlu yedek |
| `HF_API_KEY` | Hayır | Hugging Face token (gerekirse embedding indirimi için) |
| `ECZANEAPI_API_KEY` | Hayır | Nöbetçi eczane iframe sayımı (`eczaneapi.com`) |

ITS API anahtarı arayüzde **Hakkında → ITS API** alanından oturuma yazılabilir; üretimde `st.secrets` veya ortam değişkeni tercih edin.

---

## Streamlit Cloud

1. Repo: [cemevecen/medic](https://github.com/cemevecen/medic), dal: **`main`**, ana dosya: **`app.py`**.
2. **Settings → Secrets** içinde en azından:

```toml
GEMINI_API_KEY = "…"
GROQ_API_KEY = "…"
```

İhtiyaca göre: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `ECZANEAPI_API_KEY`, `HF_API_KEY`.

3. Dağıtım sonrası uygulama örneği: [medicalsearch.streamlit.app](https://medicalsearch.streamlit.app/). Güncelleme görünmüyorsa Streamlit panosunda **Reboot app** / **Redeploy** ve tarayıcıda sert yenileme deneyin.

---

## Veri dosyaları (fiyat sekmesi)

**İlaç Fiyatları** sekmesinin dolması için `data/referans_bazli_ilac_fiyat_listesi.xlsx` ve/veya `data/ilac_fiyat_web_listesi.xlsx` dosyalarının mevcut olması gerekir (ayrıntı: `referans_ilac_fiyat.py`).

---

## Proje yapısı (özet)

```
medic/
├── app.py                 # Streamlit arayüzü
├── agents.py              # Ajanlar + orkestratör + PHARMA_GUARD_VERSION
├── utils.py               # PDF rapor, görüntü yardımcıları
├── real_drug_data.py      # FDA / Wikidata + Türkçe çeviri
├── its_api.py             # İlaç Takip Sistemi (ITS) istemcisi
├── referans_ilac_fiyat.py # Birleşik fiyat DataFrame
├── gemini_models.py       # Gemini model zinciri
├── openai_compat.py       # OpenAI-uyumlu istemci
├── requirements.txt
├── .env.example
├── data/corpus/           # RAG PDF’leri
└── .streamlit/config.toml # Tema
```

---

## Lisans

MIT — ayrıntılar için [LICENSE](LICENSE).
