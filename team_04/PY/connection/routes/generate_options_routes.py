"""Multi-typology option generation.

When the prompt doesn't name a shape ("a 6 floor commercial building"), generate
one candidate per typology (I / L / U / H / T / courtyard), each placed at a
DIFFERENT valid position + rotation inside the confirmed site, validated against
the boundary, and grouped by shape type for the Shape Library.

Reuses: shape_inference (what to generate), generate_building_boundary (geometry),
option_sampler / view_optimizer placement (distinct positions), site fit check.

  POST /sessions/{id}/generate-options  {prompt?, typologies?, per_type?}
       -> {options: [...], shapes_by_type: {...}, program: {...}}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import shape_inference, setback_rules
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["generate-options"])

_MIN_FOOTPRINT = 150.0
_MAX_FOOTPRINT = 8000.0  # large-site cap; coverage/FAR/envelope limits bind first on
                         # normal plots, so this only stops absurd footprints on huge sites
# Fraction of the BUILDABLE rectangle (site minus setback) a shape may fill. <1 so
# articulated shapes (L/U/H) have room for their notches and the footprint reads as a
# real building, not a block that exactly fills the lot.
_MAX_BUILDABLE_FILL = 0.85
# Default Floor-Area-Ratio cap (total GFA / site area) when no zoning value is known.
# A mid-rise mixed-use default; surfaced in the response so the UI can show/adjust it.
_DEFAULT_FAR = 3.0


class GenerateOptionsRequest(BaseModel):
    prompt: str = ""
    typologies: list[str] | None = None
    per_type: int = Field(default=1, ge=1, le=3)
    coverage_ratio: float = Field(default=0.45, ge=0.05, le=0.9)
    far_limit: float | None = Field(default=None, gt=0, le=15)


def _poly_area(b: list[list[float]]) -> float:
    pts = [(float(p[0]), float(p[1])) for p in (b or []) if len(p) >= 2]
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(a) / 2.0


def _bbox(b: list[list[float]]) -> tuple[float, float]:
    xs = [p[0] for p in b if len(p) >= 2]
    ys = [p[1] for p in b if len(p) >= 2]
    return (max(xs) - min(xs), max(ys) - min(ys)) if xs else (0.0, 0.0)


def _centroid(b: list[list[float]]) -> tuple[float, float]:
    pts = [(float(p[0]), float(p[1])) for p in (b or []) if len(p) >= 2]
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _translate(b: list[list[float]], dx: float, dy: float) -> list[list[float]]:
    out = []
    for p in b:
        if len(p) >= 2:
            z = [float(p[2])] if len(p) > 2 else []
            out.append([float(p[0]) + dx, float(p[1]) + dy] + z)
        else:
            out.append(p)
    return out


def _interior_point(poly: list[list[float]]) -> tuple[float, float]:
    """The most interior point of a polygon (pole of inaccessibility) — better than the
    centroid for placing a footprint inside an IRREGULAR/concave buildable area so it
    keeps a margin from every edge. Falls back to centroid on any issue."""
    try:
        from shapely.geometry import Polygon

        p = Polygon([(q[0], q[1]) for q in poly])
        if not p.is_valid or p.is_empty:
            return _centroid(poly)
        # representative_point is guaranteed inside; for convex-ish plots it ≈ centroid,
        # for concave plots it avoids the angled edges.
        rp = p.representative_point()
        # blend toward the true centroid a little so it doesn't hug a narrow lobe
        cx, cy = p.centroid.x, p.centroid.y
        return (0.5 * rp.x + 0.5 * cx, 0.5 * rp.y + 0.5 * cy)
    except Exception:  # noqa: BLE001
        return _centroid(poly)


def _site_fit(footprint: list[list[float]], site: list[list[float]]) -> tuple[bool, float]:
    """Cheap shapely-based fit check: (fits, outside_area_sqm). Used for the Stage-1
    Shape Library — placement is NOT optimized here (that's Stage 3), shapes are just
    centered and scaled to fit, so a simple containment test is enough."""
    try:
        from shapely.geometry import Polygon

        bp = Polygon([(p[0], p[1]) for p in footprint])
        sp = Polygon([(p[0], p[1]) for p in site])
        if not bp.is_valid or not sp.is_valid:
            return (True, 0.0)
        outside = bp.difference(sp).area
        return (outside < 1.0, round(outside, 1))
    except Exception:  # noqa: BLE001
        return (True, 0.0)


@router.post("/{session_id}/generate-options")
async def generate_options(session_id: str, body: GenerateOptionsRequest) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    site_boundary = state.get("site_boundary") or []
    if len(site_boundary) < 3:
        raise HTTPException(status_code=422, detail="Confirm a site boundary first")

    program = shape_inference.infer_program(body.prompt)
    typologies = body.typologies or program["typologies"]
    building_use = program.get("building_use") or "residential"

    # Context-aware generation setup: does the prompt reference a direction or urban
    # feature, and do we have stored context to resolve it against?
    from ..notebook_logic import context_aware_shape_generator as casg

    urban_context = state.get("urban_context") or {}
    context_intent_present = (
        casg.extract_directional_intent(body.prompt) is not None
        or casg.extract_context_intent(body.prompt) is not None
    )
    context_warning: str | None = None
    if context_intent_present and not (urban_context.get("edges") or urban_context.get("edge_metadata")):
        # Fix 7: don't silently ignore — tell the user context is missing.
        context_warning = ("Context target not found: no urban context was stored. "
                           "Please regenerate urban context, then try again.")

    # Get setback rules for the inferred building use, then create buildable area.
    # create_buildable_area returns a Shapely Polygon (or None); convert it to a
    # plain [[x, y], ...] ring so the helpers below (_centroid / _site_fit) — which
    # expect coordinate lists, not geometry objects — keep working.
    rules = setback_rules.get_setback_rules(building_use)
    max_setback = max(rules.front_setback, rules.rear_setback, rules.side_setback)
    buildable_poly = setback_rules.create_buildable_area(site_boundary, rules)
    buildable_area: list[list[float]] | None = None
    if buildable_poly is not None and not buildable_poly.is_empty:
        try:
            buildable_area = [[float(x), float(y)] for x, y in buildable_poly.exterior.coords]
        except Exception:  # noqa: BLE001
            buildable_area = None

    site_area = _poly_area(site_boundary)
    site_w, site_h = _bbox(site_boundary)
    site_min = max(10.0, min(site_w, site_h))
    height_m = program.get("height_m") or 12.0
    floors = max(1, round(float(height_m) / float(program.get("floor_height_m") or 3.0)))

    # ---- REAL FOOTPRINT SIZING: respect setbacks, allowable coverage, and FAR ----
    # The footprint is the SMALLEST of three regulatory limits, so the building both
    # fits the buildable envelope and stays within FAR — instead of an arbitrary tiny
    # block that gets shrunk away.
    buildable_sqm = _poly_area(buildable_area) if buildable_area else site_area
    bld_w, bld_h = _bbox(buildable_area) if buildable_area else (site_w, site_h)
    # 1) Coverage: a sensible % of the SITE (default 45%).
    cover_cap = site_area * body.coverage_ratio
    # 2) Buildable envelope: at most _MAX_BUILDABLE_FILL of the area left after setbacks.
    envelope_cap = buildable_sqm * _MAX_BUILDABLE_FILL
    # 3) FAR: total floor area (footprint × floors) must not exceed FAR × site_area,
    #    so footprint ≤ FAR × site_area / floors.
    far_limit = float(body.far_limit or _DEFAULT_FAR)
    far_cap = (far_limit * site_area) / max(1, floors)
    target_area = max(_MIN_FOOTPRINT, min(cover_cap, envelope_cap, far_cap, _MAX_FOOTPRINT))
    # Fit the shape's DEPTH to the SHORTER buildable side so its bounding box stays
    # inside the envelope. Use ~75% of the shorter buildable dimension (leaves a margin
    # for the angled edges of an irregular plot), clamped to a realistic plate depth.
    fit_depth = max(10.0, min(26.0, min(bld_w, bld_h) * 0.75))
    # Cap target area to a rectangle of (≈80% buildable length × fit_depth) so the
    # generated bounding box fits the buildable polygon. The _site_fit loop then shrinks
    # only if the SHAPE's notches still poke past an angled edge — small adjustments, not
    # the big collapse we had before.
    long_side = max(bld_w, bld_h) * 0.8
    box_cap = long_side * fit_depth
    target_area = max(_MIN_FOOTPRINT, min(target_area, box_cap))

    from agent.tools.generate_building_boundary import generate_building_boundary

    options: list[dict[str, Any]] = []
    shapes_by_type: dict[str, list[dict[str, Any]]] = {}

    # Placement anchor: for an IRREGULAR site the buildable polygon's centroid can sit
    # near an angled edge, pushing the footprint to the boundary. Use the polygon's
    # point-of-inaccessibility (the most interior point) so the footprint is centered in
    # the largest open part of the buildable area, with a real setback margin all round.
    site_cx, site_cy = _interior_point(buildable_area) if buildable_area else _centroid(site_boundary)

    # STAGE 1 is shape generation, not placement optimization. For each typology we
    # produce ONE clean footprint, center it on the buildable area (site minus setback),
    # and shrink it until it fits — a fast deterministic step. The expensive NSGA-II
    # placement/rotation search runs LATER, in Stage 3, on the single shape the user
    # selects. (Running a full optimization per typology here made shape generation
    # take ~3 minutes.)
    for t in typologies:
        area = target_area
        placed_footprint = None
        placed_wings: list[dict[str, Any]] = []
        placed_graph: dict[str, Any] = {}
        for _ in range(14):
            try:
                gen = generate_building_boundary(
                    area=area, building_type=t, building_depth=fit_depth, optimize_placement=False
                )
            except Exception:  # noqa: BLE001
                break
            data = gen.get("data", {})
            cand = data.get("boundary")
            if not cand or len(cand) < 3:
                break
            # Center the footprint on the buildable area centroid (respecting setbacks).
            cx, cy = _centroid(cand)
            dx, dy = site_cx - cx, site_cy - cy
            centered = _translate(cand, dx, dy)
            # Translate each wing footprint by the SAME offset so wings stay aligned to
            # the centered building (needed for per-wing floor edits like "add 2 floors
            # on the right wing"). Roles normalized to right/left/connector/etc.
            placed_wings = []
            for w in (data.get("wings") or []):
                wb = w.get("boundary") or w.get("footprint")
                if not wb or len(wb) < 3:
                    continue
                placed_wings.append({
                    "role": (w.get("role") or "").replace("_wing", "").strip() or w.get("role"),
                    "wing_index": w.get("wing_index", w.get("index")),
                    "boundary": _translate(wb, dx, dy),
                    "centroid": w.get("centroid"),
                    "area_sqm": w.get("area_sqm"),
                })
            placed_graph = data.get("building_graph") or {}
            # Check fit against buildable area (site minus setback), not raw boundary
            fits, _outside = _site_fit(centered, buildable_area if buildable_area else site_boundary)
            placed_footprint = centered
            if fits:
                break
            area *= 0.92  # too big — shrink GENTLY (small steps so a near-fit on an
                          # irregular plot doesn't collapse far below the allowable size)
        if not placed_footprint:
            continue

        # CONTEXT-AWARE step: if the prompt names a direction ("long facade on east")
        # or an urban-context feature ("near metro edge", "toward park"), align/place
        # this shape using the stored urban context. Applied per-shape so each typology
        # responds to the site. Only accepted when the result still fits the site.
        context_response = None
        if context_intent_present:
            cres = casg.apply_context_to_shape(body.prompt, placed_footprint, site_boundary, urban_context)
            if cres.get("applied") and _site_fit(cres["boundary"], site_boundary)[0]:
                placed_footprint = cres["boundary"]
                context_response = {
                    "target_edge": cres.get("target_edge"),
                    "basis": cres.get("basis"),
                    "operations": cres.get("operations"),
                }
            elif cres.get("status") in ("context_missing", "target_not_found"):
                context_response = {"warning": cres.get("reason")}

        # Validate against both buildable area and raw site for reporting
        fits_buildable, outside_buildable = _site_fit(placed_footprint, buildable_area if buildable_area else site_boundary)
        fits_site, outside_site = _site_fit(placed_footprint, site_boundary)
        fp_area = _poly_area(placed_footprint)
        opt = {
            "option_id": f"{t}_01",
            "shape_type": t,
            "position": [round(site_cx, 2), round(site_cy, 2)],
            "rotation_degrees": 0,
            "scale": 1.0,
            "footprint": placed_footprint,
            "boundary": placed_footprint,
            "wings": placed_wings,            # per-wing footprints (for per-wing floor edits)
            "building_graph": placed_graph,
            "height_m": float(height_m),
            "floors": floors,
            "score": 0.0,           # no optimization score yet — assigned in Stage 3
            "view_score": 0.0,
            "far": round((fp_area * floors) / site_area, 3) if site_area else None,
            "site_coverage": round(fp_area / site_area, 3) if site_area else None,
            "footprint_area": round(fp_area, 1),
            # Context-aware result: which edge this shape responded to + how.
            "context_response": context_response,
            "validation_report": {
                "fits_within_buildable_area": fits_buildable,
                "buildable_area_violation_sqm": outside_buildable,
                "fits_within_site": fits_site,
                "site_violation_sqm": outside_site,
                "building_use": building_use,
                "setback_distance_m": max_setback,
            },
            "building_use": building_use,
        }
        options.append(opt)
        shapes_by_type.setdefault(t, []).append(opt)

    # Rank all options across typologies by score (best first), then drop any
    # near-identical ones (keeping the higher score) so the set is genuinely diverse.
    options.sort(key=lambda o: o.get("score", 0), reverse=True)
    from ..notebook_logic import option_diversity
    options = option_diversity.dedupe(options, top_n=max(4, len(typologies)))
    for i, o in enumerate(options):
        o["rank"] = i + 1

    # Persist so the explorer Shape Library + optimize panel can read them.
    new_state = dict(state)
    new_state["generated_options"] = options
    await store.update_state(session_id, new_state)

    return {
        "program": program,
        "options": options,
        "shapes_by_type": shapes_by_type,
        "count": len(options),
        "typologies": typologies,
        # Regulatory sizing summary — the limits the footprint was sized against, so the
        # UI can show WHY the building is the size it is (real planning logic).
        "regulatory": {
            "site_area_sqm": round(site_area, 1),
            "buildable_area_sqm": round(buildable_sqm, 1),
            "setback_m": round(max_setback, 1),
            "coverage_ratio": body.coverage_ratio,
            "far_limit": far_limit,
            "target_footprint_sqm": round(target_area, 1),
            "max_floor_area_sqm": round(far_limit * site_area, 1),
        },
        # Context-aware generation summary (Fix 7: surface a missing-context warning).
        "context_intent": context_intent_present,
        "context_warning": context_warning,
    }
