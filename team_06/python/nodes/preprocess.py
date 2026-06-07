from typing import Any
import re

# ---------------------------------------------------------------------------
# Check user prompt and determine the next action.
# ---------------------------------------------------------------------------

end_keywords = ["end", "finish", "done"]
LAYOUT_ID_PATTERN = re.compile(r"\b(layout-\d+)\b", re.IGNORECASE)

def build_preprocess_node() -> Any:
    def preprocess(state: dict) -> dict:
        user_prompt = state.get("user_prompt", "").lower()
        if any(keyword in user_prompt for keyword in end_keywords):
            return {
                "preprocess_result": "end",
                "final_response": "Layout finalized.",
                "needs_user_input": False,
            }
        
        layout_match = LAYOUT_ID_PATTERN.search(user_prompt)
        if layout_match:
            return {
                "preprocess_result": "select",
                "layout_id": layout_match.group(1),
            }

        return {"preprocess_result": "reason"}

    return preprocess