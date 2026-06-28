"""Design-brief extraction for Team 04.

The brief is the agent's *typed comprehension* of a free-text request. Phase 0 of
``BACKEND_PLAN.md`` moves intent understanding out of scattered prompt-parsing and
into one structure that the planner and the shape-generation repair layer read.

This module holds the deterministic, LLM-free fallback extractor. It reproduces
the behaviour the codebase already had (shape/area/rotation regex parsing plus the
``two building`` count heuristic) so that:

- unit tests keep running without any LLM or network access, and
- a live run degrades gracefully to regex parsing when the LLM call fails.

The richer LLM extractor lives in ``decision_engine.OpenAIDecisionEngine.extract_brief``
and returns the same :class:`~agent.models.DesignBrief` shape, only with deeper
comprehension and explicit ``ambiguities``.
"""
from __future__ import annotations

import re
from typing import Any

from .models import BuildingSpec, DesignBrief

# Reuse the existing prompt-parsing helpers. decision_engine never imports this
# module at top level (its only use of the fallback is a function-local import),
# so this direction does not create a circular import.
from .decision_engine import (
    _extract_explicit_building_area_sqm,
    _extract_requested_rotation,
    _infer_requested_building_type,
    _mentions_explicit_building_area,
)


_COURTYARD_SHAPES = {"U", "O", "H"}
_COURTYARD_QUALITY_WORDS = ("quiet", "sunny", "private", "green", "shaded", "lively")
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

# An area unit immediately following a number, so "1200 m²" reads as a size, not
# a count. Covers m²/m2/m^2, sqm, sq m / sq. m, and "square metre(s)/meter(s)".
_AREA_UNIT = r"(?:m²|m2|m\^2|sqm|sq\.?\s*m|square\s*met(?:re|er)s?)"

# A number (digit or word) that refers to "building(s)" within a few words, so
# "two U-shaped buildings" and "place 3 office buildings" both resolve, not just
# the literal "two building" the old heuristic required. The negative lookahead
# stops an area like "1200 m²" from being misread as a 1200-building count.
_COUNT_PATTERN = re.compile(
    r"\b(\d+|one|two|three|four|five)\b(?!\s*" + _AREA_UNIT + r")[\w\s-]{0,25}?buildings?\b",
    flags=re.IGNORECASE,
)


def _detect_building_count(user_prompt: str, layout_payload: dict[str, Any]) -> int:
    explicit = layout_payload.get("target_building_count")
    if isinstance(explicit, int) and explicit >= 1:
        return explicit
    match = _COUNT_PATTERN.search(user_prompt or "")
    if match:
        token = match.group(1).lower()
        value = int(token) if token.isdigit() else _NUMBER_WORDS.get(token, 1)
        if value >= 1:
            return value
    return 1


def _detect_storeys(user_prompt: str) -> int | None:
    match = re.search(
        r"(\d+)\s*(?:-|\s)?\s*(?:storey|storeys|story|stories|floor|floors)",
        user_prompt,
        flags=re.IGNORECASE,
    )
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _detect_use(user_prompt: str) -> str:
    prompt_lower = user_prompt.lower()
    if "mixed use" in prompt_lower or "mixed-use" in prompt_lower:
        return "mixed"
    if "office" in prompt_lower or "commercial" in prompt_lower:
        return "office"
    if "apartment" in prompt_lower or "residential" in prompt_lower or "housing" in prompt_lower:
        return "residential"
    return "residential"


def _detect_courtyard_qualities(user_prompt: str) -> tuple[str, ...]:
    prompt_lower = user_prompt.lower()
    return tuple(word for word in _COURTYARD_QUALITY_WORDS if word in prompt_lower)


def _detect_weights(user_prompt: str) -> dict[str, float]:
    """Nudge objective weights from emphasis words; default to balanced 0.5."""
    prompt_lower = user_prompt.lower()
    weights = {"view_weight": 0.5, "sun_weight": 0.5, "alignment_weight": 0.5}
    if any(word in prompt_lower for word in ("sun", "daylight", "sunlight", "solar")):
        weights["sun_weight"] = 0.7
    if any(word in prompt_lower for word in ("view", "outlook", "vista", "panorama")):
        weights["view_weight"] = 0.7
    if any(word in prompt_lower for word in ("align", "grid", "street-facing", "street facing", "orderly")):
        weights["alignment_weight"] = 0.7
    return weights


def extract_brief_fallback(user_prompt: str, layout_payload: dict[str, Any] | None = None) -> DesignBrief:
    """Build a :class:`DesignBrief` from a prompt using regex only (no LLM)."""
    user_prompt = user_prompt or ""
    layout_payload = layout_payload or {}

    building_count = _detect_building_count(user_prompt, layout_payload)
    shape = _infer_requested_building_type(user_prompt) or "auto"
    area = _extract_explicit_building_area_sqm(user_prompt) if _mentions_explicit_building_area(user_prompt) else None
    storeys = _detect_storeys(user_prompt)
    use = _detect_use(user_prompt)
    rotation = _extract_requested_rotation(user_prompt)
    weights = _detect_weights(user_prompt)

    raw_intents = layout_payload.get("building_intents", [])
    intents = [str(intent).strip() for intent in raw_intents] if isinstance(raw_intents, list) else []

    buildings = []
    for index in range(building_count):
        intent_text = intents[index] if index < len(intents) else ""
        buildings.append(
            BuildingSpec(
                shape_preference=shape,
                footprint_area_sqm=area,
                storeys=storeys,
                use=use,
                intent_text=intent_text,
            )
        )

    courtyard_requested = ("courtyard" in user_prompt.lower()) or (shape in _COURTYARD_SHAPES)

    return DesignBrief(
        building_count=building_count,
        buildings=tuple(buildings),
        courtyard_requested=courtyard_requested,
        courtyard_qualities=_detect_courtyard_qualities(user_prompt),
        parking_requested="parking" in user_prompt.lower(),
        requested_rotation_deg=rotation,
        view_weight=weights["view_weight"],
        sun_weight=weights["sun_weight"],
        alignment_weight=weights["alignment_weight"],
        ambiguities=(),
        source="fallback",
    )


def resolve_brief(
    decision_engine: Any,
    user_prompt: str,
    layout_payload: dict[str, Any] | None = None,
) -> DesignBrief:
    """Prefer the engine's LLM extractor; fall back to regex on any failure.

    The graph's ``extract_brief`` node calls this so the brief is always produced,
    whether or not a live LLM is configured.
    """
    layout_payload = layout_payload or {}
    extractor = getattr(decision_engine, "extract_brief", None)
    if callable(extractor):
        try:
            brief = extractor(user_prompt, layout_payload)
            if isinstance(brief, DesignBrief):
                return brief
        except Exception:
            # Any LLM/parse/network failure degrades to deterministic parsing.
            pass
    return extract_brief_fallback(user_prompt, layout_payload)
