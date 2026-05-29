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
        p    = raw_prompt.lower()
        gtype = ("triple" if "triple" in p else
                 "single" if "single" in p else
                 "double" if "double" in p else None)

        diff = {}
        if room:
            attrs   = room.setdefault("attributes", {})
            old_gr  = float(attrs.get("glazingRatio", 0.10))
            wants_more = any(k in p for k in
                ["more light", "bigger", "larger", "brighter", "window", "light", "glazing", "skylight"])
            new_gr = round(max(old_gr, 0.25), 2) if (wants_more or gtype is None) else old_gr
            attrs["glazingRatio"] = new_gr

            applied_gt = gtype or "triple"
            rid = room.get("id")
            old_gt = "double"
            for win in layout.get("windows", []):
                if win.get("attributes", {}).get("roomId") == rid:
                    old_gt = win.get("attributes", {}).get("glazingType", "double")
                    win.setdefault("attributes", {})["glazingType"] = applied_gt

            diff = _edits.make_layout_diff(
                room, "glazingRatio",
                f"ratio={old_gr:.2f}, type={old_gt}",
                f"ratio={new_gr:.2f}, type={applied_gt}",
                "visual+thermal"
            )
            print(f"[modify_glazing] {room.get('name')}: ratio {old_gr:.2f}→{new_gr:.2f}, type→{applied_gt}")

        out["layout_json_string"] = _edits.dump(layout)
        out["layout_diff"]        = diff
        out["layout_updated"]     = True
        return out

    return modify_glazing_node
