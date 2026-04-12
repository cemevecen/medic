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
        # macOS
        ("/Library/Fonts/Arial Unicode MS.ttf",
         "/Library/Fonts/Arial Unicode MS.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
         "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        # Windows
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
    ]

    # matplotlib DejaVu (numpy/scipy bağımlılığıyla gelebilir)
    try:
        import matplotlib
        mpl_dir = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
        reg = os.path.join(mpl_dir, "DejaVuSans.ttf")
        bold = os.path.join(mpl_dir, "DejaVuSans-Bold.ttf")
        if os.path.exists(reg):
            candidates.insert(0, (reg, bold if os.path.exists(bold) else reg))
    except Exception:
        pass

    for reg, bold in candidates:
        if os.path.exists(reg):
            return reg, bold if os.path.exists(bold) else reg

    return None, None


# Modül yüklenirken font kayıt et — başarısız olursa Helvetica'ya geri döner
_FONT_REGULAR = "Helvetica"
_FONT_BOLD    = "Helvetica-Bold"
_FONT_MONO    = "Courier"

def _register_unicode_fonts() -> None:
    global _FONT_REGULAR, _FONT_BOLD
    reg_path, bold_path = _find_unicode_ttf()
    if reg_path is None:
        print("[utils] Unicode TTF bulunamadı — Helvetica kullanılıyor (Türkçe bozuk olabilir).")
        return
    try:
        if "PGUnicode" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("PGUnicode",     reg_path))
            pdfmetrics.registerFont(TTFont("PGUnicodeBold", bold_path))
            from reportlab.lib.fonts import addMapping
            addMapping("PGUnicode", 0, 0, "PGUnicode")
            addMapping("PGUnicode", 1, 0, "PGUnicodeBold")
        _FONT_REGULAR = "PGUnicode"
        _FONT_BOLD    = "PGUnicodeBold"
        print(f"[utils] Unicode font kayıt edildi: {os.path.basename(reg_path)}")
    except Exception as e:
        print(f"[utils] Font kayıt hatası: {e} — Helvetica kullanılıyor.")


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
    base = getSampleStyleSheet()

    styles = {
        "title": ParagraphStyle(
            "PGTitle",
            parent=base["Title"],
            fontSize=22,
            textColor=COLOR_PRIMARY,
            spaceAfter=6,
            fontName=_FONT_BOLD,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "PGSubtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=COLOR_ACCENT,
            spaceAfter=4,
            fontName=_FONT_REGULAR,
            alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "PGH1",
            parent=base["Heading1"],
            fontSize=14,
            textColor=COLOR_PRIMARY,
            spaceBefore=14,
            spaceAfter=4,
            fontName=_FONT_BOLD,
            borderPad=4,
        ),
        "h2": ParagraphStyle(
            "PGH2",
            parent=base["Heading2"],
            fontSize=12,
            textColor=COLOR_ACCENT,
            spaceBefore=10,
            spaceAfter=3,
            fontName=_FONT_BOLD,
        ),
        "body": ParagraphStyle(
            "PGBody",
            parent=base["Normal"],
            fontSize=10,
            textColor=COLOR_TEXT,
            spaceAfter=6,
            leading=16,
            fontName=_FONT_REGULAR,
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
            fontName=_FONT_REGULAR,
        ),
        "warning": ParagraphStyle(
            "PGWarning",
            parent=base["Normal"],
            fontSize=10,
            textColor=COLOR_RED,
            fontName=_FONT_BOLD,
            spaceAfter=6,
        ),
        "footer": ParagraphStyle(
            "PGFooter",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.grey,
            fontName=_FONT_REGULAR,
            alignment=TA_CENTER,
        ),
        "code": ParagraphStyle(
            "PGCode",
            parent=base["Code"],
            fontSize=9,
            textColor=COLOR_TEXT,
            fontName=_FONT_MONO,
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
            text = _format_inline(text)
            flowables.append(Paragraph(f"• {text}", styles["bullet"]))
            i += 1
            continue

        # Numaralı liste
        if re.match(r"^\d+\.\s+", line):
            text = re.sub(r"^\d+\.\s+", "", line)
            text = _format_inline(text)
            flowables.append(Paragraph(text, styles["bullet"]))
            i += 1
            continue

        # Uyarı satırı (> ile başlayan blockquote)
        if line.startswith("> "):
            text = line[2:].strip()
            text = _format_inline(text)
            flowables.append(Paragraph(text, styles["warning"]))
            i += 1
            continue

        # Normal paragraf
        text = _format_inline(line)
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


def _format_inline(text: str) -> str:
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
    text = re.sub(r"`([^`]+)`", rf"<font name='{_FONT_MONO}'>\1</font>", text)
    return text


def generate_pdf_report(
    report_markdown: str,
    drug_name: str,
    alarm_level: str,
    avg_confidence: float,
    vision_data: Optional[Dict] = None,
) -> bytes:
    """
    Analiz raporunu profesyonel PDF formatında oluşturur.

    Returns:
        PDF dosyasının bytes içeriği (Streamlit download_button için).
    """
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
            ("FONTNAME", (0, 0), (0, -1), _FONT_BOLD),
            ("FONTNAME", (1, 0), (1, -1), _FONT_REGULAR),
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
