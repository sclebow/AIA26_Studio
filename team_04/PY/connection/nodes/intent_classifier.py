"""LAYER 2 — Intent classification.

Turns human architectural feedback into one of the 12 canonical intents by
MEANING, not exact words. So all of these reach the same intent:

    "it feels too compact" / "give it more breathing room" /
    "open it up" / "the mass feels too dense"        →  increase_openness

    "I want more daylight" / "the courtyard feels dark" /
    "bring more sun into the middle" / "reduce self shading"  →  improve_daylight

Strategy (decided with the user): LLM-FIRST, keyword FALLBACK.
  1. Ask the configured LLM to pick ONE canonical intent (constrained — it may
     only return an id from the fixed list, so it can't hallucinate a category).
  2. If the LLM is unavailable / slow / returns garbage, fall back to the existing
     keyword reason_node so the system never regresses. The keyword layer is the
     safety net, not the primary path.

This module ONLY decides the intent. Choosing the geometry operation is the
Reason Node's job (intent_to_operations.choose_operation).
"""
from __future__ import annotations

import json
import re
from typing import Any

from .architectural_operations import CANONICAL_INTENTS, is_known_intent


# Map the existing keyword reason_node's 12 internal intent ids onto the canonical
# spec vocabulary, so the fallback path speaks the same language as the LLM path.
_REASON_NODE_TO_CANONICAL: dict[str, str] = {
    "daylight": "improve_daylight",
    "environmental": "improve_daylight",
    "views": "improve_views",
    "density": "increase_density",
    "compactness": "increase_openness",
    "height": "adjust_height",
    "openspace": "improve_public_realm",
    "edgebased": "orient_to_edge",
    "courtyard": "increase_openness",
    "shapetransform": "change_character",
    "privacy": "improve_privacy",
    "acoustics": "reduce_noise",
}


_SYSTEM_PROMPT = (
    "You are an architectural design assistant. Classify the user's feedback about a "
    "building into EXACTLY ONE intent id from this fixed list. Understand MEANING, not "
    "keywords: paraphrases, metaphors and feelings all count.\n\n"
    "INTENTS:\n"
    "- increase_openness: feels too compact/dense/heavy/bulky; wants breathing room, "
    "openness, to be opened up, less crowded; OR wants better ventilation/airflow/"
    "cross-ventilation/natural air (opening the form improves airflow — even if the word "
    "'orient' is used, ventilation is increase_openness, NOT orient_to_edge)\n"
    "- improve_daylight: more daylight/sun/light; dark interior or courtyard; reduce "
    "self-shading; brighter\n"
    "- improve_views: better views/outlook; face a park/water/landmark; preserve a view "
    "corridor; open the facade to a view\n"
    "- increase_density: more floor area/FAR/capacity; bigger; denser; expand footprint\n"
    "- reduce_bulk: too bulky/massive/heavy; lighten or slim the mass\n"
    "- strengthen_frontage: stronger/active street frontage; engage the street; retail "
    "frontage; address the road\n"
    "- improve_privacy: more privacy; reduce overlooking; separate public and private; "
    "private residential zones\n"
    "- reduce_noise: away from traffic/road/highway/rail noise; quieter; acoustic comfort; "
    "noise buffer\n"
    "- improve_public_realm: more plaza/public space/green/landscape at ground; pedestrian "
    "realm\n"
    "- change_character: feels too corporate/generic; make it more residential/iconic/"
    "elegant/welcoming/premium; identity\n"
    "- orient_to_edge: orient/align toward a named edge or direction (north/east/south/west) "
    "or a site corner\n"
    "- align_to_context: align to an urban-context feature (metro, park, road) by name\n"
    "- adjust_height: taller/shorter; add or remove floors/stories; raise/lower height\n\n"
    "Reply with STRICT JSON only, no prose:\n"
    '{"intent": "<one id from the list>", "confidence": <0..1>, "reason": "<short why>"}'
)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    # Qwen3 and other reasoning models emit a <think>...</think> block before the
    # answer — strip it so the JSON after it parses.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(text[s : e + 1])
    except json.JSONDecodeError:
        return None


def _classify_llm(prompt: str) -> dict[str, Any] | None:
    """Ask the LLM for one canonical intent. Returns None on any failure so the
    caller falls back to keywords. Constrained: an id outside the list is rejected."""
    try:
        from ..notebook_logic.feedback_reasoning import _get_llm

        llm = _get_llm()
        if llm is None:
            return None
        resp = llm.invoke(
            [{"role": "system", "content": _SYSTEM_PROMPT},
             {"role": "user", "content": f"FEEDBACK: {prompt}\n\nReturn the JSON now."}]
        )
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        parsed = _extract_json(str(content))
        if not parsed:
            return None
        intent = str(parsed.get("intent", "")).strip()
        if not is_known_intent(intent):
            return None  # hallucinated category — reject, fall back
        conf = parsed.get("confidence", 0.7)
        try:
            conf = max(0.0, min(1.0, float(conf)))
        except (TypeError, ValueError):
            conf = 0.7
        return {
            "intent": intent,
            "confidence": conf,
            "reason": str(parsed.get("reason", "")).strip() or CANONICAL_INTENTS[intent],
            "source": "llm",
            "matched": True,
        }
    except Exception:  # noqa: BLE001 — any LLM error → keyword fallback
        return None


def _classify_character(prompt: str) -> dict[str, Any] | None:
    """Consult the EXISTING architectural_character layer. It recognises design
    LANGUAGE (residential/corporate/iconic/elegant/welcoming/premium) the keyword
    reason_node maps poorly. A hit → canonical change_character."""
    try:
        from ..notebook_logic import architectural_character as ac

        c = ac.classify_character(prompt)
        if c and c.get("operations"):
            return {
                "intent": "change_character",
                "confidence": round(float(c.get("confidence", 0.7)), 3),
                "reason": c.get("category") or "architectural character change",
                "source": "character",
                "matched": True,
            }
    except Exception:  # noqa: BLE001
        pass
    return None


def _classify_keywords(prompt: str) -> dict[str, Any] | None:
    """Deterministic fallback using the EXISTING keyword reason_node. Maps its
    internal intent id onto the canonical vocabulary. 'matched' is True only when
    REAL prompt words matched (matched_keywords/synonyms) — the same hallucination
    discriminator feedback_routes uses, so gibberish stays unrecognized.

    Character language (residential/corporate/iconic...) is checked FIRST via the
    character layer, since the keyword reason_node tends to misfile it as density."""
    char = _classify_character(prompt)
    if char is not None:
        return char
    try:
        from ..notebook_logic import reason_node as rn

        results = rn.classify_intent(prompt)
        if not results:
            return None
        top = results[0]
        canonical = _REASON_NODE_TO_CANONICAL.get(top.intent_id)
        if not canonical:
            return None
        matched = bool(getattr(top, "matched_keywords", None) or getattr(top, "matched_synonyms", None))
        return {
            "intent": canonical,
            "confidence": round(float(top.confidence), 3),
            "reason": (top.reasoning[0] if getattr(top, "reasoning", None) else CANONICAL_INTENTS[canonical]),
            "source": "keyword",
            "matched": matched,
        }
    except Exception:  # noqa: BLE001
        return None


def classify_intent(prompt: str) -> dict[str, Any] | None:
    """Classify a prompt into one canonical intent.

    Returns {intent, confidence, reason, source, matched} or None if neither layer
    recognised it. 'matched' = the prompt is a REAL architectural intent (vs gibberish);
    callers use it as the hallucination guard before claiming success.

    LLM-first: a successful LLM classification is trusted (it understood meaning).
    Keyword fallback only runs when the LLM is unavailable or unsure.
    """
    if not prompt or not prompt.strip():
        return None

    llm_result = _classify_llm(prompt)
    if llm_result is not None:
        # Cross-check with keywords: if keywords ALSO matched real words, raise the
        # confidence floor (two independent layers agree → very safe).
        kw = _classify_keywords(prompt)
        if kw and kw["matched"]:
            llm_result["confidence"] = max(llm_result["confidence"], 0.6)
            llm_result["keyword_agreement"] = (kw["intent"] == llm_result["intent"])
        return llm_result

    return _classify_keywords(prompt)
