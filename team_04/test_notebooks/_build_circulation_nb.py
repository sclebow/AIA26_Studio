"""Generator for test_circulation_fire.ipynb (Phase 5).

Run once to (re)emit the notebook JSON. Kept in the repo so the notebook is
reproducible and reviewable as code. Not a test; not imported by anything.
"""
import json
from pathlib import Path

md = lambda s: {"cell_type": "markdown", "metadata": {}, "source": s.splitlines(keepends=True)}
code = lambda s: {"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": s.strip("\n").splitlines(keepends=True)}

cells = []

cells.append(md("""# Phase 5 — Circulation, Access & Fire Safety

Access placement should explain *why* a building sits where it sits. This notebook
exercises `agent/tools/circulation.py`:

1. **`propose_site_entries`** — a public entry on the main-road side, an optional
   private/service entry on a secondary side.
2. **`route_internal_circulation`** — drivable L-shaped corridors from the entry to
   every building and parking zone.
3. **`building_entrance_orientation`** — each building's entrance faces the nearest path.
4. **`check_fire_access`** — every building must be within 50 m of a ≥ 4 m drivable
   path. This is the hard constraint `G ≤ 0` for the optimizer.

Sections: (a) entries, (b) routed network + parking, (c) fire-access pass colouring,
(d) a deliberately failing layout the constraint rejects."""))

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

from agent.tools.circulation import (
    DEFAULT_PATH_WIDTH_M, MIN_PATH_WIDTH_M, MAX_FIRE_DISTANCE_M,
    propose_site_entries,
    route_internal_circulation,
    building_entrance_orientation,
    check_fire_access,
)
from agent.tools.parking import compute_building_demand, allocate_parking_zones

print('Circulation tool imported OK')
print(f'  DEFAULT_PATH_WIDTH_M={DEFAULT_PATH_WIDTH_M} m  '
      f'MIN_PATH_WIDTH_M={MIN_PATH_WIDTH_M} m  MAX_FIRE_DISTANCE_M={MAX_FIRE_DISTANCE_M} m')
"""))

cells.append(md("""## Site, roads and building definitions

A 90 × 60 m site. South side (index 0) is the **main road**; the north side
(index 2) carries a **secondary** road, so a private/service entry can land there."""))

cells.append(code("""
SITE_BOUNDARY = [
    [0.0,  0.0,  0.0],
    [90.0, 0.0,  0.0],
    [90.0, 60.0, 0.0],
    [0.0,  60.0, 0.0],
    [0.0,  0.0,  0.0],
]

SITE_MODEL = {
    'boundary': SITE_BOUNDARY,
    'sides': [
        {'side_index': 0, 'start': [0.0,  0.0],  'end': [90.0, 0.0],
         'adjacent_road': {'name': 'Main Street', 'hierarchy': 'main', 'width_m': 20.0}},
        {'side_index': 1, 'start': [90.0, 0.0],  'end': [90.0, 60.0], 'adjacent_road': None},
        {'side_index': 2, 'start': [90.0, 60.0], 'end': [0.0,  60.0],
         'adjacent_road': {'name': 'Back Lane', 'hierarchy': 'secondary', 'width_m': 8.0}},
        {'side_index': 3, 'start': [0.0,  60.0], 'end': [0.0,  0.0], 'adjacent_road': None},
    ],
    'roads': {'main_road_side_index': 0, 'main_road': {'name': 'Main Street', 'width_m': 20.0}},
}

BUILDING_A = {
    'building_id': 'bld_A', 'label': 'Building A', 'storeys': 5,
    'boundary': [[10.0, 24.0, 0.0], [38.0, 24.0, 0.0], [38.0, 46.0, 0.0], [10.0, 46.0, 0.0]],
}
BUILDING_B = {
    'building_id': 'bld_B', 'label': 'Building B', 'storeys': 4,
    'boundary': [[54.0, 24.0, 0.0], [82.0, 24.0, 0.0], [82.0, 46.0, 0.0], [54.0, 46.0, 0.0]],
}
BUILDINGS = [BUILDING_A, BUILDING_B]
print('Site area:', 90 * 60, 'm2 ;  buildings:', len(BUILDINGS))
"""))

cells.append(md("""## Plot helpers"""))

cells.append(code("""
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
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor='#f0f4ff', paper_bgcolor='#f0f4ff',
        legend=dict(x=1.02, y=1, bgcolor='white', bordercolor='#ccc', borderwidth=1),
    )
    return fig

def add_buildings(fig, buildings, fire=None):
    fire_by_id = {b['building_id']: b for b in (fire or {}).get('buildings', [])}
    colors = ['rgba(15,118,110,0.45)', 'rgba(124,58,237,0.45)', 'rgba(180,83,9,0.45)']
    for i, b in enumerate(buildings):
        xs, ys = _xy(b['boundary'])
        passed = fire_by_id.get(b['building_id'], {}).get('pass')
        if passed is True:
            fill, line = 'rgba(34,197,94,0.40)', '#15803d'
        elif passed is False:
            fill, line = 'rgba(239,68,68,0.40)', '#b91c1c'
        else:
            fill, line = colors[i % len(colors)], colors[i % len(colors)].replace('0.45', '1')
        fig.add_trace(go.Scatter(x=xs, y=ys, name=b.get('label', b['building_id']),
                                 mode='lines', fill='toself', fillcolor=fill,
                                 line=dict(color=line, width=2), showlegend=True, hoverinfo='skip'))
        cx = sum(p[0] for p in b['boundary']) / len(b['boundary'])
        cy = sum(p[1] for p in b['boundary']) / len(b['boundary'])
        label = b.get('label', b['building_id'])
        if b['building_id'] in fire_by_id:
            fb = fire_by_id[b['building_id']]
            label += f"<br>{fb['distance_m']} m  G={fb['constraint_value']}"
        fig.add_annotation(x=cx, y=cy, text=label, showarrow=False,
                           font=dict(size=10, color='#111'))

def add_parking(fig, parking):
    for z in parking.get('zones', []):
        xs, ys = _xy(z['boundary'])
        fig.add_trace(go.Scatter(x=xs, y=ys, name=f"{z['zone_id']} ({z['stalls_allocated']} stalls)",
                                 mode='lines', fill='toself', fillcolor='rgba(234,179,8,0.25)',
                                 line=dict(color='#b45309', width=1, dash='dot'),
                                 showlegend=True, hoverinfo='skip'))

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
    for e in entries['entries']:
        color = '#dc2626' if e['type'] == 'public' else '#0891b2'
        fig.add_trace(go.Scatter(x=[e['point'][0]], y=[e['point'][1]],
                                 name=f"{e['type']} entry (side {e['side_index']})",
                                 mode='markers', marker=dict(size=14, color=color, symbol='triangle-up'),
                                 showlegend=True, hoverinfo='skip'))

print('Helpers defined')
"""))

cells.append(md("""## (a) Site entries — public on the main road, private on the secondary side"""))

cells.append(code("""
entries = propose_site_entries(SITE_MODEL)
print(entries['summary'])
for e in entries['entries']:
    print(f"  {e['entry_id']:16s} type={e['type']:8s} side={e['side_index']} "
          f"point={e['point'][:2]} road={e['road_name']}")

fig = base_fig('(a) Site entries')
add_buildings(fig, BUILDINGS)
add_entries(fig, entries)
fig.show()
"""))

cells.append(md("""## (b) Routed circulation network + parking

Parking demand drives the allocation (Phase 4); circulation then routes corridors
from the public entry to each building and parking zone."""))

cells.append(code("""
demand = compute_building_demand(BUILDINGS)
parking = allocate_parking_zones(SITE_MODEL, BUILDINGS, demand)
print('Parking:', parking['summary'])

circ = route_internal_circulation(SITE_MODEL, entries, BUILDINGS, parking)
print('Circulation:', circ['summary'])
for p in circ['paths']:
    print(f"  {p['path_id']:8s} {p['target_type']:8s} -> {p['serves']:14s} {p['length_m']:6.1f} m")

fig = base_fig('(b) Circulation network + parking')
add_parking(fig, parking)
add_circulation(fig, circ)
add_buildings(fig, BUILDINGS)
add_entries(fig, entries)
fig.show()
"""))

cells.append(md("""## (b2) Entrance orientation — entrances face the nearest path"""))

cells.append(code("""
orient = building_entrance_orientation(BUILDINGS, entries, circ)
print(orient['summary'])
for b in orient['buildings']:
    print(f"  {b['building_id']}: faces {b['faces']}  dir={b['entrance_direction']}  d={b['distance_m']} m")

fig = base_fig('(b2) Entrance orientation (arrows point toward access)')
add_circulation(fig, circ)
add_buildings(fig, BUILDINGS)
for b in orient['buildings']:
    if not b['entrance_point']:
        continue
    ex, ey, _ = b['entrance_point']
    dx, dy = b['entrance_direction']
    fig.add_annotation(x=ex + dx * 8, y=ey + dy * 8, ax=ex, ay=ey,
                       xref='x', yref='y', axref='x', ayref='y',
                       showarrow=True, arrowhead=2, arrowsize=1.3, arrowwidth=2,
                       arrowcolor='#dc2626')
add_entries(fig, entries)
fig.show()
"""))

cells.append(md("""## (c) Fire access — both buildings within reach pass (green)

`constraint_value = distance − max_distance`; ≤ 0 means the building is reachable."""))

cells.append(code("""
fire = check_fire_access(BUILDINGS, circ, max_distance=MAX_FIRE_DISTANCE_M)
print(fire['summary'], '| all_pass =', fire['all_pass'], '| max G =', fire['max_constraint_value'])
for b in fire['buildings']:
    print(f"  {b['building_id']}: d={b['distance_m']} m  ratio={b['reachable_perimeter_ratio']}  "
          f"G={b['constraint_value']}  pass={b['pass']}")

fig = base_fig('(c) Fire access — PASS (green) within 50 m of a drivable path')
add_circulation(fig, circ)
add_buildings(fig, BUILDINGS, fire=fire)
add_entries(fig, entries)
fig.show()
"""))

cells.append(md("""## (d) A deliberately failing layout — the constraint rejects it

A large site with a remote building that no corridor reaches. The far building's
`constraint_value > 0`, so the fire-access constraint **rejects** the layout."""))

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
fig.update_layout(title='(d) Fire-access FAIL — far building unreachable (red)',
                  yaxis=dict(scaleanchor='x', scaleratio=1, visible=False),
                  xaxis=dict(visible=False), margin=dict(l=0, r=0, t=40, b=0),
                  plot_bgcolor='#f0f4ff', paper_bgcolor='#f0f4ff',
                  legend=dict(x=1.02, y=1, bgcolor='white', bordercolor='#ccc', borderwidth=1))
fig.show()
"""))

cells.append(md("""## Summary

- **Entries** land deterministically on the main-road side (public) and a secondary
  side (private/service), driven by the Phase 2 road tags.
- **Circulation** routes drivable L-shaped corridors from the public entry to every
  building and parking zone; corridor polygons are returned as occupied obstacles.
- **Entrance orientation** points each building's entrance toward the nearest path.
- **Fire access** is the hard constraint `G ≤ 0`: section (c) passes (both reachable),
  section (d) fails (the far building's `G > 0`), so the optimizer rejects it."""))

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
