from typing import Any
import json

def build_boundary_node(mcp_client: Any) -> Any:
    """Modify boundary - only modifies input_layout in state."""
    def boundary(state: dict) -> dict:
        input_layout_json = state.get("input_layout_json_string")
        
        if not input_layout_json:
            return {"final_response": "No input layout to modify boundary on."}
        
        try:
            # Parse input layout
            if isinstance(input_layout_json, str):
                input_layout = json.loads(input_layout_json)
            else:
                input_layout = input_layout_json
            
            # Call MCP tool
            result = mcp_client.call_tool("modify_boundary_06", {
                "input_layout": input_layout
            })
            
            # boundary.py fallback pattern:
            if not result or isinstance(result, str) and result.startswith("Error"):
                return {"final_response": f"Boundary modification failed: {result}"}

            if isinstance(result, dict) and "error" in result:
                return {"final_response": f"Boundary error: {result.get('error')}"}

            modified_input = result.get("modified_input_layout", input_layout)
            
            return {
                "input_layout_json_string": json.dumps(modified_input),
                "iteration": state.get("iteration", 0) + 1,
            }
        
        except Exception as e:
            return {
                "final_response": f"Boundary modification failed: {str(e)}",
            }
    
    return boundary