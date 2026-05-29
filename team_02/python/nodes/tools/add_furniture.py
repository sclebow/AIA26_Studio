"""
ADD_FURNITURE — real edit. Appends a furniture element (default: a plant) to the
target room near its centroid, then flags a re-score. Plants lift olfactory +
visual; soft furniture lifts tactile.
"""

from __future__ import annotations
from nodes.tools import _edits


def build_add_furniture_node():
    def add_furniture_node(state: dict) -> dict:
        raw_prompt = state.get("raw_prompt", "")
        layout_str = state.get("layout_json_string", "")
        original_scores = state.get("last_scores_json", "")

        layout = _edits.load(layout_str)
        out = {
            **state,
            "original_scores_json": original_scores,
            "pending_comparison": True,
            "comfort_depth": "analyze",
        }
        if layout is None:
            print("[add_furniture] no layout — skipping edit")
            return out

        room = _edits.find_target_room(layout, raw_prompt, original_scores)
        ftype = _edits.detect_furniture_type(raw_prompt)
        material = ("natural" if ftype == "plant"
                    else "fabric" if ftype in _edits.SOFT_FURNITURE else "wood")

        if room:
            cx, cy = _edits.centroid(room.get("geometry", []))
            h = 0.4
            geo = [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h],
                   [cx - h, cy + h], [cx - h, cy - h]]
            new_id = _edits.next_id(layout, "furniture", "furn")
            layout.setdefault("furniture", []).append({
                "id": new_id,
                "name": "Added {}".format(ftype),
                "geometry": geo,
                "attributes": {"roomId": room.get("id"), "type": ftype, "material": material},
            })
            print("[add_furniture] added {} ({}) to {}".format(ftype, material, room.get("name")))

        out["layout_json_string"] = _edits.dump(layout)
        return out

    return add_furniture_node
