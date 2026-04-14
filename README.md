# WikiPharma

Streamlit tabanlı arayüz: ilaç kutusu görüntüsü, prospektüs PDF’i veya serbest metinle çok ajanlı analiz; yerel prospektüs RAG’i ve harici veri kaynakları. **Tıbbi karar desteği değildir.**

[![Canlı](https://img.shields.io/badge/Canlı-medicalsearch.streamlit.app-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://medicalsearch.streamlit.app/)
[![Kaynak](https://img.shields.io/badge/GitHub-cemevecen%2Fmedic-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/cemevecen/medic)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**Uygulama:** https://medicalsearch.streamlit.app/ · **Repo:** https://github.com/cemevecen/medic

---

## Kapsam

- **Girdi:** görüntü, PDF, ilaç adı (metin).
- **Çıktı:** Markdown rapor, ReportLab PDF, sekme içi yapılandırılmış alanlar (güvenlik, firma, benzer ilaç önerileri, liste fiyatı eşlemesi).
- **Yerel RAG:** `data/corpus/` (veya `MEDIC_CORPUS_DIR`) altındaki prospektüs PDF’leri; ChromaDB indeksi `data/chroma_db/`.
- **Doğrulama:** kural tabanlı Fact-Checker (görsel / RAG alanları); çelişkide rapor kısıtlanabilir veya uyarı üretilir.

---

## Sekmeler

| Sekme | İşlev |
|--------|--------|
| **Analiz** | Orkestrasyon (`PharmaGuardOrchestrator`), rapor, PDF indirme, nöbetçi eczane widget’ı. Son arananlar: gerçek aramalar üstte; kalan satırlar fiyat arşivinden rastgele ilaç adı ile doldurulur. |
| **FDA Arşivi** | `real_drug_data.py`: OpenFDA / Wikidata; özet metin Groq ile Türkçeleştirilir. |
| **Fiyatlar** | `referans_ilac_fiyat.py`: birleşik XLSX kaynakları, aranabilir tablo. İlk oturumda bu sekme (ve aşağıdaki veri ağırlıklı sekmeler) açıldığında önbellek ısınırken `st.progress` gösterilir; görünürlük süresi kodda `app.py` → `_PG_WARMUP_MIN_VISIBLE_SEC` (şu an 1,3 s). |
| **Firmalar** | Birleşik fiyat + özellikli liste XLSX’ten `firma → ilaç + kaynak`. Aynı ilk-yükleme progress mantığı. |
| **Özellikli ilaçlar** | `ilacrehberi_ilac_listeleri.xlsx` (Masaüstü / `data/` / `MEDIC_OZELLIKLI_ILAC_XLSX`). Aynı progress mantığı. |
| **Fihrist** | `ilacrehberi_fihrist.xlsx`. Aynı progress mantığı. |
| **Prospektüsler** | PDF yükleme / silme; indeks yenileme yalnızca vektör DB. |
| **Hakkında** | Model zincirleri, API durumu, `PHARMA_GUARD_VERSION`, RAG özet bilgisi. |

Eski `session_state` sekme değerleri (`İlaç Analizi`, `İlaç Fiyatları`, `İlaç firmaları`, `Prospektüs Yönetimi`) uygulama içinde yeni etiketlere (`Analiz`, `Fiyatlar`, `Firmalar`, `Prospektüsler`) eşlenir.

**Analiz ve fiyat metni:** Liste fiyatı tablosu arayüzde ve PDF’de yer alır; rapor Markdown gövdesine ayrı “liste fiyatı” bloğu eklenmez. Eşleme: birleşik tabloda en yüksek benzerlik + marka kökü filtresi; çıktıda tek satır hedeflenir (`referans_ilac_fiyat.lookup_fiyat_liste_for_vision`). Muadil önerileri: `similar_medicines.py` (isteğe bağlı `data/alternatives_catalog.json`, Groq JSON); model satırları etken tutarlılık ve ana ürünle çakışma filtresinden geçer.

---

## Ajanlar

| # | Bileşen | Görev |
|---|---------|--------|
| 1 | Vision Scanner | Görüntü / PDF’ten yapılandırılmış çıktı (Groq vision zinciri, Gemini yedek, OCR). |
| 2 | RAG Specialist | ChromaDB + LangChain + embedding ile prospektüs araması. |
| 3 | Fact-Checker | Görsel ve RAG alanlarının kural tabanlı karşılaştırması. |
| 4 | Safety Auditor | Groq: yan etki, etkileşim, alarm (JSON). |
| 5 | Corporate Analyst | Groq: firma / menşe özeti. |
| 6 | Report Synthesizer | Groq öncelikli, gerekirse Gemini: Türkçe Markdown rapor. |

---

## Yığın

| Katman | Dosya / servis |
|--------|----------------|
| Arayüz | `app.py` |
| Orkestrasyon | `agents.py` → `PharmaGuardOrchestrator` |
| Görüntü / OCR | Groq, Gemini, Tesseract, pyzbar, PIL |
| RAG | ChromaDB, LangChain, `sentence-transformers` |
| Harici kayıt | `real_drug_data.py` (OpenFDA, Wikidata) |
| Liste fiyatı | `referans_ilac_fiyat.py` |
| Muadil | `similar_medicines.py` |
| PDF | `utils.py` (ReportLab) |
| ITS | `its_api.py` (isteğe bağlı anahtar) |

---

## Güvenlik ve sınırlar

- Çıktılar bilgilendirme amaçlıdır; tanı ve tedavi için hekim/eczacı gerekir.
- Fact-Checker ve alarm seviyesi çelişki / risk sinyali üretir; otomatik onay anlamına gelmez.
- `PHARMA_GUARD_VERSION` değişince oturumdaki eski analiz sonuçları temizlenir (`agents.py`).

---

## Kurulum (yerel)

```bash
git clone https://github.com/cemevecen/medic.git
cd medic
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

### Ortam değişkenleri

| Değişken | Zorunluluk | Kullanım |
|----------|------------|----------|
| `GEMINI_API_KEY` | Önerilir | Görüntü/PDF/rapor yedekleri, Gemini zinciri |
| `GROQ_API_KEY` | Önerilir | Görüntü, metin, güvenlik, çeviri |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | Hayır | OpenAI uyumlu yedek |
| `HF_API_KEY` | Hayır | Embedding indirimi |
| `ECZANEAPI_API_KEY` | Hayır | Nöbetçi eczane (`eczaneapi.com`) |
| `MEDIC_CORPUS_DIR` | Hayır | Prospektüs PDF dizini (varsayılan `data/corpus`) |
| `MEDIC_OZELLIKLI_ILAC_XLSX` | Hayır | Özellikli liste XLSX tam yolu |

ITS anahtarı: **Hakkında** ekranından oturuma yazılabilir; üretimde `st.secrets` veya ortam değişkeni tercih edilir.

---

## Streamlit Cloud

- Repo: `cemevecen/medic`, dal `main`, giriş `app.py`.
- **Secrets:** en azından `GEMINI_API_KEY`, `GROQ_API_KEY`. İsteğe bağlı: `OPENAI_*`, `ECZANEAPI_API_KEY`, `HF_API_KEY`, `MEDIC_CORPUS_DIR`.
- Dağıtım: https://medicalsearch.streamlit.app/ — güncelleme yoksa panoda yeniden dağıtım / yeniden başlatma ve tarayıcı önbelleği kontrolü.

---

## Veri dosyaları

**Fiyatlar:** `data/referans_bazli_ilac_fiyat_listesi.xlsx` ve/veya `data/ilac_fiyat_web_listesi.xlsx` (`referans_ilac_fiyat.py`; `recete_haber` ile ek birleşim mümkün).

**Fihrist:** `data/ilacrehberi_fihrist.xlsx` veya üretim:

```bash
python scripts/export_ilacrehberi_fihrist_xlsx.py -o data/ilacrehberi_fihrist.xlsx
```

Referans tablo: [Google Sheets — İlaç A-Z fihrist](https://docs.google.com/spreadsheets/d/13Hd8k4zVylcRSGB9FJpTpFqBUJ7FGnytKxvAV-TIWaY/edit?gid=0#gid=0).

**Özellikli listeler:**

```bash
python scripts/export_ilacrehberi_recete_listeleri_xlsx.py
```

Varsayılan çıktı Masaüstü `ilacrehberi_ilac_listeleri.xlsx`; `-o` ile yol verilir.

**Muadil kataloğu (isteğe bağlı):** `data/alternatives_catalog.json`

---

## Dizin yapısı (özet)

```
medic/
├── app.py
├── agents.py
├── utils.py
├── real_drug_data.py
├── its_api.py
├── referans_ilac_fiyat.py
├── similar_medicines.py
├── gemini_models.py
├── openai_compat.py
├── scripts/
│   ├── export_ilacrehberi_fihrist_xlsx.py
│   └── export_ilacrehberi_recete_listeleri_xlsx.py
├── data/corpus/
├── data/alternatives_catalog.json
├── data/chroma_db/
├── requirements.txt
├── .env.example
└── .streamlit/config.toml
```

---

## Lisans

MIT — [LICENSE](LICENSE).
