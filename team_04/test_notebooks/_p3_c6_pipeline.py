from collections import Counter
import networkx as nx
from shapely.geometry import LineString, Point, Polygon as SlyPoly
from shapely.ops import unary_union

_SITE_POLY = SlyPoly([(p[0],p[1]) for p in SITE_BDRY])
SITE_CX, SITE_CY = _SITE_POLY.centroid.x, _SITE_POLY.centroid.y

scene_results = {}

for sc in SCENES:
    name   = sc['name']
    roads  = sc['roads']
    ix_raw = sc['intersections']
    jtype  = sc.get('junction')
    print(f'\n{name}')
    print('-' * 65)

    # ── Site model + road analysis
    sm        = build_site_model(SITE_BDRY)
    sm['roads'] = analyze_roads(sm, roads)
    urban     = full_urban_analysis(sm, roads, ix_raw)

    # ── NetworkX graph + centrality
    try:
        G    = build_street_graph(roads)
        C_NX = compute_centrality(G)
        IMP  = compute_urban_importance(sm, G, C_NX)
        nx_ok= G is not None and bool(C_NX)
    except Exception as _e:
        G, C_NX, IMP, nx_ok = None, {}, {'score':0.5,'grade':'B','factors':{}}, False
        print(f'  NetworkX: {_e}')

    # ── Road importance scoring
    bc_vals = C_NX.get('betweenness', {}) if C_NX else {}
    max_bc  = max(bc_vals.values(), default=1) or 1
    for ri, r in enumerate(roads):
        r['_score'] = _road_importance(r, bc_vals, G if nx_ok else None, max_bc)
        r['_id']    = f'R{ri+1:03d}'
    ranked  = sorted(roads, key=lambda r: -r.get('_score', 0))
    primary = ranked[0] if ranked else None
    # Secondary = second best, preferably perpendicular
    secondary = None
    if len(ranked) >= 2:
        for r in ranked[1:]:
            if r.get('hierarchy') in ('main','secondary'):
                secondary = r; break

    # ── Intersection classification + J-IDs
    for ix in ix_raw:
        if ix.get('degree') == 3 and ix.get('type') in ('t_junction','y_junction', None):
            nr = [r for r in roads
                  if len(r.get('centerline',[])) >= 2
                  and LineString(r['centerline']).distance(Point(ix['point'])) < 12]
            ix['type'] = classify_intersection_advanced(3, nr)
    ix_s = sorted(ix_raw, key=lambda ix: (-ix['point'][1], ix['point'][0]))
    for ji, ix in enumerate(ix_s): ix['_jid'] = f'J{ji+1:03d}'

    # ── Road polygon union (for building clipping)
    rp = [_road_poly(r) for r in roads]; rp = [p for p in rp if p and not p.is_empty]
    ru = unary_union(rp) if rp else None

    # ── Realistic road-aligned surrounding buildings
    bldgs = _gen_urban_fabric(roads, _SITE_POLY, ru, seed=42)

    # ── Trees along main / secondary roads
    trees = _trees_along_roads(roads, spacing=8.5, site_poly=_SITE_POLY)

    # ── Dijkstra to primary road
    path_nodes, path_len = [], float('inf')
    if nx_ok and primary and G.number_of_nodes() > 1:
        try:
            snd = min(G.nodes(), key=lambda n: (G.nodes[n]['x']-SITE_CX)**2+(G.nodes[n]['y']-SITE_CY)**2)
            pcl = primary.get('centerline', [])
            if pcl:
                pm  = pcl[len(pcl)//2]
                pnd = min(G.nodes(), key=lambda n: (G.nodes[n]['x']-pm[0])**2+(G.nodes[n]['y']-pm[1])**2)
                if nx.has_path(G, snd, pnd):
                    path_nodes = nx.shortest_path(G, snd, pnd, weight='length')
                    path_len   = nx.shortest_path_length(G, snd, pnd, weight='length')
        except Exception as _pe:
            print(f'  Dijkstra: {_pe}')

    # ── View bounds
    pts = [p for r in roads for p in r.get('centerline',[])] + list(SITE_BDRY)
    xs  = [p[0] for p in pts]; ys = [p[1] for p in pts]
    vcx = (min(xs)+max(xs))/2; vcy = (min(ys)+max(ys))/2
    vrng= max(max(xs)-min(xs), max(ys)-min(ys))/2*1.2+15
    view= (vcx-vrng, vcy-vrng, vcx+vrng, vcy+vrng)

    # ── Building placement proposal
    dom_jtype = jtype or (
        Counter(ix.get('type') for ix in ix_s).most_common(1)[0][0]
        if ix_s else 'crossroads'
    )
    placement = propose_building(
        SITE_BDRY, primary, urban['site_type'],
        IMP.get('score', 0.5),
        secondary_road=secondary,
        junction_type=dom_jtype,
    )

    scene_results[name] = dict(
        roads=roads, bldgs=bldgs, trees=trees, road_u=ru,
        site_model=sm, urban=urban, importance=IMP,
        G=G, nx_ok=nx_ok, bc_vals=bc_vals, max_bc=max_bc,
        ranked=ranked, primary=primary, secondary=secondary,
        ix_s=ix_s, vcx=vcx, vcy=vcy, vrng=vrng, view=view,
        path_nodes=path_nodes, path_len=path_len,
        placement=placement, dom_jtype=dom_jtype,
    )

    hc   = Counter(r.get('hierarchy') for r in roads)
    ixc  = Counter(ix.get('type') for ix in ix_s)
    p    = placement
    print(f'  Roads: main={hc.get("main",0)} sec={hc.get("secondary",0)} path={hc.get("path",0)}')
    print(f'  Junctions: {dict(ixc)}')
    print(f'  Frontages: {len(urban["frontages"])}  '
          f'Gateways: {sum(1 for c in urban["corner_conditions"] if c.get("is_gateway"))}')
    print(f'  Importance: {IMP.get("grade","?")} ({IMP.get("score",0):.2f})')
    print(f'  Proposed: {p["typology"]}  |  main facing: {p["main_facing"]}  '
          f'|  coverage: {p["coverage"]:.0%}  |  FAR est: {p["far_est"]:.1f}')
    print(f'  Surrounding buildings generated: {len(bldgs)}')
