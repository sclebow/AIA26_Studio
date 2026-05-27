from __future__ import annotations
import json
from typing import Any
from _runtime.session import save_session


# ---------------------------------------------------------------------------
# Tool node — executes MCP tool calls requested by the reason node.
# ---------------------------------------------------------------------------

def build_tool_node(mcp_client, allowed_tools, workspace_path):
    """Return a tool node function ready to be added to a LangGraph StateGraph."""

    allowed_names = {t["name"] for t in allowed_tools if t.get("name")}

    def tool_node(state):
        # Returns an update dict instead of mutating state.
        new_messages = []
        updated_placement_history = state.get("placement_history") or []
        layout_json_string = state["layout_json_string"]
        iteration = state["iteration"]

        pending = state.get("pending_tool_calls")
        if not pending:
            print("[tools] Warning: no pending tool calls — returning to reason")
            return {
                "pending_tool_calls": None,
                "iteration": iteration,
                "layout_json_string": layout_json_string,
                "messages": [],
            }

        for call in pending:

            # Stop the process if max number of iterations is reached
            iteration += 1
            if iteration > state["max_iterations"]:
                raise RuntimeError("Max iterations exceeded")

            # Validate the tool name against the allowed list
            tool_name = call["name"]
            if tool_name not in allowed_names:
                print(f"[tools] Warning: tool '{tool_name}' not found — skipping")
                new_messages.append({"role": "user", "content": f"Tool '{tool_name}' is not available. Available tools: {', '.join(sorted(allowed_names))}"})
                continue

            print(f"Calling tool: {tool_name} with arguments: {call['arguments']}")

            # Strip null/empty values and fields that are injected automatically.
            # Prevents the LLM from sending stale or duplicate layout JSON.
            _llm_skip = {"layout_json", "compare_layout_json"}
            tool_args = {k: v for k, v in call["arguments"].items()
                         if v is not None and v != "" and k not in _llm_skip}

            # Check if this tool declares layout_json in its inputSchema —
            # if yes inject it automatically without relying on the LLM to include it
            tool_schema = next(
                (t for t in allowed_tools if t.get("name") == tool_name), {}
            )
            needs_layout = "layout_json" in (
                tool_schema
                .get("inputSchema", {})
                .get("properties", {})
            )
            if needs_layout:
                tool_args["layout_json"] = layout_json_string

            # Force correct profile for collision tool — prevents LLM from
            # constructing wrong profile type from conversation history
            if tool_name == "collision-detector-grid":
                profile_config = state.get("profile_config") or {}
                gh_user_type = profile_config.get("profile_type", "standard_worker")
                tool_args["user_profile"] = json.dumps({
                    "user_type":            gh_user_type,
                    "body_width_m":         profile_config.get("body_width", 0.70),
                    "min_corridor_width_m": profile_config.get("min_path_width", 0.915),
                    "min_door_width_m":     profile_config.get("min_door_width", 0.85),
                    "turning_radius_m":     profile_config.get("turning_radius", 0.30),
                })

            # Execute the tool via the MCP client
            try:
                tool_output = mcp_client.call_tool(tool_name, tool_args)
            except Exception as exc:
                print(f"[tools] MCP call failed for {tool_name}: {exc}")
                tool_output = f"MCP error: {exc}"

            # Parse tool output and update layout state where relevant
            try:
                updated = json.loads(tool_output.strip())
                if isinstance(updated, dict):
                    if "rooms" in updated:
                        # Full layout returned — merge with current state to
                        # preserve layers the tool might not return.
                        current = json.loads(layout_json_string)
                        for key in ("doors", "windows", "mep", "structure", "outline"):
                            if key not in updated or not updated[key]:
                                if key in current and current[key]:
                                    updated[key] = current[key]
                        layout_json_string = json.dumps(updated)
                        save_session(updated, workspace_path)
                    elif "layout_json" in updated:
                        # move_object returns updated layout as a nested string
                        try:
                            moved_layout = json.loads(updated["layout_json"])
                            current = json.loads(layout_json_string)
                            for key in ("doors", "windows", "mep", "structure", "outline"):
                                if key not in moved_layout or not moved_layout[key]:
                                    if key in current and current[key]:
                                        moved_layout[key] = current[key]
                            layout_json_string = json.dumps(moved_layout)
                            save_session(moved_layout, workspace_path)
                        except (json.JSONDecodeError, KeyError):
                            pass

                        # Live viewport update —
                        # show object at new position immediately
                        try:
                            mcp_client.call_tool(
                                "set_viewport", {
                                    "layout_json": layout_json_string,
                                    "mode": "all",
                                })
                        except Exception:
                            pass

                        # Update placement history with new position
                        moved_info = updated.get("moved", {})
                        if moved_info:
                            obj_name = moved_info.get("name", "")
                            new_pos  = moved_info.get("position", [0, 0])
                            new_x    = round(new_pos[0], 2)
                            new_y    = round(new_pos[1], 2)
                            new_history = []
                            found = False
                            for entry in updated_placement_history:
                                if entry.get("name", "").lower() == obj_name.lower():
                                    new_history.append({
                                        **entry,
                                        "action": "moved",
                                        "from": entry.get("to", [new_x, new_y]),
                                        "to": [new_x, new_y],
                                    })
                                    found = True
                                else:
                                    new_history.append(entry)
                            if not found:
                                new_history.append({
                                    "name": obj_name,
                                    "action": "moved",
                                    "to": [new_x, new_y],
                                })
                            updated_placement_history = new_history
                            print(f"[tools] move_object: '{obj_name}' history updated to ({new_x}, {new_y})")
                    elif "doors" in updated:
                        # widen_doors returns only the doors array —
                        # merge into the current layout instead of replacing entirely
                        current = json.loads(layout_json_string)
                        current["doors"] = updated["doors"]
                        layout_json_string = json.dumps(current)
                        save_session(current, workspace_path)
            except (json.JSONDecodeError, AttributeError, KeyError) as exc:
                print(f"[tools] JSON parse warning: {exc}")

            # Append the tool call to conversation history, excluding layout_json
            # to keep logs readable — the full JSON is already in state
            new_messages.append({
                "role": "assistant",
                "content": json.dumps({
                    "action": "tool",
                    "final_response": "",
                    "tool_calls": [{"name": tool_name, "arguments": {
                        k: v for k, v in tool_args.items() if k != "layout_json"
                    }}],
                }),
            })

            # Truncate the tool result log to avoid flooding the console
            print(f"Tool result: {tool_output[:500]}")

            new_messages.append({
                "role": "user",
                "content": f"Tool result: {tool_output[:500]}",
            })

        return {
            "pending_tool_calls":  [],
            "iteration":           iteration,
            "layout_json_string":  layout_json_string,
            "messages":            new_messages,
            "placement_history":   updated_placement_history,
        }

    return tool_node
