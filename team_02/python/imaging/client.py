"""
imaging/client.py — provider-abstracted text-to-image generation.

generate_image(prompt) -> base64 PNG (no data: prefix). The provider is chosen by
IMAGE_PROVIDER (falls back to LLM_PROVIDER), so Gemini ("google", Nano Banana) and
OpenAI ("openai", gpt-image-1) are A/B-swappable with one .env flip.

Image generation is a SEPARATE API from chat completions — it does NOT go through
_runtime/llm.py. Gemini uses the REST generateContent endpoint (no extra SDK
needed); OpenAI uses the installed `openai` SDK's images API.
"""

from __future__ import annotations
import base64
import os
from typing import Optional

import httpx


def active_provider() -> str:
    return (os.environ.get("IMAGE_PROVIDER") or os.environ.get("LLM_PROVIDER") or "google").strip().lower()


def _require(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def _gemini_image(prompt: str, reference_b64: Optional[str]) -> str:
    """Gemini 'Nano Banana' image generation via REST generateContent."""
    model = os.environ.get("GOOGLE_IMAGE_MODEL", "gemini-2.5-flash-image")
    api_key = _require("GOOGLE_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    parts: list[dict] = [{"text": prompt}]
    if reference_b64:                      # Phase 2: anchor on a prior render
        parts.append({"inlineData": {"mimeType": "image/png", "data": reference_b64}})

    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }
    resp = httpx.post(url, params={"key": api_key}, json=body, timeout=90.0)
    resp.raise_for_status()
    data = resp.json()

    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return inline["data"]
    raise RuntimeError(f"Gemini returned no image (response keys: {list(data.keys())})")


def _openai_image(prompt: str, reference_b64: Optional[str]) -> str:
    """OpenAI gpt-image-1 via the openai SDK. Returns base64 PNG. When a reference
    image is supplied, uses images.edit so the result is anchored on it.

    Quality is pinned (default 'medium') so cost is predictable — gpt-image-1 'high'
    is ~4x the price. Override with OPENAI_IMAGE_QUALITY (low|medium|high)."""
    from openai import OpenAI
    model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
    quality = os.environ.get("OPENAI_IMAGE_QUALITY", "medium")
    client = OpenAI(api_key=_require("OPENAI_API_KEY"))
    if reference_b64:
        img_bytes = base64.b64decode(reference_b64)
        result = client.images.edit(
            model=model,
            image=("reference.png", img_bytes, "image/png"),
            prompt=prompt,
            size="1024x1024",
            quality=quality,
            n=1,
        )
        return result.data[0].b64_json
    result = client.images.generate(model=model, prompt=prompt, size="1024x1024", quality=quality, n=1)
    return result.data[0].b64_json


def generate_image(prompt: str, *, reference_b64: Optional[str] = None) -> str:
    """Generate an image from a prompt; return base64-encoded PNG (no data: prefix)."""
    provider = active_provider()
    if provider == "google":
        return _gemini_image(prompt, reference_b64)
    if provider == "openai":
        return _openai_image(prompt, reference_b64)
    raise ValueError(f"Unsupported IMAGE_PROVIDER: {provider}")
