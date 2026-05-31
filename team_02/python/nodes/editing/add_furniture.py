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
        mat   = ("natural" if ftype == "plant" else
                 "fabric"  if ftype in _edits.SOFT_FURNITURE else "wood")

        diff = {}
        if room:
            cx, cy = _edits.centroid(room.get("geometry", []))
            h = 0.4
            geo = [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h],
                   [cx - h, cy + h], [cx - h, cy - h]]
            new_id = _edits.next_id(layout, "furniture", "furn")
            layout.setdefault("furniture", []).append({
                "id": new_id,
                "name": f"Added {ftype}",
                "geometry": geo,
                "attributes": {"roomId": room.get("id"), "type": ftype, "material": mat},
            })
            sense = "olfactory+visual" if ftype == "plant" else "tactile"
            diff = _edits.make_layout_diff(
                room, "furniture", "none", f"added {ftype} ({mat})", sense
            )
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
