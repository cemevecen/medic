"""
Türkiye il / ilçe listesi — EczaneAPI widget URL slug'ları ile uyumlu (ASCII slug).
Veri kaynağı: enisbt/turkey-cities (MIT), `data/turkey_cities_counties.json`.
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "turkey_cities_counties.json"


def slug_tr(s: str) -> str:
    """Türkçe karakterleri EczaneAPI tarzı URL slug'ına çevirir (küçük harf, ASCII)."""
    t = (s or "").strip().lower()
    for a, b in (
        ("ş", "s"),
        ("ğ", "g"),
        ("ü", "u"),
        ("ö", "o"),
        ("ç", "c"),
        ("ı", "i"),
        ("â", "a"),
        ("î", "i"),
        ("û", "u"),
    ):
        t = t.replace(a, b)
    return t.replace(" ", "-")


def pretty_label(s: str) -> str:
    if not (s or "").strip():
        return ""
    return str(s).strip().capitalize()


def load_turkey_geo_rows() -> list[tuple[str, str, list[str]]]:
    """
    (il_etiketi, il_slug, ilçe_adları_ham) listesi; il_etiketi gösterim için.
    """
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    rows: list[tuple[str, str, list[str]]] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        cs = slug_tr(name)
        counties = c.get("counties") or []
        if not isinstance(counties, list):
            counties = []
        co_list = [str(x).strip() for x in counties if str(x).strip()]
        rows.append((pretty_label(name), cs, co_list))
    rows.sort(key=lambda r: r[0].casefold())
    return rows
