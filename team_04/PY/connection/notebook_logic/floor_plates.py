"""Floor-plate model — represent a building as a vertical stack of floor plates so
ANY floor-level manipulation (move bottom N floors toward an edge, add floors to one
wing only, podium/tower splits) becomes a uniform operation on the plate list.

A building's massing has historically been a single extruded footprint + a `floors`
count + `height_m`. That can't express "move the bottom 5 floors toward the north
edge" or "add 2 floors to the right wing only", because there's no per-floor geometry
to move. This module adds that geometry:

    floor_plates: [
      {"level": 0, "footprint": [[x,y],...], "z_base": 0.0,  "height": 3.0, "wing": "right"},
      {"level": 1, "footprint": [[x,y],...], "z_base": 3.0,  "height": 3.0, "wing": "right"},
      ...
    ]

Each plate is an independent footprint at a Z height, so the viewer extrudes each
plate separately and a manipulation can touch a subset (a level range, or the plates
belonging to one wing) without disturbing the rest.

Pure geometry (shapely for translate/contains); no LLM, no I/O. Used by the
manipulation tools + feedback route, and surfaced through BuildingInfo so the viewer
can extrude per-plate.
"""
from __future__ import annotations

from typing import Any

DEFAULT_FLOOR_HEIGHT_M = 3.0


# --------------------------------------------------------------------------- #
# Build / read the plate stack
# --------------------------------------------------------------------------- #
def build_floor_plates(
    footprint: list[list[float]],
    floors: int,
    *,
    floor_height: float = DEFAULT_FLOOR_HEIGHT_M,
    wings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Create the initial plate stack: `floors` identical plates of `footprint`,
    stacked from z=0 up. If `wings` are given, each plate also records which wing
    footprints make it up (so per-wing floor edits can target them)."""
    fp = _clean_ring(footprint)
    if len(fp) < 3 or floors < 1:
        return []
    wing_fps = _wing_footprints(wings)
    plates: list[dict[str, Any]] = []
    for level in range(floors):
        plate = {
            "level": level,
            "footprint": [list(p) for p in fp],
            "z_base": round(level * floor_height, 3),
            "height": float(floor_height),
        }
        # Per-wing sub-footprints for this level (so "add floors to right wing" can
        # later raise only the right-wing plates).
        if wing_fps:
            plate["wing_footprints"] = {role: [list(p) for p in ring] for role, ring in wing_fps.items()}
        plates.append(plate)
    return plates


def ensure_floor_plates(building: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the building's plate stack, building it lazily from footprint+floors if
    it doesn't have one yet. Never mutates `building`."""
    existing = building.get("floor_plates")
    if isinstance(existing, list) and existing:
        return [dict(p) for p in existing]
    footprint = building.get("boundary") or building.get("building_boundary") or building.get("footprint") or []
    floors = int(building.get("floors") or max(1, round(float(building.get("height_m") or 12.0) / DEFAULT_FLOOR_HEIGHT_M)))
    fh = float(building.get("floor_height_m") or DEFAULT_FLOOR_HEIGHT_M)
    return build_floor_plates(footprint, floors, floor_height=fh, wings=building.get("wings"))


# --------------------------------------------------------------------------- #
# Operations on the plate stack
# --------------------------------------------------------------------------- #
def select_levels(
    plates: list[dict[str, Any]],
    *,
    bottom: int | None = None,
    top: int | None = None,
    level_from: int | None = None,
    level_to: int | None = None,
) -> list[int]:
    """Resolve a human level selection into concrete plate indices.
    - bottom=N  -> the lowest N levels
    - top=N     -> the highest N levels
    - level_from/level_to -> an explicit inclusive range
    Returns a sorted list of level indices that exist in `plates`."""
    n = len(plates)
    if n == 0:
        return []
    levels = sorted(p["level"] for p in plates)
    if bottom is not None:
        return levels[: max(0, min(bottom, n))]
    if top is not None:
        return levels[max(0, n - top):]
    if level_from is not None or level_to is not None:
        lo = level_from if level_from is not None else levels[0]
        hi = level_to if level_to is not None else levels[-1]
        return [lv for lv in levels if lo <= lv <= hi]
    return levels  # default: all


def move_levels(
    plates: list[dict[str, Any]],
    level_indices: list[int],
    dx: float,
    dy: float,
    *,
    site_boundary: list[list[float]] | None = None,
) -> dict[str, Any]:
    """Translate the footprints of the given levels by (dx, dy). Used for
    "move the bottom 5 floors toward the north edge" — only those plates shift,
    the rest of the stack stays put. Validated against the site if provided."""
    if not plates:
        return {"ok": False, "reason": "Building has no floor plates."}
    targets = set(level_indices)
    new_plates: list[dict[str, Any]] = []
    moved_any = False
    for p in plates:
        np = dict(p)
        if p["level"] in targets:
            np["footprint"] = _translate(p["footprint"], dx, dy)
            if "wing_footprints" in p:
                np["wing_footprints"] = {r: _translate(ring, dx, dy) for r, ring in p["wing_footprints"].items()}
            moved_any = True
        new_plates.append(np)
    if not moved_any:
        return {"ok": False, "reason": "No matching floors to move."}
    # Site-fit check: every moved plate must stay inside the site.
    if site_boundary and len(site_boundary) >= 3:
        for p in new_plates:
            if p["level"] in targets and not _ring_in_site(p["footprint"], site_boundary):
                return {
                    "ok": False,
                    "reason": "Those floors would extend outside the site boundary.",
                    "suggestion": "Move a smaller distance, or fewer floors.",
                }
    return {"ok": True, "floor_plates": new_plates, "moved_levels": sorted(targets)}


def add_floors(
    plates: list[dict[str, Any]],
    n: int,
    *,
    wing: str | None = None,
    floor_height: float = DEFAULT_FLOOR_HEIGHT_M,
) -> dict[str, Any]:
    """Add `n` floors on top of the stack. If `wing` is given, the new plates use ONLY
    that wing's footprint (so "add 2 floors on the right wing" raises just the right
    wing, not the whole building). Without `wing`, full-footprint plates are added."""
    if n == 0:
        return {"ok": False, "reason": "No floor count given."}
    base = list(plates)
    if not base:
        return {"ok": False, "reason": "Building has no floor plates to extend."}
    top_plate = max(base, key=lambda p: p["level"])
    top_level = top_plate["level"]
    z = top_plate["z_base"] + top_plate["height"]

    if n < 0:
        # Remove the top |n| plates (optionally only wing plates).
        to_remove = abs(n)
        if wing:
            wing_levels = [p["level"] for p in base if _plate_is_wing(p, wing)]
            drop = set(sorted(wing_levels)[-to_remove:])
        else:
            drop = set(sorted(p["level"] for p in base)[-to_remove:])
        kept = [dict(p) for p in base if p["level"] not in drop]
        if not kept:
            return {"ok": False, "reason": "Can't remove all floors."}
        return {"ok": True, "floor_plates": _renumber(kept), "added": -len(drop)}

    # Determine the footprint for the new plates.
    if wing:
        # Look up the wing ring from ANY plate that still carries the full
        # wing_footprints map (the base/ground plates do). The current top plate may
        # be a previously-added single-wing plate with no wing_footprints, which is
        # why a second per-wing add used to fail ("No '<wing>' wing to add floors to").
        wing_ring = None
        for p in sorted(base, key=lambda q: q["z_base"]):
            wing_ring = _wing_ring_from_plate(p, wing)
            if wing_ring:
                break
        if not wing_ring:
            # The named wing doesn't exist on this shape. Collect the wings that DO,
            # with each wing's footprint (to resolve a DIRECTION to the actual wing).
            available: list[str] = []
            wing_rings: dict[str, list] = {}
            for p in base:
                for r, ring in (p.get("wing_footprints") or {}).items():
                    if r not in available:
                        available.append(r); wing_rings[r] = ring
            # DIRECTIONAL wing names: the user says "left/right/north/south/front/back"
            # but the shape's wings are named differently (e.g. L-shape → vertical /
            # horizontal). Map the direction to the wing that sits FURTHEST that way, so
            # "add floors on the left wing" works on any multi-wing shape.
            _dirword = (wing or "").lower()
            if _dirword in ("left", "right", "north", "south", "east", "west", "front", "back") and wing_rings:
                def _wc(ring):
                    xs = [q[0] for q in ring]; ys = [q[1] for q in ring]
                    return (sum(xs) / len(xs), sum(ys) / len(ys))
                # +x = east, +y = north (viewer is north-up).
                use_x = _dirword in ("left", "right", "east", "west")
                axis_max = _dirword in ("right", "east", "north", "back")  # else take the min
                scored = [(r, _wc(ring)[0] if use_x else _wc(ring)[1]) for r, ring in wing_rings.items()]
                chosen = (max if axis_max else min)(scored, key=lambda t: t[1])[0]
                wing_ring = wing_rings[chosen]
                new_fp = wing_ring
                wing = chosen   # report the real wing we used
            # Single-wing shape (e.g. an "I" bar has only 'main_bar'): the user clearly
            # means "add floors to this building", so gracefully use that one wing.
            if not wing_ring and len(available) == 1:
                wing_ring = _wing_ring_from_plate(
                    next(p for p in sorted(base, key=lambda q: q["z_base"])
                         if _wing_ring_from_plate(p, available[0])),
                    available[0])
                if wing_ring:
                    new_fp = wing_ring
                    wing = available[0]   # report the wing we actually used
            if not wing_ring:
                hint = (f" This shape has no separate wings — it's a single mass; "
                        f"try 'add {abs(n)} floors' (no wing)." if not available
                        else f" Available wings: {', '.join(available)}.")
                return {"ok": False, "reason": f"No '{wing}' wing on this shape.{hint}"}
        else:
            new_fp = wing_ring
    else:
        new_fp = top_plate["footprint"]

    # For a WING add, the new floors must sit on top of THAT WING's existing plates,
    # not the top of the whole building. Otherwise, if another wing is taller, the new
    # wing floors start at the tall top and leave a floating gap above the short wing
    # (the misaligned block). Recompute z as the top of this wing's own stack; the
    # whole-building case keeps the original z (top of everything). Geometry-only,
    # nothing else changes.
    if wing:
        wing_plates = [p for p in base if _plate_is_wing(p, wing)]
        if wing_plates:
            wtop = max(wing_plates, key=lambda p: p["z_base"])
            z = wtop["z_base"] + wtop["height"]
            top_level = wtop["level"]

    new_plates = [dict(p) for p in base]
    for i in range(n):
        lvl = top_level + 1 + i
        plate = {
            "level": lvl,
            "footprint": [list(p) for p in new_fp],
            "z_base": round(z + i * floor_height, 3),
            "height": float(floor_height),
        }
        if wing:
            plate["wing"] = wing
        new_plates.append(plate)
    return {"ok": True, "floor_plates": new_plates, "added": n, "wing": wing}


def twist_stack(plates: list[dict[str, Any]], total_degrees: float = 15.0) -> dict[str, Any]:
    """Progressively rotate each floor plate about the building centroid, from 0° at the
    base to `total_degrees` at the top — a twisting-tower silhouette ("make it more
    iconic / sculptural / dynamic"). Returns the new plate stack."""
    import math

    if not plates:
        return {"ok": False, "reason": "no floor plates to twist"}
    # Centroid of the base plate = the twist axis.
    base = min(plates, key=lambda p: p["z_base"])
    pts = base["footprint"]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    n = len(plates)
    ordered = sorted(plates, key=lambda p: p["z_base"])
    out = []
    for i, p in enumerate(ordered):
        frac = i / max(1, n - 1)
        ang = math.radians(total_degrees * frac)
        ca, sa = math.cos(ang), math.sin(ang)
        np = dict(p)
        np["footprint"] = [
            [cx + (q[0] - cx) * ca - (q[1] - cy) * sa,
             cy + (q[0] - cx) * sa + (q[1] - cy) * ca]
            for q in p["footprint"]
        ]
        # NOTE: deliberately do NOT rotate each plate's `holes` per-floor here. Rotating the
        # courtyard void per-floor (an earlier attempt to remove a small twist-surface
        # artifact) DROPPED the courtyard from the render entirely — the user's priority is
        # an always-visible courtyard, so the void is kept flat/shared and the persist step
        # re-applies the single working_holes to every plate. The minor twist surface over
        # the void is the accepted trade-off. Keep the plate's existing holes untouched.
        out.append(np)
    return {"ok": True, "floor_plates": out, "reason": f"twisted the tower {round(total_degrees)}° over its height"}


def taper_stack(plates: list[dict[str, Any]], top_scale: float = 0.7) -> dict[str, Any]:
    """Progressively scale each plate from full size at the base to `top_scale` at the
    top — a tapered / slender silhouette ("make it more slender / elegant / a landmark
    silhouette"). top_scale > 1 produces an inverted (widening) profile."""
    if not plates:
        return {"ok": False, "reason": "no floor plates to taper"}
    base = min(plates, key=lambda p: p["z_base"])
    pts = base["footprint"]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    n = len(plates)
    ordered = sorted(plates, key=lambda p: p["z_base"])
    out = []
    for i, p in enumerate(ordered):
        frac = i / max(1, n - 1)
        s = 1.0 + (top_scale - 1.0) * frac
        np = dict(p)
        np["footprint"] = [[cx + (q[0] - cx) * s, cy + (q[1] - cy) * s] for q in p["footprint"]]
        # NOTE: deliberately do NOT scale each plate's holes per-floor (same reason as
        # twist_stack) — keep the courtyard void flat/shared so it always renders. The
        # persist step re-applies working_holes to every plate.
        out.append(np)
    return {"ok": True, "floor_plates": out, "reason": f"tapered the massing to {round(top_scale * 100)}% at the top"}


def plates_to_summary(plates: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive floors / height_m / overall footprint from the plate stack so the rest
    of the system (FAR, explorer, persistence) stays consistent."""
    if not plates:
        return {"floors": 0, "height_m": 0.0}
    floors = len(plates)
    top = max(plates, key=lambda p: p["z_base"])
    height_m = round(top["z_base"] + top["height"], 2)
    # Overall footprint = the widest plate (the podium / ground floor in most cases).
    base_plate = min(plates, key=lambda p: p["z_base"])
    return {
        "floors": floors,
        "height_m": height_m,
        "footprint": base_plate["footprint"],
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _clean_ring(ring: list[list[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    for p in ring or []:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            out.append([float(p[0]), float(p[1])])
    return out


def _translate(ring: list[list[float]], dx: float, dy: float) -> list[list[float]]:
    return [[float(p[0]) + dx, float(p[1]) + dy] for p in ring if len(p) >= 2]


def _renumber(plates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-stack plates by z so levels/z_base are contiguous after a removal."""
    ordered = sorted(plates, key=lambda p: p["z_base"])
    z = 0.0
    out = []
    for i, p in enumerate(ordered):
        np = dict(p)
        np["level"] = i
        np["z_base"] = round(z, 3)
        z += np["height"]
        out.append(np)
    return out


def _wing_footprints(wings: list[dict[str, Any]] | None) -> dict[str, list[list[float]]]:
    """Map wing role -> its footprint ring, for building per-wing plate sub-footprints."""
    result: dict[str, list[list[float]]] = {}
    for w in wings or []:
        role = (w.get("role") or "").lower()
        ring = _clean_ring(w.get("boundary") or [])
        if role and len(ring) >= 3:
            result[role] = ring
    return result


def _wing_ring_from_plate(plate: dict[str, Any], wing: str) -> list[list[float]] | None:
    wf = plate.get("wing_footprints") or {}
    ring = wf.get(wing.lower())
    return _clean_ring(ring) if ring else None


def _plate_is_wing(plate: dict[str, Any], wing: str) -> bool:
    return (plate.get("wing") or "").lower() == wing.lower()


def _ring_in_site(ring: list[list[float]], site_boundary: list[list[float]]) -> bool:
    """True if `ring` is (almost) fully inside the site polygon."""
    try:
        from shapely.geometry import Polygon

        rp = Polygon([(p[0], p[1]) for p in ring])
        sp = Polygon([(p[0], p[1]) for p in site_boundary])
        if not rp.is_valid:
            rp = rp.buffer(0)
        if not sp.is_valid:
            sp = sp.buffer(0)
        if rp.area <= 0:
            return False
        outside = rp.difference(sp).area
        return outside / rp.area < 0.02  # allow a 2% numeric tolerance
    except Exception:  # noqa: BLE001
        return True  # don't block on a geometry hiccup
