"""
Backend 2D isovist (visibility polygon) from the layout + an observer point.

Grasshopper's `set_observer` only returns the observer point and a degenerate
"isovist" (the whole floor — constant regardless of position, because the floor
loses its obstacles when the tool runs). So we compute the REAL visibility polygon
here, deterministically, from the layout geometry:

  - Blockers: the exterior outline (always), interior walls (`structure`), and
    equipment footprints (`furniture` / `mep`) — height-aware: equipment shorter
    than the eye height does NOT block.
  - Openings: doors + windows are subtracted from interior walls, so sightlines
    pass through them (the exterior outline stays solid so the view is bounded).

Algorithm: cast rays toward every blocker endpoint (± a tiny angle to slip past
corners), keep the nearest hit per ray, sort by angle → the visibility polygon.
"""
from __future__ import annotations

import math
from typing import Any, List, Optional, Tuple

_EPS = 1e-6
_ANG_EPS = 1e-4
_COLLINEAR_TOL = 0.06  # m — how close an opening must be to a wall line to cut it

Seg = Tuple[float, float, float, float]


def _poly_edges(geom: Any) -> List[Seg]:
    out: List[Seg] = []
    if not isinstance(geom, list):
        return out
    for i in range(len(geom) - 1):
        a, b = geom[i], geom[i + 1]
        try:
            out.append((float(a[0]), float(a[1]), float(b[0]), float(b[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _height_blocks(item: dict, eye_h: float) -> bool:
    """True if the item is tall enough to block the line of sight at eye height."""
    h = (item.get("attributes") or {}).get("height")
    if h is None:
        return True  # unknown height → assume it blocks (conservative)
    try:
        return float(h) >= eye_h - 0.05
    except (TypeError, ValueError):
        return True


def _cut_collinear(w: Seg, op: Seg) -> List[Seg]:
    """Remove the part of wall `w` covered by opening `op` when they are collinear."""
    x1, y1, x2, y2 = w
    wx, wy = x2 - x1, y2 - y1
    wlen2 = wx * wx + wy * wy
    if wlen2 < _EPS:
        return [w]
    wlen = math.sqrt(wlen2)

    def perp(px: float, py: float) -> float:
        return abs(wx * (py - y1) - wy * (px - x1)) / wlen

    if perp(op[0], op[1]) > _COLLINEAR_TOL or perp(op[2], op[3]) > _COLLINEAR_TOL:
        return [w]  # opening not on this wall's line

    def proj(px: float, py: float) -> float:
        return ((px - x1) * wx + (py - y1) * wy) / wlen2

    u1, u2 = proj(op[0], op[1]), proj(op[2], op[3])
    lo, hi = max(0.0, min(u1, u2)), min(1.0, max(u1, u2))
    if hi <= lo + _EPS:
        return [w]  # no overlap within the wall

    parts: List[Seg] = []
    if lo > _EPS:
        parts.append((x1, y1, x1 + wx * lo, y1 + wy * lo))
    if hi < 1.0 - _EPS:
        parts.append((x1 + wx * hi, y1 + wy * hi, x2, y2))
    return parts


def _subtract_openings(walls: List[Seg], openings: List[Seg]) -> List[Seg]:
    res: List[Seg] = []
    for w in walls:
        parts = [w]
        for op in openings:
            nxt: List[Seg] = []
            for p in parts:
                nxt.extend(_cut_collinear(p, op))
            parts = nxt
        res.extend(parts)
    return res


def _segments(layout: dict, eye_h: float) -> List[Seg]:
    solids: List[Seg] = []      # outline + tall equipment (never cut)
    walls: List[Seg] = []       # interior walls (cut by openings)

    solids.extend(_poly_edges(layout.get("outline")))

    for s in layout.get("structure", []) or []:
        walls.extend(_poly_edges(s.get("geometry")))

    for f in layout.get("furniture", []) or []:
        if _height_blocks(f, eye_h):
            solids.extend(_poly_edges(f.get("geometry")))
    for m in layout.get("mep", []) or []:
        if _height_blocks(m, eye_h):
            solids.extend(_poly_edges(m.get("geometry")))

    openings: List[Seg] = []
    for d in layout.get("doors", []) or []:
        openings.extend(_poly_edges(d.get("geometry")))
    for wd in layout.get("windows", []) or []:
        openings.extend(_poly_edges(wd.get("geometry")))

    walls = _subtract_openings(walls, openings)
    return [s for s in (solids + walls) if (s[0] - s[2]) ** 2 + (s[1] - s[3]) ** 2 > _EPS]


def _ray_seg_t(ox: float, oy: float, dx: float, dy: float, seg: Seg) -> Optional[float]:
    ax, ay, bx, by = seg
    ex, ey = bx - ax, by - ay
    denom = dx * ey - dy * ex
    if abs(denom) < 1e-12:
        return None
    t = ((ax - ox) * ey - (ay - oy) * ex) / denom
    u = ((ax - ox) * dy - (ay - oy) * dx) / denom
    if t >= -_EPS and -_EPS <= u <= 1 + _EPS:
        return t
    return None


def compute(layout: dict, ox: float, oy: float, eye_h: float = 1.7) -> Optional[List[List[float]]]:
    """Visibility polygon (closed, layout metres) from (ox,oy). None if degenerate."""
    segs = _segments(layout, eye_h)
    if not segs:
        return None

    angles: List[float] = []
    for ax, ay, bx, by in segs:
        for px, py in ((ax, ay), (bx, by)):
            a = math.atan2(py - oy, px - ox)
            angles.append(a - _ANG_EPS)
            angles.append(a)
            angles.append(a + _ANG_EPS)

    hits: List[Tuple[float, float, float]] = []
    for a in angles:
        dx, dy = math.cos(a), math.sin(a)
        tmin: Optional[float] = None
        for seg in segs:
            t = _ray_seg_t(ox, oy, dx, dy, seg)
            if t is not None and t > _EPS and (tmin is None or t < tmin):
                tmin = t
        if tmin is not None:
            hits.append((a, ox + dx * tmin, oy + dy * tmin))

    if len(hits) < 3:
        return None
    hits.sort(key=lambda h: h[0])

    poly: List[List[float]] = []
    for _, hx, hy in hits:
        rx, ry = round(hx, 3), round(hy, 3)
        if not poly or abs(poly[-1][0] - rx) > 1e-3 or abs(poly[-1][1] - ry) > 1e-3:
            poly.append([rx, ry])
    if len(poly) >= 3 and poly[0] != poly[-1]:
        poly.append(poly[0])
    return poly if len(poly) >= 4 else None


Owner = dict  # {id, name, type, roomId?}
OwnedSeg = Tuple[Seg, Owner]


def _centroid(geom: Any) -> Optional[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    if not isinstance(geom, list):
        return None
    for p in geom:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                pts.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError):
                continue
    if not pts:
        return None
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def _sample_points(geom: Any) -> List[Tuple[float, float]]:
    """Footprint vertices + edge midpoints + centroid — the candidate points a
    line of sight could reach to call an object 'visible'."""
    verts: List[Tuple[float, float]] = []
    if not isinstance(geom, list):
        return verts
    for p in geom:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                verts.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError):
                continue
    if len(verts) > 1 and verts[0] == verts[-1]:
        verts = verts[:-1]
    if not verts:
        return verts
    samples = list(verts)
    for i in range(len(verts)):
        ax, ay = verts[i]
        bx, by = verts[(i + 1) % len(verts)]
        samples.append(((ax + bx) / 2, (ay + by) / 2))
    c = _centroid(geom)
    if c:
        samples.append(c)
    return samples


def _poly_area(poly: Optional[List[List[float]]]) -> Optional[float]:
    if not poly or len(poly) < 4:
        return None
    s = 0.0
    for i in range(len(poly) - 1):
        x1, y1 = poly[i]
        x2, y2 = poly[i + 1]
        s += x1 * y2 - x2 * y1
    return round(abs(s) / 2.0, 2)


def _owned_segments(layout: dict, eye_h: float) -> List[OwnedSeg]:
    """Like _segments, but each segment is tagged with the object that owns it,
    so a blocked sightline can be attributed back to a specific item."""
    owned: List[OwnedSeg] = []

    for s in _poly_edges(layout.get("outline")):
        owned.append((s, {"id": "outline", "name": "outline", "type": "outline"}))

    for f in layout.get("furniture", []) or []:
        if _height_blocks(f, eye_h):
            o = {"id": f.get("id"), "name": f.get("name"), "type": "furniture",
                 "roomId": (f.get("attributes") or {}).get("roomId")}
            for s in _poly_edges(f.get("geometry")):
                owned.append((s, o))
    for m in layout.get("mep", []) or []:
        if _height_blocks(m, eye_h):
            o = {"id": m.get("id"), "name": m.get("name"), "type": "mep"}
            for s in _poly_edges(m.get("geometry")):
                owned.append((s, o))

    openings: List[Seg] = []
    for d in layout.get("doors", []) or []:
        openings.extend(_poly_edges(d.get("geometry")))
    for wd in layout.get("windows", []) or []:
        openings.extend(_poly_edges(wd.get("geometry")))

    for st in layout.get("structure", []) or []:
        o = {"id": st.get("id"), "name": st.get("name"), "type": "wall"}
        for w in _poly_edges(st.get("geometry")):
            for part in _subtract_openings([w], openings):
                owned.append((part, o))

    return [(s, o) for (s, o) in owned
            if (s[0] - s[2]) ** 2 + (s[1] - s[3]) ** 2 > _EPS]


def _los_clear(ox: float, oy: float, tx: float, ty: float,
               owned: List[OwnedSeg], own_id: Any) -> bool:
    """True if the segment observer→target is not crossed by any owned segment
    (ignoring segments owned by `own_id`, so an object never occludes itself)."""
    dx, dy = tx - ox, ty - oy
    dist = math.hypot(dx, dy)
    if dist < _EPS:
        return True
    ndx, ndy = dx / dist, dy / dist
    for seg, owner in owned:
        if owner and owner.get("id") == own_id:
            continue
        t = _ray_seg_t(ox, oy, ndx, ndy, seg)
        if t is not None and _EPS < t < dist - 0.02:
            return False
    return True


def _nearest_blocker(ox: float, oy: float, tx: float, ty: float,
                     owned: List[OwnedSeg], own_id: Any) -> Optional[Owner]:
    """Owner of the nearest segment crossing observer→target (the thing in the way)."""
    dx, dy = tx - ox, ty - oy
    dist = math.hypot(dx, dy)
    if dist < _EPS:
        return None
    ndx, ndy = dx / dist, dy / dist
    best_t: Optional[float] = None
    best_owner: Optional[Owner] = None
    for seg, owner in owned:
        if owner and owner.get("id") == own_id:
            continue
        t = _ray_seg_t(ox, oy, ndx, ndy, seg)
        if t is not None and _EPS < t < dist - 0.02 and (best_t is None or t < best_t):
            best_t, best_owner = t, owner
    return best_owner


def analyze_obstructions(layout: dict, ox: float, oy: float,
                         eye_h: float = 1.7) -> dict:
    """From an observer at (ox, oy), classify every furniture/mep object as
    visible or hidden, and report which movable objects (furniture/mep) block
    the line of sight to at least one hidden object.

    Returns:
      observer:   [x, y, eye_h]
      visible:    [{id, name, type}]      — clear line of sight
      hidden:     [{id, name, type, behind}] — occluded (behind says what blocks it)
      blockers:   [{id, name, type, hides}]  — movable objects causing occlusion
      isovist_area, counts
    """
    owned = _owned_segments(layout, eye_h)

    targets: List[Tuple[str, dict]] = []
    for f in layout.get("furniture", []) or []:
        targets.append(("furniture", f))
    for m in layout.get("mep", []) or []:
        targets.append(("mep", m))

    visible: List[dict] = []
    hidden: List[dict] = []
    blockers: dict = {}   # id -> {id, name, type, hides:[names]}

    for ttype, item in targets:
        geom = item.get("geometry")
        pts = _sample_points(geom)
        if not pts:
            continue
        own_id = item.get("id")
        name = item.get("name")
        is_vis = any(_los_clear(ox, oy, px, py, owned, own_id) for px, py in pts)
        if is_vis:
            visible.append({"id": own_id, "name": name, "type": ttype})
            continue

        # Hidden — attribute the blocker via the centroid sightline.
        c = _centroid(geom) or pts[0]
        blk = _nearest_blocker(ox, oy, c[0], c[1], owned, own_id)
        behind = blk.get("name") if blk else None
        hidden.append({"id": own_id, "name": name, "type": ttype, "behind": behind})
        # Only movable objects count as "blockers" (walls/outline are structural).
        if blk and blk.get("type") in ("furniture", "mep"):
            bid = blk.get("id")
            entry = blockers.setdefault(
                bid, {"id": bid, "name": blk.get("name"), "type": blk.get("type"), "hides": []}
            )
            if name and name not in entry["hides"]:
                entry["hides"].append(name)

    iso = compute(layout, ox, oy, eye_h)
    return {
        "observer": [round(ox, 3), round(oy, 3), round(eye_h, 2)],
        "visible": visible,
        "hidden": hidden,
        "blockers": list(blockers.values()),
        "isovist_area": _poly_area(iso),
        "counts": {"visible": len(visible), "hidden": len(hidden),
                   "blockers": len(blockers)},
    }


def analyze_obstructions_path(layout: dict, points: List[Tuple[float, float]],
                              eye_h: float = 1.7) -> dict:
    """Obstruction analysis aggregated along a path: an object is 'visible' if it
    can be seen from ANY point on the route; 'hidden' only if blocked from every
    point. Blockers are unioned across the route."""
    if not points:
        return {"observer": None, "visible": [], "hidden": [], "blockers": [],
                "isovist_area": None, "counts": {"visible": 0, "hidden": 0, "blockers": 0}}

    per = [analyze_obstructions(layout, px, py, eye_h) for px, py in points]
    visible_ids: set = set()
    names: dict = {}
    for r in per:
        for v in r["visible"]:
            visible_ids.add(v["id"])
            names[v["id"]] = v
        for h in r["hidden"]:
            names.setdefault(h["id"], {"id": h["id"], "name": h["name"], "type": h["type"]})

    visible = [names[i] for i in visible_ids if i in names]
    hidden = [v for i, v in names.items() if i not in visible_ids]

    blockers: dict = {}
    for r in per:
        for b in r["blockers"]:
            # only keep blockers that hide objects still globally hidden
            still = [n for n in b.get("hides", []) if any(h["name"] == n for h in hidden)]
            if still:
                entry = blockers.setdefault(b["id"], {**b, "hides": []})
                for n in still:
                    if n not in entry["hides"]:
                        entry["hides"].append(n)

    iso = compute_path(layout, points, eye_h)
    return {
        "observer": [round(points[0][0], 3), round(points[0][1], 3), round(eye_h, 2)],
        "path_points": [[round(px, 3), round(py, 3)] for px, py in points],
        "visible": visible,
        "hidden": hidden,
        "blockers": list(blockers.values()),
        "isovist_area": _poly_area(iso),
        "counts": {"visible": len(visible), "hidden": len(hidden),
                   "blockers": len(blockers)},
    }


def compute_path(layout: dict, points: List[Tuple[float, float]], eye_h: float = 1.7) -> Optional[List[List[float]]]:
    """Union of the isovists along a path (what's visible anywhere on the route).
    Uses shapely if available; otherwise returns the first point's isovist."""
    isos = [iso for (px, py) in points if (iso := compute(layout, px, py, eye_h))]
    if not isos:
        return None
    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        u = unary_union([Polygon(i) for i in isos if len(i) >= 4])
        geom = max(u.geoms, key=lambda g: g.area) if hasattr(u, "geoms") else u
        return [[round(x, 3), round(y, 3)] for x, y in geom.exterior.coords]
    except Exception:
        return isos[0]
