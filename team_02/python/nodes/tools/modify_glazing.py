"""
MODIFY_GLAZING — real edit. Raises the target room's glazing ratio and/or upgrades
its windows' glazing type, then flags a re-score (drives visual + thermal deltas).
"""

from __future__ import annotations
from nodes.tools import _edits


def build_modify_glazing_node():
    def modify_glazing_node(state: dict) -> dict:
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
            print("[modify_glazing] no layout — skipping edit")
            return out

        room = _edits.find_target_room(layout, raw_prompt, original_scores)
        p = raw_prompt.lower()
        gtype = ("triple" if "triple" in p else "single" if "single" in p
                 else "double" if "double" in p else None)

        if room:
            attrs = room.setdefault("attributes", {})
            cur = float(attrs.get("glazingRatio", 0.10))
            wants_more_light = any(k in p for k in
                ["more light", "bigger", "larger", "brighter", "window", "light", "glazing", "skylight"])
            if wants_more_light or gtype is None:
                attrs["glazingRatio"] = round(max(cur, 0.25), 2)
            applied_gt = gtype or "triple"  # default: upgrade for thermal gain
            rid = room.get("id")
            for win in layout.get("windows", []):
                if win.get("attributes", {}).get("roomId") == rid:
                    win.setdefault("attributes", {})["glazingType"] = applied_gt
            print("[modify_glazing] {} -> glazingRatio={}, windows={}".format(
                room.get("name"), attrs.get("glazingRatio"), applied_gt))

        out["layout_json_string"] = _edits.dump(layout)
        return out

    return modify_glazing_node
