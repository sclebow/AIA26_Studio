"""
DETECT node — calls detect_sensorial_conflicts on existing scores.
Fixed: uses actual persona label (or Neutral as fallback for custom profiles).
"""

from __future__ import annotations
from nodes._shared.utils import unwrap_mcp_result


def _persona_label(persona_profile: dict) -> str:
    if not persona_profile:
        return "Neutral"
    pt = persona_profile.get("persona_type", "")
    valid = {"Elderly 65+", "Child under 12", "Sensory Sensitive", "Young Active", "Neutral"}
    return pt if pt in valid else "Neutral"


def build_detect_node(mcp_client):
    def detect_node(state: dict) -> dict:
        scores_json     = state.get("last_scores_json", "")
        persona_profile = state.get("persona_profile") or {}
        persona_label   = _persona_label(persona_profile)

        if not scores_json:
            raise RuntimeError("[detect] No scores available — ANALYZE must run first.")

        print(f"[detect] detect_sensorial_conflicts (persona={persona_label})")
        raw_output = mcp_client.call_tool(
            "detect_sensorial_conflicts",
            {"scores_json": scores_json, "persona": persona_label},
        )
        conflicts_json = unwrap_mcp_result(raw_output)
        print(f"[detect] Conflicts received ({len(conflicts_json)} chars)")

        return {**state, "last_conflicts_json": conflicts_json}

    return detect_node
