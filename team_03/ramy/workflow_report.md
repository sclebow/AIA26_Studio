# Spatial Flow Agent — LLM Workflow Report

## 1. Current Functioning Workflow

### What the LLM does today

The LLM is called at three points in the pipeline:

---

#### A. Profile Agent (`nodes/profile_agent.py`)
**One call per run.**

Input: user prompt  
Task: identify the correct movement profile  
Output: `{profile_type, min_path_width, turning_radius, reach_height_min/max}`

Example:
> "add a QC station near the labeling station"
> → `standard_worker, 0.915m corridor, 0.3m turning`

The LLM reads the prompt, matches it against industrial profiles (standard_worker, forklift, crane, pallet_jack, maintenance_worker), and outputs a structured JSON. The code enforces a minimum turning_radius of 0.30m if the LLM returns 0.

---

#### B. Space Type Agent (`nodes/space_type_agent.py`)
**One call per run.**

Input: user prompt + layout metadata  
Task: identify space subtype and set analysis weights  
Output: `{space_type, priorities, clearance, tool_weights}`

Example:
> layout has clean room → `clearance: 0.9m, collision weight: 0.40, path weight: 0.25`

The weights control how the final score is calculated. A warehouse gets higher forklift path weighting; a clean room gets lower turning radius requirements.

---

#### C. Reason Node (`nodes/reason.py`)
**Called repeatedly — the main decision loop.**

Input: full conversation history + injected context  
Context injected before each call:
- Current layout JSON (rooms, doors, furniture, walls, windows)
- Space config (clearance, priorities, tool_weights)
- Profile config (worker type, path width, turning radius)
- Tool catalog (available MCP tools)
- Analysis results from previous cycle (collision violations, path scores, etc.)

The LLM can return one of four actions:

| Action | When used | What happens |
|--------|-----------|--------------|
| `tool + place_object` | User asks to ADD/PLACE | Routes to `add_objects_node` → GH MCP → analysis pipeline |
| `tool + move_object` | Collision violation detected | Routes to `tool_node` → GH MCP → analysis pipeline |
| `query` | User asks to ANALYZE | Routes to `query_agent` → runs tools → checkpoint |
| `final` | Placement done / question answered | Routes to `analysis_fan_out` → scoring → checkpoint |

**Placement reasoning (what the LLM calculates):**

1. Parse room bounds from `rooms[].geometry`
2. Resolve spatial description — "near loading dock" → find door geometry → offset by clearance
3. Check candidate against existing furniture footprints
4. Check distance from doors (1.0m minimum)
5. Output `objects_list: "name:WxDxH:x=X,y=Y"`

**Adjustment loop (what happens after collision):**

When `group1_join_node` detects hard violations it injects a forceful message:
> "COLLISION VIOLATION — ADJUSTMENT REQUIRED (2/3). Blocked area: 35.49m². Move 'QC_Station' at least 1.4m from (23.5, 6.0). Call move_object NOW."

The LLM reads this and calls `move_object` with new coordinates. It gets 3 attempts before the pipeline moves on regardless.

---

### What the code does (not the LLM)

Everything after the LLM outputs coordinates is fully automated:

- **`add_objects.py`** — sends to GH, mirrors into state, checks door/window clearance
- **`collision.py`** — BFS distance field, wall vs equipment separation, pre-existing vs new violations
- **`path_analysis.py`** — A* between all furniture pairs, connectivity check
- **`reachability.py`** — BFS from door midpoints, checks every object's use_point
- **`visibility.py`** — centroid-to-centroid ray casting + isovist computation (72 rays per object)
- **`scoring.py`** — weighted aggregate → 0-100 grade
- **`checkpoint.py`** — displays results, viewport toggles, user decision

---

### Current LLM limitations

1. **Blind to relationships** — sees raw coordinates, not "this machine is 0.8m from the south wall and 1.2m from a window"
2. **No workflow awareness** — doesn't know that conveyor sections should connect, that QC follows assembly
3. **Generic adjustment** — when collision fires it moves randomly rather than using the direction that maximally increases clearance
4. **Identical final responses** — always says "placed successfully with 0.9m clearance on all sides" regardless of actual results

---

## 2. Proposed Addition — Enhanced Analysis Interpretation (Items 28)

### What changes

After every analysis cycle the LLM receives the full structured results, not just a summary number. It reads and interprets them using the spatial graph.

### New context injected

After `enrich_graph_node` runs, the LLM sees:

```
SPATIAL GRAPH (45 nodes, 43 edges)
STRUCTURE: 4 exterior walls, 2 interior partitions
FURNITURE in Clean Room:
  Assembly Station 1 at (7.1, 10.5) --near_wall(0.8m)--> South Exterior Wall
  QC_Station at (23.5, 6.0) --near(1.2m)--> Labeling Station 6

ISSUES:
  QC_Station: clearance 0.28m < required 0.4m → move [+0.22, 0] (east, away from Conveyor Section 5)
  Assembly Station 1: clearance OK (gap 1.4m)
```

### What the LLM produces

Instead of:
> "QC Station placed successfully with 0.9m clearance on all sides."

It produces:
> "QC Station at (23.5, 6.0) has insufficient clearance on its west side — 0.28m gap to Conveyor Section 5, below the required 0.4m minimum (OSHA 1910.22). Moving east by 0.22m to (23.72, 6.0) resolves this. Assembly Station 1 clearance is good at 1.4m. Longest path is 34.9m between Packaging Station 4 and Conveyor Section 10 — within acceptable range for this clean room footprint."

### What the LLM does with ISSUES

When the spatial graph has ISSUES with exact move vectors, the LLM calls `move_object` with the exact vector instead of guessing. This reduces the adjustment loop from 3 attempts to 1.

### What changes in the code

- `enrich_graph_node` already built by teammate — inject `spatial_graph_text` into reason.py context
- `prompts.py` — add SPATIAL GRAPH section instructing LLM to use ISSUES move vectors
- `nodes/reason.py` — inject `spatial_graph_text` alongside space_config and profile_config
- `nodes/explain.py` — use spatial graph text for the final explanation instead of raw scores

---

## 3. Proposed Addition — LLM Population of Empty Layouts

### What changes

A new planning phase before placement starts. The LLM receives an empty layout and decides what equipment goes where, in what order, before any placement tool is called.

### New workflow

```
User: "populate this clean room with a standard production line"
         ↓
populate_agent (NEW) — plans the full layout
  - reads room dimensions, door positions, window locations
  - identifies workflow type from space_config
  - divides room into functional zones
  - selects equipment list and quantities
  - calculates initial coordinates zone by zone
  - outputs ordered placement queue
         ↓
object_queue (existing, item 05) — 15-20 objects queued
         ↓
For each object (existing pipeline, unchanged):
  add_objects → GH MCP → collision + path + reachability + visibility
  if violation → move_object (guided by spatial graph ISSUES)
  if pass → next object
         ↓
Final scoring → checkpoint → user approves
```

### Zone planning logic

The LLM reads the layout and assigns zones based on door positions:

| Zone | Location | Objects |
|------|----------|---------|
| Receiving | Near loading dock | Conveyor sections, parts bin racks |
| Production | Center of room | Assembly stations, CNC machines |
| QC | Between production and exit | QC tables, labeling stations |
| Storage | Along walls | Parts racks, tool cabinets |
| Circulation | Corridors | 1.0m+ clearance maintained |

### Knowledge base (`workflow_patterns.json`)

Standard configurations by space type:

```json
{
  "clean_room": {
    "standard_production_line": {
      "flow": "loading_dock → assembly → qc → packaging → exit",
      "objects": [
        {"type": "conveyor_section", "count": 2, "zone": "receiving"},
        {"type": "assembly_station", "count": 3, "zone": "production"},
        {"type": "qc_table", "count": 1, "zone": "qc"},
        {"type": "packaging_station", "count": 2, "zone": "packaging"},
        {"type": "parts_bin_rack", "count": 2, "zone": "storage"}
      ],
      "clearance_m": 0.9,
      "min_aisle_m": 1.2
    }
  },
  "warehouse": {
    "standard_storage": {
      "flow": "loading_dock → receiving → storage → picking → shipping",
      "objects": [
        {"type": "storage_rack", "count": 8, "zone": "storage"},
        {"type": "conveyor_section", "count": 3, "zone": "receiving"},
        {"type": "forklift_charging_station", "count": 1, "zone": "equipment"}
      ],
      "clearance_m": 1.83,
      "min_aisle_m": 3.05
    }
  }
}
```

### New files

| File | Purpose |
|------|---------|
| `nodes/populate_agent.py` | Planning node — zone assignment + equipment selection |
| `knowledge/industrial/workflow_patterns.json` | Standard configurations by space type |
| `prompts.py` + `POPULATE_SYSTEM_PROMPT` | Prompt for zone planning reasoning |

### Why the spatial graph is critical here

When populating from scratch the LLM needs to know:
- Which walls have windows (avoid blocking with tall racks)
- Which doors are loading docks vs personnel exits (determines flow direction)
- Where MEP elements are fixed (HVAC, electrical panels cannot move)

All of this is in the spatial graph `near_wall`, `near_window`, `door_connects` edges.

---

## Summary

| Layer | Today | With item 28 | With population |
|-------|-------|-------------|-----------------|
| Profile | LLM picks worker type | unchanged | unchanged |
| Space type | LLM picks clearance + weights | unchanged | unchanged |
| Planning | none | none | LLM plans zones + equipment list |
| Placement | LLM picks x,y from coordinates | LLM uses graph ISSUES vectors | LLM places from zone plan |
| Adjustment | LLM guesses new position (3 tries) | LLM uses exact move vector (1 try) | same as item 28 |
| Interpretation | generic "placed successfully" | named objects + distances + standards | same as item 28 |
| Analysis | code runs, numbers shown | code runs, LLM explains findings | same as item 28 |
