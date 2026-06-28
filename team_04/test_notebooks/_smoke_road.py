"""Smoke-test for the road context notebook logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ['MPLBACKEND'] = 'Agg'

from team_04.agent.tools.road_context import analyze_roads
from team_04.agent.tools.site_model import build_site_model
from team_04.agent.tools.site_grid import derive_site_grid
from team_04.agent.tools.site_setback import compute_buildable_zone

SITE = [[0,0,0],[130,18,0],[150,92,0],[62,128,0],[-14,74,0],[0,0,0]]
MAIN_ROAD = {'type':'road','centerline':[[-20,-15],[160,25]],'width_m':20.0,'hierarchy':'main','name':'Main Street'}
SECONDARY = {'type':'road','centerline':[[170,0],[175,110]],'width_m':10.0,'hierarchy':'secondary','name':'East Lane'}
PATH = {'type':'road','centerline':[[-20,90],[75,145]],'width_m':4.0,'hierarchy':'path','name':'West Path'}

model = build_site_model(SITE, {'site_objects':[MAIN_ROAD,SECONDARY,PATH],'default_setback':5.0})
rr = model['roads']
assert rr['available'], f"roads not available: {rr}"
assert rr['main_road']['name'] == 'Main Street', rr['main_road']
print('main road:', rr['main_road']['name'], '| side', rr['main_road_side_index'])
print('edge_road_widths:', rr['edge_road_widths'])

grid_w = derive_site_grid(model, spacing=12.0)
assert grid_w['alignment_side_index'] == rr['main_road_side_index']
print('grid aligns to main-road side:', grid_w['alignment_side_index'])

model2 = build_site_model(SITE, {'default_setback':5.0})
grid_no = derive_site_grid(model2, spacing=12.0)
assert model2['roads']['ambiguity'] == 'no_road_data'
print('no-road grid falls back to side:', grid_no['alignment_side_index'])

bz_road = compute_buildable_zone(SITE, default_setback=5.0, edge_road_widths=rr['edge_road_widths'])
bz_none = compute_buildable_zone(SITE, default_setback=5.0)
assert bz_road.area < bz_none.area, "road setbacks should reduce buildable area"
print('buildable with roads:', round(bz_road.area), 'm2')
print('buildable without:   ', round(bz_none.area), 'm2')

for s in model['sides']:
    adj = s.get('adjacent_road')
    print(f"  side {s['edge_index']} ({s['cardinal_hint']}): {adj['name'] if adj else 'none'}")

print('ALL NOTEBOOK CELLS OK')
