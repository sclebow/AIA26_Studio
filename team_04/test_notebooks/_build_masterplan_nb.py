"""Generator for test_masterplan.ipynb (Phase 6 — circulation-first masterplanning).

Run once to (re)emit the notebook JSON; reproducible and reviewable as code.

    python team_04/test_notebooks/_build_masterplan_nb.py

The notebook visualises `agent/tools/masterplan.generate_masterplan` — the
circulation-FIRST pipeline — one step at a time, so you can see the skeleton get
laid before any building and watch footprints attach to it:

    1 setbacks → buildable envelope     6 drop-offs (from entrances)
    2 access structure (entry roles)    7 parking (serves destinations)
    3 movement spine + fire loop        8 pedestrian desire lines
    4 buildings attach to the spine     9 fire access + egress
    5 building entrances               10 five-axis score → accept / reject

Scene A walks an irregular site step by step. Scene B runs a constrained urban
block to show the quality gate rejecting / flagging an over-stuffed program.
"""
import json
from pathlib import Path

md = lambda s: {"cell_type": "markdown", "metadata": {}, "source": s.splitlines(keepends=True)}
code = lambda s: {"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": s.strip("\n").splitlines(keepends=True)}

cells = []

cells.append(md("""# Phase 6 — Circulation-first generative masterplanning

The earlier tools placed buildings, then connected paths — which is why layouts
came out functionally invalid (buildings on boundaries, parking under footprints,
circulation forced around an already-packed site). This rebuilds the **order of
operations** the way a design team actually works:

> reserve margins → decide access → lay the movement skeleton → **hang buildings
> off it** → entrances → drop-offs → parking → footways → fire check → score.

`generate_masterplan(site_model, program)` runs all ten steps and returns one
report with every artifact, a per-element **reasoning log**, and a five-axis
**score** that accepts or rejects the layout. Below we run it and reveal the
layers one step at a time."""))

cells.append(code("""
from __future__ import annotations
import sys
from pathlib import Path

workspace_root = Path.cwd().resolve()
candidate_roots = (workspace_root, workspace_root.parent,
                   workspace_root / 'team_04', workspace_root.parent / 'team_04')
TEAM_ROOT = next((p for p in candidate_roots if (p / 'agent').exists()), None)
if TEAM_ROOT is None:
    raise FileNotFoundError('Run from workspace root, team_04/, or team_04/test_notebooks/')
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))
print('TEAM_ROOT:', TEAM_ROOT)
"""))

cells.append(code("""
import plotly.graph_objects as go
import plotly.io as pio
pio.renderers.default = 'plotly_mimetype+notebook_connected'

from agent.tools.masterplan import generate_masterplan

# ---- plot helpers ---------------------------------------------------------
TYPE_COLORS = {'U': 'rgba(15,118,110,0.40)', 'H': 'rgba(124,58,237,0.35)',
               'X': 'rgba(180,83,9,0.35)', 'Y': 'rgba(8,145,178,0.35)',
               'O': 'rgba(190,24,93,0.35)', 'I': 'rgba(71,85,105,0.35)',
               'L': 'rgba(2,132,199,0.35)', 'T': 'rgba(101,163,13,0.35)'}
ROLE_COLORS = {'public': '#dc2626', 'service': '#2563eb',
               'residential': '#16a34a', 'courtyard': '#9333ea'}

def _xy(pts):
    xs = [p[0] for p in pts] + [pts[0][0]]
    ys = [p[1] for p in pts] + [pts[0][1]]
    return xs, ys

def new_fig(title, site, buildable=None, h=620):
    fig = go.Figure()
    xs, ys = _xy(site)
    fig.add_trace(go.Scatter(x=xs, y=ys, name='Site boundary', mode='lines',
                             line=dict(color='#1d4ed8', width=3), hoverinfo='skip'))
    if buildable:
        bx, by = _xy(buildable)
        fig.add_trace(go.Scatter(x=bx, y=by, name='Buildable envelope', mode='lines',
                                 fill='toself', fillcolor='rgba(34,197,94,0.06)',
                                 line=dict(color='#16a34a', width=1.5, dash='dash'), hoverinfo='skip'))
    fig.update_layout(title=title, height=h,
                      yaxis=dict(scaleanchor='x', scaleratio=1, visible=False),
                      xaxis=dict(visible=False), margin=dict(l=0, r=0, t=44, b=0),
                      plot_bgcolor='#f0f4ff', paper_bgcolor='#f0f4ff',
                      legend=dict(x=1.02, y=1, bgcolor='white', bordercolor='#ccc', borderwidth=1))
    return fig

def draw_spine(fig, spine):
    s = spine['vehicular_spine']
    fig.add_trace(go.Scatter(x=[p[0] for p in s], y=[p[1] for p in s], name='vehicular spine',
                             mode='lines', line=dict(color='#ea580c', width=5), hoverinfo='skip'))
    if spine.get('entry_stub'):
        st = spine['entry_stub']
        fig.add_trace(go.Scatter(x=[p[0] for p in st], y=[p[1] for p in st], name='entry stub',
                                 mode='lines', line=dict(color='#ea580c', width=3, dash='dot'), hoverinfo='skip'))
    if spine.get('fire_loop'):
        fx, fy = _xy(spine['fire_loop'])
        fig.add_trace(go.Scatter(x=fx, y=fy, name='fire loop', mode='lines',
                                 line=dict(color='#b91c1c', width=2, dash='dash'), hoverinfo='skip'))

def draw_buildings(fig, buildings, fire=None, color_by_type=True):
    fire_by = {b['building_id']: b for b in (fire or {}).get('buildings', [])}
    for b in buildings:
        xs, ys = _xy(b['boundary'])
        passed = fire_by.get(b['building_id'], {}).get('pass')
        if passed is True:
            fill, line = 'rgba(34,197,94,0.40)', '#15803d'
        elif passed is False:
            fill, line = 'rgba(239,68,68,0.40)', '#b91c1c'
        else:
            fill = TYPE_COLORS.get(b.get('type', 'I'), 'rgba(71,85,105,0.35)')
            line = fill.replace('0.40', '1').replace('0.35', '1')
        fig.add_trace(go.Scatter(x=xs, y=ys, name=b.get('label', b['building_id']),
                                 mode='lines', fill='toself', fillcolor=fill,
                                 line=dict(color=line, width=2), hoverinfo='text',
                                 text=b.get('placement_reason', '')))
        for hole in b.get('holes', []) or []:
            hx, hy = _xy(hole)
            fig.add_trace(go.Scatter(x=hx, y=hy, mode='lines', fill='toself', fillcolor='#f0f4ff',
                                     line=dict(color=line, width=1, dash='dot'), showlegend=False, hoverinfo='skip'))
        cx = sum(p[0] for p in b['boundary']) / len(b['boundary'])
        cy = sum(p[1] for p in b['boundary']) / len(b['boundary'])
        fig.add_annotation(x=cx, y=cy, text=f"{b.get('label', b['building_id'])}", showarrow=False,
                           font=dict(size=10, color='#111'))

def draw_entries(fig, access):
    seen = set()
    for r in access['roles']:
        color = '#dc2626' if r['role'] == 'main' else '#0891b2'
        fig.add_trace(go.Scatter(x=[r['point'][0]], y=[r['point'][1]], name=f"{r['role']} entry",
                                 mode='markers', marker=dict(size=17, color=color, symbol='triangle-up',
                                 line=dict(color='white', width=1)),
                                 showlegend=r['role'] not in seen, hoverinfo='text', text=r['reason']))
        seen.add(r['role'])

def draw_entrances(fig, orientation):
    shown = set()
    for b in orientation['buildings']:
        for e in b['entrances']:
            ex, ey, _ = e['point']; dx, dy = e['direction']
            c = ROLE_COLORS.get(e['role'], '#111')
            fig.add_annotation(x=ex + dx * 7, y=ey + dy * 7, ax=ex, ay=ey, xref='x', yref='y',
                               axref='x', ayref='y', showarrow=True, arrowhead=2, arrowsize=1.1,
                               arrowwidth=2, arrowcolor=c)
            fig.add_trace(go.Scatter(x=[ex], y=[ey], mode='markers', name=f"{e['role']} entrance",
                                     marker=dict(size=8, color=c, line=dict(color='white', width=1)),
                                     showlegend=e['role'] not in shown, legendgroup=e['role'],
                                     hoverinfo='text', text=e.get('reason', '')))
            shown.add(e['role'])

def draw_dropoffs(fig, dropoffs):
    first = True
    for d in dropoffs['dropoffs']:
        ep = d['entrance_point']; dp = d['point']
        fig.add_trace(go.Scatter(x=[ep[0], dp[0]], y=[ep[1], dp[1]], mode='lines',
                                 line=dict(color='#0891b2', width=1, dash='dot'), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=[dp[0]], y=[dp[1]], mode='markers', name='drop-off',
                                 marker=dict(size=12, color='#0891b2', symbol='diamond'),
                                 showlegend=first, hoverinfo='text', text=d['reason']))
        first = False

def draw_parking(fig, parking):
    first = True
    for z in parking.get('zones', []):
        xs, ys = _xy(z['boundary'])
        fig.add_trace(go.Scatter(x=xs, y=ys, name='parking', mode='lines', fill='toself',
                                 fillcolor='rgba(56,189,248,0.25)', line=dict(color='#0ea5e9', width=1),
                                 legendgroup='park', showlegend=first, hoverinfo='skip'))
        first = False

def draw_pedestrian(fig, ped):
    first = True
    for p in ped.get('paths', []):
        px = [pt[0] for pt in p['polyline']]; py = [pt[1] for pt in p['polyline']]
        fig.add_trace(go.Scatter(x=px, y=py, name='pedestrian route', mode='lines',
                                 line=dict(color='#16a34a', width=2, dash='dash'),
                                 legendgroup='ped', showlegend=first, hoverinfo='skip'))
        first = False

def score_bar(score):
    subs = score['sub_scores']
    fig = go.Figure(go.Bar(x=list(subs.values()), y=list(subs.keys()), orientation='h',
                           marker_color=['#16a34a' if v >= 0.6 else '#dc2626' for v in subs.values()],
                           text=[f'{v:.2f}' for v in subs.values()], textposition='auto'))
    verdict = 'ACCEPTED' if score['accepted'] else 'REJECTED'
    fig.update_layout(title=f"Step 10 — score {score['overall']:.2f}/1.0 → {verdict} (threshold {score['threshold']})",
                      height=300, xaxis=dict(range=[0, 1]), margin=dict(l=10, r=10, t=44, b=10),
                      plot_bgcolor='#f8fafc', paper_bgcolor='#f8fafc')
    return fig

print('helpers defined')
"""))

# =========================================================== Scene A
cells.append(md("""# Scene A — irregular site, mixed typologies, step by step

An irregular concave site fronted by **Main Blvd** (south, 24 m) and a **Service
Lane** (west). Program: a U-court, an H-block, an L-wing and an O-court. We call
`generate_masterplan` once, then reveal the layers in pipeline order."""))

cells.append(code("""
SITE = {
    'boundary': [[0,0,0],[180,0,0],[180,80,0],[120,80,0],[120,150,0],[0,150,0]],
    'sides': [
        {'side_index':0,'start':[0,0],'end':[180,0],'adjacent_road':{'name':'Main Blvd','hierarchy':'main','width_m':24.0}},
        {'side_index':1,'start':[180,0],'end':[180,80],'adjacent_road':None},
        {'side_index':2,'start':[180,80],'end':[120,80],'adjacent_road':None},
        {'side_index':3,'start':[120,80],'end':[120,150],'adjacent_road':None},
        {'side_index':4,'start':[120,150],'end':[0,150],'adjacent_road':{'name':'Park Walk','hierarchy':'path','width_m':4.0}},
        {'side_index':5,'start':[0,150],'end':[0,0],'adjacent_road':{'name':'Service Ln','hierarchy':'secondary','width_m':6.0}},
    ],
    'roads': {'main_road_side_index': 0},
}
PROGRAM = [
    {'building_id':'B1','label':'U-court','type':'U','area':1300,'storeys':6},
    {'building_id':'B2','label':'H-block','type':'H','area':1400,'storeys':7},
    {'building_id':'B3','label':'L-wing','type':'L','area':1000,'storeys':5},
    {'building_id':'B4','label':'O-court','type':'O','area':1100,'storeys':5},
]
rep = generate_masterplan(SITE, PROGRAM)
SITEB = SITE['boundary']; BLD = rep['margins']['buildable_boundary']
print(rep['summary'])
print()
for r in rep['reasoning']:
    print(r)
"""))

cells.append(md("""## Steps 1–3 — reserve margins, access, lay the spine (before any building)

The dashed green ring is the **buildable envelope** after setbacks (wider Main
Blvd → deeper front setback). Site entries are classified by role. Then the
orange **vehicular spine** + red **fire loop** are laid in the *empty* envelope —
this is the skeleton buildings will attach to."""))

cells.append(code("""
fig = new_fig('Steps 1–3 — buildable envelope + access + movement spine (no buildings yet)', SITEB, BLD)
draw_spine(fig, rep['spine'])
draw_entries(fig, rep['access'])
fig.show()
print('margins:', rep['margins']['reason'])
print('access :', rep['access']['summary'])
print('spine  :', rep['spine']['reason'])
"""))

cells.append(md("""## Step 4 — buildings attach to the spine

Each footprint takes the first slot along the central spine (or the perimeter
loop) that sits inside the envelope, clear of the corridor, and far enough from
its neighbours — biggest first, gaps filled after. Hover a building for its
placement reason. Nothing touches the boundary or the corridor."""))

cells.append(code("""
fig = new_fig('Step 4 — buildings attached to the circulation skeleton', SITEB, BLD)
draw_spine(fig, rep['spine'])
draw_buildings(fig, rep['buildings'])
draw_entries(fig, rep['access'])
fig.show()
print(rep['placement']['summary'])
for b in rep['buildings']:
    print(f"  {b['building_id']} ({b['type']}): {b['placement_reason']}")
"""))

cells.append(md("""## Steps 5–6 — entrances, then drop-offs derived from them

Public doors (red) face the spine; service doors (blue) face the quiet side.
Every drop-off (cyan diamond) is generated **from** a public entrance and snapped
to the nearest road — never random, never in open space."""))

cells.append(code("""
fig = new_fig('Steps 5–6 — building entrances + drop-offs', SITEB, BLD)
draw_spine(fig, rep['spine'])
draw_buildings(fig, rep['buildings'])
draw_entrances(fig, rep['entrances'])
draw_dropoffs(fig, rep['dropoffs'])
fig.show()
print(rep['dropoffs']['summary'])
for d in rep['dropoffs']['dropoffs']:
    print(f"  {d['drop_id']}: {d['reason']}")
"""))

cells.append(md("""## Steps 7–8 — parking that serves destinations + pedestrian desire lines

Parking (light blue) is allocated to the frontage and connected by pedestrian
routes (dashed green) that run entry→door and parking→door while **treating
parking as an obstacle** — street → site → parking → path → entrance."""))

cells.append(code("""
fig = new_fig('Steps 7–8 — parking + pedestrian network', SITEB, BLD)
draw_spine(fig, rep['spine'])
draw_parking(fig, rep['parking'])
draw_buildings(fig, rep['buildings'])
draw_pedestrian(fig, rep['pedestrian_circulation'])
draw_entrances(fig, rep['entrances'])
draw_dropoffs(fig, rep['dropoffs'])
fig.show()
print('parking   :', rep['parking']['summary'])
print('pedestrian:', rep['pedestrian_circulation']['summary'])
print('parking integration:')
for z in rep['parking_integration']['zones']:
    print(f"  {z['zone_id']}: {z['sequence']}")
"""))

cells.append(md("""## Steps 9–10 — fire validation + the quality score

Buildings shade green when a fire appliance can service them (strict: nearest
wall, deepest interior, every courtyard). Then the layout is scored on five axes;
below threshold it is **rejected**."""))

cells.append(code("""
fire = rep['fire_safety_egress']['fire_access']
fig = new_fig('Steps 9–10 — fire access (green = serviceable) + egress', SITEB, BLD)
draw_spine(fig, rep['spine'])
draw_buildings(fig, rep['buildings'], fire=fire)
draw_entries(fig, rep['access'])
fig.show()
print('fire  :', fire['summary'])
print('egress:', rep['fire_safety_egress']['egress']['summary'])
print('audit :', rep['audit']['summary'])

score_bar(rep['score']).show()
print(rep['score']['summary'])
"""))

# =========================================================== Scene B
cells.append(md("""# Scene B — constrained urban block: the quality gate at work

A tight 110 × 90 m block with a deliberately over-stuffed program (six blocks).
The pipeline reserves margins, lays the spine, and packs what it can — then
**honestly reports what doesn't fit** rather than forcing buildings into empty
space, and still scores the placed subset. This is the behaviour the brief asked
for: reject placements that can't satisfy access."""))

cells.append(code("""
BLOCK = {'boundary': [[0,0,0],[110,0,0],[110,90,0],[0,90,0]],
         'sides': [
            {'side_index':0,'start':[0,0],'end':[110,0],'adjacent_road':{'name':'High St','hierarchy':'main','width_m':18.0}},
            {'side_index':2,'start':[110,90],'end':[0,90],'adjacent_road':{'name':'Back Ln','hierarchy':'secondary','width_m':6.0}}],
         'roads': {'main_road_side_index': 0}}
DENSE = [{'building_id':f'D{i}','label':f'Blk{i}','type':t,'area':a,'storeys':6}
         for i,(t,a) in enumerate([('H',900),('U',900),('X',800),('O',800),('L',700),('T',700)],1)]
rep2 = generate_masterplan(BLOCK, DENSE)
print(rep2['summary'])
print('placed  :', [b['building_id'] for b in rep2['buildings']])
print('unplaced:', rep2['placement']['unplaced'])

fig = new_fig('Scene B — constrained block (placed buildings + skeleton)', BLOCK['boundary'],
              rep2['margins']['buildable_boundary'], h=520)
draw_spine(fig, rep2['spine'])
draw_parking(fig, rep2['parking'])
draw_buildings(fig, rep2['buildings'], fire=rep2['fire_safety_egress']['fire_access'])
draw_entrances(fig, rep2['entrances'])
draw_dropoffs(fig, rep2['dropoffs'])
fig.show()
score_bar(rep2['score']).show()
print(rep2['score']['summary'])
for c in rep2['audit']['checks']:
    print(f"  {'PASS' if c['pass'] else 'FAIL'}  {c['check']}: {c['detail']}")
"""))

cells.append(md("""## Summary — what the circulation-first rebuild changes

- **Order inverted.** Margins → access → **spine** → buildings → entrances →
  drop-offs → parking → footways → fire → score. Circulation is the skeleton;
  buildings hang off it instead of being packed into empty space.
- **No more invalid placements.** Footprints are generated only inside the
  buildable envelope, kept clear of the spine corridor and of each other, and
  oriented so the public entrance faces arrival — rejected outright if no valid
  slot exists (reported as `unplaced`, not forced).
- **Everything derives from something.** Drop-offs come from entrances and a
  road; parking serves a destination; pedestrian desire lines connect entry,
  parking and doors while avoiding the lot.
- **A quality gate.** Five weighted sub-scores (placement, vehicular, pedestrian,
  entrance, fire) accept or reject the layout — the agent optimises for site
  *function*, not geometric packing. Every decision carries a written reason."""))

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

out = Path(__file__).resolve().parent / "test_masterplan.ipynb"
out.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print("wrote", out)
