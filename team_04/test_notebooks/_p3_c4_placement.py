"""
Building Placement Engine — proposes a building footprint on the site
based on road hierarchy, junction type, and urban importance.

Rules embedded:
  H-building  → longest wing parallel to primary road (commercial frontage)
  Wide slab   → long facade faces the T-junction view axis
  L-building  → two wings: one to primary road, one to secondary road
  Tower       → centroid shift toward primary road corner
"""
import math
from shapely.geometry import Polygon as SlyPoly, box as _box
from shapely.ops import unary_union


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _rotate_pt(x, y, cx, cy, angle_deg):
    """Rotate point (x,y) around centre (cx,cy)."""
    a = math.radians(angle_deg)
    dx, dy = x - cx, y - cy
    return cx + dx*math.cos(a) - dy*math.sin(a), cy + dx*math.sin(a) + dy*math.cos(a)

def _rotate_poly(poly, cx, cy, angle_deg):
    """Return a new Polygon with all exterior coords rotated."""
    if poly is None or poly.is_empty: return poly
    pts = [_rotate_pt(x, y, cx, cy, angle_deg) for x, y in poly.exterior.coords]
    return SlyPoly(pts)

def _site_bounds(site_bdry):
    pts = [(p[0], p[1]) for p in site_bdry]
    xs  = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)   # xmin, ymin, xmax, ymax


def _grid_angle_deg(road):
    """
    Angle of the primary road in degrees from East (0° = E-W, 90° = N-S).
    Returns 0.0 if the centerline is undefined.
    """
    cl = road.get('centerline', [])
    if len(cl) < 2: return 0.0
    dx = cl[-1][0] - cl[0][0]
    dy = cl[-1][1] - cl[0][1]
    return math.degrees(math.atan2(dy, dx))


def _main_facing(site_bdry, road):
    """
    Which site edge is CLOSEST to the primary road centerline?
    Returns 'S', 'N', 'E', or 'W'.
    """
    xmin, ymin, xmax, ymax = _site_bounds(site_bdry)
    cx = (xmin+xmax)/2; cy = (ymin+ymax)/2

    cl = road.get('centerline', [])
    if not cl: return 'S'
    # Sample 5 evenly spaced points along the road centerline
    n = min(len(cl), 5)
    pts = [cl[int(i*(len(cl)-1)/(n-1))] for i in range(n)]

    # Distance from each site edge to road midpoints
    def _edge_dist(edge_pts, road_pts):
        from shapely.geometry import LineString, Point
        edge = LineString(edge_pts)
        return min(edge.distance(Point(p)) for p in road_pts)

    edges = {
        'S': [(xmin, ymin), (xmax, ymin)],
        'N': [(xmin, ymax), (xmax, ymax)],
        'W': [(xmin, ymin), (xmin, ymax)],
        'E': [(xmax, ymin), (xmax, ymax)],
    }
    return min(edges, key=lambda k: _edge_dist(edges[k], pts))


# ── Typology generators ───────────────────────────────────────────────────────

def _make_H(site_bdry, primary_road):
    """
    H-building: two parallel long wings connected by a central crossbar.
    RULE: Wing A (longest) is placed adjacent to the primary road — commercial frontage.
    Wing B is the rear wing — quieter office/residential program.
    Connector is the central crossbar linking the two wings.
    """
    xmin, ymin, xmax, ymax = _site_bounds(site_bdry)
    cx = (xmin+xmax)/2; cy = (ymin+ymax)/2
    sw = xmax-xmin; sd = ymax-ymin

    mf = _main_facing(site_bdry, primary_road)

    # Proportions
    sb       = 2.5           # setback from site edge
    wing_d   = min(8.0, sd*0.20)  # wing depth
    wing_l   = sw - sb*2         # wing length (full width minus setbacks)
    conn_w   = min(9.0, sw*0.28) # connector width
    # Connector depth = gap between Wing A and Wing B minus their own depths
    gap_d    = sd - sb*2 - wing_d*2
    gap_d    = max(gap_d, 4.0)   # ensure minimum courtyard

    if mf == 'S':
        # Wing A — south (primary road facing), commercial
        wA  = _box(cx-wing_l/2, ymin+sb,          cx+wing_l/2, ymin+sb+wing_d)
        # Wing B — north (rear), quiet
        wB  = _box(cx-wing_l/2, ymax-sb-wing_d,   cx+wing_l/2, ymax-sb)
        # Connector — central crossbar
        conn= _box(cx-conn_w/2, ymin+sb+wing_d,   cx+conn_w/2, ymax-sb-wing_d)
        A_prog = 'Wing A — Commercial retail / active ground floor'
        B_prog = 'Wing B — Office / residential / quieter program'
        A_cx, A_cy   = cx, ymin+sb+wing_d/2
        B_cx, B_cy   = cx, ymax-sb-wing_d/2
        co_cx, co_cy = cx, cy
        A_dir_deg    = 270   # arrow pointing south toward main road
        B_dir_deg    = 90    # arrow pointing north toward quiet side
        courtyard_open = 'East and West'
    elif mf == 'N':
        wA  = _box(cx-wing_l/2, ymax-sb-wing_d,   cx+wing_l/2, ymax-sb)
        wB  = _box(cx-wing_l/2, ymin+sb,          cx+wing_l/2, ymin+sb+wing_d)
        conn= _box(cx-conn_w/2, ymin+sb+wing_d,   cx+conn_w/2, ymax-sb-wing_d)
        A_prog = 'Wing A — Commercial retail / active ground floor'
        B_prog = 'Wing B — Office / residential / quieter program'
        A_cx, A_cy   = cx, ymax-sb-wing_d/2
        B_cx, B_cy   = cx, ymin+sb+wing_d/2
        co_cx, co_cy = cx, cy
        A_dir_deg    = 90; B_dir_deg = 270
        courtyard_open = 'East and West'
    elif mf == 'W':
        # Rotate H 90° — wings now run N-S
        wing_l2 = sd - sb*2
        wA  = _box(xmin+sb,          cy-wing_l2/2, xmin+sb+wing_d,         cy+wing_l2/2)
        wB  = _box(xmax-sb-wing_d,   cy-wing_l2/2, xmax-sb,                cy+wing_l2/2)
        conn= _box(xmin+sb+wing_d,   cy-conn_w/2,  xmax-sb-wing_d,         cy+conn_w/2)
        A_prog = 'Wing A — Commercial retail / active ground floor'
        B_prog = 'Wing B — Office / residential / quieter program'
        A_cx, A_cy   = xmin+sb+wing_d/2, cy
        B_cx, B_cy   = xmax-sb-wing_d/2, cy
        co_cx, co_cy = cx, cy
        A_dir_deg    = 180; B_dir_deg = 0
        courtyard_open = 'North and South'
    else:  # 'E'
        wing_l2 = sd - sb*2
        wA  = _box(xmax-sb-wing_d,   cy-wing_l2/2, xmax-sb,                cy+wing_l2/2)
        wB  = _box(xmin+sb,          cy-wing_l2/2, xmin+sb+wing_d,         cy+wing_l2/2)
        conn= _box(xmin+sb+wing_d,   cy-conn_w/2,  xmax-sb-wing_d,         cy+conn_w/2)
        A_prog = 'Wing A — Commercial retail / active ground floor'
        B_prog = 'Wing B — Office / residential / quieter program'
        A_cx, A_cy   = xmax-sb-wing_d/2, cy
        B_cx, B_cy   = xmin+sb+wing_d/2, cy
        co_cx, co_cy = cx, cy
        A_dir_deg    = 0; B_dir_deg = 180
        courtyard_open = 'North and South'

    footprint = unary_union([wA, wB, conn])
    coverage  = footprint.area / (sw*sd)
    far_est   = coverage * 4   # 4-storey estimate

    grid_angle = _grid_angle_deg(primary_road)
    pname = primary_road.get('name') or 'primary road'
    pwidth= primary_road.get('width_m', 20)

    reasoning = [
        f"Grid angle: {grid_angle:.0f} deg (from {pname})",
        f"Primary road '{pname}' ({pwidth:.0f} m) is to the {mf}.",
        "RULE: longest wing parallel to primary road → Wing A faces " + mf + ".",
        f"Wing A ({wing_l:.0f} m long x {wing_d:.0f} m deep): {A_prog.split('—')[1].strip()}",
        f"Wing B ({wing_l:.0f} m long x {wing_d:.0f} m deep): {B_prog.split('—')[1].strip()}",
        f"Connector ({conn_w:.0f} m wide): vertical circulation, structural core.",
        f"Courtyard opens to {courtyard_open} — daylight to all wings.",
        f"Coverage: {coverage:.0%}  |  Est. FAR (4 floors): {far_est:.1f}",
    ]

    return dict(
        typology='H-Building', grid_angle=grid_angle, main_facing=mf,
        wing_A=wA, wing_B=wB, connector=conn, footprint=footprint,
        A_label='WING A', B_label='WING B', conn_label='CONNECTOR',
        A_program=A_prog, B_program=B_prog,
        A_center=(A_cx, A_cy), B_center=(B_cx, B_cy), conn_center=(co_cx, co_cy),
        A_dir_deg=A_dir_deg, B_dir_deg=B_dir_deg,
        coverage=coverage, far_est=far_est, reasoning=reasoning,
        courtyard_open=courtyard_open,
    )


def _make_slab(site_bdry, primary_road, face_axis=False):
    """
    Wide slab: single long block with one primary public facade.
    Used for T-junction terminals — the building addresses the view axis.
    face_axis=True shifts the slab toward the axis end.
    """
    xmin, ymin, xmax, ymax = _site_bounds(site_bdry)
    cx = (xmin+xmax)/2; cy = (ymin+ymax)/2
    sw = xmax-xmin; sd = ymax-ymin

    mf = _main_facing(site_bdry, primary_road)
    sb = 2.5

    if mf in ('S', 'N'):
        slab_d = min(sd*0.60, 22)
        slab_l = sw - sb*2
        if mf == 'S':
            y0 = ymin+sb; y1 = y0+slab_d
        else:
            y1 = ymax-sb; y0 = y1-slab_d
        slab = _box(cx-slab_l/2, y0, cx+slab_l/2, y1)
        A_cx, A_cy = cx, (y0+y1)/2
        A_dir_deg  = 270 if mf=='S' else 90
    else:
        slab_l = min(sw*0.60, 22)
        slab_d = sd - sb*2
        if mf == 'W':
            x0 = xmin+sb; x1 = x0+slab_l
        else:
            x1 = xmax-sb; x0 = x1-slab_l
        slab = _box(x0, ymin+sb, x1, ymax-sb)
        A_cx, A_cy = (x0+x1)/2, cy
        A_dir_deg  = 180 if mf=='W' else 0

    footprint = slab
    coverage  = footprint.area / (sw*sd)
    far_est   = coverage * 5

    grid_angle = _grid_angle_deg(primary_road)
    pname = primary_road.get('name') or 'primary road'
    pwidth = primary_road.get('width_m', 20)

    reasoning = [
        f"Grid angle: {grid_angle:.0f} deg (from {pname})",
        f"Primary road '{pname}' ({pwidth:.0f} m) is to the {mf}.",
        "RULE: T-junction terminal — long facade faces the VIEW AXIS.",
        f"Slab ({slab_l if mf in ('E','W') else sw-sb*2:.0f} m long): primary public facade toward junction.",
        "Slender profile maximises floor count and reinforces the visual axis.",
        "All building services face the rear (quieter side).",
        f"Coverage: {coverage:.0%}  |  Est. FAR (5 floors): {far_est:.1f}",
    ]

    return dict(
        typology='Wide Slab', grid_angle=grid_angle, main_facing=mf,
        wing_A=slab, wing_B=None, connector=None, footprint=footprint,
        A_label='SLAB FACADE', B_label='', conn_label='',
        A_program='Primary facade — addresses T-junction view axis',
        B_program='Rear service / secondary access',
        A_center=(A_cx, A_cy), B_center=(cx, cy), conn_center=(cx, cy),
        A_dir_deg=A_dir_deg, B_dir_deg=None,
        coverage=coverage, far_est=far_est, reasoning=reasoning,
        courtyard_open=None,
    )


def _make_L(site_bdry, primary_road, secondary_road=None):
    """
    L-building: one wing to the primary road, one perpendicular to secondary.
    Used for corner sites where the L 'wraps' the corner.
    """
    xmin, ymin, xmax, ymax = _site_bounds(site_bdry)
    cx = (xmin+xmax)/2; cy = (ymin+ymax)/2
    sw = xmax-xmin; sd = ymax-ymin

    mf = _main_facing(site_bdry, primary_road)
    sb = 2.5

    # Determine the secondary facing (90 degrees from primary)
    # Try to find it from secondary road; otherwise default
    if secondary_road:
        sf = _main_facing(site_bdry, secondary_road)
    else:
        # default: clockwise from main
        sf = {'S':'W', 'W':'N', 'N':'E', 'E':'S'}[mf]

    arm_d = min(8.0, sw*0.25)  # arm depth

    if mf == 'S' and sf == 'W':
        # Horizontal arm along south (primary), vertical arm along west (secondary)
        armA = _box(xmin+sb, ymin+sb, xmax-sb,    ymin+sb+arm_d)
        armB = _box(xmin+sb, ymin+sb, xmin+sb+arm_d, ymax-sb)
        A_cx, A_cy = cx, ymin+sb+arm_d/2
        B_cx, B_cy = xmin+sb+arm_d/2, cy
        A_dir_deg  = 270; B_dir_deg = 180
    elif mf == 'S' and sf == 'E':
        armA = _box(xmin+sb, ymin+sb, xmax-sb,     ymin+sb+arm_d)
        armB = _box(xmax-sb-arm_d, ymin+sb, xmax-sb, ymax-sb)
        A_cx, A_cy = cx, ymin+sb+arm_d/2
        B_cx, B_cy = xmax-sb-arm_d/2, cy
        A_dir_deg  = 270; B_dir_deg = 0
    elif mf == 'W' and sf == 'S':
        armA = _box(xmin+sb, ymin+sb, xmin+sb+arm_d, ymax-sb)
        armB = _box(xmin+sb, ymin+sb, xmax-sb, ymin+sb+arm_d)
        A_cx, A_cy = xmin+sb+arm_d/2, cy
        B_cx, B_cy = cx, ymin+sb+arm_d/2
        A_dir_deg  = 180; B_dir_deg = 270
    else:
        # Generic fallback: L in SW corner
        armA = _box(xmin+sb, ymin+sb, xmax-sb, ymin+sb+arm_d)
        armB = _box(xmin+sb, ymin+sb, xmin+sb+arm_d, ymax-sb)
        A_cx, A_cy = cx, ymin+sb+arm_d/2
        B_cx, B_cy = xmin+sb+arm_d/2, cy
        A_dir_deg = 270; B_dir_deg = 180

    footprint = unary_union([armA, armB])
    coverage  = footprint.area / (sw*sd)
    far_est   = coverage * 5

    grid_angle = _grid_angle_deg(primary_road)
    pname = primary_road.get('name') or 'primary road'
    pwidth = primary_road.get('width_m', 20)
    sec_name = secondary_road.get('name') or 'secondary road' if secondary_road else 'secondary road'

    reasoning = [
        f"Grid angle: {grid_angle:.0f} deg (from {pname})",
        f"Corner site: '{pname}' ({pwidth:.0f} m) is to the {mf}, '{sec_name}' to the {sf}.",
        "RULE: L-building wraps the corner — Arm A faces primary road, Arm B faces secondary.",
        f"Arm A ({sw-sb*2:.0f} m long): Primary facade — commercial ground floor toward {pname}.",
        f"Arm B ({sd-sb*2:.0f} m long): Secondary facade — office / mixed-use toward {sec_name}.",
        "Corner junction: activate corner with recessed entrance or chamfered edge.",
        "Open courtyard: fills the L interior — passive ventilation and light.",
        f"Coverage: {coverage:.0%}  |  Est. FAR (5 floors): {far_est:.1f}",
    ]

    return dict(
        typology='L-Building', grid_angle=grid_angle, main_facing=mf,
        wing_A=armA, wing_B=armB, connector=None, footprint=footprint,
        A_label='ARM A', B_label='ARM B', conn_label='',
        A_program='Arm A — Commercial / primary frontage',
        B_program='Arm B — Office / secondary frontage',
        A_center=(A_cx, A_cy), B_center=(B_cx, B_cy), conn_center=((A_cx+B_cx)/2,(A_cy+B_cy)/2),
        A_dir_deg=A_dir_deg, B_dir_deg=B_dir_deg,
        coverage=coverage, far_est=far_est, reasoning=reasoning,
        courtyard_open='Interior L-courtyard',
        secondary_facing=sf,
    )


# ── Main proposal dispatcher ──────────────────────────────────────────────────

IX_TYPOLOGY = {
    # junction_type → (building_typology, function_key)
    'crossroads':       ('H-Building',  'H'),
    't_junction':       ('Wide Slab',   'slab'),
    'y_junction':       ('L-Building',  'L'),
    'complex_junction': ('H-Building',  'H'),
    'roundabout':       ('H-Building',  'H'),
    'dead_end':         ('Wide Slab',   'slab'),
    'bend':             ('L-Building',  'L'),
}

def propose_building(site_bdry, primary_road, site_type, importance_score,
                     secondary_road=None, junction_type=None):
    """
    Dispatch to the correct typology based on site context.
    Returns the placement dict from _make_H / _make_slab / _make_L.
    """
    # Choose typology
    if junction_type and junction_type in IX_TYPOLOGY:
        _, key = IX_TYPOLOGY[junction_type]
    elif site_type in ('t_junction_terminal',):
        key = 'slab'
    elif site_type in ('corner', 'triangular_corner'):
        key = 'L'
    else:
        key = 'H'    # default: H-building

    # Override by importance: very high importance → always H (landmark)
    if importance_score >= 0.70:
        key = 'H'

    if key == 'H':
        return _make_H(site_bdry, primary_road)
    elif key == 'slab':
        return _make_slab(site_bdry, primary_road)
    else:
        return _make_L(site_bdry, primary_road, secondary_road)

print('Building placement engine ready')
print('  Typologies: H-Building (crossroads/complex) | Wide Slab (T-junction) | L-Building (corner/Y)')
