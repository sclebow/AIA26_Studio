"""
ADD_FURNITURE — appends a furniture element to the target room.
Returns structured layout_diff for frontend animation.
"""

from __future__ import annotations
from nodes.editing import _edits


def build_add_furniture_node():
    def add_furniture_node(state: dict) -> dict:
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
            print("[add_furniture] no layout — skipping")
            return out

        room  = _edits.find_target_room(layout, raw_prompt, original_scores, room_hint)
        ftype = _edits.detect_furniture_type(raw_prompt)
        mat   = _edits.furniture_material_for(ftype)

        diff = _edits.apply_add_furniture(layout, room, ftype, mat)
        if room:
            print(f"[add_furniture] {ftype} ({mat}) → {room.get('name')}")

        out["layout_json_string"] = _edits.dump(layout)
        out["layout_diff"]        = diff
        # Only report an update when a room actually received furniture, so the
        # frontend doesn't trigger a (no-op) re-render for an unmatched target.
        out["layout_updated"]     = room is not None
        if room is None:
            print("[add_furniture] no target room matched — nothing added")
        return out

    return add_furniture_node
