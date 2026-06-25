"""Context-aware shape generation — make Urban Context usable design intelligence.

Turns a prompt's directional/context language into a concrete site edge or corner,
then aligns / places the building accordingly. This is what lets a user say
"long facade on east" or "place tower near the metro edge" and get a building that
actually responds to the stored urban context.

Inputs are the context blobs the frontend computes and (now) persists to backend
state:
  edge_metadata : [{edge_id, display_name, direction, a:[x,y], b:[x,y], mid:[x,y]}]
  edge_context  : per-edge relevant amenities [{label, distance, reason}] (on each edge)
  context_scores, layers, selected_edge ...

All geometry is in the LOCAL metric frame (x=east, y=north) the rest of the
manipulation engine uses. Pure functions + structured debug logs (Fix 8).
"""
from __future__ import annotations

import math
import re
from typing import Any

# 8 compass directions and their unit vectors (x=east, y=north).
_DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    "north": (0.0, 1.0), "south": (0.0, -1.0), "east": (1.0, 0.0), "west": (-1.0, 0.0),
    "northeast": (0.707, 0.707), "northwest": (-0.707, 0.707),
    "southeast": (0.707, -0.707), "southwest": (-0.707, -0.707),
}

# Context-feature phrases -> the amenity labels (as stored in edge_context/nearest)
# that satisfy them. "near metro" matches Metro/Train/Bus, etc.
_CONTEXT_FEATURES: dict[str, list[str]] = {
    "transportation": ["Metro", "Train Station", "Bus Stop"],
    "transport": ["Metro", "Train Station", "Bus Stop"],
    "metro": ["Metro"],
    "train": ["Train Station"],
    "bus": ["Bus Stop"],
    "park": ["Park"],
    "green": ["Park"],
    "primary road": ["Primary Road"],
    "main road": ["Primary Road"],
    "road": ["Primary Road"],
    "retail": ["Grocery Store", "Shopping"],
    "grocery": ["Grocery Store"],
    "shopping": ["Shopping", "Grocery Store"],
    "school": ["School", "University"],
    "college": ["University"],
    "university": ["University"],
    "hospital": ["Hospital"],
    "healthcare": ["Hospital"],
}

# "away from X" / "quiet" inverts the target (place AWAY from a noisy feature).
_NOISE_FEATURES = ["Primary Road", "Train Station", "Metro"]

_LOG: list[str] = []


def _log(msg: str) -> None:
    _LOG.append(msg)
    print(f"[context-shape] {msg}")  # Fix 8: structured debug trace


def drain_log() -> list[str]:
    out = list(_LOG)
    _LOG.clear()
    return out


# --------------------------------------------------------------------------- #
# 1. Intent extraction
# --------------------------------------------------------------------------- #
def extract_directional_intent(prompt: str) -> str | None:
    """Return the compass direction named in the prompt (longest match wins so
    'northeast' beats 'north'), or None."""
    low = (prompt or "").lower()
    # normalize 'north east' -> 'northeast'
    low = re.sub(r"\b(north|south)\s+(east|west)\b", r"\1\2", low)
    for d in ("northeast", "northwest", "southeast", "southwest",
              "north", "south", "east", "west"):
        if re.search(rf"\b{d}\b", low):
            _log(f"directional intent: {d}")
            return d
    return None


def extract_context_intent(prompt: str) -> dict[str, Any] | None:
    """Return {feature_labels, away} when the prompt references an urban-context
    feature ('near metro', 'towards retail', 'away from noisy road'), else None."""
    low = (prompt or "").lower()
    away = bool(re.search(r"\b(away from|avoid|far from|keep .* away|noisy|quiet)\b", low))
    # Longest phrases first so 'primary road' wins over 'road'.
    for phrase in sorted(_CONTEXT_FEATURES, key=len, reverse=True):
        if phrase in low:
            labels = _CONTEXT_FEATURES[phrase]
            # 'noisy/quiet' with no explicit feature -> noise features.
            if away and ("nois" in low or "quiet" in low) and phrase in ("road", "primary road"):
                labels = _NOISE_FEATURES
            _log(f"context intent: feature={phrase} labels={labels} away={away}")
            return {"feature_labels": labels, "away": away, "phrase": phrase}
    if away and ("nois" in low or "quiet" in low):
        _log("context intent: noisy/quiet -> noise features, away=True")
        return {"feature_labels": _NOISE_FEATURES, "away": True, "phrase": "noisy road"}
    return None


# --------------------------------------------------------------------------- #
# 2. Resolve the target edge
# --------------------------------------------------------------------------- #
def resolve_target_edge(prompt: str, edge_metadata: list[dict[str, Any]],
                        edges_full: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Pick the site edge the prompt targets.

    Returns {ok, edge?, reason?, basis}. Direction language -> the edge whose
    outward normal best matches the compass direction. Context language -> the edge
    whose stored edge_context/nearest has the closest matching amenity. 'away from'
    -> the FARTHEST edge."""
    edges = edges_full or edge_metadata or []
    if not edges:
        return {"ok": False, "reason": "no_edges", "basis": None}

    # (a) Context feature target takes priority when present (more specific).
    ctx_intent = extract_context_intent(prompt)
    if ctx_intent:
        edge = _edge_nearest_feature(edges, ctx_intent["feature_labels"], away=ctx_intent["away"])
        if edge is None:
            return {"ok": False, "reason": "feature_not_stored",
                    "feature": ctx_intent["phrase"], "basis": "context"}
        _log(f"resolved edge by context: {edge.get('display_name') or edge.get('edge_id')}")
        return {"ok": True, "edge": edge, "basis": "context", "feature": ctx_intent["phrase"],
                "away": ctx_intent["away"]}

    # (b) Directional target.
    direction = extract_directional_intent(prompt)
    if direction:
        edge = _edge_for_direction(edges, direction)
        if edge is None:
            return {"ok": False, "reason": "direction_edge_not_found",
                    "direction": direction, "basis": "direction"}
        _log(f"resolved edge by direction {direction}: {edge.get('display_name') or edge.get('edge_id')}")
        return {"ok": True, "edge": edge, "basis": "direction", "direction": direction}

    return {"ok": False, "reason": "no_intent", "basis": None}


def _edge_for_direction(edges, direction):
    ux, uy = _DIRECTION_VECTORS[direction]
    cx, cy = _edges_centroid(edges)
    best, best_dot = None, -2.0
    for e in edges:
        mx, my = _edge_mid(e)
        vx, vy = mx - cx, my - cy
        n = math.hypot(vx, vy) or 1.0
        dot = (vx / n) * ux + (vy / n) * uy   # how much the edge faces `direction`
        if dot > best_dot:
            best_dot, best = dot, e
    return best


def _edge_nearest_feature(edges, labels, *, away=False):
    """The edge with the smallest (or largest, if away) distance to any of `labels`."""
    scored = []
    for e in edges:
        d = _edge_feature_distance(e, labels)
        if d is not None:
            scored.append((d, e))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=away)
    return scored[0][1]


def _edge_feature_distance(edge, labels):
    """Min distance from this edge to any amenity in `labels` (from edge_context or
    nearest)."""
    best = None
    for c in (edge.get("edge_context") or []):
        if c.get("label") in labels and c.get("distance") is not None:
            best = c["distance"] if best is None else min(best, c["distance"])
    nearest = edge.get("nearest") or {}
    for lbl in labels:
        if nearest.get(lbl) is not None:
            best = nearest[lbl] if best is None else min(best, nearest[lbl])
    return best


# --------------------------------------------------------------------------- #
# 3. Geometry operations
# --------------------------------------------------------------------------- #
def align_long_facade_to_edge(boundary: list[list[float]], edge: dict[str, Any]) -> dict[str, Any]:
    """Rotate the footprint so its LONGEST edge runs PARALLEL to the target site edge
    (so the long facade faces that side). Rotation about the centroid."""
    try:
        a, b = _edge_endpoints(edge)
        if a is None:
            return {"ok": False, "reason": "edge has no geometry"}
        edge_ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        # longest footprint edge angle
        long_ang, longest = 0.0, 0.0
        n = len(boundary)
        for i in range(n):
            p, q = boundary[i], boundary[(i + 1) % n]
            d = math.hypot(q[0] - p[0], q[1] - p[1])
            if d > longest:
                longest, long_ang = d, math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
        # smallest rotation that makes them parallel (mod 180)
        delta = (edge_ang - long_ang + 90.0) % 180.0 - 90.0
        rotated = _rotate(boundary, delta)
        _log(f"align_long_facade: rotated {round(delta,1)}° to parallel {edge.get('display_name')}")
        return {"ok": True, "boundary": rotated, "rotation_degrees": round(delta, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"alignment failed: {exc}"}


_ROAD_LABEL_TO_LAYERS: dict[str, list[str]] = {
    "Primary Road": ["roads.primary", "roads.secondary", "roads.tertiary", "roads.local"],
}


def _nearest_road_segment(urban_context: dict[str, Any], boundary: list[list[float]],
                          labels: list[str] | None = None) -> dict[str, Any] | None:
    """Find the road polyline segment CLOSEST to the building from the stored context
    layers, and return its bearing + midpoint. Roads are LINE features (layers[*].roads
    = [{path:[[x,y]...]}]) — they aren't attached to site edges as point amenities, which
    is why the edge-feature lookup couldn't resolve 'main road'. We align directly to the
    real road geometry instead. `labels` (e.g. ['Primary Road']) is advisory: we prefer
    higher road classes but fall back to ANY road so 'main road' always finds the street."""
    layers = (urban_context or {}).get("layers") or {}
    if not layers:
        return None
    # Preferred class order: primary → secondary → tertiary → local. "main road" should
    # latch onto the most important nearby street, but never return nothing if only a
    # smaller road exists.
    layer_order = ["roads.primary", "roads.secondary", "roads.tertiary", "roads.local"]
    bcx, bcy = _poly_centroid(boundary)

    best = None  # (distance, ax, ay, bx, by)
    for lid in layer_order:
        layer = layers.get(lid) or {}
        roads = layer.get("roads") or []
        for road in roads:
            path = road.get("path") or []
            for i in range(len(path) - 1):
                ax, ay = float(path[i][0]), float(path[i][1])
                bx, by = float(path[i + 1][0]), float(path[i + 1][1])
                d = _dist_point_to_seg(bcx, bcy, ax, ay, bx, by) if "_dist_point_to_seg" in globals() else \
                    math.hypot(bcx - (ax + bx) / 2, bcy - (ay + by) / 2)
                if best is None or d < best[0]:
                    best = (d, ax, ay, bx, by)
        # If we found ANY segment in this (higher-priority) class, prefer it and stop —
        # so a primary road wins over a closer local lane when both exist.
        if best is not None:
            break

    if best is None:
        return None
    _d, ax, ay, bx, by = best
    bearing = math.degrees(math.atan2(by - ay, bx - ax))
    return {"bearing": bearing, "mid": [(ax + bx) / 2, (ay + by) / 2], "distance": round(_d, 1)}


def align_long_facade_to_road(boundary: list[list[float]], urban_context: dict[str, Any],
                              labels: list[str] | None = None) -> dict[str, Any]:
    """Rotate the footprint so its LONGEST edge runs PARALLEL to the nearest real road
    polyline (the facade then faces/runs-along the street). This is what 'align facade to
    main road' should do — it aligns to the ROAD GEOMETRY, not a compass direction or a
    point amenity attached to a site edge."""
    seg = _nearest_road_segment(urban_context, boundary, labels)
    if not seg:
        return {"ok": False, "reason": "no_road_geometry"}
    try:
        road_ang = seg["bearing"]
        long_ang, longest = 0.0, 0.0
        n = len(boundary)
        for i in range(n):
            p, q = boundary[i], boundary[(i + 1) % n]
            d = math.hypot(q[0] - p[0], q[1] - p[1])
            if d > longest:
                longest, long_ang = d, math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
        delta = (road_ang - long_ang + 90.0) % 180.0 - 90.0
        rotated = _rotate(boundary, delta)
        _log(f"align_long_facade_to_road: rotated {round(delta,1)} deg parallel to road "
             f"(bearing {round(road_ang,1)} deg, {seg['distance']}m away)")
        return {"ok": True, "boundary": rotated, "rotation_degrees": round(delta, 1),
                "road_bearing": round(road_ang, 1), "road_distance_m": seg["distance"]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"road alignment failed: {exc}"}


def place_shape_near_edge(boundary: list[list[float]], edge: dict[str, Any],
                          site_boundary: list[list[float]], *, margin: float = 6.0,
                          away: bool = False, building_type: str | None = None) -> dict[str, Any]:
    """DECISIVELY snap the building to a site edge relative to the target feature's edge:
    - toward (away=False): hug the SAME side as the feature (e.g. 'near transit' → that edge)
    - away  (away=True):   hug the OPPOSITE side (e.g. 'away from noise' → far edge)
    Snaps fully to the BUILDABLE edge (site minus the real setback) so the move and the
    self-debug validator agree — without this the validator pulled the building most of
    the way back (it snapped past the setback), which read as a tiny 'creeping' move while
    chat claimed the full relocation. Honestly reports when already there."""
    try:
        a, b = _edge_endpoints(edge)
        if a is None:
            return {"ok": False, "reason": "edge has no geometry"}
        emx, emy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        scx, scy = _poly_centroid(site_boundary)
        # Snap to the BUILDABLE area (site inset by the same setback the validator enforces),
        # not the raw site bbox + a guessed margin. This is the key alignment: place and
        # validate against the SAME polygon so they don't fight. Fall back to the raw site
        # (inset by `margin`) only if the setback rules are unavailable.
        place_poly = site_boundary
        buildable_shape = None  # Shapely polygon for STRICT containment (matches validator)
        try:
            from . import setback_rules as _sr

            _ba = _sr.create_buildable_area(site_boundary, building_type=building_type or "residential")
            if _ba is not None and not _ba.is_empty:
                place_poly = [[float(x), float(y)] for x, y in _ba.exterior.coords]
                buildable_shape = _ba           # use the REAL polygon, not its bbox/ring
                margin = 0.0  # the setback is already baked into place_poly
        except Exception:  # noqa: BLE001
            place_poly = site_boundary

        def _fits(ring) -> bool:
            # Strict polygon containment against the buildable area — the SAME test the
            # self-debug validator runs. Using this (not a bbox/tolerant check) is what
            # makes the snapped position one the validator will accept, so it isn't
            # recentred afterwards. Tiny buffer absorbs floating-point edge contact.
            if buildable_shape is None:
                return _ring_in_site(ring, place_poly)
            try:
                from shapely.geometry import Polygon as _P
                return buildable_shape.buffer(0.05).contains(_P([(p[0], p[1]) for p in ring]))
            except Exception:  # noqa: BLE001
                return _ring_in_site(ring, place_poly)
        # buildable + building bounding boxes (snap targets come from the buildable bbox)
        sxs = [p[0] for p in place_poly]; sys_ = [p[1] for p in place_poly]
        smin_x, smax_x, smin_y, smax_y = min(sxs), max(sxs), min(sys_), max(sys_)
        bxs = [p[0] for p in boundary]; bys = [p[1] for p in boundary]
        bmin_x, bmax_x, bmin_y, bmax_y = min(bxs), max(bxs), min(bys), max(bys)
        # which axis does the feature edge lie on? (dominant offset from site centre)
        dx_e, dy_e = emx - scx, emy - scy
        horizontal_edge = abs(dy_e) >= abs(dx_e)   # edge is N/S (move along Y) vs E/W (move along X)
        # target side: toward the feature, or the opposite if 'away'
        sign = (1 if (dy_e if horizontal_edge else dx_e) >= 0 else -1) * (-1 if away else 1)
        dx = dy = 0.0
        if horizontal_edge:
            dy = (smax_y - margin - bmax_y) if sign > 0 else (smin_y + margin - bmin_y)
        else:
            dx = (smax_x - margin - bmax_x) if sign > 0 else (smin_x + margin - bmin_x)
        # Compute the BEST reachable displacement toward the target side. The full bbox
        # snap can poke a corner outside an irregular (rotated/angled OSM) site, so we
        # find the largest fraction of (dx,dy) that still fits inside the real boundary.
        # This is the KEY to idempotency on irregular sites: if the building already sits
        # at its practical limit, the best reachable move is ~0 and we report "already
        # there" — instead of creeping a few metres on every repeat (the bug where "move
        # away from noise" kept saying "Updated" without visibly moving).
        # Validate reachable positions against the BUILDABLE polygon (place_poly) — the
        # same setback-inset area the self-debug validator enforces. Accepting only
        # positions inside it means the validator won't yank the building back, so the
        # move that's reported is the move that persists (no "claimed big move, tiny real
        # move" mismatch). Falls back to the raw site if place_poly == site_boundary.
        full = [[p[0] + dx, p[1] + dy] for p in boundary]
        if _fits(full):
            best_f = 1.0
        else:
            best_f = 0.0
            for f in (0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1):
                cand = [[p[0] + dx * f, p[1] + dy * f] for p in boundary]
                if _fits(cand):
                    best_f = f
                    break
        rdx, rdy = dx * best_f, dy * best_f
        # honesty: the building is already as far as it can usefully go (either it's at the
        # setback, or the site shape blocks any further move). 2 m tolerance — a notched/
        # rotated footprint re-measures its bbox edge ~1 m differently after a snap, and a
        # sub-2 m shift is imperceptible. Treat as no-op so the repeat says "already there".
        if (rdx * rdx + rdy * rdy) ** 0.5 < 2.0:
            return {"ok": False, "dx": 0.0, "dy": 0.0,
                    "reason": f"the building is already as far {('from' if away else 'toward')} {edge.get('display_name','that feature')} as the site allows.",
                    "suggestion": "it can't move further that way; try a different reference"}
        nb = [[p[0] + rdx, p[1] + rdy] for p in boundary]
        _log(f"place_near_edge: snapped {'away from' if away else 'toward'} {edge.get('display_name')} (dx={round(rdx,1)},dy={round(rdy,1)}, reach={best_f})")
        return {"ok": True, "boundary": nb, "shift_m": round((rdx * rdx + rdy * rdy) ** 0.5, 1)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"placement failed: {exc}"}


# --------------------------------------------------------------------------- #
# 4. Top-level orchestration
# --------------------------------------------------------------------------- #
def apply_context_to_shape(prompt: str, boundary: list[list[float]],
                           site_boundary: list[list[float]],
                           urban_context: dict[str, Any] | None,
                           building_type: str | None = None) -> dict[str, Any]:
    """Resolve the prompt's directional/context intent against the stored context and
    apply the matching geometry op to `boundary`. Returns a status dict (Fix 7: never
    silently ignore — explain when context is missing). `building_type` selects the
    setback rule so placement snaps to the same buildable area the validator enforces."""
    drain_log()
    edges = (urban_context or {}).get("edges") or (urban_context or {}).get("edge_metadata") or []
    has_directional = extract_directional_intent(prompt) is not None
    has_context = extract_context_intent(prompt) is not None
    if not (has_directional or has_context):
        return {"applied": False, "status": "no_context_intent", "boundary": boundary, "log": drain_log()}

    low_p = (prompt or "").lower()
    _wants_align_early = bool(re.search(
        r"\b(facade|frontage|align|parallel|long side|face|facing|orient|front toward|entrance)\b", low_p))
    _names_road = bool(re.search(r"\b(main road|primary road|the road|street|roadside)\b", low_p)) \
        or (extract_context_intent(prompt) or {}).get("feature_labels") == ["Primary Road"]
    # ROAD ALIGNMENT (the real fix for "align facade to main road"): roads are LINE
    # features stored in urban_context.layers — NOT point amenities attached to site
    # edges, so the edge-feature lookup below returns "feature_not_stored" and nothing
    # rotates. When the prompt asks to align a facade to a road, align to the nearest
    # real road polyline's bearing directly. This runs even if `edges` is empty, because
    # roads live in `layers`, not `edges`.
    if _wants_align_early and _names_road:
        rr = align_long_facade_to_road(boundary, urban_context or {}, ["Primary Road"])
        if rr.get("ok") and _ring_in_site(rr["boundary"], site_boundary):
            _log(f"road-aligned facade (delta {rr.get('rotation_degrees')} deg)")
            return {
                "applied": True, "status": "success", "boundary": rr["boundary"],
                "target_edge": "nearest road", "basis": "road",
                "operations": ["align_long_facade_to_road"],
                "rotation_degrees": rr.get("rotation_degrees"),
                "validation": {"inside_site": "passed"}, "log": drain_log(),
            }
        if rr.get("reason") == "no_road_geometry":
            return {"applied": False, "status": "target_not_found",
                    "reason": "No road geometry is available in the stored urban context. "
                              "Please regenerate Urban Context (it must include roads), then retry.",
                    "boundary": boundary, "log": drain_log()}
        # else: rotation left the site → fall through to the edge logic as a backup.

    if not edges:
        return {"applied": False, "status": "context_missing",
                "reason": "Context target not found: no urban context was stored. Please regenerate urban context.",
                "boundary": boundary, "log": drain_log()}

    target = resolve_target_edge(prompt, edges, edges)
    if not target.get("ok"):
        if target.get("reason") == "feature_not_stored":
            feat = target.get("feature", "that feature")
            reason = (f"Context target not found: no {feat} edge was stored. "
                      "Please regenerate urban context.")
        elif target.get("reason") == "direction_edge_not_found":
            reason = f"Could not locate the {target.get('direction')} site edge."
        else:
            reason = "Could not resolve a context target from the prompt."
        return {"applied": False, "status": "target_not_found", "reason": reason,
                "boundary": boundary, "log": drain_log()}

    edge = target["edge"]
    low = (prompt or "").lower()

    # Verb classification:
    #   align  -> "facade/frontage/align/parallel/face/orient/front toward"
    #   place  -> "place/move/tower/near/toward/plaza/courtyard/entrance ..."
    wants_align = bool(re.search(r"\b(facade|frontage|align|parallel|long side|face|facing|orient|front toward|entrance)\b", low))
    wants_place = bool(re.search(r"\b(place|move|tower|near|toward|towards|close to|corner|plaza|courtyard|patio|open .* toward)\b", low))
    # If a context feature/direction resolved but no explicit verb, DEFAULT to placing
    # the building toward (or away from) that edge — "face the park" should respond.
    if not (wants_align or wants_place):
        wants_place = True

    ops_applied = []
    work = boundary
    if wants_align or (target["basis"] == "direction" and not wants_place):
        r = align_long_facade_to_edge(work, edge)
        if r.get("ok") and _ring_in_site(r["boundary"], site_boundary):
            work = r["boundary"]; ops_applied.append("align_long_facade")
    place_reason = None
    if wants_place or target.get("away"):
        r = place_shape_near_edge(work, edge, site_boundary, away=bool(target.get("away")),
                                  building_type=building_type)
        place_reason = r.get("reason")
        if r.get("ok") and _ring_in_site(r["boundary"], site_boundary):
            # Only count it if the placement actually moved the footprint by a perceptible
            # amount (≥2 m). A sub-2 m residual from re-measuring a notched/rotated bbox is
            # not a real relocation — counting it makes the building creep on repeats.
            moved = any(abs(work[i][0] - r["boundary"][i][0]) > 2.0 or abs(work[i][1] - r["boundary"][i][1]) > 2.0
                        for i in range(min(len(work), len(r["boundary"]))))
            if moved:
                work = r["boundary"]; ops_applied.append("place_near_edge")

    if not ops_applied:
        return {"applied": False, "status": "no_valid_op",
                "reason": place_reason or "Resolved the target, but the building is already there or can't move further without leaving the site.",
                "boundary": boundary, "log": drain_log()}

    valid = _ring_in_site(work, site_boundary)
    _log(f"ops applied: {ops_applied} | inside_site: {valid}")
    return {
        "applied": True,
        "status": "success",
        "boundary": work,
        "target_edge": edge.get("display_name") or edge.get("edge_id"),
        "basis": target["basis"],
        "operations": ops_applied,
        "validation": {"inside_site": "passed" if valid else "failed"},
        "log": drain_log(),
    }


# --------------------------------------------------------------------------- #
# Geometry helpers (local metric frame)
# --------------------------------------------------------------------------- #
def _edge_endpoints(edge):
    a = edge.get("a") or (edge.get("start_point"))
    b = edge.get("b") or (edge.get("end_point"))
    if a and b and len(a) >= 2 and len(b) >= 2:
        return ([float(a[0]), float(a[1])], [float(b[0]), float(b[1])])
    # fall back to midpoint + angle if endpoints absent
    mid = edge.get("midpoint") or edge.get("mid")
    return (None, None) if not mid else (None, None)


def _edge_mid(edge):
    m = edge.get("mid") or edge.get("midpoint")
    if m and len(m) >= 2:
        return (float(m[0]), float(m[1]))
    a, b = _edge_endpoints(edge)
    if a and b:
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return (0.0, 0.0)


def _edges_centroid(edges):
    pts = [_edge_mid(e) for e in edges]
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _poly_centroid(b):
    pts = [(float(p[0]), float(p[1])) for p in b if len(p) >= 2]
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _poly_radius(b):
    cx, cy = _poly_centroid(b)
    return max((math.hypot(p[0] - cx, p[1] - cy) for p in b if len(p) >= 2), default=0.0)


def _rotate(b, deg):
    cx, cy = _poly_centroid(b)
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [[cx + (p[0] - cx) * ca - (p[1] - cy) * sa,
             cy + (p[0] - cx) * sa + (p[1] - cy) * ca] for p in b]


def _ring_in_site(ring, site):
    try:
        from shapely.geometry import Polygon

        rp = Polygon([(p[0], p[1]) for p in ring])
        sp = Polygon([(p[0], p[1]) for p in site])
        if not rp.is_valid:
            rp = rp.buffer(0)
        if not sp.is_valid:
            sp = sp.buffer(0)
        if rp.area <= 0:
            return False
        return rp.difference(sp).area / rp.area < 0.02
    except Exception:  # noqa: BLE001
        return True
