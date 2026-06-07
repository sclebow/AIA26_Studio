"""
DETECT node — flags sensorial conflicts on existing scores.

Thresholds come from the onboarding comfort_weights (weights_override) via
threshold_from_weight — no persona category buckets. `persona` is a display label only.
"""

from __future__ import annotations
import json
from nodes._shared.utils import unwrap_mcp_result, persona_display_label


def build_detect_node(mcp_client):
    def detect_node(state: dict) -> dict:
        scores_json     = state.get("last_scores_json", "")
        persona_profile = state.get("persona_profile") or {}
        persona_label   = persona_display_label(persona_profile)
        weights_override = persona_profile.get("comfort_weights")

        if not scores_json:
            raise RuntimeError("[detect] No scores available — ANALYZE must run first.")

        print(f"[detect] detect_sensorial_conflicts (persona={persona_label}, custom_weights={bool(weights_override)})")
        args = {"scores_json": scores_json, "persona": persona_label}
        if weights_override:
            args["weights_override"] = json.dumps(weights_override)
        raw_output = mcp_client.call_tool("detect_sensorial_conflicts", args)
        conflicts_json = unwrap_mcp_result(raw_output)
        print(f"[detect] Conflicts received ({len(conflicts_json)} chars)")

        return {**state, "last_conflicts_json": conflicts_json}

    return detect_node
