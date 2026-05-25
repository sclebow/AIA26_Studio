from typing import Any
import json

def build_preprocessing_node() -> Any:
    """Check: do we have a layout with rooms AND keywords in prompt?"""
    def preprocessing(state: dict) -> dict:
        user_prompt = state.get("user_prompt", "").lower()
        layout_json = state.get("layout_json_string", "")
        
        # === PRIORITY 1: END SIGNAL ===
        if "end" in user_prompt or "finish" in user_prompt or "done" in user_prompt:
            return {
                "preprocessing_result": "end",
                "final_response": "Layout finalized."
            }
        
        # === PRIORITY 2: USER FEEDBACK/COMMANDS ===
        if "change rooms" in user_prompt or "new rooms" in user_prompt:
            return {"preprocessing_result": "research"}
        
        if "change boundary" in user_prompt or "change outline" in user_prompt:
            return {"preprocessing_result": "modify_boundary"}
        
        if "layout-" in user_prompt:
            return {"preprocessing_result": "select_layout"}
        
        # === PRIORITY 3: NORMAL FLOW ===
        if not layout_json:
            return {"preprocessing_result": "parse"}
        
        try:
            layout = json.loads(layout_json)
            has_rooms = len(layout.get("rooms", [])) > 0
        except:
            return {"preprocessing_result": "parse"}
        
        # Check if layout has rooms AND prompt has keywords
        has_keywords = any(keyword in user_prompt for keyword in ["evaluate", "feedback", "daylight"])
        
        if has_rooms and has_keywords:
            return {"preprocessing_result": "evaluate"}
        else:
            return {"preprocessing_result": "parse"}
    
    return preprocessing