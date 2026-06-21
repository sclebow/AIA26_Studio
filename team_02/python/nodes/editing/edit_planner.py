"""
EDIT_PLANNER node — decompose ONE editorial prompt into a LIST of concrete edit ops.

This is what makes multi-edit work: "add 2 plants and change the glazing in the bedroom"
becomes two ops, applied together by apply_edits with a single re-score. The planner only
SEGMENTS the request (split conjunctions, attach rooms/counts) — it never touches the layout
and never invents canonical values. apply_edits canonicalises every value against the real
layout via the pure _edits helpers, so the LLM can't introduce an invalid material or a
nonexistent room.

Output (a top-level object, never a bare array — matches the action_classifier pattern):
  { "ops": [ {op, room, ...params}, ... ] }
"""

from __future__ import annotations
import json

from _runtime.llm import call_llm_simple
from nodes.editing import _edits

ALLOWED_OPS = {"add_furniture", "modify_glazing", "change_material"}


_SYSTEM_PROMPT = """\
You are the edit planner for an architectural comfort copilot. The user wants to modify an
apartment layout. Decompose their message into a list of concrete edit operations.

Rooms in the current layout: {rooms}

Return ONLY a JSON object of this exact shape (no prose, no markdown fences):
{{
  "ops": [
    {{ "op": "add_furniture",  "room": "<room name or null>", "furniture_type": "plant|rug|sofa|table|desk|shelf|cabinet", "count": 1, "material": "<material or null>" }},
    {{ "op": "modify_glazing", "room": "<room name or null>", "glazing_type": "single|double|triple|null", "wants_more_light": true }},
    {{ "op": "change_material","room": "<room name or null>", "surface": "floor|wall|furniture", "material": "<material or null>" }}
  ]
}}

Rules:
  - One op per distinct change. "add 2 plants and change the glazing" -> TWO ops.
  - Split conjunctions ("and", "then", "also", "plus", commas) into separate ops.
  - "op" MUST be exactly one of: add_furniture, modify_glazing, change_material.
  - "add / put / place [plant/rug/sofa/...]" -> add_furniture. Put how many in "count" (default 1).
  - "change / make [floor/wall/material] ..." -> change_material.
  - "bigger / more windows", "glazing", "skylight", "more light", "brighter" -> modify_glazing.
  - Use the EXACT room name from the list above when the user names a room; otherwise null.
  - If one room is given for several changes, repeat that room name on each op.
  - Return an empty ops array if there is no concrete edit to make.

Return ONLY the JSON object.
"""


def _validate_ops(raw_ops) -> list:
    """Keep only well-formed ops; coerce types. Never trusts the LLM for canonical values."""
    out: list = []
    if not isinstance(raw_ops, list):
        return out
    for o in raw_ops:
        if not isinstance(o, dict):
            continue
        op = str(o.get("op", "")).strip().lower()
        if op not in ALLOWED_OPS:
            continue
        clean = {"op": op, "room": o.get("room")}
        if op == "add_furniture":
            clean["furniture_type"] = o.get("furniture_type")
            try:
                clean["count"] = int(o.get("count", 1) or 1)
            except (TypeError, ValueError):
                clean["count"] = 1
            clean["material"] = o.get("material")
        elif op == "modify_glazing":
            clean["glazing_type"] = o.get("glazing_type")
            clean["wants_more_light"] = bool(o.get("wants_more_light", True))
        else:  # change_material
            clean["surface"] = o.get("surface")
            clean["material"] = o.get("material")
        out.append(clean)
    return out


# Keyword fallback (LLM-free). Detects EVERY category present so a plain "add a plant
# and change the floor" still produces two ops without the model. Room/count are left
# null/default for apply_edits to resolve from the raw prompt.
_FURNITURE_KW = ("plant", "rug", "sofa", "couch", "armchair", "cushion", "furniture",
                 "shelf", "bookshelf", "desk", "table", "cabinet", "bed", "chair")
_GLAZING_KW   = ("window", "glazing", "skylight", "daylight", "more light", "brighter",
                 "bigger window", "triple", "double", "single glaz")
_MATERIAL_KW  = ("floor", "flooring", "wall", "ceiling", "material", "carpet", "wood",
                 "wooden", "concrete", "tile", "fabric", "cork", "stone")


def _heuristic_ops(prompt: str) -> list:
    p = (prompt or "").lower()
    if not p.strip():
        return []
    ops = []
    if any(k in p for k in _FURNITURE_KW):
        ops.append({"op": "add_furniture", "room": None, "furniture_type": None,
                    "count": 1, "material": None})
    if any(k in p for k in _GLAZING_KW):
        ops.append({"op": "modify_glazing", "room": None, "glazing_type": None,
                    "wants_more_light": True})
    if any(k in p for k in _MATERIAL_KW):
        ops.append({"op": "change_material", "room": None, "surface": None, "material": None})
    return ops


def build_edit_planner_node(llm):
    """Return the edit_planner node, capturing the (SMART-tier) LLM instance."""

    def edit_planner_node(state: dict) -> dict:
        raw_prompt = state.get("raw_prompt", "")
        layout = _edits.load(state.get("layout_json_string", ""))
        room_names = [r.get("name") for r in (layout.get("rooms", []) if layout else []) if r.get("name")]

        ops: list = []
        try:
            raw = call_llm_simple(llm, _SYSTEM_PROMPT.format(rooms=", ".join(room_names) or "(none loaded)"), raw_prompt)
            clean = raw.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.splitlines()[1:-1]).strip()
            parsed = json.loads(clean)
            ops = _validate_ops(parsed.get("ops") if isinstance(parsed, dict) else None)
        except Exception as exc:
            print(f"[edit_planner] LLM error ({exc}) — using keyword fallback")

        if not ops:
            ops = _heuristic_ops(raw_prompt)
            if ops:
                print(f"[edit_planner] keyword fallback produced {len(ops)} op(s)")

        print(f"[edit_planner] {len(ops)} op(s): {[o.get('op') for o in ops]}")
        return {**state, "edit_ops": ops}

    return edit_planner_node
