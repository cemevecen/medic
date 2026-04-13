#!/usr/bin/env python3
"""
ilacrehberi.com İlaç A-Z Fihrist verisini XLSX olarak dışa aktarır.

Kaynak: https://www.ilacrehberi.com/ilac-fihrist/
Tam liste sayfadaki <select><option value="//.../v/.../">…</option> içindedir
(tablo satırları yalnızca “en çok aranan” alt kümesidir).

Kullanım:
  pip install requests beautifulsoup4 pandas openpyxl
  python scripts/export_ilacrehberi_fihrist_xlsx.py -o data/ilacrehberi_fihrist.xlsx

Not: Site içeriği telif / kullanım koşullarına tabidir; makul gecikme ile isteyin.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://www.ilacrehberi.com"
INDEX_PATH = "/ilac-fihrist/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122 Safari/537.36; export_ilacrehberi_fihrist_xlsx/1.0"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def _decode_html(resp: requests.Response) -> str:
    """Sayfa meta charset windows-1254; metinlerin doğru görünmesi için."""
    return resp.content.decode("cp1254", errors="replace")


def collect_fihrist_keys(session: requests.Session) -> list[str]:
    """Ana fihrist sayfasındaki tüm `h=` harf / önek değerlerini toplar."""
    r = session.get(urljoin(BASE, INDEX_PATH), headers=HEADERS, timeout=60)
    r.raise_for_status()
    text = _decode_html(r)
    found = set(re.findall(r"ilac-fihrist/\?h=([^&\"'<>]+)", text))
    # A harfi bazen menüde yok; doğrudan URL ile erişilebiliyor
    found.add("A")
    return sorted(found, key=lambda x: (len(x), x.casefold()))


def fetch_options_for_key(session: requests.Session, h: str) -> list[tuple[str, str]]:
    """Tek bir `h` grubu için (ilaç adı, mutlak URL) listesi."""
    query = urlencode({"h": h, "page": "1"}, encoding="iso-8859-9")
    url = f"{BASE}{INDEX_PATH}?{query}"
    r = session.get(url, headers=HEADERS, timeout=90)
    r.raise_for_status()
    soup = BeautifulSoup(_decode_html(r), "html.parser")
    out: list[tuple[str, str]] = []
    for opt in soup.select('select option[value*="/v/"]'):
        raw = (opt.get("value") or "").strip()
        if not raw:
            continue
        name = opt.get_text(strip=True)
        if not name:
            continue
        if raw.startswith("//"):
            raw = "https:" + raw
        elif raw.startswith("/"):
            raw = urljoin(BASE, raw)
        out.append((name, raw))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="ilacrehberi.com fihrist → XLSX")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("ilacrehberi_fihrist.xlsx"),
        help="Çıktı .xlsx dosyası",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="İstekler arası saniye (varsayılan 0.35)",
    )
    args = p.parse_args()

    rows: list[dict[str, str]] = []
    seen_url: set[str] = set()

    with requests.Session() as session:
        keys = collect_fihrist_keys(session)
        print(f"Fihrist anahtarı sayısı: {len(keys)}", file=sys.stderr)
        for i, h in enumerate(keys, 1):
            try:
                opts = fetch_options_for_key(session, h)
            except requests.RequestException as e:
                print(f"[{i}/{len(keys)}] h={h!r} HATA: {e}", file=sys.stderr)
                continue
            added = 0
            for name, url in opts:
                if url in seen_url:
                    continue
                seen_url.add(url)
                rows.append({"fihrist_grubu": h, "ilac_adi": name, "detay_url": url})
                added += 1
            print(f"[{i}/{len(keys)}] h={h!r} → {len(opts)} seçenek, +{added} yeni", file=sys.stderr)
            time.sleep(max(0.0, float(args.delay)))

    if not rows:
        print("Kayıt toplanamadı.", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_excel(args.output, index=False, sheet_name="fihrist")
    print(f"Toplam satır: {len(df)} → {args.output.resolve()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
