"""
Gemini model kimlikleri ve geri dönüş zinciri.

Ortam: GEMINI_MODEL (isteğe bağlı), ardından sabit zincir; 404’te sıradaki denenir.
"""

from __future__ import annotations

import os
from typing import Dict, List, Tuple

DEFAULT_GEMINI_CHAIN: Tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
)

DEPRECATED_MODEL_IDS: Dict[str, str] = {
    "gemini-2.0-flash-exp": "gemini-2.5-flash",
    "gemini-2.0-flash-thinking-exp-01-21": "gemini-2.5-flash",
    "gemini-2.0-flash-thinking-exp-1219": "gemini-2.5-flash",
    "gemini-exp-1206": "gemini-2.5-flash",
    "gemini-1.5-flash-latest": "gemini-1.5-flash",
    "gemini-1.5-pro-latest": "gemini-1.5-pro",
}


def normalize_model(name: str) -> str:
    """Ortam / kullanıcı girdisini API model kimliğine çevirir (büyük-küçük harf, tırnak, models/ öneki)."""
    if not name or not str(name).strip():
        return ""
    n = str(name).strip().strip('"').strip("'").strip()
    n = n.replace("models/", "", 1).strip()
    low = n.lower()
    for k, v in DEPRECATED_MODEL_IDS.items():
        if low == k.lower():
            return v
    if "flash-exp" in low or "thinking-exp" in low:
        return "gemini-2.5-flash"
    return n


def model_chain() -> List[str]:
    seen: set = set()
    out: List[str] = []
    raw = (os.getenv("GEMINI_MODEL") or "").strip()
    first = normalize_model(raw) if raw else ""
    candidates = (first, *DEFAULT_GEMINI_CHAIN) if first else DEFAULT_GEMINI_CHAIN
    for m in candidates:
        nm = normalize_model(m) if m else ""
        if nm and nm not in seen:
            seen.add(nm)
            out.append(nm)
    return out or ["gemini-2.5-flash"]


def model_missing_error(exc: Exception) -> bool:
    t = str(exc).lower()
    return (
        "404" in str(exc)
        or "not found" in t
        or "is not supported" in t
        or "invalid model" in t
    )
