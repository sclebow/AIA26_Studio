"""
Add multi-scale complex-site cells to test_urban_context_P2.ipynb.

New site : Times Square, Manhattan (Broadway diagonal through Manhattan grid)
           Roads range from 5m service alleys → 20m cross streets → 30m arterials
Site parcel : 30m × 40m custom boundary
Radii tested : 100m  |  200m  |  350m
"""
import json

NB_PATH = (
    r'c:\Users\tuemi\Downloads\Glabtools\IAAC Repo'
    r'\bimsc26-datamgmt-session03\AIA26_Studio'
    r'\team_04\test_notebooks\test_urban_context_P2.ipynb'
)

with open(NB_PATH, encoding='utf-8') as f:
    nb = json.load(f)


def code_cell(src: str):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": src,
    }


def md_cell(src: str):
    return {"cell_type": "markdown", "metadata": {}, "source": src}


# ── Cell A: Markdown divider ─────────────────────────────────────────────────
CELL_A_MD = """\
---
## Multi-Scale Urban Analysis — Times Square, Manhattan
**New complex site · Roads 5 m → 20 m → 30 m wide · Site parcel 30 m × 40 m**

Broadway cuts diagonally through the Manhattan grid, producing star/Y junctions
that the Eixample grid never generates. Three context radii are compared
side-by-side to show how the agent's analysis changes with scale.

| Panel | Radius | What it reveals |
|-------|--------|-----------------|
| **A** | 100 m  | Immediate — individual buildings, frontage, access |
| **B** | 200 m  | Neighbourhood — junction typology, hierarchy |
| **C** | 350 m  | District — full network, centrality, primary-road rank |
"""

# ── Cell B: Fetch + analyse at 3 radii ───────────────────────────────────────
CELL_B_CODE = """\
# ── Complex test site: Times Square, Manhattan ────────────────────────────────
# Broadway (≈30 m wide) cuts diagonally through the Manhattan grid (20 m streets)
# while service alleys and through-block connections add 5 m-class paths.
# The diagonal creates complex star/Y junctions very different from Eixample.

COMPLEX_NAME = 'Times Square, Manhattan, NYC'
COMPLEX_LAT  =  40.7580
COMPLEX_LON  = -73.9855

# Custom 30 m-wide, 40 m-deep site boundary centred at local origin.
# Use this instead of the auto-inferred boundary so the parcel stays fixed
# across all three radius tests.
SITE_W, SITE_D = 30, 40          # metres
CUSTOM_BDRY = [
    [-SITE_W/2, -SITE_D/2], [ SITE_W/2, -SITE_D/2],
    [ SITE_W/2,  SITE_D/2], [-SITE_W/2,  SITE_D/2],
    [-SITE_W/2, -SITE_D/2],
]

# Three context radii:
#   100 m  — roads ≈5 m (alleys) and ≈20 m (cross-streets) visible
#   200 m  — adds ≈30 m arterials (7th Ave, Broadway)
#   350 m  — full district, centrality meaningful
TEST_RADII   = [100, 200, 350]
RADIUS_LABEL = {100: 'A  100 m — Immediate',
                200: 'B  200 m — Neighbourhood',
                350: 'C  350 m — District'}

import warnings
scale_data = {}

for radius in TEST_RADII:
    print(f'\\nFetching {COMPLEX_NAME}  r={radius} m …')
    with warnings.catch_warnings(record=True) as _ww:
        warnings.simplefilter('always')
        _ctx = fetch_context_or_fallback(COMPLEX_LAT, COMPLEX_LON,
                                         radius_m=radius, fallback_index=0)
    if _ww:
        print(f'  ↳ offline fallback: {_ww[-1].message}')

    _roads  = _ctx['roads']
    _bldgs  = _ctx.get('buildings', [])
    _greens = _ctx.get('green_areas', [])
    _trees  = _ctx.get('trees', [])
    _ix_osm = _ctx.get('intersections', [])

    # Analysis pipeline — fixed 30 m site boundary
    _sm = build_site_model(CUSTOM_BDRY)
    _sm['roads'] = analyze_roads(_sm, _roads)
    _urban = full_urban_analysis(_sm, _roads, _ix_osm or None)

    try:
        _G  = build_street_graph(_roads)
        _C  = compute_centrality(_G)
        _I  = compute_urban_importance(_sm, _G, _C)
        _nxok = _G is not None and bool(_C)
    except Exception as _e:
        _G, _C, _I, _nxok = None, {}, {'score': 0.5, 'grade': 'B', 'factors': {}}, False
        print(f'  NetworkX unavailable: {_e}')

    # Road importance scoring
    _bc  = _C.get('betweenness', {}) if _C else {}
    _mbc = max(_bc.values(), default=1) or 1
    for _ri, _r in enumerate(_roads):
        _r['_score'] = _road_importance(_r, _bc, _G if _nxok else None, _mbc)
        _r['_id']    = f'R{_ri+1:03d}'
    _ranked  = sorted(_roads, key=lambda r: -r.get('_score', 0))
    _primary = _ranked[0] if _ranked else None

    # Intersection classification + J-IDs
    _ix_all = _ix_osm or detect_intersections_from_roads(_roads)
    for _ix in _ix_all:
        if _ix.get('degree') == 3 and _ix.get('type') in ('t_junction', 'y_junction', None):
            _nr = [r for r in _roads
                   if len(r.get('centerline', [])) >= 2
                   and LineString(r['centerline']).distance(Point(_ix['point'])) < 8]
            _ix['type'] = classify_intersection_advanced(3, _nr)
    _ix_s = sorted(_ix_all, key=lambda ix: (-ix['point'][1], ix['point'][0]))
    for _ji, _ix in enumerate(_ix_s): _ix['_jid'] = f'J{_ji+1:03d}'

    # View bounds from road geometry (not the tiny site)
    _pts = [p for r in _roads for p in r.get('centerline', [])]
    if _pts:
        _xs = [p[0] for p in _pts]; _ys = [p[1] for p in _pts]
        _vcx = (min(_xs)+max(_xs))/2; _vcy = (min(_ys)+max(_ys))/2
        _vrng = max(max(_xs)-min(_xs), max(_ys)-min(_ys))/2*1.25 + 20
    else:
        _vcx, _vcy, _vrng = 0, 0, radius
    _view = (_vcx-_vrng, _vcy-_vrng, _vcx+_vrng, _vcy+_vrng)

    # Road polygon union (for tree clipping + building subtraction)
    _rp = [_road_poly(r) for r in _roads]
    _rp = [p for p in _rp if p and not p.is_empty]
    _ru = unary_union(_rp) if _rp else None
    _tp = _trees if _trees else _trees_along_roads(_roads, spacing=8.0)

    scale_data[radius] = dict(
        roads=_roads, bldgs=_bldgs, greens=_greens, trees=_tp, road_u=_ru,
        site_model=_sm, urban=_urban, importance=_I,
        G=_G, nx_ok=_nxok, bc_vals=_bc, max_bc=_mbc,
        ranked=_ranked, primary=_primary,
        ix_s=_ix_s, source=_ctx['source'],
        vcx=_vcx, vcy=_vcy, vrng=_vrng, view=_view,
    )

    _hc  = Counter(r.get('hierarchy', '?') for r in _roads)
    _ixc = Counter(ix.get('type', '?') for ix in _ix_s)
    _avg_w = {h: (sum(r.get('width_m', 0) for r in _roads if r.get('hierarchy') == h) /
                  max(_hc.get(h, 1), 1))
              for h in ('main', 'secondary', 'path')}
    print(f'  Roads: main={_hc.get("main",0)} (avg {_avg_w["main"]:.0f} m)  '
          f'sec={_hc.get("secondary",0)} (avg {_avg_w["secondary"]:.0f} m)  '
          f'path={_hc.get("path",0)} (avg {_avg_w["path"]:.0f} m)')
    print(f'  Intersections: {len(_ix_s)}  → {dict(_ixc)}')
    print(f'  Frontages: {len(_urban["frontages"])}  '
          f'Importance: {_I.get("grade","?")} ({_I.get("score",0):.2f})  '
          f'Source: {_ctx["source"].upper()}')
"""

# ── Cell C: Multi-scale comparison figure ────────────────────────────────────
CELL_C_CODE = """\
# ── Figure 6 — Multi-Scale Architectural Basemap (3 panels) ─────────────────
# Each panel uses the same 30 m × 40 m site boundary (orange dashed),
# but a different OSM fetch radius so the road network grows with context.
# Roads are coloured by hierarchy: dark gray (main / ≈30 m wide),
# medium gray (secondary / ≈20 m), light gray (path / ≈5 m).

_ROAD_GRAY = {'main': '#6E6E6E', 'secondary': '#A0A0A0', 'path': '#C8C8C8'}

fig, axes = plt.subplots(1, 3, figsize=(24, 10))
fig.patch.set_facecolor('#F5F5F5')

for ax, radius in zip(axes, TEST_RADII):
    d   = scale_data[radius]
    roads = d['roads']; bldgs = d['bldgs']; greens = d['greens']
    trees = d['trees']; ru    = d['road_u']
    sm    = d['site_model']; urban = d['urban']
    ix_s  = d['ix_s'];  primary = d['primary']
    VIEW  = d['view'];  vrng = d['vrng']

    _c = sm.get('corners', [])
    _s = sm.get('sides',   [])
    frontages = urban['frontages']
    corners   = urban['corner_conditions']
    access    = urban['access']
    imp       = d['importance']

    ax.set_aspect('equal'); ax.axis('off')
    ax.set_xlim(VIEW[0], VIEW[2]); ax.set_ylim(VIEW[1], VIEW[3])
    ax.set_facecolor('#EEEEEE')

    # Green spaces
    for ga in greens:
        pts = ga.get('polygon_pts', [])
        if len(pts) >= 3:
            _draw_poly(ax, SlyPoly([(p[0],p[1]) for p in pts]),
                       fc='#BED4A8', ec='none', alpha=0.7, zorder=1)

    # Sidewalks
    for road in roads:
        _draw_poly(ax, _sidewalk_poly(road), fc='#E5E5E5', ec='none', zorder=2)

    # Road surfaces — width-coded grays
    for h in ('path', 'secondary', 'main'):
        for road in roads:
            if road.get('hierarchy') == h:
                _draw_poly(ax, _road_poly(road), fc=_ROAD_GRAY[h], ec='none', zorder=3)

    # White dashes on main roads
    for road in roads:
        if road.get('hierarchy') == 'main':
            cl = road.get('centerline', [])
            if len(cl) >= 2:
                ax.plot([p[0] for p in cl], [p[1] for p in cl],
                        color='white', lw=0.6, dashes=(5, 4), alpha=0.5, zorder=4)

    # Primary road gold highlight
    if primary:
        pcl = primary.get('centerline', [])
        if len(pcl) >= 2:
            ax.plot([p[0] for p in pcl], [p[1] for p in pcl],
                    color='#FFD700', lw=3.5, alpha=0.5, zorder=5, ls='--')

    # Buildings — uniform gray
    for bldg in bldgs:
        pts = bldg.get('polygon_pts', [])
        if len(pts) < 3: continue
        bp = SlyPoly([(p[0],p[1]) for p in pts])
        if not bp.is_valid: bp = bp.buffer(0)
        if ru: bp = bp.difference(ru)
        if bp.is_empty: continue
        _draw_poly(ax, SlyPoly([(p[0]+1.5,p[1]-1.5) for p in pts]),
                   fc='#00000010', ec='none', zorder=6)
        _draw_poly(ax, bp, fc='#C6C6C6', ec='#B2B2B2', lw=0.4, zorder=7)

    # Street trees (only within view, scaled to radius)
    _tree_r = max(1.2, 2.4 * 100 / radius)
    for tp in trees:
        if not (VIEW[0] < tp[0] < VIEW[2] and VIEW[1] < tp[1] < VIEW[3]): continue
        if ru and ru.contains(Point(tp)): continue
        ax.add_patch(plt.Circle((tp[0], tp[1]), _tree_r,
                                 color='#3D7030', alpha=0.8, zorder=9, lw=0))

    # Site boundary — 30 m × 40 m fixed parcel
    sp = SlyPoly([(p[0],p[1]) for p in CUSTOM_BDRY])
    xs_s, ys_s = sp.exterior.xy
    ax.fill(xs_s, ys_s, color='#FF8C00', alpha=0.12, zorder=10)
    ax.plot(xs_s, ys_s, color='#C84800', lw=2.5, dashes=(8, 3), zorder=11)
    ax.text(0, 0, f'SITE\\n{SITE_W}×{SITE_D}m',
            ha='center', va='center', fontsize=7,
            color='#C84800', fontweight='bold', alpha=0.75, zorder=11)

    # Frontage visibility heat lines
    for f in frontages:
        sd = next((s for s in _s if s.get('edge_index') == f.get('side_index', -1)), None)
        if not sd: continue
        fi = sd.get('from_node_index'); ti = sd.get('to_node_index')
        if fi is None or ti is None or fi >= len(_c) or ti >= len(_c): continue
        p1 = _c[fi]['point']; p2 = _c[ti]['point']
        vis = f.get('visibility_score', 0.5)
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]],
                color=_vis_color(vis), lw=7, solid_capstyle='round', alpha=0.92, zorder=12)
        mx_ = (p1[0]+p2[0])/2; my_ = (p1[1]+p2[1])/2
        ax.text(mx_, my_, f'{vis:.0%}',
                ha='center', va='center', fontsize=7.5,
                color='white', fontweight='bold', zorder=13,
                bbox=dict(fc='#00000055', ec='none', pad=0.12))

    # Access points
    for cat, sym, col in [('vehicle', 'V', '#1A3A50'), ('pedestrian', 'P', '#1A6050')]:
        for ap in access.get(cat, []):
            pt = ap.get('point', [])
            if len(pt) >= 2:
                ax.text(pt[0], pt[1], sym,
                        ha='center', va='center', fontsize=9,
                        color=col, fontweight='bold', zorder=14,
                        bbox=dict(fc='white', ec=col, lw=1.0,
                                  boxstyle='round,pad=0.2', alpha=0.92))

    # Gateway corners
    for cc in corners:
        pt = cc['point']
        col = '#E63946' if cc.get('is_gateway') else '#27AE60'
        ax.add_patch(plt.Circle((pt[0], pt[1]),
                                 4 + cc['visibility_score'] * 5,
                                 color=col, alpha=0.22, zorder=15, lw=0))
        ax.plot(pt[0], pt[1], 'o', color=col, ms=3.5, zorder=15)
        if cc.get('is_gateway'):
            ax.text(pt[0]+4, pt[1]+4, '[GW]',
                    fontsize=6.5, color=col, fontweight='bold', zorder=15)

    # Intersection markers + J-IDs (scale dot size to radius)
    _rm_scale = max(0.6, 100 / radius)
    for ix in ix_s:
        pt = ix['point']; t = ix.get('type', 't_junction')
        sym, col, fs = IX_STYLE.get(t, ('?', '#888', 9))
        jid = ix.get('_jid', 'J?')
        rm  = (4 + min(ix.get('degree', 3), 8) * 0.75) * _rm_scale
        ax.add_patch(plt.Circle((pt[0], pt[1]), rm, color=col, alpha=0.18, zorder=16, lw=0))
        ax.plot(pt[0], pt[1], 'o', color=col, ms=rm*0.55, alpha=0.85, zorder=17)
        ax.text(pt[0], pt[1], sym,
                ha='center', va='center', fontsize=max(5, fs-2),
                color='white', fontweight='bold', zorder=18)
        if radius <= 200:   # only show J-IDs at tighter scales
            ax.text(pt[0], pt[1]-rm-2, jid,
                    ha='center', va='top', fontsize=5,
                    color=col, fontweight='bold', zorder=18,
                    bbox=dict(fc='white', ec=col, lw=0.4, pad=0.12, alpha=0.88))

    # Street names on main roads (suppress at widest scale to avoid clutter)
    if radius <= 200:
        _lbl = set()
        for road in roads:
            nm = road.get('name'); h = road.get('hierarchy', 'path')
            if not nm or nm in _lbl or h == 'path': continue
            cl = road.get('centerline', [])
            if len(cl) < 2: continue
            mi = len(cl)//2
            mx_ = (cl[mi][0]+cl[mi-1][0])/2; my_ = (cl[mi][1]+cl[mi-1][1])/2
            if not (VIEW[0] < mx_ < VIEW[2] and VIEW[1] < my_ < VIEW[3]): continue
            ang = math.degrees(math.atan2(cl[-1][1]-cl[0][1], cl[-1][0]-cl[0][0]))
            if ang > 90: ang -= 180
            if ang < -90: ang += 180
            ax.text(mx_, my_, nm,
                    ha='center', va='center',
                    fontsize=6.5 if h == 'main' else 5.5,
                    rotation=ang, rotation_mode='anchor',
                    color='#0A0A0A', fontweight='bold', zorder=19,
                    bbox=dict(fc='#FFFFFF88', ec='none', pad=0.3))
            _lbl.add(nm)

    # Scale bar
    sb_v = max(10, int(vrng/4/10)*10)
    sb_x = VIEW[0]+vrng*0.10; sb_y = VIEW[1]+vrng*0.08
    ax.plot([sb_x, sb_x+sb_v], [sb_y, sb_y], color='#222', lw=2.5,
            solid_capstyle='butt', zorder=20)
    ax.text(sb_x+sb_v/2, sb_y+2.5, f'{sb_v} m',
            ha='center', fontsize=7, color='#222', fontweight='bold')

    # North arrow
    na_x = VIEW[2]-vrng*0.10; na_y = VIEW[1]+vrng*0.08; al = vrng*0.06
    ax.annotate('', xy=(na_x, na_y+al), xytext=(na_x, na_y),
                arrowprops=dict(arrowstyle='->', color='#111', lw=1.8), zorder=20)
    ax.text(na_x, na_y+al+2, 'N', ha='center', fontsize=8, color='#111', fontweight='bold')

    # Panel title
    hc   = Counter(r.get('hierarchy', '?') for r in roads)
    ixc  = Counter(ix.get('type', '?') for ix in ix_s)
    aw   = {h: (sum(r.get('width_m', 0) for r in roads if r.get('hierarchy') == h) /
                max(hc.get(h, 1), 1)) for h in ('main', 'secondary', 'path')}
    st   = SITE_TYPE_LABELS.get(urban['site_type'], urban['site_type'])
    ax.set_title(
        f"{RADIUS_LABEL[radius]}\n"
        f"Roads: {len(roads)}  "
        f"main≈{aw['main']:.0f} m  sec≈{aw['secondary']:.0f} m  path≈{aw['path']:.0f} m\n"
        f"Junctions: {len(ix_s)}  Frontages: {len(frontages)}  "
        f"Importance: {imp.get('grade','?')} ({imp.get('score',0):.2f})",
        fontsize=9, fontweight='bold', color='#1A1A2E', pad=7,
    )

# Shared legend
leg = [
    mpatches.Patch(color='#6E6E6E', label='Main road (≈30 m)'),
    mpatches.Patch(color='#A0A0A0', label='Secondary road (≈20 m)'),
    mpatches.Patch(color='#C8C8C8', label='Path / alley (≈5 m)'),
    mpatches.Patch(color='#C6C6C6', label='Building'),
    mpatches.Patch(color='#BED4A8', label='Green space'),
    Line2D([],[],color='#C84800',lw=2,ls='--',label=f'Site {SITE_W}×{SITE_D} m'),
    Line2D([],[],color=_vis_color(1.0),lw=5,label='Frontage 100% visibility'),
    Line2D([],[],color=_vis_color(0.0),lw=5,label='Frontage 0% visibility'),
    mpatches.Patch(color='#E63946',alpha=0.6,label='[GW] Gateway corner'),
    Line2D([],[],color='#FFD700',lw=3,ls='--',label='Primary road'),
    Line2D([],[],marker='o',color='#8B1A1A',ls='none',ms=8,label='Crossroads (X)'),
    Line2D([],[],marker='o',color='#8B6A1A',ls='none',ms=8,label='Y-Junction (Y)'),
    Line2D([],[],marker='o',color='#8B3A1A',ls='none',ms=8,label='T-Junction (T)'),
    Line2D([],[],marker='o',color='#6A0572',ls='none',ms=8,label='Complex junction (*)'),
]
fig.legend(handles=leg, loc='lower center', ncol=7, fontsize=8,
           framealpha=0.96, edgecolor='#CCC',
           title=f'LEGEND — {COMPLEX_NAME}', title_fontsize=9,
           bbox_to_anchor=(0.5, -0.08))

fig.suptitle(
    f"Multi-Scale Urban Analysis: {COMPLEX_NAME}\n"
    f"Site parcel: {SITE_W} m × {SITE_D} m  |  "
    f"Radii: {', '.join(str(r)+' m' for r in TEST_RADII)}",
    fontsize=13, fontweight='bold', color='#1A1A2E', y=1.02,
)
plt.tight_layout(rect=[0, 0.05, 1, 1])
plt.savefig('p2_multiscale.png', dpi=130, bbox_inches='tight')
plt.show()
print('Figure 6 saved: p2_multiscale.png')
"""

# ── Cell D: Cross-scale metrics comparison ────────────────────────────────────
CELL_D_CODE = """\
# ── Cross-scale metrics comparison table ─────────────────────────────────────
print('='*78)
print(f'  MULTI-SCALE METRICS — {COMPLEX_NAME}')
print(f'  Site: {SITE_W} m wide × {SITE_D} m deep')
print('='*78)
_col = [f'{r} m' for r in TEST_RADII]
print(f'  {"Metric":<34} {_col[0]:>12} {_col[1]:>12} {_col[2]:>12}')
print(f'  {"-"*72}')

def _v(r, fn):
    try:    return str(fn(scale_data[r]))
    except: return '—'

rows = [
    ('Data source',           lambda d: d['source'].upper()),
    ('Total roads',           lambda d: len(d['roads'])),
    ('  main roads (≈30 m)',  lambda d: Counter(r.get('hierarchy') for r in d['roads']).get('main',0)),
    ('  secondary  (≈20 m)',  lambda d: Counter(r.get('hierarchy') for r in d['roads']).get('secondary',0)),
    ('  paths/alleys (≈5 m)', lambda d: Counter(r.get('hierarchy') for r in d['roads']).get('path',0)),
    ('Avg main-road width m', lambda d: f"{sum(r.get('width_m',0) for r in d['roads'] if r.get('hierarchy')=='main') / max(Counter(r.get('hierarchy') for r in d['roads']).get('main',1),1):.1f}"),
    ('Total intersections',   lambda d: len(d['ix_s'])),
    ('  crossroads (X)',      lambda d: Counter(ix.get('type') for ix in d['ix_s']).get('crossroads',0)),
    ('  T-junction (T)',      lambda d: Counter(ix.get('type') for ix in d['ix_s']).get('t_junction',0)),
    ('  Y-junction (Y)',      lambda d: Counter(ix.get('type') for ix in d['ix_s']).get('y_junction',0)),
    ('  complex (*)',         lambda d: Counter(ix.get('type') for ix in d['ix_s']).get('complex_junction',0)),
    ('Site frontages',        lambda d: len(d['urban']['frontages'])),
    ('Gateway corners',       lambda d: sum(1 for c in d['urban']['corner_conditions'] if c.get('is_gateway'))),
    ('Urban importance',      lambda d: f"{d['importance'].get('grade','?')} ({d['importance'].get('score',0):.2f})"),
    ('Site type detected',    lambda d: SITE_TYPE_LABELS.get(d['urban']['site_type'], d['urban']['site_type'])),
    ('Primary road',          lambda d: (d['primary'].get('name') or '[unnamed]')[:22] if d['primary'] else '—'),
    ('Primary road score',    lambda d: f"{d['primary'].get('_score',0):.4f}" if d['primary'] else '—'),
]
for label, fn in rows:
    vals = [_v(r, fn) for r in TEST_RADII]
    print(f'  {label:<34} {vals[0]:>12} {vals[1]:>12} {vals[2]:>12}')

print(f'  {"-"*72}')
print()

# Per-radius reasoning chain summary
print('REASONING CHAIN COMPARISON:')
for radius in TEST_RADII:
    d   = scale_data[radius]
    u   = d['urban']
    imp = d['importance']
    st  = SITE_TYPE_LABELS.get(u['site_type'], u['site_type'])
    ixc = Counter(ix.get('type','?') for ix in d['ix_s'])
    dom = max(ixc, key=ixc.get) if ixc else '—'
    resp = u['urban_response'].get('building_response') or u['urban_response'].get('massing_strategy','')
    print(f'\\n  [{RADIUS_LABEL[radius]}]')
    print(f'  Site type   : {st}')
    print(f'  Dominant IX : {dom.replace("_"," ").title()} ({ixc.get(dom,0)} instances)')
    print(f'  Importance  : {imp.get("grade","?")} ({imp.get("score",0):.2f})  '
          f'→ {"landmark" if imp.get("score",0)>0.6 else "moderate" if imp.get("score",0)>0.3 else "low"} exposure')
    if IX_RESPONSE.get(dom):
        print(f'  Design resp : {IX_RESPONSE[dom][:110]}')
    if resp:
        print(f'  Massing     : {resp[:110]}')

print()
print('='*78)
"""

# ── Append all four cells ─────────────────────────────────────────────────────
nb['cells'].append(md_cell(CELL_A_MD))
nb['cells'].append(code_cell(CELL_B_CODE))
nb['cells'].append(code_cell(CELL_C_CODE))
nb['cells'].append(code_cell(CELL_D_CODE))

with open(NB_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print(f'Done.  Notebook now has {len(nb["cells"])} cells.')
print('New cells: 13=markdown header, 14=fetch+analyse, 15=Figure6, 16=metrics table')
