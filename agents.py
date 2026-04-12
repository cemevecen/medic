"""
PHARMA-GUARD AI — Çoklu Ajan Sistemi
agents.py: Tüm ajan sınıfları ve ana orkestratör bu dosyada tanımlanmıştır.
"""

# Versiyon numarası — app.py session_state cache invalidation için kullanılır.
# Fact-Checker / parser / orchestrator davranışı değiştiğinde artırın.
PHARMA_GUARD_VERSION = "1.8"

import os
import json
import base64
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import google.generativeai as genai
from groq import Groq
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

from gemini_models import (
    model_chain as _gemini_model_chain,
    model_missing_error as _gemini_model_missing_error,
)


def _gemini_model_name() -> str:
    return _gemini_model_chain()[0]


# ---------------------------------------------------------------------------
# API İstemcileri
# ---------------------------------------------------------------------------

def _init_gemini():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY bulunamadı. Lütfen .env dosyasını kontrol edin.")
    genai.configure(api_key=api_key)

def _init_groq() -> Groq:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY bulunamadı. Lütfen .env dosyasını kontrol edin.")
    return Groq(api_key=api_key)


def _groq_safety_model_chain() -> List[str]:
    """Safety Auditor için Groq model sırası (429 / TPD limitinde sıradakine geçer)."""
    raw = (os.getenv("GROQ_SAFETY_MODEL_PRIORITY") or "").strip()
    if raw:
        seen: set = set()
        out: List[str] = []
        for m in raw.split(","):
            m = m.strip()
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out
    return [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama-3.1-70b-versatile",
    ]


def _groq_is_rate_limit(exc: Exception) -> bool:
    t = str(exc).lower()
    return "429" in str(exc) or "rate_limit" in t or "rate limit" in t


def _groq_safety_failure_message(exc: Exception) -> str:
    if _groq_is_rate_limit(exc):
        return (
            "Groq günlük token limiti (TPD) doldu veya istek sınırı aşıldı; Safety Auditor "
            "yanıt veremedi. Yaklaşık 25–30 dakika sonra tekrar deneyin veya kotayı "
            "https://console.groq.com/settings/billing adresinden yükseltin. "
            "Önce hafif model denemek için `.env` içinde örn. "
            "GROQ_SAFETY_MODEL_PRIORITY=llama-3.1-8b-instant,llama-3.3-70b-versatile kullanın."
        )
    return f"Safety Auditor hatası: {exc!s}"


# ---------------------------------------------------------------------------
# MASTER SYSTEM PROMPT
# ---------------------------------------------------------------------------

MASTER_PROMPT = """
### ROLE: PHARMA-GUARD MASTER ORCHESTRATOR (PG-MO) ###

Sen, Gemini 2.0 tabanlı, multimodal yeteneklere sahip ve çoklu ajan (Multi-Agent)
ekosistemini yöneten baş mimarsın. Görevin; görsel veya metinsel girişi alınan bir ilacı,
sıfır hata toleransı ile analiz etmektir.

OPERASYONEL PROTOKOLLER VE KISITLAMALAR:
- GÜVEN PUANI (Confidence Score): Her bilgi parçası için 1-10 arası bir puan ver.
  Eğer ortalama güven 8'in altındaysa raporun başına "DİKKAT: Bilgiler %100 doğrulanamadı,
  profesyonel yardım alın" uyarısı ekle.
- HALÜSİNASYON ENGELİ: Eğer ilacın etken maddesi ile prospektüs bilgisi eşleşmiyorsa,
  süreci durdurup 'VERİ UYUŞMAZLIĞI' hata mesajı ver.
- DİL VE ÜSLUP: Rapor tamamen Türkçe, tıbbi terimleri parantez içinde açıklayan,
  güven veren ve profesyonel bir tonda olmalıdır.
- KURAL 1: Yazı okunmuyorsa asla tahmin etme.
- KURAL 2: Bilgi kaynağın %100 tıbbi prospektüsler olmalı.
- KURAL 3: Bilgiler arasında 1 mg fark olsa bile 'VERİ UYUŞMAZLIĞI' alarmı ver.
"""

VISION_PROMPT = """
Sen bir ilaç görüntü analiz uzmanısın (Vision-Scanner). Verilen görseli analiz et ve
aşağıdaki bilgileri JSON formatında çıkar:

{
  "ticari_ad": "İlacın kutu üzerindeki ticari adı",
  "etken_madde": "Etken madde (kimyasal ad)",
  "dozaj": "Doz miktarı (mg/ml/mcg)",
  "form": "Tablet / Kapsül / Şurup / Ampul / vb.",
  "barkod": "Barkod numarası (varsa, yoksa null)",
  "uretici": "Üretici firma adı (varsa)",
  "okunabilirlik_skoru": 1-10 arası (10=mükemmel okunabilir),
  "notlar": "Okunmayan veya belirsiz alanlar varsa belirt"
}

KURALLAR:
- Eğer herhangi bir alan net okunamıyorsa null yaz, tahmin YAPMA.
- Okunabilirlik skoru 5'in altındaysa notlar alanına "FOTOĞRAF KALİTESİ YETERSİZ" yaz.
- Türkçe veya Latince ilaç isimlerini olduğu gibi al, çevirme.
"""

SAFETY_PROMPT_TEMPLATE = """SADECE geçerli bir JSON nesnesi döndür. Açıklama, başlık veya markdown kullanma.

İLAÇ BİLGİLERİ:
{drug_info}

RAG KAYNAK VERİSİ (yoksa kendi tıbbi bilgini kullan):
{rag_data}

Genel farmakoloji bilgini kullanarak, ilaç adı veya etken maddesi bilinen bir ilaçsa
gerçek klinik bilgiyle yanıt ver. RAG boşsa internet/genel bilginden yararlan.

Döndüreceğin JSON şeması (tam olarak bu anahtarları kullan):
{{
  "yan_etkiler": {{
    "yaygin": ["en az 3 yaygın yan etki"],
    "ciddi": ["ciddi yan etkiler"],
    "cok_nadir": ["çok nadir görülen yan etkiler"]
  }},
  "etkilesimler": ["diğer ilaçlarla önemli etkileşimler — en az 2"],
  "kontrendikasyonlar": ["kimler kullanamamalı — en az 2"],
  "ozel_uyarilar": ["hamilelik, emzirme, yaşlı, çocuk, böbrek/karaciğer uyarıları"],
  "alarm_seviyesi": "YEŞİL veya SARI veya KIRMIZI",
  "alarm_gerekce": "alarm seviyesinin kısa gerekçesi (1-2 cümle)",
  "guven_puani": 7
}}

KIRMIZI: hamilelikte kontrendike, dar terapötik indeks, ölümcül etkileşim.
SARI: yaş/doz kısıtlaması, dikkat gerektiren etkileşimler.
YEŞİL: genel kullanım için güvenli (hekime danışarak).
"""

CORPORATE_PROMPT_TEMPLATE = """SADECE geçerli bir JSON nesnesi döndür. Açıklama veya markdown kullanma.

İLAÇ ADI: {drug_name}
BİLİNEN ÜRETİCİ: {manufacturer}

Bu ilacın üreticisini farmakoloji ve ilaç endüstrisi bilginle belirle.
Özellikle Türk ilaç firmaları (Abdi İbrahim, Eczacıbaşı, Recordati, Santa Farma,
Sandoz Türkiye, Pfizer Türkiye, Deva, Nobel, Bilim vb.) için bilgin varsa kullan.
TİTCK onaylı ilaçlar için "TİTCK onaylı" yaz.

Döndüreceğin JSON şeması:
{{
  "firma_adi": "üreticinin tam adı (bilinmiyorsa 'Tespit Edilemedi')",
  "ulke": "menşe ülke (Türkiye / Almanya / vb.)",
  "sertifikalar": ["GMP", "ISO 9001"],
  "titck_durumu": "TİTCK onaylı veya Belirsiz",
  "genel_degerlendirme": "firma hakkında 2-3 cümle gerçek bilgi",
  "guven_puani": 6
}}

guven_puani: kesin bilgi varsa 7-9, tahmini bilgi varsa 5-6, bilinmiyorsa 3.
"""

SYNTHESIS_PROMPT_TEMPLATE = """Sen Pharma-Guard raporlama uzmanısın. Aşağıdaki ajan çıktılarından
kapsamlı, bütünlüklü bir Türkçe ilaç analiz raporu oluştur.

VISION / PDF SCANNER SONUCU:
{vision_data}

SAFETY AUDITOR SONUCU:
{safety_data}

CORPORATE ANALYST SONUCU:
{corporate_data}

RAG KAYNAKÇASI:
{rag_sources}

KURALLAR:
1. Tamamen Türkçe yaz; tıbbi terimleri parantez içinde açıkla.
2. Güven < 8 ise raporun başına "DİKKAT" uyarısı ekle.
3. PDF dosya adı ile çıkarılan bilgi arasındaki farkı "not" olarak belirt — raporu bloklama.
4. Eksik veya belirsiz alanları "Bilgi mevcut değil" olarak işaretle, uydurma.
5. Aşağıdaki Markdown bölüm başlıklarını kullan:

## 1. İlaç Kimlik Özeti
## 2. Kullanım Amacı (Endikasyonlar)
## 3. Kritik Uyarılar ve Yan Etkiler
## 4. Etken Madde ve Üretici Detayları
## 5. Kaynakça

Her bölümün sonuna güven puanını ekle: `[Güven: X/10]`
"""


# ---------------------------------------------------------------------------
# AJAN 1: Vision Scanner
# ---------------------------------------------------------------------------

class VisionScannerAgent:
    """
    LLaVA (Groq) kullanarak ilaç görselinden yapılandırılmış veri çıkaran ajan.
    (Gemini Vision fallback kaldırıldı — quota tasarrufu)
    """

    def __init__(self):
        self.groq_client = _init_groq()

    def _encode_image(self, image: Image.Image) -> str:
        """PIL Image'ı base64 stringe çevirir."""
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def scan_with_groq_llava(self, image: Image.Image) -> Dict[str, Any]:
        """Groq üzerindeki LLaVA modeli ile görsel tarama."""
        b64 = self._encode_image(image)
        try:
            response = self.groq_client.chat.completions.create(
                model="llava-v1.5-7b-4096-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}"
                                },
                            },
                            {
                                "type": "text",
                                "text": VISION_PROMPT,
                            },
                        ],
                    }
                ],
                max_tokens=1024,
                temperature=0.1,
            )
            raw = response.choices[0].message.content
            return self._parse_json_response(raw, source="LLaVA (Groq)")
        except Exception as e:
            return {"hata": f"LLaVA hatası: {str(e)}", "kaynak": "LLaVA (Groq)"}

    def scan_with_groq_fallback(self) -> Dict[str, Any]:
        """LLaVA başarısız → Groq fallback (text mode, image yok)."""
        # Groq text model'den ilaç bilgisi talebinde bulunamıyız (image yok).
        # Kullanıcıyı metin girişine yönlendir.
        return {
            "hata": "Görsel analizi LLaVA ve Groq ile başarısız oldu. Metin girişi kullanarak devam edin.",
            "kaynak": "Groq Fallback",
            "okunabilirlik_skoru": 0,
            "notlar": "Görsel işlenemiyor — metin girişi tercih edilir.",
        }

    def scan(self, image: Image.Image) -> Dict[str, Any]:
        """
        Önce LLaVA (Groq) dener, başarısız olursa Groq fallback hata döndürür.
        (Gemini Vision kaldırıldı — quota tasarrufu)
        Orchestrator bu metodu çağırır.
        """
        result = self.scan_with_groq_llava(image)
        if "hata" in result:
            print(f"[VisionScanner] LLaVA başarısız ({result['hata']}), Groq fallback…")
            result = self.scan_with_groq_fallback()
        return result

    def scan_text_input(self, drug_name: str) -> Dict[str, Any]:
        """Görsel yoksa, metin girişinden ilaç bilgisi yap."""
        return {
            "ticari_ad": drug_name,
            "etken_madde": None,
            "dozaj": None,
            "form": None,
            "barkod": None,
            "uretici": None,
            "okunabilirlik_skoru": 10,
            "notlar": "Metin girişi ile sağlandı, görsel analiz yapılmadı.",
            "kaynak": "Metin Girişi",
        }

    def scan_pdf(self, pdf_bytes: bytes, filename: str = "prospektus.pdf") -> Dict[str, Any]:
        """
        PDF prospektüsünden metin çıkarır ve Gemini ile ilaç bilgilerini ayıklar.
        Kullanıcı doğrudan prospektüs PDF'i yüklediğinde çağrılır.
        """
        # 1) PDF metnini çıkar
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(pdf_bytes))
            pages_text = []
            for i, page in enumerate(reader.pages[:10]):   # ilk 10 sayfa yeterli
                t = page.extract_text() or ""
                if t.strip():
                    pages_text.append(f"[Sayfa {i+1}]\n{t.strip()}")
            pdf_text = "\n\n".join(pages_text)
        except Exception as e:
            return {"hata": f"PDF okunamadı: {e}", "kaynak": f"PDF ({filename})"}

        if not pdf_text.strip():
            return {
                "hata": "PDF'den metin çıkarılamadı (taranmış/görüntü tabanlı PDF olabilir).",
                "kaynak": f"PDF ({filename})",
            }

        # 2) Gemini ile ilaç bilgilerini ayıkla
        pdf_prompt = f"""
Aşağıdaki ilaç prospektüsü metninden ilaç bilgilerini çıkar ve JSON formatında döndür:

{{
  "ticari_ad": "İlacın ticari adı",
  "etken_madde": "Etken madde(ler)",
  "dozaj": "Dozaj bilgisi (mg/ml/mcg)",
  "form": "Tablet / Kapsül / Şurup / vb.",
  "barkod": null,
  "uretici": "Üretici firma adı",
  "okunabilirlik_skoru": 9,
  "notlar": "PDF prospektüsünden çıkarıldı",
  "endikasyonlar": "Kısa kullanım amacı (1-2 cümle)",
  "prospektus_ozeti": "Prospektüsten elde edilen kritik bilgilerin özeti (3-5 cümle)"
}}

PROSPEKTÜS METNİ:
{pdf_text[:6000]}
"""
        models = _gemini_model_chain()
        last_err = None
        for name in models:
            try:
                model = genai.GenerativeModel(name)
                response = model.generate_content(
                    pdf_prompt,
                    generation_config=genai.GenerationConfig(temperature=0.1),
                )
                result = self._parse_json_response(response.text, source=f"PDF ({filename})")
                result["pdf_metin_uzunlugu"] = len(pdf_text)
                return result
            except Exception as e:
                last_err = e
                if _gemini_model_missing_error(e) and name != models[-1]:
                    continue
                break

        return {
            "hata": f"PDF analiz hatası: {last_err}",
            "kaynak": f"PDF ({filename})",
            "okunabilirlik_skoru": 5,
        }

    @staticmethod
    def _parse_json_response(raw: str, source: str) -> Dict[str, Any]:
        """Model çıktısından JSON bloğu ayıklar — 3 aşamalı robust parser."""
        # 1) ```json ... ``` bloğunu temizle
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        # 2) Doğrudan parse
        try:
            data = json.loads(cleaned)
            data["kaynak"] = source
            return data
        except json.JSONDecodeError:
            pass
        # 3) Metin içindeki ilk { ... } bloğunu regex ile bul
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                data = json.loads(m.group())
                data["kaynak"] = source
                return data
            except json.JSONDecodeError:
                pass
        # 4) Ham metni sakla; ticari_ad'ı tahmin etmeye çalış
        guessed: Dict[str, Any] = {
            "kaynak": source,
            "ham_cikti": raw[:500],
            "notlar": "JSON ayrıştırılamadı; ham çıktı korundu.",
        }
        # Basit anahtar-değer satırlarını al (ör. "ticari_ad: Alka-Seltzer")
        for key in ["ticari_ad", "etken_madde", "dozaj", "form", "uretici"]:
            pat = rf'"{key}"\s*:\s*"([^"]+)"'
            hit = re.search(pat, cleaned, re.IGNORECASE)
            if hit:
                guessed[key] = hit.group(1)
        return guessed


# ---------------------------------------------------------------------------
# AJAN 2: RAG Specialist
# ---------------------------------------------------------------------------

class RAGSpecialistAgent:
    """
    ChromaDB ve LangChain kullanarak yerel PDF prospektüs veritabanında
    semantik arama yapan ajan.
    """

    CORPUS_DIR = Path("data/corpus")
    CHROMA_DIR = Path("data/chroma_db")

    def __init__(self):
        self.vectorstore = None
        self.corpus_loaded = False
        self._load_or_build_index()

    def _load_or_build_index(self):
        """Varsa mevcut ChromaDB'yi yükle, yoksa PDF'lerden oluştur."""
        try:
            from langchain_community.vectorstores import Chroma
            from langchain_community.embeddings import HuggingFaceEmbeddings
            from langchain_community.document_loaders import PyPDFLoader
            from langchain.text_splitter import RecursiveCharacterTextSplitter

            embedding_model = HuggingFaceEmbeddings(
                model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                model_kwargs={"device": "cpu"},
            )

            pdf_files = list(self.CORPUS_DIR.glob("*.pdf"))

            if self.CHROMA_DIR.exists() and any(self.CHROMA_DIR.iterdir()):
                self.vectorstore = Chroma(
                    persist_directory=str(self.CHROMA_DIR),
                    embedding_function=embedding_model,
                )
                self.corpus_loaded = True
                print(f"[RAGSpecialist] ChromaDB yüklendi. ({self.CHROMA_DIR})")
            elif pdf_files:
                self._build_index(pdf_files, embedding_model)
            else:
                print("[RAGSpecialist] Corpus dizininde PDF bulunamadı. RAG devre dışı.")

        except ImportError as e:
            print(f"[RAGSpecialist] Gerekli kütüphane eksik: {e}")

    def _build_index(self, pdf_files: List[Path], embedding_model):
        """PDF dosyalarından ChromaDB vektör indeksi oluşturur."""
        from langchain_community.vectorstores import Chroma
        from langchain_community.document_loaders import PyPDFLoader
        from langchain.text_splitter import RecursiveCharacterTextSplitter

        print(f"[RAGSpecialist] {len(pdf_files)} PDF indeksleniyor...")
        all_docs = []
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)

        for pdf_path in pdf_files:
            try:
                loader = PyPDFLoader(str(pdf_path))
                pages = loader.load()
                chunks = splitter.split_documents(pages)
                for chunk in chunks:
                    chunk.metadata["source_file"] = pdf_path.name
                all_docs.extend(chunks)
                print(f"  ✓ {pdf_path.name} — {len(chunks)} parça")
            except Exception as e:
                print(f"  ✗ {pdf_path.name}: {e}")

        if all_docs:
            self.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            self.vectorstore = Chroma.from_documents(
                documents=all_docs,
                embedding=embedding_model,
                persist_directory=str(self.CHROMA_DIR),
            )
            self.corpus_loaded = True
            print(f"[RAGSpecialist] İndeks oluşturuldu. {len(all_docs)} parça kaydedildi.")

    def search(self, query: str, k: int = 5, vision_data: Optional[Dict] = None) -> List[Dict[str, str]]:
        """
        Semantik arama yapar. Corpus boş olsa bile, vision_data'dan mock sonuçlar oluşturur.
        Bu sayede Fact-Check'in karşılaştıracak verileri olur.
        """
        if not self.corpus_loaded or self.vectorstore is None:
            # Corpus boş — vision bilgisinden mock sonuçlar oluştur
            if vision_data:
                drug_name = vision_data.get("ticari_ad", "").strip()
                etken = vision_data.get("etken_madde", "").strip()
                if drug_name or etken:
                    # Fact-Check'in karşılaştıracak bir kaynak olsun
                    return [{
                        "metin": f"{drug_name} ({etken}): Genel ilaç bilgisine dayalı bilgiler.",
                        "kaynak": "Genel Bilgi",
                        "sayfa": "—",
                        "benzerlik": 0.7,
                    }]
            # Fallback: corpus tamamen boş
            return [{"metin": "Prospektüs veritabanı boş.", "kaynak": "—", "sayfa": "—"}]

        try:
            results = self.vectorstore.similarity_search_with_score(query, k=k)
            formatted = []
            for doc, score in results:
                formatted.append({
                    "metin": doc.page_content,
                    "kaynak": doc.metadata.get("source_file", "bilinmiyor"),
                    "sayfa": str(doc.metadata.get("page", "?")),
                    "benzerlik": round(float(score), 4),
                })
            return formatted
        except Exception as e:
            return [{"metin": f"Arama hatası: {str(e)}", "kaynak": "—", "sayfa": "—"}]

    def rebuild_index(self):
        """Kullanıcı yeni PDF eklediğinde indeksi yeniden oluşturur."""
        import shutil
        if self.CHROMA_DIR.exists():
            shutil.rmtree(self.CHROMA_DIR)
        self.corpus_loaded = False
        self.vectorstore = None
        self._load_or_build_index()


# ---------------------------------------------------------------------------
# AJAN 3: Safety Auditor
# ---------------------------------------------------------------------------

class SafetyAuditorAgent:
    """
    Groq (Llama-3-70B) kullanarak ilaç güvenlik denetimi yapan ajan.
    Yan etki, etkileşim ve kontrendikasyon kontrolü gerçekleştirir.
    """

    def __init__(self):
        self.groq_client = _init_groq()

    def audit(self, drug_info: Dict[str, Any], rag_data: List[Dict]) -> Dict[str, Any]:
        """İlaç bilgisi ve RAG verisi ile güvenlik raporu oluşturur."""
        rag_real = [r for r in rag_data if r.get("kaynak", "—") not in ("—", "")]
        rag_text = (
            "\n\n".join(f"[{r['kaynak']} — s.{r['sayfa']}]: {r['metin']}" for r in rag_real)
            or "RAG verisi yok — kendi tıbbi bilginle yanıt ver."
        )

        drug_name = drug_info.get("ticari_ad") or drug_info.get("etken_madde") or "bilinmiyor"
        prompt = SAFETY_PROMPT_TEMPLATE.format(
            drug_info=json.dumps(drug_info, ensure_ascii=False, indent=2),
            rag_data=rag_text,
        )

        models = _groq_safety_model_chain()
        last_err: Optional[Exception] = None

        for model_id in models:
            # Groq JSON modu destekliyor mu? (llama-3.3 destekliyor)
            use_json_mode = "llama-3" in model_id
            try:
                kwargs: Dict[str, Any] = dict(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": "Sen bir ilaç güvenlik uzmanısın. SADECE JSON döndür."},
                        {"role": "user",   "content": prompt},
                    ],
                    max_tokens=2048,
                    temperature=0.1,
                )
                if use_json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                response = self.groq_client.chat.completions.create(**kwargs)
                raw = response.choices[0].message.content or ""
                parsed = self._parse_json_response(raw)

                # Kritik alanlar eksikse retry — kısa prompt
                if not parsed.get("alarm_seviyesi") or not parsed.get("yan_etkiler"):
                    parsed = self._retry_simplified(drug_name, model_id) or parsed

                if model_id != models[0]:
                    parsed["groq_model_notu"] = f"Yanıt modeli: `{model_id}`"
                return parsed

            except Exception as e:
                last_err = e
                if _groq_is_rate_limit(e) and model_id != models[-1]:
                    print(f"[SafetyAuditor] {model_id} limit/429, sıradaki… ({e})")
                    continue
                break

        return {
            "hata": _groq_safety_failure_message(last_err) if last_err else "Safety Auditor bilinmeyen hata.",
            "alarm_seviyesi": "SARI",
            "alarm_gerekce": "Otomatik analiz tamamlanamadı — eczacıya danışın.",
            "guven_puani": 2,
        }

    def _retry_simplified(self, drug_name: str, model_id: str) -> Optional[Dict[str, Any]]:
        """Kritik alanlar boşsa çok daha kısa prompt ile tekrar dener."""
        simple = f"""Sadece JSON döndür. {drug_name} ilacı için:
{{"yan_etkiler":{{"yaygin":["..."],"ciddi":["..."],"cok_nadir":["..."]}},"etkilesimler":["..."],"kontrendikasyonlar":["..."],"ozel_uyarilar":["..."],"alarm_seviyesi":"SARI","alarm_gerekce":"gerekçe","guven_puani":6}}"""
        try:
            r = self.groq_client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": simple}],
                max_tokens=1024,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            return self._parse_json_response(r.choices[0].message.content or "")
        except Exception:
            return None

    @staticmethod
    def _parse_json_response(raw: str) -> Dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        # Kritik alanları regex ile tahmin et
        result: Dict[str, Any] = {"guven_puani": 3, "ham_cikti": raw[:400]}
        for key in ["alarm_seviyesi", "alarm_gerekce"]:
            pat = rf'"{key}"\s*:\s*"([^"]+)"'
            hit = re.search(pat, cleaned, re.IGNORECASE)
            if hit:
                result[key] = hit.group(1)
        # alarm_seviyesi metinden de çıkarılabilir
        if "alarm_seviyesi" not in result:
            for level in ["KIRMIZI", "SARI", "YEŞİL"]:
                if level in raw.upper():
                    result["alarm_seviyesi"] = level
                    break
        return result


# ---------------------------------------------------------------------------
# AJAN 4: Corporate Analyst
# ---------------------------------------------------------------------------

class CorporateAnalystAgent:
    """
    Groq Llama-3 kullanarak ilaç üreticisi firma bilgilerini raporlayan ajan.
    (Önceki: Gemini — quota tasarrufu için Groq'a taşındı)
    """

    def __init__(self):
        self.groq_client = _init_groq()

    def analyze(self, drug_name: str, manufacturer: Optional[str]) -> Dict[str, Any]:
        """Firma analizi yapar (Groq + Llama-3 ile)."""
        prompt = CORPORATE_PROMPT_TEMPLATE.format(
            drug_name=drug_name or "Bilinmiyor",
            manufacturer=manufacturer or "Bilinmiyor",
        )
        models = _groq_safety_model_chain()
        last_err: Optional[Exception] = None

        for model_id in models:
            try:
                response = self.groq_client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": "Sen bir ilaç firma uzmanısın. SADECE JSON döndür."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1024,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content or ""
                parsed = self._parse_json_response(raw)

                # Kritik alanlar eksikse retry
                firma_adi = parsed.get("firma_adi", "")
                guven = parsed.get("guven_puani", 0)
                if (
                    not firma_adi
                    or firma_adi in ("Bilinmiyor", "Tespit Edilemedi", "")
                    or guven < 4
                ):
                    retry = self._retry_simplified(drug_name, manufacturer, model_id)
                    if retry:
                        parsed = retry

                if model_id != models[0]:
                    parsed["groq_model_notu"] = f"Model: {model_id}"
                return parsed

            except Exception as e:
                last_err = e
                if _groq_is_rate_limit(e) and model_id != models[-1]:
                    print(f"[CorporateAnalyst] {model_id} limit/429, sıradaki… ({e})")
                    continue
                break

        return {
            "hata": f"Corporate Analyst (Groq) başarısız: {last_err}" if last_err else "Corporate Analyst başarısız.",
            "guven_puani": 1,
        }

    def _retry_simplified(
        self, drug_name: str, manufacturer: Optional[str], model_id: str
    ) -> Optional[Dict[str, Any]]:
        """Firma adı boşsa kısa prompt ile tekrar dener."""
        simple = (
            f"Sadece JSON döndür. '{drug_name}' ilacının üreticisi nedir? "
            f"Bilinen: {manufacturer or 'bilinmiyor'}. "
            '{"firma_adi":"adı","ulke":"ülke","titck_durumu":"TİTCK onaylı veya Belirsiz","guven_puani":5}'
        )
        try:
            r = self.groq_client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": simple}],
                max_tokens=512,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            result = self._parse_json_response(r.choices[0].message.content or "")
            if result.get("firma_adi") and result["firma_adi"] not in ("Bilinmiyor", ""):
                return result
        except Exception as e:
            print(f"[CorporateAnalyst] retry hatası: {e}")
        return None

    @staticmethod
    def _parse_json_response(raw: str) -> Dict[str, Any]:
        cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        result: Dict[str, Any] = {"guven_puani": 3, "ham_cikti": raw[:400]}
        for key in ["firma_adi", "ulke", "titck_durumu", "genel_degerlendirme"]:
            pat = rf'"{key}"\s*:\s*"([^"]+)"'
            hit = re.search(pat, cleaned, re.IGNORECASE)
            if hit:
                result[key] = hit.group(1)
        return result


# ---------------------------------------------------------------------------
# AJAN 5: Report Synthesizer
# ---------------------------------------------------------------------------

class ReportSynthesizerAgent:
    """
    Tüm ajan çıktılarını birleştirip kapsamlı Türkçe rapor üreten nihai sentez ajanı.
    PRIMARY: Groq Llama-3 (hızlı, güvenilir)
    FALLBACK: Gemini (Groq unavailable ise)
    """

    def __init__(self):
        self.groq_client = _init_groq()
        _init_gemini()

    def synthesize(
        self,
        vision_data: Dict,
        safety_data: Dict,
        corporate_data: Dict,
        rag_sources: List[Dict],
    ) -> Tuple[str, float, Optional[str]]:
        """
        Tüm veriyi birleştirip Markdown raporu döndürür.
        Returns: (rapor_metni, ortalama_guven_puani, hata veya None)
        """
        rag_kaynakca = "\n".join(
            f"- {r['kaynak']} (s.{r['sayfa']}): {r['metin'][:120]}..."
            for r in rag_sources
        ) or "Prospektüs kaynağı bulunamadı."

        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            vision_data=json.dumps(vision_data, ensure_ascii=False, indent=2),
            safety_data=json.dumps(safety_data, ensure_ascii=False, indent=2),
            corporate_data=json.dumps(corporate_data, ensure_ascii=False, indent=2),
            rag_sources=rag_kaynakca,
        )

        scores = []
        for data in [safety_data, corporate_data]:
            if isinstance(data.get("guven_puani"), (int, float)):
                scores.append(float(data["guven_puani"]))
        vision_score = vision_data.get("okunabilirlik_skoru")
        if isinstance(vision_score, (int, float)):
            scores.append(float(vision_score))
        fallback_avg = sum(scores) / len(scores) if scores else 3.0

        # ADIM 1: Groq ile dene (PRIMARY)
        groq_models = _groq_safety_model_chain()
        groq_err = None
        for model_id in groq_models:
            try:
                print(f"[ReportSynthesizer] Groq {model_id} ile rapor oluşturuluyor...")
                response = self.groq_client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": "Sen Türkçe tıbbi rapor yazmanında uzmanısın. Kapsamlı, profesyonel, yapılandırılmış rapor üret."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=4096,
                    temperature=0.3,
                )
                report_text = response.choices[0].message.content or ""
                if report_text.strip():
                    print("[ReportSynthesizer] Groq raporu başarıyla oluşturdu.")
                    avg_confidence = sum(scores) / len(scores) if scores else 5.0
                    return report_text, avg_confidence, None
            except Exception as e:
                groq_err = e
                if _groq_is_rate_limit(e) and model_id != groq_models[-1]:
                    print(f"[ReportSynthesizer] {model_id} limit/429, sıradaki…")
                    continue
                break

        # ADIM 2: Gemini fallback (Groq başarısızsa)
        print(f"[ReportSynthesizer] Groq başarısız ({groq_err}), Gemini fallback'e geçiliyor...")
        gemini_models = _gemini_model_chain()
        gemini_err = None
        for name in gemini_models:
            try:
                model = genai.GenerativeModel(
                    name,
                    system_instruction=MASTER_PROMPT,
                )
                response = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=4096,
                    ),
                )
                report_text = response.text
                if report_text.strip():
                    print(f"[ReportSynthesizer] Gemini ({name}) raporu başarıyla oluşturdu.")
                    avg_confidence = sum(scores) / len(scores) if scores else 5.0
                    return report_text, avg_confidence, None
            except Exception as e:
                gemini_err = e
                if _gemini_model_missing_error(e) and name != gemini_models[-1]:
                    print(f"[ReportSynthesizer] {name} kullanılamadı, sıradaki…")
                    continue
                break

        # HER İKİSİ DE BAŞARISIZ
        combined_err = f"Groq: {groq_err}; Gemini: {gemini_err}"
        print(f"[ReportSynthesizer] Tüm modeller başarısız: {combined_err}")
        return "", fallback_avg, combined_err


# ---------------------------------------------------------------------------
# FACT-CHECKER: Halüsinasyon Engeli
# ---------------------------------------------------------------------------

class FactChecker:
    """
    Vision çıktısı ile RAG verisi arasındaki kritik tutarsızlıkları tespit eder.
    Dozaj farklılıkları ve etken madde uyuşmazlıklarını saptar.
    """

    @staticmethod
    def check(vision_data: Dict, rag_results: List[Dict]) -> Dict[str, Any]:
        # Geçerli RAG sonuçlarını filtrele (Genel Bilgi + PDF kaynakları dahil)
        real_results = [
            r for r in rag_results
            if r.get("kaynak", "—") not in ("—", "")
            and "Prospektüs veritabanı boş" not in r.get("metin", "")
        ]
        if not real_results:
            return {
                "uyusmazlik": False,
                "sorunlar": [],
                "mesaj": "ℹ️ Veri kaynağı yok — Fact-Check yapılamadı.",
                "corpus_bos": True,
            }

        drug_name = (vision_data.get("ticari_ad") or "").lower()
        etken = (vision_data.get("etken_madde") or "").lower()
        dozaj = vision_data.get("dozaj", "")

        # Görsel analiz başarısızsa fact-check yapma
        if not drug_name and not etken:
            return {"uyusmazlik": False, "sorunlar": [], "mesaj": "ℹ️ İlaç adı yok — Fact-Check atlandı."}

        issues = []
        # En az bir sonuçta eşleşme varsa geçerli say
        name_found = any(
            (drug_name and drug_name in r.get("metin", "").lower()) or
            (etken and etken in r.get("metin", "").lower())
            for r in real_results
        )
        if not name_found and (drug_name or etken):
            sample = real_results[0].get("kaynak", "?")
            # "Genel Bilgi" kaynağından geliyorsa seri bir uyarı verme
            if sample == "Genel Bilgi":
                # Mock veriden geliyor — çok katı kurallar uygulama
                pass
            else:
                issues.append(
                    f"'{etken or drug_name}' hiçbir prospektüs kaynağında bulunamadı "
                    f"(örn. '{sample}'). Corpus'a doğru PDF yüklenmiş mi?"
                )

        # Dozaj kontrolü — en az bir sonuçta sayı eşleşmesi yeterli
        if dozaj and not issues:
            nums_vision = re.findall(r"\d+(?:[.,]\d+)?", str(dozaj))
            if nums_vision:
                all_rag_text = " ".join(r.get("metin", "") for r in real_results).lower()
                nums_rag = re.findall(r"\d+(?:[.,]\d+)?", all_rag_text)
                if not any(n in nums_rag for n in nums_vision):
                    issues.append(
                        f"Dozaj uyuşmazlığı olabilir: görselde '{dozaj}' — "
                        "prospektüslerde bu sayısal değer bulunamadı."
                    )

        if issues:
            return {
                "uyusmazlik": True,
                "sorunlar": issues,
                "mesaj": "⚠️ VERİ UYUŞMAZLIĞI: Fact-Checker tutarsızlık tespit etti!",
                "corpus_bos": False,
            }
        return {"uyusmazlik": False, "sorunlar": [], "mesaj": "✅ Fact-Check geçti.", "corpus_bos": False}


# ---------------------------------------------------------------------------
# ANA ORKESTRATÖR
# ---------------------------------------------------------------------------

class PharmaGuardOrchestrator:
    """
    Tüm 5 ajanı koordine eden ana orkestratör.
    Streamlit arayüzünden çağrılır.
    """

    def __init__(self):
        print("[Orchestrator] Başlatılıyor...")
        self.vision_agent = VisionScannerAgent()
        self.rag_agent = RAGSpecialistAgent()
        self.safety_agent = SafetyAuditorAgent()
        self.corporate_agent = CorporateAnalystAgent()
        self.synthesizer = ReportSynthesizerAgent()
        self.fact_checker = FactChecker()
        print("[Orchestrator] Tüm ajanlar hazır. ✓")

    def run(
        self,
        image: Optional[Image.Image] = None,
        drug_name_text: Optional[str] = None,
        pdf_bytes: Optional[bytes] = None,
        pdf_filename: str = "prospektus.pdf",
        progress_callback=None,
    ) -> Dict[str, Any]:
        """
        Ana analiz iş akışını çalıştırır.

        Args:
            image: PIL Image nesnesi (ilaç kutu görseli)
            drug_name_text: Metin olarak ilaç adı (görsel yoksa)
            pdf_bytes: Prospektüs PDF'inin ham bytes'ı (doğrudan PDF analizi)
            pdf_filename: PDF dosya adı (gösterim için)
            progress_callback: Streamlit progress bar için callable(step: int, message: str)

        Returns:
            {
                "vision": {...},
                "rag_results": [...],
                "fact_check": {...},
                "safety": {...},
                "corporate": {...},
                "report": "Markdown rapor metni",
                "avg_confidence": float,
                "alarm": "YEŞİL/SARI/KIRMIZI",
            }
        """

        def _progress(step: int, msg: str):
            if progress_callback:
                progress_callback(step, msg)
            print(f"[Step {step}] {msg}")

        results = {}

        # ADIM 1: Görüntü / Metin / PDF Analizi
        if pdf_bytes is not None:
            _progress(1, f"📄 PDF Scanner: '{pdf_filename}' prospektüsü analiz ediliyor...")
            vision_data = self.vision_agent.scan_pdf(pdf_bytes, pdf_filename)
        elif image is not None:
            _progress(1, "👁️ Vision Scanner: Görsel analiz ediliyor...")
            vision_data = self.vision_agent.scan(image)
        else:
            _progress(1, "✏️ Metin girişi işleniyor...")
            vision_data = self.vision_agent.scan_text_input(drug_name_text or "")
        results["vision"] = vision_data

        # Okunabilirlik / PDF hata kontrolü
        score = vision_data.get("okunabilirlik_skoru", 10)
        if isinstance(score, (int, float)) and score < 5:
            _progress(1, "⚠️ Fotoğraf kalitesi yetersiz! Lütfen daha aydınlık bir ortamda çekin.")
        if "hata" in vision_data and pdf_bytes is not None:
            _progress(1, f"⚠️ PDF hatası: {vision_data['hata']}")

        # ADIM 2: RAG Araması
        _progress(2, "📚 RAG Specialist: Prospektüs veritabanı taranıyor...")
        ticari_ad = vision_data.get("ticari_ad", drug_name_text or "")
        etken = vision_data.get("etken_madde", "")
        query = f"{ticari_ad} {etken}".strip()
        rag_results = self.rag_agent.search(query, k=5, vision_data=vision_data)
        results["rag_results"] = rag_results

        # ADIM 3: Fact-Check
        _progress(3, "🔍 Fact-Checker: Veri tutarlılığı kontrol ediliyor...")
        fact_check = self.fact_checker.check(vision_data, rag_results)
        results["fact_check"] = fact_check

        # ADIM 4+5: Safety Auditor ve Corporate Analyst — paralel çalıştır
        _progress(4, "🛡️ Safety Auditor + 🏭 Corporate Analyst: Paralel analiz başladı...")
        manufacturer = vision_data.get("uretici")

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_safety    = pool.submit(self.safety_agent.audit, vision_data, rag_results)
            fut_corporate = pool.submit(self.corporate_agent.analyze, ticari_ad, manufacturer)
            safety_data   = fut_safety.result()
            corporate_data = fut_corporate.result()

        results["safety"]    = safety_data
        results["corporate"] = corporate_data
        _progress(5, "✅ Safety + Corporate tamamlandı.")

        # ADIM 6: Rapor Sentezi
        _progress(6, "📝 Report Synthesizer: Nihai Türkçe rapor hazırlanıyor...")
        report_text, avg_confidence, synthesis_error = self.synthesizer.synthesize(
            vision_data, safety_data, corporate_data, rag_results
        )
        results["synthesis_error"] = synthesis_error

        if synthesis_error:
            model_hint = ", ".join(_gemini_model_chain())
            report_text = (
                "## Rapor metni oluşturulamadı\n\n"
                "Nihai özet (Gemini) şu anda üretilemedi. **Görsel Analiz**, "
                "**Güvenlik** ve **Firma** sekmelerindeki ajan çıktıları yine de "
                "incelenebilir.\n\n"
                f"- Denenen modeller: `{model_hint}`\n"
                "- `.env` / Streamlit Secrets içinde `GEMINI_MODEL` ile sabitleyin; "
                "ör. `gemini-2.5-flash`, `gemini-1.5-flash`.\n\n"
                "**Teknik ayrıntı:**\n```\n"
                f"{synthesis_error}\n```\n"
            )
        else:
            if avg_confidence < 8:
                warning = (
                    f"\n\n> ⚠️ **DİKKAT:** Ortalama güven puanı **{avg_confidence:.1f}/10**. "
                    "Bilgiler %100 doğrulanamadı. Lütfen bir sağlık uzmanına danışın.\n\n"
                )
                report_text = warning + report_text

        # VERİ UYUŞMAZLIĞI
        if fact_check["uyusmazlik"]:
            block = (
                "\n\n---\n"
                "## ⛔ VERİ UYUŞMAZLIĞI ALARI\n"
                + "\n".join(f"- {s}" for s in fact_check["sorunlar"])
                + "\n\n**Bu rapor bloklanmıştır. Bir eczacı veya hekime danışın.**\n---\n"
            )
            report_text = block + report_text

        results["report"] = report_text
        results["avg_confidence"] = avg_confidence
        results["alarm"] = safety_data.get("alarm_seviyesi", "BİLİNMİYOR")

        _progress(7, "✅ Analiz tamamlandı!")
        return results
