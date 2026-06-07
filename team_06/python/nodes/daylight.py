from typing import Any
import json
from pathlib import Path
from tools.layout_utils import save_layout

def build_daylight_node(mcp_client: Any) -> Any:
    """Attach daylight analysis to the current layout using MCP tool daylight_06."""
    def evaluate(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        iteration = state.get("iteration", 0)

        if not layout_json:
            return {
                "daylight_result": "failed",
                "clarification": "No layout available for daylight analysis.",
                "iteration": iteration + 1,
            }
        try:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json

            rooms = layout_data.get("rooms")
            facades = layout_data.get("facades")
            if not isinstance(rooms, list) or not rooms:
                return {
                    "daylight_result": "failed",
                    "clarification": "Daylight analysis failed: layout has no rooms.",
                    "iteration": iteration + 1,
                }
            if not isinstance(facades, list) or not facades:
                return {
                    "daylight_result": "failed",
                    "clarification": "Daylight analysis failed: layout has no facades.",
                    "iteration": iteration + 1,
                }

            result = mcp_client.call_tool("daylight_06", {
                "layout_json": layout_data,
                "window_wall_ratio": 0.5
            })

            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    return {
                        "daylight_result": "failed",
                        "clarification": "Daylight analysis failed: could not parse the result.",
                        "iteration": iteration + 1,
                    }

            if not result or (isinstance(result, str) and result.startswith("Error")):
                return {
                    "daylight_result": "failed",
                    "clarification": f"Daylight analysis failed: {result}",
                    "iteration": iteration + 1,
                }

            if isinstance(result, dict) and "error" in result:
                return {
                    "daylight_result": "failed",
                    "clarification": f"Daylight analysis error: {result.get('error')}",
                    "iteration": iteration + 1,
                }

            layout_data = result

            repo_root = Path(__file__).resolve().parent.parent.parent
            edited_path = repo_root / "team_06_edited_layout.json"
            save_layout(layout_data, state, edited_path)

            return {
                "daylight_result": "evaluate",
                "layout_json_string": json.dumps(layout_data),
                "iteration": iteration + 1,
            }

        except Exception as e:
            return {
                "daylight_result": "failed",
                "clarification": f"Daylight analysis failed: {str(e)}",
                "iteration": iteration + 1,
            }

    return evaluate