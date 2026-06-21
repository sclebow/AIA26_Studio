import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch
from shapely.geometry import Polygon as SlyPoly, Point
from collections import Counter

# ── Colour palette ──────────────────────────────────────────────────────────
_ROAD_GRAY = {'main': '#5E5E5E', 'secondary': '#909090', 'path': '#C2C2C2'}
IX_STYLE   = {
    'crossroads':       ('X', '#8B1A1A', 13),
    't_junction':       ('T', '#8B3A1A', 12),
    'y_junction':       ('Y', '#8B6A1A', 12),
    'complex_junction': ('*', '#6A0572', 12),
    'dead_end':         ('.', '#5A5A5A',  8),
    'bend':             ('.', '#5A5A5A',  7),
    'roundabout':       ('O', '#1A4A8B', 14),
}

# ── Figure layout ────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(26, 12))
fig.patch.set_facecolor('#F0F0F0')

for ax, sc in zip(axes, SCENES):
    d   = scene_results[sc['name']]
    roads = d['roads']; bldgs = d['bldgs']; trees = d['trees']
    ru    = d['road_u']; sm    = d['site_model']; urban = d['urban']
    ix_s  = d['ix_s'];   primary = d['primary']
    VIEW  = d['view'];   vrng = d['vrng']
    IMP   = d['importance']
    p     = d['placement']            # building placement dict
    _c    = sm.get('corners', []); _s = sm.get('sides', [])
    front = urban['frontages']; corners = urban['corner_conditions']
    access= urban['access']

    ax.set_aspect('equal'); ax.axis('off')
    ax.set_xlim(VIEW[0], VIEW[2]); ax.set_ylim(VIEW[1], VIEW[3])
    ax.set_facecolor('#EBEBEB')

    # ── 1. Sidewalks ──────────────────────────────────────────────────────
    for road in roads:
        _draw_poly(ax, _sidewalk_poly(road), fc='#E0E0E0', ec='none', zorder=2)

    # ── 2. Road surfaces (hierarchy-coded gray) ───────────────────────────
    for h in ('path', 'secondary', 'main'):
        for road in roads:
            if road.get('hierarchy') == h:
                _draw_poly(ax, _road_poly(road), fc=_ROAD_GRAY[h], ec='none', zorder=3)

    # Centre-line dashes on main roads
    for road in roads:
        if road.get('hierarchy') == 'main':
            cl = road.get('centerline', [])
            if len(cl) >= 2:
                ax.plot([p_[0] for p_ in cl], [p_[1] for p_ in cl],
                        color='white', lw=0.65, dashes=(5, 4), alpha=0.45, zorder=4)

    # Width annotation on primary road (single label)
    if primary:
        pcl = primary.get('centerline', [])
        pw  = primary.get('width_m', 20)
        if len(pcl) >= 2:
            mi  = len(pcl)//2
            mx_ = (pcl[mi][0]+pcl[mi-1][0])/2
            my_ = (pcl[mi][1]+pcl[mi-1][1])/2
            ax.text(mx_, my_, f'{pw:.0f} m',
                    ha='center', va='center', fontsize=7.5,
                    color='white', fontweight='bold', zorder=10,
                    bbox=dict(fc='#00000060', ec='none', pad=0.3))

    # ── 3. Surrounding buildings (road-aligned, organic) ─────────────────
    for bldg in bldgs:
        pts_ = bldg.get('polygon_pts', [])
        if len(pts_) < 3: continue
        bp = SlyPoly([(p_[0], p_[1]) for p_ in pts_])
        if not bp.is_valid: bp = bp.buffer(0)
        if ru: bp = bp.difference(ru)
        if bp.is_empty: continue
        # Drop shadow
        _draw_poly(ax, SlyPoly([(q[0]+1.2, q[1]-1.2) for q in pts_]),
                   fc='#00000015', ec='none', zorder=5)
        _draw_poly(ax, bp, fc='#BFBFBF', ec='#ABABAB', lw=0.4, zorder=6)

    # ── 4. Street trees ───────────────────────────────────────────────────
    _tr = max(1.4, 2.0 * 100 / vrng)
    for tp in trees:
        if not (VIEW[0] < tp[0] < VIEW[2] and VIEW[1] < tp[1] < VIEW[3]): continue
        if ru and ru.contains(Point(tp)): continue
        ax.add_patch(plt.Circle((tp[0], tp[1]), _tr,
                                 color='#3E7232', alpha=0.82, zorder=9, lw=0))

    # ── 5. Site boundary ──────────────────────────────────────────────────
    sp = SlyPoly([(pt[0], pt[1]) for pt in SITE_BDRY])
    xs_s, ys_s = sp.exterior.xy
    ax.fill(xs_s, ys_s, color='#FF8C00', alpha=0.06, zorder=10)
    ax.plot(xs_s, ys_s, color='#C84800', lw=2.5, dashes=(8, 3), zorder=11)

    # ── 6. Proposed building footprint ────────────────────────────────────
    bldg_color = '#1E2D4A'   # dark navy

    def _draw_wing(polygon, label, program, cx_, cy_, dir_deg):
        if polygon is None or polygon.is_empty: return
        _draw_poly(ax, polygon, fc=bldg_color, ec='#0A1628', alpha=0.82,
                   lw=0.8, zorder=20)
        # Label on the wing
        ax.text(cx_, cy_, label,
                ha='center', va='center', fontsize=7.5,
                color='white', fontweight='bold', zorder=22,
                bbox=dict(fc='#FFFFFF20', ec='none', pad=0.2))

    _draw_wing(p['wing_A'],    p['A_label'], p['A_program'], *p['A_center'], p['A_dir_deg'])
    _draw_wing(p['wing_B'],    p['B_label'], p['B_program'], *p['B_center'],
               p.get('B_dir_deg', 90))
    if p['connector'] is not None and not p['connector'].is_empty:
        _draw_poly(ax, p['connector'], fc=bldg_color, ec='#0A1628',
                   alpha=0.82, lw=0.8, zorder=20)
        ax.text(p['conn_center'][0], p['conn_center'][1],
                p['conn_label'] or 'CONNECTOR',
                ha='center', va='center', fontsize=6.5,
                color='white', alpha=0.8, zorder=22)

    # Active frontage arrows: arrow from Wing A face toward primary road
    if p.get('A_dir_deg') is not None and p['wing_A'] is not None:
        acx, acy = p['A_center']
        adir = math.radians(p['A_dir_deg'])
        al   = vrng * 0.14
        ax.annotate('',
                    xy  =(acx + al*math.cos(adir), acy + al*math.sin(adir)),
                    xytext=(acx, acy),
                    arrowprops=dict(arrowstyle='->', color='#27AE60',
                                    lw=2.0, mutation_scale=16),
                    zorder=25)
        ax.text(acx + al*math.cos(adir)*1.25, acy + al*math.sin(adir)*1.25,
                'ACTIVE\nFRONTAGE',
                ha='center', va='center', fontsize=6.5, color='#27AE60',
                fontweight='bold', zorder=25)

    # Grid angle line across site
    ga = math.radians(p['grid_angle'])
    gl = vrng * 0.25
    gx1, gy1 = SITE_CX - gl*math.cos(ga), SITE_CY - gl*math.sin(ga)
    gx2, gy2 = SITE_CX + gl*math.cos(ga), SITE_CY + gl*math.sin(ga)
    ax.plot([gx1, gx2], [gy1, gy2], color='#C84800', lw=1.0,
            ls=':', alpha=0.55, zorder=12)
    ax.text(gx2+2, gy2+2, f'GRID {p["grid_angle"]:.0f}\xb0',
            fontsize=6, color='#C84800', alpha=0.7, zorder=12)

    # ── 7. Frontage visibility lines on site edges ────────────────────────
    for f in front:
        sd_ = next((s for s in _s if s.get('edge_index') == f.get('side_index', -1)), None)
        if not sd_: continue
        fi = sd_.get('from_node_index'); ti = sd_.get('to_node_index')
        if fi is None or ti is None or fi >= len(_c) or ti >= len(_c): continue
        p1 = _c[fi]['point']; p2 = _c[ti]['point']
        vis = f.get('visibility_score', 0.5)
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]],
                color=_vis_color(vis), lw=7, solid_capstyle='round',
                alpha=0.92, zorder=13)
        mx_ = (p1[0]+p2[0])/2; my_ = (p1[1]+p2[1])/2
        ax.text(mx_, my_, f'{vis:.0%}',
                ha='center', va='center', fontsize=8, color='white',
                fontweight='bold', zorder=14,
                bbox=dict(fc='#00000055', ec='none', pad=0.12))

    # ── 8. Gateway corners ────────────────────────────────────────────────
    for cc in corners:
        pt_  = cc['point']
        col_ = '#E63946' if cc.get('is_gateway') else '#27AE60'
        ax.add_patch(plt.Circle((pt_[0], pt_[1]),
                                 4+cc['visibility_score']*5,
                                 color=col_, alpha=0.22, zorder=15, lw=0))
        ax.plot(pt_[0], pt_[1], 'o', color=col_, ms=3.5, zorder=15)
        if cc.get('is_gateway'):
            ax.text(pt_[0]+4, pt_[1]+4, '[GW]',
                    fontsize=6.5, color=col_, fontweight='bold', zorder=15)

    # ── 9. Intersection markers ───────────────────────────────────────────
    for ix in ix_s:
        pt_  = ix['point']; t_ = ix.get('type', 't_junction')
        sym_, col_, fs_ = IX_STYLE.get(t_, ('?', '#888', 9))
        jid_ = ix.get('_jid', 'J?')
        rm_  = 4 + min(ix.get('degree', 3), 8)*0.8
        ax.add_patch(plt.Circle((pt_[0], pt_[1]), rm_,
                                 color=col_, alpha=0.18, zorder=16, lw=0))
        ax.plot(pt_[0], pt_[1], 'o', color=col_, ms=rm_*0.55,
                alpha=0.85, zorder=17)
        ax.text(pt_[0], pt_[1], sym_,
                ha='center', va='center', fontsize=max(5, fs_-2),
                color='white', fontweight='bold', zorder=18)
        ax.text(pt_[0], pt_[1]-rm_-2.5, jid_,
                ha='center', va='top', fontsize=5.5, color=col_,
                fontweight='bold', zorder=18,
                bbox=dict(fc='white', ec=col_, lw=0.4, pad=0.12, alpha=0.88))

    # ── 10. Road names on main/secondary ─────────────────────────────────
    _lbl = set()
    for road in d['ranked'][:8]:
        nm_ = road.get('name'); h_ = road.get('hierarchy', 'path')
        if not nm_ or nm_ in _lbl: continue
        cl_ = road.get('centerline', [])
        if len(cl_) < 2: continue
        mi_ = len(cl_)//2
        mx_ = (cl_[mi_][0]+cl_[mi_-1][0])/2; my_ = (cl_[mi_][1]+cl_[mi_-1][1])/2
        if not (VIEW[0] < mx_ < VIEW[2] and VIEW[1] < my_ < VIEW[3]): continue
        ang_ = math.degrees(math.atan2(cl_[-1][1]-cl_[0][1], cl_[-1][0]-cl_[0][0]))
        if ang_ > 90: ang_ -= 180
        if ang_ < -90: ang_ += 180
        ax.text(mx_, my_, nm_, ha='center', va='center',
                fontsize=7 if h_=='main' else 6,
                rotation=ang_, rotation_mode='anchor',
                color='#0A0A0A', fontweight='bold', zorder=19,
                bbox=dict(fc='#FFFFFF88', ec='none', pad=0.3))
        _lbl.add(nm_)

    # ── 11. Scale bar + North arrow ───────────────────────────────────────
    sb_v = max(10, int(vrng/4/10)*10)
    sb_x = VIEW[0]+vrng*0.10; sb_y = VIEW[1]+vrng*0.08
    ax.plot([sb_x, sb_x+sb_v], [sb_y, sb_y], color='#222', lw=2.5,
            solid_capstyle='butt', zorder=25)
    ax.text(sb_x+sb_v/2, sb_y+3, f'{sb_v} m',
            ha='center', fontsize=7.5, color='#222', fontweight='bold')
    na_x = VIEW[2]-vrng*0.10; na_y = VIEW[1]+vrng*0.08; al_ = vrng*0.06
    ax.annotate('', xy=(na_x, na_y+al_), xytext=(na_x, na_y),
                arrowprops=dict(arrowstyle='->', color='#111', lw=2.0), zorder=25)
    ax.text(na_x, na_y+al_+2, 'N', ha='center', fontsize=9,
            color='#111', fontweight='bold')

    # ── 12. Reasoning text panel (lower right inset) ──────────────────────
    reasoning = p['reasoning']
    reason_txt = '\n'.join([f'  {ln}' for ln in reasoning])
    reason_box = (
        f"  PLACEMENT REASONING\n"
        f"  {'─'*32}\n"
        f"  Typology: {p['typology']}\n"
        + reason_txt
    )
    ax.text(VIEW[2] - vrng*0.03, VIEW[1] + vrng*0.03,
            reason_box,
            ha='right', va='bottom',
            fontsize=6.3, family='monospace',
            color='#1A1A2E', zorder=30,
            bbox=dict(fc='white', ec='#CCCCCC', lw=1.0,
                      boxstyle='round,pad=0.6', alpha=0.95))

    # ── 13. Panel title ───────────────────────────────────────────────────
    hc_  = Counter(r.get('hierarchy') for r in roads)
    st_  = SITE_TYPE_LABELS.get(urban['site_type'], urban['site_type'])
    imp_ = IMP.get('score', 0); grade_ = IMP.get('grade', '?')
    gw_  = sum(1 for c in corners if c.get('is_gateway'))
    ax.set_title(
        sc['name'] + '\n' +
        f"Roads: {len(roads)} "
        f"(main={hc_.get('main',0)} sec={hc_.get('secondary',0)} path={hc_.get('path',0)})  "
        f"Junctions: {len(ix_s)}\n"
        f"Frontages: {len(front)}  Gateways: {gw_}  "
        f"Importance: {grade_} ({imp_:.2f})  Site: {st_}",
        fontsize=9, fontweight='bold', color='#1A1A2E', pad=8,
    )

# ── Shared legend ─────────────────────────────────────────────────────────────
leg = [
    mpatches.Patch(color='#5E5E5E', label='Main road (20-30 m)'),
    mpatches.Patch(color='#909090', label='Secondary road (12-15 m)'),
    mpatches.Patch(color='#C2C2C2', label='Path / alley (4-5 m)'),
    mpatches.Patch(color='#BFBFBF', label='Existing buildings (road-aligned)'),
    Line2D([],[],color='#C84800',lw=2,ls='--',label='Site 30x40 m'),
    mpatches.Patch(color='#1E2D4A', label='Proposed building (Wing A / B / Connector)'),
    Line2D([],[],color='#27AE60',lw=2,marker='>',ms=8,label='Active frontage direction'),
    Line2D([],[],color=_vis_color(1.0),lw=5,label='Frontage visibility 100%'),
    Line2D([],[],color=_vis_color(0.0),lw=5,label='Frontage visibility 0%'),
    mpatches.Patch(color='#E63946',alpha=0.6,label='[GW] Gateway corner'),
    Line2D([],[],marker='o',color='#8B1A1A',ls='none',ms=8,label='Crossroads (X)'),
    Line2D([],[],marker='o',color='#8B3A1A',ls='none',ms=8,label='T-junction (T)'),
    Line2D([],[],marker='o',color='#8B6A1A',ls='none',ms=8,label='Y-junction (Y)'),
    Line2D([],[],marker='o',color='#6A0572',ls='none',ms=8,label='Complex junction (*)'),
]
fig.legend(handles=leg, loc='lower center', ncol=7, fontsize=8,
           framealpha=0.97, edgecolor='#CCC',
           title='Building Placement Agent — Three Urban Conditions',
           title_fontsize=9.5, bbox_to_anchor=(0.5, -0.07))

fig.suptitle(
    'Urban Site Intelligence — Building Placement Reasoning\n'
    'Same 30 m x 40 m Parcel  |  '
    'H-Building (crossroads)  /  Wide Slab (T-junction)  /  L-Building (Y-junction)',
    fontsize=13.5, fontweight='bold', color='#1A1A2E', y=1.01,
)
plt.tight_layout(rect=[0, 0.07, 1, 1])
plt.savefig('p3_placement.png', dpi=140, bbox_inches='tight')
plt.show()
print('Figure saved: p3_placement.png')
