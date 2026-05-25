from __future__ import annotations
import json
from _runtime.llm import write_tool_result


def _generate_column_grid(layout_json_str: str, grid_spacing: float) -> str:
    layout = json.loads(layout_json_str)
    outline = layout.get("outline", [])
    if not outline:
        return layout_json_str

    xs = [p[0] for p in outline if len(p) >= 2]
    ys = [p[1] for p in outline if len(p) >= 2]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    def grid_pts(lo, hi, spacing):
        pts = [lo]
        cur = lo + spacing
        while cur < hi - spacing * 0.3:
            pts.append(round(cur, 3))
            cur += spacing
        if pts[-1] != hi:
            pts.append(hi)
        return pts

    x_pos = grid_pts(xmin, xmax, grid_spacing)
    y_pos = grid_pts(ymin, ymax, grid_spacing)
    letters = [chr(65 + i) for i in range(len(x_pos))]
    nums = list(range(1, len(y_pos) + 1))

    structure = []

    for xi, x in enumerate(x_pos):
        L = letters[xi]
        for yi, y in enumerate(y_pos):
            n = nums[yi]
            exterior = (x == xmin or x == xmax or y == ymin or y == ymax)
            structure.append({
                "id": f"{L}_{n}", "name": f"Column_{L}_{n}",
                "geometry": [[x, y]],
                "attributes": {
                    "type": "exterior" if exterior else "internal",
                    "dimensions": "200x200", "height": "3.5",
                    "isWallAligned": "true", "structuralRole": "primary",
                    "material": "RCC", "conflict": "None",
                },
            })

    for yi, y in enumerate(y_pos):
        n = nums[yi]
        for xi in range(len(x_pos) - 1):
            La, Lb = letters[xi], letters[xi + 1]
            x1, x2 = x_pos[xi], x_pos[xi + 1]
            structure.append({
                "id": f"{La}{Lb}_{n}", "name": f"Beam_{La}{Lb}_{n}",
                "geometry": [[x1, y], [x2, y]],
                "attributes": {
                    "type": "perimeter", "length": str(round(x2 - x1, 3)),
                    "depth": "300", "width": "200",
                    "isWallAligned": "True", "structuralRole": "primary",
                    "material": "RCC", "conflict": "None",
                },
            })

    for xi, x in enumerate(x_pos):
        L = letters[xi]
        for yi in range(len(y_pos) - 1):
            na, nb = nums[yi], nums[yi + 1]
            y1, y2 = y_pos[yi], y_pos[yi + 1]
            structure.append({
                "id": f"{L}_{na}{nb}", "name": f"Beam_{L}_{na}{nb}",
                "geometry": [[x, y1], [x, y2]],
                "attributes": {
                    "type": "perimeter", "length": str(round(y2 - y1, 3)),
                    "depth": "300", "width": "200",
                    "isWallAligned": "True", "structuralRole": "primary",
                    "material": "RCC", "conflict": "None",
                },
            })

    layout["structure"] = structure
    return json.dumps(layout)


def build_modify_node(mcp_client, allowed_tools, edited_layout_path):

    allowed_names = {t["name"] for t in allowed_tools if t.get("name")}

    def modify_node(state):
        print(f"\n{'='*50}")
        print(f"  NODE: MODIFY")
        print(f"{'='*50}")

        # Save original layout before first modification
        if not state.get("original_layout_json_string"):
            state["original_layout_json_string"] = state["layout_json_string"]

        last_tool = None
        for call in state["pending_tool_calls"]:
            state["iteration"] += 1
            if state["iteration"] > state["max_iterations"]:
                raise RuntimeError("Max iterations exceeded")

            tool_name = call["name"]
            last_tool = tool_name
            if tool_name not in allowed_names:
                raise RuntimeError(f"Tool '{tool_name}' is not in the allowed tools list")

            print(f"Calling tool: {tool_name} with arguments: {call['arguments']}")

            tool_args = {k: v for k, v in call["arguments"].items() if v is not None}

            if "layout_json" in tool_args:
                tool_args["layout_json"] = state["layout_json_string"]

            tool_output = mcp_client.call_tool(tool_name, tool_args)

            if not tool_output or not tool_output.strip():
                if tool_name == "tag_and_audit":
                    spacing = float(tool_args.get("grid_spacing", 4.0))
                    tool_output = _generate_column_grid(state["layout_json_string"], spacing)
                    print(f"[modify] GH returned empty — generated column grid in Python (spacing={spacing}m)")
                else:
                    print(f"[modify] WARNING: {tool_name} returned empty output — layout unchanged.")

            try:
                _parsed = json.loads(tool_output.strip())
                if isinstance(_parsed, dict) and ("layoutId" in _parsed or "rooms" in _parsed):
                    write_tool_result(tool_output, edited_layout_path)
            except (json.JSONDecodeError, AttributeError):
                pass

            try:
                updated = json.loads(tool_output.strip())
                if isinstance(updated, dict):
                    state["layout_json_string"] = json.dumps(updated)
            except (json.JSONDecodeError, AttributeError):
                pass

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
            print(f"Tool result: {tool_output[:200]}..." if len(tool_output) > 200 else f"Tool result: {tool_output}")

        state["pending_tool_calls"] = None
        state["came_from"] = "tag_and_audit" if last_tool == "tag_and_audit" else "modify"
        return state

    return modify_node
