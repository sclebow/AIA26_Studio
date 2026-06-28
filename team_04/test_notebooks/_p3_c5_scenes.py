# ============================================================
# Three synthetic urban scenes — rich road networks
# All use 30 m x 40 m site at centre (0,0) → x: -15..15, y: -20..20
# ============================================================
# Road hierarchy widths per scene:
#   Scene 1 (crossroads corner)  : 5 m + 12 m + 20 m
#   Scene 2 (T-junction terminal): 5 m + 12 m + 28 m
#   Scene 3 (Y-junction complex) : 4 m + 15 m + 30 m diagonal
# ============================================================

SITE_BDRY = [[-15,-20],[15,-20],[15,20],[-15,20],[-15,-20]]

# ── Scene 1: Crossroads Corner (Barcelona / Paris style) ──────────────────────
# Site sits at the corner of a 20 m main road (south) and a 12 m secondary (west).
# The H-building is the correct typology here.
SCENE_1 = {
    'name'    : 'SCENE 1  |  Crossroads Corner  (H-Building)',
    'junction': 'crossroads',
    'roads'   : [
        # Main road E-W (20 m wide): 12 m south of site bottom
        {'type':'road','centerline':[[-140,-32],[140,-32]],
         'width_m':20.0,'hierarchy':'main','name':'Main Boulevard'},
        # Secondary road N-S W (12 m): 13 m west of site left edge
        {'type':'road','centerline':[[-28,-140],[-28,140]],
         'width_m':12.0,'hierarchy':'secondary','name':'West Street'},
        # Secondary road N-S E (12 m): 17 m east of site right edge
        {'type':'road','centerline':[[32,-140],[32,140]],
         'width_m':12.0,'hierarchy':'secondary','name':'East Street'},
        # Secondary road E-W N (12 m): 18 m north of site top
        {'type':'road','centerline':[[-140,38],[140,38]],
         'width_m':12.0,'hierarchy':'secondary','name':'Upper Street'},
        # Service lane just south of site (5 m): parallel to main road
        {'type':'road','centerline':[[-140,-22],[140,-22]],
         'width_m':5.0,'hierarchy':'path','name':'Service Lane'},
        # Narrow alley just west of site (4 m)
        {'type':'road','centerline':[[-17,-140],[-17,140]],
         'width_m':4.5,'hierarchy':'path','name':'West Alley'},
    ],
    'intersections': [
        {'point':[-28,-32],'degree':4,'type':'crossroads'},
        {'point':[32,-32], 'degree':4,'type':'crossroads'},
        {'point':[-28,38], 'degree':4,'type':'crossroads'},
        {'point':[32,38],  'degree':4,'type':'crossroads'},
        {'point':[-17,-32],'degree':3,'type':'t_junction'},
        {'point':[-17,38], 'degree':3,'type':'t_junction'},
        {'point':[-28,-22],'degree':3,'type':'t_junction'},
        {'point':[32,-22], 'degree':3,'type':'t_junction'},
    ],
}

# ── Scene 2: T-Junction Terminal (London / Bloomsbury style) ──────────────────
# Site sits at the END of a secondary street that terminates on a main boulevard.
# The building forms a visual terminus. Wide slab faces the view axis.
SCENE_2 = {
    'name'    : 'SCENE 2  |  T-Junction Terminal  (Wide Slab)',
    'junction': 't_junction',
    'roads'   : [
        # Main boulevard E-W (28 m wide): 18 m south of site bottom
        {'type':'road','centerline':[[-160,-38],[160,-38]],
         'width_m':28.0,'hierarchy':'main','name':'Grand Boulevard'},
        # Terminus street N-S (12 m): ENDS at the boulevard, runs away from site south
        {'type':'road','centerline':[[0,-38],[0,-130]],
         'width_m':12.0,'hierarchy':'secondary','name':'Terminus Road'},
        # Secondary street E-W (12 m): north of site
        {'type':'road','centerline':[[-160,42],[160,42]],
         'width_m':12.0,'hierarchy':'secondary','name':'North Cross Street'},
        # Secondary N-S E (12 m)
        {'type':'road','centerline':[[45,-160],[45,160]],
         'width_m':12.0,'hierarchy':'secondary','name':'East Road'},
        # Secondary N-S W (12 m)
        {'type':'road','centerline':[[-45,-160],[-45,160]],
         'width_m':12.0,'hierarchy':'secondary','name':'West Road'},
        # Service alley W of site
        {'type':'road','centerline':[[-18,-160],[-18,160]],
         'width_m':4.5,'hierarchy':'path','name':'West Alley'},
        # Service alley E of site
        {'type':'road','centerline':[[18,-160],[18,160]],
         'width_m':4.5,'hierarchy':'path','name':'East Alley'},
    ],
    'intersections': [
        # T-junction: where terminus road meets the boulevard
        {'point':[0,-38], 'degree':3,'type':'t_junction'},
        {'point':[45,-38],'degree':4,'type':'crossroads'},
        {'point':[-45,-38],'degree':4,'type':'crossroads'},
        {'point':[45,42], 'degree':4,'type':'crossroads'},
        {'point':[-45,42],'degree':4,'type':'crossroads'},
        {'point':[18,-38],'degree':3,'type':'t_junction'},
        {'point':[-18,-38],'degree':3,'type':'t_junction'},
        {'point':[18,42], 'degree':3,'type':'t_junction'},
        {'point':[-18,42],'degree':3,'type':'t_junction'},
    ],
}

# ── Scene 3: Y-Junction / Complex (Istanbul Beyoglu / Paris diagonal style) ───
# Diagonal avenue (30 m) crosses a main boulevard (28 m) creating a complex star
# junction south-west of the site. L-building wraps the site corner.
SCENE_3 = {
    'name'    : 'SCENE 3  |  Y-Junction Complex  (L-Building)',
    'junction': 'y_junction',
    'roads'   : [
        # Grand boulevard E-W (28 m): 18 m south of site bottom
        {'type':'road','centerline':[[-160,-38],[160,-38]],
         'width_m':28.0,'hierarchy':'main','name':'Grand Boulevard'},
        # Diagonal avenue (25 m) at ~37 deg: (-70,-95) → (85,75)
        # At y=-38: x ≈ -70 + ((-38+95)/170)*155 = -70 + 0.335*155 = -70+52 = -18
        {'type':'road','centerline':[[-70,-95],[85,75]],
         'width_m':25.0,'hierarchy':'main','name':'Avenue Diagonale'},
        # Secondary E-W north (15 m)
        {'type':'road','centerline':[[-160,45],[160,45]],
         'width_m':15.0,'hierarchy':'secondary','name':'Rue Transversale'},
        # Secondary N-S east (15 m)
        {'type':'road','centerline':[[48,-160],[48,160]],
         'width_m':15.0,'hierarchy':'secondary','name':'Rue Perpendiculaire'},
        # Short secondary connector N-S between boulevard and transversale (12 m)
        {'type':'road','centerline':[[0,-38],[0,45]],
         'width_m':12.0,'hierarchy':'secondary','name':'Rue Centrale'},
        # Service alley W of site (4 m)
        {'type':'road','centerline':[[-18,-160],[-18,160]],
         'width_m':4.5,'hierarchy':'path','name':'Ruelle Ouest'},
        # Service path parallel to diagonal (4 m)
        {'type':'road','centerline':[[-55,-55],[70,60]],
         'width_m':4.0,'hierarchy':'path','name':'Passage Diagonal'},
    ],
    'intersections': [
        # Complex star where diagonal meets boulevard near x=-18, y=-38
        {'point':[-18,-38],'degree':5,'type':'complex_junction'},
        # Crossroads: boulevard x N-S secondary
        {'point':[48,-38], 'degree':4,'type':'crossroads'},
        # T-junction: connector meets boulevard
        {'point':[0,-38],  'degree':3,'type':'t_junction'},
        # Crossroads: transversale x N-S secondary
        {'point':[48,45],  'degree':4,'type':'crossroads'},
        {'point':[0,45],   'degree':4,'type':'crossroads'},
        # T-junction: alley meets transversale
        {'point':[-18,45], 'degree':3,'type':'t_junction'},
        # Where diagonal crosses transversale
        {'point':[30,45],  'degree':3,'type':'y_junction'},
    ],
}

SCENES = [SCENE_1, SCENE_2, SCENE_3]
print(f'{len(SCENES)} scenes defined')
for sc in SCENES:
    hc = {}
    for r in sc['roads']:
        h = r.get('hierarchy','?')
        hc[h] = hc.get(h, 0) + 1
    print(f"  {sc['name'][:45]}: {len(sc['roads'])} roads "
          f"(main={hc.get('main',0)} sec={hc.get('secondary',0)} path={hc.get('path',0)}) "
          f"{len(sc['intersections'])} junctions")
