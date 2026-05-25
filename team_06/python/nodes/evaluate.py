from typing import Any
import json
import logging
from pathlib import Path
from tools.layout_utils import save_layout

logger = logging.getLogger(__name__)

def build_evaluate_node(mcp_client: Any) -> Any:
    """Evaluate layout using MCP tool daylight_06."""
    def evaluate(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        iteration = state.get("iteration", 0)
        
        if not layout_json:
            return {
                "final_response": "No layout to evaluate.",
                "iteration": iteration + 1,
            }
        
        try:
            # Parse layout
            if isinstance(layout_json, str):
                layout_data = json.loads(layout_json)
            else:
                layout_data = layout_json
            
            logger.info(f"🔍 Before MCP: {len(layout_data.get('rooms', []))} rooms")
            
            # Call MCP tool
            result = mcp_client.call_tool("daylight_06", {
                "layout_json": layout_data,
                "window_wall_ratio": 0.5
            })
            
            logger.info(f"🔍 MCP result type: {type(result)}")
            
            # Parse result if it's a string
            if isinstance(result, str):
                logger.info(f"🔍 Parsing MCP result from string...")
                try:
                    result = json.loads(result)
                except:
                    logger.error(f"❌ Failed to parse MCP result as JSON")
                    return {
                        "final_response": f"Evaluation failed: could not parse result",
                        "iteration": iteration + 1,
                    }
            
            logger.info(f"🔍 After parsing: result type = {type(result)}")
            
            # Handle errors
            if not result or (isinstance(result, str) and result.startswith("Error")):
                logger.error(f"❌ MCP returned error: {result}")
                return {
                    "final_response": f"Evaluation failed: {result}",
                    "iteration": iteration + 1,
                }

            if isinstance(result, dict) and "error" in result:
                logger.error(f"❌ MCP returned error dict: {result.get('error')}")
                return {
                    "final_response": f"Evaluation error: {result.get('error')}",
                    "iteration": iteration + 1,
                }
            
            # result IS the layout with daylight already merged in!
            layout_data = result
            logger.info(f"✅ Using MCP result as layout_data")
            
            # Extract daylight summary for feedback
            rooms = layout_data.get('rooms', [])
            daylight_summary = {}
            
            for room in rooms:
                room_id = room.get('id')
                program = room.get('attributes', {}).get('program', 'unknown')
                daylight_score = room.get('attributes', {}).get('daylight', 'N/A')
                logger.info(f"   {room_id} ({program}): daylight = {daylight_score}")
                
                daylight_summary[room_id] = {
                    "name": room.get('name', 'Unknown'),
                    "program": program,
                    "daylight": daylight_score
                }
            
            # Save updated layout
            repo_root = Path(__file__).resolve().parent.parent.parent
            edited_path = repo_root / "team_06_edited_layout.json"
            logger.info(f"💾 Saving to {edited_path}")
            save_layout(layout_data, state, edited_path)
            logger.info(f"💾 Saved")
            
            return {
                "layout_json_string": json.dumps(layout_data),
                "evaluation_json_string": json.dumps(daylight_summary),
                "iteration": iteration + 1,
            }
        
        except Exception as e:
            logger.error(f"❌ Evaluate error: {str(e)}", exc_info=True)
            return {
                "final_response": f"Evaluation failed: {str(e)}",
                "iteration": iteration + 1,
            }
    
    return evaluate