"""
CONFLICT_REASONER node — explains WHY each sense failed in each room.
References layout attributes (orientation, materials, adjacency, ventilation).
Does NOT suggest fixes; that is SUGGEST's job. Writes conflict_reasoning.
"""

from __future__ import annotations
import json
from _runtime.llm import call_llm_simple


_SYSTEM_PROMPT = """\
You are an architectural comfort diagnostician.

You receive a list of sensorial conflicts (senses that scored below the persona's
threshold in specific rooms), the layout's physical attributes, and the score
interpretation from the previous step.

Your ONLY job: explain WHY each conflict occurred. What caused it?

Root causes to consider:
  thermal   → orientation (sun angle), glazingRatio, shading, ventilationType
  acoustic  → adjacent room types (noisy kitchen? corridor?), partition materials,
              doors sharing walls with loud spaces, room geometry
  visual    → glazingRatio, window orientation, glare risk, deep-plan rooms
  spatial   → room dimensions, ceiling height, furniture density, circulation width
  olfactory → adjacent wet rooms, ventilation path, air movement between spaces
  tactile   → surface materials, floor finishes, thermal mass

Rules:
  - One short paragraph per failing room (max 3 sentences)
  - Reference SPECIFIC layout attributes (orientation, glazingRatio, adjacency, etc.)
  - Do NOT suggest fixes. Do NOT repeat the scores. Just explain the cause.
  - Plain language. No markdown headers. No JSON.

CONFLICTS:
{conflicts_summary}

LAYOUT ATTRIBUTES (relevant rooms):
{layout_attributes}

SCORE INTERPRETATION (context):
{score_interpretation}
"""


def _format_conflicts(conflicts_json: str) -> str:
    if not conflicts_json:
        return "(no conflicts)"
    try:
        data = json.loads(conflicts_json)
        flagged = data.get("flaggedRooms", [])
        if not flagged:
            return "no conflicts detected"
        lines = []
        for room in flagged:
            name = room.get("roomName", "?")
            senses = []
            for c in room.get("conflicts", []):
                for s in ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]:
                    if s in c and s not in senses:
                        senses.append(s)
            lines.append(f"{name}: {', '.join(senses)}")
        return "\n".join(lines)
    except Exception:
        return conflicts_json


def _extract_room_attributes(layout_json_string: str, conflicted_rooms: list[str]) -> str:
    """Pull relevant attributes for rooms that have conflicts."""
    if not layout_json_string:
        return "(no layout)"
    try:
        layout = json.loads(layout_json_string)
        lines = []
        for room in layout.get("rooms", []):
            name = room.get("name", "")
            if conflicted_rooms and not any(cr.lower() in name.lower() for cr in conflicted_rooms):
                continue  # only include rooms with conflicts
            attrs = room.get("attributes", {})
            lines.append(
                f"{name}: orientation={room.get('orientation','?')}, "
                f"glazingRatio={attrs.get('glazingRatio','?')}, "
                f"ventilation={attrs.get('ventilationType','?')}, "
                f"roomType={room.get('roomType','?')}"
            )
        return "\n".join(lines) if lines else "(no attribute data)"
    except Exception:
        return "(layout parse error)"


def build_conflict_reasoner_node(llm):
    """Return the conflict_reasoner node function, capturing the LLM instance."""

    def conflict_reasoner_node(state: dict) -> dict:
        conflicts_json: str = state.get("last_conflicts_json", "")
        score_interpretation: str = state.get("score_interpretation", "")
        layout_json_string: str = state.get("layout_json_string", "")

        print("[conflict_reasoner] Reasoning about root causes...")

        # Extract conflicted room names for targeted attribute lookup
        conflicted_rooms: list[str] = []
        try:
            data = json.loads(conflicts_json)
            conflicted_rooms = [r.get("roomName", "") for r in data.get("flaggedRooms", [])]
        except Exception:
            pass

        conflicts_summary = _format_conflicts(conflicts_json)
        layout_attributes = _extract_room_attributes(layout_json_string, conflicted_rooms)

        system = _SYSTEM_PROMPT.format(
            conflicts_summary=conflicts_summary,
            layout_attributes=layout_attributes,
            score_interpretation=score_interpretation or "(not available)",
        )

        reasoning = call_llm_simple(llm, system, "Explain why these conflicts occurred.")
        print(f"[conflict_reasoner] Reasoning: {reasoning[:80]}...")

        return {
            **state,
            "conflict_reasoning": reasoning,
        }

    return conflict_reasoner_node
