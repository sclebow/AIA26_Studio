"""
MODIFY_GLAZING — raises glazing ratio and/or upgrades glazing type.
Returns structured layout_diff for frontend animation.
"""

from __future__ import annotations
from nodes.editing import _edits


def build_modify_glazing_node():
    def modify_glazing_node(state: dict) -> dict:
        raw_prompt      = state.get("raw_prompt", "")
        layout_str      = state.get("layout_json_string", "")
        original_scores = state.get("last_scores_json", "")
        room_hint       = state.get("target_room_hint") or ""

        layout = _edits.load(layout_str)
        out = {
            **state,
            "original_scores_json": original_scores,
            "pending_comparison":   True,
            "layout_diff":          {},
        }
        if layout is None:
            print("[modify_glazing] no layout — skipping")
            return out

        room = _edits.find_target_room(layout, raw_prompt, original_scores, room_hint)
        gtype, wants_more = _edits.resolve_glazing(raw_prompt)

        diff = _edits.apply_modify_glazing(layout, room, gtype, wants_more)
        if room:
            print(f"[modify_glazing] {room.get('name')}: {diff.get('new_value', '')}")

        out["layout_json_string"] = _edits.dump(layout)
        out["layout_diff"]        = diff
        out["layout_updated"]     = True
        return out

    return modify_glazing_node
