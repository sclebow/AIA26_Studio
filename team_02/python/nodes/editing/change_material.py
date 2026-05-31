"""
CHANGE_MATERIAL — edits room material (floor, wall, or furniture).
Fixed: correctly targets floor vs wall vs furniture.
Returns structured layout_diff for frontend animation.
"""

from __future__ import annotations
from nodes.editing import _edits


def build_change_material_node():
    def change_material_node(state: dict) -> dict:
        raw_prompt      = state.get("raw_prompt", "")
        layout_str      = state.get("layout_json_string", "")
        original_scores = state.get("last_scores_json", "")
        room_hint       = state.get("target_room_hint") or ""
        material_hint   = state.get("material_hint") or ""

        layout = _edits.load(layout_str)
        out = {
            **state,
            "original_scores_json": original_scores,
            "pending_comparison":   True,
            "layout_diff":          {},
        }
        if layout is None:
            print("[change_material] no layout — skipping edit")
            return out

        room     = _edits.find_target_room(layout, raw_prompt, original_scores, room_hint)
        material = _edits.detect_material(raw_prompt, material_hint) or "wood"
        surface  = _edits.detect_surface_target(raw_prompt)

        diff = _edits.apply_change_material(layout, room, surface, material)
        print(f"[change_material] {surface} → {material} in {room.get('name') if room else '?'}")

        out["layout_json_string"] = _edits.dump(layout)
        out["layout_diff"]        = diff
        out["layout_updated"]     = True
        return out

    return change_material_node
