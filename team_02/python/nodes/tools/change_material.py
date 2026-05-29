"""
CHANGE_MATERIAL — real edit. Sets the material of furniture in the target room
(or the walls, if the prompt mentions walls/floor), then flags a re-score so
analyze → compare_versions shows the tactile delta.
"""

from __future__ import annotations
from nodes.tools import _edits


def build_change_material_node():
    def change_material_node(state: dict) -> dict:
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
            print("[change_material] no layout — skipping edit")
            return out

        room = _edits.find_target_room(layout, raw_prompt, original_scores)
        material = _edits.detect_material(raw_prompt) or "wood"
        p = raw_prompt.lower()
        applied = False

        if room and "wall" not in p and "floor" not in p:
            rid = room.get("id")
            for f in layout.get("furniture", []):
                if f.get("attributes", {}).get("roomId") == rid:
                    f.setdefault("attributes", {})["material"] = material
                    applied = True
        if not applied:
            for w in layout.get("structure", []):
                w.setdefault("attributes", {})["material"] = material
                applied = True

        where = ("furniture in " + room.get("name")) if (room and applied and "wall" not in p) else "walls"
        print("[change_material] set material={} on {} (applied={})".format(material, where, applied))
        out["layout_json_string"] = _edits.dump(layout)
        return out

    return change_material_node
