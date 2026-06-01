from typing import Any
import json
import logging
from pathlib import Path
from tools.layout_utils import save_layout
from tools.layout_evaluator import summarize_evaluation

logger = logging.getLogger(__name__)

def build_evaluate_node(mcp_client: Any) -> Any:
    """Evaluate layout using MCP tool daylight_06 and summarize results."""
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
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json

            def preview(d):
                if isinstance(d, dict):
                    return {k: str(v)[:120] for k, v in d.items()}
                return str(d)[:120]

            print(f"[EVALUATE] Calling MCP tool 'daylight_06' with layout_json keys: {list(layout_data.keys())} and values: {preview(layout_data)}")
            result = mcp_client.call_tool("daylight_06", {
                "layout_json": layout_data,
                "window_wall_ratio": 0.5
            })
            print(f"[EVALUATE] MCP tool 'daylight_06' result: {str(result)[:300]}")

            logger.info(f"🔍 MCP result type: {type(result)}")

            # Parse result if it's a string
            if isinstance(result, str):
                logger.info(f"🔍 Parsing MCP result from string...")
                try:
                    result = json.loads(result)
                except Exception:
                    logger.error(f"❌ Failed to parse MCP result as JSON")
                    return {
                        "final_response": f"Evaluation failed: could not parse result",
                        "iteration": iteration + 1,
                    }

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

            # Use MCP result as layout_data (with daylight injected)
            layout_data = result
            logger.info(f"✅ Using MCP result as layout_data")

            # Summarize evaluation (all logic in layout_evaluator.py)
            topology_json = state.get("topology_graph_json_string")
            evaluation_summary = summarize_evaluation(layout_data, topology_json)

            # Save updated layout
            repo_root = Path(__file__).resolve().parent.parent.parent
            edited_path = repo_root / "team_06_edited_layout.json"
            logger.info(f"💾 Saving to {edited_path}")
            save_layout(layout_data, state, edited_path)
            logger.info(f"💾 Saved")

            return {
                "layout_json_string": json.dumps(layout_data),
                "evaluation_json_string": json.dumps(evaluation_summary),
                "iteration": iteration + 1,
            }

        except Exception as e:
            logger.error(f"❌ Evaluate error: {str(e)}", exc_info=True)
            return {
                "final_response": f"Evaluation failed: {str(e)}",
                "iteration": iteration + 1,
            }

    return evaluate