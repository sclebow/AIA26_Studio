from typing import Any
import re

# ---------------------------------------------------------------------------
# Check user prompt and determine the next action.
# ---------------------------------------------------------------------------

END_PATTERN = re.compile(r"\b(end|finish|done)\b", re.IGNORECASE)
LAYOUT_ID_PATTERN = re.compile(r"\b(layout-\d+)\b", re.IGNORECASE)
SELECT_LAYOUT_PATTERN = re.compile(r"\bselect\s+layout\s+([A-Za-z0-9_.-]+)\b", re.IGNORECASE)

def build_preprocess_node() -> Any:
    def preprocess(state: dict) -> dict:
        forced_layout_id = state.get("forced_layout_id")
        if isinstance(forced_layout_id, str) and forced_layout_id.strip():
            return {
                "preprocess_result": "select",
                "layout_id": forced_layout_id.strip(),
                "forced_layout_id": None,
            }

        user_prompt = state.get("user_prompt", "")
        if END_PATTERN.search(user_prompt):
            return {
                "preprocess_result": "end",
                "final_response": "Layout finalized.",
                "needs_user_input": False,
            }

        select_layout_match = SELECT_LAYOUT_PATTERN.search(state.get("user_prompt", ""))
        if select_layout_match:
            return {
                "preprocess_result": "select",
                "layout_id": select_layout_match.group(1),
            }
        
        layout_match = LAYOUT_ID_PATTERN.search(user_prompt)
        if layout_match:
            return {
                "preprocess_result": "select",
                "layout_id": layout_match.group(1),
            }

        return {"preprocess_result": "reason"}

    return preprocess