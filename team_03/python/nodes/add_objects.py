from __future__ import annotations
import json
import re
from typing import Any
from _runtime.session import save_session


_OBJECT_PATTERN = re.compile(
    r'([a-zA-Z_][a-zA-Z0-9_ ]*)'
    r':(\d+\.?\d*)[x*](\d+\.?\d*)[x*](\d+\.?\d*)'
    r'(?::x=([\d.]+),y=([\d.]+))?'
)


def _parse_objects_list(objects_str: str) -> list[dict]:
    results = []
    for m in _OBJECT_PATTERN.finditer(objects_str):
        name, w, d, h, x, y = m.groups()
        if x is None or y is None:
            continue
        results.append({
            "name":     name.strip(),
            "position": [float(x), float(y)],
            "size":     [float(w), float(d), float(h)],
        })
    return results


def build_add_objects_node(mcp_client, workspace_path):

    def add_objects_node(state):
        iteration = state["iteration"] + 1
        if iteration > state["max_iterations"]:
            raise RuntimeError("Max iterations exceeded")

        updated_placement_history = state.get("placement_history") or []

        object_to_place = state.get("object_to_place")
        if not object_to_place:
            print("[add_objects] Warning: object_to_place is empty — skipping placement.")
            return {"iteration": iteration, "object_to_place": {}}

        raw_objects = object_to_place.get("objects_list", "")
        if isinstance(raw_objects, str):
            parsed_objects = _parse_objects_list(raw_objects)
            objects_list_json = json.dumps(parsed_objects)
        else:
            parsed_objects = []
            objects_list_json = json.dumps(raw_objects)

        layout_json_string = state["layout_json_string"]

        _pre_layout = json.loads(layout_json_string)
        _pre_doors = len(_pre_layout.get("doors", []))
        print(f"[add_objects] Layout integrity before MCP: {_pre_doors} doors, "
              f"{len(_pre_layout.get('rooms', []))} rooms, "
              f"{len(_pre_layout.get('furniture', []))} furniture")

        tool_args = {
            "layout_json":  layout_json_string,
            "room_name":    object_to_place["room_name"],
            "objects_list": objects_list_json,
            "user_profile": object_to_place.get("user_profile", "standard"),
            "clear_room":   object_to_place.get("clear_room", False),
        }
        try:
            tool_output = mcp_client.call_tool("place_objects", tool_args)
        except Exception as exc:
            print(f"[add_objects] MCP call failed: {exc}")
            tool_output = f"MCP error: {exc}"

        updates: dict = {
            "iteration":            iteration,
            "object_to_place":      {},
            "last_placement_result": None,
        }

        try:
            parsed = json.loads(tool_output.strip())
            if isinstance(parsed, dict):
                _has_rooms = "rooms" in parsed
                _has_doors = len(parsed.get("doors", [])) if isinstance(parsed.get("doors"), list) else 0
                print(f"[add_objects] MCP response: has_rooms={_has_rooms}, doors={_has_doors}, keys={list(parsed.keys())[:8]}")
                if "rooms" in parsed:
                    current_layout = json.loads(layout_json_string)
                    for key in ("doors", "windows", "mep", "structure", "outline"):
                        if key not in parsed or not parsed[key]:
                            if key in current_layout and current_layout[key]:
                                parsed[key] = current_layout[key]
                    layout_json_string = json.dumps(parsed)
                    updates["layout_json_string"] = layout_json_string
                    save_session(parsed, workspace_path)
                    updates["last_placement_result"] = parsed
                    # Rebuild base spatial graph from updated layout.
                    # Rebuild from scratch — prior analysis edges are stale.
                    try:
                        from spatial_graph import build_graph_from_layout, graph_to_dict, serialize_for_llm
                        _sg = build_graph_from_layout(parsed)
                        updates["spatial_graph"] = graph_to_dict(_sg)
                        updates["spatial_graph_text"] = serialize_for_llm(_sg)
                        # Highlight added/moved furniture in the visualizer
                        try:
                            from visualize_interactive import build_interactive_graph as _viz
                            from pathlib import Path as _Path
                            _pre_geom = {f.get("id"): f.get("geometry")
                                         for f in _pre_layout.get("furniture", [])}
                            _new_viz_ids = set()
                            for _f in parsed.get("furniture", []):
                                _fid = _f.get("id")
                                if _fid not in _pre_geom:
                                    _new_viz_ids.add(_fid)        # newly added
                                elif _f.get("geometry") != _pre_geom[_fid]:
                                    _new_viz_ids.add(_fid)        # moved
                            _viz_path = _Path(__file__).parent.parent / "view_graph" / "spatial_graph_interactive.html"
                            _viz(_sg, title="Spatial Graph", output_path=_viz_path,
                                 new_ids=_new_viz_ids)
                            updates["viz_highlight_ids"] = list(_new_viz_ids)
                            print(f"\033[36m[viz] Graph updated: "
                                  f"{len(_new_viz_ids)} elements highlighted\033[0m")
                        except Exception as _ve:
                            print(f"[viz] Warning: {_ve}")
                    except Exception:
                        pass
                else:
                    updates["last_placement_result"] = parsed
        except (json.JSONDecodeError, AttributeError):
            pass

        if "layout_json_string" not in updates:
            try:
                current_layout = json.loads(layout_json_string)
                room_name = object_to_place.get("room_name", "")
                if isinstance(raw_objects, str):
                    placed_objects = _parse_objects_list(raw_objects)
                else:
                    placed_objects = raw_objects if isinstance(raw_objects, list) else []

                if placed_objects:
                    room_id = None
                    for room in current_layout.get("rooms", []):
                        if room.get("name", "").lower() == room_name.lower():
                            room_id = room.get("id")
                            break

                    changes = []

                    for obj in placed_objects:
                        pos  = obj.get("position", [0, 0])
                        size = obj.get("size", [1, 1, 1])
                        name = obj.get("name", "")
                        x, y = pos[0], pos[1]
                        w, d = size[0], size[1]

                        # Hard overlap check — shift if overlapping existing furniture
                        for existing in current_layout.get("furniture", []):
                            eg = existing.get("geometry", [])
                            if len(eg) < 4:
                                continue
                            exs = [p[0] for p in eg]
                            eys = [p[1] for p in eg]
                            ex0, ex1 = min(exs), max(exs)
                            ey0, ey1 = min(eys), max(eys)
                            overlap_x = x < ex1 + 0.9 and x + w > ex0 - 0.9
                            overlap_y = y < ey1 + 0.9 and y + d > ey0 - 0.9
                            if overlap_x and overlap_y:
                                x = ex1 + 0.9
                                print(f"[add_objects] Overlap detected with '{existing.get('name')}' — shifted to x={x:.2f}")
                                break

                        new_geom = [
                            [x, y], [x + w, y], [x + w, y + d],
                            [x, y + d], [x, y],
                        ]

                        found = False
                        for furn in current_layout.get("furniture", []):
                            if furn.get("name", "").lower() == name.lower():
                                old_geom = furn.get("geometry", [])
                                old_x = old_geom[0][0] if old_geom else 0
                                old_y = old_geom[0][1] if old_geom else 0
                                furn["geometry"] = new_geom
                                if abs(old_x - x) > 0.01 or abs(old_y - y) > 0.01:
                                    changes.append({
                                        "name":   name,
                                        "action": "moved",
                                        "from":   [round(old_x, 2), round(old_y, 2)],
                                        "to":     [round(x, 2), round(y, 2)],
                                        "size":   [w, d],
                                        "room":   room_name,
                                    })
                                found = True
                                break

                        if not found:
                            furn_id = f"furn-{len(current_layout.get('furniture', [])) + 1}"
                            new_furn = {
                                "id":       furn_id,
                                "name":     name,
                                "geometry": new_geom,
                                "attributes": {
                                    "roomId": room_id or "",
                                    "height": size[2] if len(size) > 2 else 1.0,
                                },
                            }

                            # Door blocking check — warn if object placed within
                            # 1.0m of any door midpoint (OSHA door clearance zone)
                            door_warnings = []
                            # Use closest corner distance not centroid —
                            # large objects like conveyors have wide footprints
                            furn_corners = [[x, y], [x+w, y], [x+w, y+d], [x, y+d]]
                            for door in current_layout.get("doors", []):
                                dg = door.get("geometry", [])
                                if len(dg) == 2:
                                    dmx = (dg[0][0] + dg[1][0]) / 2.0
                                    dmy = (dg[0][1] + dg[1][1]) / 2.0
                                    min_dist = min(
                                        ((cx - dmx) ** 2 + (cy - dmy) ** 2) ** 0.5
                                        for cx, cy in furn_corners
                                    )
                                    if min_dist < 1.0:
                                        door_warnings.append(
                                            f"WARNING: '{name}' is {min_dist:.2f}m from door "
                                            f"'{door.get('name', door.get('id', '?'))}' "
                                            f"— minimum clearance is 1.0m"
                                        )
                            if door_warnings:
                                for w_msg in door_warnings:
                                    print(f"[add_objects] {w_msg}")

                            # Window blocking check — warn if object placed within
                            # 0.5m of any window midpoint (NFPA 101 egress + ventilation)
                            window_warnings = []
                            for window in current_layout.get("windows", []):
                                wg = window.get("geometry", [])
                                if len(wg) == 2:
                                    wmx = (wg[0][0] + wg[1][0]) / 2.0
                                    wmy = (wg[0][1] + wg[1][1]) / 2.0
                                    min_dist = min(
                                        ((cx - wmx) ** 2 + (cy - wmy) ** 2) ** 0.5
                                        for cx, cy in furn_corners
                                    )
                                    if min_dist < 0.5:
                                        window_warnings.append(
                                            f"WARNING: '{name}' is {min_dist:.2f}m from window "
                                            f"'{window.get('name', window.get('id', '?'))}' "
                                            f"— minimum clearance is 0.5m (NFPA 101)"
                                        )
                            if window_warnings:
                                for w_msg in window_warnings:
                                    print(f"[add_objects] {w_msg}")

                            current_layout.setdefault("furniture", []).append(new_furn)
                            changes.append({
                                "name":     name,
                                "action":   "added",
                                "to":       [round(x, 2), round(y, 2)],
                                "size":     [w, d],
                                "room":     room_name,
                                "door_warnings": door_warnings,
                                "window_warnings": window_warnings,
                            })

                    layout_json_string = json.dumps(current_layout)
                    updates["layout_json_string"] = layout_json_string
                    save_session(current_layout, workspace_path)
                    # Rebuild base spatial graph from updated layout (fallback path).
                    try:
                        from spatial_graph import build_graph_from_layout, graph_to_dict, serialize_for_llm
                        _sg = build_graph_from_layout(current_layout)
                        updates["spatial_graph"] = graph_to_dict(_sg)
                        updates["spatial_graph_text"] = serialize_for_llm(_sg)
                        # Highlight added/moved furniture in the visualizer
                        try:
                            from visualize_interactive import build_interactive_graph as _viz
                            from pathlib import Path as _Path
                            _changed_names = {c["name"].lower() for c in changes}
                            _new_viz_ids = set()
                            for _nid, _ndata in _sg.nodes(data=True):
                                if _ndata.get("name", "").lower() in _changed_names:
                                    _new_viz_ids.add(_nid)
                            _viz_path = _Path(__file__).parent.parent / "view_graph" / "spatial_graph_interactive.html"
                            _viz(_sg, title="Spatial Graph", output_path=_viz_path,
                                 new_ids=_new_viz_ids)
                            updates["viz_highlight_ids"] = list(_new_viz_ids)
                            print(f"\033[36m[viz] Graph updated: "
                                  f"{len(_new_viz_ids)} elements highlighted\033[0m")
                        except Exception as _ve:
                            print(f"[viz] Warning: {_ve}")
                    except Exception:
                        pass

                    updated_placement_history = updated_placement_history + changes
                    updates["placement_history"] = updated_placement_history

                    print(f"[add_objects] Updated {len(placed_objects)} furniture positions in layout state")
                    for c in changes:
                        if c["action"] == "moved":
                            print(f"  {c['name']}: ({c['from'][0]}, {c['from'][1]}) -> ({c['to'][0]}, {c['to'][1]})")
                        else:
                            print(f"  {c['name']}: NEW at ({c['to'][0]}, {c['to'][1]})")

            except Exception as exc:
                print(f"[add_objects] Warning: could not mirror placement to state: {exc}")

        queue = state.get("object_queue") or []
        if queue:
            if len(queue) % 5 == 0 or len(queue) < 3:
                print(f"[add_objects] Queue: {len(queue)} objects remaining")
            updates["object_queue"]    = queue
            updates["object_to_place"] = {}
        else:
            updates["object_queue"]    = []
            updates["object_to_place"] = {}

        updates["messages"] = [
            {
                "role": "assistant",
                "content": json.dumps({
                    "action":         "tool",
                    "final_response": "",
                    "tool_calls": [{"name": "place_objects", "arguments": {
                        k: v for k, v in tool_args.items() if k != "layout_json"
                    }}],
                }),
            },
            {
                "role":    "user",
                "content": f"Tool result: {tool_output[:500]}",
            },
        ]

        return updates

    return add_objects_node
