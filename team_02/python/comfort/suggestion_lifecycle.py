"""
suggestion_lifecycle — keep the agent's advice and what it actually did in sync.

When an edit fulfils a standing suggestion (e.g. "Add rugs and curtains to absorb sound"
in the Living Room, and the user adds a rug there), that suggestion should be crossed off
the list — not silently dropped. The match is by ROOM + SENSE: an edit whose diff affects a
room's flagged sense fulfils that room's suggestion for that sense.

Two pure helpers, no state:
  - newly_applied(diffs, suggestions_json)  -> [{roomName, sense}] fulfilled by these diffs
  - overlay_applied(suggestions_json, list) -> suggestions_json with applied:true flags

apply_edits accumulates the {roomName, sense} list across the session; the API contract
overlays the flags onto whatever suggestions it surfaces, so the panel strikes them through.
"""

from __future__ import annotations
import json


def _diff_senses(diff: dict) -> set:
    """The single senses a diff touches ('tactile+acoustic' -> {'tactile','acoustic'})."""
    return {s for s in (diff.get("sense_affected") or "").replace("+", " ").split() if s}


def newly_applied(diffs, suggestions_json: str) -> list:
    """Suggestions (room + sense) fulfilled by the given edit diffs."""
    try:
        improvements = json.loads(suggestions_json).get("improvements", []) if suggestions_json else []
    except Exception:
        improvements = []
    if not improvements:
        return []
    by_room = {imp.get("roomName"): {s.get("sense") for s in imp.get("suggestions", [])}
               for imp in improvements}
    out = []
    for d in diffs or []:
        if not d:
            continue
        room = d.get("room_name")
        if room not in by_room:
            continue
        for sense in _diff_senses(d) & by_room[room]:
            entry = {"roomName": room, "sense": sense}
            if entry not in out:
                out.append(entry)
    return out


def overlay_applied(suggestions_json: str, applied) -> str:
    """Flag each suggestion in `applied` (matched by room + sense) with applied:true."""
    try:
        data = json.loads(suggestions_json) if suggestions_json else None
    except Exception:
        return suggestions_json
    if not data or not data.get("improvements"):
        return suggestions_json
    done = {(a.get("roomName"), a.get("sense")) for a in (applied or [])}
    for imp in data.get("improvements", []):
        room = imp.get("roomName")
        for s in imp.get("suggestions", []):
            s["applied"] = (room, s.get("sense")) in done
    return json.dumps(data)
