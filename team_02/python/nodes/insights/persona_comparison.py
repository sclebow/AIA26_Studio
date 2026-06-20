"""
PERSONA_COMPARISON — real dual-persona comfort comparison.
Runs compute_comfort_scores twice (the USER'S actual persona vs a contrasting
archetype), computes the per-room delta.

Fixed (session 6): the comparison used to key off a dead `persona_type` field the
compiler never sets (→ always "Neutral") AND passed only a label string to the
scorer with no weights — so BOTH runs used identical default weights and every room
tied. Now the user's side scores with their real persona (weights + personality +
household context) and the comparison archetype carries representative weights, so
the delta is genuine.
"""

from __future__ import annotations
import json
from nodes._shared.utils import unwrap_mcp_result
from nodes._shared.persona_context import persona_scoring_args, derive_context

# Representative comfort_weights / personality / household-context per comparison
# archetype, so each scores meaningfully differently from the user and from each other.
_ARCHETYPES: dict[str, dict] = {
    "Elderly 65+": {
        "weights": {"thermal": 0.85, "visual": 0.75, "acoustic": 0.80,
                    "spatial": 0.55, "olfactory": 0.65, "tactile": 0.60},
        "personality": -0.5, "context": {"elderly": True},
    },
    "Child under 12": {
        "weights": {"thermal": 0.65, "visual": 0.60, "acoustic": 0.80,
                    "spatial": 0.70, "olfactory": 0.70, "tactile": 0.55},
        "personality": 0.5, "context": {"children": True},
    },
    "Sensory Sensitive": {
        "weights": {"thermal": 0.85, "visual": 0.80, "acoustic": 0.90,
                    "spatial": 0.70, "olfactory": 0.80, "tactile": 0.80},
        "personality": -1.0, "context": {},
    },
    "Young Active": {
        "weights": {"thermal": 0.55, "visual": 0.70, "acoustic": 0.45,
                    "spatial": 0.80, "olfactory": 0.50, "tactile": 0.55},
        "personality": 1.0, "context": {},
    },
    "Neutral": {
        "weights": {s: 0.5 for s in
                    ("thermal", "visual", "acoustic", "spatial", "olfactory", "tactile")},
        "personality": 0.0, "context": {},
    },
}


def _derive_primary_label(profile: dict) -> str:
    """A human archetype label for the USER, derived from their real persona (not a
    dead field). Used only for display + to pick a meaningful contrast — the user's
    side is always scored from their actual profile."""
    ctx = derive_context(profile)
    if ctx.get("elderly"):
        return "Elderly 65+"
    if ctx.get("children"):
        return "Child under 12"
    weights = profile.get("comfort_weights") or {}
    high = sum(1 for v in weights.values() if isinstance(v, (int, float)) and v >= 0.75)
    if high >= 4 or len(profile.get("sensory_sensitivities") or []) >= 4:
        return "Sensory Sensitive"
    try:
        pers = float(profile.get("personality", 0) or 0)
    except (TypeError, ValueError):
        pers = 0.0
    if pers >= 0.5:
        return "Young Active"
    return "Balanced"


def _pick_comparison_persona(raw_prompt: str, primary_label: str) -> str:
    """Pick which archetype to compare against — an explicit ask in the prompt wins,
    otherwise a meaningful contrast to the user's own archetype."""
    p = raw_prompt.lower()
    if "elderly" in p or "old" in p or "senior" in p or "grandparent" in p:
        return "Elderly 65+"
    if "child" in p or "kid" in p:
        return "Child under 12"
    if "sensitive" in p or "sensory" in p:
        return "Sensory Sensitive"
    if "active" in p or "sport" in p or "young" in p:
        return "Young Active"
    # Default: contrast with the opposite kind of occupant.
    defaults = {
        "Elderly 65+": "Young Active",
        "Child under 12": "Young Active",
        "Sensory Sensitive": "Young Active",
        "Young Active": "Elderly 65+",
        "Balanced": "Sensory Sensitive",
        "Neutral": "Sensory Sensitive",
    }
    return defaults.get(primary_label, "Sensory Sensitive")


def build_persona_comparison_node(mcp_client=None):
    def persona_comparison_node(state: dict) -> dict:
        layout_json     = state.get("layout_json_string", "")
        persona_profile = state.get("persona_profile") or {}
        raw_prompt      = state.get("raw_prompt", "")

        if not layout_json:
            summary = "No layout loaded — cannot run persona comparison."
            return {**state, "persona_comparison_summary": summary}

        # Primary archetype label, derived from the user's REAL persona (display + to
        # choose a contrast). The user's side is scored from their actual profile.
        primary_label = _derive_primary_label(persona_profile)
        primary_name  = persona_profile.get("name", "you")

        # Comparison archetype + its representative scoring args.
        compare_label = _pick_comparison_persona(raw_prompt, primary_label)
        comp = _ARCHETYPES.get(compare_label, _ARCHETYPES["Neutral"])

        print(f"[persona_comparison] Comparing {primary_name} ({primary_label}) vs {compare_label}")

        # Run scoring for both — the user with their real weights/personality/context,
        # the archetype with its own — so the two genuinely differ.
        if mcp_client:
            primary_args = {"layout_json": layout_json, "room_ids": "all",
                            **persona_scoring_args(persona_profile)}
            compare_args = {"layout_json": layout_json, "room_ids": "all",
                            "persona": compare_label,
                            "weights_override": json.dumps(comp["weights"]),
                            "personality": comp["personality"]}
            if comp.get("context"):
                compare_args["context"] = json.dumps(comp["context"])
            raw_a = mcp_client.call_tool("compute_comfort_scores", primary_args)
            raw_b = mcp_client.call_tool("compute_comfort_scores", compare_args)
            scores_a = json.loads(unwrap_mcp_result(raw_a))
            scores_b = json.loads(unwrap_mcp_result(raw_b))
        else:
            # Fallback if no client
            scores_a, scores_b = {"rooms": []}, {"rooms": []}

        # Compute per-room, per-sense delta
        rooms_a = {r["roomName"]: r for r in scores_a.get("rooms", [])}
        rooms_b = {r["roomName"]: r for r in scores_b.get("rooms", [])}

        lines = [f"PERSONA COMPARISON: {primary_name} ({primary_label}) vs {compare_label}"]
        winner_counts = {primary_label: 0, compare_label: 0, "tie": 0}

        for room_name, ra in rooms_a.items():
            rb = rooms_b.get(room_name)
            if not rb:
                continue
            sc_a = ra.get("comfortScores", {})
            sc_b = rb.get("comfortScores", {})
            ov_a = ra.get("overallScore", 0)
            ov_b = rb.get("overallScore", 0)
            delta = ov_b - ov_a
            worse_for = primary_label if delta > 0.05 else (compare_label if delta < -0.05 else "neither")
            if delta > 0.05:
                winner_counts[compare_label] += 1
            elif delta < -0.05:
                winner_counts[primary_label] += 1
            else:
                winner_counts["tie"] += 1

            lines.append(
                f"  {room_name}: {primary_label}={ov_a:.2f} | {compare_label}={ov_b:.2f} "
                f"(worse for: {worse_for})"
            )

        summary = "\n".join(lines)
        comparison_data = {
            "primary_label":   primary_label,
            "compare_label":   compare_label,
            "scores_primary":  scores_a,
            "scores_compare":  scores_b,
            "winner_counts":   winner_counts,
        }

        print(f"[persona_comparison] Done. {winner_counts}")
        return {
            **state,
            "persona_comparison_summary": summary,
            "persona_comparison_data":    comparison_data,
            # Surface as primary scores so downstream scoring nodes can use them
            "last_scores_json": unwrap_mcp_result(raw_a) if mcp_client else "",
        }

    return persona_comparison_node
