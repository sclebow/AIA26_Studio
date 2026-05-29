"""
COMPARE_VERSIONS placeholder — computes before/after score delta after a layout modification.
TODO: Wire to MCP compare_layout_versions tool.
"""

from __future__ import annotations
import json


def build_compare_versions_node():
    """Return the compare_versions node function."""

    def compare_versions_node(state: dict) -> dict:
        new_scores_json: str = state.get("last_scores_json", "")
        original_scores_json: str = state.get("original_scores_json", "")

        print("[compare_versions] PLACEHOLDER — computing score delta")

        delta_summary = "(no comparison available)"

        # Mock: compute delta from raw JSONs
        try:
            original = json.loads(original_scores_json) if original_scores_json else {}
            new = json.loads(new_scores_json) if new_scores_json else {}

            orig_rooms = {r["roomName"]: r for r in original.get("rooms", [])}
            new_rooms = {r["roomName"]: r for r in new.get("rooms", [])}

            lines = ["SCORE DELTA (after modification):"]
            for room_name, new_room in new_rooms.items():
                orig_room = orig_rooms.get(room_name)
                if not orig_room:
                    continue
                orig_sc = orig_room.get("comfortScores", {})
                new_sc = new_room.get("comfortScores", {})
                deltas = []
                for sense in ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]:
                    orig_val = orig_sc.get(sense, 0.0)
                    new_val = new_sc.get(sense, 0.0)
                    diff = new_val - orig_val
                    if abs(diff) > 0.01:  # only show meaningful changes
                        sign = "+" if diff > 0 else ""
                        deltas.append(f"{sense}: {sign}{diff:.2f}")
                if deltas:
                    lines.append(f"  {room_name}: {', '.join(deltas)}")
                else:
                    lines.append(f"  {room_name}: no change")

            delta_summary = "\n".join(lines)
            print(f"[compare_versions] {delta_summary[:120]}")
        except Exception as exc:
            print(f"[compare_versions] Delta error ({exc})")
            delta_summary = "(delta computation failed — proceeding with new scores)"

        # Reset pending_comparison flag now that comparison is done
        return {
            **state,
            "compare_versions_summary": delta_summary,
            "pending_comparison": False,
        }

    return compare_versions_node
