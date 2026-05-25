from __future__ import annotations
import json
import re
from typing import Any
from _runtime.session import save_session


# ---------------------------------------------------------------------------
# objects_list parser — converts the LLM's compact string format to the
# JSON array the GH place_objects script expects.
#
# LLM produces:  "cnc_machine:2.0x1.5x1.2:x=5.0,y=3.0"
# GH expects:    [{"name": "cnc_machine", "position": [5.0, 3.0],
#                  "size": [2.0, 1.5, 1.2]}]
#
# Multiple objects can be comma-separated or newline-separated in the string.
# Items with no x=/y= coordinates are skipped — a position is required.
# ---------------------------------------------------------------------------

_OBJECT_PATTERN = re.compile(
    r'([a-zA-Z_][a-zA-Z0-9_ ]*)'        # name (allows spaces)
    r':(\d+\.?\d*)[x*](\d+\.?\d*)[x*](\d+\.?\d*)'  # WxDxH
    r'(?::x=([\d.]+),y=([\d.]+))?'      # optional :x=X,y=Y
)


def _parse_objects_list(objects_str: str) -> list[dict]:
    # Walk every regex match in the string — handles comma-separated,
    # newline-separated, or single-item input from the LLM.
    results = []
    for m in _OBJECT_PATTERN.finditer(objects_str):
        name, w, d, h, x, y = m.groups()
        if x is None or y is None:
            # Position is required; skip items the LLM forgot to coordinate.
            continue
        results.append({
            "name":     name.strip(),
            "position": [float(x), float(y)],
            "size":     [float(w), float(d), float(h)],
        })
    return results


# ---------------------------------------------------------------------------
# Object placement node — places ONE object at a time via the MCP tool.
# Collision detection is NOT done here — it runs as a separate graph step
# after this node returns. This node only places and saves.
# ---------------------------------------------------------------------------

def build_add_objects_node(mcp_client, workspace_path):
    """Return a node closure that places one object via the place_objects MCP tool.

    Capture mcp_client and workspace_path at build time (same closure pattern
    as build_tool_node and build_visibility_node) so add_objects_node(state)
    only needs the live graph state as its argument.
    """

    def add_objects_node(state):
        # Returns an update dict instead of mutating state.
        iteration = state["iteration"] + 1
        if iteration > state["max_iterations"]:
            raise RuntimeError("Max iterations exceeded")

        # ---------------------------------------------------------------------------
        # Guard: nothing queued -> skip.
        # The reason node sets object_to_place before routing here.
        # If it's missing or empty the graph wired incorrectly — warn and bail out
        # rather than crashing, so the graph can continue to the next step.
        # ---------------------------------------------------------------------------
        object_to_place = state.get("object_to_place")
        if not object_to_place:
            print("[add_objects] Warning: object_to_place is empty — skipping placement.")
            return {"iteration": iteration, "object_to_place": {}}

        # ---------------------------------------------------------------------------
        # Parse objects_list from LLM string format to JSON array.
        # The LLM emits "name:WxDxH:x=X,y=Y" but the GH script expects a JSON
        # array of dicts. Convert here so GH never has to handle raw strings.
        # If the LLM already sent a list (e.g. from a retry), use it directly.
        # ---------------------------------------------------------------------------
        raw_objects = object_to_place.get("objects_list", "")
        if isinstance(raw_objects, str):
            parsed_objects = _parse_objects_list(raw_objects)
            objects_list_json = json.dumps(parsed_objects)
        else:
            # Already a list — re-serialize to ensure valid JSON string.
            objects_list_json = json.dumps(raw_objects)

        # ---------------------------------------------------------------------------
        # Call the MCP place_objects tool with the coordinates the LLM decided.
        # layout_json is always injected here — never trusted from the LLM output
        # to guarantee the tool receives the latest saved state.
        # ---------------------------------------------------------------------------
        layout_json_string = state["layout_json_string"]

        # Diagnostic: verify doors exist before MCP call
        _pre_layout = json.loads(layout_json_string)
        _pre_doors = len(_pre_layout.get("doors", []))
        print(f"[add_objects] Layout integrity before MCP: {_pre_doors} doors, "
              f"{len(_pre_layout.get('rooms', []))} rooms, "
              f"{len(_pre_layout.get('furniture', []))} furniture")

        tool_args = {
            "layout_json": layout_json_string,
            "room_name": object_to_place["room_name"],
            "objects_list": objects_list_json,
            "user_profile": object_to_place.get("user_profile", "standard"),
            "clear_room": object_to_place.get("clear_room", False),
        }
        try:
            tool_output = mcp_client.call_tool("place_objects", tool_args)
        except Exception as exc:
            print(f"[add_objects] MCP call failed: {exc}")
            tool_output = f"MCP error: {exc}"

        # ---------------------------------------------------------------------------
        # Parse tool output — place_objects can return two different shapes:
        #   a) Full updated layout (has "rooms") -> replace session entirely.
        #   b) Result summary only (has "placed"/"failed") -> store for the next node.
        # Either way, save_session keeps workspace/session_active.json in sync
        # so a crash between placements doesn't lose work.
        # ---------------------------------------------------------------------------
        updates: dict = {
            "iteration": iteration,
            "object_to_place": {},
            "last_placement_result": None,
        }

        try:
            parsed = json.loads(tool_output.strip())
            if isinstance(parsed, dict):
                _has_rooms = "rooms" in parsed
                _has_doors = len(parsed.get("doors", [])) if isinstance(parsed.get("doors"), list) else 0
                print(f"[add_objects] MCP response: has_rooms={_has_rooms}, doors={_has_doors}, keys={list(parsed.keys())[:8]}")
                if "rooms" in parsed:
                    # Full layout returned — merge with current state to preserve
                    # layers the MCP tool might not return (doors, windows, mep,
                    # structure, outline). Only update layers that the response
                    # explicitly provides; keep everything else from the current state.
                    current_layout = json.loads(layout_json_string)
                    for key in ("doors", "windows", "mep", "structure", "outline"):
                        if key not in parsed or not parsed[key]:
                            if key in current_layout and current_layout[key]:
                                parsed[key] = current_layout[key]
                    layout_json_string = json.dumps(parsed)
                    updates["layout_json_string"] = layout_json_string
                    save_session(parsed, workspace_path)
                    updates["last_placement_result"] = parsed
                else:
                    # Summary only — store so collision or reason nodes can inspect it
                    updates["last_placement_result"] = parsed
        except (json.JSONDecodeError, AttributeError):
            pass

        # -----------------------------------------------------------------------
        # If the MCP tool returned a summary (not a full layout), the furniture
        # positions in layout_json_string are stale. Mirror the placement into
        # the state's layout so downstream analysis nodes see the new positions.
        # -----------------------------------------------------------------------
        if "layout_json_string" not in updates:
            try:
                current_layout = json.loads(layout_json_string)
                room_name = object_to_place.get("room_name", "")
                # Parse the objects we sent to place_objects
                if isinstance(raw_objects, str):
                    placed_objects = _parse_objects_list(raw_objects)
                else:
                    placed_objects = raw_objects if isinstance(raw_objects, list) else []

                if placed_objects:
                    # Find the room ID for this room name
                    room_id = None
                    for room in current_layout.get("rooms", []):
                        if room.get("name", "").lower() == room_name.lower():
                            room_id = room.get("id")
                            break

                    # Track what changed for the placement history
                    changes = []

                    for obj in placed_objects:
                        pos = obj.get("position", [0, 0])
                        size = obj.get("size", [1, 1, 1])
                        name = obj.get("name", "")
                        x, y = pos[0], pos[1]
                        w, d = size[0], size[1]

                        # Build furniture polygon from position + size
                        new_geom = [
                            [x, y], [x + w, y], [x + w, y + d],
                            [x, y + d], [x, y],
                        ]

                        # Try to find and update existing furniture by name
                        found = False
                        for furn in current_layout.get("furniture", []):
                            if furn.get("name", "").lower() == name.lower():
                                old_geom = furn.get("geometry", [])
                                old_x = old_geom[0][0] if old_geom else 0
                                old_y = old_geom[0][1] if old_geom else 0
                                furn["geometry"] = new_geom
                                # Only record as a move if position actually changed
                                if abs(old_x - x) > 0.01 or abs(old_y - y) > 0.01:
                                    changes.append({
                                        "name": name,
                                        "action": "moved",
                                        "from": [round(old_x, 2), round(old_y, 2)],
                                        "to": [round(x, 2), round(y, 2)],
                                        "size": [w, d],
                                        "room": room_name,
                                    })
                                found = True
                                break

                        # If not found, add as new furniture
                        if not found:
                            furn_id = f"furn-{len(current_layout.get('furniture', [])) + 1}"
                            new_furn = {
                                "id": furn_id,
                                "name": name,
                                "geometry": new_geom,
                                "attributes": {"roomId": room_id or ""},
                            }
                            current_layout.setdefault("furniture", []).append(new_furn)
                            changes.append({
                                "name": name,
                                "action": "added",
                                "to": [round(x, 2), round(y, 2)],
                                "size": [w, d],
                                "room": room_name,
                            })

                    layout_json_string = json.dumps(current_layout)
                    updates["layout_json_string"] = layout_json_string
                    save_session(current_layout, workspace_path)

                    # Merge with existing placement history
                    prev_history = state.get("placement_history") or []
                    updates["placement_history"] = prev_history + changes

                    print(f"[add_objects] Updated {len(placed_objects)} furniture positions in layout state")
                    for c in changes:
                        if c["action"] == "moved":
                            print(f"  {c['name']}: ({c['from'][0]}, {c['from'][1]}) -> ({c['to'][0]}, {c['to'][1]})")
                        else:
                            print(f"  {c['name']}: NEW at ({c['to'][0]}, {c['to'][1]})")

            except Exception as exc:
                print(f"[add_objects] Warning: could not mirror placement to state: {exc}")

        # Append tool call to conversation history.
        # Exclude layout_json from logged arguments — it's large and already in state.
        updates["messages"] = [
            {
                "role": "assistant",
                "content": json.dumps({
                    "action": "tool",
                    "final_response": "",
                    "tool_calls": [{"name": "place_objects", "arguments": {
                        k: v for k, v in tool_args.items() if k != "layout_json"
                    }}],
                }),
            },
            {
                "role": "user",
                "content": f"Tool result: {tool_output[:500]}",
            },
        ]

        return updates

    return add_objects_node
