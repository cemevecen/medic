"""
PHARMA-GUARD AI — Yardımcı Araçlar
utils.py: Görüntü işleme, PDF rapor oluşturma ve yardımcı fonksiyonlar.
"""

import io
import os
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from xml.sax.saxutils import escape

from PIL import Image, ImageEnhance, ImageFilter

# ReportLab PDF oluşturma
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# ---------------------------------------------------------------------------
# UNICODE FONT KURULUMU (Türkçe karakter desteği)
# ---------------------------------------------------------------------------

def _search_fonts_in_directory(directory: str, font_names: list) -> Optional[str]:
    """
    Verilen dizinde arama yaparak belirtilen isimlerden biriyle eşleşen font dosyasını bulur.
    macOS'ta /Library/Fonts/ içinde font araması için.
    """
    if not os.path.isdir(directory):
        return None

    try:
        for filename in os.listdir(directory):
            # Normalize dosya adı
            name_lower = filename.lower()

            # Font uzantıları: .ttf, .otf, .dfont, .ttc
            if not any(name_lower.endswith(ext) for ext in ['.ttf', '.otf', '.dfont', '.ttc']):
                continue

            # Font adlarında arama
            for font_name in font_names:
                if font_name.lower() in name_lower:
                    full_path = os.path.join(directory, filename)
                    try:
                        # Dosyanın okunabilir olup olmadığını kontrol et
                        with open(full_path, 'rb') as f:
                            f.read(4)  # İlk 4 byte oku
                        return full_path
                    except:
                        continue
    except:
        pass

    return None


def _find_unicode_ttf() -> tuple:
    """
    Sistemde Unicode destekli bir TTF font çifti (regular + bold) arar.
    Streamlit Cloud (Ubuntu), macOS ve Windows'ta çalışır.
    Returns: (regular_path, bold_path) — bulunamazsa (None, None)
    """
    candidates = [
        # Ubuntu / Debian (Streamlit Cloud)
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        # Noto Sans — Ubuntu
        ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
         "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
        ("/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
         "/usr/share/fonts/opentype/noto/NotoSans-Bold.ttf"),
        # Liberation Sans — Ubuntu
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        # Windows
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
    ]

    # 1. matplotlib DejaVu (EN YÜKSEK ÖNCELİK — her zaman Unicode destekli)
    try:
        import matplotlib
        mpl_dir = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
        reg = os.path.join(mpl_dir, "DejaVuSans.ttf")
        bold = os.path.join(mpl_dir, "DejaVuSans-Bold.ttf")
        if os.path.exists(reg) and os.path.exists(bold):
            print(f"[utils] ✓ matplotlib DejaVuSans bulundu (EN YÜKSEK ÖNCELİK)")
            return reg, bold
    except Exception as e:
        print(f"[utils] matplotlib font kontrolü: {e}")

    # 2. Verilen path'lerde ara
    for reg, bold in candidates:
        if os.path.exists(reg):
            bold_path = bold if os.path.exists(bold) else reg
            print(f"[utils] ✓ Font bulundu: {os.path.basename(reg)}")
            return reg, bold_path

    # 3. macOS — /Library/Fonts/ dizininde Unicode font ara
    library_fonts_dir = "/Library/Fonts"
    if os.path.isdir(library_fonts_dir):
        print(f"[utils] Araştırılıyor: {library_fonts_dir}")
        # Öncelik sırası: DejaVu > Noto > Arial > Courier > Times > Helvetica
        for font_names in [
            ["dejavu"],           # DejaVu (mükemmel Türkçe desteği)
            ["notosans", "noto"], # Noto Sans (çok iyi Türkçe desteği)
            ["arial"],            # Arial (iyi Türkçe desteği)
            ["courier"],          # Courier (temel Türkçe desteği)
            ["times"],            # Times (temel Türkçe desteği)
        ]:
            found = _search_fonts_in_directory(library_fonts_dir, font_names)
            if found:
                # Bold variant ara
                bold_names = [name + "bold" for name in font_names] + font_names
                bold_found = _search_fonts_in_directory(library_fonts_dir, bold_names)
                print(f"[utils] ✓ macOS font bulundu: {os.path.basename(found)}")
                return found, bold_found if bold_found else found

    # 4. macOS — /System/Library/Fonts/ dizininde ara
    system_fonts_dir = "/System/Library/Fonts"
    if os.path.isdir(system_fonts_dir):
        print(f"[utils] Araştırılıyor: {system_fonts_dir}")
        for font_names in [["times"], ["courier"], ["helvetica"]]:
            found = _search_fonts_in_directory(system_fonts_dir, font_names)
            if found:
                print(f"[utils] ✓ Sistem font bulundu: {os.path.basename(found)}")
                return found, found

    return None, None


# Modül yüklenirken font kayıt et — başarısız olursa Helvetica'ya geri döner
_FONT_REGULAR = "Helvetica"
_FONT_BOLD    = "Helvetica-Bold"
_FONT_MONO    = "Courier"

def _register_unicode_fonts() -> None:
    global _FONT_REGULAR, _FONT_BOLD, _FONT_MONO

    # Adım 1: Sistem font'u bul
    reg_path, bold_path = _find_unicode_ttf()

    # Adım 2: Fallback path'ler (Streamlit Cloud Ubuntu'da daima vardır)
    if reg_path is None:
        print("[utils] ⚠️  Sistem font'u bulunamadı, fallback path'lere bakılıyor...")
        fallback_paths = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVu Sans.ttf",
        ]
        for fb_path in fallback_paths:
            if os.path.exists(fb_path):
                reg_path = fb_path
                # Bold path'i bulunuz
                bold_path_cand = fb_path.replace("Regular", "Bold").replace("DejaVu Sans", "DejaVu Sans Bold")
                bold_path = bold_path_cand if os.path.exists(bold_path_cand) else fb_path
                print(f"[utils] Fallback font bulundu: {os.path.basename(reg_path)}")
                break

    # Adım 3: Font registration
    if reg_path is None:
        print("[utils] ❌ Font bulunamadı! Helvetica kullanılacak (Türkçe karakterler ■ olarak görünecek).")
        print("[utils] Çözüm: DejaVuSans, Arial, Courier New vb. Unicode font yükleyin.")
        return

    try:
        print(f"[utils] 📝 Font kayıt ediliyor: {reg_path}")
        if "PGUnicode" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("PGUnicode", reg_path))
            pdfmetrics.registerFont(TTFont("PGUnicodeBold", bold_path))
            _FONT_REGULAR = "PGUnicode"
            _FONT_BOLD = "PGUnicodeBold"
            print(f"[utils] ✅ Font başarıyla kayıt edildi: {os.path.basename(reg_path)}")
        else:
            _FONT_REGULAR = "PGUnicode"
            _FONT_BOLD = "PGUnicodeBold"
            print(f"[utils] ℹ️  Font zaten register edilmiş: PGUnicode")
    except Exception as e:
        print(f"[utils] ❌ Font kayıt hatası: {e}")
        print(f"[utils] Font dosyası: {reg_path}")
        print(f"[utils] Helvetica fallback kullanılacak.")


_register_unicode_fonts()


# ---------------------------------------------------------------------------
# GÖRÜNTÜ İŞLEME
# ---------------------------------------------------------------------------

def preprocess_image(image: Image.Image, target_size: int = 1024) -> Image.Image:
    """
    Yüklenen ilaç görselini modele göndermeden önce optimize eder:
    - Boyut normalizasyonu
    - Kontrast artırma
    - Keskinleştirme
    """
    # RGBA veya diğer modları RGB'ye dönüştür
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    # Boyut sınırla (çok büyük görseller API kotasını hızla tüketir)
    w, h = image.size
    if max(w, h) > target_size:
        ratio = target_size / max(w, h)
        image = image.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # Kontrast ve keskinlik artır (ilaç kutu yazısının daha iyi okunması için)
    image = ImageEnhance.Contrast(image).enhance(1.3)
    image = ImageEnhance.Sharpness(image).enhance(1.5)

    return image


def image_to_bytes(image: Image.Image, fmt: str = "JPEG") -> bytes:
    """PIL Image'ı bytes olarak döndürür."""
    buf = io.BytesIO()
    image.save(buf, format=fmt, quality=90)
    return buf.getvalue()


def load_image_from_upload(uploaded_file) -> Image.Image:
    """Streamlit UploadedFile nesnesini PIL Image'a çevirir."""
    return Image.open(io.BytesIO(uploaded_file.read()))


# ---------------------------------------------------------------------------
# MARKDOWN → DÜZLEŞTIRILMIŞ METİN
# ---------------------------------------------------------------------------

def strip_markdown(text: str) -> str:
    """Markdown formatını sade metne dönüştürür (PDF için)."""
    # Başlıkları düz metin başlıklarına çevir
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Bold/italic temizle
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}(.*?)_{1,3}", r"\1", text)
    # Bağlantıları temizle
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Satır içi kod
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


# ---------------------------------------------------------------------------
# PDF RAPOR OLUŞTURUCU
# ---------------------------------------------------------------------------

# Renk Paleti
COLOR_PRIMARY = colors.HexColor("#1A3A5C")    # Koyu mavi — başlıklar
COLOR_ACCENT = colors.HexColor("#0078D4")     # Parlak mavi — vurgu
COLOR_RED = colors.HexColor("#C0392B")        # Kırmızı alarm
COLOR_YELLOW = colors.HexColor("#F39C12")     # Sarı uyarı
COLOR_GREEN = colors.HexColor("#27AE60")      # Yeşil onay
COLOR_LIGHT_BG = colors.HexColor("#F5F8FA")   # Açık gri arkaplan
COLOR_BORDER = colors.HexColor("#BDC3C7")     # Sınır çizgisi rengi
COLOR_TEXT = colors.HexColor("#2C3E50")       # Ana metin rengi

ALARM_COLOR_MAP = {
    "KIRMIZI": COLOR_RED,
    "SARI": COLOR_YELLOW,
    "YEŞİL": COLOR_GREEN,
}


def _build_styles():
    """PDF için özel stil seti oluşturur."""
    # Font adını kontrol et — global variable'ı oku
    font_regular = _FONT_REGULAR
    font_bold = _FONT_BOLD
    font_mono = _FONT_MONO

    # Eğer register edilen font (PGUnicode) varsa, onu kullan
    # Yoksa Helvetica kullan (Türkçe desteklemez ama en azından PDF oluşur)
    registered_fonts = pdfmetrics.getRegisteredFontNames()

    if "PGUnicode" not in registered_fonts:
        # PGUnicode bulunamadı, Helvetica'ya geri dön
        font_regular = "Helvetica"
        font_bold = "Helvetica-Bold"

    # Fallback olarak Courier'i mono font olarak kullan
    if font_mono not in registered_fonts and font_mono != "Courier":
        font_mono = "Courier"

    base = getSampleStyleSheet()

    styles = {
        "title": ParagraphStyle(
            "PGTitle",
            parent=base["Title"],
            fontSize=22,
            textColor=COLOR_PRIMARY,
            spaceAfter=6,
            fontName=font_bold,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "PGSubtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=COLOR_ACCENT,
            spaceAfter=4,
            fontName=font_regular,
            alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "PGH1",
            parent=base["Heading1"],
            fontSize=14,
            textColor=COLOR_PRIMARY,
            spaceBefore=14,
            spaceAfter=4,
            fontName=font_bold,
            borderPad=4,
        ),
        "h2": ParagraphStyle(
            "PGH2",
            parent=base["Heading2"],
            fontSize=12,
            textColor=COLOR_ACCENT,
            spaceBefore=10,
            spaceAfter=3,
            fontName=font_bold,
        ),
        "body": ParagraphStyle(
            "PGBody",
            parent=base["Normal"],
            fontSize=10,
            textColor=COLOR_TEXT,
            spaceAfter=6,
            leading=16,
            fontName=font_regular,
        ),
        "bullet": ParagraphStyle(
            "PGBullet",
            parent=base["Normal"],
            fontSize=10,
            textColor=COLOR_TEXT,
            spaceAfter=3,
            leftIndent=16,
            bulletIndent=0,
            leading=14,
            fontName=font_regular,
        ),
        "warning": ParagraphStyle(
            "PGWarning",
            parent=base["Normal"],
            fontSize=10,
            textColor=COLOR_RED,
            fontName=font_bold,
            spaceAfter=6,
        ),
        "footer": ParagraphStyle(
            "PGFooter",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.grey,
            fontName=font_regular,
            alignment=TA_CENTER,
        ),
        "code": ParagraphStyle(
            "PGCode",
            parent=base["Code"],
            fontSize=9,
            textColor=COLOR_TEXT,
            fontName=font_mono,
            backColor=COLOR_LIGHT_BG,
            spaceAfter=6,
        ),
    }
    return styles


def _markdown_to_flowables(md_text: str, styles: dict) -> list:
    """
    Markdown metnini ReportLab Flowable listesine dönüştürür.
    Başlıkları, madde işaretlerini ve paragrafları tanır.
    """
    mono_font = styles.get("code", type('obj', (object,), {'fontName': "Courier"})()).fontName
    flowables = []
    lines = md_text.split("\n")
    i = 0

    while i < len(lines):
        line = _strip_emoji(lines[i].rstrip())

        # Boş satır
        if not line:
            flowables.append(Spacer(1, 0.15 * cm))
            i += 1
            continue

        # Yatay çizgi
        if re.match(r"^-{3,}$", line) or re.match(r"^={3,}$", line):
            flowables.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER))
            i += 1
            continue

        # H1 başlık: ## veya # ile başlayan
        m = re.match(r"^(#{1,3})\s+(.+)", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            # Özel karakterleri escape et
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            style_key = "h1" if level <= 2 else "h2"
            flowables.append(Paragraph(text, styles[style_key]))
            i += 1
            continue

        # Madde işareti: - veya * ile başlayan
        if re.match(r"^[-*]\s+", line):
            text = re.sub(r"^[-*]\s+", "", line)
            text = _format_inline(text, mono_font)
            flowables.append(Paragraph(f"• {text}", styles["bullet"]))
            i += 1
            continue

        # Numaralı liste
        if re.match(r"^\d+\.\s+", line):
            text = re.sub(r"^\d+\.\s+", "", line)
            text = _format_inline(text, mono_font)
            flowables.append(Paragraph(text, styles["bullet"]))
            i += 1
            continue

        # Uyarı satırı (> ile başlayan blockquote)
        if line.startswith("> "):
            text = line[2:].strip()
            text = _format_inline(text, mono_font)
            flowables.append(Paragraph(text, styles["warning"]))
            i += 1
            continue

        # Normal paragraf
        text = _format_inline(line, mono_font)
        flowables.append(Paragraph(text, styles["body"]))
        i += 1

    return flowables


def _strip_emoji(text: str) -> str:
    """PDF'de sorun çıkaran emoji karakterlerini ASCII karşılıklarıyla değiştirir."""
    replacements = {
        "⚠️": "[!]", "⚕️": "[+]", "✅": "[OK]", "⛔": "[X]", "ℹ️": "[i]",
        "🔴": "[KIRMIZI]", "🟡": "[SARI]", "🟢": "[YESIL]", "⚪": "[?]",
        "💊": "", "📄": "", "📝": "", "🛡️": "", "🏭": "", "👁️": "",
        "📚": "", "🔍": "", "✏️": "", "🚀": "",
        "•": "-",
    }
    for emoji, repl in replacements.items():
        text = text.replace(emoji, repl)
    # Kalan emoji bloğunu kaldır (U+1F000–U+1FFFF arası)
    text = re.sub(r"[\U0001F000-\U0001FFFF]", "", text)
    return text


def _format_inline(text: str, mono_font: str = "Courier") -> str:
    """Satır içi Markdown formatlamayı ReportLab XML'e çevirir."""
    # & < > escape
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bold: **text** veya __text__
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.*?)__", r"<b>\1</b>", text)
    # Italic: *text* veya _text_
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.*?)_", r"<i>\1</i>", text)
    # Inline code: `text`
    text = re.sub(r"`([^`]+)`", rf"<font name='{mono_font}'>\1</font>", text)
    return text


def generate_pdf_report(
    report_markdown: str,
    drug_name: str,
    alarm_level: str,
    avg_confidence: float,
    vision_data: Optional[Dict] = None,
    similar_drugs_bundle: Optional[Dict] = None,
) -> bytes:
    """
    Analiz raporunu profesyonel PDF formatında oluşturur.

    Returns:
        PDF dosyasının bytes içeriği (Streamlit download_button için).
    """
    # Font registration'ı ensure et
    _register_unicode_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = _build_styles()
    story = []

    # ── KAPAK BÖLÜMÜ ──────────────────────────────────────────────────────
    story.append(Paragraph("PHARMA-GUARD AI", styles["title"]))
    story.append(Paragraph("Yapay Zeka Destekli İlaç Analiz Raporu", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_PRIMARY, spaceAfter=8))
    story.append(Spacer(1, 0.3 * cm))

    # Meta bilgi tablosu
    alarm_color = ALARM_COLOR_MAP.get(alarm_level, COLOR_PRIMARY)
    alarm_display = f"● {alarm_level}" if alarm_level in ALARM_COLOR_MAP else alarm_level

    meta_data = [
        ["İlaç Adı:", drug_name or "Bilinmiyor"],
        ["Rapor Tarihi:", datetime.now().strftime("%d.%m.%Y %H:%M")],
        ["Alarm Seviyesi:", alarm_display],
        ["Ortalama Güven Puanı:", f"{avg_confidence:.1f} / 10"],
    ]

    meta_table = Table(meta_data, colWidths=[4.5 * cm, 12 * cm])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), COLOR_LIGHT_BG),
            ("TEXTCOLOR", (0, 0), (0, -1), COLOR_PRIMARY),
            ("FONTNAME", (0, 0), (0, -1), styles["title"].fontName),
            ("FONTNAME", (1, 0), (1, -1), styles["body"].fontName),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, COLOR_LIGHT_BG]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ])
    )

    # Alarm seviyesine göre renklendir
    alarm_row_index = 2  # "Alarm Seviyesi" satırı
    meta_table.setStyle(
        TableStyle([("TEXTCOLOR", (1, alarm_row_index), (1, alarm_row_index), alarm_color)])
    )

    story.append(meta_table)
    story.append(Spacer(1, 0.5 * cm))

    # Düşük güven uyarısı
    if avg_confidence < 8:
        story.append(
            Paragraph(
                f"[!] DİKKAT: Ortalama güven puanı {avg_confidence:.1f}/10 — "
                "Bilgiler %100 doğrulanamadı. Lütfen bir sağlık uzmanına danışın.",
                styles["warning"],
            )
        )
        story.append(Spacer(1, 0.2 * cm))

    if vision_data and isinstance(vision_data.get("barkod_detay"), dict):
        bd = vision_data["barkod_detay"]
        story.append(Paragraph("<b>Barkod taraması</b>", styles["subtitle"]))
        bd_lines = [
            escape(str(bd.get("mesaj", "—"))),
            f"Değer: {escape(str(bd.get('deger') or '—'))}",
            f"Format: {escape(str(bd.get('format') or '—'))}",
        ]
        if bd.get("gorsel_celiski"):
            bd_lines.append(
                "Uyarı: Görsel OCR ile barkod okuması farklı — kimlik sinyali düşük güvenli."
            )
        story.append(Paragraph("<br/>".join(bd_lines), styles["body"]))
        story.append(Spacer(1, 0.25 * cm))

    if vision_data and isinstance(vision_data.get("qr_kod_detay"), dict):
        qr = vision_data["qr_kod_detay"]
        story.append(Paragraph("<b>QR kod taraması</b>", styles["subtitle"]))
        qr_lines = [
            escape(str(qr.get("mesaj", "—"))),
            f"İçerik: {escape(str(qr.get('deger') or '—'))}",
            f"Format: {escape(str(qr.get('format') or '—'))}",
        ]
        story.append(Paragraph("<br/>".join(qr_lines), styles["body"]))
        story.append(Spacer(1, 0.25 * cm))

    if similar_drugs_bundle and isinstance(similar_drugs_bundle, dict):
        story.append(Paragraph("<b>Benzer İlaçlar / Muadil Alternatifler (özet)</b>", styles["subtitle"]))
        story.append(
            Paragraph(escape(str(similar_drugs_bundle.get("uyari", ""))), styles["footer"])
        )
        story.append(
            Paragraph(
                escape(str(similar_drugs_bundle.get("fiyat_entegrasyonu_notu", ""))),
                styles["footer"],
            )
        )
        story.append(Spacer(1, 0.15 * cm))
        for row in similar_drugs_bundle.get("oneriler") or []:
            if not isinstance(row, dict):
                continue
            line = (
                f"<b>{escape(str(row.get('ticari_ad') or '—'))}</b><br/>"
                f"Etken: {escape(str(row.get('etken_madde') or '—'))} · "
                f"Dozaj: {escape(str(row.get('dozaj') or '—'))} · "
                f"Form: {escape(str(row.get('form') or '—'))}<br/>"
                f"<i>{escape(str(row.get('benzerlik_aciklamasi') or ''))}</i> "
                f"({escape(str(row.get('kaynak') or ''))})"
            )
            story.append(Paragraph(line, styles["body"]))
            story.append(Spacer(1, 0.12 * cm))
        story.append(Spacer(1, 0.2 * cm))

    # ── RAPOR İÇERİĞİ ─────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 0.2 * cm))

    content_flowables = _markdown_to_flowables(report_markdown, styles)
    story.extend(content_flowables)

    # ── YASAL UYARI ────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_BORDER))
    story.append(Spacer(1, 0.2 * cm))
    story.append(
        Paragraph(
            "Bu rapor yalnızca bilgilendirme amaçlıdır. Tanı, tedavi veya ilaç "
            "değişikliği için mutlaka lisanslı bir sağlık uzmanına başvurun. "
            "Pharma-Guard AI'ın sunduğu bilgiler tıbbi tavsiye niteliği taşımaz.",
            styles["footer"],
        )
    )
    story.append(
        Paragraph(
            f"Rapor: Pharma-Guard AI v1.0 | {datetime.now().strftime('%d.%m.%Y')}",
            styles["footer"],
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ---------------------------------------------------------------------------
# YARDIMCI: CORPUS YÖNETİMİ
# ---------------------------------------------------------------------------

def save_uploaded_pdf(uploaded_file, corpus_dir: str = "data/corpus") -> str:
    """Kullanıcının yüklediği PDF'yi corpus dizinine kaydeder."""
    target = Path(corpus_dir) / uploaded_file.name
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(target)


def list_corpus_pdfs(corpus_dir: str = "data/corpus") -> list:
    """Corpus dizinindeki PDF dosyalarını listeler."""
    p = Path(corpus_dir)
    if not p.exists():
        return []
    return sorted([f.name for f in p.glob("*.pdf")])


# ---------------------------------------------------------------------------
# YARDIMCI: ALARM RENK ETİKETİ
# ---------------------------------------------------------------------------

ALARM_EMOJI = {
    "KIRMIZI": "🔴",
    "SARI": "🟡",
    "YEŞİL": "🟢",
    "BİLİNMİYOR": "⚪",
}

ALARM_MESSAGE = {
    "KIRMIZI": "Kritik Risk — Derhal Sağlık Uzmanına Başvurun!",
    "SARI": "Dikkat Gerekiyor — Kullanmadan Önce Eczacıya Danışın.",
    "YEŞİL": "Genel Kullanım İçin Uygun (Doktor/Eczacı Gözetiminde).",
    "BİLİNMİYOR": "Alarm seviyesi belirlenemedi.",
}
