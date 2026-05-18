from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from _runtime.llm import write_tool_result


# ---------------------------------------------------------------------------
# Tool node — executes MCP tool calls requested by the reason node.
# ---------------------------------------------------------------------------

def build_tool_node(mcp_client, allowed_tools, edited_layout_path, input_layout_path=None):
    """Return a tool node function ready to be added to a LangGraph StateGraph."""

    allowed_names = {t["name"] for t in allowed_tools if t.get("name")}

    def tool_node(state):

        # Iterate over the pending tool calls
        for call in state["pending_tool_calls"]:

            # Stop the process if max number of iterations is reached
            state["iteration"] += 1
            if state["iteration"] > state["max_iterations"]:
                raise RuntimeError("Max iterations exceeded")


            # Get the tool name and check its valid
            tool_name = call["name"]
            if tool_name not in allowed_names:
                raise RuntimeError(f"Tool '{tool_name}' is not in the allowed tools list")
            
            print(f"Calling tool: {tool_name} with arguments: {call['arguments']}")

            # Cleanup any null values accidentally included by the LLM
            tool_args = {k: v for k, v in call["arguments"].items() if v is not None}

            # Inject layout_json
            if "layout_json" in tool_args:
                tool_args["layout_json"] = state["layout_json_string"]

            # Inject input_layout from file
            if "input_layout" in tool_args and input_layout_path and input_layout_path.exists():
                try:
                    input_layout = json.loads(input_layout_path.read_text(encoding="utf-8"))
                    tool_args["input_layout"] = json.dumps(input_layout)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Warning: Could not load input_layout from {input_layout_path}: {e}")

            # Call the tool
            tool_output = mcp_client.call_tool(tool_name, tool_args)

            # Store the updated layout returned by the MCP tool to a json file
            write_tool_result(tool_output, edited_layout_path)

            # If the tool returned valid JSON, update the layout in state so
            # subsequent tool calls in this loop receive the latest layout.
            try:
                updated = json.loads(tool_output.strip())
                if isinstance(updated, dict):
                    state["layout_json_string"] = json.dumps(updated)
            except (json.JSONDecodeError, AttributeError):
                pass

            # Append the tool call and its result to the conversation history
            state["messages"].append({
                "role": "assistant",
                "content": json.dumps({
                    "action": "tool",
                    "final_response": "",
                    "tool_calls": [{"name": tool_name, "arguments": tool_args}],
                }),
            })
            
            state["messages"].append({
                "role": "user",
                "content": f"Tool result: {tool_output}",
            })
            print(f"Used tool: {tool_name}")

        state["pending_tool_calls"] = None
        return state

    return tool_node
