"""LAYER 1 — Direct command detection.

For UNAMBIGUOUS commands the user can issue like a tool ("move 5m north",
"rotate 20 degrees", "add 5 floors", "scale up", "make courtyard larger") we skip
intent classification entirely and map straight to a geometry operation. These are
deterministic, no LLM needed.

This reuses the EXISTING literal parser (feedback_reasoning.parse_action) and the
precise-command detector — it does not re-implement parsing. It only DECIDES whether
a prompt is a direct command, so the orchestrator can short-circuit Layer 2/3.
"""
from __future__ import annotations

import re
from typing import Any


# Verbs/patterns that signal a direct geometry command (vs design feedback). Kept
# small and high-precision — anything not matched here falls through to the intent
# layer, which understands MEANING.
_DIRECT_PATTERNS = [
    r"\bmove\b.*\b(north|south|east|west|left|right|up|down)\b",
    r"\bmove\b.*\d",
    r"\brotate\b.*\d",
    r"\brotate\b\s+(it|the building)?\s*(clockwise|counterclockwise|cw|ccw)\b",
    r"\bscale\b\s*(up|down|to)?\b",
    r"\b(add|remove)\b\s+\d+\s+floors?\b",
    r"\bmake it\b\s+\d+\s+(floors?|storeys?|stories)\b",
    r"\bset\b.*\bfloors?\b",
    r"\b(make|set)\b.*\bheight\b.*\d",
    r"\b(taller|shorter)\b\s+by\s+\d",
    r"\bplace\b.*\b(corner|edge)\b",
]


def is_direct_command(prompt: str) -> bool:
    """True if the prompt is an explicit geometry command (Layer 1)."""
    low = (prompt or "").lower().strip()
    if not low:
        return False
    # Defer to the project's own precise-command detector first (authoritative).
    try:
        from ..routes.feedback_routes import _is_precise_command

        if _is_precise_command(low):
            return True
    except Exception:  # noqa: BLE001
        pass
    return any(re.search(p, low) for p in _DIRECT_PATTERNS)


def parse_direct(prompt: str) -> dict[str, Any] | None:
    """Parse a direct command to an op via the existing literal parser.
    Returns the parser dict ({op, transform, text}) or None if it isn't parseable."""
    try:
        from ..notebook_logic import feedback_reasoning as fr

        action = fr.parse_action(prompt)
        if action and action.get("op") not in (None, "unsupported"):
            return action
    except Exception:  # noqa: BLE001
        pass
    return None
