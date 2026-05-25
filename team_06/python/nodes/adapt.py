from typing import Any
from tools.layout_utils import save_layout
import json
from pathlib import Path

def build_adapt_node(mcp_client: Any) -> Any:
    """Adapt layout using MCP tool adapt_layout_06."""
    
    def adapt(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        input_layout_json = state.get("input_layout_json_string")
        iteration = state.get("iteration", 0)
        
        if not layout_json:
            return {"final_response": "No layout to adapt."}
        
        try:
            # Parse layouts
            if isinstance(layout_json, str):
                layout_data = json.loads(layout_json)
            else:
                layout_data = layout_json
            
            if input_layout_json:
                if isinstance(input_layout_json, str):
                    input_layout = json.loads(input_layout_json)
                else:
                    input_layout = input_layout_json
            else:
                input_layout = {}
            
            # Call MCP tool
            result = mcp_client.call_tool("adapt_layout_06", {
                "layout_json": layout_data,
                "input_layout": input_layout
            })
            
            # Fallback: check if result is empty or error
            if not result or isinstance(result, str) and result.startswith("Error"):
                return {"final_response": f"Adaptation failed: {result}"}
            
            if isinstance(result, dict) and "error" in result:
                return {"final_response": f"Adaptation error: {result.get('error')}"}
            
            adapted = result.get("adapted_layout", layout_data) if isinstance(result, dict) else layout_data
            
            if not adapted:
                return {"final_response": "Adaptation returned empty layout."}
            
            repo_root = Path(__file__).resolve().parent.parent.parent
            edited_path = repo_root / "team_06_edited_layout.json"
            save_layout(adapted, state, edited_path)
    
            return {
                "layout_json_string": json.dumps(adapted),
                "iteration": iteration + 1,
            }
        
        except Exception as e:
            return {"final_response": f"Adaptation failed: {str(e)}"}
    
    return adapt