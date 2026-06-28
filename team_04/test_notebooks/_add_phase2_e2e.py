"""
Append Phase 2 Urban Context + Complex Building Placement section
to end_to_end_api_agent.ipynb.
Run once. Safe to re-run (checks for existing section first).
"""
import json, uuid
from pathlib import Path

BASE = Path(r'c:\Users\tuemi\Downloads\Glabtools\IAAC Repo\bimsc26-datamgmt-session03\AIA26_Studio\team_04\test_notebooks')
NB   = BASE / 'end_to_end_api_agent.ipynb'

with open(NB, encoding='utf-8') as f:
    nb = json.load(f)

# Guard: don't add twice
existing_src = ' '.join(
    (c['source'] if isinstance(c['source'], str) else ''.join(c['source']))
    for c in nb['cells'] if c['cell_type'] == 'markdown'
)
if 'Phase 2' in existing_src and 'Complex Site' in existing_src:
    print('Phase 2 complex-site section already present — nothing to do.')
    raise SystemExit(0)


def _md(src):
    return {"cell_type": "markdown", "id": str(uuid.uuid4())[:8],
            "metadata": {}, "source": src}

def _code(src):
    return {"cell_type": "code", "id": str(uuid.uuid4())[:8],
            "metadata": {}, "outputs": [], "execution_count": None,
            "source": src}


# ─────────────────────────────────────────────────────────────────────────────
# CELL A — section header
# ─────────────────────────────────────────────────────────────────────────────
CELL_A = _md("""\
## Phase 2 — Urban Context Analysis + Complex Building Placement

Tests the Phase 2 road-context and urban-analysis tools on a richer site, then
sends a **complex architectural prompt** to the live agent asking it to place a
commercial H-building with the longest wing next to the main road.

**Site**: 30 m × 40 m parcel at a crossroads.
**Roads**: Main Boulevard (20 m) south · West / East Streets (12 m) · Upper Street (12 m) · Service Lane (5 m) · West Alley (4.5 m).
**Prompt**: H-shaped, commercial ground floor, longest wing to Main Boulevard, grid-aligned.

| Step | What it checks |
|------|---------------|
| Phase 2 tool check | `analyze_roads`, `full_urban_analysis`, `compute_urban_importance` |
| Complex agent run  | Brief extraction, road-aware placement, H-typology selection |
| Visualisation      | Site plan with placed building and road overlay |
| Backend API        | `/tools/road_context`, `/tools/urban_analysis` (SKIP if server offline) |
""")


# ─────────────────────────────────────────────────────────────────────────────
# CELL B — complex site definition
# ─────────────────────────────────────────────────────────────────────────────
CELL_B = _code("""\
# ── Complex site: 30 m x 40 m parcel at a busy crossroads ────────────────────
COMPLEX_SITE_BOUNDARY = [
    [0.0,  0.0, 0.0],
    [30.0, 0.0, 0.0],
    [30.0, 40.0, 0.0],
    [0.0,  40.0, 0.0],
    [0.0,  0.0, 0.0],
]

# Roads in the agent's site_objects format (for the LangGraph run)
COMPLEX_SITE_OBJECTS = [
    {"name": "Main Boulevard",  "type": "street", "points": [[-60.0, -12.0, 0.0], [90.0, -12.0, 0.0]]},
    {"name": "West Street",     "type": "street", "points": [[-12.0, -60.0, 0.0], [-12.0,  80.0, 0.0]]},
    {"name": "East Street",     "type": "street", "points": [[ 42.0, -60.0, 0.0], [ 42.0,  80.0, 0.0]]},
    {"name": "Upper Street",    "type": "street", "points": [[-60.0,  52.0, 0.0], [ 90.0,  52.0, 0.0]]},
    {"name": "Service Lane",    "type": "street", "points": [[-60.0,  -3.0, 0.0], [ 90.0,  -3.0, 0.0]]},
    {"name": "West Alley",      "type": "street", "points": [[-17.0, -60.0, 0.0], [-17.0,  80.0, 0.0]]},
]

# Same roads in the analysis-tool format (for Phase 2 tool checks)
COMPLEX_ROADS = [
    {"type": "road", "name": "Main Boulevard", "centerline": [[-60,-12],[90,-12]], "width_m": 20.0, "hierarchy": "main"},
    {"type": "road", "name": "West Street",    "centerline": [[-12,-60],[-12,80]], "width_m": 12.0, "hierarchy": "secondary"},
    {"type": "road", "name": "East Street",    "centerline": [[ 42,-60],[ 42,80]], "width_m": 12.0, "hierarchy": "secondary"},
    {"type": "road", "name": "Upper Street",   "centerline": [[-60, 52],[ 90,52]], "width_m": 12.0, "hierarchy": "secondary"},
    {"type": "road", "name": "Service Lane",   "centerline": [[-60, -3],[ 90,-3]], "width_m":  5.0, "hierarchy": "path"},
    {"type": "road", "name": "West Alley",     "centerline": [[-17,-60],[-17,80]], "width_m":  4.5, "hierarchy": "path"},
]

COMPLEX_PROMPT = (
    "I need a commercial H-shaped building on this crossroads site. "
    "Main Boulevard (20 m wide) runs along the south — this is the primary commercial frontage. "
    "Place the building's longest wing parallel to Main Boulevard so the ground floor is all retail. "
    "The rear wing faces the quieter north side for office or residential use. "
    "Align the building to the road grid direction. "
    "Target approximately 800 square metres footprint, 5 floors, mixed use "
    "(commercial ground floor, office above)."
)

{
    "site": "30 m x 40 m crossroads parcel",
    "roads": len(COMPLEX_ROADS),
    "main_road": "Main Boulevard (20 m, south)",
    "prompt_length": len(COMPLEX_PROMPT),
}
""")


# ─────────────────────────────────────────────────────────────────────────────
# CELL C — Phase 2 tool surface check (deterministic, no LLM)
# ─────────────────────────────────────────────────────────────────────────────
CELL_C = _code("""\
import time
from agent.tools.site_model import build_site_model
from agent.tools.road_context import analyze_roads
from agent.tools.urban_analysis import (
    full_urban_analysis, compute_urban_importance,
    detect_intersections_from_roads, SITE_TYPE_LABELS,
)
try:
    from agent.tools.osm_context import build_street_graph
    from agent.tools.urban_analysis import compute_centrality
    _nx_ok = True
except Exception:
    _nx_ok = False

p2_checks = []

def _p2_chk(name, fn):
    t = time.time()
    try:
        p2_checks.append((name, "OK", f"{fn()}  ({time.time()-t:.2f}s)"))
    except Exception as exc:
        p2_checks.append((name, "FAIL", f"{type(exc).__name__}: {exc}"))

# Build site model from complex site
_sm = build_site_model(
    COMPLEX_SITE_BOUNDARY,
    {"site_objects": COMPLEX_ROADS, "default_setback": 5.0},
)
_p2_chk(
    "site_model.build_site_model",
    lambda: f"corners={len(_sm['corners'])}  sides={len(_sm['sides'])}  area={_sm.get('setbacks',{}).get('site_area_sqm',0):.0f} m2",
)

# Road context
_rr = analyze_roads(_sm, COMPLEX_ROADS)
_sm['roads'] = _rr
_p2_chk(
    "road_context.analyze_roads",
    lambda: (
        f"main_road={_rr.get('main_road',{}).get('name','?')}  "
        f"side={_rr.get('main_road_side_index','?')}  "
        f"roads={len(_rr.get('roads',[]))}"
    ),
)

# Intersection detection
_ix = detect_intersections_from_roads(COMPLEX_ROADS)
_p2_chk(
    "urban_analysis.detect_intersections_from_roads",
    lambda: f"{len(_ix)} intersections detected",
)

# Full urban analysis
_ua = full_urban_analysis(_sm, COMPLEX_ROADS, _ix)
_p2_chk(
    "urban_analysis.full_urban_analysis",
    lambda: (
        f"site_type={SITE_TYPE_LABELS.get(_ua['site_type'],_ua['site_type'])}  "
        f"frontages={len(_ua['frontages'])}  "
        f"gateways={sum(1 for c in _ua['corner_conditions'] if c.get('is_gateway'))}"
    ),
)

# Urban importance (NetworkX)
if _nx_ok:
    try:
        _g = build_street_graph(COMPLEX_ROADS)
        _cen = compute_centrality(_g) if _g else {}
        _imp = compute_urban_importance(_sm, _g, _cen)
        _p2_chk(
            "urban_analysis.compute_urban_importance",
            lambda: f"grade={_imp['grade']}  score={_imp['score']:.2f}",
        )
    except Exception as _e:
        p2_checks.append(("urban_analysis.compute_urban_importance", "SKIP", str(_e)[:80]))
else:
    p2_checks.append(("urban_analysis.compute_urban_importance", "SKIP", "osm_context unavailable"))

print(f"{'TOOL':<58} {'STATUS':6} DETAIL")
print("-" * 110)
for name, status, detail in p2_checks:
    print(f"{name:<58} {status:6} {detail}")

n_ok   = sum(1 for _,s,_ in p2_checks if s == "OK")
n_skip = sum(1 for _,s,_ in p2_checks if s == "SKIP")
print(f"\\n{n_ok} OK  {n_skip} SKIP (NetworkX/OSM)  Phase 2 tool surface check complete")
assert n_ok >= 4, "Core Phase 2 tools failed — see FAIL rows above."

# Print the key urban analysis result
print("\\n=== PHASE 2 SITE READING ===")
print(f"  Site type    : {SITE_TYPE_LABELS.get(_ua['site_type'], _ua['site_type'])}")
print(f"  Primary road : {_rr.get('main_road',{}).get('name','?')}  ({_rr.get('main_road',{}).get('width_m',0):.0f} m wide)  side={_rr.get('main_road_side_index','?')}")
print(f"  Frontages    : {len(_ua['frontages'])}")
print(f"  Gateways     : {sum(1 for c in _ua['corner_conditions'] if c.get('is_gateway'))}")
print(f"  Junctions    : {len(_ix)}")
for ix in _ix[:6]:
    print(f"    [{ix.get('type','?'):18}] deg={ix.get('degree','?')}  at ({ix['point'][0]:.0f},{ix['point'][1]:.0f})")
""")


# ─────────────────────────────────────────────────────────────────────────────
# CELL D — Complex prompt agent run
# ─────────────────────────────────────────────────────────────────────────────
CELL_D = _code("""\
# ── Complex prompt agent run — crossroads + H-building with road-aware placement ──
from agent.mcp_client import CompositeToolClient, build_default_local_tool_client
from agent.notebook_demo_tools import build_notebook_demo_tool_client
from agent.tool_catalog import ToolCatalog

# Build a new tool client scoped to the complex site
_complex_notebook_client = build_notebook_demo_tool_client(
    COMPLEX_SITE_BOUNDARY,
    site_summary=(
        "30 m x 40 m crossroads site. Main Boulevard (20 m) runs south. "
        "West Street and East Street are 12 m secondary roads. "
        "H-building requested: longest wing to Main Boulevard."
    ),
    site_objects=COMPLEX_SITE_OBJECTS,
    setback_m=5.0,
    spatial_intention_score=0.88,
    performance_score=0.85,
    shape_integrity_score=0.92,
)
_complex_tool_client = CompositeToolClient(
    [build_default_local_tool_client(), _complex_notebook_client]
)
_complex_catalog = ToolCatalog.from_discovered_tools(_complex_tool_client.list_tools())

_complex_layout = {
    "workflow_mode": "full",
    "site_boundary": COMPLEX_SITE_BOUNDARY,
    "site_objects": COMPLEX_SITE_OBJECTS,
    "target_building_count": 1,
    "building_intents": [
        "H-shaped building, longest wing parallel to Main Boulevard (south), retail ground floor.",
        "Rear quieter wing faces north. Grid aligned to road direction.",
    ],
}

print("Sending complex prompt to agent...")
print(f"  Prompt: {COMPLEX_PROMPT[:100]}...")
print()

complex_state = run_agent(
    user_prompt=COMPLEX_PROMPT,
    decision_engine=decision_engine,
    tool_client=_complex_tool_client,
    catalog=_complex_catalog,
    initial_layout=_complex_layout,
    max_optimization_cycles=3,
    planner=RuleBasedPlanner(),
)

# Surface the design brief the agent extracted
_db = complex_state.get("design_brief") or {}
_sm_c = complex_state.get("site_model") or {}
print("=== AGENT COMPREHENSION (Phase 0 — design brief) ===")
print(f"  source         : {_db.get('source')}")
print(f"  building_count : {_db.get('building_count')}")
for i, b in enumerate(_db.get("buildings", [])):
    print(f"  building {i+1}    : shape={b.get('shape_preference')}  "
          f"area={b.get('footprint_area_sqm')} m2  "
          f"storeys={b.get('storeys')}  use={b.get('use')}")
print(f"  alignment_wt   : {_db.get('alignment_weight')}")
print(f"  ambiguities    : {_db.get('ambiguities') or '(none)'}")

print()
print("=== PLACEMENT RESULT ===")
print(f"  Buildings placed : {len(complex_state.get('placed_buildings', []))}")
print(f"  Re-asked?        : {bool(complex_state.get('clarification_request'))}")
_resp = (complex_state.get('final_response') or '')
print(f"  Final response   : {_resp[:300]}")

{
    "prompt": COMPLEX_PROMPT[:80] + "...",
    "brief_source": _db.get("source"),
    "shape": [b.get("shape_preference") for b in _db.get("buildings", [])],
    "buildings_placed": len(complex_state.get("placed_buildings", [])),
}
""")


# ─────────────────────────────────────────────────────────────────────────────
# CELL E — Visualise result
# ─────────────────────────────────────────────────────────────────────────────
CELL_E = _code("""\
# ── Visualise the complex-site placement ─────────────────────────────────────
try:
    _complex_shape = extract_latest_shape(complex_state)
except Exception:
    _complex_shape = None

# Decision trace
_trace = [
    m for m in complex_state.get("messages", [])
    if m.startswith(("Design brief", "Planner", "Supervisor", "Tool ", "Final"))
]
print(f"Decision steps: {len(_trace)}")
for step in _trace:
    print(f"  {step[:110]}")

print()
make_site_plan_figure(
    COMPLEX_SITE_BOUNDARY,
    current_shape=_complex_shape,
    placed_buildings=complex_state.get("placed_buildings", []),
    site_objects=COMPLEX_SITE_OBJECTS,
    title=(
        "Complex Site — H-building · Longest wing to Main Boulevard (20 m) · "
        f"{len(complex_state.get('placed_buildings',[]))} building(s) placed"
    ),
)
""")


# ─────────────────────────────────────────────────────────────────────────────
# CELL F — Backend HTTP API for Phase 2
# ─────────────────────────────────────────────────────────────────────────────
CELL_F = _md("""\
## Phase 2 — Backend HTTP API (road context endpoints)

Calls the live FastAPI server to confirm the Phase 2 backend routes are wired up
(these match `backend/routers/tools.py` and the frontend `Team04Api` methods).

Start the server first if not running:
```
uvicorn team_04.backend.app:app --reload --port 8000
```

Endpoints exercised: `POST /tools/road_context`, `POST /tools/urban_analysis`.
""")


CELL_G = _code("""\
import json as _json
import urllib.request, urllib.error

_BASE = "http://localhost:8000"

def _post_p2(tool: str, args: dict) -> dict:
    body = _json.dumps({"tool_name": tool, "arguments": args}).encode()
    req = urllib.request.Request(
        f"{_BASE}/tools/{tool}", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return _json.loads(r.read())

p2_api = []

def _api(name, fn):
    try:
        p2_api.append((name, "OK", str(fn())[:100]))
    except urllib.error.URLError as exc:
        p2_api.append((name, "SKIP", f"server offline — {exc.reason}"))
    except Exception as exc:
        p2_api.append((name, "FAIL", f"{type(exc).__name__}: {exc}"))

# GET /tools — check road-context tools are registered
_api(
    "GET /tools  (road_context / urban_analysis present)",
    lambda: sorted(
        t for t in _json.loads(
            urllib.request.urlopen(f"{_BASE}/tools", timeout=5).read()
        )["tools"]
        if any(k in t for k in ("road", "urban", "site_model", "intersection"))
    ),
)

# POST /tools/road_context — identify main road on complex site
_api(
    "POST /tools/road_context",
    lambda: (lambda r: f"success={r['success']}  main_road={r['result'].get('main_road',{}).get('name','?')}")(
        _post_p2("road_context", {
            "site_boundary": COMPLEX_SITE_BOUNDARY,
            "roads": COMPLEX_ROADS,
        })
    ),
)

# POST /tools/urban_analysis — full urban analysis
_api(
    "POST /tools/urban_analysis",
    lambda: (lambda r: f"success={r['success']}  site_type={r['result'].get('site_type','?')}")(
        _post_p2("urban_analysis", {
            "site_boundary": COMPLEX_SITE_BOUNDARY,
            "roads": COMPLEX_ROADS,
        })
    ),
)

print(f"{'ENDPOINT':<56} {'STATUS':6} DETAIL")
print("-" * 110)
for name, status, detail in p2_api:
    print(f"{name:<56} {status:6} {detail}")

n_ok   = sum(1 for _,s,_ in p2_api if s == "OK")
n_skip = sum(1 for _,s,_ in p2_api if s == "SKIP")
n_fail = sum(1 for _,s,_ in p2_api if s == "FAIL")
print(f"\\n{n_ok} OK  {n_skip} SKIP (server offline)  {n_fail} FAIL")
if n_fail:
    raise AssertionError("Phase 2 backend API checks FAILED — see FAIL rows.")
if n_skip == len(p2_api):
    print("\\nAll checks skipped: start the backend server to test the live HTTP connection.")
    print("  uvicorn team_04.backend.app:app --reload --port 8000")
""")


# ─────────────────────────────────────────────────────────────────────────────
# Append all new cells
# ─────────────────────────────────────────────────────────────────────────────
nb['cells'].extend([CELL_A, CELL_B, CELL_C, CELL_D, CELL_E, CELL_F, CELL_G])

with open(NB, 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print(f'Written: {len(nb["cells"])} total cells  ({NB.name})')
print('New cells added:')
print('  CELL_A  md   Phase 2 section header')
print('  CELL_B  code Complex site + roads definition')
print('  CELL_C  code Phase 2 tool surface check (deterministic)')
print('  CELL_D  code Complex prompt agent run (live LLM)')
print('  CELL_E  code Placement visualisation')
print('  CELL_F  md   Phase 2 backend API header')
print('  CELL_G  code Phase 2 backend HTTP API check')
