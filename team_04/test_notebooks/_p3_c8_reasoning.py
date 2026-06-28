from collections import Counter

IX_RESPONSE = {
    'crossroads': (
        'Maximum visibility from 4 directions. Activate all corners. '
        'Retail frontage recommended. LANDMARK potential: VERY HIGH.'
    ),
    't_junction': (
        'Building terminates 180 m view corridor. '
        'Primary facade MUST face the approaching axis. Architectural focal point required.'
    ),
    'y_junction': (
        'Building mediates two diverging directions. '
        'Dynamic or tapered geometry preferred. Both arms must be architecturally addressed.'
    ),
    'complex_junction': (
        'Multi-leg convergence. High urban complexity. '
        'Building must anchor the space. Civic or mixed-use program.'
    ),
    'dead_end': (
        'Lower visibility. Private or residential uses preferred. No landmark pressure.'
    ),
    'bend': (
        'Curved road creates extended viewshed. Consider angled or curved facade.'
    ),
}

DIV = '=' * 76

for sc in SCENES:
    nm  = sc['name']
    d   = scene_results[nm]
    u   = d['urban']
    imp = d['importance']
    p   = d['placement']
    st  = SITE_TYPE_LABELS.get(u['site_type'], u['site_type'])
    ixc = Counter(ix.get('type') for ix in d['ix_s'])
    dom = d['dom_jtype']
    front_vis  = [f.get('visibility_score', 0) for f in u['frontages']]
    avg_vis    = sum(front_vis)/len(front_vis) if front_vis else 0
    gw_cnt     = sum(1 for c in u['corner_conditions'] if c.get('is_gateway'))
    imp_s      = imp.get('score', 0)
    pri        = d['primary']

    print(DIV)
    print(f'  {nm}')
    print(DIV)

    print(f'\n[1. SITE READING]')
    print(f'  Site type    : {st}')
    print(f'  Frontages    : {len(u["frontages"])} face(s)  avg visibility {avg_vis:.0%}')
    print(f'  Gateway cnrs : {gw_cnt}')
    print(f'  Importance   : {imp.get("grade","?")} ({imp_s:.2f})  '
          f'-> {"LANDMARK" if imp_s>0.6 else "moderate" if imp_s>0.3 else "low"} exposure')

    print(f'\n[2. ROAD IDENTIFICATION]')
    hc = Counter(r.get('hierarchy') for r in d['roads'])
    for rank, r in enumerate(d['ranked'][:4], 1):
        tag = ['PRIMARY','2nd    ','3rd    ','4th    '][rank-1]
        print(f'  {tag}: {r.get("name","[unnamed]"):<24} '
              f'{r.get("hierarchy","?"):<12} '
              f'{r.get("width_m",0):.0f} m  score={r.get("_score",0):.4f}')

    print(f'\n[3. JUNCTION ANALYSIS]')
    print(f'  Total junctions: {len(d["ix_s"])}')
    for t, n in sorted(ixc.items()):
        print(f'    {t.replace("_"," ").title():<26}: {n}')
    print(f'  Dominant type: {dom.replace("_"," ").title()}')
    if dom in IX_RESPONSE:
        print(f'  Urban response: {IX_RESPONSE[dom]}')

    print(f'\n[4. BUILDING PLACEMENT DECISION]')
    print(f'  Grid angle   : {p["grid_angle"]:.0f} deg  (from {pri.get("name","primary road") if pri else "?"})')
    print(f'  Primary road : {pri.get("name","?") if pri else "?"}'
          f'  ({pri.get("width_m",0):.0f} m wide)  facing site from {p["main_facing"]}')
    print(f'  Typology     : {p["typology"]}')
    for ln in p['reasoning']:
        print(f'  >> {ln}')

    print(f'\n[5. PLACEMENT RULES APPLIED]')
    typ = p['typology']
    if typ == 'H-Building':
        print(f'  RULE 1: Longest wing (Wing A) parallel to primary road → commercial frontage')
        print(f'  RULE 2: Wing B (rear) perpendicular to quieter program → office/residential')
        print(f'  RULE 3: Central connector anchors structural core and vertical circulation')
        print(f'  RULE 4: Open courtyard E/W → daylight penetration to all wings')
        print(f'  RULE 5: Gateway corner (if present) → entrance activated at corner')
    elif typ == 'Wide Slab':
        print(f'  RULE 1: Long slab perpendicular to view axis → terminates the T-junction vista')
        print(f'  RULE 2: All primary program faces the boulevard (south facade = public face)')
        print(f'  RULE 3: Services and cores to rear → unobstructed public frontage')
        print(f'  RULE 4: Slender profile maximises height vs. footprint')
    elif typ == 'L-Building':
        print(f'  RULE 1: Arm A parallel to primary road → commercial ground floor')
        print(f'  RULE 2: Arm B wraps secondary road → office / mixed use')
        print(f'  RULE 3: Corner junction: recessed entrance or chamfered corner')
        print(f'  RULE 4: L-courtyard interior → passive ventilation, residential outlook')

    print(f'\n[6. SUMMARY]')
    print(f'  Site coverage (footprint): {p["coverage"]:.0%}')
    print(f'  Estimated FAR (4-5 fl.)  : {p["far_est"]:.1f}')
    if d['path_nodes']:
        print(f'  Walk to primary road     : {d["path_len"]:.0f} m ({len(d["path_nodes"])-1} hops)')
    print()
