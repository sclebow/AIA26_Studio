"""
ADD_FURNITURE placeholder — annotates layout with mock furniture/plant addition, flags re-score.
TODO: Wire to MCP add_furniture_element tool.
"""

from __future__ import annotations
import json


def build_add_furniture_node():
    """Return the add_furniture node function."""

    def add_furniture_node(state: dict) -> dict:
        raw_prompt: str = state.get("raw_prompt", "")
        layout_json_string: str = state.get("layout_json_string", "")
        original_scores: str = state.get("last_scores_json", "")

        print("[add_furniture] PLACEHOLDER — mock furniture/plant addition")
        print(f"[add_furniture] User request: {raw_prompt[:80]}")

        modified_layout = layout_json_string
        try:
            layout = json.loads(layout_json_string)
            layout["_placeholder_modification"] = {
                "type": "add_furniture",
                "user_request": raw_prompt[:200],
                "status": "PLACEHOLDER — furniture not actually added",
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

    return add_furniture_node
