from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from _runtime.llm import write_tool_result


# ---------------------------------------------------------------------------
# Tool schemas — used by the LLM to know what actions are available.
# ---------------------------------------------------------------------------

def get_action_tools() -> list[dict[str, Any]]:
    """Return the list of tool schemas the agent LLM can call."""
    return [
        {
            "name": "tag_and_audit",
            "description": "Generate a structural column/beam grid for the current layout. Call ONLY when the user explicitly requests grid generation.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "layout_json": {"type": "string", "description": "The layout JSON string."},
                    "typology":    {"type": "string", "enum": ["column_grid", "perimeter_load_bearing", "shear_wall"], "description": "Structural typology."},
                    "grid_spacing":{"type": "number", "description": "Target grid spacing in metres (default 4.0)."},
                },
                "required": ["layout_json"],
            },
        },
        {
            "name": "modify_structure",
            "description": "Modify a structural element: remove it or update an attribute.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action":     {"type": "string", "enum": ["remove", "set_attribute"]},
                    "element_id": {"type": "string", "description": "The ID of the element to modify."},
                    "attribute":  {"type": "string", "description": "Attribute name (for set_attribute)."},
                    "value":      {"type": "string", "description": "New value (for set_attribute)."},
                },
                "required": ["action", "element_id"],
            },
        },
        {
            "name": "remove_element",
            "description": "Remove a single structural element by ID. For columns, collinear beams are merged automatically.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "string", "description": "The ID of the column or beam to remove."},
                },
                "required": ["element_id"],
            },
        },
        {
            "name": "add_midspan_column",
            "description": "Add a new column at the midpoint of an existing beam, splitting it into two shorter beams.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "beam_id":  {"type": "string", "description": "The ID of the beam to split."},
                    "material": {"type": "string", "description": "Material for the new column (RCC / Steel / Timber)."},
                },
                "required": ["beam_id"],
            },
        },
        {
            "name": "upgrade_element_section",
            "description": "Upgrade a beam or column to the next larger standard section.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "element_id":  {"type": "string", "description": "The ID of the element to upgrade."},
                    "new_section": {"type": "string", "description": "Target section string, e.g. '300x600' or 'IPE300'."},
                },
                "required": ["element_id"],
            },
        },
        {
            "name": "add_column",
            "description": "Add a NEW column at a distance from a reference column, measured along the axes from that column. Use for 'add a column 2 m in x from C3' or 'put a column 1.5 m below C5 on level 02'. dx is along X (east +, west −), dy along Y (north +, south −). Stays orthogonal.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "reference_id": {"type": "string", "description": "Column to measure the offset from."},
                    "dx": {"type": "number", "description": "Metres along X (east +, west −). 0 / omit for none."},
                    "dy": {"type": "number", "description": "Metres along Y (north +, south −). 0 / omit for none."},
                    "level_key": {"type": "string", "description": "Level to add the column on, e.g. 'level_02'. Omit for the same level as the reference column."},
                },
                "required": ["reference_id"],
            },
        },
        {
            "name": "add_beam",
            "description": "Add a beam connecting two existing columns. The two columns MUST share an X (vertical beam) or a Y (horizontal beam) — diagonal beams are rejected. Use for 'add a beam between C3 and C5 on level 02'.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "column_a": {"type": "string", "description": "First column id."},
                    "column_b": {"type": "string", "description": "Second column id."},
                    "level_key": {"type": "string", "description": "Level to add the beam on, e.g. 'level_02'. Omit to auto-detect from column positions."},
                },
                "required": ["column_a", "column_b"],
            },
        },
        {
            "name": "move_element",
            "description": "Move a column (or beam) to clear a window/door clash or fine-tune grid spacing. Use dx/dy in metres to nudge it, or absolute x/y to place it. Keep moves axis-aligned (dx OR dy) so the grid stays orthogonal. Beams joined to a moved column follow it automatically.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "string", "description": "ID of the column or beam to move."},
                    "dx": {"type": "number", "description": "Metres to move along X (east +, west -). 0 or omit for none."},
                    "dy": {"type": "number", "description": "Metres to move along Y (north +, south -). 0 or omit for none."},
                    "x": {"type": "number", "description": "Optional absolute X position in metres (overrides dx)."},
                    "y": {"type": "number", "description": "Optional absolute Y position in metres (overrides dy)."},
                },
                "required": ["element_id"],
            },
        },
        {
            "name": "set_material",
            "description": "Change the structural material. Use for 'switch to timber', 'change material to concrete/RCC', 'make it steel'. Optionally scope to one level and/or element type, e.g. 'change all columns and beams of level 2 to timber'.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "material": {"type": "string", "enum": ["RCC", "STEEL", "TIMBER"],
                                  "description": "Target material."},
                    "level": {"type": "string",
                               "description": "Optional level key to limit the change to, e.g. 'level_02'. Omit for all levels."},
                    "element_type": {"type": "string", "enum": ["column", "beam"],
                                      "description": "Optional: limit to 'column' or 'beam'. Omit for both."},
                },
                "required": ["material"],
            },
        },
        {
            "name": "evaluate_structure",
            "description": "Run a full structural evaluation (bending, shear, deflection, buckling) on all elements in the current layout.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "layout_json": {"type": "string", "description": "The layout JSON string."},
                },
                "required": [],
            },
        },
    ]


# ---------------------------------------------------------------------------
# Tool node — executes MCP tool calls requested by the reason node.
# ---------------------------------------------------------------------------

def build_tool_node(mcp_client, allowed_tools, edited_layout_path):
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

            # Call the tool
            tool_output = mcp_client.call_tool(tool_name, tool_args)

            # Only persist results that look like a layout (have layoutId or rooms)
            try:
                _parsed = json.loads(tool_output.strip())
                if isinstance(_parsed, dict) and ("layoutId" in _parsed or "rooms" in _parsed):
                    write_tool_result(tool_output, edited_layout_path)
            except (json.JSONDecodeError, AttributeError):
                pass

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
            print(f"Tool result: {tool_output}")

        state["pending_tool_calls"] = None
        return state

    return tool_node
