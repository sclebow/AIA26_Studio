"""
APPLY_EDITS node — the single deterministic chokepoint where the working layout is mutated.

Replaces the three near-identical edit nodes (change_material / modify_glazing / add_furniture).
Consumes the validated `edit_ops` list from edit_planner, applies each op to the canonical
layout via the pure mutators in _edits, and accumulates ONE diff per op into `layout_diffs`.
The pre-edit scores are snapshotted ONCE (not per op) so compare_versions reports the
cumulative before/after delta, and downstream re-scores exactly once.

Forward-compat (Task 3 — checkpoints): this node is the ONLY place the working layout is
mutated and the baseline is captured. A future checkpoint layer wraps exactly this node and
sources `original_scores_json` from the last committed checkpoint instead of the turn cache —
kept here as a single assignment so that swap is one line.
"""

from __future__ import annotations
from nodes.editing import _edits

COUNT_CAP = 5  # guard against "add 100 plants"


def build_apply_edits_node():
    """Return the apply_edits node (no LLM — pure mutation over _edits helpers)."""

    def apply_edits_node(state: dict) -> dict:
        raw_prompt      = state.get("raw_prompt", "")
        layout_str      = state.get("layout_json_string", "")
        original_scores = state.get("last_scores_json", "")
        edit_ops        = state.get("edit_ops", []) or []

        # Baseline snapshot — ONCE, before any mutation (see module docstring).
        out = {
            **state,
            "original_scores_json": original_scores,
            "layout_diffs":         [],
            "layout_diff":          {},
            "pending_comparison":   False,
            "layout_updated":       False,
        }

        layout = _edits.load(layout_str)
        if layout is None:
            out["final_response"] = "I need a layout loaded before I can make a change."
            print("[apply_edits] no layout — skipping")
            return out

        if not edit_ops:
            out["final_response"] = (
                "I couldn't find a concrete change to make. Tell me what to change and where — "
                'for example: "add a plant in the living room" or "change the bedroom floor to wood".'
            )
            print("[apply_edits] no ops — nothing applied")
            return out

        diffs: list = []
        capped = False

        for op in edit_ops:
            kind = op.get("op")
            hint = op.get("room") or ""
            # The LLM gives a room STRING; _edits.find_target_room matches it against real
            # room names/types, falling back to worst-scoring then first. Never trust an id.
            room = _edits.find_target_room(layout, hint or raw_prompt, original_scores, hint)
            if room is None:
                continue

            if kind == "add_furniture":
                ftype = op.get("furniture_type") or _edits.detect_furniture_type(raw_prompt)
                mat   = op.get("material") or _edits.furniture_material_for(ftype)
                count = op.get("count", 1)
                try:
                    count = int(count)
                except (TypeError, ValueError):
                    count = 1
                if count > COUNT_CAP:
                    count, capped = COUNT_CAP, True
                count = max(1, count)
                last = None
                for _ in range(count):
                    last = _edits.apply_add_furniture(layout, room, ftype, mat)
                if last:
                    # One consolidated diff per op (so "2 plants" is one timeline change).
                    if count > 1:
                        last = {**last, "new_value": f"added {count}x {ftype} ({mat})"}
                    diffs.append(last)

            elif kind == "modify_glazing":
                gtype = op.get("glazing_type")
                wants = bool(op.get("wants_more_light", True))
                if gtype is None and not wants:  # nothing specified — read intent from prompt
                    gtype, wants = _edits.resolve_glazing(raw_prompt)
                d = _edits.apply_modify_glazing(layout, room, gtype, wants)
                if d:
                    diffs.append(d)

            elif kind == "change_material":
                surface  = op.get("surface") or _edits.detect_surface_target(raw_prompt)
                material = op.get("material") or _edits.detect_material(raw_prompt) or "wood"
                d = _edits.apply_change_material(layout, room, surface, material)
                if d:
                    diffs.append(d)

        out["layout_json_string"] = _edits.dump(layout)
        out["layout_diffs"]       = diffs
        out["layout_diff"]        = diffs[-1] if diffs else {}   # singular kept for back-compat
        out["layout_updated"]     = bool(diffs)
        out["pending_comparison"] = bool(diffs)

        if not diffs:
            out["final_response"] = (
                "I understood the request but couldn't match it to a room in this layout. "
                "Which room should I change?"
            )
        print(f"[apply_edits] applied {len(diffs)} change(s) across {len(edit_ops)} op(s)"
              + (f" (count capped at {COUNT_CAP})" if capped else ""))
        return out

    return apply_edits_node
