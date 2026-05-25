"""
CHANGE_MATERIAL placeholder — annotates layout with mock material change, flags re-score.
TODO: Wire to MCP modify_room_material tool.
"""

from __future__ import annotations
import json


def build_change_material_node():
    """Return the change_material node function."""

    def change_material_node(state: dict) -> dict:
        raw_prompt: str = state.get("raw_prompt", "")
        layout_json_string: str = state.get("layout_json_string", "")
        original_scores: str = state.get("last_scores_json", "")

        print("[change_material] PLACEHOLDER — mock material modification")
        print(f"[change_material] User request: {raw_prompt[:80]}")

        # Mock: annotate layout with a placeholder modification note
        modified_layout = layout_json_string  # unchanged in placeholder
        try:
            layout = json.loads(layout_json_string)
            layout["_placeholder_modification"] = {
                "type": "change_material",
                "user_request": raw_prompt[:200],
                "status": "PLACEHOLDER — material not actually changed",
            }
            modified_layout = json.dumps(layout)
        except Exception:
            pass

        print("[change_material] Layout flagged for re-scoring (mock)")

        return {
            **state,
            "layout_json_string": modified_layout,
            "original_scores_json": original_scores,
            "pending_comparison": True,
            "comfort_depth": "analyze",
        }

    return change_material_node
