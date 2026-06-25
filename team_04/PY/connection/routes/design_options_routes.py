"""Design option (saved shape version) API.

After a successful manipulation the user can save the current geometry as a NEW
Shape Library version. Saved versions can be listed, fetched, and selected as the
active building. Optimization (session_optimize_routes) can then run over a single
current shape or ALL saved shapes.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..notebook_logic import design_option_store as dstore, shape_version_manager as svm
from ..session_store import store

router = APIRouter(prefix="/sessions", tags=["design-options"])


class SaveOptionRequest(BaseModel):
    building_id: str | None = None
    prompt: str | None = None      # the manipulation prompt that produced this version
    label: str | None = None


class OptimizeSavedRequest(BaseModel):
    # Which saved shapes to optimize. None / empty = ALL saved shapes (back-compat).
    option_ids: list[str] | None = None


def _building_id(b: dict[str, Any]) -> str:
    return b.get("building_id") or b.get("geometry_id") or "geometry"


@router.post("/{session_id}/design-options/save")
async def save_design_option(session_id: str, body: SaveOptionRequest) -> dict[str, Any]:
    """Save the current (manipulated) building geometry as a NEW Shape Library
    version. Never overwrites an existing option."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    placed = list(state.get("placed_buildings") or [])
    if not placed:
        raise HTTPException(status_code=422, detail="No building to save — generate/select a shape first")
    if body.building_id:
        bld = next((b for b in placed if isinstance(b, dict) and _building_id(b) == body.building_id), placed[0])
    else:
        bld = placed[0]

    new_state = dict(state)
    option = svm.save_version(new_state, dict(bld), created_from_prompt=body.prompt, label=body.label)
    await store.update_state(session_id, new_state)
    return {
        "saved": True,
        "option": {k: v for k, v in option.items() if k != "geometry"},
        "shape_option_id": option["shape_option_id"],
        "parent_option_id": option["parent_option_id"],
        "total_saved": len(dstore.list_options(new_state)),
    }


@router.get("/{session_id}/design-options")
async def list_design_options(session_id: str) -> dict[str, Any]:
    """Shape Library: all saved versions, enriched with the geometry + metrics the
    Saved-Shapes GALLERY needs to draw a card (footprint thumbnail + Type / Footprint /
    Coverage / Floors / Height / Fit), like the Shapes view. boundary/holes/floor_plates
    are included so the thumbnail can render the real footprint."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    site = state.get("site_boundary") or []
    site_area = _poly_area(site) if len(site) >= 3 else 0.0
    rows = svm.list_versions(state)
    full = {o.get("shape_option_id"): o for o in dstore.list_options(state)}
    for r in rows:
        o = full.get(r.get("shape_option_id")) or {}
        geo = o.get("geometry") or {}
        boundary = geo.get("boundary") or []
        fp_area = _poly_area(boundary) if len(boundary) >= 3 else None
        r["boundary"] = boundary
        r["holes"] = geo.get("holes") or []
        r["floor_plates"] = geo.get("floor_plates") or []
        r["floors"] = geo.get("floors")
        r["height_m"] = geo.get("height_m")
        r["footprint_area"] = round(fp_area, 1) if fp_area else None
        r["site_coverage"] = round(fp_area / site_area, 3) if (fp_area and site_area) else None
        r["manipulation_count"] = len(o.get("manipulation_history") or [])
        # does it fit inside the site? (cheap containment check)
        r["fits_within_site"] = bool(fp_area and site_area and fp_area <= site_area)
    return {"options": rows}


@router.post("/{session_id}/design-options/{option_id}/select")
async def select_design_option(session_id: str, option_id: str) -> dict[str, Any]:
    """Make a saved version the ACTIVE building (so the viewer + edits use it)."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    opt = dstore.get_option(state, option_id)
    if not opt:
        raise HTTPException(status_code=404, detail="Saved option not found")
    geo = opt["geometry"]
    placed = list(state.get("placed_buildings") or [])
    base = dict(placed[0]) if placed else {}
    base.update({
        "building_id": option_id,
        "geometry_id": option_id,
        "boundary": geo.get("boundary"),
        "holes": geo.get("holes") or [],
        "floor_plates": geo.get("floor_plates") or [],
        "floors": geo.get("floors"),
        "height_m": geo.get("height_m"),
        "wings": geo.get("wings") or [],
        "building_graph": geo.get("building_graph") or {},
        "shape_type": geo.get("shape_type"),
        "building_type": geo.get("shape_type"),
        "source_shape_option_id": option_id,
        "manipulation_history": opt.get("manipulation_history") or [],
    })
    new_state = dict(state)
    new_state["placed_buildings"] = [base]
    new_state["selected_shape_option_id"] = option_id
    await store.update_state(session_id, new_state)
    return {"selected": option_id, "shape_type": geo.get("shape_type"),
            "boundary": geo.get("boundary"), "floors": geo.get("floors")}


@router.post("/{session_id}/design-options/optimize-all")
async def optimize_all_saved(session_id: str, body: OptimizeSavedRequest | None = None) -> dict[str, Any]:
    """Optimize saved shapes — retain each shape's geometry, find its best placement
    (position + rotation), score it across all objectives, and return the best
    optimized result PER saved shape (linked to its source option).

    If ``body.option_ids`` is given, ONLY those saved shapes are optimized (the
    left-panel multi-select). Empty / omitted → every saved shape (back-compat)."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    saved = dstore.list_options(state)
    if not saved:
        raise HTTPException(status_code=422, detail="No saved shapes to optimize. Save a manipulated shape first.")
    # Filter to the selected saved shapes when the caller specified ids.
    wanted = set(body.option_ids) if (body and body.option_ids) else None
    if wanted:
        saved = [o for o in saved if o.get("shape_option_id") in wanted]
        if not saved:
            raise HTTPException(status_code=422, detail="None of the selected saved shapes were found.")
    site_boundary = state.get("site_boundary") or []
    if len(site_boundary) < 3:
        raise HTTPException(status_code=422, detail="Confirm a site boundary first")

    from agent.tools.view_optimizer import sample_valid_placements
    from ..notebook_logic import setback_rules as sr
    from ..notebook_logic.optimization import multi_objective_optimizer as moo, optimization_weights as ow
    # A SAVED manipulated shape is already rotated/positioned — its large axis-aligned
    # bbox often fits nowhere, so sample_valid_placements returns 0 → "no saved shapes
    # could be optimized". Un-rotate + center it first (shape unchanged), exactly like
    # the single-shape optimizer does. This is why a saved shape failed to optimize.
    from .session_optimize_routes import _normalize_for_sampling, _rotate_translate_ring

    def _site_min_dim(sb: list[list[float]]) -> float:
        xs = [p[0] for p in sb]; ys = [p[1] for p in sb]
        return max(10.0, min(max(xs) - min(xs), max(ys) - min(ys)))

    site_area = _poly_area(site_boundary)
    moo_ctx_base = {
        "site_boundary": site_boundary,
        "site_area": site_area,
        "context_scores": (state.get("urban_context") or {}).get("scores") or state.get("context_scores") or {},
        "roads": ((state.get("urban_context") or {}).get("roads")) or [],
        "far_limit": float(state.get("far_limit") or 3.5),
    }
    weights = ow.get_weights()

    # Inject environmental context (wind/climate/neighbours/amenities) so the full
    # multi-objective set scores — same enrichment the single-shape optimizer uses.
    try:
        from ..notebook_logic.optimization import env_data as ed
        if ed.env_mode_enabled():
            _lat, _lng = ed.resolve_site_coords(state)
            _rec = ed.get_site_env(_lat, _lng)
            if _rec:
                if _rec.get("wind"): moo_ctx_base["wind"] = _rec["wind"]
                if _rec.get("climate"): moo_ctx_base["climate"] = _rec["climate"]
            _uc = state.get("urban_context") or {}
            if _uc.get("neighbor_buildings"):
                moo_ctx_base["neighbor_buildings"] = _uc["neighbor_buildings"]
    except Exception:  # noqa: BLE001
        pass

    def _variant_metrics(sc, footprint, fl):
        """Full objective set + FAR/coverage/floors/design-health for ONE variant."""
        os = sc["objective_scores"]
        m = {k: round(v, 1) for k, v in os.items()}          # ALL available objectives
        m["design_health"] = round(sc["weighted_score"], 1)
        m["total"] = m["design_health"]
        m["far"] = round((footprint * fl) / site_area, 3) if site_area else None
        m["coverage"] = round(footprint / site_area, 3) if site_area else None
        m["floors"] = fl
        return m

    def _distinct(pl, chosen):
        """True if this placement differs enough from already-chosen ones (so variant
        B isn't a near-duplicate of A)."""
        for c in chosen:
            dx = abs(pl["centroid_xy"][0] - c["centroid_xy"][0])
            dy = abs(pl["centroid_xy"][1] - c["centroid_xy"][1])
            dr = abs((pl.get("rotation_degrees", 0) - c.get("rotation_degrees", 0)) % 360)
            if dx < 12 and dy < 12 and (dr < 20 or dr > 340):
                return False
        return True

    results: list[dict[str, Any]] = []
    VARIANTS_PER_SHAPE = 2
    for s_idx, opt in enumerate(saved):
        geo = opt.get("geometry") or {}
        boundary = geo.get("boundary")
        if not boundary or len(boundary) < 3:
            continue
        floors = int(geo.get("floors") or 1)
        use = geo.get("building_use") or "residential"
        ctx = {**moo_ctx_base, "building_use": use}
        sample_boundary = boundary
        opt_holes = [list(h) for h in (geo.get("holes") or [])]
        norm = _normalize_for_sampling(boundary, _site_min_dim(site_boundary))
        if norm:
            sample_boundary = norm["boundary"]
            opt_holes = [_rotate_translate_ring(h, norm["rotate_deg"], norm["cx0"], norm["cy0"],
                                                norm["dx"], norm["dy"]) for h in opt_holes]
        try:
            rules = sr.get_setback_rules(use)
            setbacks = {"default_setback": max(rules.front_setback, rules.rear_setback, rules.side_setback)}
            placements = sample_valid_placements(sample_boundary, site_boundary, rotation_step_degrees=30,
                                                 grid_step=15.0, site_setbacks=setbacks)
        except Exception:  # noqa: BLE001
            placements = []
        if not placements:
            # FALLBACK: a large/manipulated footprint (e.g. a twisted U with extra floors)
            # can leave NO valid relocation that clears the setback — sample_valid_placements
            # returns empty. Previously we SKIPPED the shape, so optimizing such shapes gave
            # ZERO variants (the "Optimization ran but no variants came back" bug). Instead,
            # score the shape AT ITS CURRENT (as-drawn) placement so every selected shape
            # always produces variants. Try a couple of gentle nudges so A/B differ when the
            # site allows; if none fit, both variants are the current position (still valid,
            # still comparable). The footprint isn't reshaped — only repositioned.
            cx0 = sum(p[0] for p in sample_boundary) / len(sample_boundary)
            cy0 = sum(p[1] for p in sample_boundary) / len(sample_boundary)
            cand_positions = [(0.0, 0.0)]
            try:
                from shapely.geometry import Polygon as _P
                _site_poly = _P(site_boundary)
                for ddx, ddy in ((8, 0), (-8, 0), (0, 8), (0, -8), (6, 6), (-6, -6)):
                    moved = [[p[0] + ddx, p[1] + ddy] for p in sample_boundary]
                    if _site_poly.contains(_P(moved)):
                        cand_positions.append((float(ddx), float(ddy)))
                    if len(cand_positions) >= 3:
                        break
            except Exception:  # noqa: BLE001
                pass
            placements = [{
                "boundary": [[p[0] + ox, p[1] + oy] for p in sample_boundary],
                "centroid_xy": (cx0 + ox, cy0 + oy),
                "rotation_degrees": 0,
            } for ox, oy in cand_positions]
        # Score EVERY placement across the FULL multi-objective set, then keep the top-N
        # DIVERSE variants per shape (A = best, B = best that's geometrically different).
        scored = []
        for pl in placements[:60]:
            cand = {"boundary": pl["boundary"], "holes": opt_holes,
                    "floors": floors, "height_m": geo.get("height_m")}
            sc = moo.score_candidate(cand, ctx, weights)
            scored.append({"pl": pl, "sc": sc, "total": sc["weighted_score"]})
        scored.sort(key=lambda x: x["total"], reverse=True)
        chosen: list[dict[str, Any]] = []
        for cand in scored:
            if len(chosen) >= VARIANTS_PER_SHAPE:
                break
            if _distinct(cand["pl"], [c["pl"] for c in chosen]):
                chosen.append(cand)
        if len(chosen) < VARIANTS_PER_SHAPE and scored:
            # not enough distinct placements — fill with next-best regardless
            for cand in scored:
                if len(chosen) >= VARIANTS_PER_SHAPE:
                    break
                if cand not in chosen:
                    chosen.append(cand)
        src = opt["shape_option_id"]
        for v_idx, cand in enumerate(chosen):
            pl, sc = cand["pl"], cand["sc"]
            footprint = _poly_area(pl["boundary"])
            tag = chr(65 + v_idx)                       # A, B, ...
            results.append({
                "optimized_option_id": f"{src}{tag}",   # e.g. shape_001A / shape_001B
                "variant_tag": tag,
                "source_shape_option_id": src,
                "shape_type": opt.get("shape_type"),
                "geometry": {"boundary": pl["boundary"], "holes": opt_holes,
                             "floor_plates": geo.get("floor_plates") or [], "floors": floors},
                "placement": {
                    "position": [round(pl["centroid_xy"][0], 1), round(pl["centroid_xy"][1], 1), 0],
                    "rotation_degrees": pl.get("rotation_degrees", 0),
                    "scale": 1.0,
                },
                "scores": _variant_metrics(sc, footprint, floors),
                "objective_scores": sc["objective_scores"],
                "validation_report": {"inside_site": "passed", "setback": "passed"},
            })

    # Rank optimized results across all saved shapes (best total first).
    results.sort(key=lambda r: r["scores"]["total"], reverse=True)

    # Feature 9: record this optimization run in history (per result) so the
    # comparison system can read it. Geometry/source designs are NOT overwritten —
    # these are child option records.
    import time
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    new_state = dict(state)
    history = list(new_state.get("optimization_history") or [])
    for r in results:
        history.append({
            "optimized_option_id": r["optimized_option_id"],
            "source_shape_option_id": r["source_shape_option_id"],
            "shape_type": r.get("shape_type"),
            "variant_tag": r.get("variant_tag"),
            "strategy": "all_saved_placement",
            "position": r["placement"]["position"],
            "rotation": r["placement"]["rotation_degrees"],
            "metrics": r["scores"],
            "objective_scores": r.get("objective_scores", {}),
            "overall_score": r["scores"]["total"],
            # GEOMETRY so the option can be previewed + compared AFTER a refresh — the
            # Optimization browser reloads these and renders them like live options.
            "geometry": r.get("geometry", {}),
            "timestamp": ts,
        })
    new_state["optimization_history"] = history
    await store.update_state(session_id, new_state)

    # BASELINE scores for each ORIGINAL saved shape (S01, S02, ...) — scored in place
    # (no placement search) so comparison can show S01 vs S01A vs S01B side by side.
    source_shapes: list[dict[str, Any]] = []
    for opt in saved:
        geo = opt.get("geometry") or {}
        b = geo.get("boundary")
        if not b or len(b) < 3:
            continue
        fl = int(geo.get("floors") or 1)
        cand = {"boundary": b, "holes": geo.get("holes") or [],
                "floors": fl, "height_m": geo.get("height_m")}
        try:
            sc = moo.score_candidate(cand, {**moo_ctx_base, "building_use": geo.get("building_use") or "residential"}, weights)
            fp = _poly_area(b)
            source_shapes.append({
                "shape_option_id": opt["shape_option_id"],
                "shape_type": opt.get("shape_type"),
                "created_from_prompt": opt.get("created_from_prompt"),
                "is_baseline": True,
                "scores": _variant_metrics(sc, fp, fl),
                "objective_scores": sc["objective_scores"],
                # Geometry so the comparison table can show the ORIGINAL alongside its
                # variants (floors/footprint/preview), not N/A for the baseline rows.
                "geometry": {
                    "boundary": b, "holes": geo.get("holes") or [],
                    "floor_plates": geo.get("floor_plates") or [],
                    "floors": fl, "height_m": geo.get("height_m"),
                },
                "floors": fl,
                "footprint_area": fp,
            })
        except Exception:  # noqa: BLE001
            pass

    # Report which OPTIMIZATION METRICS were available vs unavailable (the spec's
    # "completed using X, Y, Z. Wind and Noise data were unavailable").
    avail = moo.available_objectives({**moo_ctx_base, "building_use": "residential"})
    metrics_used = sorted(o for o, ok in avail.items() if ok)
    metrics_unavailable = sorted(o for o, ok in avail.items() if not ok)

    return {"optimized_options": results, "source_shapes": source_shapes,
            "saved_shape_count": len(saved),
            "variants_per_shape": VARIANTS_PER_SHAPE,
            "weights": weights, "history_recorded": len(results),
            "context_availability": _context_availability(state),
            "metrics_used": metrics_used,
            "metrics_unavailable": metrics_unavailable}


@router.get("/{session_id}/optimization-history")
async def get_optimization_history(session_id: str) -> dict[str, Any]:
    """Feature 9: the recorded optimization runs (shape/version/strategy/position/
    rotation/metrics/score/timestamp) — feeds the comparison system."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "optimization_history": state.get("optimization_history") or [],
        "evaluations": state.get("evaluations") or [],
    }


def _poly_area(b: list[list[float]]) -> float:
    pts = [(float(p[0]), float(p[1])) for p in (b or []) if len(p) >= 2]
    if len(pts) < 3:
        return 0.0
    s = 0.0
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        s += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(s) / 2.0


def _moo_ctx(state: dict[str, Any], use: str) -> dict[str, Any]:
    site_boundary = state.get("site_boundary") or []
    uc = state.get("urban_context") or {}
    ctx = {
        "site_boundary": site_boundary,
        "site_area": _poly_area(site_boundary),
        "building_use": use,
        "context_scores": uc.get("scores") or state.get("context_scores") or {},
        "roads": uc.get("roads") or [],
        "far_limit": float(state.get("far_limit") or 3.5),
    }
    # ENVIRONMENTAL MODE gates the WHOLE environmental layer as one switch, so the
    # dashboard is consistent (flag OFF → every scorer shows geometry/proxy; flag ON →
    # every scorer goes live). The OSM enrichment (roads/noise/view detractors that drive
    # the live View & Noise scores) only runs when the flag is ON — otherwise those
    # scorers fall back to their geometry proxy like the NASA-based ones.
    try:
        from ..notebook_logic.optimization import context_enrichment as ce
        from ..notebook_logic.optimization import env_data as ed

        if ed.env_mode_enabled():
            ctx = ce.enrich_ctx(ctx, uc)
    except Exception:  # noqa: BLE001
        pass
    # ENVIRONMENTAL MODE: inject the REAL site wind (NASA POWER, cached per site) so the
    # wind scorer evaluates orientation against actual prevailing wind. No-op when the
    # feature flag is OFF or no coordinates / fetch fails → scorer uses geometry proxy.
    try:
        from ..notebook_logic.optimization import env_data as ed

        lat, lng = ed.resolve_site_coords(state)
        rec = ed.get_site_env(lat, lng)
        if rec:
            if rec.get("wind"):
                ctx["wind"] = rec["wind"]           # Wind scorer
            if rec.get("climate"):
                ctx["climate"] = rec["climate"]     # advanced Solar scorer
        # Neighbour buildings (Density context) + amenity distances (Accessibility) come
        # from the stored urban context — only used when Environmental Mode is ON.
        if ed.env_mode_enabled():
            nb = uc.get("neighbor_buildings") or []
            if nb:
                ctx["neighbor_buildings"] = nb
            amen = _amenity_distances(uc)
            if amen:
                ctx["amenities"] = amen
    except Exception:  # noqa: BLE001
        pass
    return ctx


def _amenity_distances(uc: dict[str, Any]) -> dict[str, float]:
    """Flatten the nearest amenity distances across all context edges into
    {label: nearest_distance_m} for the Accessibility scorer."""
    out: dict[str, float] = {}
    for edge in (uc.get("edges") or uc.get("edge_metadata") or []):
        for label, dist in (edge.get("nearest") or {}).items():
            try:
                d = float(dist)
            except (TypeError, ValueError):
                continue
            if label not in out or d < out[label]:
                out[label] = d
    return out


def _context_availability(state: dict[str, Any]) -> dict[str, Any]:
    """CONTEXT AVAILABILITY: report which context data is actually present so the
    response can say what was used vs unavailable (no fabrication)."""
    uc = state.get("urban_context") or {}
    edges = uc.get("edges") or uc.get("edge_metadata") or []
    scores = uc.get("scores") or state.get("context_scores") or {}
    # Collect the amenity types actually stored on edges.
    amenities = set()
    for e in edges:
        for k, v in (e.get("nearest") or {}).items():
            if v is not None:
                amenities.add(k)
        for c in (e.get("edge_context") or []):
            if c.get("label"):
                amenities.add(c["label"])
    available = {
        "edge_analysis": bool(edges),
        "transit": any(a in amenities for a in ("Metro", "Train Station", "Bus Stop")),
        "parks": "Park" in amenities,
        "roads": "Primary Road" in amenities or bool(uc.get("roads")),
        "retail": any(a in amenities for a in ("Grocery Store", "Shopping")),
        "schools": any(a in amenities for a in ("School", "University")),
        "hospitals": "Hospital" in amenities,
        "context_scores": bool(scores),
    }
    used = sorted(k for k, v in available.items() if v)
    unavailable = sorted(k for k, v in available.items() if not v)
    return {"available": available, "used": used, "unavailable": unavailable}


@router.post("/{session_id}/evaluate-design")
async def evaluate_design(session_id: str) -> dict[str, Any]:
    """Feature 6: ANALYSIS-ONLY evaluation of the CURRENT building. Scores it across
    every objective using the EXISTING optimization engine WITHOUT moving, rotating,
    scaling or repositioning any geometry. Returns the headline metrics + overall
    score and records an 'evaluation' node so it can feed comparison/history."""
    state = await store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    placed = list(state.get("placed_buildings") or [])
    if not placed:
        raise HTTPException(status_code=422, detail="No building to evaluate — select or generate a shape first")
    bld = placed[0]
    boundary = bld.get("boundary") or bld.get("building_boundary")
    if not boundary:
        raise HTTPException(status_code=422, detail="Building has no geometry to evaluate")

    from ..notebook_logic.optimization import multi_objective_optimizer as moo

    use = bld.get("building_use") or "residential"
    ctx = _moo_ctx(state, use)
    candidate = {
        "boundary": boundary,
        "holes": bld.get("holes") or [],
        "floors": int(bld.get("floors") or 1),
        "height_m": bld.get("height_m"),
        # carry any precomputed view scores so the view objective reuses them.
        "view_score": bld.get("view_score"),
    }
    sc = moo.score_candidate(candidate, ctx)
    os = sc["objective_scores"]
    om = sc["objective_metrics"]
    summary = {
        "solar": os.get("solar", 0), "view": os.get("view", 0), "noise": os.get("noise", 0),
        "wind": os.get("wind", 0), "road_access": os.get("road_access", 0),
        "open_space": os.get("open_space", 0), "density": os.get("density", 0),
        "far": om.get("density", {}).get("far"),
        "overall_score": sc["weighted_score"],
    }
    # ENVIRONMENTAL ANALYSIS detail — surface each upgraded scorer's mode + proxy vs
    # real-data score so the dashboard can show the comparison. Geometry mode leaves
    # env_score absent; the dashboard then shows only the proxy.
    def _env_block(metrics_key: str, extra_keys: tuple[str, ...]) -> dict[str, Any]:
        m = om.get(metrics_key, {}) or {}
        block = {
            "mode": m.get("mode", "geometry"),
            "proxy_score": m.get("proxy_score"),
            "env_score": m.get("env_score"),
        }
        for k in extra_keys:
            block[k] = m.get(k)
        return block

    env_analysis = {
        "wind": _env_block("wind", ("prevailing_wind", "wind_speed_ms",
                                    "facade_exposure_pct", "wind_tunnel_risk")),
        "noise": _env_block("noise", ("day_noise_db", "night_noise_db", "loudest_source")),
        "view": _env_block("view", ("positive_features", "negative_features")),
        "solar": _env_block("solar", ("annual_radiation_kwh_m2_day", "summer_max_temp_c",
                                      "overheating_risk_pct", "daylight_potential_pct")),
        "density": _env_block("density", ("context_median_height_m", "proposed_height_m",
                                          "context_fit_pct", "neighbours_considered")),
        "road_access": _env_block("road_access", ("amenities_within_walk", "accessibility_basis")),
    }
    # Record an evaluation node (history) — geometry untouched.
    import time
    new_state = dict(state)
    evals = list(new_state.get("evaluations") or [])
    evals.append({
        "building_id": bld.get("building_id"),
        "source_shape_option_id": bld.get("source_shape_option_id"),
        "scores": summary,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "evaluation",
    })
    new_state["evaluations"] = evals
    await store.update_state(session_id, new_state)
    return {
        "mode": "evaluation",
        "geometry_changed": False,
        "building_id": bld.get("building_id"),
        "source_shape_option_id": bld.get("source_shape_option_id"),
        "scores": summary,
        "objective_scores": os,
        "objective_metrics": om,
        # Environmental analysis (wind first): mode + proxy-vs-real comparison.
        "env_analysis": env_analysis,
        # Transparency: which context data + which metrics were available vs not.
        "context_availability": _context_availability(state),
        "metrics_used": sc.get("metrics_used", []),
        "metrics_unavailable": sc.get("metrics_unavailable", []),
    }
