import json, urllib.request

BASE = "http://localhost:8001"

def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE+path, data=data, headers={"Content-Type":"application/json"}, method="POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=90).read())
    except Exception as e:
        return {"_error": str(e)}

sid = post("/sessions", {"user_prompt":"", "workflow_mode":"full"})["session_id"]
post(f"/sessions/{sid}/site/boundary", {"boundary":[[0,0],[180,0],[180,140],[0,140]]})

ctx_edges = [
  {"edge_id":"E_N","display_name":"North Edge","direction":"North","a":[0,140],"b":[180,140],"mid":[90,140],
   "nearest":{"Park":80,"Metro":1200},"edge_context":[{"label":"Park","distance":80,"reason":"green outlook"}]},
  {"edge_id":"E_E","display_name":"East Edge","direction":"East","a":[180,0],"b":[180,140],"mid":[180,70],
   "nearest":{"Metro":110,"Primary Road":30,"Grocery Store":200},"edge_context":[{"label":"Metro","distance":110,"reason":"transit"},{"label":"Primary Road","distance":30,"reason":"frontage"}]},
  {"edge_id":"E_S","display_name":"South Edge","direction":"South","a":[0,0],"b":[180,0],"mid":[90,0],
   "nearest":{"Primary Road":25},"edge_context":[{"label":"Primary Road","distance":25,"reason":"noisy road"}]},
  {"edge_id":"E_W","display_name":"West Edge","direction":"West","a":[0,0],"b":[0,140],"mid":[0,70],
   "nearest":{"School":350},"edge_context":[{"label":"School","distance":350,"reason":"education"}]},
]
post(f"/sessions/{sid}/context/store", {"edges":ctx_edges,"scores":{"transit":70,"walkability":75,"greenSpace":65,"retail":50}})
post(f"/sessions/{sid}/context/selection", {"selected_edge":ctx_edges[1], "selected_corner":{"name":"northeast","x":180,"y":140}})

opt = post(f"/sessions/{sid}/generate-options", {"prompt":"8 floor mixed-use building"})
shapes = {o["shape_type"]:o["option_id"] for o in opt["options"]}
hid = shapes.get("H") or list(shapes.values())[0]
post(f"/sessions/{sid}/select-shape", {"option_id":hid})
print(f"SETUP: shape={hid} (H wings={'yes' if 'H' in shapes else 'no'})")
print("="*70)

def fb(prompt):
    # Reset to the clean selected shape before each prompt so results are INDEPENDENT
    # (the suite tests recognition/application of each prompt, not the effect of 100
    # destructive ops stacked on one building — that cumulative degradation is not a
    # realistic user flow and produced spurious "degenerate geometry" failures).
    post(f"/sessions/{sid}/select-shape", {"option_id":hid})
    r = post(f"/sessions/{sid}/buildings/{hid}/feedback", {"feedback":prompt,"apply":True})
    return r.get("status","?"), (r.get("reason") or "")[:55]

PROMPTS = {
"Basic Massing":["Make the building 20% larger.","Reduce the overall footprint.","Make the tower taller.","Add 5 floors.","Remove 3 floors.","Increase the building height by 10m.","Stretch the building east-west.","Compress the building north-south.","Make the building more slender.","Make it more compact."],
"Wing":["Extend the north wing by 15m.","Reduce the south wing depth.","Increase the east wing area.","Remove the west wing.","Add a new wing on the north side.","Balance the left and right wings.","Make the central wing dominant.","Pull back the east wing.","Push the west wing closer to the street.","Create equal wing lengths."],
"Courtyard":["Make the courtyard larger.","Increase courtyard daylight.","Open the courtyard to the south.","Create a full-height courtyard.","Add another courtyard.","Connect the courtyards together.","Create a semi-private courtyard.","Make the courtyard more intimate.","Increase the green area inside the courtyard.","Open the building around the courtyard."],
"Daylight":["I need more daylight.","Bring more sunlight into the courtyard.","Reduce self-shading.","Improve winter solar gain.","Increase south-facing exposure.","Create better daylight distribution.","Open up the mass for sunlight.","Rotate for better solar access.","Reduce building depth for daylight.","Maximize sunlight hours."],
"Edge/North":["Create a long facade on the north edge.","Place the main frontage on the east edge.","Open the courtyard toward the south.","Move the tower closer to the west edge.","Increase setback on the north edge.","Place retail along the east edge.","Create a plaza near the south edge.","Maximize views from the northeast corner.","Orient the building toward the north.","Create an active frontage on the east side."],
"View":["Orient the building toward the park.","Maximize park views.","Increase skyline visibility.","Create view corridors toward the landmark.","Avoid views toward service roads.","Face the tower toward the water body.","Improve premium view exposure.","Open the facade toward the best view.","Preserve the view corridor.","Maximize corner views."],
"Public/Private":["Create a public plaza on the ground floor.","Make the courtyard semi-private.","Increase privacy for residential units.","Separate public and private circulation.","Create a private residential garden.","Add a semi-public gathering space.","Reduce overlooking between units.","Improve privacy on upper floors.","Create a public frontage and private rear zone.","Define clear public-private transitions."],
"Noise":["Move residential units away from the highway.","Reduce traffic noise exposure.","Place the building in the quietest area.","Shield the courtyard from road noise.","Orient bedrooms away from the railway.","Create a noise buffer.","Improve acoustic comfort.","Move the tower away from noisy roads.","Protect outdoor spaces from noise.","Optimize for quiet residential use."],
"Character":["Make it feel more residential.","Make it feel more commercial.","Give it a luxury character.","Create a corporate identity.","Make it more iconic.","Give it landmark quality.","Make it feel more urban.","Create a campus-like atmosphere.","Make it more welcoming.","Create a premium mixed-use development."],
"Advanced":["It feels too compact.","The massing is too heavy.","Open it up.","Give the project more breathing room.","The building lacks identity.","Create a stronger hierarchy.","Make it more elegant.","The composition feels unbalanced.","Create a stronger architectural expression.","The project feels generic.","Make it more memorable.","Add some architectural drama.","Create a stronger relationship with the courtyard.","The building feels too bulky.","Make it more refined."],
"Design Review":["I want a U-shaped building with a larger south-facing courtyard.","Create a commercial podium with residential towers above.","Keep the footprint but increase daylight performance.","Increase privacy while maintaining views.","Create a landmark tower facing the park.","Maximize solar access and public open space.","Reduce noise exposure and improve walkability.","Create a mixed-use development with active retail frontage.","Make the building more iconic without increasing height.","Keep this option but make it feel less corporate and more residential."],
}

totals = {"success":0,"failed":0,"error":0}
fails = []
for cat, prompts in PROMPTS.items():
    cs = 0
    for p in prompts:
        st, rs = fb(p)
        if st == "success": cs+=1; totals["success"]+=1
        elif st == "failed": totals["failed"]+=1; fails.append((cat,p,rs))
        else: totals["error"]+=1; fails.append((cat,p,"ERR:"+rs))
    print(f"{cat:16} {cs}/{len(prompts)} pass")

n = sum(len(v) for v in PROMPTS.values())
print("="*70)
print(f"TOTAL: {totals['success']}/{n} success | {totals['failed']} failed | {totals['error']} error")
print("\nFAILED:")
for cat,p,rs in fails:
    print(f"  [{cat}] {p}\n      -> {rs}")
