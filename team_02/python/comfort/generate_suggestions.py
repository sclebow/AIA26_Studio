"""
generate_suggestions — one prioritised, actionable fix per failing sense per room.

Migrated verbatim from the Grasshopper cluster script. Takes the JSON output of
detect_sensorial_conflicts. Logic unchanged; GH inputs became parameters and the
GH output variable `a` became the return value.

NOTE: the GH input here was named `conflicts`; kept identical so the existing
SUGGEST node call site (call_tool("generate_suggestions", {"conflicts": ...}))
works without modification.
"""

import json

try:
    from comfort.sense_model import SENSES, priority_order
except ImportError:  # same-dir fallback
    from sense_model import SENSES, priority_order


def generate_suggestions(conflicts, persona=None, weights_override=None):
    """Return a JSON string of prioritised suggestions for each flagged room.

    Args:
        conflicts: the JSON string returned by detect_sensorial_conflicts.
        persona: persona label; defaults to "Neutral".

    Returns:
        JSON string: {"layoutId", "persona", "totalRoomsAddressed", "improvements": [...]}.
    """
    conflicts_data = None
    try:
        conflicts_data = json.loads(conflicts)
    except Exception:
        return json.dumps({"error": "Invalid conflicts input"})

    flagged_rooms = conflicts_data.get("flaggedRooms", [])
    persona_str = str(persona).strip() if persona else "Neutral"

    SUGGESTIONS = {
        "thermal":   [
            "Upgrade to double or triple glazing to reduce thermal loss",
            "Add thermal mass to stabilize temperature",
            "Add ceiling fan for air circulation"
        ],
        "visual":    [
            "Add larger windows or skylights",
            "Use lighter wall colors",
            "Install task lighting"
        ],
        "acoustic":  [
            "Add rugs and curtains to absorb sound",
            "Install acoustic panels on shared walls",
            "Use solid-core doors"
        ],
        "spatial":   [
            "Remove unnecessary furniture",
            "Use multi-functional furniture",
            "Reorganize layout for better flow"
        ],
        "olfactory": [
            "Upgrade to mixed or mechanical ventilation for active air exchange",
            "Add air-purifying plants",
            "Install extraction fan to support natural ventilation"
        ],
        "tactile":   [
            "Add natural material surfaces (wood, cork)",
            "Introduce soft flooring in bare-foot areas",
            "Add textured wall treatments"
        ],
    }

    # Priority = the user's senses ranked by their real onboarding weights
    # (highest first). No persona categories: with no profile, priority_order()
    # falls back to the canonical SENSES order.
    weights = None
    if weights_override:
        try:
            raw = json.loads(weights_override) if isinstance(weights_override, str) else weights_override
            if all(s in raw for s in SENSES):
                weights = {s: float(raw[s]) for s in SENSES}
        except Exception:
            weights = None
    priority = priority_order(weights)

    results = []
    for flagged in flagged_rooms:
        conflict_senses = []
        for c in flagged.get("conflicts", []):
            for s in ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]:
                if s in c and s not in conflict_senses:
                    conflict_senses.append(s)
        sorted_senses = sorted(conflict_senses, key=lambda s: priority.index(s) if s in priority else 99)
        suggestions = [
            {
                "sense": s,
                "priority": priority.index(s) + 1 if s in priority else 99,
                "suggestion": SUGGESTIONS[s][0],
                "alternatives": SUGGESTIONS[s][1:]
            }
            for s in sorted_senses if s in SUGGESTIONS
        ]
        if suggestions:
            results.append({
                "roomId":   flagged.get("roomId"),
                "roomName": flagged.get("roomName"),
                "persona":  persona_str,
                "suggestions": suggestions
            })

    return json.dumps({
        "layoutId":            conflicts_data.get("layoutId", "?"),
        "persona":             persona_str,
        "totalRoomsAddressed": len(results),
        "improvements":        results
    })
