"""Session optimization route — run the REAL view_optimizer pipeline on a placed
building and return the top-ranked options with full metrics.

This is the backend optimization the frontend Optimization stage calls. It uses
the EXISTING analysis logic validated in test_view_analysis.ipynb — no arbitrary
variations are generated:

  view_optimizer.optimize_view_placement   (NSGA-II over placement + shape morph)
  view_optimizer objective registry         (unblocked/attractor view, clearance…)
  site_setback.setback_summary              (setback compliance)

Each returned option carries: score, objective breakdown, setback compliance,
view score, site coverage, FAR, height, floors, placement metadata, reasoning.

  POST /sessions/{id}/optimize
       {building_id?, saved_option_count?, population_size?, generation_count?,
        objective_configs?, optimize_shape?}
       -> {options: [...enriched...], objective_names, site_area_sqm}
"""
from __future__ import annotations

import copy
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import option_diversity, view_optimization_runtime as vo
from ..notebook_logic.agent_runtime import parse_program
from ..notebook_logic import optimization_constraints as oc
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["session-optimize"])

DEFAULT_FLOOR_HEIGHT_M = 3.0


class OptimizeSessionRequest(BaseModel):
    building_id: str | None = None
    saved_option_count: int = Field(default=4, ge=1, le=20)
    # Kept modest so a single interactive optimize returns in a few seconds.
    population_size: int = Field(default=24, ge=10, le=200)
    generation_count: int = Field(default=24, ge=10, le=400)
    # Fixed-shape placement optimization by default (fast, reliable ranked options);
    # shape morphing is opt-in via the request since it roughly doubles runtime.
    optimize_shape: bool = False
    objective_configs: list[dict[str, Any]] | None = None
    random_seed: int = 7
    # Fix 5: "current" optimizes the live building only; "all_saved" runs over every
    # saved Shape Library version, retaining each shape's geometry and optimizing only
    # its placement/rotation/score.
    optimize_scope: str = "current"


def _building_id(bld: dict[str, Any]) -> str:
    return str(bld.get("building_id") or bld.get("geometry_id") or id(bld))


def _bbox_extent(boundary: list[list[float]]) -> tuple[float, float]:
    pts = [p for p in boundary if isinstance(p, (list, tuple)) and len(p) >= 2]
    if not pts:
        return 0.0, 0.0
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    return max(xs) - min(xs), max(ys) - min(ys)


def _poly_area(boundary: list[list[float]]) -> float:
    if not boundary or len(boundary) < 3:
        return 0.0
    pts = [(float(p[0]), float(p[1])) for p in boundary if len(p) >= 2]
    a = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(a) / 2.0


def _normalize_for_sampling(boundary: list[list[float]], site_min_dim: float) -> dict | None:
    """Un-rotate a MANIPULATED footprint to axis-aligned + center it at the origin so
    the placement sampler can fit it, WITHOUT changing its shape. Returns the
    normalized ring + the transform params (so holes can be moved the same way).
    The optimizer then re-rotates/re-positions this preserved shape itself."""
    import math

    pts = [(float(p[0]), float(p[1])) for p in boundary if len(p) >= 2]
    if len(pts) < 3:
        return None
    cx0 = sum(p[0] for p in pts) / len(pts)
    cy0 = sum(p[1] for p in pts) / len(pts)
    # Find the longest edge angle and rotate it to horizontal (axis-aligned).
    longest, ang = 0.0, 0.0
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d > longest:
            longest, ang = d, math.atan2(b[1] - a[1], b[0] - a[0])
    rotate_deg = -math.degrees(ang)
    ca, sa = math.cos(math.radians(rotate_deg)), math.sin(math.radians(rotate_deg))
    rotated = [[(p[0] - cx0) * ca - (p[1] - cy0) * sa, (p[0] - cx0) * sa + (p[1] - cy0) * ca] for p in pts]
    # Re-center at origin.
    rcx = sum(p[0] for p in rotated) / len(rotated)
    rcy = sum(p[1] for p in rotated) / len(rotated)
    centered = [[p[0] - rcx, p[1] - rcy] for p in rotated]
    return {"boundary": centered, "rotate_deg": rotate_deg, "cx0": cx0, "cy0": cy0,
            "dx": -rcx, "dy": -rcy}


def _rotate_translate_ring(ring, rotate_deg, cx0, cy0, dx, dy):
    """Apply the same normalize transform (rotate about (cx0,cy0), then translate) to a
    hole ring so it stays registered to the normalized footprint."""
    import math

    ca, sa = math.cos(math.radians(rotate_deg)), math.sin(math.radians(rotate_deg))
    out = []
    for p in ring:
        x, y = float(p[0]) - cx0, float(p[1]) - cy0
        rx, ry = x * ca - y * sa, x * sa + y * ca
        out.append([rx + dx, ry + dy])
    return out


def _default_objectives(
    site_boundary: list[list[float]], directives: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """A balanced multi-objective config so the optimizer returns a varied front.
    The longest site edge is used as a view attractor (a common 'face the street'
    heuristic).

    CONTEXT-AWARE: when the Urban Context stage produced design directives, the
    objective weights shift so the optimization responds to the surrounding city:
      * preserve_views (high green-space context)  -> weight unblocked views higher
      * activate_street_edges (high retail context) -> weight the street attractor higher
      * density_bias (high transit context)         -> relax clearance to allow denser fit
    """
    attractors: list[dict[str, Any]] = []
    pts = [p for p in site_boundary if isinstance(p, (list, tuple)) and len(p) >= 2]
    if len(pts) >= 2:
        longest = None
        best_len = -1.0
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            length = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            if length > best_len:
                best_len = length
                longest = [[float(a[0]), float(a[1]), 0.0], [float(b[0]), float(b[1]), 0.0]]
        if longest:
            attractors = [{"type": "line", "geometry": longest}]

    d = directives or {}
    w_view = 0.5
    w_attr = 0.3
    w_clear = 0.2
    if d.get("preserve_views"):
        w_view, w_attr, w_clear = 0.6, 0.25, 0.15
    if d.get("activate_street_edges"):
        w_attr += 0.1
        w_view -= 0.05
        w_clear = max(0.1, w_clear - 0.05)
    if d.get("density_bias", 0) >= 0.2:
        # denser context → care less about clearance, more about views/street
        w_clear = max(0.1, w_clear - 0.05)
        w_view += 0.05
    total = w_view + w_attr + w_clear
    return [
        {"name": "unblocked_view", "weight": round(w_view / total, 3)},
        {"name": "attractor_view", "weight": round(w_attr / total, 3), "attractors": attractors},
        {"name": "clearance_from_site", "weight": round(w_clear / total, 3)},
    ]


@router.post("/{session_id}/optimize")
async def optimize_session(session_id: str, body: OptimizeSessionRequest) -> dict[str, Any]:
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    placed = state.get("placed_buildings", []) or []
    if not placed:
        raise HTTPException(status_code=422, detail="No building to optimize — generate one first.")

    if body.building_id:
        bld = next((b for b in placed if isinstance(b, dict) and _building_id(b) == body.building_id), None)
        if bld is None:
            raise HTTPException(status_code=404, detail="Building not found")
    else:
        bld = placed[0]

    boundary = bld.get("boundary") or bld.get("building_boundary")
    if not boundary:
        raise HTTPException(status_code=422, detail="Building has no boundary")
    site_boundary = state.get("site_boundary") or None
    if not site_boundary:
        raise HTTPException(status_code=422, detail="Session has no site boundary")

    building_type = bld.get("building_type") or bld.get("shape_type") or "L"

    # The placed building's boundary is already rotated/positioned, which gives it a
    # large axis-aligned bounding box that the placement sampler cannot fit anywhere
    # (→ 0 options). We need a centered, unrotated footprint to OPTIMIZE PLACEMENT of.
    #
    # IMPORTANT: if the user MANIPULATED the shape (carved a courtyard / holes, edited
    # the footprint, etc.), we must keep THAT geometry — only normalize its orientation
    # and position. We regenerate a clean typology ONLY for a plain, unedited shape
    # (which is geometrically identical to the generator's output anyway). This is what
    # makes optimization run on the manipulated shape, not the original.
    footprint_area = _poly_area(boundary) or 800.0
    safe_type = building_type if building_type in {"I", "L", "U", "T", "H", "X", "Y", "O"} else "L"
    site_w, site_h = _bbox_extent(site_boundary)
    site_min_dim = max(10.0, min(site_w, site_h))

    is_manipulated = bool(
        bld.get("holes")
        or (bld.get("manipulation_history"))
        or bld.get("source_shape_option_id")  # a saved/selected version
    )
    optimize_holes = [list(h) for h in (bld.get("holes") or [])]
    # The MANIPULATED plate stack (twist/taper sculpting + per-wing added floors) lives
    # in floor_plates. The optimizer must carry THIS forward — otherwise every optimized
    # option is a flat re-extrusion of the footprint and the futuristic shape / added
    # floors vanish. We normalize each plate's rings alongside the boundary below, then
    # re-place the whole stack into each placement candidate.
    optimize_plates = copy.deepcopy(bld.get("floor_plates") or [])

    if is_manipulated:
        # Preserve the manipulated footprint + holes — just normalize orientation
        # (un-rotate to axis-aligned) and center it so the placement sampler can fit it.
        normalized = _normalize_for_sampling(boundary, site_min_dim)
        if normalized:
            # translate holes by the same centering so they stay registered to the shape.
            dx, dy = normalized["dx"], normalized["dy"]
            ang = normalized["rotate_deg"]
            boundary = normalized["boundary"]
            optimize_holes = [_rotate_translate_ring(h, ang, normalized["cx0"], normalized["cy0"], dx, dy)
                              for h in optimize_holes]
            # Normalize the manipulated plate stack the SAME way (each plate's footprint
            # + per-wing rings) so it registers to the normalized boundary. Z stays as-is.
            for _pl in optimize_plates:
                if _pl.get("footprint"):
                    _pl["footprint"] = _rotate_translate_ring(
                        _pl["footprint"], ang, normalized["cx0"], normalized["cy0"], dx, dy)
                _wf = _pl.get("wing_footprints")
                if isinstance(_wf, dict):
                    _pl["wing_footprints"] = {
                        _k: _rotate_translate_ring(_v, ang, normalized["cx0"], normalized["cy0"], dx, dy)
                        for _k, _v in _wf.items() if _v
                    }
    else:
        # Plain unedited shape — regenerate a clean centered typology (same as before).
        try:
            from agent.tools.generate_building_boundary import generate_building_boundary

            area = footprint_area
            fresh_boundary = None
            for _ in range(6):
                fresh = generate_building_boundary(
                    area=area, building_type=safe_type, optimize_placement=False
                )
                cand = fresh.get("data", {}).get("boundary")
                if not cand or len(cand) < 3:
                    break
                bw, bh = _bbox_extent(cand)
                if max(bw, bh) <= site_min_dim * 0.9:
                    fresh_boundary = cand
                    break
                fresh_boundary = cand
                area *= 0.6
            if fresh_boundary and len(fresh_boundary) >= 3:
                boundary = fresh_boundary
        except Exception:  # noqa: BLE001 — fall back to the placed boundary if generation fails
            pass

    site_area = _poly_area(site_boundary)
    # Other placed buildings act as obstacles for view analysis.
    obstacles = [
        b.get("boundary")
        for b in placed
        if isinstance(b, dict) and b is not bld and b.get("boundary")
    ]
    obstacles = [ob for ob in obstacles if ob]

    # Program (floors/height/use) parsed from the original prompt, for FAR/floors.
    program = parse_program(str(state.get("user_prompt", "")))
    height_m = bld.get("height_m") or program.get("height_m") or 12.0
    floor_height = float(program.get("floor_height_m") or DEFAULT_FLOOR_HEIGHT_M)
    floors = max(1, round(float(height_m) / floor_height))

    # Default objectives: a multi-objective mix so the Pareto front has variety
    # (a single objective on an empty site collapses to one tied solution). The
    # nearest/longest site edge is used as a view attractor.
    context_directives = (state.get("urban_context") or {}).get("directives")
    objective_configs = body.objective_configs or _default_objectives(site_boundary, context_directives)

    # Ask the optimizer for MORE candidates than we'll show, so after de-duplicating
    # near-identical solutions we still have N genuinely distinct options to return.
    pool_count = min(20, max(body.saved_option_count * 3, body.saved_option_count + 4))

    def _run(optimize_shape: bool) -> dict[str, Any]:
        res = vo.optimize(
            boundary,
            obstacles=obstacles,
            site_boundary=site_boundary,
            building_type=building_type,
            optimize_shape=optimize_shape,
            objective_configs=objective_configs,
            saved_option_count=pool_count,
            population_size=body.population_size,
            generation_count=body.generation_count,
            random_seed=body.random_seed,
        )
        return res.get("data", res) if isinstance(res, dict) else res

    try:
        data = _run(body.optimize_shape)
        raw_options = data.get("pareto_solutions") or data.get("saved_options") or []
        # Shape morphing can over-constrain and return too few solutions. Fall back
        # to fixed-shape placement optimization so the user still gets ranked options.
        if body.optimize_shape and len(raw_options) < 2:
            data = _run(False)
            raw_options = data.get("pareto_solutions") or data.get("saved_options") or []
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Optimization failed: {exc}") from exc

    # Setback compliance (once per site).
    try:
        from agent.tools.site_setback import setback_summary

        setbacks = setback_summary(site_boundary)
        setback_ok = all(
            (row.get("setback_m", 0) or 0) >= (row.get("min_setback_m", 0) or 0)
            for row in setbacks
        ) if isinstance(setbacks, list) else True
    except Exception:  # noqa: BLE001
        setbacks, setback_ok = [], True

    # Get site context for constraint scoring
    site_latitude = state.get("site_latitude")
    site_longitude = state.get("site_longitude")
    context_edges = (state.get("urban_context") or {}).get("edges") or []

    # Load selected edge from edge state (user selected it on the map)
    import json
    import os as _os
    _edge_state_path = _os.path.join(
        _os.path.dirname(__file__), "..", "data", "selected_edge.json"
    )
    selected_edge_id = state.get("selected_edge_id")
    if not selected_edge_id and _os.path.exists(_edge_state_path):
        try:
            with open(_edge_state_path, encoding="utf-8") as fh:
                edge_state = json.load(fh)
                selected_edge_id = edge_state.get("edge_id")
        except (json.JSONDecodeError, OSError):
            pass

    options: list[dict[str, Any]] = []
    valid_options: list[dict[str, Any]] = []

    for i, opt in enumerate(raw_options):
        # deepcopy the raw solution so each option is an independent object (never a
        # shared reference — that was making options look identical downstream).
        opt = copy.deepcopy(opt)
        opt_boundary = opt.get("boundary") or boundary
        footprint = _poly_area(opt_boundary)
        far = round((footprint * floors) / site_area, 3) if site_area else None
        coverage = round(footprint / site_area, 3) if site_area else None
        fits = opt.get("fits_within_site", True)
        obj_scores = opt.get("objective_scores") or {}

        # Constraint validation: check if option is inside site boundary and buildable area
        try:
            validation = oc.validate_optimization_candidate(
                opt_boundary,
                site_boundary,
                building_type=building_type,
            )
            is_valid = validation.get("valid", False)
            if not is_valid:
                # Skip invalid options - do not include them in results
                continue
        except Exception:
            # If validation fails, assume option is invalid and skip
            is_valid = False
            validation = {"valid": False, "constraints": {}, "violations": []}

        # Score the option with constraint scoring
        constraint_scores = {}
        try:
            candidate = {
                "position": opt_boundary,
                "rotation": opt.get("rotation_degrees", 0),
            }
            score_result = oc.score_optimization_candidate(
                candidate,
                site_boundary,
                context_edges=context_edges,
                site_latitude=site_latitude,
                site_longitude=site_longitude,
                selected_edge_id=selected_edge_id,
            )
            constraint_scores = score_result.get("scores", {})
            constraint_total = score_result.get("total_score", 0)
        except Exception:
            constraint_scores = {
                "setback_score": 0,
                "sunlight_score": 50,
                "daylight_score": 50,
                "edge_attraction_score": 0,
                "road_access_score": 50,
                "open_space_score": 50,
                "density_score": 50,
            }
            constraint_total = 0

        reasons = []
        if opt.get("unblocked_view_score") is not None:
            reasons.append(f"unblocked view {opt['unblocked_view_score']:.2f}")
        if opt.get("attractor_view_score"):
            reasons.append(f"attractor view {opt['attractor_view_score']:.2f}")
        reasons.append(f"rotation {opt.get('rotation_degrees', 0)}°")
        if not fits:
            reasons.append("⚠ extends outside site")

        # Carry the manipulated holes (courtyard/patio) into THIS option by applying
        # the option's placement transform (rotate by rotation_degrees about origin,
        # then translate to its centroid) to the normalized holes — so the optimized
        # massing keeps the carved courtyard, not a solid block.
        opt_holes = []
        if optimize_holes and opt.get("centroid_xy"):
            import math as _math
            rot = _math.radians(opt.get("rotation_degrees", 0) or 0)
            ca, sa = _math.cos(rot), _math.sin(rot)
            ocx, ocy = opt["centroid_xy"][0], opt["centroid_xy"][1]
            for h in optimize_holes:
                opt_holes.append([[ocx + p[0] * ca - p[1] * sa, ocy + p[0] * sa + p[1] * ca] for p in h])

        # Carry the manipulated plate stack (twist/taper + added floors) into THIS view
        # option using the same placement transform, so these options don't flatten back
        # to a plain extrusion when they're folded into the multi-objective pool.
        opt_plates = []
        if optimize_plates and opt.get("centroid_xy"):
            import math as _math2
            _rot = _math2.radians(opt.get("rotation_degrees", 0) or 0)
            _ca, _sa = _math2.cos(_rot), _math2.sin(_rot)
            _ocx, _ocy = opt["centroid_xy"][0], opt["centroid_xy"][1]

            def _pring(r):
                return [[_ocx + p[0] * _ca - p[1] * _sa, _ocy + p[0] * _sa + p[1] * _ca] for p in r]

            for _pl in optimize_plates:
                _np = dict(_pl)
                if _pl.get("footprint"):
                    _np["footprint"] = _pring(_pl["footprint"])
                _wf = _pl.get("wing_footprints")
                if isinstance(_wf, dict):
                    _np["wing_footprints"] = {k: _pring(v) for k, v in _wf.items() if v}
                opt_plates.append(_np)

        option_dict = {
            "option_id": opt.get("option_id") or f"opt_{i + 1:02d}",
            "rank": opt.get("rank", i + 1),
            "shape_type": building_type,
            "boundary": opt_boundary,
            "holes": opt_holes,
            "floor_plates": opt_plates,
            "centroid_xy": opt.get("centroid_xy"),
            "rotation_degrees": opt.get("rotation_degrees", 0),
            # View Scores
            "score": opt.get("combined_score", 0.0),
            "combined_score": opt.get("combined_score", 0.0),
            "view_score": opt.get("unblocked_view_score", 0.0),
            "unblocked_view_score": opt.get("unblocked_view_score", 0.0),
            "attractor_view_score": opt.get("attractor_view_score", 0.0),
            "objective_breakdown": obj_scores,
            # Constraint Scores
            "setback_score": constraint_scores.get("setback_score", 0),
            "sunlight_score": constraint_scores.get("sunlight_score", 50),
            "daylight_score": constraint_scores.get("daylight_score", 50),
            "edge_attraction_score": constraint_scores.get("edge_attraction_score", 0),
            "road_access_score": constraint_scores.get("road_access_score", 50),
            "open_space_score": constraint_scores.get("open_space_score", 50),
            "density_score": constraint_scores.get("density_score", 50),
            "constraint_total_score": constraint_total,
            # Metrics
            "footprint_area": round(footprint, 1),
            "far": far,
            "site_coverage": coverage,
            "height_m": float(height_m),
            "floors": floors,
            "fits_within_site": fits and is_valid,
            "outside_area_sqm": opt.get("outside_area_sqm", 0.0),
            "setback_ok": is_valid and fits,
            # Validation Report
            "validation_report": {
                "inside_site": validation.get("constraints", {}).get("site_boundary", {}).get("passed", False),
                "inside_buildable_area": validation.get("constraints", {}).get("buildable_area", {}).get("passed", False),
                "setbacks": validation.get("constraints", {}).get("setback", {}).get("passed", False),
                "open_space": validation.get("constraints", {}).get("open_space", {}).get("passed", False),
                "violations": validation.get("violations", []),
            },
            # Shape morph params (if optimize_shape)
            "building_depth": opt.get("building_depth"),
            "shape_ratio": opt.get("shape_ratio"),
            "reasoning": ", ".join(reasons),
            "is_valid": is_valid,
        }

        options.append(option_dict)
        if is_valid:
            valid_options.append(option_dict)

    # Use valid options if available, otherwise fall back to all options
    final_options = valid_options if valid_options else options

    # MULTI-OBJECTIVE PARETO SELECTION: build a GENUINELY DIVERSE candidate pool
    # (placement grid × rotation × massing variants), score every candidate across
    # ALL objectives using the cached Site Context Memory (so noise/view/access etc.
    # actually respond to WHERE + WHAT each candidate is), compute one true Pareto
    # front, then select 8 representative options (Highest Solar / View / Lowest Noise
    # / Open Space / Density / Wind / Balanced / Landmark) with ENFORCED geometric
    # diversity — near-identical candidates are discarded and replaced with a more
    # diverse Pareto candidate. This replaces the old "re-weight the same placement"
    # behaviour that made options look identical. The existing view optimizer is
    # reused as the 'view' objective — not rewritten.
    multi_objective_meta: dict[str, Any] = {}
    _cached_site_memory: dict[str, Any] | None = None
    try:
        from ..notebook_logic.optimization import (
            optimization_weights as ow,
            pareto_selector as ps,
            site_context_memory as scm,
        )
        from ..notebook_logic import option_sampler

        # Site Context Memory: built ONCE per context version, referenced here (not
        # recomputed). Carries roads / noise_sources / view_corridors derived from the
        # urban-context edges captured after boundary confirmation. We build it on a
        # mutable dict and stash it so the persist step below caches it on the session.
        _scm_state = dict(state)
        site_mem = scm.ensure(_scm_state)
        scm_ctx = site_mem or {}
        _cached_site_memory = _scm_state.get("site_context_memory")

        moo_ctx = {
            "site_boundary": site_boundary,
            "site_area": site_area,
            "building_use": building_type if isinstance(building_type, str) else "residential",
            "obstacles": obstacles,
            "context_scores": scm_ctx.get("scores") or (state.get("urban_context") or {}).get("scores") or state.get("context_scores") or {},
            "roads": scm_ctx.get("roads") or [],
            "noise_sources": scm_ctx.get("noise_sources") or [],
            "view_attractors": scm_ctx.get("view_corridors") or [],
            "far_limit": float(state.get("far_limit") or 3.5),
        }
        # ENVIRONMENTAL MODE: inject real site wind (cached). No-op when flag OFF /
        # no coordinates / fetch fails → wind scorer uses its geometry proxy.
        try:
            from ..notebook_logic.optimization import env_data as ed

            _lat, _lng = ed.resolve_site_coords(state)
            _rec = ed.get_site_env(_lat, _lng)
            if _rec:
                if _rec.get("wind"):
                    moo_ctx["wind"] = _rec["wind"]
                if _rec.get("climate"):
                    moo_ctx["climate"] = _rec["climate"]
            if ed.env_mode_enabled():
                _uc = state.get("urban_context") or {}
                if _uc.get("neighbor_buildings"):
                    moo_ctx["neighbor_buildings"] = _uc["neighbor_buildings"]
                _amen = {}
                for _e in (_uc.get("edges") or _uc.get("edge_metadata") or []):
                    for _l, _d in (_e.get("nearest") or {}).items():
                        try:
                            _df = float(_d)
                        except (TypeError, ValueError):
                            continue
                        if _l not in _amen or _df < _amen[_l]:
                            _amen[_l] = _df
                if _amen:
                    moo_ctx["amenities"] = _amen
        except Exception:  # noqa: BLE001
            pass

        # Build the candidate pool: site-validated placements (position × rotation).
        # Use the OPTIMIZED footprint (preserves manipulated/courtyard geometry) as the base.
        base_ring = boundary
        placements = option_sampler.sample_candidates(
            base_ring, site_boundary=site_boundary, grid_step=24.0, rotation_step_degrees=45,
        )
        pool: list[dict[str, Any]] = []
        # IF THE USER MANIPULATED/SAVED THE SHAPE: optimize PLACEMENT ONLY — never morph
        # the massing. Re-shaping an edited building (carving an extra courtyard, slabbing
        # it) produced the malformed/notched geometry. Keep the user's exact footprint +
        # holes and just try different positions/rotations. Massing variants are only for
        # a plain unedited shape (where exploring forms is the point).
        import math as _m

        def _place_holes(holes, rot_deg, centroid):
            """Rotate the normalized holes by the candidate rotation and translate to its
            centroid, so a carved courtyard stays registered to the rotated footprint."""
            if not holes or not centroid:
                return [list(h) for h in (holes or [])]
            rad = _m.radians(rot_deg or 0)
            ca, sa = _m.cos(rad), _m.sin(rad)
            ox, oy = centroid[0], centroid[1]
            return [[[ox + p[0] * ca - p[1] * sa, oy + p[0] * sa + p[1] * ca] for p in h]
                    for h in holes]

        def _place_plates(plates, rot_deg, centroid):
            """Re-place the normalized manipulated plate stack (twist/taper sculpting +
            per-wing added floors) into a candidate's position/rotation — same transform
            as _place_holes, applied per plate footprint + per wing ring. Z preserved."""
            if not plates or not centroid:
                return copy.deepcopy(plates or [])
            rad = _m.radians(rot_deg or 0)
            ca, sa = _m.cos(rad), _m.sin(rad)
            ox, oy = centroid[0], centroid[1]

            def _ring(r):
                return [[ox + p[0] * ca - p[1] * sa, oy + p[0] * sa + p[1] * ca] for p in r]

            out = []
            for pl in plates:
                np = dict(pl)
                if pl.get("footprint"):
                    np["footprint"] = _ring(pl["footprint"])
                wf = pl.get("wing_footprints")
                if isinstance(wf, dict):
                    np["wing_footprints"] = {k: _ring(v) for k, v in wf.items() if v}
                out.append(np)
            return out

        for pl in placements[:48]:
            if is_manipulated:
                cand = {
                    "boundary": pl["boundary"],          # the manipulated shape, repositioned
                    "holes": _place_holes(optimize_holes, pl.get("rotation_degrees", 0),
                                          pl.get("centroid_xy")),  # carved holes follow the placement
                    "massing": "as_drawn",
                    "rotation_degrees": pl.get("rotation_degrees", 0),
                    "centroid_xy": pl.get("centroid_xy"),
                    "floors": floors,
                    "height_m": float(height_m),
                }
                # Carry the manipulated plate stack (twist + added floors) into THIS option.
                if optimize_plates:
                    cand["floor_plates"] = _place_plates(
                        optimize_plates, pl.get("rotation_degrees", 0), pl.get("centroid_xy"))
                pool.append(cand)
            else:
                for mv in ps.massing_variants(pl["boundary"]):
                    pool.append({
                        "boundary": mv["boundary"],
                        "holes": mv["holes"] or optimize_holes,
                        "massing": mv["massing"],
                        "rotation_degrees": pl.get("rotation_degrees", 0),
                        "centroid_xy": pl.get("centroid_xy"),
                        "floors": floors,
                        "height_m": float(height_m),
                    })
        # Fold in the validated view-NSGA options too (they carry real precomputed view
        # scores) so the 'view' objective uses the existing optimizer's output.
        for vo_opt in final_options:
            pool.append({**vo_opt, "massing": vo_opt.get("massing", "as_drawn")})

        sel = ps.select_representatives(pool, moo_ctx)
        strat_options = sel.get("options") or []
        if strat_options:
            for so in strat_options:
                so["option_id"] = so.get("strategy_id", so.get("option_id"))
                so["score"] = round(float(so.get("score", 0)), 1)
                # carry FAR/coverage for the option card from the chosen footprint
                fp = _poly_area(so.get("boundary") or [])
                so.setdefault("footprint_area", round(fp, 1))
                so.setdefault("far", round((fp * floors) / site_area, 3) if site_area else None)
                so.setdefault("site_coverage", round(fp / site_area, 3) if site_area else None)
                so.setdefault("shape_type", building_type)
            final_options = strat_options
            multi_objective_meta = {
                "weights": ow.get_weights(),
                "strategies": [{"id": s["strategy_id"], "name": s["strategy_name"]} for s in strat_options],
                "pareto_count": sel.get("pareto_count"),
                "scored_count": sel.get("scored_count"),
                "unavailable_objectives": sel.get("unavailable_objectives", []),
                "backfilled": sel.get("backfilled", []),
                "context_memory_used": bool(site_mem),
                "context_availability": (site_mem or {}).get("availability", {}),
            }
    except Exception as exc:  # noqa: BLE001
        import traceback
        multi_objective_meta = {"error": f"multi-objective Pareto selection skipped: {exc}",
                                "trace": traceback.format_exc().splitlines()[-3:]}

    if multi_objective_meta.get("strategies"):
        # Representative options are already distinct by Pareto purpose + enforced
        # geometric diversity. Keep them as-is — the geometry dedup would collapse
        # legitimately different objective-extreme placements.
        distinct = final_options
    else:
        # De-duplicate near-identical options (same shape + position + rotation + area),
        # keeping the higher-scoring one, then top up from the pool if needed so the user
        # gets `saved_option_count` genuinely DIFFERENT options.
        distinct = option_diversity.dedupe(final_options, top_n=body.saved_option_count)
        distinct = option_diversity.ensure_count(distinct, final_options, top_n=body.saved_option_count)

    # If we have no valid options, inform the user
    if not distinct and options:
        # Return the best invalid option with a warning
        distinct = [max(options, key=lambda x: x.get("combined_score", 0))]
        for opt in distinct:
            opt["warning"] = "No options passed constraint validation. Best unconstrained option shown."

    # Persist the option catalog onto the building so /explorer + compare can read it.
    bld_copy = copy.deepcopy(bld)
    bld_copy["option_catalog"] = {"options": distinct}
    new_placed = [bld_copy if b is bld else b for b in placed]
    new_state = dict(state)
    new_state["placed_buildings"] = new_placed
    # Cache the Site Context Memory so subsequent optimize/manipulate runs REFERENCE it
    # (built once after boundary confirmation, not recomputed per run).
    if _cached_site_memory is not None:
        new_state["site_context_memory"] = _cached_site_memory
    await store.update_state(session_id, new_state)

    return {
        "building_id": _building_id(bld),
        "options": distinct,
        "objective_names": vo.configure_objectives(),
        "site_area_sqm": round(site_area, 1),
        "setback_summary": setbacks,
        "algorithm": data.get("algorithm", "NSGA-II"),
        "pareto_solution_count": data.get("pareto_solution_count", len(options)),
        # Multi-objective engine framing: weights used + the strategies returned.
        "multi_objective": multi_objective_meta,
    }
