"""
spatial.py — spatial-awareness helpers for the edit tools (Shapely-backed).

Edits must be sound BY CONSTRUCTION. A plant goes on a clear floor spot against a wall
(never the dead centre of the room); a window goes on a clear span of a real EXTERIOR
wall; a curtain hangs just inside a window wall. These helpers compute those placements
from the layout geometry. `check_layout_geometry.audit_layout` then validates the result
and `apply_edits` reverts anything that still introduces a defect — so this module only
has to be *good*, not perfect.

Coordinates are metric metres and axis-aligned; y is NOT flipped (model space, exactly
like the JS `walls.js`/`geometry.js`). Reuses the same WALL tolerance as those.
"""
from __future__ import annotations

from typing import Optional

from shapely.geometry import Polygon, Point, box

TOL = 0.02          # geometric slop (matches check_layout_geometry + walls.js)
WALL_MARGIN = 0.15  # keep openings clear of wall corners / each other
WINDOW_LEN = 1.2    # default window opening width (m)


# ── small geometry helpers ────────────────────────────────────────────────────
def _ring(coords):
    """Open ring (drop the duplicate closing vertex if present)."""
    if coords and len(coords) > 1 and coords[0] == coords[-1]:
        return coords[:-1]
    return coords or []


def _edges(coords):
    """Edges of a closed polygon as ((x1,y1),(x2,y2)) tuples."""
    pts = _ring(coords)
    out = []
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        out.append((tuple(a), tuple(b)))
    return out


def _orient(a, b):
    """'h' (constant y), 'v' (constant x), or None (point / diagonal)."""
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    if dx <= TOL and dy <= TOL:
        return None
    if dy <= TOL:
        return "h"
    if dx <= TOL:
        return "v"
    return None


def _seg_len(geom):
    if not geom or len(geom) < 2:
        return 0.0
    a, b = geom[0], geom[-1]
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _bbox(geom):
    xs = [p[0] for p in geom]
    ys = [p[1] for p in geom]
    return (min(xs), min(ys), max(xs), max(ys))


def _box_ring(x0, y0, x1, y1):
    """Closed axis-aligned rectangle as a layout geometry ring."""
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def room_polygon(room) -> Optional[Polygon]:
    geo = room.get("geometry") if room else None
    if not geo or len(geo) < 3:
        return None
    try:
        p = Polygon(_ring(geo))
        return p if p.is_valid and not p.is_empty else p.buffer(0)
    except Exception:
        return None


def outline_polygon(layout) -> Optional[Polygon]:
    o = layout.get("outline")
    if not o or len(o) < 3:
        return None
    try:
        p = Polygon(_ring(o))
        return p if p.is_valid and not p.is_empty else p.buffer(0)
    except Exception:
        return None


def facing_from_normal(nx, ny) -> str:
    """Outward normal → cardinal facing. N=+y, S=-y, E=+x, W=-x (matches scoring)."""
    if abs(nx) >= abs(ny):
        return "E" if nx > 0 else "W"
    return "N" if ny > 0 else "S"


def _normal(orient, mid, poly, outward=True):
    """Pick the ±normal of an axis-aligned edge that points OUT of (or INTO) `poly`."""
    cands = [(1, 0), (-1, 0)] if orient == "v" else [(0, 1), (0, -1)]
    for nx, ny in cands:
        inside = poly is not None and poly.contains(Point(mid[0] + 0.1 * nx, mid[1] + 0.1 * ny))
        if outward and not inside:
            return (nx, ny)
        if not outward and inside:
            return (nx, ny)
    return cands[0]


# ── wall / opening queries ────────────────────────────────────────────────────
def exterior_edges(layout, room):
    """Room polygon edges lying on the building outline (the exterior walls).

    Each: {orient, const, lo, hi, length, facing}. `facing` is the cardinal the wall
    faces, derived from its outward normal — this becomes a new window's orientation.
    """
    poly = room_polygon(room)
    o_poly = outline_polygon(layout)
    ring = o_poly.exterior if o_poly is not None else None
    out = []
    for a, b in _edges(room.get("geometry", []) if room else []):
        orient = _orient(a, b)
        if orient is None:
            continue
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        if ring is None or ring.distance(Point(mid)) > TOL:
            continue  # not on the perimeter → interior wall
        const = a[0] if orient == "v" else a[1]
        if orient == "v":
            lo, hi = min(a[1], b[1]), max(a[1], b[1])
        else:
            lo, hi = min(a[0], b[0]), max(a[0], b[0])
        nx, ny = _normal(orient, mid, poly, outward=True)
        out.append({"orient": orient, "const": const, "lo": lo, "hi": hi,
                    "length": hi - lo, "facing": facing_from_normal(nx, ny)})
    return out


def _openings_on_line(layout, orient, const):
    """Occupied (lo, hi) intervals of existing windows + doors on one wall line."""
    occ = []
    for key in ("windows", "doors"):
        for el in layout.get(key, []) or []:
            g = el.get("geometry", [])
            if len(g) < 2:
                continue
            a, b = g[0], g[-1]
            if _orient(a, b) != orient:
                continue
            c = a[0] if orient == "v" else a[1]
            if abs(c - const) > TOL:
                continue
            if orient == "v":
                occ.append((min(a[1], b[1]), max(a[1], b[1])))
            else:
                occ.append((min(a[0], b[0]), max(a[0], b[0])))
    return occ


def clear_spans(lo, hi, occupied, need, margin=WALL_MARGIN):
    """Free runs of length >= `need` on [lo, hi], clear of corners and `occupied`."""
    a, b = lo + margin, hi - margin
    if b - a < need:
        return []
    blocked = sorted((x0 - margin, x1 + margin) for x0, x1 in occupied)
    spans, cur = [], a
    for x0, x1 in blocked:
        if x1 <= cur:
            continue
        if x0 > cur and (min(x0, b) - cur) >= need:
            spans.append((cur, min(x0, b)))
        cur = max(cur, x1)
        if cur >= b:
            break
    if b - cur >= need:
        spans.append((cur, b))
    return [s for s in spans if s[1] - s[0] >= need]


def place_window(layout, room, need=WINDOW_LEN, facing_pref=None):
    """Best clear span on an exterior wall for a new (or relocated) window.

    Returns {geometry (2-pt segment), orient, const, facing} or None if the room has
    no clear exterior span (caller surfaces "couldn't place"). Prefers the longest
    span, breaking ties toward sunnier orientations — or toward `facing_pref` when the
    user named a specific wall ("move the window to the north wall").
    """
    favor = {"S": 3, "E": 2, "W": 1, "N": 0}
    if facing_pref in favor:
        favor = {k: (10 if k == facing_pref else v) for k, v in favor.items()}
    best = None
    for e in exterior_edges(layout, room):
        occ = _openings_on_line(layout, e["orient"], e["const"])
        for s0, s1 in clear_spans(e["lo"], e["hi"], occ, need):
            f = favor.get(e["facing"], 0)
            # a named wall leads; otherwise the longest span leads (sunnier breaks ties)
            score = (f, s1 - s0) if facing_pref else (s1 - s0, f)
            if best is None or score > best[0]:
                best = (score, e, s0, s1)
    if best is None:
        return None
    _, e, s0, s1 = best
    mid, half = (s0 + s1) / 2.0, need / 2.0
    if e["orient"] == "v":
        geo = [[e["const"], mid - half], [e["const"], mid + half]]
    else:
        geo = [[mid - half, e["const"]], [mid + half, e["const"]]]
    return {"geometry": geo, "orient": e["orient"], "const": e["const"], "facing": e["facing"]}


def place_curtain(layout, room, depth=0.12):
    """A thin footprint hung just inside the room's largest window wall (or, if the
    room has no window, its longest exterior wall). Returns a closed geometry ring."""
    rid = room.get("id") if room else None
    poly = room_polygon(room)
    if poly is None:
        return None
    wins = [w for w in layout.get("windows", []) or []
            if w.get("attributes", {}).get("roomId") == rid and len(w.get("geometry", [])) >= 2]
    if wins:
        g = max(wins, key=lambda w: _seg_len(w["geometry"]))["geometry"]
        a, b = g[0], g[-1]
    else:
        edges = exterior_edges(layout, room)
        if not edges:
            return None
        e = max(edges, key=lambda e: e["length"])
        if e["orient"] == "v":
            a, b = [e["const"], e["lo"]], [e["const"], e["hi"]]
        else:
            a, b = [e["lo"], e["const"]], [e["hi"], e["const"]]
    orient = _orient(a, b)
    if orient is None:
        return None
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    nx, ny = _normal(orient, mid, poly, outward=False)  # inward
    off = depth / 2.0 + 0.02
    cx, cy = mid[0] + nx * off, mid[1] + ny * off
    if orient == "v":  # window runs in y → curtain spans y, thin in x
        return _box_ring(cx - depth / 2.0, min(a[1], b[1]), cx + depth / 2.0, max(a[1], b[1]))
    return _box_ring(min(a[0], b[0]), cy - depth / 2.0, max(a[0], b[0]), cy + depth / 2.0)


def place_rug(layout, room):
    """A rug is a central floor covering (it legitimately sits under furniture), so it
    goes at the room centre, sized to ~60% of the room and clamped inside."""
    poly = room_polygon(room)
    if poly is None:
        return None
    minx, miny, maxx, maxy = poly.bounds
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    w = max(0.8, min(2.2, (maxx - minx) * 0.6))
    h = max(0.8, min(3.0, (maxy - miny) * 0.6))
    return _box_ring(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def place_furniture(layout, room, w, h, clearance=0.10):
    """A clear floor spot for a w×h footprint, preferring corners/walls over the centre.

    Returns a closed geometry ring. Never fails: if nothing is clear it falls back to a
    representative interior point (the old centroid behaviour), and the audit/revert loop
    is the final guard.
    """
    poly = room_polygon(room)
    if poly is None:
        return _box_ring(-w / 2, -h / 2, w / 2, h / 2)
    rid = room.get("id")
    obstacles = [box(*_bbox(f["geometry"]))
                 for f in layout.get("furniture", []) or []
                 if f.get("attributes", {}).get("roomId") == rid and f.get("geometry")]
    minx, miny, maxx, maxy = poly.bounds
    m = 0.05
    hw, hh = w / 2.0, h / 2.0
    if (maxx - minx) <= w + 2 * m or (maxy - miny) <= h + 2 * m:
        rp = poly.representative_point()
        return _box_ring(rp.x - hw, rp.y - hh, rp.x + hw, rp.y + hh)

    xs0, xs1 = minx + m + hw, maxx - m - hw
    ys0, ys1 = miny + m + hh, maxy - m - hh
    n = 5
    cands = [(xs0, ys0), (xs1, ys0), (xs0, ys1), (xs1, ys1)]  # corners first
    for i in range(n + 1):                                    # then slide along walls
        fx = xs0 + (xs1 - xs0) * i / n
        fy = ys0 + (ys1 - ys0) * i / n
        cands += [(fx, ys0), (fx, ys1), (xs0, fy), (xs1, fy)]
    for i in range(1, n):                                     # then an interior grid
        for j in range(1, n):
            cands.append((xs0 + (xs1 - xs0) * i / n, ys0 + (ys1 - ys0) * j / n))

    for cx, cy in cands:
        b = box(cx - hw, cy - hh, cx + hw, cy + hh)
        if not poly.contains(b):
            continue
        if any(b.buffer(clearance).intersects(o) for o in obstacles):
            continue
        return _box_ring(cx - hw, cy - hh, cx + hw, cy + hh)

    rp = poly.representative_point()
    return _box_ring(rp.x - hw, rp.y - hh, rp.x + hw, rp.y + hh)
