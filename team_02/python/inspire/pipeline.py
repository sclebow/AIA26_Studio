"""
pipeline.py — VLM aesthetic analysis + sense-tagged Unsplash fetch, plus the
profile-review chat reply. Extracted verbatim from sensi_pyqt.py so the FastAPI
backend can reuse it without importing PyQt.

The public entry points are:
  - run_inspire_round(...)   -> one moodboard round (mirrors InspireWorker.run)
  - profile_chat_reply(...)  -> one profile-chat answer (mirrors ProfileChatWorker.run)

Both accept an optional `progress` callback (str -> None) used to surface the
loading-overlay status strings; the API streams these over SSE.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# VLM aesthetic analysis
# ═══════════════════════════════════════════════════════════════════════════════

def _vlm_analyze(llm, images_b64: list, text_desc: str) -> str:
    from langchain_core.messages import HumanMessage
    SYSTEM = (
        "You are a spatial aesthetic analyst. Extract a rich sensory and visual "
        "profile from the provided reference images and/or description.\n\n"
        "Capture:\n"
        "  - Color palette - dominant hues, temperature (warm/cool), saturation\n"
        "  - Light quality - source (natural/artificial), quality (soft/harsh/diffuse), tone\n"
        "  - Materials & textures - wood, stone, concrete, fabric, metal, plaster, plant\n"
        "  - Spatial mood - intimate/open, minimal/layered, calm/dynamic, raw/refined\n"
        "  - Atmosphere - time of day feel, level of cosiness vs grandeur\n\n"
        "Write a specific, grounded aesthetic profile in 120-150 words. "
        "No lists. No headers. Just a flowing description."
    )
    if images_b64:
        content = [{"type": "text", "text": f"{SYSTEM}\n\nUser description: {text_desc}"}]
        for b64 in images_b64[:4]:
            content.append({"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        try:
            return llm.invoke([HumanMessage(content=content)]).content.strip()
        except Exception:
            pass  # fall through to text-only
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": text_desc or "minimalist interior, warm and natural"},
    ]
    try:
        return llm.invoke(messages).content.strip()
    except Exception:
        return f"Aesthetic preference: {text_desc}"


# ═══════════════════════════════════════════════════════════════════════════════
# Sense-tagged query generation
# ═══════════════════════════════════════════════════════════════════════════════

_SENSE_DESCRIPTORS = {
    "thermal":   "warmth, temperature, sun exposure, radiant heat, cozy warmth, fireplace",
    "visual":    "light quality, color palette, brightness, shadow play, visual texture",
    "acoustic":  "sound absorption, quiet atmosphere, soft materials, echo, acoustic quality",
    "spatial":   "spatial volume, ceiling height, openness, layout, proportion, flow",
    "olfactory": "natural materials, plants, wood, earthy quality, fresh air, greenery",
    "tactile":   "material texture, roughness, softness, tactile surfaces, woven fabric",
}
_SENSE_ORDER = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]


def _gen_queries_sensed(llm, analysis: str, prev_desc: str = "", n_per_sense: int = 2) -> list:
    """Return a list of (query_str, sense_str) tuples - n_per_sense per sense."""
    from langchain_core.messages import HumanMessage
    extra  = f"\n\nThe user particularly liked: {prev_desc}" if prev_desc else ""
    sense_lines = "\n".join(
        f'  - {s}: focus on {d}' for s, d in _SENSE_DESCRIPTORS.items()
    )
    example_obj = (
        '{"thermal":["q1","q2"],"visual":["q3","q4"],"acoustic":["q5","q6"],'
        '"spatial":["q7","q8"],"olfactory":["q9","q10"],"tactile":["q11","q12"]}'
    )
    prompt = (
        f"Aesthetic analysis:\n{analysis}{extra}\n\n"
        f"Generate {n_per_sense} Unsplash search queries per sensory category to find interior "
        f"architectural spaces matching this aesthetic.\n"
        f"RULES: Every query MUST describe an interior room, residential space, or architectural scene. "
        f"No people, no landscapes, no food, no fashion, no abstract imagery.\n"
        f"Each query = 3-5 words.\n\n"
        f"Sensory categories:\n{sense_lines}\n\n"
        f"Return ONLY a JSON object matching this shape exactly:\n{example_obj}"
    )
    defaults = {
        "thermal":   ["warm sunlit interior cozy", "fireplace living room warmth"],
        "visual":    ["diffuse natural light minimal interior", "bright airy architectural space"],
        "acoustic":  ["quiet library soft materials interior", "calm reading nook absorptive"],
        "spatial":   ["open plan high ceiling loft", "intimate courtyard spatial volume"],
        "olfactory": ["indoor plants greenery natural material", "wood stone earthy interior"],
        "tactile":   ["rough concrete tactile texture interior", "woven fabric soft surface room"],
    }
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        m = re.search(r"\{.*\}", resp.content, re.DOTALL)
        if m:
            parsed = json.loads(m.group())
            if isinstance(parsed, dict):
                result = []
                for sense in _SENSE_ORDER:
                    qs = parsed.get(sense, defaults[sense])
                    for q in (qs or defaults[sense])[:n_per_sense]:
                        result.append((str(q), sense))
                return result
    except Exception:
        pass
    result = []
    for sense in _SENSE_ORDER:
        for q in defaults[sense][:n_per_sense]:
            result.append((q, sense))
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Unsplash fetch
# ═══════════════════════════════════════════════════════════════════════════════

_SENSE_FALLBACKS = {
    "thermal":   "warm sunlit room interior",
    "visual":    "natural light minimal interior",
    "acoustic":  "quiet cozy reading nook interior",
    "spatial":   "open loft architectural space",
    "olfactory": "indoor plants greenery room",
    "tactile":   "wood texture material interior",
}
_SENSE_EXTRAS = [
    ("minimalist interior warm light",      "visual"),
    ("cozy residential room texture",       "tactile"),
    ("serene architectural space calm",     "spatial"),
    ("warm wood interior sunlight",         "thermal"),
    ("calm interior soft diffuse light",    "acoustic"),
    ("earthy natural material room",        "olfactory"),
]


def _fetch_unsplash_sensed(queries_with_senses: list, per_query: int = 2,
                           target: int = 12) -> tuple:
    """Fetch per_query images per (query, sense); retry empty senses; pad to target."""
    import httpx
    key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    if not key:
        return [], [], []

    urls, descs, sense_tags = [], [], []
    sense_counts: dict = {}

    def _call(q: str, sense: str, n: int) -> int:
        added = 0
        try:
            resp = httpx.get(
                "https://api.unsplash.com/search/photos",
                params={"query": q, "per_page": n, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {key}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    urls.append(r["urls"]["small"])
                    descs.append(r.get("alt_description") or q)
                    sense_tags.append([sense])
                    sense_counts[sense] = sense_counts.get(sense, 0) + 1
                    added += 1
        except Exception:
            pass
        return added

    # Primary pass
    for q, sense in queries_with_senses:
        _call(q, sense, per_query)

    # Retry senses that returned 0 images
    for sense in _SENSE_ORDER:
        if sense_counts.get(sense, 0) == 0 and len(urls) < target:
            _call(_SENSE_FALLBACKS[sense], sense, 2)

    # Generic top-up if still short of target
    for q, sense in _SENSE_EXTRAS:
        if len(urls) >= target:
            break
        _call(q, sense, target - len(urls))

    return urls[:target], descs[:target], sense_tags[:target]


# ═══════════════════════════════════════════════════════════════════════════════
# Public orchestrators
# ═══════════════════════════════════════════════════════════════════════════════

def run_inspire_round(
    llm,
    text: str,
    b64s: list,
    existing_analysis: str,
    round_num: int,
    refine_desc: str = "",
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """Run one moodboard round. Mirrors InspireWorker.run.

    Returns a dict: {ok, round, urls, descs, senses, analysis} or {ok: False, error}.
    `progress` (if given) is called with each loading-overlay status string.
    """
    def _emit(msg: str) -> None:
        if progress:
            progress(msg)

    try:
        # Step 1 - VLM (first round only; subsequent rounds reuse analysis)
        _emit("reading your aesthetic...")
        analysis = existing_analysis or _vlm_analyze(llm, b64s, text)

        # Step 2 - Sense-tagged query generation (1 query per sense, 6 total)
        _emit("building search queries...")
        queries_sensed = _gen_queries_sensed(llm, analysis, prev_desc=refine_desc, n_per_sense=1)

        # Step 3 - Fetch 2 images per query = 12 total for the 3x4 grid
        _emit("gathering images...")
        urls, descs, senses = _fetch_unsplash_sensed(queries_sensed, per_query=2, target=12)

        return {
            "ok":       True,
            "round":    round_num,
            "urls":     urls,
            "descs":    descs,
            "senses":   senses,
            "analysis": analysis,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


_PROFILE_CHAT_SYSTEM = (
    "You are Sensi, helping the user understand and optionally refine their comfort profile.\n"
    "Speak warmly and specifically - reference actual numbers from their profile.\n\n"
    "You can:\n"
    "  - Explain how each comfort weight was derived from quiz answers and moodboard picks\n"
    "  - Explain the formula: C(room) = sum of w(s) x raw(room, s)\n"
    "  - Explain what 'evidence baseline' means and why a deviation matters\n"
    "  - Help the user reflect on whether something feels wrong\n"
    "  - Note requested changes (but explain major edits require a fresh session)\n\n"
    "Keep replies concise - 2-4 sentences. No bullet points. No markdown."
)


def profile_chat_reply(llm, profile: dict, text: str) -> dict:
    """One profile-review chat answer. Mirrors ProfileChatWorker.run.

    Returns {ok: True, message} or {ok: False, error}.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    try:
        profile_block = json.dumps(profile, indent=2, ensure_ascii=False)
        system_full   = f"{_PROFILE_CHAT_SYSTEM}\n\nCurrent profile:\n{profile_block}"
        messages = [
            SystemMessage(content=system_full),
            HumanMessage(content=text),
        ]
        reply = llm.invoke(messages).content.strip()
        return {"ok": True, "message": reply}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
