"""
Architectural geometry checker for the Sensi example layouts.

Where validate_layouts.py checks *topology* (rooms tile the outline, areas match,
doors sit on shared walls), this checker is the *architectural-soundness* layer it
does not cover. It enumerates the defects a human reviewer would catch on a plan:

  1. furniture overlapping furniture                          (overlap area)
  2. furniture poking through a wall / outside its room       (area outside)
  3. door leaf swing-arc blocked by furniture (no openable side)
  4. doorway approach blocked — can't stand at / pass the door (clear depth)
  5. door clear width below standard                          (leaf width)
  6. window blocked by a tall piece of furniture             (gap to glazing)
  7. circulation corridor narrower than standard             (clear width)

All layouts are metric (metres) and axis-aligned (one L-shaped room is handled by
rectilinear decomposition). Pure stdlib so it can gate CI / pre-commit.

Usage (from anywhere):
    python team_02/python/check_layout_geometry.py
    python team_02/python/check_layout_geometry.py path/to/layout.json [more ...]

Exits non-zero if any layout has a defect.
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys

# ── Architectural standards (metres) ─────────────────────────────────────────
TOL              = 0.02   # geometric slop: shared edges / rounding are not defects
APPROACH_DEPTH   = 0.60   # clear floor needed in front of a door to stand & pass
CIRC_MIN         = 0.90   # min clear width of a circulation corridor
CORRIDOR_MAX_DIM = 1.80   # a room is "corridor-like" only if its short side < this
DOOR_MIN_HAB     = 0.80   # min clear leaf width, habitable rooms
DOOR_MIN_UTIL    = 0.70   # min clear leaf width, closets / stores / pantries
SWING_MAX_LEAF   = 1.05   # doors wider than this read as cased openings (no leaf)
WINDOW_GAP       = 0.35   # a tall piece this close to glazing blocks the window

# Tall / opaque furniture that blocks daylight if placed at a window.
TALL_TYPES = {"dresser", "wardrobe", "bookshelf", "cabinet", "shelf",
              "shelving", "fridge", "refrigerator", "armoire", "closet"}

# Flat / soft furnishings that are NOT collision obstacles (rugs go under furniture,
# curtains hang on the wall, cushions sit on a sofa). Excluded from overlap/containment.
NON_OBSTACLE_TYPES = {"rug", "carpet", "curtain", "curtains", "blind", "blinds",
                      "drape", "drapes", "shade", "cushion", "mat", "runner"}

# Room kinds where a 0.70 m leaf is acceptable (you reach in, you don't walk in).
UTILITY_NAME_HINTS = ("store", "linen", "pantry", "closet", "wardrobe")

ACCESS_CLEAR = 0.55   # a bed needs at least this clear on one long side to get in
GAP_MIN      = 0.05   # below this two pieces read as intentionally flush / grouped
GAP_WALK     = 0.60   # above this a gap is a usable walkway; between = dead space

# Realistic furniture footprints, metres: type -> (small_min, small_max, long_min,
# long_max) where small/long are the sorted side lengths. Generous ranges — they
# catch gross mis-scaling (a 3 m "bed", a 1.5 m-deep sofa), not centimetre quibbles.
FURNITURE_SIZE = {
    "bed":        (0.90, 2.00, 1.85, 2.20),
    "sofa":       (0.75, 1.10, 1.40, 3.30),
    "armchair":   (0.60, 1.05, 0.60, 1.10),
    "table":      (0.45, 1.30, 0.80, 2.60),   # dining + coffee share this type
    "desk":       (0.45, 0.85, 0.90, 1.90),
    "island":     (0.80, 1.30, 1.00, 2.60),
    "counter":    (0.50, 0.75, 0.80, 5.00),
    "dresser":    (0.45, 0.75, 0.70, 2.60),
    "wardrobe":   (0.50, 0.75, 0.70, 2.60),
    "bookshelf":  (0.22, 0.50, 0.50, 2.00),
    "nightstand": (0.30, 0.65, 0.30, 0.70),
    "plant":      (0.25, 0.80, 0.25, 0.90),
    "toilet":     (0.35, 0.60, 0.55, 0.80),
    "sink":       (0.40, 0.70, 0.40, 1.40),
    "vanity":     (0.40, 0.70, 0.50, 1.60),
    "shower":     (0.75, 1.10, 0.75, 1.30),
    "bathtub":    (0.65, 0.90, 1.40, 1.90),
    "fridge":     (0.55, 0.80, 0.55, 0.95),
    "stove":      (0.50, 0.70, 0.50, 0.95),
}

# Fixtures a room type must contain to read as that room (each entry = a set of
# acceptable type names; the room must include at least one from each).
REQUIRED_FIXTURES = {
    "bathroom": [("a toilet", {"toilet"}), ("a sink/vanity", {"sink", "vanity"})],
}

# Type pairs that may sit close (< GAP_WALK) without it being a defect — the gap
# is the intended grouping (sofa↔coffee table, bed↔nightstand/bedside table).
GROUPED_OK = {
    frozenset({"sofa", "table"}),
    frozenset({"armchair", "table"}),
    frozenset({"bed", "nightstand"}),
    frozenset({"bed", "table"}),
    frozenset({"desk", "chair"}),
    frozenset({"island", "counter"}),
}

# Bulky floor pieces that need a real circulation gap around them. The dead-gap
# rule only fires between two of THESE — small wall-lined fixtures (a toilet beside
# a sink, a bookshelf, a nightstand) legitimately sit close and aren't dead space.
CIRCULATION_FURNITURE = {"bed", "sofa", "desk", "table", "island",
                         "dresser", "wardrobe", "armchair"}


# ── Geometry primitives ──────────────────────────────────────────────────────
def _open(poly):
    """Drop the repeated closing vertex if present."""
    return poly[:-1] if poly and poly[0] == poly[-1] else poly


def pip(pt, poly):
    """Ray-casting point-in-polygon. Accepts open or closed polygons."""
    p = _open(poly)
    x, y = pt
    inside = False
    n = len(p)
    j = n - 1
    for i in range(n):
        xi, yi = p[i]
        xj, yj = p[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def bbox(geom):
    xs = [p[0] for p in geom]
    ys = [p[1] for p in geom]
    return (min(xs), min(ys), max(xs), max(ys))


def rect_overlap(a, b):
    """Overlap rectangle of two AABBs, or None. Touching edges -> None."""
    ox0, oy0 = max(a[0], b[0]), max(a[1], b[1])
    ox1, oy1 = min(a[2], b[2]), min(a[3], b[3])
    if ox1 - ox0 > TOL and oy1 - oy0 > TOL:
        return (ox0, oy0, ox1, oy1)
    return None


def rect_area(r):
    return (r[2] - r[0]) * (r[3] - r[1])


def decompose(poly):
    """Tile an axis-aligned rectilinear polygon into a set of rectangles.

    Cut on every unique x and y of the polygon, keep cells whose centre is inside.
    Exact for rectangles and L-shapes alike — no sampling error.
    """
    p = _open(poly)
    xs = sorted({round(v[0], 6) for v in p})
    ys = sorted({round(v[1], 6) for v in p})
    cells = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx = (xs[i] + xs[i + 1]) / 2
            cy = (ys[j] + ys[j + 1]) / 2
            if pip((cx, cy), poly):
                cells.append((xs[i], ys[j], xs[i + 1], ys[j + 1]))
    return cells


def area_outside(rect, cells):
    """Area of `rect` not covered by the room's `cells` (its footprint outside the room)."""
    inside = sum(rect_area(o) for c in cells if (o := rect_overlap(rect, c)))
    return max(0.0, rect_area(rect) - inside)


def in_room(pt, cells):
    x, y = pt
    return any(c[0] - TOL <= x <= c[2] + TOL and c[1] - TOL <= y <= c[3] + TOL for c in cells)


# ── Layout model ─────────────────────────────────────────────────────────────
class Layout:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self._build(json.load(open(path, encoding="utf-8")))

    @classmethod
    def from_dict(cls, d, name="<memory>"):
        """Build a Layout from an in-memory layout dict (no file). Lets the edit
        chokepoint validate a working layout before committing it."""
        self = cls.__new__(cls)
        self.path = None
        self.name = name
        self._build(d)
        return self

    def _build(self, d):
        self.d = d
        self.rooms = {r["id"]: r for r in self.d.get("rooms", [])}
        self.cells = {rid: decompose(r["geometry"]) for rid, r in self.rooms.items()}

        # Obstacles = furniture only. MEP (exhaust hoods, ducts, wall units) is a
        # separate schema layer and legitimately overlaps counters / sits on walls,
        # so it is not part of the furniture-collision ground truth. Flat / soft
        # furnishings (rugs under furniture, curtains on the wall, cushions on a sofa)
        # are likewise NOT collision obstacles — excluding them lets the agent add a
        # rug under a sofa or a curtain at a window without a false overlap defect.
        self.obstacles = []
        for f in self.d.get("furniture", []):
            ftype = f.get("attributes", {}).get("type", "")
            if ftype.lower() in NON_OBSTACLE_TYPES:
                continue
            self.obstacles.append({
                "name": f["name"], "rect": bbox(f["geometry"]),
                "roomId": f.get("attributes", {}).get("roomId"),
                "type": ftype, "kind": "furniture",
            })

    def obstacles_in(self, rid):
        return [o for o in self.obstacles if o["roomId"] == rid]

    def room_name(self, rid):
        return self.rooms.get(rid, {}).get("name", rid)


# ── Individual checks (each appends human-readable defect strings) ────────────
def check_overlaps(lo, out):
    obs = lo.obstacles
    for i in range(len(obs)):
        for j in range(i + 1, len(obs)):
            ov = rect_overlap(obs[i]["rect"], obs[j]["rect"])
            if ov:
                out.append(f"furniture overlap: '{obs[i]['name']}' & '{obs[j]['name']}' "
                           f"share {rect_area(ov):.2f} m²")


def check_containment(lo, out):
    for o in lo.obstacles:
        if o["kind"] != "furniture":
            continue
        rid = o["roomId"]
        if rid not in lo.cells:
            continue
        outside = area_outside(o["rect"], lo.cells[rid])
        if outside > TOL:
            out.append(f"'{o['name']}' pokes outside {lo.room_name(rid)} / through a wall "
                       f"({outside:.2f} m² out)")


def _door_axis(g):
    """Return (is_vertical, const_coord, lo, hi) for an axis-aligned door segment."""
    (ax, ay), (bx, by) = g[0], g[-1]
    if abs(ax - bx) < 1e-9:            # vertical wall, runs in y
        return True, ax, min(ay, by), max(ay, by)
    return False, ay, min(ax, bx), max(ax, bx)


def check_door_width(lo, out):
    for dr in lo.d.get("doors", []):
        g = dr["geometry"]
        seg = math.dist(g[0], g[-1])
        stated = dr.get("attributes", {}).get("width", seg)
        leaf = stated
        # the smaller standard applies if any connected room is a store/closet/pantry
        conn = dr.get("attributes", {}).get("connectsRooms", [])
        names = " ".join(lo.room_name(c).lower() for c in conn)
        utility = any(h in names for h in UTILITY_NAME_HINTS)
        minw = DOOR_MIN_UTIL if utility else DOOR_MIN_HAB
        if leaf < minw - 1e-6:
            out.append(f"door '{dr['name']}' clear width {leaf:.2f} m < {minw:.2f} m standard")
        if abs(seg - stated) > 0.05:
            out.append(f"door '{dr['name']}' width attr {stated:.2f} m ≠ drawn leaf {seg:.2f} m")


def check_swing(lo, out):
    for dr in lo.d.get("doors", []):
        g = dr["geometry"]
        leaf = math.dist(g[0], g[-1])
        width = dr.get("attributes", {}).get("width", leaf)
        if width > SWING_MAX_LEAF:      # cased opening, no swinging leaf
            continue
        conn = dr.get("attributes", {}).get("connectsRooms", [])
        A, B = tuple(g[0]), tuple(g[-1])
        radius = leaf
        ok = False
        for hinge, other in ((A, B), (B, A)):
            tx, ty = other[0] - hinge[0], other[1] - hinge[1]
            tl = math.hypot(tx, ty) or 1.0
            tx, ty = tx / tl, ty / tl
            mid = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)
            # Each inward normal paired with the rotation sense that sweeps the
            # tangent onto it through +90°:  R(+90°)·t = (-ty, tx).
            for nx, ny, sign in ((-ty, tx, 1.0), (ty, -tx, -1.0)):
                probe = (mid[0] + 0.1 * nx, mid[1] + 0.1 * ny)
                rid = next((c for c in conn if in_room(probe, lo.cells.get(c, []))), None)
                if rid is None:
                    continue
                cells = lo.cells.get(rid, [])
                furn = [o["rect"] for o in lo.obstacles_in(rid)]
                blocked = False
                for k in range(0, 19):                 # 0..90° in 5° steps
                    phi = math.radians(5 * k) * sign
                    ux = tx * math.cos(phi) - ty * math.sin(phi)
                    uy = tx * math.sin(phi) + ty * math.cos(phi)
                    r = 0.10
                    while r <= radius + 1e-9:
                        pt = (hinge[0] + r * ux, hinge[1] + r * uy)
                        if not in_room(pt, cells):
                            blocked = True
                            break
                        if any(fr[0] - TOL <= pt[0] <= fr[2] + TOL and
                               fr[1] - TOL <= pt[1] <= fr[3] + TOL for fr in furn):
                            blocked = True
                            break
                        r += 0.10
                    if blocked:
                        break
                if not blocked:
                    ok = True
                    break
            if ok:
                break
        if not ok:
            out.append(f"door '{dr['name']}' swing blocked — no side opens clear of furniture")


def check_approach(lo, out):
    for dr in lo.d.get("doors", []):
        g = dr["geometry"]
        vert, const, lo_c, hi_c = _door_axis(g)
        conn = dr.get("attributes", {}).get("connectsRooms", [])
        for rid in conn:
            cells = lo.cells.get(rid, [])
            # which perpendicular direction points into this room?
            for s in (+1, -1):
                probe = (const + 0.1 * s, (lo_c + hi_c) / 2) if vert else ((lo_c + hi_c) / 2, const + 0.1 * s)
                if in_room(probe, cells):
                    side = s
                    break
            else:
                continue
            if vert:
                strip = (const, lo_c, const + APPROACH_DEPTH, hi_c) if side > 0 \
                        else (const - APPROACH_DEPTH, lo_c, const, hi_c)
            else:
                strip = (lo_c, const, hi_c, const + APPROACH_DEPTH) if side > 0 \
                        else (lo_c, const - APPROACH_DEPTH, hi_c, const)
            worst = 0.0
            culprit = None
            for o in lo.obstacles_in(rid):
                ov = rect_overlap(strip, o["rect"])
                if ov:
                    intr = (ov[2] - ov[0]) if vert else (ov[3] - ov[1])
                    if intr > worst:
                        worst, culprit = intr, o["name"]
            if culprit:
                clear = APPROACH_DEPTH - worst
                out.append(f"door '{dr['name']}' blocked entering {lo.room_name(rid)} — "
                           f"only {clear:.2f} m clear (need {APPROACH_DEPTH:.2f}); '{culprit}'")


def check_windows(lo, out):
    for w in lo.d.get("windows", []):
        g = w["geometry"]
        rid = w.get("attributes", {}).get("roomId")
        vert, const, lo_c, hi_c = _door_axis(g)
        for o in lo.obstacles_in(rid):
            if o["type"].lower() not in TALL_TYPES:
                continue
            fx0, fy0, fx1, fy1 = o["rect"]
            if vert:
                gap = max(fx0 - const, const - fx1, 0.0)
                span = min(hi_c, fy1) - max(lo_c, fy0)
            else:
                gap = max(fy0 - const, const - fy1, 0.0)
                span = min(hi_c, fx1) - max(lo_c, fx0)
            if gap <= WINDOW_GAP and span > 0.05:
                out.append(f"window '{w['name']}' blocked by '{o['name']}' "
                           f"(tall, {gap:.2f} m from glazing)")


def check_circulation(lo, out):
    for rid, r in lo.rooms.items():
        rtype = r.get("attributes", {}).get("roomType", "")
        if rtype != "circulation" and "hall" not in r.get("name", "").lower():
            continue
        x0, y0, x1, y1 = bbox(r["geometry"])
        w, h = x1 - x0, y1 - y0
        short = min(w, h)
        if short >= CORRIDOR_MAX_DIM:        # a room, not a corridor
            continue
        width_axis_vertical = h < w          # corridor runs along its long axis
        for o in lo.obstacles_in(rid):
            fx0, fy0, fx1, fy1 = o["rect"]
            depth = (fy1 - fy0) if width_axis_vertical else (fx1 - fx0)
            clear = short - depth            # best case: piece pushed against a wall
            if clear < CIRC_MIN - 1e-6:
                out.append(f"corridor {r['name']} clear width {clear:.2f} m < {CIRC_MIN:.2f} m "
                           f"(blocked by '{o['name']}')")


def check_scale(lo, out):
    """Flag furniture whose footprint is not a plausible real-world size."""
    for o in lo.obstacles:
        spec = FURNITURE_SIZE.get(o["type"].lower())
        if not spec:
            continue
        x0, y0, x1, y1 = o["rect"]
        w, h = x1 - x0, y1 - y0
        small, large = sorted((w, h))
        smin, smax, lmin, lmax = spec
        if (small < smin - 0.03 or small > smax + 0.03
                or large < lmin - 0.03 or large > lmax + 0.03):
            out.append(f"'{o['name']}' ({o['type']}) is {w:.2f}×{h:.2f} m — outside the "
                       f"plausible range ({smin:.2f}–{smax:.2f} short × {lmin:.2f}–{lmax:.2f} long)")


def check_fixtures(lo, out):
    """Flag rooms missing a fixture their type requires (e.g. a bathroom toilet)."""
    for rid, r in lo.rooms.items():
        reqs = REQUIRED_FIXTURES.get(r.get("attributes", {}).get("roomType", ""))
        if not reqs:
            continue
        present = {o["type"].lower() for o in lo.obstacles_in(rid)}
        for label, accept in reqs:
            if not (present & accept):
                out.append(f"{r['name']} is missing {label}")


def _facing_gap(a, b):
    """If two AABBs face each other across one axis, return their gap; else None."""
    yov = min(a[3], b[3]) - max(a[1], b[1])
    xov = min(a[2], b[2]) - max(a[0], b[0])
    if yov > 0.10 and xov <= 0:        # side by side, gap in x
        return max(b[0] - a[2], a[0] - b[2])
    if xov > 0.10 and yov <= 0:        # stacked, gap in y
        return max(b[1] - a[3], a[1] - b[3])
    return None


def check_furniture_gaps(lo, out):
    """Flag dead space — two pieces too far apart to be a pair, too close to walk."""
    by_room = {}
    for o in lo.obstacles:
        by_room.setdefault(o["roomId"], []).append(o)
    for rid, items in by_room.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                ta, tb = a["type"].lower(), b["type"].lower()
                if ta not in CIRCULATION_FURNITURE or tb not in CIRCULATION_FURNITURE:
                    continue
                gap = _facing_gap(a["rect"], b["rect"])
                if gap is None or not (GAP_MIN < gap < GAP_WALK):
                    continue
                if frozenset({ta, tb}) in GROUPED_OK:
                    continue
                out.append(f"dead gap {gap:.2f} m between '{a['name']}' and '{b['name']}' "
                           f"in {lo.room_name(rid)} — too tight to use, too wide to be paired")


def _clear_on_side(rect, side, rbb, others):
    """Clear distance from one side of `rect` to the nearest wall/furniture facing it."""
    bx0, by0, bx1, by1 = rect
    rx0, ry0, rx1, ry1 = rbb
    if side in ("left", "right"):
        face = lambda f: min(by1, f[3]) - max(by0, f[1]) > 0.05
        if side == "right":
            g = rx1 - bx1
            g = min([g] + [f[0] - bx1 for f in others if face(f) and f[0] >= bx1 - TOL])
        else:
            g = bx0 - rx0
            g = min([g] + [bx0 - f[2] for f in others if face(f) and f[2] <= bx0 + TOL])
    else:
        face = lambda f: min(bx1, f[2]) - max(bx0, f[0]) > 0.05
        if side == "top":
            g = ry1 - by1
            g = min([g] + [f[1] - by1 for f in others if face(f) and f[1] >= by1 - TOL])
        else:
            g = by0 - ry0
            g = min([g] + [by0 - f[3] for f in others if face(f) and f[3] <= by0 + TOL])
    return max(0.0, g)


def check_bed_access(lo, out):
    """A bed must have ≥ ACCESS_CLEAR on at least one of its two long sides."""
    for o in lo.obstacles:
        if o["type"].lower() != "bed" or o["roomId"] not in lo.rooms:
            continue
        rbb = bbox(lo.rooms[o["roomId"]]["geometry"])
        # A bedside table grouped with the bed doesn't block getting in.
        others = [x["rect"] for x in lo.obstacles_in(o["roomId"])
                  if x is not o and frozenset({"bed", x["type"].lower()}) not in GROUPED_OK]
        x0, y0, x1, y1 = o["rect"]
        sides = ("left", "right") if (y1 - y0) >= (x1 - x0) else ("top", "bottom")
        best = max(_clear_on_side(o["rect"], s, rbb, others) for s in sides)
        if best < ACCESS_CLEAR - 1e-6:
            out.append(f"'{o['name']}' has no clear access side "
                       f"(best {best:.2f} m < {ACCESS_CLEAR:.2f})")


CHECKS = [check_overlaps, check_containment, check_swing, check_approach,
          check_door_width, check_windows, check_circulation,
          check_scale, check_fixtures, check_furniture_gaps, check_bed_access]


def _run_checks(lo):
    defects = []
    for chk in CHECKS:
        try:
            chk(lo, defects)
        except Exception as e:  # noqa: BLE001 — a malformed element must not crash the audit
            defects.append(f"{getattr(chk, '__name__', 'check')} errored: {e}")
    return defects


def audit(path):
    return _run_checks(Layout(path))


def audit_layout(layout_dict):
    """Run the architectural-soundness checks on an in-memory layout dict.

    The graph entry point used by apply_edits to validate an edit before committing.
    Returns the same human-readable defect strings as the CLI `audit(path)`."""
    return _run_checks(Layout.from_dict(layout_dict))


def main(argv):
    paths = argv[1:]
    if not paths:
        here = os.path.dirname(os.path.abspath(__file__))
        paths = sorted(glob.glob(os.path.join(here, "..", "randomized_layouts", "*.json")))
    total = 0
    for path in paths:
        name = os.path.basename(path)
        try:
            defects = audit(path)
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] {name}: {e}")
            total += 1
            continue
        if defects:
            total += len(defects)
            print(f"[DEFECT] {name} — {len(defects)} issue(s)")
            for d in defects:
                print(f"    - {d}")
        else:
            print(f"[OK] {name}")
    print(f"\n{total} architectural issue(s) across {len(paths)} layout(s).")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
