"""Run optimization end-to-end and verify the options are GENUINELY different
(distinct placement / massing / objective focus), referencing Site Context Memory."""
import json, urllib.request
BASE = "http://localhost:8001"
def post(p, b=None):
    d = json.dumps(b or {}).encode()
    r = urllib.request.Request(BASE+p, data=d, headers={"Content-Type":"application/json"}, method="POST")
    try: return json.loads(urllib.request.urlopen(r, timeout=180).read())
    except Exception as e:
        try: return json.loads(e.read())
        except Exception: return {"_error": str(e)}

def centroid(ring):
    pts=[p for p in (ring or []) if len(p)>=2]
    if not pts: return (0,0)
    return (round(sum(p[0] for p in pts)/len(pts)), round(sum(p[1] for p in pts)/len(pts)))
def area(ring):
    pts=[(p[0],p[1]) for p in (ring or []) if len(p)>=2]
    if len(pts)<3: return 0
    a=sum(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts)))
    return round(abs(a)/2)

sid = post("/sessions", {"workflow_mode":"full"})["session_id"]
post(f"/sessions/{sid}/site/boundary", {"boundary":[[0,0],[180,0],[180,140],[0,140]]})

# Urban context with REAL feature variety: park north, noisy road south, metro+road east.
edges = [
  {"edge_id":"E_N","direction":"North","a":[0,140],"b":[180,140],"mid":[90,140],"nearest":{"Park":70,"Green Space":90}},
  {"edge_id":"E_E","direction":"East","a":[180,0],"b":[180,140],"mid":[180,70],"nearest":{"Metro":110,"Primary Road":30,"Retail":150}},
  {"edge_id":"E_S","direction":"South","a":[0,0],"b":[180,0],"mid":[90,0],"nearest":{"Primary Road":18,"Highway":60}},
  {"edge_id":"E_W","direction":"West","a":[0,0],"b":[0,140],"mid":[0,70],"nearest":{"School":300}},
]
post(f"/sessions/{sid}/context/store", {"edges":edges,"scores":{"transit":72,"walkability":78,"greenSpace":80,"retail":55}})

opt = post(f"/sessions/{sid}/generate-options", {"prompt":"10 floor mixed-use building"})
shapes = {o["shape_type"]:o["option_id"] for o in opt["options"]}
hid = shapes.get("I") or shapes.get("L") or list(shapes.values())[0]
post(f"/sessions/{sid}/select-shape", {"option_id":hid})

print("Running optimization...\n")
res = post(f"/sessions/{sid}/optimize", {"saved_option_count":8, "population_size":16, "generation_count":16})
if res.get("_error") or res.get("detail"):
    print("ERROR:", res.get("_error") or res.get("detail")); raise SystemExit
opts = res.get("options", [])
mo = res.get("multi_objective", {})

print("="*108)
print("OPTIMIZATION OPTIONS — diversity check")
print("="*108)
print(f"Pareto front: {mo.get('pareto_count')} | scored: {mo.get('scored_count')} | "
      f"unavailable objectives: {mo.get('unavailable_objectives')} | backfilled: {mo.get('backfilled')}")
print(f"Context Memory used: {mo.get('context_memory_used')} | availability: {mo.get('context_availability')}")
if mo.get("error"): print("MO ERROR:", mo.get("error"), mo.get("trace"))
print("-"*108)
print(f"{'OPTION':28} {'POSITION':>12} {'ROT':>5} {'MASSING':>10} {'AREA':>7} {'SCORE':>6}  {'KEY OBJECTIVES'}")
print("-"*108)
seen_pos=[]
for o in opts:
    c=centroid(o.get("boundary"))
    os=o.get("objective_scores",{})
    keyobj=" ".join(f"{k[:4]}={os[k]:.0f}" for k in ["solar","view","noise","wind","density","open_space"] if k in os)
    print(f"{o.get('strategy_name',o.get('option_id')):28} {f'{c[0]},{c[1]}':>12} {o.get('rotation_degrees',0):>5} {o.get('massing','-'):>10} {area(o.get('boundary')):>7} {o.get('score',0):>6}  {keyobj}")
    seen_pos.append(c)

# Diversity metrics
import math
uniq_pos = len(set(seen_pos))
uniq_mass = len(set(o.get("massing","-") for o in opts))
pairs=[(seen_pos[i],seen_pos[j]) for i in range(len(seen_pos)) for j in range(i+1,len(seen_pos))]
mindist = min((math.hypot(a[0]-b[0],a[1]-b[1]) for a,b in pairs), default=0)
print("-"*108)
print(f"DIVERSITY: {len(opts)} options | {uniq_pos} distinct positions | {uniq_mass} distinct massings | "
      f"closest pair {mindist:.0f}m apart")
print("(Options with the same position AND massing would be near-duplicates — there should be none.)")
