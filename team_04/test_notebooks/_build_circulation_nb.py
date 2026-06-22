"""Generator for test_circulation_fire.ipynb (Phase 5).

Run once to (re)emit the notebook JSON. Kept in the repo so the notebook is
reproducible and reviewable as code. Not a test; not imported by anything.

This version deliberately exercises the *hard* cases the simple-rectangle demo
ignored:
  - a concave (L-shaped) site — no real site is a clean rectangle;
  - a U-shaped courtyard building and an O-shaped enclosed-courtyard building;
  - an obstacle building that corridors must route *around*, not through;
  - multiple typed building entrances (public / service / residential / courtyard);
  - strict fire access that checks the deepest interior point and every courtyard.
"""
import json
from pathlib import Path

md = lambda s: {"cell_type": "markdown", "metadata": {}, "source": s.splitlines(keepends=True)}
code = lambda s: {"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": s.strip("\n").splitlines(keepends=True)}

cells = []

cells.append(md("""# Phase 5 — Circulation, Access & Fire Safety (complex sites)

Access placement should explain *why* a building sits where it sits. This notebook
exercises `agent/tools/circulation.py` on **non-rectangular sites and courtyard
buildings**, not toy boxes:

1. **`propose_site_entries`** — public entries on the main road (one, or several on
   a long frontage) + a private/service entry on a secondary side.
2. **`route_internal_circulation`** — drivable corridors routed with an
   *obstacle-aware visibility graph*: they bend **around** other buildings and follow
   the free space of a concave site instead of cutting through anything.
3. **`detect_courtyards` / `building_entrance_orientation`** — every building gets
   *typed* entrances: a public/main entrance, a service entrance, a quiet
   residential entrance, and one courtyard entrance per detected courtyard.
4. **`check_fire_access`** — every building within 50 m of a ≥ 4 m drivable path.
   `strict=True` also checks the **deepest interior point** and each **courtyard's**
   reachability — the cases the nearest-wall test silently passes.

Sections: (a) entries, (b) obstacle-aware network, (c) typed entrances,
(d) strict fire access on a courtyard building, (e) a deliberately failing layout."""))

cells.append(code("""
from __future__ import annotations
import sys
from pathlib import Path

workspace_root = Path.cwd().resolve()
candidate_roots = (
    workspace_root,
    workspace_root.parent,
    workspace_root / 'team_04',
    workspace_root.parent / 'team_04',
)
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

# Embed figures so they render inline in VS Code / Jupyter (and survive a
# pre-executed notebook). 'plotly_mimetype' is what VS Code renders natively;
# 'notebook_connected' keeps the classic-notebook path working too.
pio.renderers.default = 'plotly_mimetype+notebook_connected'

from agent.tools.circulation import (
    DEFAULT_PATH_WIDTH_M, MIN_PATH_WIDTH_M, MAX_FIRE_DISTANCE_M,
    detect_courtyards,
    propose_site_entries,
    route_internal_circulation,
    building_entrance_orientation,
    check_fire_access,
)

print('Circulation tool imported OK')
print(f'  DEFAULT_PATH_WIDTH_M={DEFAULT_PATH_WIDTH_M} m  '
      f'MIN_PATH_WIDTH_M={MIN_PATH_WIDTH_M} m  MAX_FIRE_DISTANCE_M={MAX_FIRE_DISTANCE_M} m')
"""))

cells.append(md("""## A concave (L-shaped) site with real building footprints

The site is **L-shaped** — the bottom-right quadrant is cut out, so corridors must
respect a re-entrant boundary. Three buildings sit on it:

* **`block`** — a long slab placed between the entry and the rest of the site; the
  network has to drive *around* it.
* **`court_U`** — a **U-shaped** building with an open courtyard.
* **`court_O`** — an **O-shaped** building with a true enclosed courtyard (a hole)."""))

cells.append(code("""
# L-shaped site: bottom-right notch removed.
SITE_BOUNDARY = [
    [0.0,   0.0,   0.0],
    [110.0, 0.0,   0.0],
    [110.0, 45.0,  0.0],
    [55.0,  45.0,  0.0],
    [55.0,  95.0,  0.0],
    [0.0,   95.0,  0.0],
    [0.0,   0.0,   0.0],
]

SITE_MODEL = {
    'boundary': SITE_BOUNDARY,
    'sides': [
        {'side_index': 0, 'start': [0.0, 0.0],   'end': [110.0, 0.0],
         'adjacent_road': {'name': 'Main Street', 'hierarchy': 'main', 'width_m': 20.0}},
        {'side_index': 1, 'start': [110.0, 0.0],  'end': [110.0, 45.0], 'adjacent_road': None},
        {'side_index': 2, 'start': [110.0, 45.0], 'end': [55.0, 45.0],  'adjacent_road': None},
        {'side_index': 3, 'start': [55.0, 45.0],  'end': [55.0, 95.0],  'adjacent_road': None},
        {'side_index': 4, 'start': [55.0, 95.0],  'end': [0.0, 95.0],
         'adjacent_road': {'name': 'Service Lane', 'hierarchy': 'secondary', 'width_m': 6.0}},
        {'side_index': 5, 'start': [0.0, 95.0],   'end': [0.0, 0.0], 'adjacent_road': None},
    ],
    'roads': {'main_road_side_index': 0, 'main_road': {'name': 'Main Street', 'width_m': 20.0}},
}

# A wall-like slab that sits between the entry (bottom) and the upper-left
# courtyard building, leaving a gap on the right — the network must detour
# around its right end to reach anything above it on the left.
BLOCK = {
    'building_id': 'block', 'label': 'Slab (obstacle)', 'storeys': 4,
    'boundary': [[4.0, 42.0, 0.0], [40.0, 42.0, 0.0], [40.0, 50.0, 0.0], [4.0, 50.0, 0.0]],
}

# U-shaped courtyard building (open court facing +y).
COURT_U = {
    'building_id': 'court_U', 'label': 'U-court', 'storeys': 6,
    'boundary': [
        [62.0, 8.0, 0.0], [100.0, 8.0, 0.0], [100.0, 38.0, 0.0], [86.0, 38.0, 0.0],
        [86.0, 20.0, 0.0], [76.0, 20.0, 0.0], [76.0, 38.0, 0.0], [62.0, 38.0, 0.0],
    ],
}

# O-shaped building with a true enclosed courtyard (a hole).
COURT_O = {
    'building_id': 'court_O', 'label': 'O-court', 'storeys': 7,
    'boundary': [[8.0, 55.0, 0.0], [46.0, 55.0, 0.0], [46.0, 90.0, 0.0], [8.0, 90.0, 0.0]],
    'holes': [[[18.0, 64.0], [36.0, 64.0], [36.0, 81.0], [18.0, 81.0]]],
}

BUILDINGS = [BLOCK, COURT_U, COURT_O]
for b in BUILDINGS:
    courts = detect_courtyards(b['boundary'], b.get('holes'))
    print(f"{b['building_id']:8s}: {len(courts)} courtyard(s) -> "
          f"{[(c['type'], round(c['area_sqm'])) for c in courts]}")
"""))

cells.append(md("""## Plot helpers

Building **courtyards** are drawn as light voids; **site entries** are big triangles;
**building entrances** are small arrows coloured by role (public/service/
residential/courtyard)."""))

cells.append(code("""
ROLE_COLORS = {
    'public': '#dc2626', 'service': '#2563eb',
    'residential': '#16a34a', 'courtyard': '#9333ea',
}

def _xy(pts):
    xs = [p[0] for p in pts] + [pts[0][0]]
    ys = [p[1] for p in pts] + [pts[0][1]]
    return xs, ys

def base_fig(title):
    fig = go.Figure()
    xs, ys = _xy(SITE_BOUNDARY)
    fig.add_trace(go.Scatter(x=xs, y=ys, name='Site boundary',
                             mode='lines', line=dict(color='#1d4ed8', width=3),
                             showlegend=True, hoverinfo='skip'))
    fig.update_layout(
        title=title,
        yaxis=dict(scaleanchor='x', scaleratio=1, visible=False),
        xaxis=dict(visible=False),
        margin=dict(l=0, r=0, t=40, b=0), height=620,
        plot_bgcolor='#f0f4ff', paper_bgcolor='#f0f4ff',
        legend=dict(x=1.02, y=1, bgcolor='white', bordercolor='#ccc', borderwidth=1),
    )
    return fig

def add_buildings(fig, buildings, fire=None):
    fire_by_id = {b['building_id']: b for b in (fire or {}).get('buildings', [])}
    palette = ['rgba(15,118,110,0.40)', 'rgba(124,58,237,0.40)', 'rgba(180,83,9,0.40)']
    for i, b in enumerate(buildings):
        xs, ys = _xy(b['boundary'])
        passed = fire_by_id.get(b['building_id'], {}).get('pass')
        if passed is True:
            fill, line = 'rgba(34,197,94,0.40)', '#15803d'
        elif passed is False:
            fill, line = 'rgba(239,68,68,0.40)', '#b91c1c'
        else:
            fill, line = palette[i % len(palette)], palette[i % len(palette)].replace('0.40', '1')
        fig.add_trace(go.Scatter(x=xs, y=ys, name=b.get('label', b['building_id']),
                                 mode='lines', fill='toself', fillcolor=fill,
                                 line=dict(color=line, width=2), showlegend=True, hoverinfo='skip'))
        # Punch out enclosed courtyards (holes) so they read as voids.
        for hole in b.get('holes', []) or []:
            hxs, hys = _xy(hole)
            fig.add_trace(go.Scatter(x=hxs, y=hys, mode='lines', fill='toself',
                                     fillcolor='#f0f4ff', line=dict(color=line, width=1, dash='dot'),
                                     showlegend=False, hoverinfo='skip'))
        cx = sum(p[0] for p in b['boundary']) / len(b['boundary'])
        cy = sum(p[1] for p in b['boundary']) / len(b['boundary'])
        label = b.get('label', b['building_id'])
        if b['building_id'] in fire_by_id:
            fb = fire_by_id[b['building_id']]
            label += f"<br>near {fb['distance_m']}m  deep {fb['deepest_point_distance_m']}m"
        fig.add_annotation(x=cx, y=cy, text=label, showarrow=False, font=dict(size=10, color='#111'))

def add_circulation(fig, circ):
    for p in circ.get('paths', []):
        if p['buffered_boundary']:
            xs, ys = _xy(p['buffered_boundary'])
            fig.add_trace(go.Scatter(x=xs, y=ys, mode='lines', fill='toself',
                                     fillcolor='rgba(100,116,139,0.30)',
                                     line=dict(color='rgba(100,116,139,0.0)', width=0),
                                     showlegend=False, hoverinfo='skip'))
        px = [pt[0] for pt in p['polyline']]
        py = [pt[1] for pt in p['polyline']]
        fig.add_trace(go.Scatter(x=px, y=py, name=f"{p['path_id']} -> {p['serves']}",
                                 mode='lines', line=dict(color='#334155', width=2),
                                 showlegend=False, hoverinfo='skip'))

def add_entries(fig, entries):
    seen = set()
    for e in entries['entries']:
        color = '#dc2626' if e['type'] == 'public' else '#0891b2'
        show = e['type'] not in seen
        seen.add(e['type'])
        fig.add_trace(go.Scatter(x=[e['point'][0]], y=[e['point'][1]],
                                 name=f"{e['type']} site entry",
                                 mode='markers', marker=dict(size=16, color=color, symbol='triangle-up'),
                                 showlegend=show, hoverinfo='skip'))

def add_entrances(fig, orient):
    shown = set()
    for b in orient['buildings']:
        for e in b['entrances']:
            ex, ey, _ = e['point']
            dx, dy = e['direction']
            color = ROLE_COLORS.get(e['role'], '#111')
            fig.add_annotation(x=ex + dx * 7, y=ey + dy * 7, ax=ex, ay=ey,
                               xref='x', yref='y', axref='x', ayref='y',
                               showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2,
                               arrowcolor=color)
            if e['role'] not in shown:
                shown.add(e['role'])
                fig.add_trace(go.Scatter(x=[ex], y=[ey], mode='markers',
                                         name=f"{e['role']} entrance",
                                         marker=dict(size=9, color=color, symbol='circle'),
                                         showlegend=True, hoverinfo='skip'))

print('Helpers defined')
"""))

cells.append(md("""## (a) Site entries — public on the main road, service on the secondary side"""))

cells.append(code("""
entries = propose_site_entries(SITE_MODEL)
print(entries['summary'])
for e in entries['entries']:
    print(f"  {e['entry_id']:16s} type={e['type']:8s} side={e['side_index']} "
          f"point={e['point'][:2]} road={e['road_name']}")

fig = base_fig('(a) Site entries on a concave L-site')
add_buildings(fig, BUILDINGS)
add_entries(fig, entries)
fig.show()
"""))

cells.append(md("""## (b) Obstacle-aware circulation — corridors bend around the slab

The slab (`block`) sits between the entry and the courtyard buildings. The
visibility-graph router drives **around** it; `routed_around > 0` flags every
corridor that had to detour."""))

cells.append(code("""
circ = route_internal_circulation(SITE_MODEL, entries, BUILDINGS, None)
print('Circulation:', circ['summary'])
for p in circ['paths']:
    print(f"  {p['path_id']:8s} -> {p['serves']:8s} {p['length_m']:6.1f} m "
          f"vertices={len(p['polyline'])} routed_around={p['routed_around']}")

fig = base_fig('(b) Obstacle-aware corridors (bend around the slab)')
add_circulation(fig, circ)
add_buildings(fig, BUILDINGS)
add_entries(fig, entries)
fig.show()
"""))

cells.append(md("""## (c) Typed building entrances — public / service / residential / courtyard

Each building now gets several entrances by role. The U- and O-court buildings get a
**courtyard** entrance facing into the void; the residential entrance is the quiet one
(courtyard-facing when a court exists, otherwise opposite the public door)."""))

cells.append(code("""
orient = building_entrance_orientation(BUILDINGS, entries, circ)
print(orient['summary'])
for b in orient['buildings']:
    roles = ', '.join(f"{e['role']}->{e['faces']}" for e in b['entrances'])
    print(f"  {b['building_id']:8s} ({len(b['courtyards'])} court): {roles}")

fig = base_fig('(c) Typed entrances (arrows coloured by role)')
add_circulation(fig, circ)
add_buildings(fig, BUILDINGS)
add_entries(fig, entries)
add_entrances(fig, orient)
fig.show()
"""))

cells.append(md("""## (d) Fire access — loose vs strict

`constraint_value = distance − max_distance` (≤ 0 ⇒ the nearest wall is reachable) is
unchanged. **Loose** mode checks only that nearest wall. **Strict** mode also requires
the *deepest interior point* and every *courtyard* to be serviceable — so a building
whose outer wall is reachable but whose enclosed court is not will pass loose and
**fail strict**."""))

cells.append(code("""
loose  = check_fire_access(BUILDINGS, circ, max_distance=MAX_FIRE_DISTANCE_M)
strict = check_fire_access(BUILDINGS, circ, max_distance=MAX_FIRE_DISTANCE_M, strict=True)
print('loose :', loose['summary'],  '| all_pass =', loose['all_pass'])
print('strict:', strict['summary'], '| all_pass =', strict['all_pass'])
for lb, sb in zip(loose['buildings'], strict['buildings']):
    courts = ','.join(f"{c['type']}:{'ok' if c['reachable'] else 'X'}" for c in sb['courtyards']) or '-'
    print(f"  {lb['building_id']:8s} near={lb['distance_m']:5}m deep={sb['deepest_point_distance_m']:5}m "
          f"courts=[{courts}]  loose_pass={lb['pass']} strict_pass={sb['pass']}")

fig = base_fig('(d) Strict fire access — green pass / red fail')
add_circulation(fig, circ)
add_buildings(fig, BUILDINGS, fire=strict)
add_entries(fig, entries)
fig.show()
"""))

cells.append(md("""## (d2) Strict mode catches an **unreachable enclosed courtyard**

This is the case the nearest-wall test silently passes. A large **O-court** block sits
on a wide plaza; the perimeter road touches its outer wall (`distance ≈ 0`, so the
loose check and the optimizer's `G ≤ 0` constraint are happy). But its enclosed
courtyard sits ~60 m inside, beyond hose reach — **strict mode fails it** and the
courtyard is flagged unreachable. Compare the loose-green vs strict-red colouring."""))

cells.append(code("""
PLAZA = [[0,0,0],[170,0,0],[170,150,0],[0,150,0],[0,0,0]]
PLAZA_MODEL = {'boundary': PLAZA, 'roads': {'main_road_side_index': 0}}

# Big ring building: outer 130 x 120, a 60 x 60 enclosed courtyard in the middle.
BIG_O = {
    'building_id': 'big_O', 'label': 'Large O-court', 'storeys': 8,
    'boundary': [[20,15,0],[150,15,0],[150,135,0],[20,135,0]],
    'holes': [[[55,50],[115,50],[115,100],[55,100]]],
}

plaza_ent  = propose_site_entries(PLAZA_MODEL)
plaza_circ = route_internal_circulation(PLAZA_MODEL, plaza_ent, [BIG_O], None)
loose_o  = check_fire_access([BIG_O], plaza_circ, strict=False)
strict_o = check_fire_access([BIG_O], plaza_circ, strict=True)

lb, sb = loose_o['buildings'][0], strict_o['buildings'][0]
print(f"outer-wall distance = {lb['distance_m']} m  -> within_reach={lb['within_reach']}  G={lb['constraint_value']}")
print(f"deepest interior    = {sb['deepest_point_distance_m']} m")
print(f"courtyard reachable = {sb['courtyards'][0]['reachable']} "
      f"(court centre {sb['courtyards'][0]['distance_m']} m from a road)")
print(f"loose pass = {lb['pass']}   |   strict pass = {sb['pass']}")

def plaza_fig(title, fire):
    fig = go.Figure()
    xs, ys = _xy(PLAZA)
    fig.add_trace(go.Scatter(x=xs, y=ys, name='Site', mode='lines',
                             line=dict(color='#1d4ed8', width=3), hoverinfo='skip'))
    add_circulation(fig, plaza_circ)
    add_buildings(fig, [BIG_O], fire=fire)
    add_entries(fig, plaza_ent)
    # Mark the unreachable courtyard centre.
    c = sb['courtyards'][0]['centroid']
    ok = sb['courtyards'][0]['reachable']
    fig.add_trace(go.Scatter(x=[c[0]], y=[c[1]], mode='markers+text',
                             text=['court OK' if ok else 'court UNREACHABLE'],
                             textposition='top center',
                             marker=dict(size=14, color='#15803d' if ok else '#b91c1c', symbol='x'),
                             showlegend=False, hoverinfo='skip'))
    fig.update_layout(title=title, yaxis=dict(scaleanchor='x', scaleratio=1, visible=False),
                      xaxis=dict(visible=False), margin=dict(l=0, r=0, t=40, b=0), height=560,
                      plot_bgcolor='#f0f4ff', paper_bgcolor='#f0f4ff',
                      legend=dict(x=1.02, y=1, bgcolor='white', bordercolor='#ccc', borderwidth=1))
    return fig

plaza_fig('(d2) LOOSE — outer wall reachable, building passes (green)', loose_o).show()
plaza_fig('(d2) STRICT — enclosed courtyard unreachable, building fails (red)', strict_o).show()
"""))

cells.append(md("""## (e) A deliberately failing layout — the constraint rejects it

A large site with a remote building that no corridor reaches: its
`constraint_value > 0`, so the hard fire-access constraint **rejects** the layout —
the same `G ≤ 0` signal the optimizer consumes."""))

cells.append(code("""
BIG_BOUNDARY = [[0,0,0],[200,0,0],[200,200,0],[0,200,0],[0,0,0]]
BIG_MODEL = {'boundary': BIG_BOUNDARY, 'roads': {'main_road_side_index': 0}}
NEAR = {'building_id': 'near', 'label': 'Near (served)',
        'boundary': [[15,15,0],[45,15,0],[45,40,0],[15,40,0]]}
FAR  = {'building_id': 'far', 'label': 'Far (unreachable)',
        'boundary': [[155,155,0],[190,155,0],[190,190,0],[155,190,0]]}

big_entries = propose_site_entries(BIG_MODEL)
big_circ = route_internal_circulation(BIG_MODEL, big_entries, [NEAR], None)  # only serves NEAR
big_fire = check_fire_access([NEAR, FAR], big_circ, max_distance=MAX_FIRE_DISTANCE_M)
print(big_fire['summary'], '| all_pass =', big_fire['all_pass'])
for b in big_fire['buildings']:
    print(f"  {b['building_id']:6s}: d={b['distance_m']} m  G={b['constraint_value']}  pass={b['pass']}")

fig = go.Figure()
xs, ys = _xy(BIG_BOUNDARY)
fig.add_trace(go.Scatter(x=xs, y=ys, name='Site', mode='lines',
                         line=dict(color='#1d4ed8', width=3), hoverinfo='skip'))
add_circulation(fig, big_circ)
add_buildings(fig, [NEAR, FAR], fire=big_fire)
add_entries(fig, big_entries)
fig.update_layout(title='(e) Fire-access FAIL — far building unreachable (red)',
                  yaxis=dict(scaleanchor='x', scaleratio=1, visible=False),
                  xaxis=dict(visible=False), margin=dict(l=0, r=0, t=40, b=0), height=560,
                  plot_bgcolor='#f0f4ff', paper_bgcolor='#f0f4ff',
                  legend=dict(x=1.02, y=1, bgcolor='white', bordercolor='#ccc', borderwidth=1))
fig.show()
"""))

cells.append(md("""## Summary

- **Concave site:** entries and corridors respect an L-shaped boundary, not a box.
- **Obstacle-aware routing:** corridors bend *around* the slab (`routed_around > 0`)
  and never cut through a neighbouring footprint — the old straight-L logic did.
- **Typed entrances:** public, service, residential and courtyard doors per building,
  with courtyard entrances facing into auto/explicitly detected courts.
- **Courtyard-aware fire access:** `strict=True` adds the deepest-interior-point reach
  and per-courtyard reachability, catching the enclosed-court case the nearest-wall
  test silently passes — while keeping the optimizer's `G = d − max_distance`
  constraint unchanged."""))

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
