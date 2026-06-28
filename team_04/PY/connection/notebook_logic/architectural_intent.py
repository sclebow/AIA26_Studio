"""Architectural Intent Manipulation — the geometry operations behind design-intent
prompts ("add a courtyard", "create a patio on the south side", "make the north
wing longer"). These are REAL footprint mutations, not move/rotate/scale:

  carve_courtyard   — subtract a central void from the footprint (daylight to the core)
  carve_patio       — subtract an edge void on a given true-geographic side
  lengthen_side     — extend the footprint outward on a given true side (longer facade)
  reduce_depth      — shrink the footprint along its short axis (shallower floor plate)

All ops work in the building's local METRIC frame where +y is true north (the same
frame move/rotate/scale use), so "north/south/east/west" are TRUE geographic
directions, not screen directions. Each returns {outer, holes, ok, reason} so the
route can validate against the site before committing.

This is the home the prompt asked for as backend/nodes/{courtyard_generator,
patio_generator,facade_orientation_tools,daylight_modifier}.py — gathered into one
module because they share the same geometry helpers and this project keeps runtime
logic under connection/notebook_logic/ (thin, shapely-based, no duplicate engine).
"""
from __future__ import annotations

from typing import Any

# Unit vectors for TRUE geographic directions in the local metric frame (+y = north).
DIRECTION_VECTORS = {
    "north": (0.0, 1.0), "south": (0.0, -1.0),
    "east": (1.0, 0.0), "west": (-1.0, 0.0),
    "northeast": (0.7071, 0.7071), "northwest": (-0.7071, 0.7071),
    "southeast": (0.7071, -0.7071), "southwest": (-0.7071, -0.7071),
}


def _poly(boundary: list[list[float]]):
    from shapely.geometry import Polygon

    return Polygon([(float(p[0]), float(p[1])) for p in boundary if len(p) >= 2])


def _rings(geom) -> dict[str, Any]:
    """Normalize a shapely (multi)polygon into {outer:[[x,y]...], holes:[[...],...]}.
    On a MultiPolygon (op split the building) we keep the largest piece."""
    from shapely.geometry import MultiPolygon, Polygon

    if isinstance(geom, MultiPolygon):
        geom = max(geom.geoms, key=lambda g: g.area)
    if not isinstance(geom, Polygon) or geom.is_empty:
        return {"outer": [], "holes": []}
    outer = [[round(x, 3), round(y, 3)] for x, y in geom.exterior.coords]
    holes = [[[round(x, 3), round(y, 3)] for x, y in ring.coords] for ring in geom.interiors]
    return {"outer": outer, "holes": holes}


def _centroid(boundary: list[list[float]]) -> tuple[float, float]:
    pts = [(float(p[0]), float(p[1])) for p in boundary if len(p) >= 2]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _extent(boundary):
    xs = [float(p[0]) for p in boundary if len(p) >= 2]
    ys = [float(p[1]) for p in boundary if len(p) >= 2]
    return (max(xs) - min(xs), max(ys) - min(ys), min(xs), min(ys), max(xs), max(ys))


def _principal_angle(boundary) -> float:
    """Orientation (degrees) of the footprint's LONGEST edge — the building's long axis.
    Used to carve a courtyard in the building's own frame so the void is a clean
    rectangle aligned to the walls even when the footprint is rotated."""
    import math
    pts = [(float(p[0]), float(p[1])) for p in boundary if len(p) >= 2]
    if len(pts) < 2:
        return 0.0
    best_len, best_ang = -1.0, 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        d = math.hypot(x2 - x1, y2 - y1)
        if d > best_len:
            best_len = d
            best_ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return best_ang


def _scale_about(poly, f: float, origin):
    """Scale a shapely polygon uniformly about a point (origin = shapely Point)."""
    from shapely.affinity import scale as _scale
    return _scale(poly, xfact=f, yfact=f, origin=(origin.x, origin.y))


# --------------------------------------------------------------------------- #
# courtyard_generator
# --------------------------------------------------------------------------- #
def carve_courtyard(boundary, holes=None, *, fraction: float = 0.3) -> dict[str, Any]:
    """Subtract a central rectangular void sized `fraction` of the footprint's
    bounding box, leaving a perimeter wall thickness so it stays a valid building.
    Turns a solid block into an O/courtyard for daylight to the core."""
    try:
        from shapely.geometry import Polygon

        # If a courtyard already exists (e.g. a "more daylight" prompt added a small one),
        # REPLACE it with a fresh, clean, full bottom-to-top rectangle rather than refusing
        # — so "add courtyard" always gives the clear rectangular cutout the user wants.
        # We drop existing holes here and carve one clean court below.
        holes = None
        outer = _poly(boundary)
        if outer.area < 1:
            return {"ok": False, "reason": "footprint too small to carve a courtyard"}
        w, h, minx, miny, maxx, maxy = _extent(boundary)
        short = min(w, h)
        if short < 16:
            return {"ok": False, "reason": "footprint too shallow for a courtyard (needs ≥ ~16 m across)"}
        from shapely.affinity import rotate as _rot
        from shapely.geometry import Polygon

        # CLEAN RECTANGULAR void. A negative buffer (the old approach) produced a pinched
        # "hourglass/bowtie" opening on a normal rectangle (and got worse when scaled), so
        # instead we build a proper axis-aligned RECTANGLE in the centre of the footprint,
        # sized so its area is ~`fraction` of the floor, leaving a wall of ≥6 m all round.
        # To stay correct on a ROTATED footprint we carve in the building's OWN frame:
        # de-rotate by the footprint's principal angle, cut the rectangle, re-rotate back.
        ang = _principal_angle(boundary)            # building's long-axis orientation (deg)
        oc = outer.centroid
        local = _rot(outer, -ang, origin=oc)        # axis-align the footprint
        lminx, lminy, lmaxx, lmaxy = local.bounds
        lw, lh = lmaxx - lminx, lmaxy - lminy
        # SQUARE courtyard, centred. Sizing both sides off the SHORTER building dimension
        # makes the void roughly square instead of a long thin slot (which is what you get
        # if each side is just a % of its own axis: a 140×26 building gave a 63×12 slot).
        # The square is ~55% of the short side, capped so it can't be wider than ~45% of
        # the long side (always leaves a real wall all around). A clean 4-corner court.
        short = min(lw, lh)
        side = max(6.0, min(short * 0.55, lw * 0.45, lh * 0.85))
        vw = vh = side
        if vw < 5 or vh < 5:
            return {"ok": False, "reason": "footprint too narrow to carve a courtyard"}
        # Position the courtyard at the building's centre of mass (centroid). For a
        # symmetric I/U/O this is the exact middle (offset 0). For an L/asymmetric shape
        # the geometric "middle" falls in the empty notch, so the centroid (which sits in
        # the solid mass) is the right, architecturally-sensible placement — a courtyard
        # can only sit where there's actually a building.
        cx, cy = oc.x, oc.y
        rect_local = Polygon([
            (cx - vw / 2, cy - vh / 2), (cx + vw / 2, cy - vh / 2),
            (cx + vw / 2, cy + vh / 2), (cx - vw / 2, cy + vh / 2),
        ])
        void = _rot(rect_local, ang, origin=oc)      # rotate the clean rectangle back
        # Define the SAFE interior = footprint inset by a ~6 m wall. The courtyard must sit
        # inside this so a wall always remains. For a convex rectangle the void already fits;
        # for a CONCAVE shape (U / L / H / twisted) a centred rectangle pokes into the notch,
        # so we (a) shrink it to fit if possible, else (b) INTERSECT it with the safe interior
        # so it still carves the largest clean rectangular court that fits — never just fails.
        # join_style=2 (mitre) keeps the inset corners SHARP. The default round join
        # rounded the safe-region corners, and when the courtyard rectangle got clipped to
        # that region it inherited a curved corner (the "courtyard isn't a rectangle" bug).
        # 6 m inset keeps the courtyard clear of the building's own edges/notches, so it
        # stays a CLEAN 4-corner rectangle (a thinner inset let the void touch a notched
        # edge → it inherited a bump). For a concave shape (U/L/H) where the centred
        # rectangle still pokes out, SHRINK it uniformly to fit (keeps it a rectangle) —
        # only clip as a last resort.
        safe = outer.buffer(-6.0, join_style=2, mitre_limit=5.0)
        if safe.geom_type == "MultiPolygon" and not safe.is_empty:
            safe = max(safe.geoms, key=lambda g: g.area)
        if not (safe and not safe.is_empty and safe.contains(void)):
            if not (safe and not safe.is_empty):
                return {"ok": False, "reason": "footprint too narrow to carve a courtyard that leaves a wall"}
            placed = None
            for f in (0.9, 0.8, 0.7, 0.6, 0.5, 0.4):
                cand = _scale_about(void, f, oc)
                # accept only if it stays a reasonable size (≥40% of the original area) —
                # otherwise a notched shape shrinks the rectangle to a thin sliver.
                if safe.contains(cand) and cand.area >= void.area * 0.40:
                    placed = cand; break
            if placed is not None:
                void = placed                       # clean rectangle, scaled to fit
            else:
                clip = void.intersection(safe)      # concave shape → clip to the interior
                if clip.geom_type == "MultiPolygon" and not clip.is_empty:
                    clip = max(clip.geoms, key=lambda g: g.area)
                if clip and not clip.is_empty and clip.area >= 16:
                    void = clip
                else:
                    return {"ok": False, "reason": "footprint too narrow to carve a courtyard that leaves a wall"}
        result = _apply_existing_holes(outer, holes).difference(void)
        rings = _rings(result)
        if not rings["outer"] or not rings["holes"]:
            return {"ok": False, "reason": "couldn't carve a courtyard that leaves a valid building"}
        rings["ok"] = True
        rings["reason"] = f"carved a central courtyard void (~{round(void.area)} m²)"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"courtyard op failed: {exc}"}


# --------------------------------------------------------------------------- #
# patio_generator
# --------------------------------------------------------------------------- #
def carve_patio(boundary, holes=None, *, direction: str = "south", fraction: float = 0.2) -> dict[str, Any]:
    """Subtract a void set toward a TRUE geographic side (a patio/open recess on
    that side). `direction` is north/south/east/west/etc. — geographic, not screen."""
    try:
        from shapely.geometry import Polygon

        ux, uy = DIRECTION_VECTORS.get(direction.lower(), DIRECTION_VECTORS["south"])
        outer = _poly(boundary)
        if outer.area < 1:
            return {"ok": False, "reason": "footprint too small for a patio"}
        cx, cy = outer.centroid.x, outer.centroid.y
        w, h, *_ = _extent(boundary)
        pw = max(3.0, min(w, h) * fraction)
        # offset the patio center toward the requested side
        ox = cx + ux * (w / 2 - pw / 2) * 0.9
        oy = cy + uy * (h / 2 - pw / 2) * 0.9
        void = Polygon([
            (ox - pw / 2, oy - pw / 2), (ox + pw / 2, oy - pw / 2),
            (ox + pw / 2, oy + pw / 2), (ox - pw / 2, oy + pw / 2),
        ])
        result = _apply_existing_holes(outer, holes).difference(void)
        rings = _rings(result)
        if not rings["outer"]:
            return {"ok": False, "reason": "patio would consume the footprint"}
        rings["ok"] = True
        rings["reason"] = f"opened a {direction} patio (~{round(void.area)} m²)"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"patio op failed: {exc}"}


# --------------------------------------------------------------------------- #
# facade_orientation_tools
# --------------------------------------------------------------------------- #
def lengthen_side(boundary, holes=None, *, direction: str = "north", amount_pct: float = 0.2) -> dict[str, Any]:
    """Extend the footprint outward on a TRUE geographic side, lengthening the
    facade there. Implemented as a union with a rectangle grown off that side."""
    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union

        ux, uy = DIRECTION_VECTORS.get(direction.lower(), DIRECTION_VECTORS["north"])
        outer = _poly(boundary)
        w, h, minx, miny, maxx, maxy = _extent(boundary)
        cx, cy = outer.centroid.x, outer.centroid.y
        # extension slab: full width of the relevant side, depth = amount_pct of the
        # perpendicular dimension.
        if abs(uy) > abs(ux):  # north/south → extend in y, slab spans x
            depth = max(3.0, h * amount_pct)
            y0 = maxy if uy > 0 else miny - depth
            slab = Polygon([(minx, y0), (maxx, y0), (maxx, y0 + depth), (minx, y0 + depth)])
        else:  # east/west → extend in x, slab spans y
            depth = max(3.0, w * amount_pct)
            x0 = maxx if ux > 0 else minx - depth
            slab = Polygon([(x0, miny), (x0 + depth, miny), (x0 + depth, maxy), (x0, maxy)])
        merged = unary_union([_apply_existing_holes(outer, holes), slab])
        rings = _rings(merged)
        if not rings["outer"]:
            return {"ok": False, "reason": "could not extend that side"}
        rings["ok"] = True
        rings["reason"] = f"lengthened the {direction} facade (+{round(depth)} m)"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"facade op failed: {exc}"}


# --------------------------------------------------------------------------- #
# wing_scaler — enlarge/shrink the WING on a given true geographic side
# --------------------------------------------------------------------------- #
def enlarge_wing(boundary, holes=None, *, direction: str = "east", factor: float = 1.3) -> dict[str, Any]:
    """Make the wing on a TRUE geographic side bigger (or smaller if factor<1).
    Splits the footprint by the line through the centroid PERPENDICULAR to the
    requested direction, then scales only the half on that side AWAY from the
    centroid along the direction axis. So "make the east wing bigger" stretches the
    east portion eastward, leaving the rest in place. Direction is geographic
    (north/south/east/west/…), never screen 'right/left'."""
    try:
        from shapely.affinity import scale as _scale
        from shapely.geometry import Polygon
        from shapely.ops import unary_union

        ux, uy = DIRECTION_VECTORS.get(direction.lower(), DIRECTION_VECTORS["east"])
        outer = _poly(boundary)
        if outer.area < 1:
            return {"ok": False, "reason": "footprint too small to edit a wing"}
        cx, cy = outer.centroid.x, outer.centroid.y
        w, h, minx, miny, maxx, maxy = _extent(boundary)
        big = max(w, h) * 4 + 100  # half-plane size

        # Half-plane covering the side toward (ux,uy): a big rectangle on that side
        # of the centroid, perpendicular split. Build it by offsetting a huge box.
        # Perpendicular axis to (ux,uy):
        px, py = -uy, ux
        # rectangle corners: from centroid, out along +dir to `big`, spanning ±big on perp
        c0 = (cx + px * big, cy + py * big)
        c1 = (cx - px * big, cy - py * big)
        c2 = (cx - px * big + ux * big, cy - py * big + uy * big)
        c3 = (cx + px * big + ux * big, cy + py * big + uy * big)
        sideHalf = Polygon([c0, c1, c2, c3])

        wing = outer.intersection(sideHalf)         # the part on the requested side
        rest = outer.difference(sideHalf)           # everything else, untouched
        if wing.is_empty:
            return {"ok": False, "reason": f"no {direction} wing to resize"}

        # Scale the wing AWAY from the centroid along the direction axis. We scale the
        # whole wing about the centroid but only along (ux,uy): approximate by scaling
        # x or y when the direction is axis-aligned (the common case), else uniform.
        if abs(ux) > abs(uy):     # east/west → scale x
            grown = _scale(wing, xfact=factor, yfact=1.0, origin=(cx, cy))
        elif abs(uy) > abs(ux):   # north/south → scale y
            grown = _scale(wing, xfact=1.0, yfact=factor, origin=(cx, cy))
        else:                      # diagonal → uniform from centroid
            grown = _scale(wing, xfact=factor, yfact=factor, origin=(cx, cy))

        merged = unary_union([rest, grown])
        rings = _rings(_apply_existing_holes(merged, holes))
        if not rings["outer"]:
            return {"ok": False, "reason": "wing resize produced no valid footprint"}
        verb = "enlarged" if factor >= 1 else "reduced"
        rings["ok"] = True
        rings["reason"] = f"{verb} the {direction} wing (×{round(factor, 2)})"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"wing op failed: {exc}"}


# --------------------------------------------------------------------------- #
# daylight_modifier
# --------------------------------------------------------------------------- #
def reduce_depth(boundary, holes=None, *, amount_pct: float = 0.15) -> dict[str, Any]:
    """Shrink the footprint along its SHORT axis only (a shallower floor plate so
    daylight reaches deeper), preserving the long facade length."""
    try:
        outer = _poly(boundary)
        cx, cy = outer.centroid.x, outer.centroid.y
        w, h, *_ = _extent(boundary)
        # short axis is the smaller of w/h
        sx = 1.0 - amount_pct if w <= h else 1.0
        sy = 1.0 - amount_pct if h < w else 1.0
        from shapely.affinity import scale as _scale

        # Scale the ASSEMBLED polygon (outer WITH its existing holes) as one, so a
        # courtyard/patio void shrinks WITH the boundary and stays inside it. Scaling
        # only the outer and re-subtracting the original-size hole made the void poke
        # out as a notch when the plate got shallower — that was the misalignment.
        assembled = _apply_existing_holes(outer, holes)
        result = _scale(assembled, xfact=sx, yfact=sy, origin=(cx, cy))
        rings = _rings(result)
        rings["ok"] = bool(rings["outer"])
        rings["reason"] = f"reduced building depth by {round(amount_pct * 100)}%"
        if not rings["ok"]:
            rings["reason"] = "depth reduction failed"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"depth op failed: {exc}"}


def align_facade(boundary, holes=None, *, direction: str = "north") -> dict[str, Any]:
    """Rotate the whole footprint so its LONGEST edge (the 'long facade') faces the
    given true direction. "align long facade to north" → the long side ends up
    perpendicular to north, i.e. the facade looks north. Rotation is about the
    centroid so the building stays in place; returns the new outer ring (+ holes)."""
    try:
        import math

        from shapely.affinity import rotate as _rotate

        outer = _poly(boundary)
        if outer.area < 1:
            return {"ok": False, "reason": "footprint too small to align"}
        cx, cy = outer.centroid.x, outer.centroid.y

        # Find the longest edge of the footprint and its current angle.
        ring = list(outer.exterior.coords)
        longest = 0.0
        edge_ang = 0.0
        for i in range(len(ring) - 1):
            x1, y1 = ring[i]
            x2, y2 = ring[i + 1]
            d = math.hypot(x2 - x1, y2 - y1)
            if d > longest:
                longest = d
                edge_ang = math.degrees(math.atan2(y2 - y1, x2 - x1))

        # Target: the FACADE (long edge) should FACE `direction`. A facade faces the
        # direction of its outward normal, which is perpendicular to the edge. So the
        # edge itself must be perpendicular to the target direction vector.
        ux, uy = DIRECTION_VECTORS.get(direction.lower(), DIRECTION_VECTORS["north"])
        facing_ang = math.degrees(math.atan2(uy, ux))   # direction the facade should face
        target_edge_ang = facing_ang + 90.0             # edge is perpendicular to facing
        # Smallest rotation that brings the long edge onto the target line (mod 180,
        # since an edge and its reverse are the same line).
        delta = (target_edge_ang - edge_ang + 90.0) % 180.0 - 90.0

        rotated = _rotate(outer, delta, origin=(cx, cy))
        result = _apply_existing_holes(rotated, holes)
        rings = _rings(result)
        rings["ok"] = bool(rings["outer"])
        rings["reason"] = f"aligned the long facade to face {direction} (rotated {round(delta, 1)}°)"
        rings["rotation_applied"] = round(delta, 2)
        if not rings["ok"]:
            rings["reason"] = "facade alignment failed"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"facade alignment failed: {exc}"}


def _buildable_extent(site_boundary, building_type=None):
    """Return (smin_x, smin_y, smax_x, smax_y, buildable_shape) for the SITE MINUS the
    real setback — the same buildable area the self-debug validator enforces. This is
    what the literal 'move to <edge>/<corner>' placements must snap to so the building
    never lands inside the setback zone (the 'going outside the setback' bug). Falls back
    to the raw site bbox with a 5 m guard when setback rules are unavailable."""
    try:
        from . import setback_rules as _sr

        _ba = _sr.create_buildable_area(site_boundary, building_type=building_type or "residential")
        if _ba is not None and not _ba.is_empty:
            xs, ys = _ba.exterior.coords.xy
            return (min(xs), min(ys), max(xs), max(ys), _ba)
    except Exception:  # noqa: BLE001
        pass
    # Fallback: raw site bbox inset by a uniform 5 m guard.
    _, _, smin_x, smin_y, smax_x, smax_y = _extent(site_boundary)
    g = 5.0
    return (smin_x + g, smin_y + g, smax_x - g, smax_y - g, None)


def _fits_buildable(ring, buildable_shape, site_boundary) -> bool:
    """Strict containment of `ring` inside the buildable area (matches the validator).
    Falls back to the raw site when no buildable polygon is available."""
    try:
        from shapely.geometry import Polygon as _P

        rp = _P([(p[0], p[1]) for p in ring])
        if buildable_shape is not None:
            return buildable_shape.buffer(0.05).contains(rp)
        sp = _P([(p[0], p[1]) for p in site_boundary])
        return sp.buffer(0.05).contains(rp)
    except Exception:  # noqa: BLE001
        return True


# Corner name -> which extreme of the SITE bounding box the building hugs.
# +x = east, +y = north (local metric frame). Each corner is an (x_side, y_side)
# pick from {"min","max"}.
_CORNER_SIDES: dict[str, tuple[str, str]] = {
    "northeast": ("max", "max"), "ne": ("max", "max"), "top right": ("max", "max"), "topright": ("max", "max"),
    "northwest": ("min", "max"), "nw": ("min", "max"), "top left": ("min", "max"), "topleft": ("min", "max"),
    "southeast": ("max", "min"), "se": ("max", "min"), "bottom right": ("max", "min"), "bottomright": ("max", "min"),
    "southwest": ("min", "min"), "sw": ("min", "min"), "bottom left": ("min", "min"), "bottomleft": ("min", "min"),
}


def place_at_corner(
    boundary, holes=None, *, corner: str = "northeast",
    site_boundary: list[list[float]] | None = None, margin: float = 5.0,
    building_type: str | None = None,
) -> dict[str, Any]:
    """Translate the building so it sits AT the named corner of the site, snapped to the
    BUILDABLE area (site minus the REAL setback) so it never lands inside the setback
    zone. Pure translation — the footprint shape/rotation is preserved; only its position
    changes. Returns the moved outer ring (+ holes) and the dx/dy applied."""
    try:
        if not site_boundary or len(site_boundary) < 3:
            return {"ok": False, "reason": "no site boundary to place against"}
        sides = _CORNER_SIDES.get(corner.lower().strip())
        if not sides:
            return {"ok": False, "reason": f"unknown corner '{corner}'"}

        # Snap targets come from the BUILDABLE bbox (setback already baked in), not the raw
        # site + a guessed margin. This is what keeps the building inside the setback.
        smin_x, smin_y, smax_x, smax_y, buildable_shape = _buildable_extent(site_boundary, building_type)
        _, _, bmin_x, bmin_y, bmax_x, bmax_y = _extent(boundary)

        x_side, y_side = sides
        # Target the building's matching corner onto the buildable-area corner (no extra
        # margin — the setback is already inset into the buildable bbox).
        if x_side == "max":   # east: align building's right edge to buildable right
            dx = smax_x - bmax_x
        else:                 # west
            dx = smin_x - bmin_x
        if y_side == "max":   # north
            dy = smax_y - bmax_y
        else:                 # south
            dy = smin_y - bmin_y

        # If the building is wider/deeper than the buildable area on an axis, snapping both
        # extremes is impossible — clamp the move to whatever keeps it inside, and pull back
        # if a corner pokes out of an irregular (rotated) buildable polygon.
        full = [[p[0] + dx, p[1] + dy] for p in boundary]
        if not _fits_buildable(full, buildable_shape, site_boundary):
            best = 0.0
            for f in (0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1):
                cand = [[p[0] + dx * f, p[1] + dy * f] for p in boundary]
                if _fits_buildable(cand, buildable_shape, site_boundary):
                    best = f
                    break
            dx, dy = dx * best, dy * best

        # HONESTY: already at that corner → ~0 displacement → don't claim a move.
        if (dx * dx + dy * dy) ** 0.5 < 0.5:
            return {"ok": False, "dx": 0.0, "dy": 0.0,
                    "reason": f"the building is already at the {corner} corner — it can't move further that way.",
                    "suggestion": "it's already as far as the setback allows; try a different corner"}

        from shapely.affinity import translate as _translate

        moved = _translate(_poly(boundary), xoff=dx, yoff=dy)
        result = _apply_existing_holes(moved, [_shift_ring(h, dx, dy) for h in (holes or [])])
        rings = _rings(result)
        rings["ok"] = bool(rings["outer"])
        rings["dx"] = round(dx, 2)
        rings["dy"] = round(dy, 2)
        rings["reason"] = f"placed the building at the {corner} corner of the site"
        if not rings["ok"]:
            rings["reason"] = "corner placement failed"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"corner placement failed: {exc}"}


def place_at_edge(
    boundary, holes=None, *, direction: str = "north",
    site_boundary: list[list[float]] | None = None, margin: float = 5.0,
    building_type: str | None = None,
) -> dict[str, Any]:
    """Translate the building so it hugs the named SITE edge (north/south/east/west),
    snapped to the BUILDABLE area (site minus the REAL setback) so it never lands inside
    the setback zone. Keeps its position on the perpendicular axis. Pure translation;
    shape preserved."""
    try:
        if not site_boundary or len(site_boundary) < 3:
            return {"ok": False, "reason": "no site boundary to place against"}
        d = direction.lower().strip()
        # Snap targets = BUILDABLE bbox (setback baked in), not raw site + a guessed margin.
        smin_x, smin_y, smax_x, smax_y, buildable_shape = _buildable_extent(site_boundary, building_type)
        _, _, bmin_x, bmin_y, bmax_x, bmax_y = _extent(boundary)
        dx = dy = 0.0
        if d in ("north", "top"):
            dy = smax_y - bmax_y
        elif d in ("south", "bottom"):
            dy = smin_y - bmin_y
        elif d in ("east", "right"):
            dx = smax_x - bmax_x
        elif d in ("west", "left"):
            dx = smin_x - bmin_x
        else:
            return {"ok": False, "reason": f"unknown edge '{direction}'"}

        # Pull back if the full snap pokes a corner out of an irregular buildable polygon.
        full = [[p[0] + dx, p[1] + dy] for p in boundary]
        if not _fits_buildable(full, buildable_shape, site_boundary):
            best = 0.0
            for f in (0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1):
                cand = [[p[0] + dx * f, p[1] + dy * f] for p in boundary]
                if _fits_buildable(cand, buildable_shape, site_boundary):
                    best = f
                    break
            dx, dy = dx * best, dy * best

        # HONESTY: if the building is already at that edge, the displacement is ~0.
        # Don't claim a move that didn't happen — report it can't move further.
        if (dx * dx + dy * dy) ** 0.5 < 0.5:
            return {"ok": False, "dx": 0.0, "dy": 0.0,
                    "reason": f"the building is already at the {direction} edge — it can't move further {direction}.",
                    "suggestion": "it's already as far as the setback allows; try a different direction"}

        from shapely.affinity import translate as _translate

        moved = _translate(_poly(boundary), xoff=dx, yoff=dy)
        result = _apply_existing_holes(moved, [_shift_ring(h, dx, dy) for h in (holes or [])])
        rings = _rings(result)
        rings["ok"] = bool(rings["outer"])
        rings["dx"] = round(dx, 2)
        rings["dy"] = round(dy, 2)
        rings["reason"] = f"placed the building against the {direction} edge of the site"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"edge placement failed: {exc}"}


def stretch_mass(boundary, holes=None, *, axis: str = "x", factor: float = 1.25) -> dict[str, Any]:
    """Anisotropic scale along ONE axis about the centroid — "stretch it horizontally"
    (axis x), "make it taller/slimmer" via the plate stack, "wider and lower". Unlike
    a uniform scale this changes proportion, not just size."""
    try:
        from shapely.affinity import scale as _scale

        outer = _poly(boundary)
        cx, cy = outer.centroid.x, outer.centroid.y
        xf = factor if axis in ("x", "horizontal", "ew", "width") else 1.0
        yf = factor if axis in ("y", "vertical", "ns", "depth") else 1.0
        # Scale outer WITH its holes together so a courtyard void stays inside the mass
        # (not re-applied at original size, which would push it outside the new boundary).
        result = _scale(_apply_existing_holes(outer, holes), xfact=xf, yfact=yf, origin=(cx, cy))
        rings = _rings(result)
        rings["ok"] = bool(rings["outer"])
        verb = "stretched" if factor >= 1 else "compressed"
        rings["reason"] = f"{verb} the mass along {axis} (×{round(factor, 2)})"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"stretch op failed: {exc}"}


def articulate_facade(boundary, holes=None, *, direction: str = "south", depth_pct: float = 0.08,
                      count: int = 3) -> dict[str, Any]:
    """Break up a flat facade with rhythmic RECESSES along the named side — "the facade
    feels too flat", "add recesses and projections", "break up the long facade". Carves
    `count` shallow notches into that edge so the facade reads articulated, not flat."""
    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union

        ux, uy = DIRECTION_VECTORS.get(direction.lower(), DIRECTION_VECTORS["south"])
        outer = _poly(boundary)
        w, h, minx, miny, maxx, maxy = _extent(boundary)
        # The facade runs perpendicular to the direction; carve notches across its span.
        depth = max(1.5, min(w, h) * depth_pct)
        notches = []
        if abs(ux) > abs(uy):   # east/west facade — vertical run, notch in x
            edge_x = maxx if ux > 0 else minx
            span = h
            for k in range(count):
                cy0 = miny + span * (k + 0.5) / count
                half = span / (count * 3)
                x0 = edge_x - depth if ux > 0 else edge_x
                notches.append(Polygon([(x0, cy0 - half), (x0 + depth, cy0 - half),
                                        (x0 + depth, cy0 + half), (x0, cy0 + half)]))
        else:                   # north/south facade — horizontal run, notch in y
            edge_y = maxy if uy > 0 else miny
            span = w
            for k in range(count):
                cx0 = minx + span * (k + 0.5) / count
                half = span / (count * 3)
                y0 = edge_y - depth if uy > 0 else edge_y
                notches.append(Polygon([(cx0 - half, y0), (cx0 + half, y0),
                                        (cx0 + half, y0 + depth), (cx0 - half, y0 + depth)]))
        carved = outer.difference(unary_union(notches))
        result = _apply_existing_holes(carved, holes)
        rings = _rings(result)
        rings["ok"] = bool(rings["outer"])
        rings["reason"] = f"articulated the {direction} facade with {count} recesses"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"facade articulation failed: {exc}"}


def chamfer_corners(boundary, holes=None, *, amount_pct: float = 0.12, mode: str = "chamfer") -> dict[str, Any]:
    """Soften ("add curvature"/"make geometry softer") or sharpen the silhouette. mode
    'chamfer'/'round' bevels the corners (sculptural, iconic); 'sharpen' is the inverse
    (a small negative-then-positive buffer to crisp the outline)."""
    try:
        outer = _poly(boundary)
        w, h, *_ = _extent(boundary)
        r = max(1.0, min(w, h) * amount_pct)
        if mode in ("round", "soft", "curve", "organic"):
            geom = outer.buffer(-r, join_style=1).buffer(r * 1.0, join_style=1)  # round joins
        elif mode in ("sharpen", "sharp", "crisp"):
            geom = outer.buffer(r * 0.5, join_style=2).buffer(-r * 0.5, join_style=2)  # mitre
        else:  # chamfer (bevel)
            geom = outer.buffer(-r, join_style=2).buffer(r, join_style=1)
        if geom.is_empty or geom.area <= 0:
            return {"ok": False, "reason": "corner adjustment collapsed the footprint"}
        result = _apply_existing_holes(geom, holes)
        rings = _rings(result)
        rings["ok"] = bool(rings["outer"])
        rings["reason"] = f"{mode}ed the building corners"
        return rings
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"corner op failed: {exc}"}


def _shift_ring(ring, dx, dy):
    return [[float(p[0]) + dx, float(p[1]) + dy] for p in (ring or []) if len(p) >= 2]


def _apply_existing_holes(outer, holes):
    """Re-subtract any pre-existing holes so a second op (e.g. patio after courtyard)
    doesn't lose the earlier void."""
    if not holes:
        return outer
    from shapely.geometry import Polygon

    geom = outer
    for h in holes:
        if h and len(h) >= 3:
            try:
                geom = geom.difference(Polygon([(p[0], p[1]) for p in h]))
            except Exception:  # noqa: BLE001
                pass
    return geom
