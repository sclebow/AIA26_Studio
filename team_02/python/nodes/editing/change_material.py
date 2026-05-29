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

        diff = {}

        if surface == "floor" and room:
            # Set floorMaterial on the room's attributes
            attrs    = room.setdefault("attributes", {})
            old_val  = attrs.get("floorMaterial", "unset")
            attrs["floorMaterial"] = material
            diff = _edits.make_layout_diff(room, "floorMaterial", old_val, material, "tactile")
            print(f"[change_material] {room.get('name')} floorMaterial: {old_val} → {material}")

        elif surface == "wall":
            # Set material on all structure elements (global wall material)
            old_vals = [w.get("attributes", {}).get("material", "plaster")
                        for w in layout.get("structure", [])]
            old_val  = old_vals[0] if old_vals else "plaster"
            for w in layout.get("structure", []):
                w.setdefault("attributes", {})["material"] = material
            diff = _edits.make_layout_diff(room, "wallMaterial", old_val, material, "tactile")
            print(f"[change_material] wall material: {old_val} → {material}")

        else:
            # Furniture material in target room
            if room:
                rid     = room.get("id")
                changed = False
                old_val = material  # default if nothing found
                for f in layout.get("furniture", []):
                    if f.get("attributes", {}).get("roomId") == rid:
                        old_val = f.get("attributes", {}).get("material", "unknown")
                        f.setdefault("attributes", {})["material"] = material
                        changed = True
                diff = _edits.make_layout_diff(
                    room, "furnitureMaterial", old_val if changed else "none", material, "tactile"
                )
                print(f"[change_material] furniture in {room.get('name')}: → {material}")

        out["layout_json_string"] = _edits.dump(layout)
        out["layout_diff"]        = diff
        out["layout_updated"]     = True
        return out

    return change_material_node
