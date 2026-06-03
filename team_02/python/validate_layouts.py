"""
Layout integrity validator for Sensi example layouts.

Checks each layout JSON for sound architectural-planning logic:
  1. Rooms tile the building outline with no overlaps and no gaps.
  2. Every door lies on a wall shared by exactly the two rooms it connects.
  3. Every furniture piece sits inside the room it claims (roomId).
  4. Each room's stated `attributes.area` matches its geometry.

Pure stdlib (point-in-polygon sampling), so it handles L-shaped rooms too.

Usage (from the AIA26_Studio repo root, or anywhere):
    python team_02/python/validate_layouts.py
    python team_02/python/validate_layouts.py path/to/layout.json [more.json ...]

Exits non-zero if any layout has a defect, so it can gate CI / pre-commit.
"""
import json
import os
import sys
import glob

STEP = 0.25  # grid sample size (m) for overlap/gap detection


def pip(pt, poly):
    """Ray-casting point-in-polygon. poly may be open or closed."""
    p = poly[:-1] if poly and poly[0] == poly[-1] else poly
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


def obb(geom):
    xs = [p[0] for p in geom]
    ys = [p[1] for p in geom]
    return [min(xs), min(ys), max(xs), max(ys)]


def shoelace(poly):
    pts = poly[:-1] if poly[0] == poly[-1] else poly
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return round(abs(s) / 2.0, 1)


def validate(path):
    """Return a list of defect strings ([] means clean)."""
    d = json.load(open(path, encoding="utf-8"))
    defects = []
    rooms = {r["id"]: (r["name"], r["geometry"], r.get("attributes", {})) for r in d.get("rooms", [])}
    outline = d.get("outline")
    if not outline:
        return ["no building outline"]

    # 1. tiling: sample grid, count rooms covering each interior cell
    ob = obb(outline)
    cell = STEP * STEP
    overlap = gap = 0.0
    y = ob[1] + STEP / 2
    while y < ob[3]:
        x = ob[0] + STEP / 2
        while x < ob[2]:
            if pip((x, y), outline):
                cnt = sum(1 for _, g, _ in rooms.values() if pip((x, y), g))
                if cnt > 1:
                    overlap += cell
                elif cnt == 0:
                    gap += cell
            x += STEP
        y += STEP
    if overlap > 0.3:
        defects.append(f"rooms overlap by ~{round(overlap, 1)} m²")
    if gap > 0.3:
        defects.append(f"unassigned floor area ~{round(gap, 1)} m² (gaps)")

    # 2. doors on a shared wall of their two connected rooms
    for dr in d.get("doors", []):
        g = dr["geometry"]
        conn = dr.get("attributes", {}).get("connectsRooms", [])
        if len(conn) != 2 or any(c not in rooms for c in conn):
            defects.append(f"door '{dr['name']}' has bad connectsRooms {conn}")
            continue
        ax, ay = g[0]
        bx, by = g[-1]
        mx, my = (ax + bx) / 2, (ay + by) / 2
        dx, dy = bx - ax, by - ay
        L = (dx * dx + dy * dy) ** 0.5 or 1.0
        nx, ny = -dy / L, dx / L
        s1 = (mx + 0.2 * nx, my + 0.2 * ny)
        s2 = (mx - 0.2 * nx, my - 0.2 * ny)
        g1 = rooms[conn[0]][1]
        g2 = rooms[conn[1]][1]
        ok = (pip(s1, g1) and pip(s2, g2)) or (pip(s1, g2) and pip(s2, g1))
        if not ok:
            defects.append(f"door '{dr['name']}' is not on the shared wall of {conn}")

    # 3. furniture inside its room
    for f in d.get("furniture", []):
        b = obb(f["geometry"])
        c = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        rid = f.get("attributes", {}).get("roomId")
        if rid in rooms and not pip(c, rooms[rid][1]):
            defects.append(f"furniture '{f['name']}' is outside {rooms[rid][0]}")

    # 4. stated area matches geometry
    for _id, (name, geom, attr) in rooms.items():
        stated = attr.get("area")
        if stated is not None and abs(shoelace(geom) - stated) > 0.2:
            defects.append(f"{name}: stated area {stated} != geometry {shoelace(geom)}")

    return defects


def main(argv):
    paths = argv[1:]
    if not paths:
        here = os.path.dirname(os.path.abspath(__file__))
        paths = sorted(glob.glob(os.path.join(here, "..", "randomized_layouts", "*.json")))
    bad = 0
    for path in paths:
        name = os.path.basename(path)
        try:
            defects = validate(path)
        except Exception as e:  # noqa: BLE001
            print(f"[ERROR] {name}: {e}")
            bad += 1
            continue
        if defects:
            bad += 1
            print(f"[DEFECT] {name}")
            for d in defects:
                print(f"    - {d}")
        else:
            print(f"[OK] {name}")
    if bad:
        print(f"\n{bad} layout(s) with problems.")
        return 1
    print("\nAll layouts valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
