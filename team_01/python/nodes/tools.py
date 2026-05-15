from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any
from _runtime.llm import write_tool_result


def build_tool_node(mcp_client, allowed_tools, edited_layout_path):

    allowed_names = {t["name"] for t in allowed_tools if t.get("name")}

    def tool_node(state):

        for call in state["pending_tool_calls"]:

            state["iteration"] += 1
            if state["iteration"] > state["max_iterations"]:
                raise RuntimeError("Max iterations exceeded")

            tool_name = call["name"]
            if tool_name not in allowed_names:
                raise RuntimeError(f"Tool '{tool_name}' is not in the allowed tools list")

            print(f"Calling tool: {tool_name} with arguments: {call['arguments']}")

            tool_args = {k: v for k, v in call["arguments"].items() if v is not None}

            # Inject layout_json only if LLM did not provide one
            provided = tool_args.get("layout_json", "")
            if "layout_json" not in tool_args or str(provided).strip() in ("", "{}", "null", "None"):
                tool_args["layout_json"] = state["layout_json_string"]

            # Call the tool with retry
            tool_output = None
            for attempt in range(3):
                try:
                    tool_output = mcp_client.call_tool(tool_name, tool_args)
                    break
                except Exception as e:
                    if attempt < 2:
                        wait = 5 * (attempt + 1)
                        print(f"Tool call failed (attempt {attempt+1}/3), retrying in {wait}s... {e}")
                        time.sleep(wait)
                    else:
                        raise RuntimeError(f"Tool {tool_name} failed after 3 attempts: {e}") from e

            write_tool_result(tool_output, edited_layout_path)

            # Update layout in state
            try:
                updated = json.loads(tool_output.strip())
                if isinstance(updated, dict):
                    full = json.loads(state["layout_json_string"])
                    if isinstance(full, list):
                        for idx, layout in enumerate(full):
                            if layout.get("layoutId") == updated.get("layoutId"):
                                full[idx] = updated
                                break
                        state["layout_json_string"] = json.dumps(full)
                    else:
                        state["layout_json_string"] = json.dumps(updated)
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass

            # Append short summary to conversation history
            try:
                layout_id = json.loads(tool_output).get("layoutId", "?") if tool_output.strip().startswith("{") else "?"
            except Exception:
                layout_id = "?"

            state["messages"].append({
                "role": "assistant",
                "content": json.dumps({
                    "action": "tool",
                    "final_response": "",
                    "tool_calls": [{"name": tool_name, "arguments": {k: v for k, v in tool_args.items() if k != "layout_json"}}],
                }),
            })

            state["messages"].append({
                "role": "user",
                "content": f"Tool {tool_name} completed for {layout_id}.",
            })
            print(f"Tool result: {tool_output}")

        state["pending_tool_calls"] = None
        return state

    return tool_node