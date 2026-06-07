"""
PREVIEW node — score a HYPOTHETICAL edit WITHOUT committing it ("what if…").

Clones the layout, applies the requested mutation to the clone, scores it, diffs
the per-sense scores against the current cached scores, and stashes everything in
preview_* state keys. It NEVER touches layout_json_string, last_scores_json, or
layout_updated — so the canvas and the score cache stay exactly where they are until
the user asks for the real edit. This is the agent's forecast and the user's sandbox.
"""

from __future__ import annotations
import json

from nodes.editing import _edits
from nodes._shared.utils import unwrap_mcp_result, persona_display_label

SENSES = ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]


def _decompose_ops(prompt: str) -> list:
    """Which edits does this 'what if' refer to? Detects EVERY category present so
    "what if I add a plant AND change the floor" previews both. Keyword-only (no LLM)
    — the preview is hypothetical, so a wrong guess is cheap (nothing is committed)."""
    p = (prompt or "").lower()
    ops = []
    if any(k in p for k in ("plant", "rug", "sofa", "couch", "armchair", "cushion",
                            "furniture", "shelf", "bookshelf", "desk", "table", "cabinet")):
        ops.append("add_furniture")
    if any(k in p for k in ("window", "glazing", "skylight", "daylight", "more light")):
        ops.append("modify_glazing")
    if any(k in p for k in ("floor", "wall", "material", "carpet", "wood", "concrete",
                            "tile", "fabric", "cork", "stone")):
        ops.append("change_material")
    return ops or ["change_material"]  # default fallback


def _layout_score(scores_json: str):
    """Predicted layout headline — same non-additive blend as the frontend
    (0.6*mean + 0.4*worst room). Returns None if unparseable."""
    try:
        rooms = json.loads(scores_json).get("rooms", [])
        vals = [r.get("overallScore", 0.0) for r in rooms]
        if not vals:
            return None
        return round(0.6 * (sum(vals) / len(vals)) + 0.4 * min(vals), 2)
    except Exception:
        return None


def _delta_summary(original_scores_json: str, new_scores_json: str) -> str:
    """Per-sense before/after deltas per room (same shape as compare_versions),
    labelled as a PREDICTION since nothing is applied."""
    try:
        original = json.loads(original_scores_json) if original_scores_json else {}
        new = json.loads(new_scores_json) if new_scores_json else {}
        orig_rooms = {r["roomName"]: r for r in original.get("rooms", [])}
        new_rooms = {r["roomName"]: r for r in new.get("rooms", [])}

        lines = ["PREDICTED SCORE DELTA (not yet applied):"]
        for room_name, new_room in new_rooms.items():
            orig_room = orig_rooms.get(room_name)
            if not orig_room:
                continue
            orig_sc = orig_room.get("comfortScores", {})
            new_sc = new_room.get("comfortScores", {})
            deltas = []
            for sense in SENSES:
                diff = new_sc.get(sense, 0.0) - orig_sc.get(sense, 0.0)
                if abs(diff) > 0.01:
                    deltas.append(f"{sense}: {'+' if diff > 0 else ''}{diff:.2f}")
            if deltas:
                lines.append(f"  {room_name}: {', '.join(deltas)}")
        return "\n".join(lines) if len(lines) > 1 else "PREDICTED: no meaningful change."
    except Exception as exc:
        return f"(preview delta failed: {exc})"


def build_preview_node(mcp_client):
    """Return the preview node, capturing the MCP client (for scoring the clone)."""

    def preview_node(state: dict) -> dict:
        raw_prompt      = state.get("raw_prompt", "")
        layout_str      = state.get("layout_json_string", "")
        current_scores  = state.get("last_scores_json", "")
        room_hint       = state.get("target_room_hint") or ""
        material_hint   = state.get("material_hint") or ""
        persona_profile = state.get("persona_profile") or {}

        out = {**state, "preview_scores_json": "", "preview_diff": {},
               "preview_diffs": [], "preview_summary": ""}

        layout = _edits.load(layout_str)
        if layout is None:
            out["final_response"] = "I need a layout loaded before I can simulate a change."
            print("[preview] no layout — cannot simulate")
            return out

        # Clone so the canonical layout is NEVER mutated. Apply ALL hypothetical ops
        # to the one clone, then score it ONCE (matches the committed multi-edit path).
        clone = json.loads(_edits.dump(layout))
        room  = _edits.find_target_room(clone, raw_prompt, current_scores, room_hint)
        diffs = []
        for edit in _decompose_ops(raw_prompt):
            if room is None:
                break
            if edit == "add_furniture":
                ftype = _edits.detect_furniture_type(raw_prompt)
                mat   = _edits.furniture_material_for(ftype)
                d = _edits.apply_add_furniture(clone, room, ftype, mat)
            elif edit == "modify_glazing":
                gtype, wants_more = _edits.resolve_glazing(raw_prompt)
                d = _edits.apply_modify_glazing(clone, room, gtype, wants_more)
            else:
                material = _edits.detect_material(raw_prompt, material_hint) or "wood"
                surface  = _edits.detect_surface_target(raw_prompt)
                d = _edits.apply_change_material(clone, room, surface, material)
            if d:
                diffs.append(d)
        diff = diffs[-1] if diffs else {}

        # Score the hypothetical clone — same args as the analyze node.
        persona_label    = persona_display_label(persona_profile)
        weights_override = persona_profile.get("comfort_weights")
        pers = persona_profile.get("personality", 0)
        if isinstance(pers, str):
            pers = {"introvert": -1.0, "extrovert": 1.0}.get(pers.strip().lower(), 0.0)
        try:
            personality = float(pers or 0)
        except (TypeError, ValueError):
            personality = 0.0

        args = {
            "layout_json": _edits.dump(clone),
            "persona":     persona_label,
            "room_ids":    "all",
            "personality": personality,
        }
        if weights_override:
            args["weights_override"] = json.dumps(weights_override)

        raw = mcp_client.call_tool("compute_comfort_scores", args)
        preview_scores = unwrap_mcp_result(raw)

        summary = _delta_summary(current_scores, preview_scores)
        now_score = _layout_score(current_scores)
        new_score = _layout_score(preview_scores)
        headline = ""
        if now_score is not None and new_score is not None:
            arrow = "→" if new_score != now_score else "≈"
            headline = f"\n\nPredicted layout score: {now_score:.2f} {arrow} {new_score:.2f}"

        room_name = room.get("name") if room else "the layout"
        if len(diffs) > 1:
            change_desc = f"made {len(diffs)} changes in {room_name}"
        elif diffs:
            change_desc = f"{diff.get('new_value', 'made that change')} in {room_name}"
        else:
            change_desc = f"made that change in {room_name}"

        out["preview_scores_json"] = preview_scores
        out["preview_diff"]        = diff
        out["preview_diffs"]       = diffs
        out["preview_summary"]     = summary
        out["final_response"]      = (
            f"Here's what would happen if I {change_desc} — nothing is applied yet:"
            f"{headline}\n\n{summary}"
        )
        print(f"[preview] simulated {len(diffs)} op(s) on {room_name} (no commit)")
        return out

    return preview_node
