#!/usr/bin/env python3
"""
ilacrehberi.com reçete / liste sayfalarındaki ilaç tablolarını XLSX'e aktarır.

export_ilacrehberi_fihrist_xlsx.py ile aynı HTTP yaklaşımı:
  - requests.Session, cp1254 gövde, aynı User-Agent / Accept-Language

Her kaynak URL ayrı bir Excel sayfasına yazılır. Sayfalama: GET ?page=2,3,…
(javascript:yeniilaclar(n) formunun gönderdiği istekle uyumlu).

Kullanım:
  pip install requests beautifulsoup4 pandas openpyxl
  python scripts/export_ilacrehberi_recete_listeleri_xlsx.py
  python scripts/export_ilacrehberi_recete_listeleri_xlsx.py -o ~/Desktop/ozel.xlsx

Not: Site içeriği ve kullanım koşullarına tabidir; istekler arasında gecikme kullanın.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://www.ilacrehberi.com"

LIST_SOURCES: list[tuple[str, str]] = [
    ("/yesil-receteli-ilaclar/", "Yesil_Receteli"),
    ("/kirmizi-receteli-ilaclar/", "Kirmizi_Receteli"),
    ("/mor-receteli-ilaclar/", "Mor_Receteli"),
    ("/turuncu-receteli-ilaclar/", "Turuncu_Receteli"),
    ("/takibi-zorunlu-ilaclar/", "Takibi_Zorunlu"),
    ("/recetesiz-ilaclar/", "Recetesiz"),
    ("/geri-cekilen-ilaclar/", "Geri_Cekilen"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122 Safari/537.36; export_ilacrehberi_recete_listeleri/1.0"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def _decode_html(resp: requests.Response) -> str:
    return resp.content.decode("cp1254", errors="replace")


def _max_page_from_html(html: str) -> int:
    nums = [int(x) for x in re.findall(r"yeniilaclar\((\d+)\)", html, flags=re.I)]
    return max(nums) if nums else 1


def _unique_header_labels(raw: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for h in raw:
        base = (h or "").strip() or "sutun"
        base = re.sub(r"[\[\]:*?/\\]", "_", base)[:60]
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append(base if n == 0 else f"{base}_{n + 1}")
    return out


def _detay_url_from_cell(td: Any, base: str = BASE) -> str:
    for a in td.find_all("a", href=True):
        h = (a.get("href") or "").strip()
        if not h.startswith("/v/"):
            continue
        if "/kt" in h or "/kub" in h:
            continue
        return urljoin(base, h.split("#")[0])
    return ""


def parse_table_rows(html: str, base: str = BASE) -> tuple[list[str], list[dict[str, str]]]:
    """İlk anlamlı tablodan başlık + satır sözlükleri (metin + detay_url)."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return [], []

    trs = table.find_all("tr")
    if not trs:
        return [], []

    header_cells = trs[0].find_all(["th", "td"])
    raw_heads = [c.get_text(strip=True) for c in header_cells]
    heads = _unique_header_labels(raw_heads)

    rows_out: list[dict[str, str]] = []
    for tr in trs[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue
        row: dict[str, str] = {}
        detay = ""
        for i, td in enumerate(tds):
            key = heads[i] if i < len(heads) else f"col_{i}"
            row[key] = td.get_text(" ", strip=True)
            if not detay:
                detay = _detay_url_from_cell(td, base=base)
        row["detay_url"] = detay
        rows_out.append(row)

    out_heads = heads + ["detay_url"]
    return out_heads, rows_out


def scrape_list_url(session: requests.Session, path: str, delay: float) -> pd.DataFrame:
    path = path if path.startswith("/") else "/" + path
    url = urljoin(BASE, path)
    r = session.get(url, headers=HEADERS, timeout=90)
    r.raise_for_status()
    html0 = _decode_html(r)
    max_p = _max_page_from_html(html0)

    all_rows: list[dict[str, str]] = []
    columns: list[str] | None = None

    for p in range(1, max_p + 1):
        if p == 1:
            html = html0
        else:
            time.sleep(max(0.0, delay))
            rp = session.get(url, params={"page": str(p)}, headers=HEADERS, timeout=90)
            rp.raise_for_status()
            html = _decode_html(rp)

        heads, rows = parse_table_rows(html)
        if not rows and p == 1:
            break
        if columns is None:
            columns = heads
        for row in rows:
            aligned: dict[str, str] = {c: row.get(c, "") for c in (columns or [])}
            all_rows.append(aligned)

        if p < max_p:
            time.sleep(max(0.0, delay))

    if not all_rows:
        return pd.DataFrame(
            [
                {
                    "_uyari": (
                        "Parse edilebilen tablo satırı yok; sayfa yapısı değişmiş veya liste boş olabilir "
                        "(ör. geri çekilen ilaçlar sayfası şu an HTML tablosu içermeyebilir)."
                    )
                }
            ]
        )

    return pd.DataFrame(all_rows)


def _safe_sheet_name(name: str) -> str:
    s = re.sub(r"[\[\]:*?/\\]", "_", name).strip("_.") or "Sheet"
    return s[:31]


def default_desktop_output() -> Path:
    return Path.home() / "Desktop" / "ilacrehberi_ilac_listeleri.xlsx"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="ilacrehberi.com reçete/liste sayfaları → tek XLSX (sayfa başına sheet)"
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Çıktı .xlsx (varsayılan: Masaüstü/ilacrehberi_ilac_listeleri.xlsx)",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="İstekler arası saniye (varsayılan 0.35)",
    )
    args = ap.parse_args()
    out: Path = args.output or default_desktop_output()
    delay = float(args.delay)

    out.parent.mkdir(parents=True, exist_ok=True)

    with requests.Session() as session, pd.ExcelWriter(out, engine="openpyxl") as writer:
        for path, sheet in LIST_SOURCES:
            label = f"{urlparse(path).path}"
            try:
                df = scrape_list_url(session, path, delay=delay)
            except requests.RequestException as e:
                print(f"HATA {path}: {e}", file=sys.stderr)
                pd.DataFrame([{"hata": str(e)}]).to_excel(
                    writer, sheet_name=_safe_sheet_name(sheet), index=False
                )
                continue

            sn = _safe_sheet_name(sheet)
            df.to_excel(writer, sheet_name=sn, index=False)
            print(f"{path} → sheet {sn!r}: {len(df)} satır", file=sys.stderr)

    print(f"Yazıldı: {out.resolve()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
