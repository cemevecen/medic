"""
OpenAI API uyumlu uç noktalar (OpenAI, OpenRouter, Together, Azure OpenAI uyumlu proxy vb.).

Tek tip: Chat Completions + JSON çıktı. Anahtar .env veya Streamlit oturumundan gelir.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def resolve_openai_compat_config(overrides: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
    """
    overrides: api_key, base_url, model (boş değerler env ile tamamlanır).
    api_key yoksa None döner.
    """
    o = dict(overrides or {})
    api_key = str(o.get("api_key") or os.getenv("OPENAI_API_KEY", "") or "").strip()
    if not api_key:
        return None
    base = str(o.get("base_url") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
    base = base.rstrip("/")
    model = str(o.get("model") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    if not model:
        model = "gpt-4o-mini"
    return {"api_key": api_key, "base_url": base, "model": model}


def chat_json_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 2500,
    temperature: float = 0.1,
    timeout: float = 120.0,
) -> str:
    """Sistem+kullanıcı mesajı; mümkünse JSON modu. Ham asistan metnini döndürür."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        r = client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
    except Exception:
        r = client.chat.completions.create(**kwargs)
    return (r.choices[0].message.content or "").strip()
