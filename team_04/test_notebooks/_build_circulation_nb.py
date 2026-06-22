"""Generator for test_circulation_fire.ipynb (Phase 5+ — functional access).

Run once to (re)emit the notebook JSON. Kept in the repo so the notebook is
reproducible and reviewable as code. Not a test; not imported by anything.

To re-embed the rendered figures after editing:

    python team_04/test_notebooks/_build_circulation_nb.py
    # then execute in VS Code, or re-run the nbclient one-liner used in the PR.

This notebook exercises the *functional* access reasoning the rebuild added —
how people arrive, which door they pick, how cars reach parking and people walk
from it, and how everyone gets out in a fire — on the hard cases a simple
rectangle never shows:

  - an irregular concave site with several real wing-typology buildings;
  - typed building entrances (public / service / residential / courtyard) WITH
    the reason each sits where it does;
  - separate pedestrian and vehicular networks (pedestrians avoid parking);
  - parking integrated as a journey (drop-off, accessible walk, sequence);
  - emergency egress with multiple independent directions, courtyard-avoiding;
  - a full validation audit + identified conflicts and resolutions;
  - an egress gallery across U / H / X / Y / E / courtyard typologies.
"""
import json
from pathlib import Path

md = lambda s: {"cell_type": "markdown", "metadata": {}, "source": s.splitlines(keepends=True)}
code = lambda s: {"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": s.strip("\n").splitlines(keepends=True)}

cells = []

cells.append(md("""# Phase 5+ — Functional Circulation, Access & Fire Safety

The first version of this tool only *placed* paths. This rebuild makes the agent
reason about how a building is actually **used**: how people arrive from the
street, which entrance they pick, how cars reach parking and people walk up from
it, and how everyone gets **out** in a fire — on irregular sites and complex
building forms, not toy rectangles.

Everything here is driven by `agent/tools/circulation.py`. The single entry point
is **`evaluate_site_circulation(site_model, buildings, parking)`**, which returns
one report with the sections a reviewer asks for:

| Section | Question it answers |
|---|---|
| `entrances` | Where is each public / service / residential / courtyard door, and **why**? |
| `site_access` | How do pedestrians vs vehicles arrive at each frontage? |
| `vehicular_circulation` | Drivable corridors (obstacle-aware, bend around buildings). |
| `pedestrian_circulation` | Walkways that **avoid crossing parking**. |
| `parking_integration` | Drop-off, accessible walk, street→park→door sequence. |
| `fire_safety_egress` | Multi-direction emergency exits + fire-appliance reach. |
| `conflicts` | Pedestrian/vehicle crossings + resolutions. |
| `audit` | The pre-finalisation validation checklist. |

**Scenes:** (A) an irregular site with mixed wing typologies — the full report,
layer by layer; (B) an egress gallery across U/H/X/Y/E/courtyard forms;
(C) the enclosed-courtyard case strict fire access catches."""))

# --------------------------------------------------------------------------- setup
cells.append(code("""
from __future__ import annotations
import sys
from pathlib import Path

workspace_root = Path.cwd().resolve()
candidate_roots = (
    workspace_root, workspace_root.parent,
    workspace_root / 'team_04', workspace_root.parent / 'team_04',
)
TEAM_ROOT = next((p for p in candidate_roots if (p / 'agent').exists()), None)
if TEAM_ROOT is None:
    raise FileNotFoundError('Run from workspace root, team_04/, or team_04/test_notebooks/')
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))
print('TEAM_ROOT:', TEAM_ROOT)
"""))

cells.append(code("""
import math
import plotly.graph_objects as go
import plotly.io as pio

# Embed figures so they render inline in VS Code / Jupyter (and survive a
# pre-executed notebook). 'plotly_mimetype' is what VS Code renders natively.
pio.renderers.default = 'plotly_mimetype+notebook_connected'

from agent.tools.building_shape_graph import build_shape_model, apply_shape_transform
from agent.tools.parking import compute_building_demand, allocate_parking_zones
from agent.tools.circulation import (
    DEFAULT_PATH_WIDTH_M, MIN_PATH_WIDTH_M, MAX_FIRE_DISTANCE_M,
    evaluate_site_circulation,
    propose_site_entries, route_internal_circulation, building_entrance_orientation,
    route_pedestrian_network, analyze_site_arrival, analyze_parking_access,
    analyze_egress, detect_circulation_conflicts, audit_circulation,
    segment_facades, generate_emergency_exits, check_fire_access,
)
print('circulation tools imported OK')

def shp_to_bnd(poly):
    return [[round(float(x), 3), round(float(y), 3), 0.0] for x, y in poly.exterior.coords]

def winged(building_type, area, depth, ratio, xy, rot=0.0):
    m = build_shape_model(area=area, building_type=building_type,
                          building_depth=depth, shape_ratio=ratio)
    m = apply_shape_transform(m, translation_xy=xy, rotation_degrees=rot)
    return shp_to_bnd(m.polygon)
"""))

# --------------------------------------------------------------------------- helpers
cells.append(md("""## Plot helpers

Colour key — entrances by role: **public** red · **service** blue ·
**residential** green · **courtyard** purple. **Emergency exits** are orange
arrows. Vehicular corridors are grey bands; **pedestrian** routes are dashed
green. Site entries are big triangles; parking is light blue with cyan drop-off
diamonds; conflicts are black ✕."""))

cells.append(code("""
ROLE_COLORS = {'public': '#dc2626', 'service': '#2563eb',
               'residential': '#16a34a', 'courtyard': '#9333ea'}
EXIT_COLOR = '#ea580c'

def _xy(pts):
    xs = [p[0] for p in pts] + [pts[0][0]]
    ys = [p[1] for p in pts] + [pts[0][1]]
    return xs, ys

def new_fig(title, site_boundary, h=640):
    fig = go.Figure()
    xs, ys = _xy(site_boundary)
    fig.add_trace(go.Scatter(x=xs, y=ys, name='Site boundary', mode='lines',
                             line=dict(color='#1d4ed8', width=3), hoverinfo='skip'))
    fig.update_layout(title=title, height=h,
                      yaxis=dict(scaleanchor='x', scaleratio=1, visible=False),
                      xaxis=dict(visible=False), margin=dict(l=0, r=0, t=44, b=0),
                      plot_bgcolor='#f0f4ff', paper_bgcolor='#f0f4ff',
                      legend=dict(x=1.02, y=1, bgcolor='white', bordercolor='#ccc', borderwidth=1))
    return fig

def draw_buildings(fig, buildings, fire=None):
    fire_by = {b['building_id']: b for b in (fire or {}).get('buildings', [])}
    palette = ['rgba(15,118,110,0.35)', 'rgba(124,58,237,0.30)',
               'rgba(180,83,9,0.30)', 'rgba(8,145,178,0.30)']
    for i, b in enumerate(buildings):
        xs, ys = _xy(b['boundary'])
        passed = fire_by.get(b['building_id'], {}).get('pass')
        if passed is True:
            fill, line = 'rgba(34,197,94,0.35)', '#15803d'
        elif passed is False:
            fill, line = 'rgba(239,68,68,0.35)', '#b91c1c'
        else:
            fill, line = palette[i % len(palette)], palette[i % len(palette)].replace('0.35', '1').replace('0.30', '1')
        fig.add_trace(go.Scatter(x=xs, y=ys, name=b.get('label', b['building_id']),
                                 mode='lines', fill='toself', fillcolor=fill,
                                 line=dict(color=line, width=2), hoverinfo='skip'))
        for hole in b.get('holes', []) or []:
            hxs, hys = _xy(hole)
            fig.add_trace(go.Scatter(x=hxs, y=hys, mode='lines', fill='toself',
                                     fillcolor='#f0f4ff', line=dict(color=line, width=1, dash='dot'),
                                     showlegend=False, hoverinfo='skip'))
        cx = sum(p[0] for p in b['boundary']) / len(b['boundary'])
        cy = sum(p[1] for p in b['boundary']) / len(b['boundary'])
        fig.add_annotation(x=cx, y=cy, text=b.get('label', b['building_id']),
                           showarrow=False, font=dict(size=11, color='#111'))

def draw_vehicular(fig, veh):
    first = True
    for p in veh.get('paths', []):
        if p.get('buffered_boundary'):
            xs, ys = _xy(p['buffered_boundary'])
            fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', fill='toself',
                                     fillcolor='rgba(100,116,139,0.30)',
                                     line=dict(color='rgba(0,0,0,0)', width=0),
                                     showlegend=False, hoverinfo='skip'))
        px = [pt[0] for pt in p['polyline']]; py = [pt[1] for pt in p['polyline']]
        fig.add_trace(go.Scatter(x=px, y=py, name='vehicular corridor', mode='lines',
                                 line=dict(color='#334155', width=2),
                                 legendgroup='veh', showlegend=first, hoverinfo='skip'))
        first = False

def draw_pedestrian(fig, ped):
    first = True
    for p in ped.get('paths', []):
        px = [pt[0] for pt in p['polyline']]; py = [pt[1] for pt in p['polyline']]
        fig.add_trace(go.Scatter(x=px, y=py, name='pedestrian route', mode='lines',
                                 line=dict(color='#16a34a', width=2, dash='dash'),
                                 legendgroup='ped', showlegend=first, hoverinfo='text',
                                 text=f"{p['serves']} ({p['hierarchy']})"))
        first = False

def draw_entries(fig, entries):
    seen = set()
    for e in entries['entries']:
        color = '#dc2626' if e['type'] == 'public' else '#0891b2'
        show = e['type'] not in seen; seen.add(e['type'])
        fig.add_trace(go.Scatter(x=[e['point'][0]], y=[e['point'][1]],
                                 name=f"{e['type']} site entry", mode='markers',
                                 marker=dict(size=17, color=color, symbol='triangle-up',
                                             line=dict(color='white', width=1)),
                                 showlegend=show, hoverinfo='text', text=e.get('road_name') or ''))

def draw_entrances(fig, orientation, arrow=8.0):
    shown = set()
    for b in orientation['buildings']:
        for e in b['entrances']:
            ex, ey, _ = e['point']; dx, dy = e['direction']
            color = ROLE_COLORS.get(e['role'], '#111')
            fig.add_annotation(x=ex + dx * arrow, y=ey + dy * arrow, ax=ex, ay=ey,
                               xref='x', yref='y', axref='x', ayref='y', showarrow=True,
                               arrowhead=2, arrowsize=1.1, arrowwidth=2, arrowcolor=color)
            fig.add_trace(go.Scatter(x=[ex], y=[ey], mode='markers',
                                     name=f"{e['role']} entrance",
                                     marker=dict(size=9, color=color, symbol='circle',
                                                 line=dict(color='white', width=1)),
                                     showlegend=e['role'] not in shown, legendgroup=e['role'],
                                     hoverinfo='text', text=e.get('reason', '')))
            shown.add(e['role'])

def draw_emergency_exits(fig, egress, arrow=7.0):
    shown = False
    for b in egress['buildings']:
        for e in b['exits']:
            ex, ey, _ = e['point']; dx, dy = e['direction']
            fig.add_annotation(x=ex + dx * arrow, y=ey + dy * arrow, ax=ex, ay=ey,
                               xref='x', yref='y', axref='x', ayref='y', showarrow=True,
                               arrowhead=3, arrowsize=1.1, arrowwidth=2, arrowcolor=EXIT_COLOR)
            fig.add_trace(go.Scatter(x=[ex], y=[ey], mode='markers', name='emergency exit',
                                     marker=dict(size=9, color=EXIT_COLOR, symbol='square',
                                                 line=dict(color='white', width=1)),
                                     showlegend=not shown, legendgroup='exit', hoverinfo='skip'))
            shown = True

def draw_parking(fig, parking, parking_access=None):
    for z in (parking or {}).get('zones', []):
        xs, ys = _xy(z['boundary'])
        fig.add_trace(go.Scatter(x=xs, y=ys, name='parking', mode='lines', fill='toself',
                                 fillcolor='rgba(56,189,248,0.25)', line=dict(color='#0ea5e9', width=1),
                                 legendgroup='park', showlegend=False, hoverinfo='skip'))
    first = True
    for z in (parking_access or {}).get('zones', []):
        d = z.get('drop_off_point')
        if d:
            fig.add_trace(go.Scatter(x=[d[0]], y=[d[1]], mode='markers', name='drop-off',
                                     marker=dict(size=11, color='#0891b2', symbol='diamond'),
                                     showlegend=first, hoverinfo='text',
                                     text=f"to {z['nearest_entrance_building']} ~{z['straight_distance_m']} m"))
            first = False

def draw_conflicts(fig, conflicts):
    pts = [c['location'] for c in conflicts.get('conflicts', []) if c.get('location')]
    if pts:
        fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode='markers',
                                 name='conflict', marker=dict(size=12, color='#111', symbol='x'),
                                 hoverinfo='text', text=[c['type'] for c in conflicts['conflicts'] if c.get('location')]))
print('helpers defined')
"""))

# =========================================================== Scene A
cells.append(md("""# Scene A — Irregular site, mixed wing typologies

A concave site (a notch cut from the top-right) fronted by **Main Street**
(south) and a **Service Lane** (west). Three real buildings sit on it:

* **U-court** — a U-shaped block (built from the wing model), open court facing in;
* **H-block** — an H-shaped building with two pockets;
* **O-court** — a perimeter block with a true enclosed courtyard (a hole).

Parking is allocated from real demand on the main-road frontage. We then call
`evaluate_site_circulation` once and read the report section by section."""))

cells.append(code("""
SITE_BOUNDARY = [
    [0,0,0], [165,0,0], [165,70,0], [110,70,0], [110,130,0], [0,130,0], [0,0,0],
]
SITE_MODEL = {
    'boundary': SITE_BOUNDARY,
    'sides': [
        {'side_index':0,'start':[0,0],'end':[165,0],
         'adjacent_road':{'name':'Main Street','hierarchy':'main','width_m':20.0}},
        {'side_index':1,'start':[165,0],'end':[165,70],'adjacent_road':None},
        {'side_index':2,'start':[165,70],'end':[110,70],'adjacent_road':None},
        {'side_index':3,'start':[110,70],'end':[110,130],'adjacent_road':None},
        {'side_index':4,'start':[110,130],'end':[0,130],
         'adjacent_road':{'name':'Park Walk','hierarchy':'path','width_m':4.0}},
        {'side_index':5,'start':[0,130],'end':[0,0],
         'adjacent_road':{'name':'Service Lane','hierarchy':'secondary','width_m':6.0}},
    ],
    'roads': {'main_road_side_index': 0, 'main_road': {'name':'Main Street','width_m':20.0}},
}

U_COURT = {'building_id':'U_court','label':'U-court','storeys':6,
           'boundary': winged('U', area=1500, depth=12, ratio=0.5, xy=(18, 30))}
H_BLOCK = {'building_id':'H_block','label':'H-block','storeys':7,
           'boundary': winged('H', area=1700, depth=12, ratio=0.5, xy=(96, 28))}
O_COURT = {'building_id':'O_court','label':'O-court','storeys':8,
           'boundary':[[18,92,0],[78,92,0],[78,124,0],[18,124,0]],
           'holes':[[[34,100],[62,100],[62,117],[34,117]]]}
BUILDINGS = [U_COURT, H_BLOCK, O_COURT]

demand  = compute_building_demand(BUILDINGS, parking_ratio=0.6)
parking = allocate_parking_zones(SITE_MODEL, BUILDINGS, demand)
print('parking:', parking['summary'])

report = evaluate_site_circulation(SITE_MODEL, BUILDINGS, parking)
print()
print(report['summary'])
"""))

cells.append(md("""## A1 — Entrance placement **reasoning**

Each building gets typed entrances; hover any entrance marker to read *why* it
sits there. The public door faces the arrival route; the service door faces the
quiet Service Lane side; residential/courtyard doors open onto the court."""))

cells.append(code("""
orient = report['entrances']
for b in orient['buildings']:
    print(f"### {b['building_id']}  ({b['n_entrances']} entrances, {len(b['courtyards'])} courtyard)")
    for e in b['entrances']:
        print(f"   - {e['role']:11s} faces={e['faces']:12s} :: {e['reason']}")

fig = new_fig('A1 — Typed building entrances (hover for the reason)', SITE_BOUNDARY)
draw_parking(fig, parking)
draw_buildings(fig, BUILDINGS)
draw_entries(fig, propose_site_entries(SITE_MODEL))
draw_entrances(fig, orient)
fig.show()
"""))

cells.append(md("""## A2 — Site arrival strategy + vehicular network

`site_access` says, per frontage, whether pedestrians and/or vehicles arrive,
and gives each site entry's street→site→building sequence. The vehicular network
is obstacle-aware — corridors bend **around** other buildings."""))

cells.append(code("""
arr = report['site_access']
print(arr['summary'])
for f in arr['frontages']:
    print(f"   frontage side {f['side_index']:>2} [{f['road_name']}] {f['hierarchy']:9s} -> {f['note']}")
print('arrivals:')
for a in arr['arrivals']:
    print(f"   {a['entry_id']:16s} [{a['mode']:10s}] {a['sequence']}")

veh = report['vehicular_circulation']
print(); print('vehicular:', veh['summary'])

fig = new_fig('A2 — Vehicular circulation (obstacle-aware)', SITE_BOUNDARY)
draw_vehicular(fig, veh)
draw_parking(fig, parking)
draw_buildings(fig, BUILDINGS)
draw_entries(fig, propose_site_entries(SITE_MODEL))
fig.show()
"""))

cells.append(md("""## A3 — Pedestrian network + parking integration

Pedestrian routes (dashed green) connect the site entry to each public door and
walk people up from parking — and they treat **parking as an obstacle**, so they
don't cut across the lot. Drop-off diamonds mark where you'd alight nearest each
entrance; the report flags whether the walk is within comfortable / accessible
range."""))

cells.append(code("""
ped = report['pedestrian_circulation']
pa  = report['parking_integration']
print('pedestrian:', ped['summary'])
print('parking   :', pa['summary'])
for z in pa['zones']:
    print(f"   {z['zone_id']}: nearest={z['nearest_entrance_building']} "
          f"~{z['straight_distance_m']} m  accessible_ok={z['accessible_parking_ok']}  "
          f"| {z['sequence']}")

fig = new_fig('A3 — Pedestrian network + drop-off (parking is an obstacle)', SITE_BOUNDARY)
draw_vehicular(fig, veh)
draw_pedestrian(fig, ped)
draw_parking(fig, parking, pa)
draw_buildings(fig, BUILDINGS)
draw_entries(fig, propose_site_entries(SITE_MODEL))
fig.show()
"""))

cells.append(md("""## A4 — Fire safety & emergency egress

`fire_safety_egress` combines two things per building: **emergency exits**
(orange arrows) placed on open exterior facades with multiple independent escape
directions — never discharging into a courtyard — and **fire-appliance reach**
(strict: nearest wall, deepest interior, every courtyard). Buildings shade green
(serviceable) / red (a courtyard or core out of reach)."""))

cells.append(code("""
fs = report['fire_safety_egress']
fire, egress = fs['fire_access'], fs['egress']
print('fire  :', fire['summary'])
print('egress:', egress['summary'])
for r in egress['buildings']:
    fa = r['fire_appliance_access']
    print(f"   {r['building_id']:8s} exits={r['n_exits']} indep_dir={r['independent_directions']} "
          f"single_point={r['single_point_failure']} court_only={r['courtyard_only_egress_risk']} "
          f"| appliance: near={fa['distance_m']}m deep={fa['deepest_point_distance_m']}m "
          f"courts_ok={fa['courtyards_reachable']} compliant={r['compliant']}")

fig = new_fig('A4 — Emergency exits (orange) + fire-appliance reach (green/red)', SITE_BOUNDARY)
draw_vehicular(fig, veh)
draw_buildings(fig, BUILDINGS, fire=fire)
draw_emergency_exits(fig, egress)
draw_entries(fig, propose_site_entries(SITE_MODEL))
fig.show()
"""))

cells.append(md("""## A5 — Conflicts & the validation audit

`conflicts` lists every pedestrian/vehicle crossing and pedestrian-through-parking
with a **resolution**; `audit` runs the pre-finalisation checklist. A failing
conflict check here is a *correct* finding — the south parking forces arrival
walks to cross it, which is exactly what the audit should surface."""))

cells.append(code("""
conf = report['conflicts']
audit = report['audit']
print(conf['summary'])
for c in conf['conflicts']:
    loc = c.get('location')
    where = f"@({loc[0]:.0f},{loc[1]:.0f})" if loc else f"[{c.get('building_id')}]"
    print(f"   {c['type']:28s} {where:14s} -> {c['resolution']}")
print()
print(audit['summary'])
for c in audit['checks']:
    print(f"   {'PASS' if c['pass'] else 'FAIL'}  {c['check']:38s} {c['detail']}")

fig = new_fig('A5 — Conflicts (black ✕): ped/vehicle + ped-through-parking', SITE_BOUNDARY)
draw_vehicular(fig, veh)
draw_pedestrian(fig, ped)
draw_parking(fig, parking, pa)
draw_buildings(fig, BUILDINGS)
draw_conflicts(fig, conf)
fig.show()
"""))

# =========================================================== Scene B
cells.append(md("""# Scene B — Emergency-egress gallery across typologies

Egress reasoning is typology-aware because it runs on **facades**, not boxes.
Each footprint below is split into facades (open = grey, courtyard pocket =
purple, enclosed-court ring = dashed) and exits (orange) are placed only on
**open** facades, spread for independent escape directions and per-wing coverage.
This covers U, H, X, Y, an **E** comb, and a true **courtyard / O** building."""))

cells.append(code("""
# E-shaped comb footprint (spine + three prongs) — built by hand.
E_SHAPE = [[0,0,0],[40,0,0],[40,10,0],[12,10,0],[12,25,0],[40,25,0],[40,35,0],
           [12,35,0],[12,50,0],[40,50,0],[40,60,0],[0,60,0]]
O_RING  = {'boundary':[[0,0,0],[44,0,0],[44,44,0],[0,44,0]],
           'holes':[[[14,14],[30,14],[30,30],[14,30]]]}

GALLERY = [
    ('U', {'boundary': winged('U', 1500, 12, 0.5, (0, 0))}),
    ('H', {'boundary': winged('H', 1700, 12, 0.5, (0, 0))}),
    ('X', {'boundary': winged('X', 1500, 12, 0.5, (0, 0))}),
    ('Y', {'boundary': winged('Y', 1500, 12, 0.5, (0, 0))}),
    ('E (comb)', {'boundary': E_SHAPE}),
    ('O (courtyard)', O_RING),
]

FACE_COLORS = {'open': 'rgba(100,116,139,0.30)', 'courtyard': 'rgba(147,51,234,0.25)',
               'enclosed_courtyard': 'rgba(147,51,234,0.0)'}

def egress_fig(name, bld):
    facades = segment_facades(bld)
    ee = generate_emergency_exits(bld)
    poly = bld['boundary']
    fig = go.Figure()
    xs, ys = _xy(poly)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', fill='toself',
                             fillcolor='rgba(15,118,110,0.12)', line=dict(color='#0f766e', width=2),
                             showlegend=False, hoverinfo='skip'))
    for hole in bld.get('holes', []) or []:
        hxs, hys = _xy(hole)
        fig.add_trace(go.Scatter(x=hxs, y=hys, mode='lines', fill='toself', fillcolor='white',
                                 line=dict(color='#9333ea', width=1, dash='dot'),
                                 showlegend=False, hoverinfo='skip'))
    # facade midpoints coloured by what they face
    for f in facades:
        mx, my, _ = f['midpoint']
        fig.add_trace(go.Scatter(x=[mx], y=[my], mode='markers',
                                 marker=dict(size=8, color=FACE_COLORS.get(f['faces'], '#999'),
                                             line=dict(color='#555', width=0.5)),
                                 showlegend=False, hoverinfo='text', text=f['faces']))
    # exits
    for e in ee['exits']:
        ex, ey, _ = e['point']; dx, dy = e['direction']
        fig.add_annotation(x=ex + dx * 6, y=ey + dy * 6, ax=ex, ay=ey, xref='x', yref='y',
                           axref='x', ayref='y', showarrow=True, arrowhead=3, arrowsize=1.1,
                           arrowwidth=2, arrowcolor=EXIT_COLOR)
    risk = ('  ⚠ ' + ('single-point ' if ee['single_point_failure'] else '')
            + ('courtyard-only' if ee['courtyard_only_egress_risk'] else '')).rstrip()
    title = (f"{name}: {ee['n_exits']} exits, {ee['independent_directions']} independent dir, "
             f"wings_covered={ee['wing_coverage'].get('covered')}" + (risk if risk.strip('⚠ ') else '  ✓'))
    fig.update_layout(title=title, height=380, width=440,
                      yaxis=dict(scaleanchor='x', scaleratio=1, visible=False),
                      xaxis=dict(visible=False), margin=dict(l=0, r=0, t=40, b=0),
                      plot_bgcolor='#f8fafc', paper_bgcolor='#f8fafc')
    return fig, ee

for name, bld in GALLERY:
    fig, ee = egress_fig(name, bld)
    print(f"{name:16s}: {ee['summary']}")
    fig.show()
"""))

# =========================================================== Scene C
cells.append(md("""# Scene C — Strict fire access catches an unreachable enclosed courtyard

The case the nearest-wall test silently passes. A large **O-court** sits on a
plaza; the perimeter road touches its outer wall (`distance ≈ 0`, loose check and
the optimizer's `G ≤ 0` constraint are happy) — but its enclosed courtyard is
~60 m inside, beyond hose reach. **Strict mode fails it.** Note the emergency
exits still sit on the *outer* facades (orange), never into the trapped court."""))

cells.append(code("""
PLAZA = [[0,0,0],[180,0,0],[180,150,0],[0,150,0]]
PLAZA_MODEL = {'boundary': PLAZA, 'roads': {'main_road_side_index': 0}}
BIG_O = {'building_id':'big_O','label':'Large O-court','storeys':8,
         'boundary':[[25,18,0],[155,18,0],[155,135,0],[25,135,0]],
         'holes':[[[60,52],[120,52],[120,102],[60,102]]]}

p_ent  = propose_site_entries(PLAZA_MODEL)
p_circ = route_internal_circulation(PLAZA_MODEL, p_ent, [BIG_O], None)
loose  = check_fire_access([BIG_O], p_circ, strict=False)
strict = check_fire_access([BIG_O], p_circ, strict=True)
eg     = analyze_egress([BIG_O], p_circ)

lb, sb = loose['buildings'][0], strict['buildings'][0]
print(f"outer-wall distance = {lb['distance_m']} m  within_reach={lb['within_reach']}  G={lb['constraint_value']}")
print(f"deepest interior    = {sb['deepest_point_distance_m']} m")
print(f"courtyard reachable = {sb['courtyards'][0]['reachable']} "
      f"(centre {sb['courtyards'][0]['distance_m']} m from a road)")
print(f"loose pass = {lb['pass']}   |   strict pass = {sb['pass']}")
print('egress:', eg['summary'])

def plaza_fig(title, fire):
    fig = new_fig(title, PLAZA, h=560)
    draw_vehicular(fig, p_circ)
    draw_buildings(fig, [BIG_O], fire=fire)
    draw_emergency_exits(fig, eg)
    draw_entries(fig, p_ent)
    c = sb['courtyards'][0]['centroid']; ok = sb['courtyards'][0]['reachable']
    fig.add_trace(go.Scatter(x=[c[0]], y=[c[1]], mode='markers+text',
                             text=['court OK' if ok else 'court UNREACHABLE'], textposition='top center',
                             marker=dict(size=14, color='#15803d' if ok else '#b91c1c', symbol='x'),
                             showlegend=False, hoverinfo='skip'))
    return fig

plaza_fig('C — LOOSE: outer wall reachable, building passes (green)', loose).show()
plaza_fig('C — STRICT: enclosed courtyard unreachable, building fails (red)', strict).show()
"""))

cells.append(md("""## Summary — what the rebuild added

- **Functional, not just geometric.** `evaluate_site_circulation` reasons about
  arrival → entrance → parking → walk → egress, returning one report per layout.
- **Typed entrances with reasons.** Public / service / residential / courtyard
  doors, each carrying *why* it sits where it does — placed on real facades.
- **Pedestrian ≠ vehicular.** Separate networks; pedestrians route **around**
  parking; conflicts where they cross are flagged with resolutions.
- **Parking as a journey.** Drop-off points, accessible-walk checks, and the
  street→site→park→door sequence — not an isolated rectangle.
- **Egress that understands form.** Multi-direction emergency exits on open
  facades only, courtyard-avoiding, with per-wing coverage and single-point-
  failure flags — across U / H / X / Y / E / courtyard typologies.
- **Audited.** A validation checklist (public entrance, connectivity, parking
  link, compliant egress, fire access, no isolation, conflicts) gates the layout
  — while the optimizer's `G = distance − max_distance` fire constraint is
  unchanged, so nothing downstream broke."""))

# nbformat minor 5 requires a stable id on every cell.
for _k, _c in enumerate(cells):
    _c["id"] = f"cell-{_k:02d}"

nb = {
    "cells": cells,
    "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                 "language_info": {"name": "python"}},
    "nbformat": 4,
    "nbformat_minor": 5,
}

out = Path(__file__).resolve().parent / "test_circulation_fire.ipynb"
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print("wrote", out)
