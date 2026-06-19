"""
APPLY_EDITS node — the single deterministic chokepoint where the working layout is mutated.

Consumes the validated `edit_ops` list from edit_planner and applies each op to the canonical
layout via the pure mutators in _edits, accumulating ONE diff per op into `layout_diffs`.

Every op is gated by an in-memory SOUNDNESS check: the architectural rules of
`check_layout_geometry` (the same ones the floor-plan-review skill uses) run on the working
layout after each op. If an op introduces a NEW defect that wasn't in the pre-edit baseline,
that op is REVERTED (per-op atomic) and recorded in `rejected_edits` with a human reason — so a
bad edit can never corrupt the layout, and the copilot can explain what it couldn't do. The
pre-edit scores are snapshotted ONCE so compare_versions reports the cumulative before/after
delta, and downstream re-scores exactly once.

Forward-compat (Task 3 — checkpoints): this node is the ONLY place the working layout is
mutated and the baseline is captured. A future checkpoint layer wraps exactly this node and
sources `original_scores_json` from the last committed checkpoint instead of the turn cache.
"""

from __future__ import annotations
import json

from nodes.editing import _edits
import check_layout_geometry as geo
from comfort import suggestion_lifecycle as sugg_life

COUNT_CAP = 5  # guard against "add 100 plants"


def _apply_one(kind, op, layout, room, raw_prompt):
    """Apply ONE op to `layout` in place. Returns (diff_or_None, note_or_None).

    A `note` is a surfaced assumption ("capped at 5", "defaulted glazing to triple",
    "used 'wood' — unknown material 'oakwood'") so the response can stay honest.
    """
    if kind == "add_furniture":
        ftype = op.get("furniture_type") or _edits.detect_furniture_type(raw_prompt)
        mat   = _edits.validate_material(op.get("material")) or _edits.furniture_material_for(ftype)
        try:
            count = int(op.get("count", 1) or 1)
        except (TypeError, ValueError):
            count = 1
        capped = count > COUNT_CAP
        count = max(1, min(count, COUNT_CAP))
        diff, placed = None, 0
        for _ in range(count):
            d = _edits.apply_add_furniture(layout, room, ftype, mat)
            if not d:
                break
            diff, placed = d, placed + 1
        if diff and placed > 1:
            diff = {**diff, "new_value": f"added {placed}x {ftype} ({mat})"}
        note = f"added {placed}, capped at {COUNT_CAP}" if capped else None
        return (diff or None), note

    if kind == "modify_glazing":
        gtype = op.get("glazing_type")
        wants = bool(op.get("wants_more_light", True))
        if gtype is None and not wants:
            gtype, wants = _edits.resolve_glazing(raw_prompt)
        note = "defaulted glazing to triple" if gtype is None else None
        return (_edits.apply_modify_glazing(layout, room, gtype, wants) or None), note

    if kind == "change_material":
        surface = op.get("surface") or _edits.detect_surface_target(raw_prompt)
        raw_mat = op.get("material")
        material = _edits.validate_material(raw_mat) or _edits.detect_material(raw_prompt) or "wood"
        note = (f"used '{material}' (unknown material '{raw_mat}')"
                if raw_mat and _edits.validate_material(raw_mat) is None else None)
        return (_edits.apply_change_material(layout, room, surface, material) or None), note

    if kind == "modify_ventilation":
        vt = op.get("ventilation_type") or _edits.detect_ventilation(raw_prompt) or "natural"
        return (_edits.apply_modify_ventilation(layout, room, vt) or None), None

    if kind == "add_window":
        return (_edits.apply_add_window(layout, room, op.get("glazing_type")) or None), None

    if kind == "move_window":
        return (_edits.apply_move_window(layout, room, op.get("target") or raw_prompt) or None), None

    if kind == "remove_furniture":
        item = op.get("item") or _edits.detect_furniture_type(raw_prompt)
        return (_edits.apply_remove_furniture(layout, room, item) or None), None

    if kind == "remove_window":
        return (_edits.apply_remove_window(layout, room, op.get("target") or "") or None), None

    if kind == "remove_door":
        return (_edits.apply_remove_door(layout, room, op.get("target") or "") or None), None

    return None, None


def _op_phrase(op):
    """Short human label for an op, for the 'couldn't do X' message."""
    kind = (op.get("op") or "edit").replace("_", " ")
    room = op.get("room")
    return f"{kind} in {room}" if room else kind


def build_apply_edits_node():
    """Return the apply_edits node (no LLM — pure mutation + geometry validation)."""

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
            "rejected_edits":       [],
            "edit_notes":           [],
            "pending_comparison":   False,
            "layout_updated":       False,
        }

        layout = _edits.load(layout_str)
        if layout is None:
            out["final_response"] = "I need a layout loaded before I can make a change."
            print("[apply_edits] no layout — skipping")
            return out

        if not edit_ops:
            msg = (
                "I couldn't find a concrete change to make. Tell me what to change and where — "
                'for example: "add a plant in the living room" or "change the bedroom floor to wood".'
            )
            if state.get("planner_note") == "planner_llm_error":
                msg += " (I had trouble parsing that — could you rephrase?)"
            out["final_response"] = msg
            print("[apply_edits] no ops — nothing applied")
            return out

        try:
            baseline = set(geo.audit_layout(layout))
        except Exception as exc:  # noqa: BLE001 — never let the validator break the edit
            baseline = set()
            print(f"[apply_edits] baseline audit failed ({exc}) — proceeding without revert gate")

        diffs: list = []
        rejected: list = []
        notes: list = []

        for op in edit_ops:
            kind = op.get("op")
            hint = op.get("room") or ""
            # The LLM gives a room STRING; _edits.find_target_room matches it against real
            # room names/types, falling back to worst-scoring then first. Never trust an id.
            room = _edits.find_target_room(layout, hint or raw_prompt, original_scores, hint)
            if room is None:
                rejected.append({"op": kind, "reason": f"no room matched '{hint or 'this layout'}'",
                                 "phrase": _op_phrase(op)})
                continue

            snapshot = json.loads(_edits.dump(layout))   # cheap deep copy for per-op revert
            try:
                diff, note = _apply_one(kind, op, layout, room, raw_prompt)
                # Only audit when something actually changed (audit is the per-op gate).
                new_defects = (set(geo.audit_layout(layout)) - baseline) if diff else set()
            except Exception as exc:  # a degenerate edit must never crash the whole turn
                layout.clear()
                layout.update(snapshot)
                rejected.append({"op": kind, "reason": f"errored ({exc})", "phrase": _op_phrase(op)})
                print(f"[apply_edits] ERROR in {kind}: {exc}")
                continue

            if note:
                notes.append(note)
            if not diff:
                rejected.append({"op": kind, "reason": "couldn't apply it here", "phrase": _op_phrase(op)})
                continue
            if new_defects:
                layout.clear()
                layout.update(snapshot)               # revert THIS op only
                rejected.append({"op": kind, "reason": "; ".join(sorted(new_defects)),
                                 "phrase": _op_phrase(op)})
                print(f"[apply_edits] REVERTED {kind}: {sorted(new_defects)}")
                continue

            diffs.append(diff)

        out["layout_json_string"] = _edits.dump(layout)
        out["layout_diffs"]       = diffs
        out["layout_diff"]        = diffs[-1] if diffs else {}   # singular kept for back-compat
        out["rejected_edits"]     = rejected
        out["edit_notes"]         = notes
        out["layout_updated"]     = bool(diffs)
        out["pending_comparison"] = bool(diffs)

        # Suggestion lifecycle: cross off any standing suggestion this edit fulfilled
        # (matched room + sense). Accumulates across the session; analyze won't clear it.
        applied_acc = list(state.get("applied_suggestions") or [])
        prior_sugg = state.get("last_suggestions_json") or state.get("suggestions_sticky") or ""
        if diffs and prior_sugg:
            for entry in sugg_life.newly_applied(diffs, prior_sugg):
                if entry not in applied_acc:
                    applied_acc.append(entry)
        out["applied_suggestions"] = applied_acc

        if not diffs:
            # Nothing applied — explain why here (the re-score/respond path is skipped).
            if rejected:
                couldnt = "; ".join(r["phrase"] for r in rejected)
                reasons = "; ".join(sorted({r["reason"] for r in rejected}))
                out["final_response"] = (
                    f"I couldn't make that change: {couldnt}. ({reasons}.) "
                    "Which room should I use, or want me to try a different spot?"
                )
            else:
                out["final_response"] = (
                    "I understood the request but couldn't match it to a room in this layout. "
                    "Which room should I change?"
                )

        print(f"[apply_edits] applied {len(diffs)} change(s), rejected {len(rejected)}, "
              f"across {len(edit_ops)} op(s)" + (f"; notes={notes}" if notes else ""))
        return out

    return apply_edits_node
