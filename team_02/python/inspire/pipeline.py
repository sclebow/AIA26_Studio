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


def _gen_queries_sensed(llm, analysis: str, prev_desc: str = "", n_per_sense: int = 2,
                        seed_context: str = "") -> list:
    """Return a list of (query_str, sense_str) tuples - n_per_sense per sense.

    `seed_context` (from the quiz) and `prev_desc` (what the user leaned toward / said this
    round) personalise the queries so the board reflects them AND varies between rounds."""
    from langchain_core.messages import HumanMessage
    extra  = f"\n\nThe user particularly liked: {prev_desc}" if prev_desc else ""
    seed   = f"\n\nWhat we already know about them: {seed_context}" if seed_context else ""
    sense_lines = "\n".join(
        f'  - {s}: focus on {d}' for s, d in _SENSE_DESCRIPTORS.items()
    )
    example_obj = (
        '{"thermal":["q1","q2"],"visual":["q3","q4"],"acoustic":["q5","q6"],'
        '"spatial":["q7","q8"],"olfactory":["q9","q10"],"tactile":["q11","q12"]}'
    )
    prompt = (
        f"Aesthetic analysis:\n{analysis}{seed}{extra}\n\n"
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

# Curated, license-clean interior images (verified Unsplash CDN URLs, one per
# sense) used as a FLOOR whenever the live API is rate-limited, timing out, down,
# or unkeyed — so the grid never collapses to a broken 2-3 cells. These are plain
# image-CDN URLs (no API call, no auth), so they render even with zero quota.
# Expand this list with more curated URLs to raise the guaranteed offline floor
# toward a full 12-cell grid during a hard outage.
_FALLBACK_POOL = [
    ("https://images.unsplash.com/photo-1696814543693-31fcf942ccb7?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400", "thermal"),
    ("https://images.unsplash.com/photo-1552290403-015b13a5221c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",     "visual"),
    ("https://images.unsplash.com/photo-1617326021886-53d6be1d7154?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "acoustic"),
    ("https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "spatial"),
    ("https://images.unsplash.com/photo-1571977796766-578d484a6c25?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "olfactory"),
    ("https://images.unsplash.com/photo-1579761804843-f997ade7fa35?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "tactile"),
    # Second curated set (verified CDN URLs) so a full 12-cell grid survives a hard outage.
    ("https://images.unsplash.com/photo-1631510390389-c1e4fb20ff31?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "thermal"),
    ("https://images.unsplash.com/photo-1625585598750-3535fe40efb3?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "visual"),
    ("https://images.unsplash.com/photo-1727707185480-a50e6090b58c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "acoustic"),
    ("https://images.unsplash.com/photo-1505873242700-f289a29e1e0f?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "spatial"),
    ("https://images.unsplash.com/photo-1521334884684-d80222895322?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "olfactory"),
    ("https://images.unsplash.com/photo-1770573322210-204dea84450f?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=400",  "tactile"),
]


def _fill_from_fallback(urls: list, descs: list, sense_tags: list,
                        target: int, diag: dict, seen: Optional[set] = None) -> None:
    """Top the grid up to `target` from the curated fallback pool (no duplicates)."""
    seen = seen if seen is not None else set(urls)
    for url, sense in _FALLBACK_POOL:
        if len(urls) >= target:
            break
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
        descs.append(f"{sense} interior")
        sense_tags.append([sense])
        diag["fallback_used"] = True


# Cross-round result cache: query -> list[(url, desc)]. A cache hit serves images with
# NO HTTP request, so re-running onboarding (demo rehearsal) never re-drains the hourly
# quota. Process-lifetime only — fine for a session/demo.
_QUERY_CACHE: dict = {}

# Fetch a DEEP pool per query (one request, more results) and cache it keyed by query, so
# excluding already-shown images across rounds still leaves fresh ones — that's what makes
# each round UNIQUE without burning extra requests (3 fresh/round from a pool of ~10).
_POOL_PER_QUERY = 10


def _unsplash_search(key: str, q: str, pool: int = _POOL_PER_QUERY, timeout: float = 10.0) -> tuple:
    """One Unsplash search — pure I/O so it is safe to run in a worker thread. Fetches a
    deep `pool` of candidates. Returns (results | None, status_code, ratelimit_remaining)
    where results is a list of (url, desc)."""
    import httpx
    try:
        resp = httpx.get(
            "https://api.unsplash.com/search/photos",
            params={"query": q, "per_page": max(1, pool), "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {key}"},
            timeout=timeout,
        )
        rem = resp.headers.get("X-Ratelimit-Remaining")
        if resp.status_code == 200:
            res = [(r["urls"]["small"], r.get("alt_description") or q)
                   for r in resp.json().get("results", [])]
            return res, 200, rem
        return None, resp.status_code, rem
    except Exception as exc:
        return None, -1, f"{type(exc).__name__}: {exc}"


def _fetch_unsplash_sensed(queries_with_senses: list, per_query: int = 3,
                           target: int = 12, max_requests: int = 12,
                           exclude_urls=None) -> tuple:
    """Fetch per_query images per (query, sense); retry empty senses; pad to target.

    Hardened so the moodboard grid stays at ~12 options every round, stays fast, and is
    UNIQUE across rounds:
      - the primary pass (one query per sense) runs in PARALLEL (~1s vs ~4s serial);
      - each query caches a DEEP pool, and `exclude_urls` (the URLs already shown earlier
        this session) is seeded into `seen` so every round draws FRESH images — no repeats;
      - the cache means a re-run/identical query costs zero requests and never re-drains the
        demo-tier 50-req/hour cap;
      - a per-round BUDGET + early stop on a depleted rate limit avoid doomed fan-out;
      - every HTTP failure is LOGGED; the grid is FLOORED from a 12-URL curated pool.

    Returns (urls, descs, sense_tags, diag) where diag reports what happened.
    """
    import concurrent.futures as _futures
    diag = {"requests": 0, "ok": 0, "failed": 0, "rate_limited": False,
            "fallback_used": False, "key_present": False}
    urls, descs, sense_tags = [], [], []
    sense_counts: dict = {}

    key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    if not key:
        print("[inspire] UNSPLASH_ACCESS_KEY is not set - serving the curated fallback moodboard.")
        _fill_from_fallback(urls, descs, sense_tags, target, diag, seen=set(exclude_urls or []))
        return urls[:target], descs[:target], sense_tags[:target], diag

    diag["key_present"] = True
    seen: set = set(exclude_urls or [])   # cross-round exclusion → unique options each round

    def _ingest(results, sense, limit) -> int:
        """Take up to `limit` not-yet-seen items from a query's pool."""
        added = 0
        for u, desc in results or []:
            if added >= limit:
                break
            if u in seen:
                continue
            seen.add(u)
            urls.append(u); descs.append(desc); sense_tags.append([sense])
            sense_counts[sense] = sense_counts.get(sense, 0) + 1
            added += 1
        return added

    def _note_rate(status, rem) -> None:
        if status in (401, 403, 429):
            diag["rate_limited"] = True
        if rem is not None and str(rem).strip().lstrip("-").isdigit() and int(rem) <= 0:
            diag["rate_limited"] = True

    def _budget_left() -> bool:
        return diag["requests"] < max_requests and not diag["rate_limited"]

    # ── Primary pass — PARALLEL + cache-aware. Cache hits cost no request. ──────────
    live = []
    for q, sense in queries_with_senses:
        if q in _QUERY_CACHE:
            _ingest(_QUERY_CACHE[q], sense, per_query)
        else:
            live.append((q, sense))
    live = live[:max_requests]
    if live:
        with _futures.ThreadPoolExecutor(max_workers=min(6, len(live))) as ex:
            futs = {ex.submit(_unsplash_search, key, q): (q, sense) for q, sense in live}
            for fut in _futures.as_completed(futs):
                q, sense = futs[fut]
                diag["requests"] += 1
                results, status, rem = fut.result()
                if status == 200:
                    diag["ok"] += 1
                    _QUERY_CACHE[q] = results
                    _ingest(results, sense, per_query)
                else:
                    diag["failed"] += 1
                    print(f"[inspire] Unsplash {status} for query {q!r} (ratelimit-remaining={rem})")
                _note_rate(status, rem)

    # Cache-aware serial fetch for the (rare) retry + top-up passes.
    def _call_cached(q: str, sense: str, limit: int) -> int:
        if q in _QUERY_CACHE:
            return _ingest(_QUERY_CACHE[q], sense, limit)
        if not _budget_left():
            return 0
        diag["requests"] += 1
        results, status, rem = _unsplash_search(key, q)
        if status == 200:
            diag["ok"] += 1
            _QUERY_CACHE[q] = results
            _note_rate(status, rem)
            return _ingest(results, sense, limit)
        diag["failed"] += 1
        _note_rate(status, rem)
        print(f"[inspire] Unsplash {status} for query {q!r} (ratelimit-remaining={rem})")
        return 0

    # Retry senses that returned 0 images (only while budget + quota remain).
    for sense in _SENSE_ORDER:
        if len(urls) >= target or not _budget_left():
            break
        if sense_counts.get(sense, 0) == 0:
            _call_cached(_SENSE_FALLBACKS[sense], sense, per_query)

    # Generic top-up if still short of target.
    for q, sense in _SENSE_EXTRAS:
        if len(urls) >= target or not _budget_left():
            break
        _call_cached(q, sense, target - len(urls))

    # Floor: never let the grid collapse — pad from the curated fallback pool.
    if len(urls) < target:
        _fill_from_fallback(urls, descs, sense_tags, target, diag, seen=seen)

    if diag["failed"] or diag["rate_limited"] or diag["fallback_used"]:
        print(f"[inspire] fetch summary: {len(urls)} images "
              f"(requests={diag['requests']} ok={diag['ok']} failed={diag['failed']} "
              f"rate_limited={diag['rate_limited']} fallback_used={diag['fallback_used']} "
              f"cache={len(_QUERY_CACHE)})")

    return urls[:target], descs[:target], sense_tags[:target], diag


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
    exclude_urls=None,
    seed_context: str = "",
) -> dict:
    """Run one moodboard round. Mirrors InspireWorker.run.

    Returns a dict: {ok, round, urls, descs, senses, analysis} or {ok: False, error}.
    `progress` (if given) is called with each loading-overlay status string.
    `exclude_urls` are already-shown URLs to skip (unique-per-round); `seed_context` is the
    quiz-derived seed so round 1 can build a relevant board with NO typed description.
    """
    def _emit(msg: str) -> None:
        if progress:
            progress(msg)

    try:
        # Step 1 - VLM (first round only; subsequent rounds reuse analysis). When the user
        # typed nothing, seed the aesthetic from the quiz so a relevant board still appears.
        _emit("reading your aesthetic...")
        analysis = existing_analysis or _vlm_analyze(llm, b64s, text or seed_context)

        # Step 2 - Sense-tagged query generation (1 query per sense, 6 total). seed_context
        # (quiz) + refine_desc (this round's lean / "say more") personalise + vary the queries.
        _emit("building search queries...")
        queries_sensed = _gen_queries_sensed(llm, analysis, prev_desc=refine_desc,
                                             n_per_sense=1, seed_context=seed_context)

        # Step 3 - Fetch images (per_query=3 gives margin so a couple of failed queries still
        # fill the 12-cell grid); resilient + floored + UNIQUE-per-round (exclude_urls).
        _emit("gathering images...")
        urls, descs, senses, diag = _fetch_unsplash_sensed(
            queries_sensed, per_query=3, target=12, exclude_urls=exclude_urls)

        return {
            "ok":            True,
            "round":         round_num,
            "urls":          urls,
            "descs":         descs,
            "senses":        senses,
            "analysis":      analysis,
            "degraded":      bool(diag.get("fallback_used") or diag.get("rate_limited")),
            "fallback_used": bool(diag.get("fallback_used")),
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
