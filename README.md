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

WikiPharma; ilaç kutusu fotoğrafı, prospektüs PDF’i veya ilaç adı ile **kimlik, güvenlik ve tutarlılık** odaklı bir özet üretir. Prospektüs PDF’leri corpus dizinine kaydedilir (varsayılan `data/corpus/`; isteğe bağlı `MEDIC_CORPUS_DIR`), ChromaDB’de indekslenir; etken madde ve dozaj gibi alanlar **RAG + kural tabanlı Fact-Checker** ile karşılaştırılır. Bu bir tanı/tedavi aracı değildir; çıktılar bilgilendirme amaçlıdır.

---

## Arayüz sekmeleri

| Sekme | İçerik |
|--------|--------|
| **İlaç Analizi** | Görsel / PDF / metin → `PharmaGuardOrchestrator` ile ajan zinciri, Markdown rapor ve indirilebilir PDF. |
| **FDA Arşivi** | OpenFDA + Wikidata tabanlı gerçek kayıt sorgusu; özetler Groq ile Türkçeleştirilir. Onayı olmayan ürünler arşivde görünmeyebilir. |
| **İlaç Fiyatları** | Birleştirilmiş referans fiyat listesi (`referans_ilac_fiyat.py`, `data/*.xlsx`). Filtrelenmiş tüm satırlar tabloda gösterilir; uzun listelerde kaydırma tablo kutusunun içindedir. |
| **Fihrist** | Yerel `ilacrehberi_fihrist.xlsx` ile A–Z ilaç listesi; KT/KUB ve ilaç adı bağlantıları Google aramasına gider. Uygulama içi kaynak satırında [referans Google Sheets](https://docs.google.com/spreadsheets/d/13Hd8k4zVylcRSGB9FJpTpFqBUJ7FGnytKxvAV-TIWaY/edit?gid=0#gid=0) ve [ilacrehberi.com fihrist](https://www.ilacrehberi.com/ilac-fihrist/) verilir. |
| **Prospektüs Yönetimi** | PDF yükleme; dosyalar üzerine yazılmadan kaydedilir, yalnızca kullanıcı **Sil** ile kaldırılır. **İndeksi yenile** yalnızca Chroma vektör veritabanını günceller, PDF’leri silmez. |
| **Hakkında** | Güncel model zincirleri, API durumu, sürüm (`PHARMA_GUARD_VERSION`), RAG dosya sayısı. |

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
| `MEDIC_CORPUS_DIR` | Hayır | Prospektüs PDF’lerinin yazılacağı kalıcı dizin (Streamlit Cloud / Docker’da volume yolu); boşsa `data/corpus` kullanılır |

ITS API anahtarı arayüzde **Hakkında → ITS API** alanından oturuma yazılabilir; üretimde `st.secrets` veya ortam değişkeni tercih edin.

---

## Streamlit Cloud

1. Repo: [cemevecen/medic](https://github.com/cemevecen/medic), dal: **`main`**, ana dosya: **`app.py`**.
2. **Settings → Secrets** içinde en azından:

```toml
GEMINI_API_KEY = "…"
GROQ_API_KEY = "…"
```

İhtiyaca göre: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `ECZANEAPI_API_KEY`, `HF_API_KEY`, `MEDIC_CORPUS_DIR` (prospektüs PDF’lerinin dağıtım örneği yeniden başlatıldığında da kalması için harici/kalıcı bir yol).

3. Dağıtım sonrası uygulama örneği: [medicalsearch.streamlit.app](https://medicalsearch.streamlit.app/). Güncelleme görünmüyorsa Streamlit panosunda **Reboot app** / **Redeploy** ve tarayıcıda sert yenileme deneyin.

---

## Veri dosyaları

### İlaç fiyatları

**İlaç Fiyatları** sekmesinin dolması için `data/referans_bazli_ilac_fiyat_listesi.xlsx` ve/veya `data/ilac_fiyat_web_listesi.xlsx` dosyalarının mevcut olması gerekir (ayrıntı: `referans_ilac_fiyat.py`). İsteğe bağlı olarak `recete_haber` ile birleştirilen ek kaynaklar da kullanılır.

### Fihrist (A–Z liste)

**Fihrist** sekmesi `data/ilacrehberi_fihrist.xlsx` (veya Masaüstündeki aynı adda dosya) okur. Dosyayı üretmek için:

```bash
python scripts/export_ilacrehberi_fihrist_xlsx.py -o data/ilacrehberi_fihrist.xlsx
```

Referans düzen için uygulamadaki kaynak linklerine bakın; örnek eşleme tablosu: [Google Sheets — İlaç A-Z fihrist](https://docs.google.com/spreadsheets/d/13Hd8k4zVylcRSGB9FJpTpFqBUJ7FGnytKxvAV-TIWaY/edit?gid=0#gid=0).

Yeşil / kırmızı / mor / turuncu reçete, takibi zorunlu, reçetesiz ve geri çekilen ilaç listelerini tek XLSX’te (sayfa başına bir sheet) indirmek için:

```bash
python scripts/export_ilacrehberi_recete_listeleri_xlsx.py
```

Varsayılan çıktı: Masaüstünde `ilacrehberi_ilac_listeleri.xlsx`. `-o yol.xlsx` ile değiştirilebilir.

### Prospektüs (RAG)

Yüklü PDF’ler `data/corpus/` altında tutulur (`MEDIC_CORPUS_DIR` ile özelleştirilebilir). İndeks `data/chroma_db/` altında tutulur; indeks yenileme bu klasörü yeniden oluşturur, PDF dosyalarını silmez.

---

## Proje yapısı (özet)

```
medic/
├── app.py                 # Streamlit arayüzü
├── agents.py              # Ajanlar + orkestratör + PHARMA_GUARD_VERSION
├── utils.py               # PDF rapor, corpus yardımcıları (kaydet / listele / sil)
├── real_drug_data.py      # FDA / Wikidata + Türkçe çeviri
├── its_api.py             # İlaç Takip Sistemi (ITS) istemcisi
├── referans_ilac_fiyat.py # Birleşik fiyat DataFrame
├── gemini_models.py       # Gemini model zinciri
├── openai_compat.py       # OpenAI-uyumlu istemci
├── scripts/
│   ├── export_ilacrehberi_fihrist_xlsx.py       # ilacrehberi.com A–Z fihrist → XLSX
│   └── export_ilacrehberi_recete_listeleri_xlsx.py  # reçete/liste sayfaları → çok sayfalı XLSX
├── requirements.txt
├── .env.example
├── data/corpus/           # RAG PDF’leri (MEDIC_CORPUS_DIR ile değiştirilebilir)
├── data/chroma_db/        # Chroma vektör indeksi (.gitignore)
└── .streamlit/config.toml # Tema
```

---

## Lisans

MIT — ayrıntılar için [LICENSE](LICENSE).
