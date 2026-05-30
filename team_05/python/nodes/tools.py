from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Any
from _runtime.llm import write_tool_result
from live_material_api import live_db

# live_db is already initialized in the imported file,
# so we just assign it to sheets_db to keep your variable names intact!
sheets_db = live_db

# ---------------------------------------------------------------------------
# Cost rates loader (for virtual tools)
# ---------------------------------------------------------------------------

_cost_rates_cache: dict = {}

def _load_cost_rates() -> dict:
    global _cost_rates_cache
    if _cost_rates_cache:
        return _cost_rates_cache
    candidates = [
        Path(__file__).resolve().parents[2] / "gh" / "cost_rates.json",
        Path(__file__).resolve().parents[1] / "cost_rates.json",
        Path("cost_rates.json"),
    ]
    for p in candidates:
        if p.exists():
            _cost_rates_cache = json.loads(p.read_text(encoding="utf-8"))
            return _cost_rates_cache
    return {}


def _normalise_material(s: str) -> str:
    return s.lower().replace(" ", "_").replace("-", "_")


def _polygon_perimeter(polygon: list) -> float:
    if not polygon or len(polygon) < 2:
        return 0.0
    total = 0.0
    n = len(polygon)
    for i in range(n):
        p1, p2 = polygon[i], polygon[(i + 1) % n]
        total += math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
    return total


def _find_room(layout: dict, room_name: str) -> dict | None:
    for room in layout.get("rooms", []):
        if room.get("name", "").lower() == room_name.lower():
            # Normalise area field: support both area_m2 and attributes.area
            if "area_m2" not in room:
                area = room.get("attributes", {}).get("area")
                if area is not None:
                    room = {**room, "area_m2": area}
            # Normalise polygon field: support both polygon and geometry
            if "polygon" not in room and "geometry" in room:
                room = {**room, "polygon": room["geometry"]}
            return room
    return None


# ---------------------------------------------------------------------------
# Virtual tool handlers
# ---------------------------------------------------------------------------

def _handle_get_count_by_type(tool_args: dict, state: dict) -> str:
    element_type = tool_args.get("element_type", "").lower().rstrip("s")  # normalise plural
    layout = json.loads(state.get("layout_json_string", "{}"))

    # Support both layout schemas:
    # new: top-level "doors", "windows", "rooms", "columns" arrays
    # old: "openings" array with type field, "rooms", "columns"
    type_map = {
        "door":   lambda l: len(l.get("doors", [])) or sum(1 for o in l.get("openings", []) if o.get("type") == "door"),
        "window": lambda l: len(l.get("windows", [])) or sum(1 for o in l.get("openings", []) if o.get("type") == "window"),
        "room":   lambda l: len(l.get("rooms", [])),
        "column": lambda l: len(l.get("columns", [])),
    }
    counter = type_map.get(element_type)
    if not counter:
        return json.dumps({"error": f"Unknown element type '{element_type}'. Use door, window, room, or column."})

    count = counter(layout)
    return json.dumps({"element_type": element_type, "count": count})


def _handle_get_area_by_type(tool_args: dict, state: dict) -> str:
    element_type = tool_args.get("element_type", "").lower()
    layout = json.loads(state.get("layout_json_string", "{}"))

    total_area = 0.0
    if element_type in ("floor", "ceiling", "room"):
        for room in layout.get("rooms", []):
            area = room.get("area_m2") or room.get("attributes", {}).get("area", 0)
            total_area += float(area)
    else:
        return json.dumps({"error": f"Area lookup not supported for '{element_type}'. Use room/floor/ceiling."})

    return json.dumps({"element_type": element_type, "total_area_m2": round(total_area, 2)})


def _handle_compute_finish_cost(tool_args: dict, state: dict) -> str:
    room_name = tool_args.get("room_name", "")
    surface = tool_args.get("surface", "floor").lower()
    material = _normalise_material(tool_args.get("material", ""))
    height_m = float(tool_args.get("height_m", 3.0))
    area_override = tool_args.get("area_m2")

    layout = json.loads(state.get("layout_json_string", "{}"))
    room = _find_room(layout, room_name)
    if not room:
        return json.dumps({"error": f"Room '{room_name}' not found in layout"})

    rates_db = _load_cost_rates().get("room_finishes", {})

    if surface == "floor":
        section = rates_db.get("floor_finish", {})
        rate = section.get("by_material", {}).get(material, section.get("default", 49))
        area_m2 = area_override if area_override is not None else room.get("area_m2", 0)
    elif surface == "wall":
        section = rates_db.get("wall_finish", {})
        rate = section.get("by_material", {}).get(material, section.get("default", 24))
        if area_override is not None:
            area_m2 = area_override
        else:
            perimeter = _polygon_perimeter(room.get("polygon", []))
            area_m2 = perimeter * height_m
    elif surface == "ceiling":
        section = rates_db.get("ceiling_material", {})
        rate = section.get("by_material", {}).get(material, section.get("default", 35))
        area_m2 = area_override if area_override is not None else room.get("area_m2", 0)
    else:
        return json.dumps({"error": f"Unknown surface '{surface}'. Must be floor, wall, or ceiling"})

    cost = round(area_m2 * rate, 2)
    return json.dumps({
        "room_name": room_name,
        "surface": surface,
        "material": material,
        "area_m2": round(area_m2, 2),
        "rate_per_m2": rate,
        "finish_cost": cost,
        "currency": "USD",
    })


def _handle_compute_slab_cost(tool_args: dict, state: dict) -> str:
    room_name = tool_args.get("room_name", "")
    thickness_m = float(tool_args.get("thickness_m", 0.2))
    material = _normalise_material(tool_args.get("material", "rc_solid"))
    area_override = tool_args.get("area_m2")

    layout = json.loads(state.get("layout_json_string", "{}"))
    room = _find_room(layout, room_name)
    if not room:
        return json.dumps({"error": f"Room '{room_name}' not found in layout"})

    area_m2 = area_override if area_override is not None else room.get("area_m2", 0)

    slab_section = _load_cost_rates().get("room_finishes", {}).get("slab_material", {})
    rate_per_m3 = slab_section.get("by_material", {}).get(material, slab_section.get("default", 435))

    slab_cost = round(area_m2 * thickness_m * rate_per_m3, 2)
    room_base_cost = room.get("total_cost", 0)

    return json.dumps({
        "room_name": room_name,
        "material": material,
        "area_m2": round(area_m2, 2),
        "thickness_m": thickness_m,
        "rate_per_m3": rate_per_m3,
        "slab_cost": slab_cost,
        "room_base_cost": round(room_base_cost, 2),
        "room_slabs_total": slab_cost,
        "room_finishes_total": 0,
        "room_updated_total_cost": round(room_base_cost + slab_cost, 2),
        "currency": "USD",
    })


# ---------------------------------------------------------------------------
# Tool node — executes MCP tool calls requested by the reason node.
# ---------------------------------------------------------------------------

def build_tool_node(mcp_client, allowed_tools, edited_layout_path, cost_db: dict | None = None):
    """Return a tool node function ready to be added to a LangGraph StateGraph."""

    allowed_names = {t["name"] for t in allowed_tools if t.get("name")}

    def tool_node(state):

        # Iterate over the pending tool calls
        for call in state["pending_tool_calls"]:

            # Stop the process if max number of iterations is reached
            state["iteration"] += 1
            if state["iteration"] > state["max_iterations"]:
                raise RuntimeError("Max iterations exceeded")


            # Get the tool name and check it is valid. Older graph stubs used
            # {"tool": ..., "action": ..., "args": ...}; the LLM uses
            # {"name": ..., "arguments": ...}. Accept both shapes.
            tool_name = call.get("name") or call.get("action")
            if not tool_name:
                raise RuntimeError(f"Tool call is missing a name/action: {call}")

            if tool_name not in allowed_names:
                raise RuntimeError(f"Tool '{tool_name}' is not in the allowed tools list")

            raw_args = call.get("arguments", call.get("args", {}))
            if raw_args is None:
                raw_args = {}
            if not isinstance(raw_args, dict):
                raise RuntimeError(f"Tool call arguments must be an object: {call}")

            print(f"Calling tool: {tool_name} with arguments: {raw_args}")

            # Cleanup any null values accidentally included by the LLM
            tool_args = {k: v for k, v in raw_args.items() if v is not None}

            # Inject layout_json for any tool that needs it
            if "layout_json" in tool_args:
                tool_args["layout_json"] = state["layout_json_string"]
            
            # ENFORCE: compute_room_cost always receives the FULL layout_schema JSON.
            # This is the ONLY sanctioned path for room/space area + cost.
            if tool_name == "compute_room_cost":
                tool_args["layout_schema"] = state["layout_json_string"]
                print(
                    f"[ENFORCE] compute_room_cost via Grasshopper MCP | room='{tool_args.get('room_name')}' | "
                    f"layout_schema bytes={len(state['layout_json_string'])}"
                )

            # Call the tool — virtual tools are handled locally; everything else goes to MCP
            if tool_name == "get_unit_cost_by_type":
                element_type = _normalise_material(str(tool_args.get("element_type", "")))
                subtype = _normalise_material(str(tool_args.get("subtype", "")))
                rates = _load_cost_rates()

                # Look up cost_rates.json first: doors → by_subtype or by_material leaf
                cost = None
                if element_type in ("door", "doors"):
                    door_rates = rates.get("doors", {})
                    cost = (
                        door_rates.get("by_subtype", {}).get(subtype)
                        or rates.get("door_finishes", {}).get("leaf_material", {}).get("by_material", {}).get(subtype)
                        or door_rates.get("default")
                    )
                elif element_type in ("window", "windows"):
                    win_rates = rates.get("windows", {})
                    cost = (
                        win_rates.get("by_subtype", {}).get(subtype)
                        or rates.get("window_finishes", {}).get("by_material", {}).get(subtype)
                        or win_rates.get("default")
                    )
                elif element_type in ("column", "columns"):
                    col_rates = rates.get("columns", {})
                    cost = col_rates.get("by_subtype", {}).get(subtype) or col_rates.get("default")

                # Fall back to live Supabase rate if cost_rates.json has no match
                if cost is None:
                    cost = sheets_db.get_live_rate(element_type, base_rate=500.0)

                tool_output = json.dumps(
                    {"element_type": element_type, "subtype": subtype or None, "unit_cost": cost, "currency": "USD"}
                    if cost is not None
                    else {"error": f"No cost data found for '{element_type}' subtype '{subtype}'"}
                )
            elif tool_name == "get_count_by_type":
                tool_output = _handle_get_count_by_type(tool_args, state)
            elif tool_name == "get_area_by_type":
                tool_output = _handle_get_area_by_type(tool_args, state)
            elif tool_name == "compute_finish_cost":
                tool_output = _handle_compute_finish_cost(tool_args, state)
            elif tool_name == "compute_slab_cost":
                tool_output = _handle_compute_slab_cost(tool_args, state)
            else:
                tool_output = mcp_client.call_tool(tool_name, tool_args)

            # Store the updated layout returned by the MCP tool to a json file
            write_tool_result(tool_output, edited_layout_path)

            # Only update the layout in state when the tool output is actually
            # a layout (has a "rooms" key). Cost-result dicts from virtual tools
            # must NOT overwrite the layout.
            try:
                updated = json.loads(tool_output.strip())
                if isinstance(updated, dict) and "rooms" in updated:
                    state["layout_json_string"] = json.dumps(updated)
                    state["layout_data"] = updated
                    state["has_layout"] = True
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
        state["return_to"] = state.get("return_to", "reasoning")
        return state

    return tool_node
