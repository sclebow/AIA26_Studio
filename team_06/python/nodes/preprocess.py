from typing import Any

# ---------------------------------------------------------------------------
# Check user prompt and determine the next action.
# ---------------------------------------------------------------------------

end_keywords = ["end", "finish", "done"]
topology_keywords = ["layout", "apartment", "house", "floor plan", "topology"]
modify_keywords = ["change", "modify", "adjust", "move", "relocate", "add", "remove"]
evaluate_keywords = ["evaluate", "feedback", "daylight", "privacy", "flow", "functionality"]

def build_preprocess_node() -> Any:
    def preprocess(state: dict) -> dict:
        user_prompt = state.get("user_prompt", "").lower()
        if any(keyword in user_prompt for keyword in end_keywords):
            return {
                "preprocess_result": "end",
                "final_response": "Layout finalized."
            }
        
        if any(keyword in user_prompt for keyword in topology_keywords):
            return {"preprocess_result": "topology"}
        
        if "layout-" in user_prompt:
            return {"preprocess_result": "select"}

        if any(keyword in user_prompt for keyword in modify_keywords):
            return {"preprocess_result": "modify"}
        
        if any(keyword in user_prompt for keyword in evaluate_keywords):
            return {"preprocess_result": "evaluate"}
        
        return {"preprocess_result": "reason"}

    return preprocess