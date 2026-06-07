"""
nodes/utils.py — Shared helpers used across multiple nodes.

Keep this file small and pure: no LLM calls, no MCP calls, no state mutation.
"""

from __future__ import annotations
import json
import re


def unwrap_mcp_result(tool_output: str) -> str:
    """
    MCP tool responses arrive as: {"result": "<json string>"}

    Unwrap the envelope so downstream nodes receive the actual JSON payload,
    not the outer wrapper. Falls back to the original string if the structure
    is unexpected (already unwrapped, or an error string).

    Example:
        input : '{"result": "{\"comfortScores\": {...}}"}'
        output: '{"comfortScores": {...}}'
    """
    try:
        outer = json.loads(tool_output)
        if isinstance(outer, dict) and "result" in outer:
            inner = outer["result"]
            if isinstance(inner, str):
                # Validate that the inner string is well-formed JSON
                json.loads(inner)
                return inner
    except (json.JSONDecodeError, TypeError):
        pass
    return tool_output


def layout_digits(value) -> str:
    """Reduce any layout-id form ('204', 'Layout-204', 'layout_204.json') to its
    digits, or '' if there are none. Lets the frontend id, the JSON layoutId, and
    the filename all match on the numeric part."""
    if not value:
        return ""
    m = re.search(r"\d+", str(value))
    return m.group(0) if m else ""


def persona_display_label(persona_profile: dict) -> str:
    """A human label for OUTPUT only — never a scoring input (comfort weights drive
    scoring). 'Name (role)', else name or role, else 'you'."""
    if not persona_profile:
        return "you"
    name = persona_profile.get("name", "")
    role = persona_profile.get("role", "")
    if name and role:
        return f"{name} ({role})"
    return name or role or "you"


def grounded_extremes(scores_json: str) -> dict | None:
    """Return the TRUE cross-room extremes as a dict, or None if unavailable.

    Keys: worst_room, worst_overall, best_room, best_overall,
          lo_room, lo_sense, lo_val, hi_room, hi_sense, hi_val.
    """
    try:
        rooms = json.loads(scores_json).get("rooms", [])
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None
    rooms = [r for r in rooms if r.get("comfortScores")]
    if not rooms:
        return None

    worst_room = min(rooms, key=lambda r: r.get("overallScore", 1.0))
    best_room  = max(rooms, key=lambda r: r.get("overallScore", 0.0))

    lo_room = lo_sense = hi_room = hi_sense = None
    lo_val, hi_val = 2.0, -1.0
    for r in rooms:
        for sense, val in r.get("comfortScores", {}).items():
            if val < lo_val:
                lo_val, lo_room, lo_sense = val, r.get("roomName", "?"), sense
            if val > hi_val:
                hi_val, hi_room, hi_sense = val, r.get("roomName", "?"), sense

    return {
        "worst_room": worst_room.get("roomName", "?"),
        "worst_overall": worst_room.get("overallScore", 0.0),
        "best_room": best_room.get("roomName", "?"),
        "best_overall": best_room.get("overallScore", 0.0),
        "lo_room": lo_room, "lo_sense": lo_sense, "lo_val": lo_val,
        "hi_room": hi_room, "hi_sense": hi_sense, "hi_val": hi_val,
    }


def grounded_facts(scores_json: str) -> str:
    """Deterministically compute the TRUE cross-room extremes from a scores payload.

    LLM nodes hallucinate comparative claims ("lowest of all rooms", "highest"),
    so we compute them here and hand them over as the ONLY ranking statements the
    model is allowed to make. Returns a short labelled block, or "" if unavailable.
    """
    e = grounded_extremes(scores_json)
    if not e:
        return ""
    return (
        "GROUNDED FACTS (the ONLY cross-room comparative claims you may make - copy verbatim):\n"
        f"  - Lowest-scoring room overall: {e['worst_room']} ({e['worst_overall']:.2f})\n"
        f"  - Highest-scoring room overall: {e['best_room']} ({e['best_overall']:.2f})\n"
        f"  - Lowest single sense in the whole layout: {e['lo_sense']} in {e['lo_room']} ({e['lo_val']:.2f})\n"
        f"  - Highest single sense in the whole layout: {e['hi_sense']} in {e['hi_room']} ({e['hi_val']:.2f})"
    )
