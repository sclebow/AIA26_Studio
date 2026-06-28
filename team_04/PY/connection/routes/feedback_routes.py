"""Architectural-feedback routes — the AI manipulation layer ABOVE move/rotate/
scale.

POST /sessions/{id}/buildings/{building_id}/feedback   {feedback: "I want more daylight"}
  1. gather_metrics()        — existing analysis tools (setback, 3D view, density…)
  2. reason_about_feedback() — LLM (or heuristic fallback) -> {reason, observations, actions[]}
  3. parse_actions()         — abstract action strings -> concrete transforms
  4. execute each transform through the SAME geometry backend the manual Move/
     Rotate/Scale tools use (tool_dev_runtime.modify_geometry + _validate_transformed),
     accumulating onto a working footprint and rejecting any step that leaves the site.
  5. persist the final accepted footprint (+ floors/height metadata) and return the
     full reasoning trace so the UI can show "✓ reasoning … ✓ actions … applied".

The existing explicit-command route (building_transform_routes) is untouched —
this is a strictly additive second mode that ends up calling the same engine.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..notebook_logic import feedback_reasoning, tool_dev_runtime
from ..session_store import store
from .building_transform_routes import (
    _building_id,
    _scale_about_centroid,
    _unwrap,
    _validate_transformed,
)

router = APIRouter(prefix="/sessions", tags=["architectural-feedback"])

DEFAULT_FLOOR_HEIGHT_M = 3.0


class FeedbackRequest(BaseModel):
    feedback: str
    # When false, only reason + parse (no geometry change) — lets a UI preview the
    # plan first. Defaults to true (reason AND apply in one call).
    apply: bool = True
    # The SELECTED building element this command targets ("central mass", a wing, a
    # tower). The manipulation must modify ONLY this part. None = whole building.
    part_id: str | None = None
    part_name: str | None = None


def _has_road_geometry(urban_ctx: dict[str, Any] | None) -> bool:
    """True if the stored urban context carries any road polyline (layers[*].roads).
    Road alignment ('align facade to main road') needs road LINES, not site edges — so
    the context-availability gate must let it through when roads exist even if edges
    don't."""
    layers = (urban_ctx or {}).get("layers") or {}
    for lid, layer in layers.items():
        if str(lid).startswith("roads.") and (layer or {}).get("roads"):
            return True
    return False


def _ring_fits_site(ring: list[list[float]], site_boundary: list[list[float]] | None) -> bool:
    """True if `ring` lies (within ~1 m²) inside the confirmed site. Used to reject
    a footprint-GROWING op (e.g. lengthen a facade) that would leave the site."""
    if not site_boundary or len(site_boundary) < 3 or not ring or len(ring) < 3:
        return False
    try:
        from shapely.geometry import Polygon

        bp = Polygon([(p[0], p[1]) for p in ring])
        sp = Polygon([(p[0], p[1]) for p in site_boundary])
        if not bp.is_valid or not sp.is_valid:
            return False
        return bp.difference(sp).area < 1.0
    except Exception:  # noqa: BLE001
        return False


# Reason Node action name -> a phrase the literal parser (feedback_reasoning.
# parse_action) already understands. Used as a FALLBACK when a vague prompt
# classifies to an intent but yields no explicit geometry command.
_REASON_ACTION_PHRASES: dict[str, str] = {
    "reduce_depth": "reduce depth",
    "modify_mass_depth": "reduce depth",
    "create_courtyard": "add courtyard",
    "generate_courtyard": "add courtyard",
    "carve_void": "add courtyard",
    "add_central_space": "add courtyard",
    "create_atrium": "add courtyard",
    "hollow_interior": "add courtyard",
    "rotate_building": "rotate 15 degrees",
    "rotate_facade": "rotate 15 degrees",
    "modify_orientation": "rotate 15 degrees",
    "add_floors": "add 2 floors",
    "increase_height": "add 2 floors",
    "modify_height": "add 2 floors",
    "adjust_tower_height": "add 2 floors",
    "remove_floors": "remove 1 floor",
    "increase_facade_length": "lengthen the north facade",
    "stretch_wings": "lengthen the north facade",
    "expand_wings": "lengthen the north facade",
    "reduce_footprint": "reduce depth",
    "reduce_coverage": "reduce depth",
    "orient_facade": "align long facade to north",
    "align_to_direction": "align long facade to north",
    "face_direction": "align long facade to north",
    # Repositioning / separation actions (privacy, acoustics, openspace intents).
    # These map to real geometry ops the parser already understands so a vague
    # intent ("reduce noise", "more privacy") still produces a concrete change.
    "reposition_building": "move 8m north",
    "shift_mass": "move 8m north",
    "increase_setback": "move 8m north",
    "move_building": "move 8m north",
    "separate_masses": "add courtyard",
    "increase_spacing": "add courtyard",
    "split_mass": "add courtyard",
}


def _reason_actions_to_phrases(actions: list[str], intent_id: str) -> list[str]:
    """Translate Reason Node action names into parser-ready phrases (fallback path).
    Unknown actions are dropped; keeps order, de-duplicates."""
    phrases: list[str] = []
    for a in actions:
        phrase = _REASON_ACTION_PHRASES.get(str(a))
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    return phrases[:3]  # cap so a single vague prompt doesn't fire many ops


# Map a selected part name/id onto the wing ROLE used by the floor-plate stack, so a
# command targets exactly the selected geometry. "central mass" -> the connector/stem
# (the central wing); explicit wings map to themselves. None/whole building -> None.
_PART_ALIASES: dict[str, list[str]] = {
    "central": ["connector", "stem", "central", "core", "centre", "center"],
    "right": ["right", "right_wing", "east", "east_wing"],
    "left": ["left", "left_wing", "west", "west_wing"],
    "north": ["north", "north_wing", "north_tower"],
    "south": ["south", "south_wing", "south_tower"],
}


def _retransform_rings(rings: list[list], old_b: list, new_b: list) -> list[list]:
    """Apply the boundary's old→new transform (rotation + centroid shift + uniform scale)
    to a set of rings (courtyard/patio holes), so the carved void tracks the moved/
    rotated/scaled facade exactly. Rotation is inferred from the longest-edge bearing of
    old vs new boundary, so a rotate op carries the hole around with the mass."""
    import math as _m

    def _centroid(b):
        pts = [(float(p[0]), float(p[1])) for p in b if len(p) >= 2]
        if not pts:
            return (0.0, 0.0)
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    def _span(b):
        xs = [p[0] for p in b if len(p) >= 2]; ys = [p[1] for p in b if len(p) >= 2]
        if not xs:
            return 1.0
        return max(1e-6, max(max(xs) - min(xs), max(ys) - min(ys)))

    def _longest_edge_angle(b):
        pts = [(float(p[0]), float(p[1])) for p in b if len(p) >= 2]
        best_len, ang = 0.0, 0.0
        n = len(pts)
        for i in range(n):
            a, c = pts[i], pts[(i + 1) % n]
            d = _m.hypot(c[0] - a[0], c[1] - a[1])
            if d > best_len:
                best_len, ang = d, _m.atan2(c[1] - a[1], c[0] - a[0])
        return ang

    ocx, ocy = _centroid(old_b)
    ncx, ncy = _centroid(new_b)
    scale = _span(new_b) / _span(old_b)
    # rotation = change in the longest-edge bearing (handles a rotate op).
    drot = _longest_edge_angle(new_b) - _longest_edge_angle(old_b)
    ca, sa = _m.cos(drot), _m.sin(drot)
    out = []
    for ring in rings:
        new_ring = []
        for q in ring:
            # translate to old centroid, scale, rotate, then to new centroid.
            x, y = (float(q[0]) - ocx) * scale, (float(q[1]) - ocy) * scale
            rx, ry = x * ca - y * sa, x * sa + y * ca
            new_ring.append([ncx + rx, ncy + ry])
        out.append(new_ring)
    return out


def _translate_plates(plates: list[dict[str, Any]], dx: float, dy: float) -> list[dict[str, Any]]:
    """Shift every plate by (dx, dy) — its footprint, its per-wing footprints AND its
    courtyard/patio HOLES. The place_center / place_corner / place_edge moves used to
    translate only `footprint`, leaving `wing_footprints` at the old spot (a later 'add
    floors on <wing>' then placed the new floor at the stale location — the misaligned
    block) and leaving each plate's `holes` at the old spot (the carved courtyard stayed
    behind while the mass moved — the 'cutout doesn't move with the building' bug).
    Translating all three keeps the whole floor — walls AND void — welded to the move."""
    out = []
    for p in plates:
        np = dict(p)
        np["footprint"] = [[pt[0] + dx, pt[1] + dy] for pt in p["footprint"]]
        wf = p.get("wing_footprints")
        if isinstance(wf, dict):
            np["wing_footprints"] = {
                r: [[pt[0] + dx, pt[1] + dy] for pt in ring] for r, ring in wf.items()
            }
        ph = p.get("holes")
        if isinstance(ph, list) and ph:
            np["holes"] = [[[pt[0] + dx, pt[1] + dy] for pt in ring] for ring in ph]
        out.append(np)
    return out


def _retransform_plates(plates: list[dict[str, Any]], old_b: list, new_b: list) -> list[dict[str, Any]]:
    """Move/scale every plate footprint to follow a whole-building boundary change.
    Infers translation (centroid shift) + uniform scale (size ratio) from old->new
    boundary and applies it about the old centroid, so the floor stack stays welded
    to the facade. Rotation from a rotate op is captured by the scale+translate of the
    bbox closely enough for stacked plates; per-wing floor differences are preserved."""
    def _centroid(b):
        pts = [(float(p[0]), float(p[1])) for p in b if len(p) >= 2]
        if not pts:
            return (0.0, 0.0)
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    def _span(b):
        xs = [p[0] for p in b if len(p) >= 2]; ys = [p[1] for p in b if len(p) >= 2]
        if not xs:
            return 1.0
        return max(1e-6, max(max(xs) - min(xs), max(ys) - min(ys)))

    ocx, ocy = _centroid(old_b)
    ncx, ncy = _centroid(new_b)
    scale = _span(new_b) / _span(old_b)

    def _xf(q):
        return [ncx + (q[0] - ocx) * scale, ncy + (q[1] - ocy) * scale]

    out = []
    for p in plates:
        np = dict(p)
        np["footprint"] = [_xf(q) for q in p["footprint"]]
        if "wing_footprints" in p:
            np["wing_footprints"] = {
                r: [_xf(q) for q in ring] for r, ring in p["wing_footprints"].items()
            }
        # Carry each plate's courtyard/patio holes through the same transform so the void
        # follows the moved/scaled footprint instead of staying at the old spot (the
        # 'cutout doesn't move with the building' bug on whole-building move/rotate/scale).
        ph = p.get("holes")
        if isinstance(ph, list) and ph:
            np["holes"] = [[_xf(q) for q in ring] for ring in ph]
        out.append(np)
    return out


def _geometry_signature(bld: dict[str, Any]) -> tuple:
    """A hashable snapshot of the building geometry, used to detect a REAL change
    (boundary + holes + floor count + per-plate footprints, rounded to ~1cm)."""
    def _r(ring):
        return tuple((round(float(p[0]), 2), round(float(p[1]), 2)) for p in (ring or []) if len(p) >= 2)
    boundary = _r(bld.get("boundary") or bld.get("building_boundary") or [])
    holes = tuple(_r(h) for h in (bld.get("holes") or []))
    floors = int(bld.get("floors") or 0)
    plates = tuple((round(p.get("z_base", 0), 2), _r(p.get("footprint"))) for p in (bld.get("floor_plates") or []))
    return (boundary, holes, floors, plates)


def _edge_direction(edge: dict[str, Any]) -> str | None:
    """Compass direction an edge faces, from its midpoint relative to the edge segment's
    own a/b — fallback when the stored edge has no 'direction' field. Uses the outward
    normal of the a→b segment (x=east, y=north), matching the viewer/overpass convention."""
    a, b, mid = edge.get("a"), edge.get("b"), edge.get("mid")
    if not (a and b and len(a) >= 2 and len(b) >= 2):
        return None
    # Edge direction vector; outward normal is perpendicular. Pick the normal pointing
    # away from the segment's own midpoint reference if available, else just use one.
    ex, ey = float(b[0]) - float(a[0]), float(b[1]) - float(a[1])
    nx, ny = ey, -ex  # right-hand normal
    import math as _m
    ang = (_m.degrees(_m.atan2(ny, nx)) + 360) % 360
    octants = ["East", "Northeast", "North", "Northwest", "West", "Southwest", "South", "Southeast"]
    return octants[round(ang / 45) % 8].lower()


def _is_precise_command(text: str) -> bool:
    """True for explicit, numeric commands ("add 2 floors", "scale 1.2", "move 5m
    north", "make it 20 floors", "rotate 30") — these should bypass the character
    layer and use the literal parser, so a precise instruction is honoured exactly."""
    low = (text or "").lower()
    return bool(
        re.search(r"\b(add|remove)\s+\d+\s*(floors?|stor(?:eys?|ies)|levels?)", low)
        or re.search(r"\b(make it|set to)\s+\d+\s*(floors?|m\b|meters?)", low)
        or re.search(r"\bscale\s+\d", low)
        or re.search(r"\b(move|shift|rotate|turn)\b.*\d", low)
        or re.search(r"\bcorner\b", low)
    )


def _resolve_part_role(part_id, part_name, wings) -> str | None:
    """Return the wing ROLE (e.g. 'connector') for the selected part, or None for the
    whole building. Prefers the unambiguous part_id ('wing_<idx>'); falls back to
    alias/name matching."""
    wlist = [w for w in (wings or []) if isinstance(w, dict)]
    pid = str(part_id or "").lower()
    if pid in ("building", "") or "whole" in pid:
        # Only treat as whole-building when there's no informative name either.
        if not part_name or "whole" in str(part_name).lower() or "building" in str(part_name).lower():
            return None

    # 1) Exact part_id 'wing_<idx>' -> that wing's real role (most reliable).
    m = re.match(r"wing_(\d+)", pid)
    if m:
        idx = int(m.group(1))
        for w in wlist:
            if int(w.get("wing_index", w.get("index", -1))) == idx:
                return str(w.get("role") or "").lower() or None
        if 0 <= idx < len(wlist):
            return str(wlist[idx].get("role") or "").lower() or None

    # 2) Alias/name matching against the building's actual roles.
    key = (pid + " " + str(part_name or "")).lower()
    roles = [str(w.get("role") or "").lower() for w in wlist]
    for _group, aliases in _PART_ALIASES.items():
        if any(a in key for a in aliases):
            for r in roles:
                if any(a in r for a in aliases):
                    return r
    for r in roles:  # direct role-name match
        if r and r.replace("_", " ") in key:
            return r
    return None


def _apply_footprint_transform(
    geometry_id: str,
    boundary: list[list[float]],
    transform: dict[str, Any],
    site_boundary: list[list[float]] | None,
) -> dict[str, Any]:
    """Run ONE move/rotate/scale through the existing backend + validation.
    Returns {accepted, boundary, reason?}. Mirrors building_transform_routes so
    both modes share identical geometry + site-fit behaviour."""
    scale = float(transform.get("scale", 1.0) or 1.0)
    dx = float(transform.get("dx", 0.0) or 0.0)
    dy = float(transform.get("dy", 0.0) or 0.0)
    rotation = float(transform.get("rotation", 0.0) or 0.0)

    working = _scale_about_centroid(boundary, scale)
    try:
        result = tool_dev_runtime.modify_geometry(
            geometry_id, working, site_boundary=site_boundary,
            translate_by_xy=[dx, dy], rotation_degrees=rotation,
        )
    except Exception as exc:  # noqa: BLE001
        return {"accepted": False, "boundary": boundary, "reason": str(exc)}

    data = _unwrap(result)
    new_boundary = data.get("transformed_boundary") or working
    verdict = _validate_transformed(new_boundary, site_boundary, data)
    if not verdict["valid"]:
        return {"accepted": False, "boundary": boundary, "reason": verdict["reason"]}
    return {"accepted": True, "boundary": new_boundary}


@router.post("/{session_id}/buildings/{building_id}/feedback")
async def architectural_feedback(
    session_id: str, building_id: str, body: FeedbackRequest
) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not (body.feedback or "").strip():
        raise HTTPException(status_code=422, detail="No feedback text provided")

    placed = list(state.get("placed_buildings", []) or [])
    idx = next(
        (i for i, b in enumerate(placed) if isinstance(b, dict) and _building_id(b) == building_id),
        None,
    )
    if idx is None:
        raise HTTPException(status_code=404, detail="Building not found in session")

    bld = dict(placed[idx])
    boundary = bld.get("boundary") or bld.get("building_boundary")
    geometry_id = bld.get("geometry_id") or building_id
    if not boundary:
        raise HTTPException(status_code=422, detail="Building has no boundary to manipulate")

    # SELECTED TARGET (spec #2/#3/#7): resolve the selected part to a wing role so the
    # manipulation modifies ONLY that geometry. "central mass" -> connector/stem, etc.
    target_role = _resolve_part_role(body.part_id, body.part_name, bld.get("wings"))
    target_name = body.part_name or (target_role.replace("_", " ") if target_role else "the whole building")

    # BEFORE snapshot (spec #8): per-wing floor counts, to verify only the target changed.
    def _wing_floor_counts(b: dict[str, Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in (b.get("floor_plates") or []):
            w = (p.get("wing") or "__base__")
            counts[w] = counts.get(w, 0) + 1
        return counts

    before_counts = _wing_floor_counts(bld)
    before_total = int(bld.get("floors") or 0)
    # GEOMETRY SIGNATURE before any op — to confirm a REAL change happened (Fix 1/2).
    before_sig = _geometry_signature(bld)

    site_boundary = state.get("site_boundary") or None
    # BUILDABLE area = site minus the setback. Rotations/moves are validated against THIS
    # (not the raw site) so a building can never sit in the setback zone or poke past the
    # boundary. Falls back to the raw site if setback rules aren't available.
    buildable_boundary = site_boundary
    if site_boundary:
        try:
            from ..notebook_logic import setback_rules as _sr

            _use = bld.get("building_use") or "residential"
            _bp = _sr.create_buildable_area(site_boundary, _sr.get_setback_rules(_use))
            if _bp is not None and not _bp.is_empty:
                buildable_boundary = [[float(x), float(y)] for x, y in _bp.exterior.coords]
        except Exception:  # noqa: BLE001
            buildable_boundary = site_boundary
    others = [
        b.get("boundary")
        for j, b in enumerate(placed)
        if j != idx and isinstance(b, dict) and b.get("boundary")
    ]

    # 1 + 2: gather metrics and reason about the feedback.
    metrics = feedback_reasoning.gather_metrics(
        bld, site_boundary=site_boundary, others=others
    )
    plan = feedback_reasoning.reason_about_feedback(body.feedback, metrics)
    parsed = feedback_reasoning.parse_actions(plan.get("actions", []))

    # FEATURE 12 — CONTEXT-AWARE MANIPULATION: if the prompt references an urban
    # feature ("move toward metro", "face park", "reduce noise exposure") or "selected
    # edge", resolve it against the STORED urban context and produce a concrete
    # align/place op. This makes manipulation use context memory + selected edge, no
    # coordinates needed.
    context_manip = None
    ctx_intent_obj = None  # set below; pre-bound so later references are always safe
    try:
        from ..notebook_logic import context_aware_shape_generator as casg

        urban_ctx = state.get("urban_context") or {}
        low_fb = (body.feedback or "").lower()
        # A per-wing / per-floor command ("add 3 floors on the north wing", "move the
        # bottom 5 floors to the north edge") names a WING/edge as the target of a floor
        # op — NOT a request to place the whole building near a context feature. Detect
        # it first and SUPPRESS directional/context placement so the floor op wins.
        _pre_literal = feedback_reasoning.parse_action(body.feedback)
        _is_floor_plate_cmd = bool(_pre_literal and _pre_literal.get("op") in ("floor_add_wing", "floor_move", "set_floors"))
        # "lengthen the facade facing the road" names the road only to identify WHICH
        # facade to GROW — not to move the building there. Detect it and suppress the
        # context PLACEMENT (the lengthen op is built separately, below) so we don't both
        # move AND lengthen.
        _is_facade_lengthen = bool(
            re.search(r"\b(lengthen|extend|elongate|longer|stretch)\b", low_fb)
            and re.search(r"\b(facade|frontage|front|side|edge)\b", low_fb)
        )
        # If the literal parser already resolved a corner/edge/centre PLACEMENT (e.g.
        # "move building towards southwest" → place_corner), let THAT win — don't also run
        # the context path (which fails with "Unable to act on 'that feature'" for a bare
        # direction). This is what makes "move southwest" / "move south" actually move.
        _is_literal_place = bool(_pre_literal and _pre_literal.get("op") in ("place_corner", "place_edge", "place_center"))
        _suppress_placement = _is_floor_plate_cmd or _is_facade_lengthen or _is_literal_place
        ctx_intent_obj = casg.extract_context_intent(body.feedback)
        dir_intent = None if _suppress_placement else casg.extract_directional_intent(body.feedback)
        wants_selected_edge = "selected edge" in low_fb
        wants_selected_corner = "selected corner" in low_fb
        wants_context = (not _suppress_placement) and bool(
            ctx_intent_obj or dir_intent or wants_selected_edge or wants_selected_corner)

        # CONTEXT AVAILABILITY RULES: verify the REQUIRED context exists before acting.
        # Never fabricate; explain exactly what is missing.
        if wants_selected_edge and not (state.get("selected_edge") or urban_ctx.get("selected_edge")):
            context_manip = {"missing": "No edge is currently selected. Please select a site edge first."}
        elif wants_selected_corner and not state.get("selected_corner"):
            context_manip = {"missing": "No corner is currently selected. Please select a site corner first."}
        elif wants_context and not (urban_ctx.get("edges") or urban_ctx.get("edge_metadata")
                                    or _has_road_geometry(urban_ctx)):
            # The whole context memory is missing. (Road alignment only needs road
            # polylines in `layers`, not site `edges` — so don't block it when roads
            # exist but edges don't.)
            feat = (ctx_intent_obj or {}).get("phrase", "that feature")
            context_manip = {"missing": (
                f"Unable to act on '{feat}' because urban context analysis has not been "
                "generated. Please run Urban Context first, then try again.")}
        elif wants_selected_edge:
            # Use the STORED selected edge directly (validated present above).
            sel = state.get("selected_edge") or urban_ctx.get("selected_edge")
            align = bool(re.search(r"\b(facade|frontage|align|parallel|long side|face|entrance)\b", low_fb))
            if align:
                r = casg.align_long_facade_to_edge(boundary, sel)
            else:
                _btype = bld.get("building_type") or bld.get("shape_type") or "L"
                r = casg.place_shape_near_edge(boundary, sel, site_boundary, building_type=_btype)
            if r.get("ok"):
                context_manip = {"boundary": r["boundary"],
                                 "target_edge": sel.get("display_name") or sel.get("label"),
                                 "operations": ["selected_edge"]}
            else:
                context_manip = {"missing": f"Could not apply to the selected edge: {r.get('reason')}"}
        elif wants_context:
            # Use the SAME building_type the self-debug validator uses (validate_design:
            # building_type or shape_type or "L") so place_near_edge snaps to the IDENTICAL
            # buildable area the validator enforces. A mismatch (e.g. "residential" here vs
            # "L" in the validator) gave different setbacks → the validator rejected the
            # snapped position and self-debug recentred the building, collapsing the move.
            _btype = bld.get("building_type") or bld.get("shape_type") or "L"
            cres = casg.apply_context_to_shape(body.feedback, boundary, site_boundary, urban_ctx,
                                               building_type=_btype)
            if cres.get("applied"):
                context_manip = {
                    "boundary": cres["boundary"],
                    "target_edge": cres.get("target_edge"),
                    "operations": cres.get("operations"),
                }
            elif cres.get("status") == "target_not_found" and cres.get("reason"):
                # A SPECIFIC feature wasn't stored (e.g. no metro edge) — explain it
                # precisely instead of a generic "couldn't map" message.
                feat = (ctx_intent_obj or {}).get("phrase", "that feature")
                context_manip = {"missing": (
                    f"Unable to act on '{feat}' because {feat} analysis is not available "
                    "in the stored urban context. Please regenerate urban context.")}
            elif cres.get("status") == "context_missing":
                context_manip = {"missing": cres.get("reason")}
            elif cres.get("status") == "no_valid_op":
                # The target resolved but the building is ALREADY at the best spot for it
                # (e.g. "move away from noise" when it's already as far from the road as the
                # setback allows). That's not a failure — report it honestly and positively
                # instead of a fake "✅ Updated" with no visible move. Phrase it in terms of
                # the FEATURE the user named ("noise"/"the park") rather than the raw edge.
                _intent = ctx_intent_obj or {}
                _phrase = _intent.get("phrase")
                _away = _intent.get("away")
                if _phrase:
                    _already = (f"the building is already positioned as far from {_phrase} "
                                "as the site setback allows" if _away
                                else f"the building is already as close to {_phrase} as the site setback allows")
                else:
                    _already = cres.get("reason") or "the building is already in the best position for that."
                context_manip = {"already": _already}
    except Exception:  # noqa: BLE001
        context_manip = None

    # CONTEXT-AWARE LENGTHEN: "lengthen the facade facing the road" / "make the facade
    # toward the primary road longer". The user's VERB is lengthen (grow that side), but
    # the side is named by a CONTEXT FEATURE ("the road"), not a compass word — so the
    # literal parser can't resolve a direction. Resolve the feature → the road-facing
    # EDGE → its compass direction, then run the real `lengthen` op on that side. This is
    # what makes the road-facing phrasing actually EXTEND the facade instead of rotating.
    context_lengthen: dict[str, Any] | None = None
    try:
        import re as _re
        _low = (body.feedback or "").lower()
        _wants_lengthen = bool(_re.search(r"\b(lengthen|extend|elongate|longer|stretch)\b", _low)) and \
            bool(_re.search(r"\b(facade|frontage|front|side|edge|wing|mass)\b", _low))
        # Only when there's NO explicit compass direction (that path already works) but
        # there IS a context feature to resolve.
        _has_dir = bool(casg.extract_directional_intent(body.feedback)) if "casg" in dir() else False
        if _wants_lengthen and not _has_dir and ctx_intent_obj:
            from ..notebook_logic import context_aware_shape_generator as _casg2

            urban_ctx2 = state.get("urban_context") or {}
            edge_meta = urban_ctx2.get("edge_metadata") or urban_ctx2.get("edges") or []
            resolved = _casg2.resolve_target_edge(body.feedback, edge_meta)
            if resolved.get("ok"):
                edge = resolved["edge"]
                # Edge's compass direction (stored, or derived from its outward normal).
                direction = (edge.get("direction") or "").lower() or _edge_direction(edge)
                if direction:
                    context_lengthen = {
                        "op": "lengthen",
                        "transform": {"direction": direction, "amount_pct": 0.2},
                        "text": body.feedback,
                        "target_feature": (ctx_intent_obj or {}).get("phrase"),
                        "target_edge": edge.get("display_name") or edge.get("edge_id"),
                    }
            elif resolved.get("reason") == "feature_not_stored":
                feat = (ctx_intent_obj or {}).get("phrase", "that feature")
                context_manip = context_manip or {"missing": (
                    f"Unable to lengthen the facade toward '{feat}' because no {feat} edge "
                    "is in the stored urban context. Run Urban Context, or name a direction "
                    "(e.g. 'lengthen the south facade').")}
    except Exception:  # noqa: BLE001
        context_lengthen = None

    # Track whether a RECOGNIZED layer understood the RAW USER PROMPT (literal parser
    # or precise command) — NOT the LLM plan (which can hallucinate parseable actions
    # from nonsense). If only the LLM produced an op for otherwise-unrecognized input,
    # we must NOT claim success (Fix 1). Character recognition is added after its block.
    raw_literal = feedback_reasoning.parse_action(body.feedback)
    literal_recognized = (
        _is_precise_command(body.feedback)
        or bool(raw_literal and raw_literal.get("op") not in (None, "unsupported"))
        or bool(context_manip and context_manip.get("boundary"))
    )

    # LAYER 1 — DIRECT COMMAND PRIORITY. A precise, explicit command ("add 4 floors",
    # "rotate 25", "scale 1.2", "scale up by 1.2", "move 10m north") must use its OWN
    # parsed op, not the LLM/heuristic plan's guess (which for unrecognised metrics
    # often falls back to a generic "rotate 10 degrees"). Without this, "add 4 floors"
    # silently rotated. We trust the literal parse when EITHER the precise-command
    # detector fires OR the nodes/ direct-command layer recognises it as a command and
    # the parser produced a deterministic op (covers "scale up by 1.2").
    _is_direct_cmd = False
    try:
        from ..nodes import direct_command as _dc

        _is_direct_cmd = _dc.is_direct_command(body.feedback)
    except Exception:  # noqa: BLE001
        _is_direct_cmd = False
    # Also trust the literal parse when it produced a DETERMINISTIC footprint/geometry
    # op — even without a numeric amount. "increase the footprint" → scale, "add a
    # courtyard" → courtyard, "reduce depth" → reduce_depth. These are unambiguous user
    # commands; without this they were overridden by the reason-node's generic fallback
    # (e.g. "increase footprint" silently rotated). Excludes align_facade/rotate (those
    # are handled by their own priority paths) to avoid hijacking orient requests.
    # Trust ONLY unambiguous, self-validating ops here. Sizing/floor ops are safe
    # ("increase footprint"→scale, "add 2 floors"→floors). Placement/move ops are NOT
    # in this list: a bare move with a heuristically-chosen direction can collapse the
    # footprint on a multi-wing shape — those flow through the normal path where the
    # reason-node candidate fall-through can pick a different valid op instead.
    _deterministic_literal = bool(
        raw_literal and raw_literal.get("op") in (
            "scale", "courtyard", "patio", "reduce_depth", "lengthen", "wing",
            "floors", "set_floors", "height",
        )
    )
    if (raw_literal and raw_literal.get("op") not in (None, "unsupported")
            and (_is_precise_command(body.feedback) or _is_direct_cmd or _deterministic_literal)):
        parsed = [raw_literal]

    # CONTEXT-LENGTHEN PRIORITY: "lengthen the facade facing the road" resolved to a
    # lengthen op on the road-facing edge above. The user's VERB is lengthen — honour it
    # over the literal parser's incidental align/rotate reading and over the LLM plan.
    if context_lengthen:
        parsed = [context_lengthen]
        literal_recognized = True  # a real, user-stated op — not a hallucination

    # CONTEXT "ALREADY OPTIMAL" SHORT-CIRCUIT: a context placement ("move away from noise",
    # "move toward transit") resolved its target but the building is ALREADY at the best
    # spot, so there's nothing to do. Clear all parsed ops and mark the prompt recognized
    # so the response is an honest "no change needed" — NOT a fall-through to a generic
    # LLM-guessed align/rotate that produces the misleading "already aligned" message.
    _ctx_already = bool(context_manip and context_manip.get("already"))
    if _ctx_already:
        parsed = []
        literal_recognized = True  # we DID understand the prompt; it just needs no move

    # ───────────────────────── RULES WIN, LLM LAST ─────────────────────────
    # Deterministic precedence. A prompt is resolved by the FIRST rule that matches,
    # and when a rule matches we DROP the LLM/heuristic plan ("parsed" from
    # reason_about_feedback) so the same prompt always produces the same result. The
    # LLM plan is only used when NO rule recognised the prompt (genuinely vague input
    # like "make it feel calmer"). This is what stops "fix one thing, break another":
    # the move/rotate/floors/courtyard/context commands no longer depend on whether the
    # non-deterministic LLM happened to answer on a given run.
    #   1. context placement that MOVED the building   (context_manip.boundary)
    #   2. context placement already optimal (no-op)    (_ctx_already)            [above]
    #   3. context-lengthen toward a feature            (context_lengthen)        [above]
    #   4. explicit literal command                     (raw_literal, set below)
    # When 1 fires, the LLM plan must not also run a second, conflicting op.
    _rule_resolved = bool(
        (context_manip and context_manip.get("boundary"))
        or _ctx_already
        or context_lengthen
    )
    if context_manip and context_manip.get("boundary") and not context_lengthen:
        # A context MOVE/ALIGN resolved the whole prompt — it's applied directly from
        # context_manip later. Don't let the LLM plan tack on a generic rotate/courtyard.
        parsed = []
        literal_recognized = True

    # ARCHITECTURAL CHARACTER layer: turn design LANGUAGE ("make it more residential",
    # "the facade feels too flat", "increase tower separation", "make it iconic") into
    # an ordered op sequence. This is what makes TerraPilot a design partner rather than
    # a move/rotate tool. It TAKES PRIORITY for character/facade/tower/proportion language
    # (the LLM tends to map these to generic courtyard/patio ops), but a precise literal
    # command ("add 2 floors", "scale 1.2") still wins via _is_precise_command below.
    character: dict[str, Any] | None = None
    try:
        from ..notebook_logic import architectural_character as ac

        precise = _is_precise_command(body.feedback)
        character = ac.classify_character(body.feedback)
        # Don't let the character layer clobber a precise command or any prompt a
        # deterministic RULE already resolved (context move/align, already-optimal no-op,
        # context-lengthen). Rules win; the character layer is for vague design language.
        if _rule_resolved:
            character = None
        elif character and character.get("operations") and not precise and not context_lengthen:
            parsed = [
                {"op": o["op"], "transform": o.get("transform", {}), "text": o.get("text", o["op"])}
                for o in character["operations"]
            ]
        elif not parsed and character and character.get("operations"):
            parsed = [
                {"op": o["op"], "transform": o.get("transform", {}), "text": o.get("text", o["op"])}
                for o in character["operations"]
            ]
    except Exception:  # noqa: BLE001
        character = None

    # REASON NODE (intent classification brain): classify the feedback into one of
    # the 10 architectural intent categories with a confidence + WHY. This is the
    # "Reason Node" in the architecture (User Prompt -> Intent Parser -> Reason Node
    # -> Geometry Action List). It explains every manipulation and, when the literal
    # parser found NO concrete action, supplies the intent's recommended ops as a
    # fallback so vague phrasing ("it feels dark in the middle") still does something.
    reason_node: dict[str, Any] | None = None
    try:
        from ..notebook_logic import reason_node as rn

        classified = rn.classify_intent(body.feedback)
        if classified:
            top = classified[0]
            recs = rn.recommend_actions(classified)
            rec_ids = [getattr(a, "action_id", getattr(a, "action", str(a))) for a in (recs or [])]
            reason_node = {
                "intent": top.intent_id,
                "intent_name": top.intent_name,
                "confidence": round(top.confidence, 3),
                "reasoning": list(top.reasoning) if getattr(top, "reasoning", None) else [],
                "recommended_actions": rec_ids[:6],
                # Actual prompt words the Reason Node matched — the reliable signal that
                # the prompt is a REAL architectural intent (vs a low-confidence guess
                # on gibberish like 'quantum flavored' which matches no keywords).
                "matched_keywords": list(getattr(top, "matched_keywords", []) or []),
                "matched_synonyms": list(getattr(top, "matched_synonyms", []) or []),
            }
            # Fallback: if the literal parser produced nothing actionable, map the
            # Reason Node's recommended actions into concrete ops the route runs.
            # (Skip entirely when a deterministic rule already resolved the prompt.)
            if not parsed and not _rule_resolved and reason_node["recommended_actions"]:
                fallback = feedback_reasoning.parse_actions(
                    _reason_actions_to_phrases(reason_node["recommended_actions"], top.intent_id)
                )
                parsed = [p for p in fallback if p.get("op") != "unsupported"]
    except Exception:  # noqa: BLE001
        reason_node = None

    # 3-LAYER PROMPT UNDERSTANDING (connection/nodes): the upgraded intent system.
    # Runs LLM-first semantic classification (keyword fallback) -> Reason Node, which
    # returns an ORDERED set of candidate operations. We apply them as a fall-through
    # group: the execution loop tries each in turn and stops at the first that yields
    # a real geometry change. This is what makes "open it up" / "too bulky" succeed
    # even when the first choice (e.g. courtyard) doesn't fit the current shape.
    understanding: dict[str, Any] | None = None
    try:
        from ..nodes import prompt_understanding as pu

        u_ctx = {
            "shape_type": bld.get("shape_type") or bld.get("typology"),
            "site_coverage": metrics.get("site_coverage"),
            "edges": (state.get("urban_context") or {}).get("edges")
                     or state.get("context_edges") or [],
            "selected_edge": state.get("selected_edge"),
            "selected_corner": state.get("selected_corner"),
            "urban_context": state.get("urban_context"),
            "resolved_direction": (ctx_intent_obj or {}).get("direction"),
        }
        understanding = pu.understand(body.feedback, u_ctx)
        # Supply the LLM/intent candidates when the existing layers produced NOTHING —
        # OR when the only plan so far is a generic ROTATE but the LLM confidently read a
        # DESIGN-GOAL intent (e.g. "orient for ventilation" → increase_openness, whose
        # courtyard/reduce-depth ops actually move the wind/daylight scores, unlike the
        # keyword layer's incidental orient→rotate). This stops the rotate hijack.
        _only_rotate = bool(parsed) and all(p.get("op") == "rotate" for p in parsed)
        _llm_goal = (understanding.get("intent_source") == "llm"
                     and understanding.get("intent") in (
                         "increase_openness", "improve_daylight", "reduce_bulk",
                         "improve_public_realm"))
        if not _rule_resolved and (not parsed or (_only_rotate and _llm_goal)) and understanding.get("candidates"):
            cand_phrases = [c["op_phrase"] for c in understanding["candidates"]]
            cand_parsed = feedback_reasoning.parse_actions(cand_phrases)
            group = []
            for ph, cp in zip(cand_phrases, cand_parsed):
                if cp.get("op") not in (None, "unsupported"):
                    cp = dict(cp)
                    cp["_candidate_group"] = True  # fall-through marker
                    group.append(cp)
            if group:
                parsed = group
    except Exception:  # noqa: BLE001
        understanding = None

    # Also parse the RAW feedback directly: explicit floor-plate commands ("move the
    # bottom 5 floors close to the north edge", "add 2 floors on the right wing") are
    # precise geometry instructions the reasoning layer may not echo verbatim. If the
    # raw text yields a floor-plate op the plan missed, prepend it so it runs.
    raw_action = feedback_reasoning.parse_action(body.feedback)
    # If a CONTEXT alignment already rotated the footprint (e.g. "align facade to main
    # road" → aligned to the real road bearing), do NOT also run the literal compass
    # align_facade — that would re-rotate to a default direction and undo the road
    # alignment (the "already aligned, no rotation needed" bug). The context result wins.
    _ctx_aligned = bool(context_manip and context_manip.get("boundary")
                        and "align" in str(context_manip.get("operations") or []).lower())
    if raw_action and _ctx_aligned and raw_action.get("op") == "align_facade":
        raw_action = None
    # If a deterministic context rule already resolved the prompt (a move/align that ran,
    # or an already-optimal no-op), don't let a raw place/move re-enter the pipeline and
    # apply a second, conflicting op. Rules win; keep the single resolved result.
    if _rule_resolved:
        raw_action = None
    if raw_action and raw_action.get("op") in (
        "floor_move", "floor_add_wing", "set_floors", "align_facade",
        "place_corner", "place_edge", "place_center",
    ):
        if not any(p.get("op") == raw_action["op"] for p in parsed):
            # Drop the reasoning layer's GENERIC equivalent so the same intent isn't
            # applied twice: a floor_move/place_* supersedes a whole-building "move";
            # floor_add_wing / set_floors supersedes a generic "floors"; align_facade
            # supersedes a "rotate" or a mistaken "lengthen".
            redundant = {
                "floor_move": "move", "floor_add_wing": "floors",
                "set_floors": "floors", "align_facade": "lengthen",
                "place_corner": "move", "place_edge": "move", "place_center": "move",
            }[raw_action["op"]]
            parsed = [raw_action, *[p for p in parsed if p.get("op") not in (redundant, "rotate")]]

    # Context already aligned to the road → strip any align_facade/rotate the reasoning
    # plan also produced, so the footprint isn't rotated twice.
    if _ctx_aligned:
        parsed = [p for p in parsed if p.get("op") not in ("align_facade", "rotate")]

    # Preview-only: return the plan without touching geometry.
    if not body.apply:
        return {
            "building_id": building_id,
            "feedback": body.feedback,
            "reason": plan.get("reason"),
            "observations": plan.get("observations", []),
            "reasoning_source": plan.get("source"),
            "actions": [
                {"text": p["text"], "op": p["op"], "transform": p.get("transform")}
                for p in parsed
            ],
            "metrics": metrics,
            "applied": False,
        }

    # 3 + 4: execute each action, accumulating onto a working footprint. Footprint
    # ops go through the shared geometry backend; floors/height are metadata-only
    # (preserve the footprint, per the "make it taller / keep this option" intent).
    working_boundary = list(boundary)
    working_holes = [list(h) for h in (bld.get("holes") or [])]  # courtyard/patio voids
    floor_height = float(metrics.get("height_m", 12.0)) / max(1, int(bld.get("floors") or 4))
    if not bld.get("floors"):
        floor_height = DEFAULT_FLOOR_HEIGHT_M
    current_floors = int(bld.get("floors") or 0)
    current_height = float(bld.get("height_m") or metrics.get("height_m") or 12.0)
    floors_changed = False
    holes_changed = False
    # Per-floor geometry stack (built lazily when a floor-plate op first runs).
    working_plates = [dict(p) for p in (bld.get("floor_plates") or [])]
    plates_changed = False
    applied_results: list[dict[str, Any]] = []

    # FEATURE 12: apply a resolved context-aware placement FIRST (it already moved/
    # aligned the footprint using stored context). Sync the plates to the new boundary.
    if context_manip and context_manip.get("boundary"):
        old_b = list(working_boundary)
        working_boundary = context_manip["boundary"]
        if working_plates:
            working_plates = _retransform_plates(working_plates, old_b, working_boundary)
            plates_changed = True
        # Carry any HOLES (a courtyard/patio) along with the move — otherwise the void
        # stays at the OLD position while the footprint moves, producing invalid geometry
        # that self-debug then REVERTS (the prompt failing with "no concrete operation"
        # after a courtyard was added, e.g. "move away from noise" on a courtyard-ed U).
        if working_holes:
            working_holes = _retransform_rings(working_holes, old_b, working_boundary)
            holes_changed = True
        applied_results.append({
            "text": f"context placement toward {context_manip.get('target_edge')}",
            "op": "context_place", "accepted": True, "modified_part": "building",
            "result": f"placed/aligned toward {context_manip.get('target_edge')}",
        })

    # Fall-through control for Reason-Node candidate groups: once ANY candidate in a
    # group is accepted, skip the rest (they're alternatives, not a sequence). We
    # detect acceptance by watching the accepted-op count grow across iterations.
    candidate_group_satisfied = False
    _prev_accepted = 0

    for p in parsed:
        op, transform, text = p["op"], p.get("transform"), p["text"]
        is_candidate = bool(p.get("_candidate_group"))
        # A previous candidate in this group succeeded → its accepted count grew.
        if is_candidate:
            now_accepted = sum(1 for r in applied_results if r.get("accepted"))
            if now_accepted > _prev_accepted:
                candidate_group_satisfied = True
            _prev_accepted = now_accepted
            if candidate_group_satisfied:
                continue  # skip remaining alternatives
        if op == "unsupported" or not transform:
            applied_results.append({"text": text, "op": op, "accepted": False,
                                    "reason": "Action not recognized by the manipulation engine."})
            continue

        # Corner / edge placement: translate the WHOLE building (footprint + plates)
        # so it sits at the named site corner/edge, inset by a setback margin.
        # Move to the SITE CENTRE: translate the footprint (and plates) so the building
        # centroid sits at the site centroid. Resolved here because the parser can't see
        # the site geometry. Validated against the site like any other move.
        if op == "place_center":
            if not site_boundary:
                applied_results.append({"text": text, "op": op, "accepted": False,
                                        "reason": "no site boundary to centre within",
                                        "suggestion": "confirm the site first"})
                continue
            spts = [(float(p[0]), float(p[1])) for p in site_boundary if len(p) >= 2]
            bpts = [(float(p[0]), float(p[1])) for p in working_boundary if len(p) >= 2]
            scx = sum(p[0] for p in spts) / len(spts)
            scy = sum(p[1] for p in spts) / len(spts)
            bcx = sum(p[0] for p in bpts) / len(bpts)
            bcy = sum(p[1] for p in bpts) / len(bpts)
            dx, dy = scx - bcx, scy - bcy
            moved = [[p[0] + dx, p[1] + dy] for p in working_boundary]
            if not _ring_fits_site(moved, buildable_boundary):
                applied_results.append({"text": text, "op": op, "accepted": False,
                                        "reason": "the building doesn't fit centred with the setback",
                                        "suggestion": "make the building smaller first"})
                continue
            working_boundary = moved
            working_holes = [[[pt[0] + dx, pt[1] + dy] for pt in h] for h in working_holes]
            holes_changed = True
            if working_plates:
                working_plates = _translate_plates(working_plates, dx, dy)
                plates_changed = True
            applied_results.append({"text": text, "op": op, "accepted": True,
                                    "result": "centred on the site"})
            continue

        if op in ("place_corner", "place_edge"):
            from ..notebook_logic import architectural_intent as ai

            _btype = bld.get("building_type") or bld.get("shape_type") or bld.get("building_use") or "residential"
            if op == "place_corner":
                r = ai.place_at_corner(working_boundary, working_holes,
                                       corner=transform.get("corner", "northeast"),
                                       site_boundary=site_boundary, building_type=_btype)
            else:
                r = ai.place_at_edge(working_boundary, working_holes,
                                     direction=transform.get("direction", "north"),
                                     site_boundary=site_boundary, building_type=_btype)
            if not r.get("ok"):
                applied_results.append({"text": text, "op": op, "accepted": False,
                                        "reason": r.get("reason", "placement failed")})
                continue
            # Validate against the BUILDABLE area (site minus setback) — NOT the raw site —
            # so a placement can never sit in the setback zone. place_at_edge/corner already
            # snap to the buildable bbox; this is the matching guard.
            if not _ring_fits_site(r["outer"], buildable_boundary):
                applied_results.append({"text": text, "op": op, "accepted": False,
                                        "reason": "the building doesn't fit at that edge/corner with the setback",
                                        "suggestion": "make the building smaller first"})
                continue
            dx, dy = r.get("dx", 0.0), r.get("dy", 0.0)
            working_boundary = r["outer"]
            working_holes = r.get("holes", working_holes)
            holes_changed = True
            # Shift every floor plate by the same delta so the stack moves with it.
            if working_plates:
                working_plates = _translate_plates(working_plates, dx, dy)
                plates_changed = True
            applied_results.append({"text": text, "op": op, "accepted": True,
                                    "result": r.get("reason", "placed")})
            continue

        # Plate-stack sculpting (twist / taper): progressive per-floor rotation/scale.
        # These reshape the silhouette for iconic/elegant character; no footprint change.
        if op in ("twist", "taper"):
            from ..notebook_logic import floor_plates as fpl

            plate_src = dict(bld)
            plate_src["boundary"] = working_boundary
            plates = working_plates if working_plates else fpl.ensure_floor_plates(plate_src)
            if op == "twist":
                r = fpl.twist_stack(plates, total_degrees=float(transform.get("total_degrees", 25)))
            else:
                r = fpl.taper_stack(plates, top_scale=float(transform.get("top_scale", 0.75)))
            if not r.get("ok"):
                applied_results.append({"text": text, "op": op, "accepted": False,
                                        "reason": r.get("reason", "sculpting failed")})
                continue
            working_plates = r["floor_plates"]
            plates_changed = True
            applied_results.append({"text": text, "op": op, "accepted": True,
                                    "modified_part": "building", "result": r.get("reason", "applied")})
            continue

        # Architectural-intent ops: mutate the footprint (and holes), then validate
        # the new OUTER ring against the site exactly like a move/rotate/scale.
        if op in ("courtyard", "patio", "lengthen", "reduce_depth", "wing", "align_facade",
                  "stretch", "compress", "articulate_facade", "chamfer"):
            from ..notebook_logic import architectural_intent as ai

            old_b_for_op = list(working_boundary)  # boundary BEFORE this op, for plate re-transform
            if op in ("stretch", "compress"):
                axis = transform.get("axis", "x")
                factor = float(transform.get("factor", 1.25 if op == "stretch" else 0.85))
                r = ai.stretch_mass(working_boundary, working_holes, axis=axis, factor=factor)
            elif op == "articulate_facade":
                r = ai.articulate_facade(working_boundary, working_holes,
                                         direction=transform.get("direction", "south"),
                                         count=int(transform.get("count", 3)),
                                         depth_pct=float(transform.get("depth_pct", 0.08)))
            elif op == "chamfer":
                r = ai.chamfer_corners(working_boundary, working_holes,
                                       mode=transform.get("mode", "chamfer"),
                                       amount_pct=float(transform.get("amount_pct", 0.12)))
            else:
                fn = {"courtyard": ai.carve_courtyard, "patio": ai.carve_patio,
                      "lengthen": ai.lengthen_side, "reduce_depth": ai.reduce_depth,
                      "wing": ai.enlarge_wing, "align_facade": ai.align_facade}[op]
                r = fn(working_boundary, working_holes, **{k: v for k, v in transform.items()})
            # DAYLIGHT FALLBACK: a courtyard that can't fit (footprint too shallow/small —
            # e.g. after the building was scaled down) should still satisfy a "more daylight"
            # intent by REDUCING DEPTH instead of just failing. Same goal, works on small
            # footprints. Only triggers when courtyard genuinely failed.
            if op == "courtyard" and not r.get("ok") and not r.get("already"):
                try:
                    rd = ai.reduce_depth(working_boundary, working_holes)
                    if rd.get("ok"):
                        r = rd
                        op = "reduce_depth"
                        text = "shallower floor plates for daylight (courtyard didn't fit)"
                except Exception:  # noqa: BLE001
                    pass
            if not r.get("ok"):
                applied_results.append({"text": text, "op": op, "accepted": False,
                                        "reason": r.get("reason", "operation failed")})
                continue
            # Validate against the BUILDABLE area (site minus setback) so a rotated/grown
            # footprint can never poke past the boundary OR into the setback zone.
            # align_facade rotates (corners can sweep out) so it's ALWAYS checked, not
            # just when it grows.
            grows = (op in ("lengthen", "align_facade")
                     or (op in ("stretch", "compress") and float(transform.get("factor", 1)) > 1)
                     or (op == "wing" and (transform.get("factor", 1) > 1)))
            if grows and not _ring_fits_site(r["outer"], buildable_boundary):
                _why = ("aligning the facade would rotate the building past the setback/site edge"
                        if op == "align_facade" else
                        "that change would extend past the setback / site boundary")
                applied_results.append({"text": text, "op": op, "accepted": False,
                                        "reason": _why,
                                        # NOTE: explicitly do NOT shrink as a fallback — an
                                        # align/orient request must never silently rescale the
                                        # building. Tell the user instead.
                                        "suggestion": "make the building smaller first, then align"})
                continue
            working_boundary = r["outer"]
            working_holes = r.get("holes", working_holes)
            holes_changed = True
            # Any whole-footprint reshape (align/stretch/compress/articulate/chamfer)
            # must rebuild the plate stack so every floor follows the new footprint —
            # else the per-plate viewer keeps drawing the old shape.
            if op in ("align_facade", "stretch", "compress", "articulate_facade", "chamfer") and working_plates:
                # Transform the EXISTING plates to follow the new footprint instead of
                # rebuilding from scratch — rebuilding dropped each plate's
                # wing_footprints, so afterwards "add floors on the <wing>" failed ("No
                # '<wing>' wing") and the added floors rendered as a detached block.
                # _retransform_plates carries wing_footprints through the transform.
                working_plates = _retransform_plates(working_plates, old_b_for_op, working_boundary)
                plates_changed = True
            applied_results.append({"text": text, "op": op, "accepted": True,
                                    "modified_part": "building", "result": r.get("reason", "applied")})
            continue

        # Absolute floor target ("make it 20 floors") → convert to a delta against the
        # current count, then fall through to the same plate-rebuild as a relative add.
        if op == "set_floors":
            target = max(1, int(transform["floors"]))
            transform = {"floors": target - current_floors}
            op = "floors"

        if op == "floors":
            from ..notebook_logic import floor_plates as fpl

            fh = floor_height or DEFAULT_FLOOR_HEIGHT_M
            delta = int(transform["floors"])
            plate_src = dict(bld)
            plate_src["boundary"] = working_boundary
            plates = working_plates if working_plates else fpl.ensure_floor_plates(plate_src)

            # SELECTED-PART targeting (spec #4): if a wing/tower/central mass is selected,
            # add the floors ONLY to that wing's plates — never the whole building.
            if target_role and plates:
                r = fpl.add_floors(plates, delta, wing=target_role, floor_height=fh)
                if not r.get("ok"):
                    applied_results.append({"text": text, "op": op, "accepted": False,
                                            "reason": r.get("reason", f"could not add floors to {target_name}"),
                                            "modified_part": None})
                    continue
                working_plates = r["floor_plates"]
                plates_changed = True
                current_floors = len(working_plates)
                current_height = round(max((p["z_base"] + p["height"]) for p in working_plates), 1)
                floors_changed = True
                applied_results.append({"text": text, "op": op, "accepted": True,
                                        "modified_part": target_role,
                                        "result": f"added {delta} floors to {target_name}"})
                continue

            # Whole-building path (no part selected).
            new_floors = max(1, current_floors + delta)
            current_height = round(new_floors * fh, 1)
            delta = new_floors - current_floors
            current_floors = new_floors
            floors_changed = True
            if delta != 0 and plates:
                r = fpl.add_floors(plates, delta, floor_height=fh)
                if r.get("ok"):
                    working_plates = r["floor_plates"]
                    plates_changed = True
            elif not plates:
                working_plates = fpl.build_floor_plates(working_boundary, new_floors, floor_height=fh, wings=bld.get("wings"))
                plates_changed = True
            applied_results.append({"text": text, "op": op, "accepted": True,
                                    "modified_part": "building",
                                    "result": f"floors -> {current_floors} (height {current_height} m)"})
            continue

        # --- Floor-plate ops: per-floor geometry (move a level range, raise one wing) ---
        if op in ("floor_move", "floor_add_wing"):
            from ..notebook_logic import floor_plates as fpl

            plate_src = dict(bld)
            plate_src["boundary"] = working_boundary
            plate_src["floors"] = current_floors
            plate_src["height_m"] = current_height
            plates = working_plates if working_plates else fpl.ensure_floor_plates(plate_src)

            if op == "floor_move":
                sel = transform.get("select", {})
                levels = fpl.select_levels(plates, bottom=sel.get("bottom"), top=sel.get("top"))
                dvec = fpl.DIRECTION_VECTORS if hasattr(fpl, "DIRECTION_VECTORS") else None
                from ..notebook_logic.feedback_reasoning import DIRECTION_VECTORS
                ux, uy = DIRECTION_VECTORS.get(transform["direction"], (0.0, 0.0))
                dist = float(transform.get("distance_m", 8.0))
                r = fpl.move_levels(plates, levels, ux * dist, uy * dist, site_boundary=site_boundary)
            else:  # floor_add_wing
                r = fpl.add_floors(plates, int(transform["floors"]), wing=transform.get("wing"))

            if not r.get("ok"):
                applied_results.append({"text": text, "op": op, "accepted": False,
                                        "reason": r.get("reason", "floor operation failed"),
                                        "suggestion": r.get("suggestion")})
                continue
            working_plates = r["floor_plates"]
            plates_changed = True
            # Keep the summary (floors/height/base footprint) consistent with the stack.
            summ = fpl.plates_to_summary(working_plates)
            current_floors = summ.get("floors", current_floors)
            current_height = summ.get("height_m", current_height)
            if summ.get("footprint"):
                working_boundary = summ["footprint"]
            floors_changed = True
            applied_results.append({"text": text, "op": op, "accepted": True,
                                    "result": r.get("note") or f"{op} applied ({current_floors} floors)"})
            continue
        if op == "height":
            current_height = round(current_height * float(transform["height_factor"]), 1)
            current_floors = max(1, int(round(current_height / (floor_height or DEFAULT_FLOOR_HEIGHT_M))))
            floors_changed = True
            applied_results.append({"text": text, "op": op, "accepted": True,
                                    "result": f"height -> {current_height} m ({current_floors} floors)"})
            continue

        # Footprint op (move / rotate / scale) — shared backend + validation.
        old_boundary = list(working_boundary)
        res = _apply_footprint_transform(geometry_id, working_boundary, transform, site_boundary)
        if res["accepted"]:
            working_boundary = res["boundary"]
            # Apply the SAME affine transform to every plate footprint so the floors
            # follow the moved/rotated/scaled boundary AND keep per-wing differences.
            # Without this the boundary moved but the plates stayed put — the gap/seam
            # between the floor stack and the facade.
            if working_plates:
                working_plates = _retransform_plates(working_plates, old_boundary, working_boundary)
                plates_changed = True
            # CRITICAL: the courtyard/patio HOLES must follow the same move/rotate/scale,
            # or the carved void detaches from the building (stays at its old spot while
            # the mass moves). Infer the transform from old→new boundary (rotation +
            # centroid shift + scale) and apply it to each hole — same proven approach as
            # _retransform_plates, so holes track the facade exactly regardless of op order.
            if working_holes:
                working_holes = _retransform_rings(working_holes, old_boundary, working_boundary)
                holes_changed = True
            applied_results.append({"text": text, "op": op, "accepted": True})
        else:
            # Skip the step (keep the last valid footprint) and report why.
            applied_results.append({"text": text, "op": op, "accepted": False,
                                    "reason": res.get("reason", "would leave the site boundary")})

    any_geom_applied = any(
        r["accepted"] and r["op"] in (
            "move", "rotate", "scale", "courtyard", "patio", "lengthen",
            "reduce_depth", "wing", "floor_move", "floor_add_wing", "align_facade",
            "place_corner", "place_edge", "place_center", "stretch", "compress",
            "articulate_facade", "chamfer", "twist", "taper", "context_place",
        )
        for r in applied_results
    )

    # 5: persist whatever was accepted (outer boundary + courtyard/patio holes +
    #    per-floor plate stack).
    bld["boundary"] = working_boundary
    if holes_changed:
        bld["holes"] = working_holes
        # CRITICAL: the 3D viewer renders the FLOOR PLATES, not building.holes. So a
        # courtyard/patio void must also be written into EACH plate's `holes`, otherwise
        # the void is in the data but every floor renders SOLID (the "I can't see the
        # courtyard" bug). Apply the same hole rings to every plate. (Restored to the
        # original gated behaviour — the unconditional re-sync/clear variant was dropping
        # the courtyard in some move→reshape flows.)
        if working_plates:
            _hcopy = [[list(pt) for pt in ring] for ring in (working_holes or [])]
            for _p in working_plates:
                _p["holes"] = [[list(pt) for pt in ring] for ring in _hcopy]
            plates_changed = True
    if floors_changed:
        bld["floors"] = current_floors
        bld["height_m"] = current_height
    if plates_changed:
        bld["floor_plates"] = working_plates

    # VALIDATE + SELF-DEBUG (additive guard): after a geometry op, deterministically
    # check the result is valid on the site (inside boundary, within setback, no
    # overlap, holes inside). If invalid, try a bounded corrective fix; if that still
    # fails, REVERT this op's geometry instead of persisting a broken shape — same
    # philosophy as the hallucination guard. Fully wrapped so any error falls back to
    # the previous behaviour (persist as-is) and never breaks the manipulation flow.
    validation_report: dict[str, Any] | None = None
    self_debug_log: list[str] = []
    try:
        from ..notebook_logic import design_debug as _dbg

        _site = state.get("site_boundary")
        if _site and len(_site) >= 3 and working_boundary and len(working_boundary) >= 3:
            _others = [b for b in placed if isinstance(b, dict) and b is not bld and _building_id(b) != geometry_id]
            _res = _dbg.run_self_debug(bld, _site, other_buildings=_others, max_attempts=3)
            validation_report = _res.get("verdict")
            self_debug_log = _res.get("log") or []
            if _res.get("ok"):
                # keep the (possibly corrected) geometry — carry any fixed boundary/holes.
                # If a corrective fix MOVED the footprint, re-sync the plate stack to the
                # new boundary so the 3D floors follow it (preserves the floor-plate model).
                _fixed = _res.get("building") or {}
                if _res.get("attempts", 0) > 0 and _fixed.get("boundary"):
                    _old_b = list(working_boundary)
                    bld["boundary"] = working_boundary = _fixed["boundary"]
                    if "holes" in _fixed:
                        bld["holes"] = working_holes = _fixed["holes"]
                    if plates_changed and working_plates:
                        try:
                            bld["floor_plates"] = working_plates = _retransform_plates(
                                working_plates, _old_b, working_boundary)
                        except Exception:  # noqa: BLE001
                            pass
            else:
                # Could not reach a valid geometry → REVERT this op so we never persist
                # a building that's outside the site / overlapping. The original snapshot
                # is restored from the pre-op building captured at request start.
                bld = dict(placed[idx])
                working_boundary = bld.get("boundary") or working_boundary
    except Exception:  # noqa: BLE001 — validation must never break the editing path
        validation_report = None

    placed[idx] = bld
    new_state = dict(state)
    new_state["placed_buildings"] = placed

    # VERIFICATION (spec #8/#10): which part actually changed, and does it match the
    # selected target? Compare per-wing floor counts before vs after.
    after_counts = _wing_floor_counts(bld)
    changed_wings = sorted(
        {w for w in set(before_counts) | set(after_counts)
         if before_counts.get(w, 0) != after_counts.get(w, 0)}
    )
    # The wing that actually received floors (strip the synthetic base marker).
    modified_part = next((w for w in changed_wings if w != "__base__"), None)
    if modified_part is None and changed_wings:
        modified_part = "building"  # whole-building change (base plates)
    # target_match: did we modify exactly the selected part?
    if target_role:
        target_match = (modified_part == target_role)
    else:
        target_match = True  # no specific part selected → any change is fine
    target_mismatch = bool(target_role) and modified_part is not None and not target_match

    # Decision tree: record a REASONING NODE for this manipulation — the Reason Node's
    # intent + confidence + WHY, plus the concrete ops applied. This is the "every
    # manipulation generates a reasoning node explaining WHY" requirement.
    if reason_node and (any_geom_applied or floors_changed or plates_changed):
        history = list(new_state.get("decision_history") or [])
        history.append({
            "stage": "editing",
            "action": "architectural_feedback",
            "input": body.feedback,
            "intent": reason_node["intent"],
            "confidence": reason_node["confidence"],
            "reasoning": reason_node["reasoning"],
            "actions_applied": [r["op"] for r in applied_results if r.get("accepted")],
        })
        new_state["decision_history"] = history

    # REAL change check (Fix 1): did the geometry ACTUALLY change vs the snapshot?
    after_sig = _geometry_signature(bld)
    geometry_changed = (after_sig != before_sig)

    # SELF-CORRECTION decision nodes (validate + self-debug). Recorded whenever the
    # geometry actually changed and we ran a validation pass — independent of whether a
    # reason_node fired — so the decision tree always shows the verify→debug loop.
    if geometry_changed and (validation_report is not None or self_debug_log):
        _hist = list(new_state.get("decision_history") or [])
        if self_debug_log and any("attempt" in str(s) for s in self_debug_log):
            _hist.append({
                "stage": "debug",
                "action": "self_debug",
                "input": body.feedback,
                "result": "self-corrected",
                "reasoning": "Manipulated geometry failed validation; auto-corrected it back into the site.",
                "self_debug_log": self_debug_log,
            })
        if validation_report is not None:
            _vfail = validation_report.get("failures") or []
            _hist.append({
                "stage": "validate",
                "action": "validate",
                "input": body.feedback,
                "result": "passed" if validation_report.get("passed") else f"failed: {', '.join(_vfail)}",
                "reasoning": ("All geometry checks passed." if validation_report.get("passed")
                              else f"Validation failures: {', '.join(_vfail)}."),
                "validation_report": validation_report,
            })
        new_state["decision_history"] = _hist

    # Hallucination guard (Fix 1): if the geometry changed but NO recognized layer
    # understood the prompt, the change came only from an LLM guess on unrecognized
    # input — reject it so we don't claim success for nonsense ("quantum flavored").
    # Recognized = literal parser / precise command / character classifier / a Reason
    # Node intent that MATCHED REAL PROMPT WORDS. Using matched keywords/synonyms (not
    # raw confidence) is the reliable discriminator: "more daylight"/"too compact"
    # match real words -> recognized; "quantum flavored" matches none -> NOT recognized
    # (so its LLM-guessed op is still rejected as a hallucination).
    reason_matched = bool(
        reason_node
        and (reason_node.get("matched_keywords") or reason_node.get("matched_synonyms"))
    )
    recognized = (
        literal_recognized
        or bool(character and character.get("operations"))
        or reason_matched
    )
    hallucinated = geometry_changed and not recognized
    if hallucinated:
        geometry_changed = False
        bld = dict(placed[idx])  # restore the original building (discard the LLM edit)

    # Only persist if something really changed — never silently overwrite with a no-op.
    if geometry_changed:
        # Record this manipulation on the building's history so a later "save as
        # option" captures the full edit lineage (Fix 3/4).
        try:
            from ..notebook_logic import shape_version_manager as svm

            op_name = next((r["op"] for r in applied_results if r.get("accepted")), "edit")
            svm.record_manipulation(bld, prompt=body.feedback, operation=op_name, target_part=target_role)
            new_state["placed_buildings"][idx] = bld
        except Exception:  # noqa: BLE001
            pass
        await store.update_state(session_id, new_state)

    # Build the spec's status envelope (Fix 2). The intent/operation come from the
    # Reason Node + the ops that ran; the reason/suggestion from the first rejected
    # action (or a sensible default) when nothing changed.
    accepted_ops = [r for r in applied_results if r.get("accepted")]
    rejected = [r for r in applied_results if not r.get("accepted")]
    # Prefer the 3-layer pipeline's canonical intent (semantic) when it classified the
    # prompt; fall back to the keyword reason_node / character category.
    intent = (
        (understanding or {}).get("intent")
        or (reason_node or {}).get("intent")
        or (character or {}).get("category")
        or "manipulation"
    )
    intent_label = (understanding or {}).get("intent_label") or intent
    intent_source = (understanding or {}).get("intent_source") or (
        "keyword" if reason_node else None
    )
    operation = (accepted_ops[0]["op"] if accepted_ops else (rejected[0]["op"] if rejected else "none"))
    # Human label of WHAT changed, for the "Updated building: ..." message. Prefer the
    # matched candidate's label; else describe the accepted op.
    _changed_label = ""
    if geometry_changed and understanding and understanding.get("candidates"):
        applied_phrase_ops = {r["op"] for r in accepted_ops}
        for c in understanding["candidates"]:
            cp = feedback_reasoning.parse_action(c["op_phrase"])
            if cp and cp.get("op") in applied_phrase_ops:
                _changed_label = c.get("label", "")
                break
    if geometry_changed and not _changed_label:
        _op_labels = {
            "courtyard": "carved a courtyard", "patio": "carved a patio",
            "reduce_depth": "reduced the mass depth", "lengthen": "extended the facade",
            "move": "repositioned the building", "rotate": "rotated the building",
            "scale": "rescaled the footprint", "floors": "changed the floor count",
            "set_floors": "set the floor count", "height": "adjusted the height",
            "align_facade": "aligned the facade", "place_corner": "placed at the corner",
            "place_edge": "placed at the edge", "place_center": "centred on the site",
            "stretch": "stretched the mass",
            "compress": "compressed the mass", "wing": "resized a wing",
            "articulate_facade": "articulated the facade", "chamfer": "chamfered corners",
            "twist": "twisted the stack", "taper": "tapered the stack",
            "floor_move": "moved floors", "floor_add_wing": "added floors to a wing",
        }
        _changed_label = ", ".join(
            dict.fromkeys(_op_labels.get(r["op"], r["op"]) for r in accepted_ops)
        ) or "updated the geometry"

    # "Already optimal" — a context placement (e.g. "move away from noise") resolved its
    # target but found the building is already at the best position. No geometry change,
    # but it is NOT a failure: report it honestly and positively, never a fake "Updated".
    already_reason = context_manip.get("already") if context_manip else None

    if geometry_changed:
        status = "success"
        reason = ""
        suggestion = ""
    elif already_reason:
        status = "no_change"
        reason = already_reason
        suggestion = ""
    else:
        status = "failed"
        # CONTEXT AVAILABILITY: a missing-context explanation takes priority — never
        # claim a generic failure when the real cause is unavailable context data.
        if context_manip and context_manip.get("missing"):
            reason = context_manip["missing"]
            suggestion = "select an edge/corner or regenerate urban context, then retry"
        # Prefer a concrete rejection reason; else explain the intent-without-op case.
        elif hallucinated:
            reason = ("I couldn't map that to a known architectural operation for this "
                      "shape")
            suggestion = ("rephrase it as a design intent - e.g. 'more daylight', 'add a "
                          "courtyard', 'make it taller', or a command like 'add 2 floors'")
        elif rejected:
            reason = rejected[0].get("reason") or "the requested change could not be applied"
            suggestion = rejected[0].get("suggestion") or "try a smaller amount or a different part"
        elif not parsed:
            reason = (f"I understood the intent as {intent}, but no concrete operation "
                      f"is available for this shape/prompt")
            suggestion = "try a specific command like 'add 2 floors', 'add courtyard', or 'scale 1.2'"
        else:
            # An align/orient that produced no rotation means the building is ALREADY
            # aligned — that's not a failure, so say so honestly instead of "failed".
            _ops_run = {r.get("op") for r in applied_results}
            if _ops_run & {"align_facade", "context_place"} and operation in ("align_facade", "context_place", "rotate"):
                reason = "the building is already aligned that way — no rotation was needed"
                suggestion = "rotate it off-axis first if you want to re-align, or pick a different direction"
            else:
                reason = "the operation ran but did not change the geometry"
                suggestion = "try a different amount or a different part"

    # Spec response rule: a single message line that NEVER says "Updated building"
    # unless geometry actually changed.
    if geometry_changed:
        message = f"Updated building: {_changed_label}."
    elif already_reason:
        # Positive, honest "no move needed" — not "Action failed".
        message = f"No change needed — {reason}"
    else:
        message = f"Action failed: {reason}. Try {suggestion}."

    return {
        # ---- Fix 2 status envelope ----
        "status": status,
        "message": message,
        # ---- 3-layer prompt-understanding report (spec: every response must include
        # detected intent, selected operation, target geometry, whether geometry
        # changed, validation result) ----
        "detected_intent": intent,
        "intent_label": intent_label,
        "intent_source": intent_source,
        "selected_operation": operation,
        "validation": "passed" if geometry_changed else "failed",
        # Deterministic geometry verdict from validate_design (+ any self-debug fixes
        # applied). None when there was no site to validate against.
        "validation_report": validation_report,
        "self_debug_log": self_debug_log,
        "understanding_layer": (understanding or {}).get("layer"),
        "intent": intent,
        "operation": operation,
        "target_part": target_role or "building",
        "geometry_changed": geometry_changed,
        "reason": reason if status in ("failed", "no_change") else (plan.get("reason") or ""),
        "suggestion": suggestion,
        "updated_geometry": {
            "boundary": working_boundary,
            "holes": working_holes,
            "floor_plates": bld.get("floor_plates"),
            "floors": bld.get("floors"),
            "height_m": bld.get("height_m"),
        } if geometry_changed else {},
        # ---- existing fields (kept for back-compat) ----
        "building_id": building_id,
        "feedback": body.feedback,
        "observations": plan.get("observations", []),
        "reasoning_source": plan.get("source"),
        "reason_node": reason_node,
        "character": character,
        "actions": applied_results,
        "metrics": metrics,
        "boundary": working_boundary,
        "holes": working_holes,
        "floors": bld.get("floors"),
        "height_m": bld.get("height_m"),
        "floor_plates": bld.get("floor_plates"),
        # `applied` now reflects the REAL geometry change, not just op flags.
        "applied": geometry_changed,
        "selected_part": target_role or "building",
        "selected_part_name": target_name,
        "modified_part": modified_part,
        "target_match": target_match,
        "target_mismatch": target_mismatch,
        "before_floor_counts": before_counts,
        "after_floor_counts": after_counts,
    }
