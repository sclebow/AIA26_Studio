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
import re

from _runtime.llm import call_llm_simple
from nodes.editing import _edits


def _has_word(p: str, words) -> bool:
    """Whole-word (optional plural) match — so 'bed' doesn't fire on 'bedroom'."""
    return any(re.search(r"\b" + re.escape(w) + r"s?\b", p) for w in words)

ALLOWED_OPS = {
    "add_furniture", "modify_glazing", "change_material", "modify_ventilation",
    "add_window", "move_window", "remove_furniture", "remove_window", "remove_door",
}


_SYSTEM_PROMPT = """\
You are the edit planner for an architectural comfort copilot. The user wants to modify an
apartment layout. Decompose their message into a list of concrete edit operations.

Rooms in the current layout: {rooms}

Return ONLY a JSON object of this exact shape (no prose, no markdown fences):
{{
  "ops": [
    {{ "op": "add_furniture",     "room": "<room name or null>", "furniture_type": "plant|rug|curtain|blind|sofa|table|desk|shelf|cabinet", "count": 1, "material": "<material or null>" }},
    {{ "op": "modify_glazing",    "room": "<room name or null>", "glazing_type": "single|double|triple|null", "wants_more_light": true }},
    {{ "op": "change_material",   "room": "<room name or null>", "surface": "floor|wall|furniture", "material": "<material or null>" }},
    {{ "op": "modify_ventilation","room": "<room name or null>", "ventilation_type": "natural|mixed|mechanical" }},
    {{ "op": "add_window",        "room": "<room name or null>", "glazing_type": "single|double|triple|null" }},
    {{ "op": "move_window",       "room": "<room name or null>", "target": "<a wall e.g. 'north wall' or null>" }},
    {{ "op": "remove_furniture",  "room": "<room name or null>", "item": "<furniture name/type or null>" }},
    {{ "op": "remove_window",     "room": "<room name or null>", "target": "<window name or null>" }},
    {{ "op": "remove_door",       "room": "<room name or null>", "target": "<door name or null>" }}
  ]
}}

Rules:
  - One op per distinct change. "add 2 plants and change the glazing" -> TWO ops.
  - Split conjunctions ("and", "then", "also", "plus", commas) into separate ops.
  - "op" MUST be exactly one of: add_furniture, modify_glazing, change_material,
    modify_ventilation, add_window, move_window, remove_furniture, remove_window, remove_door.
  - "add / put / place [plant/rug/curtain/blinds/sofa/...]" -> add_furniture. Put how many in "count" (default 1).
  - "add a window / new window / more daylight by adding a window" -> add_window.
  - "move / relocate the window", "window on the <N/S/E/W> wall" -> move_window (put the wall in "target").
  - "bigger / wider existing window", "glazing", "skylight", "brighter", "more light" (no NEW window) -> modify_glazing.
  - "change / make [floor/wall/material] ..." -> change_material (surface = floor|wall|furniture).
  - "better ventilation", "add extraction/mechanical/natural ventilation", "stuffy / fresh air" -> modify_ventilation.
  - "remove / delete / take out [item]" -> remove_furniture (or remove_window / remove_door if a window/door).
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
        elif op == "change_material":
            clean["surface"] = o.get("surface")
            clean["material"] = o.get("material")
        elif op == "modify_ventilation":
            clean["ventilation_type"] = o.get("ventilation_type")
        elif op == "add_window":
            clean["glazing_type"] = o.get("glazing_type")
        elif op == "move_window":
            clean["target"] = o.get("target")
        elif op == "remove_furniture":
            clean["item"] = o.get("item")
        elif op in ("remove_window", "remove_door"):
            clean["target"] = o.get("target")
        out.append(clean)
    return out


# Keyword fallback (LLM-free). Detects EVERY category present so a plain "add a plant
# and change the floor" still produces two ops without the model. Room/params are left
# null/default for apply_edits to resolve from the raw prompt. Precedence matters:
# remove > add/move-window > glazing, so "add a window" isn't read as "more glazing".
_REMOVE_KW    = ("remove", "delete", "take out", "get rid of", "take away")
_WINDOW_ADD   = ("add a window", "add window", "new window", "another window",
                 "more windows", "extra window", "put a window", "install a window")
_WINDOW_MOVE  = ("move the window", "move window", "relocate", "reposition the window",
                 "window to the", "window on the")
_GLAZING_KW   = ("glazing", "skylight", "daylight", "more light", "brighter",
                 "bigger window", "larger window", "triple", "double", "single glaz")
_VENT_KW      = ("ventilation", "ventilate", "stuffy", "fresh air", "air quality",
                 "extraction", "extractor", "airflow", "air flow")
_FURNITURE_KW = ("plant", "rug", "curtain", "blind", "drape", "sofa", "couch", "armchair",
                 "cushion", "furniture", "shelf", "bookshelf", "desk", "table", "cabinet",
                 "bed", "chair")
_MATERIAL_NOUNS = ("carpet", "wood", "wooden", "concrete", "tile", "tiles", "fabric",
                   "cork", "stone", "ceramic", "plaster", "brick", "timber", "marble")
_SURFACE_WORDS  = ("floor", "flooring", "wall", "walls", "ceiling")
_MATERIAL_VERBS = ("change", "make", "switch", "swap", "replace")


def _heuristic_ops(prompt: str) -> list:
    p = (prompt or "").lower()
    if not p.strip():
        return []
    ops = []
    if any(k in p for k in _REMOVE_KW):
        if "window" in p:
            ops.append({"op": "remove_window", "room": None, "target": None})
        if "door" in p:
            ops.append({"op": "remove_door", "room": None, "target": None})
        if _has_word(p, _FURNITURE_KW):
            ops.append({"op": "remove_furniture", "room": None, "item": None})
        if ops:
            return ops  # a remove sentence is rarely also an add

    if any(k in p for k in _WINDOW_ADD):
        ops.append({"op": "add_window", "room": None, "glazing_type": None})
    elif "window" in p and any(k in p for k in _WINDOW_MOVE):
        ops.append({"op": "move_window", "room": None, "target": None})
    elif any(k in p for k in _GLAZING_KW):
        ops.append({"op": "modify_glazing", "room": None, "glazing_type": None,
                    "wants_more_light": True})

    if any(k in p for k in _VENT_KW):
        ops.append({"op": "modify_ventilation", "room": None, "ventilation_type": None})
    if _has_word(p, _FURNITURE_KW):
        ops.append({"op": "add_furniture", "room": None, "furniture_type": None,
                    "count": 1, "material": None})
    if any(m in p for m in _MATERIAL_NOUNS) or (
            any(s in p for s in _SURFACE_WORDS) and any(v in p for v in _MATERIAL_VERBS)):
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
