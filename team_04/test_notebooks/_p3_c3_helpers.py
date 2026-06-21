import math
from shapely.geometry import LineString, Point, Polygon as SlyPoly
from shapely.ops import unary_union

def _road_poly(road):
    cl = road.get('centerline', []); w = road.get('width_m', 6.0)
    if len(cl) < 2: return None
    try: return LineString(cl).buffer(w/2, cap_style=2, join_style=2)
    except: return None

def _sidewalk_poly(road):
    cl = road.get('centerline', []); w = road.get('width_m', 6.0)
    h = road.get('hierarchy', 'path')
    if len(cl) < 2 or h == 'path': return None
    sw = 3.5 if h == 'main' else 2.5
    try:
        return (LineString(cl).buffer(w/2+sw, cap_style=2, join_style=2)
                .difference(LineString(cl).buffer(w/2, cap_style=2, join_style=2)))
    except: return None

def _draw_poly(ax, geom, fc='#CCC', ec='none', alpha=1.0, lw=0.5, zorder=1):
    if geom is None or geom.is_empty: return
    polys = [geom] if geom.geom_type == 'Polygon' else list(getattr(geom, 'geoms', []))
    for p in polys:
        if hasattr(p, 'exterior'):
            xs, ys = p.exterior.xy
            ax.fill(xs, ys, fc=fc, ec=ec, alpha=alpha, linewidth=lw, zorder=zorder)

def _vis_color(s):
    return '#{:02X}{:02X}{:02X}'.format(
        int(244+(42-244)*s), int(226+(157-226)*s), int(133+(143-133)*s))

def _imp_color(s):
    t = max(0, min(1, s))
    return '#{:02X}{:02X}{:02X}'.format(
        int(30+(255-30)*t), int(100+(215-100)*t), int(255+(0-255)*t))

def _bc_color(s, mn=0, mx=1):
    t = max(0, min(1, (s-mn)/(mx-mn+1e-9)))
    return '#{:02X}{:02X}{:02X}'.format(
        int(37+(212-37)*t), int(99+(37-99)*t), int(212+(37-212)*t))

def _draw_cone(ax, apex, dir_deg, half=45, dist=70, fc='#FFD70022', ec='#FFD700', lw=1.0, z=4):
    ang_c = math.radians(dir_deg)
    ang1 = ang_c - math.radians(half); ang2 = ang_c + math.radians(half)
    xs = [apex[0]]; ys = [apex[1]]
    for i in range(21):
        a = ang1 + (ang2-ang1)*i/20
        xs.append(apex[0]+dist*math.cos(a)); ys.append(apex[1]+dist*math.sin(a))
    xs.append(apex[0]); ys.append(apex[1])
    ax.fill(xs, ys, fc=fc, ec=ec, lw=lw, zorder=z)

def _outward_dir(p1, p2, site_cx, site_cy):
    dx, dy = p2[0]-p1[0], p2[1]-p1[1]; L = math.hypot(dx,dy)+1e-9
    nxv, nyv = -dy/L, dx/L
    midx, midy = (p1[0]+p2[0])/2, (p1[1]+p2[1])/2
    if nxv*(midx-site_cx)+nyv*(midy-site_cy) < 0: nxv, nyv = -nxv, -nyv
    return math.degrees(math.atan2(nyv, nxv))

HIER_OSM  = {'main': 1.0, 'secondary': 0.5, 'path': 0.2}
HIER_AF   = {'main': 0.7, 'secondary': 0.4, 'path': 0.1}
HIER_RANK = {'main': 1, 'secondary': 2, 'path': 3}

def _road_importance(road, bc_vals, graph, max_bc):
    h   = road.get('hierarchy', 'path')
    osm = HIER_OSM.get(h, 0.2); af = HIER_AF.get(h, 0.1)
    bc = conn = 0.0
    cl = road.get('centerline', [])
    if cl and bc_vals and graph is not None and len(graph.nodes) > 0:
        mid = cl[len(cl)//2]
        try:
            nid  = min(graph.nodes(), key=lambda n: (graph.nodes[n]['x']-mid[0])**2+(graph.nodes[n]['y']-mid[1])**2)
            bc   = bc_vals.get(nid, 0)/(max_bc or 1)
            conn = min(graph.degree(nid)/8.0, 1.0)
        except: pass
    return round(osm*0.40 + bc*0.30 + conn*0.20 + af*0.10, 4)

def _gen_urban_fabric(roads, site_poly, road_union, seed=7):
    """
    Generate road-aligned buildings that look like real urban fabric.
    Buildings follow the road direction, vary in width/depth, and have
    small gaps between them — far more realistic than a regular grid.
    """
    import random
    rng = random.Random(seed)
    buildings = []

    for road in roads:
        h   = road.get('hierarchy', 'path')
        w   = road.get('width_m', 6.0)
        cl  = road.get('centerline', [])
        if len(cl) < 2: continue

        line = LineString(cl)
        road_len = line.length

        # Building parameters per hierarchy
        if h == 'main':
            b_d_range  = (12, 20)   # depth range (m)
            b_w_range  = (10, 24)   # width (plot frontage)
            gap_range  = (0.8, 2.5) # gap between buildings
            setback    = 1.5        # from road edge
        elif h == 'secondary':
            b_d_range  = (9, 16)
            b_w_range  = (7, 18)
            gap_range  = (1.0, 3.5)
            setback    = 1.2
        else:
            continue   # no buildings generated along paths

        for side in (1, -1):          # both sides of the road
            x_pos = rng.uniform(4, 10)  # random start offset

            while x_pos < road_len - 6:
                b_w = rng.uniform(*b_w_range)
                b_d = rng.uniform(*b_d_range)
                if x_pos + b_w > road_len: break

                # Get road direction at this position
                pt_s = line.interpolate(x_pos)
                pt_e = line.interpolate(min(x_pos + b_w, road_len - 0.1))
                dx   = pt_e.x - pt_s.x; dy = pt_e.y - pt_s.y
                L    = math.hypot(dx, dy) + 1e-9
                # Outward perpendicular
                nx = -dy/L * side; ny = dx/L * side

                road_offset = w/2 + setback

                # Building footprint (parallelogram aligned to road)
                p1 = (pt_s.x + nx*road_offset,        pt_s.y + ny*road_offset)
                p2 = (pt_e.x + nx*road_offset,        pt_e.y + ny*road_offset)
                p3 = (pt_e.x + nx*(road_offset+b_d),  pt_e.y + ny*(road_offset+b_d))
                p4 = (pt_s.x + nx*(road_offset+b_d),  pt_s.y + ny*(road_offset+b_d))

                # Slight taper on one side for organic feel
                taper = rng.uniform(-0.5, 0.5)
                p3 = (p3[0] + nx*taper, p3[1] + ny*taper)

                try:
                    bpoly = SlyPoly([p1, p2, p3, p4])
                    if not bpoly.is_valid: bpoly = bpoly.buffer(0)
                    if bpoly.is_empty: raise ValueError
                    # Skip if it clips the road surface or the site
                    if road_union and road_union.buffer(0.5).intersects(bpoly): raise ValueError
                    if site_poly  and site_poly.buffer(2.0).intersects(bpoly):  raise ValueError
                    buildings.append({
                        'building_type': 'unknown',
                        'polygon_pts': list(bpoly.exterior.coords),
                        'name': None,
                    })
                except Exception:
                    pass

                x_pos += b_w + rng.uniform(*gap_range)

    return buildings

def _trees_along_roads(roads, spacing=8.5, site_poly=None):
    out = []
    for road in roads:
        if road.get('hierarchy', 'path') == 'path': continue
        cl = road.get('centerline', []); w = road.get('width_m', 6.0)
        if len(cl) < 2: continue
        line = LineString(cl); h = road.get('hierarchy', 'secondary')
        sw = 3.5 if h == 'main' else 2.5; off = w/2 + sw*0.55
        n = max(1, int(line.length/spacing))
        for i in range(n):
            t   = (i+0.4)/n*line.length; pt = line.interpolate(t)
            t2  = min(t+0.5, line.length-0.01); p2 = line.interpolate(t2)
            dx, dy = p2.x-pt.x, p2.y-pt.y; L = math.hypot(dx,dy)+1e-9
            nxv, nyv = -dy/L, dx/L
            for s in (1, -1):
                tx, ty = pt.x+s*nxv*off, pt.y+s*nyv*off
                if site_poly and site_poly.buffer(3).contains(Point(tx,ty)): continue
                out.append([tx, ty])
    return out

print('Helpers v3 ready — road-aligned urban fabric generator loaded')
