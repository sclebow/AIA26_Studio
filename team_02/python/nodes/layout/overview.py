"""
OVERVIEW_RESPOND node — lists rooms in a layout with basic attributes.
Pure Python, no LLM. No analysis, no persona. Writes final_response.
"""

from __future__ import annotations
import json as _json


def overview_respond_node(state: dict) -> dict:
    layout_json_string = state.get("layout_json_string", "")
    layout_id          = state.get("layout_id", "?")

    if not layout_json_string:
        return {
            **state,
            "final_response": (
                "No layout loaded. Mention a layout number (201, 202, or 203) "
                "to get started."
            ),
        }

    try:
        data = _json.loads(layout_json_string)
    except Exception:
        return {**state, "final_response": "Could not read the layout data."}

    name  = data.get("name", "Layout {}".format(layout_id))
    rooms = data.get("rooms", [])

    if not rooms:
        return {**state, "final_response": "{} has no rooms defined.".format(name)}

    lines = [
        "{} -- {} room{}:".format(name, len(rooms), "s" if len(rooms) != 1 else "")
    ]

    for r in rooms:
        attrs       = r.get("attributes", {})
        rtype       = attrs.get("roomType", "unknown").capitalize()
        area        = attrs.get("area", "?")
        height      = attrs.get("height", "?")
        orientation = attrs.get("orientation", "?")

        try:
            area_str = "{:.0f} m2".format(float(area))
        except (TypeError, ValueError):
            area_str = "? m2"

        lines.append("  - {} ({}) -- {}, {}m ceiling, facing {}".format(
            r.get("name", "?"),
            rtype,
            area_str,
            height,
            orientation,
        ))

    lines.append("")
    lines.append(
        "To run a comfort analysis, add a persona -- "
        "e.g. 'analyze layout {} for an elderly user'.".format(layout_id)
    )

    print("[overview] Listing {} rooms for layout {}".format(len(rooms), layout_id))

    return {
        **state,
        "final_response": "\n".join(lines),
    }
