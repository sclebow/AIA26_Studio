"""
detect_sensorial_conflicts — flag senses scoring below the persona's threshold.

Migrated verbatim from the Grasshopper cluster script. Takes the JSON output of
compute_comfort_scores. Logic unchanged; GH inputs became parameters and the GH
output variable `a` became the return value.
"""

import json

try:
    from comfort.sense_model import SENSES, threshold_from_weight
except ImportError:  # same-dir fallback
    from sense_model import SENSES, threshold_from_weight


def detect_sensorial_conflicts(scores_json, persona=None, weights_override=None):
    """Return a JSON string of rooms whose senses fall below the user's thresholds.

    Thresholds come from the REAL onboarding comfort weights when provided
    (weights_override), via sense_model.threshold_from_weight — so detection is
    personalised, not bucketed into a category. The per-category table is only a
    fallback when no weights are available.

    Args:
        scores_json: the JSON string returned by compute_comfort_scores.
        persona: persona label (fallback labelling only); defaults to "Neutral".
        weights_override: dict or JSON string of the user's per-sense comfort weights.

    Returns:
        JSON string: {"layoutId", "persona", "totalFlagged", "flaggedRooms": [...]}.
    """
    scores_data = None
    try:
        scores_data = json.loads(scores_json)
    except Exception:
        return json.dumps({"error": "Invalid scores_json -- must be the output from compute_comfort_scores"})

    persona_str = str(persona).strip() if persona else "you"

    # Thresholds are derived from the REAL onboarding weights. No persona
    # categories: with no profile, every sense defaults to weight 0.5 → a uniform
    # neutral threshold (~0.55).
    weights = None
    if weights_override:
        try:
            raw = json.loads(weights_override) if isinstance(weights_override, str) else weights_override
            if all(s in raw for s in SENSES):
                weights = {s: float(raw[s]) for s in SENSES}
        except Exception:
            weights = None
    if weights is None:
        weights = {s: 0.5 for s in SENSES}
    thresholds = {s: threshold_from_weight(weights[s]) for s in SENSES}

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
