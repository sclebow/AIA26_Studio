"""
detect_sensorial_conflicts — flag senses scoring below the persona's threshold.

Migrated verbatim from the Grasshopper cluster script. Takes the JSON output of
compute_comfort_scores. Logic unchanged; GH inputs became parameters and the GH
output variable `a` became the return value.
"""

import json


def detect_sensorial_conflicts(scores_json, persona=None):
    """Return a JSON string of rooms whose senses fall below persona thresholds.

    Args:
        scores_json: the JSON string returned by compute_comfort_scores.
        persona: persona label; defaults to "Neutral".

    Returns:
        JSON string: {"layoutId", "persona", "totalFlagged", "flaggedRooms": [...]}.
    """
    scores_data = None
    try:
        scores_data = json.loads(scores_json)
    except Exception:
        return json.dumps({"error": "Invalid scores_json -- must be the output from compute_comfort_scores"})

    persona_str = str(persona).strip() if persona else "Neutral"

    THRESHOLDS = {
        "Elderly 65+":      {"thermal":0.60,"visual":0.60,"acoustic":0.65,"spatial":0.50,"olfactory":0.55,"tactile":0.55},
        "Child under 12":   {"thermal":0.50,"visual":0.50,"acoustic":0.55,"spatial":0.60,"olfactory":0.45,"tactile":0.60},
        "Sensory Sensitive":{"thermal":0.65,"visual":0.65,"acoustic":0.70,"spatial":0.55,"olfactory":0.65,"tactile":0.65},
        "Young Active":     {"thermal":0.35,"visual":0.35,"acoustic":0.35,"spatial":0.35,"olfactory":0.35,"tactile":0.35},
        "Neutral":          {"thermal":0.45,"visual":0.45,"acoustic":0.45,"spatial":0.45,"olfactory":0.45,"tactile":0.45},
    }
    thresholds = THRESHOLDS.get(persona_str, THRESHOLDS["Neutral"])

    flagged = []
    for room in scores_data.get("rooms", []):
        scores = room.get("comfortScores", {})
        conflicts = [
            "{} score {:.2f} below threshold {:.2f}".format(s, scores[s], thresholds[s])
            for s in scores if scores[s] < thresholds[s]
        ]
        if conflicts:
            flagged.append({
                "roomId":   room.get("roomId"),
                "roomName": room.get("roomName"),
                "persona":  persona_str,
                "conflicts": conflicts
            })

    return json.dumps({
        "layoutId":     scores_data.get("layoutId", "?"),
        "persona":      persona_str,
        "totalFlagged": len(flagged),
        "flaggedRooms": flagged
    })
