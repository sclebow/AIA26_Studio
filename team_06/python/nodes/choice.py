from typing import Any
import json
import re
from pathlib import Path
from tools.layout_utils import load_and_save_layout

def build_choice_node(llm):
    def choice(state: dict) -> dict:
        user_prompt = state.get("user_prompt", "").lower()
        
        # Check if user provided a layout ID
        if "layout-" in user_prompt:
            match = re.search(r'layout-(\w+)', user_prompt)
            if match:
                layout_id = f"layout-{match.group(1)}"
                save_path = Path(__file__).parent.parent.parent / "team_06_edited_layout.json"
                load_and_save_layout(layout_id, state, save_path)
                return {"final_response": None}
        
        # Otherwise, ask which layout from search results
        search_json = state.get("search_results_json_string", "[]")
        try:
            results = json.loads(search_json)
        except:
            return {"final_response": "No search results found."}
        
        if len(results) == 0:
            return {"final_response": "No layouts matched your search."}
        
        options_text = "\n".join(
            f"- layout-{r['id']}: {r['description']} (score: {r['score']:.2f})"
            for r in results
        )
        
        return {
            "final_response": f"Found {len(results)} matching layouts:\n\n{options_text}\n\nWhich layout? (type: layout-ID)"
        }
    
    return choice