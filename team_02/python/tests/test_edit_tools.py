"""
Focused tests for the expanded agentic edit tools and the soundness chokepoint.

All pure (no LLM, no MCP): they exercise the mutators, the Shapely placement, the
in-memory geometry validator, the per-op revert loop in apply_edits, and the
suggestion-lifecycle matcher. Run from team_02/python:  python -m pytest tests/
"""
import copy
import json
import os

import pytest

import spatial
import check_layout_geometry as geo
from nodes.editing import _edits
from nodes.editing.apply_edits import build_apply_edits_node
from comfort import suggestion_lifecycle as sl
from comfort.compute_comfort_scores import compute_comfort_scores

_HERE = os.path.dirname(os.path.abspath(__file__))
_LAYOUT = os.path.join(_HERE, "..", "..", "randomized_layouts", "layout_201.json")


@pytest.fixture
def layout():
    with open(_LAYOUT, encoding="utf-8") as f:
        return json.load(f)


def _new_defects(before, after):
    return set(geo.audit_layout(after)) - set(geo.audit_layout(before))


def _room(layout, name):
    return _edits.find_target_room(layout, name, "", name)


# ── audit_layout parity + material validation ─────────────────────────────────
def test_audit_layout_matches_cli(layout):
    assert geo.audit_layout(layout) == geo.audit(_LAYOUT)


@pytest.mark.parametrize("raw,expected", [
    ("oakwood", "wood"), ("timber", "wood"), ("granite", "stone"),
    ("warm wood floor", "wood"), ("wood", "wood"), ("velvet", None), ("#fff", None), (None, None),
])
def test_validate_material(raw, expected):
    assert _edits.validate_material(raw) == expected


# ── Shapely placement is sound by construction ────────────────────────────────
def test_place_furniture_inside_and_clear(layout):
    from shapely.geometry import Polygon, box
    room = _room(layout, "master bedroom")
    poly = Polygon(spatial._ring(room["geometry"]))
    geom = spatial.place_furniture(layout, room, 0.5, 0.5)
    b = box(*spatial._bbox(geom))
    assert poly.contains(b) or poly.intersection(b).area > 0.9 * b.area  # inside the room
    for f in layout["furniture"]:
        if f["attributes"].get("roomId") == room["id"]:
            assert box(*spatial._bbox(f["geometry"])).intersection(b).area < 0.01  # no overlap


def test_place_window_on_exterior_clear_span(layout):
    room = _room(layout, "living room")
    spot = spatial.place_window(layout, room)
    assert spot is not None
    edges = spatial.exterior_edges(layout, room)
    consts = {(e["orient"], round(e["const"], 2)) for e in edges}
    assert (spot["orient"], round(spot["const"], 2)) in consts          # really on a wall
    assert spot["facing"] in ("N", "E", "S", "W")


# ── the chokepoint: every op stays sound, multi-edit, atomic revert ───────────
def _run(layout, ops, prompt="edit"):
    node = build_apply_edits_node()
    state = {"raw_prompt": prompt, "layout_json_string": json.dumps(layout),
             "last_scores_json": "", "edit_ops": ops}
    return node(state)


@pytest.mark.parametrize("ops", [
    [{"op": "add_furniture", "room": "master bedroom", "furniture_type": "plant", "count": 2}],
    [{"op": "add_window", "room": "living room", "glazing_type": "triple"}],
    [{"op": "change_material", "room": "kitchen", "surface": "wall", "material": "cork"}],
    [{"op": "add_furniture", "room": "kitchen", "furniture_type": "curtain"}],
    [{"op": "modify_ventilation", "room": "kitchen", "ventilation_type": "mechanical"}],
    [{"op": "move_window", "room": "master bedroom", "target": "south wall"}],
])
def test_edit_never_introduces_defect(layout, ops):
    out = _run(layout, ops)
    assert out["layout_updated"] is True
    after = json.loads(out["layout_json_string"])
    assert _new_defects(layout, after) == set()


def test_multi_edit_one_turn(layout):
    ops = [
        {"op": "add_window", "room": "guest bedroom", "glazing_type": "double"},
        {"op": "add_furniture", "room": "guest bedroom", "furniture_type": "curtain"},
        {"op": "change_material", "room": "guest bedroom", "surface": "wall", "material": "fabric"},
    ]
    out = _run(layout, ops)
    assert len(out["layout_diffs"]) == 3
    assert _new_defects(layout, json.loads(out["layout_json_string"])) == set()


def test_remove_door_connectivity_guard(layout):
    # The bathroom has a single door; removing it would seal the room → rejected, no change.
    out = _run(layout, [{"op": "remove_door", "room": "bathroom"}], prompt="remove the bathroom door")
    assert out["layout_updated"] is False
    assert any(r["op"] == "remove_door" for r in out["rejected_edits"])


def test_diff_exposes_touched_element_and_senses(layout):
    out = _run(layout, [{"op": "change_material", "room": "kitchen", "surface": "wall", "material": "cork"}])
    d = out["layout_diffs"][0]
    assert d["attribute"] == "wallMaterial" and d["new_value"] == "cork"
    assert d["sense_affected"] == "tactile+acoustic" and d["room_name"]


# ── scoring coherence: each tool moves its intended sense ─────────────────────
def _scores(layout, room_id):
    data = json.loads(compute_comfort_scores(json.dumps(layout)))
    return next(r["comfortScores"] for r in data["rooms"] if r["roomId"] == room_id)


def test_curtain_credits_acoustic(layout):
    rid = "room-3"
    before = _scores(layout, rid)
    room = next(r for r in layout["rooms"] if r["id"] == rid)
    _edits.apply_add_furniture(layout, room, "curtain", "fabric")
    after = _scores(layout, rid)
    assert after["acoustic"] > before["acoustic"]


def test_wall_material_moves_tactile(layout):
    rid = "room-3"
    before = _scores(layout, rid)
    room = next(r for r in layout["rooms"] if r["id"] == rid)
    _edits.apply_change_material(layout, room, "wall", "cork")
    after = _scores(layout, rid)
    assert after["tactile"] > before["tactile"]


# ── suggestion lifecycle ──────────────────────────────────────────────────────
def test_suggestion_crossoff_matches_room_and_sense():
    suggestions = json.dumps({"improvements": [
        {"roomName": "Living Room", "suggestions": [
            {"sense": "acoustic", "suggestion": "Add rugs and curtains to absorb sound"},
            {"sense": "thermal", "suggestion": "Upgrade glazing"}]}]})
    diffs = [{"room_name": "Living Room", "attribute": "furniture",
              "new_value": "added rug (fabric)", "sense_affected": "tactile+acoustic"}]
    applied = sl.newly_applied(diffs, suggestions)
    assert {"roomName": "Living Room", "sense": "acoustic"} in applied
    overlaid = json.loads(sl.overlay_applied(suggestions, applied))
    flags = {s["sense"]: s["applied"] for s in overlaid["improvements"][0]["suggestions"]}
    assert flags["acoustic"] is True and flags["thermal"] is False
