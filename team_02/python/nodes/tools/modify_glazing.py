"""
MODIFY_GLAZING placeholder — annotates layout with mock glazing change, flags re-score.
TODO: Wire to MCP modify_glazing tool.
"""

from __future__ import annotations
import json


def build_modify_glazing_node():
    """Return the modify_glazing node function."""

    def modify_glazing_node(state: dict) -> dict:
        raw_prompt: str = state.get("raw_prompt", "")
        layout_json_string: str = state.get("layout_json_string", "")
        original_scores: str = state.get("last_scores_json", "")

        print("[modify_glazing] PLACEHOLDER — mock glazing modification")
        print(f"[modify_glazing] User request: {raw_prompt[:80]}")

        modified_layout = layout_json_string
        try:
            layout = json.loads(layout_json_string)
            layout["_placeholder_modification"] = {
                "type": "modify_glazing",
                "user_request": raw_prompt[:200],
                "status": "PLACEHOLDER — glazing not actually changed",
            }
            modified_layout = json.dumps(layout)
        except Exception:
            pass

        return {
            **state,
            "layout_json_string": modified_layout,
            "original_scores_json": original_scores,
            "pending_comparison": True,
            "comfort_depth": "analyze",
        }

    return modify_glazing_node
