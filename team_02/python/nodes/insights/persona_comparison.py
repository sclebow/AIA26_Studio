"""
PERSONA_COMPARISON — real dual-persona comfort comparison.
Runs compute_comfort_scores twice (user persona vs comparison persona), computes delta.
"""

from __future__ import annotations
import json
from nodes._shared.utils import unwrap_mcp_result

_COMPARISON_PERSONAS = ["Elderly 65+", "Sensory Sensitive", "Young Active", "Child under 12", "Neutral"]


def _pick_comparison_persona(raw_prompt: str, primary_label: str) -> str:
    """Pick which persona to compare against based on the prompt."""
    p = raw_prompt.lower()
    if "elderly" in p or "old" in p or "senior" in p:
        return "Elderly 65+"
    if "child" in p or "kid" in p or "young" in p:
        return "Child under 12"
    if "sensitive" in p or "sensory" in p:
        return "Sensory Sensitive"
    if "active" in p or "sport" in p:
        return "Young Active"
    # Default: compare against the polar opposite
    defaults = {
        "Elderly 65+": "Young Active",
        "Young Active": "Elderly 65+",
        "Sensory Sensitive": "Young Active",
        "Neutral": "Sensory Sensitive",
    }
    return defaults.get(primary_label, "Elderly 65+")


def build_persona_comparison_node(mcp_client=None):
    def persona_comparison_node(state: dict) -> dict:
        layout_json     = state.get("layout_json_string", "")
        persona_profile = state.get("persona_profile") or {}
        raw_prompt      = state.get("raw_prompt", "")

        if not layout_json:
            summary = "No layout loaded — cannot run persona comparison."
            return {**state, "persona_comparison_summary": summary}

        # Primary persona label
        pt = persona_profile.get("persona_type", "")
        valid = {"Elderly 65+", "Child under 12", "Sensory Sensitive", "Young Active", "Neutral"}
        primary_label = pt if pt in valid else "Neutral"
        primary_name  = persona_profile.get("name", "you")

        # Comparison persona
        compare_label = _pick_comparison_persona(raw_prompt, primary_label)

        print(f"[persona_comparison] Comparing {primary_label} vs {compare_label}")

        # Run scoring for both personas
        if mcp_client:
            raw_a = mcp_client.call_tool("compute_comfort_scores",
                                          {"layout_json": layout_json, "persona": primary_label, "room_ids": "all"})
            raw_b = mcp_client.call_tool("compute_comfort_scores",
                                          {"layout_json": layout_json, "persona": compare_label, "room_ids": "all"})
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
