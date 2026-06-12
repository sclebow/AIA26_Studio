# Team 04 Backend Improvement Plan — Site-Intelligent Placement Agent

Created: 2026-06-12. Branch policy: all work stays inside `team_04/`; never touch files outside this folder so merges with `main` stay conflict-free.

## Where We Are vs. Where We're Going

**Today** the agent places buildings on a site using a view-only fitness (perpendicular ray casting + NSGA-II in `agent/tools/view_optimizer.py`). The reasoning layer is shallow: user intent is parsed with regex keyword matching in `agent/decision_engine.py` (`_infer_requested_building_type`, `_extract_requested_rotation`, …), and the supervisor prompt is a long list of hand-written rules. Placement candidates are a free grid sweep with 10° rotations — buildings land anywhere the fitness allows, with no relationship to the site's sides, its surroundings, or how people and vehicles would actually reach them.

**The target** is an agent that comprehends short, natural prompts ("two U-shaped apartment buildings with a quiet courtyard, parking for residents") because it extracts a *typed design brief* with an LLM and then reasons over a *structured site model* (sides, grid, roads, sun, setbacks) with deterministic tools. The prompt gets shorter because the intelligence moves out of the prompt and into (a) structured intent extraction and (b) a richer world model the tools share.

**Guiding principle:** LLM for comprehension (free text → typed brief, choosing between options, explaining decisions). Deterministic geometry tools for everything measurable (sun, roads, grids, parking counts, fire distances). Never ask the LLM to do math the tools can do; never hardcode regex for language the LLM can understand.

## Workflow Rules (apply to every phase)

- [ ] Every new capability ships as a tool module in `agent/tools/` with pure functions (Shapely in / dict out), no LLM calls inside tools.
- [ ] Every phase gets **one notebook** in `test_notebooks/` that visualizes the capability and proves it works before it is wired into the agent graph.
- [ ] Every phase gets **unit regressions** in `benchmarking/` (deterministic, no LLM, no MCP).
- [ ] Every completed phase gets a dated entry in `PROGRESS.md` (Completed / Validation / Active MVP Status sections, same format as existing entries).
- [ ] Every architectural change (new state keys, new graph nodes, new tool families) is reflected in `ARCHITECTURE.md` in the same commit.
- [ ] Before merging to `main`: `git fetch origin main && git merge-base --is-ancestor` check, confirm `git diff origin/main --name-only` only lists `team_04/` paths.
- [ ] Frontend wiring is **last** (Phase 9) — backend contracts stabilize first.

---

## Phase 0 — Reasoning Core: Less Prompt, More Comprehension

The single highest-leverage change. Replace keyword regex with structured LLM intent extraction, and shrink the supervisor prompt by feeding it structured state instead of rules.

### 0.1 Typed Design Brief (intent extraction node)

- [ ] Define a `DesignBrief` Pydantic model in `agent/models.py`:
  - `building_count`, per-building: `shape_preference` (I/L/T/U/H/Y/X/O or `auto`), `footprint_area_sqm`, `storeys` or `height_m`, `use` (residential/office/mixed), `apartments_per_floor` hint.
  - Site-level: `courtyard_requested` (bool + quality words like "quiet", "sunny"), `parking_requested`, `orientation_preferences`, `requested_positions`.
  - Objective weights: `view_weight`, `sun_weight`, `alignment_weight` — inferred from emphasis in the prompt ("most important is daylight" → sun weight up).
  - `ambiguities`: list of things the brief could not infer, used to drive `await_human` instead of guessing.
- [ ] Add an `extract_brief` LangGraph node that runs **once** at the start: one short system prompt ("Extract a design brief from the user's request; fill the schema; leave unknown fields null; list ambiguities") + the schema. Use structured/JSON-mode output.
- [ ] Replace `_infer_requested_building_type`, `_extract_explicit_building_area_sqm`, `_extract_requested_rotation`, `_mentions_explicit_building_area` call sites with brief lookups. Keep the regex helpers only as an offline fallback when no LLM is configured (tests).
- [ ] Planner (`RuleBasedPlanner`) reads the brief instead of re-parsing `user_prompt`.

### 0.2 Canonical Site Model

- [ ] Define a `SiteModel` structure in `agent/models.py` built once by `read_site` and stored in state: boundary polygon, boundary graph (corners/sides from `site_boundary_graph.py`), per-side metadata (length, orientation, adjacent road if any), setbacks/buildable zone (`site_setback.py`), placement grid (Phase 3), roads (Phase 2), sun context (Phase 1).
- [ ] All downstream tools accept the `SiteModel` (or its sub-objects) instead of raw coordinate lists, so there is one source of truth.

### 0.3 Prompt Diet

- [ ] Rewrite `SUPERVISOR_PROMPT` to ~10 lines: role, the active step goal, the brief, the relevant catalog slice, and "return JSON with this schema". Delete per-tool rules — argument completion already happens deterministically in `_repair_generate_shape_decision`; generalize that repair pattern to all tool families (defaults table per tool in `tool_catalog.py`).
- [ ] Move every "never do X / always do Y" prompt rule into a deterministic guard in the planner or the repair layer. Rule of thumb: if violating the rule is detectable in code, enforce it in code.

### 0.4 Validation

- [ ] Notebook `test_notebooks/test_intent_extraction.ipynb`: table of ≥15 varied short prompts (terse, verbose, vague, contradictory) → extracted brief side by side; show that vague prompts produce `ambiguities` instead of invented values.
- [ ] Regression `benchmarking/test_design_brief.py`: schema validation, fallback parsing path, planner consumption of a brief.
- [ ] Update `PROGRESS.md` + `ARCHITECTURE.md` (new node, new state keys, slimmed prompt).

---

## Phase 1 — Sun Analysis Fitness

Method (per team decision): represent the sun in **one diagonal view** — a single dominant sun vector (azimuth + altitude, e.g. low western sun as the worst case) rather than a full annual simulation. Identify the worst sun exposure direction and let placement/orientation avoid it.

### 1.1 Tool: `agent/tools/sun_analysis.py`

- [ ] `compute_sun_vectors(latitude, date, hours)` → list of `{azimuth, altitude, weight}`; provide a `worst_case_preset` (e.g. summer west, 240°–270° azimuth, low altitude) so the simple "one diagonal" mode works with zero astronomy.
- [ ] `evaluate_sun_exposure(boundary, sun_vectors, obstacles)` — reuse the test-point machinery from `view_analysis.divide_boundary_into_test_points`; for each facade test point, exposure = Σ over sun vectors of `max(0, cos(angle between outward normal and horizontal sun direction)) × weight`, zeroed when an obstacle (with height, projected) blocks the vector. Returns `sun_exposure_score` (0–1, **lower = better** for the avoid-worst-sun objective) and per-test-point detail for visualization.
- [ ] `identify_worst_sun_side(site_model, sun_vectors)` → which site side / compass sector receives the worst exposure (drives "place the building to avoid that worst sun view").
- [ ] Keep a `return_ray_detail=False` fast path for optimizer inner loops (mirror `view_analysis`).

### 1.2 Optimizer integration

- [ ] Extend `optimize_view_placement` / `optimize_two_building_placement` with `sun_vectors` input; objective becomes `F = [-view_score, +sun_exposure_score]` (or fold into the existing combined-score pattern with `sun_weight` from the brief, same way `attractor_weight` works today — weight ranks results, NSGA-II explores the full Pareto front).
- [ ] Mutual shading: pass other buildings (with heights) as sun obstacles, same as the view obstacle pattern.

### 1.3 Validation

- [ ] Notebook `test_notebooks/test_sun_analysis.ipynb`: (a) sun vector drawn as the diagonal arrow over the site, (b) facade test points colored by exposure, (c) worst-sun side highlighted on the site boundary, (d) Pareto front view vs. sun for one building, (e) before/after comparison showing the optimizer rotates/places the building away from the worst sun.
- [ ] Regression `benchmarking/test_sun_analysis.py`: known geometry → expected exposure ordering (south facade > north facade for a southern sun, fully shaded point scores 0, etc.).
- [ ] `PROGRESS.md` + `ARCHITECTURE.md` updates.

---

## Phase 2 — Transportation / Road Context

The agent must know its surroundings — at minimum the biggest road near the site.

### 2.1 Input contract

- [ ] Extend the site input payload (notebook scenarios + `read_site` + future Grasshopper `context_reader`) with `site_objects` of type `road`: `{type: "road", centerline: [[x,y],...], width_m, hierarchy: "main"|"secondary"|"path", name?}`. The notebook-local site readers already support generic site objects — formalize the road schema.

### 2.2 Tool: `agent/tools/road_context.py`

- [ ] `analyze_roads(site_model, roads)` → for each road: nearest site side, distance to site, frontage length (portion of site boundary within `width` buffer). Identify `main_road` = highest hierarchy, tie-break by width then frontage.
- [ ] Tag each site side in the `SiteModel` with `adjacent_road` so prompts/tools can say "the side along the main road".
- [ ] Wire road widths into `site_setback.compute_buildable_zone` (`edge_road_widths` already exists — feed it from real road objects instead of manual dicts).
- [ ] If no road data is provided, record an ambiguity in the brief (ask the user / fall back to "no road context") instead of inventing one.

### 2.3 Validation

- [ ] Notebook `test_notebooks/test_road_context.ipynb`: site + 2–3 roads of different widths; visualize main-road identification, side tagging, and the resulting per-edge setback buildable zone.
- [ ] Regression `benchmarking/test_road_context.py`: main-road selection, side tagging, setback derivation.
- [ ] Docs updated.

---

## Phase 3 — Grid and Side Alignment (No More Random-Looking Placement)

Placement must read as intentional: buildings align to site sides and to a site grid, even when fitness alone wouldn't force it.

### 3.1 Tool: `agent/tools/site_grid.py`

- [ ] `derive_site_grid(site_model, spacing, alignment_side=None)` → grid origin + two axis directions aligned to a reference side (default: the main-road side from Phase 2; fallback: longest side), clipped to the buildable zone. Returns grid lines for visualization and grid-node seed points.
- [ ] `snap_to_grid(point, grid)` and `aligned_orientations(grid)` → the discrete orientation set {parallel, perpendicular} to the grid axes (± small offsets if allowed).

### 3.2 Optimizer integration

- [ ] `sample_valid_placements`: replace the free 5 m sweep + 36 rotations with grid-node positions × aligned orientations when a grid exists (keep the free mode behind a flag for comparison).
- [ ] Add an `alignment_score` (deviation of building long edge from nearest grid axis, normalized) — either a hard restriction (only aligned orientations sampled) or a soft objective weighted by `alignment_weight` from the brief. **Default: hard restriction**; soft mode only when the brief asks for free orientation.
- [ ] Reuse `measure_boundary_proximity` + the existing longest-edge side alignment in `modify_building_boundary` as the repair path when a candidate is slightly off-grid.

### 3.3 Validation

- [ ] Notebook `test_notebooks/test_grid_alignment.ipynb`: diagonal-sided site + main road; show derived grid, seed points, and a side-by-side of free-placement result vs. grid-aligned result for identical fitness inputs (this is the "it doesn't look random anymore" picture).
- [ ] Regression `benchmarking/test_site_grid.py`: grid axes match reference side orientation, all sampled candidates aligned within tolerance.
- [ ] Docs updated.

---

## Phase 4 — Parking

Parking demand derived from apartments per building, allocated as real site area.

### 4.1 Tool: `agent/tools/parking.py`

- [ ] `estimate_apartments(footprint_area, storeys, efficiency=0.8, avg_apartment_sqm=70)` → apartment count per building (overridable from the brief).
- [ ] `parking_demand(apartments, ratio=1.0)` → required stalls; area = stalls × ~25–30 m²/stall (stall + aisle share), constants centralized and documented.
- [ ] `allocate_parking_zones(site_model, buildings, demand)` → rectangular parking polygons placed: (a) inside the buildable zone or setback strip where permitted, (b) preferring frontage near the main road (Phase 2), (c) not overlapping buildings or required clearances. Returns polygons + per-building stall assignment + shortfall if the site can't fit demand.
- [ ] Optimizer hook: parking area becomes an occupied obstacle for subsequent building placement, and a hard feasibility check (`shortfall == 0`) or a reported warning when infeasible.

### 4.2 Validation

- [ ] Notebook `test_notebooks/test_parking_allocation.ipynb`: two buildings with different storey counts → demand table, allocated lots drawn near the main road, shortfall scenario demo.
- [ ] Regression `benchmarking/test_parking.py`: demand math, no-overlap invariant, near-road preference.
- [ ] Docs updated.

---

## Phase 5 — Circulation, Access, and Fire Safety

Access placement should explain *why* a building sits where it sits.

### 5.1 Tool: `agent/tools/circulation.py`

- [ ] `propose_site_entries(site_model)` → public entry point(s) on the main-road side, optional private/service entry on a secondary side. Each entry: point on boundary + type (`public`/`private`).
- [ ] `route_internal_circulation(site_model, entries, buildings, parking)` → drivable internal path network (start simple: straight/L-shaped corridors of min width 4–6 m from entries to each building's entrance side and to parking), returned as polylines + buffered polygons.
- [ ] `check_fire_access(buildings, circulation, max_distance=50, min_path_width=4)` → per building: distance from the drivable network, reachable perimeter ratio, pass/fail. This becomes a **hard constraint** G in the optimizer: every building must be reachable.
- [ ] Building entrance orientation heuristic: entrance facade faces the nearest circulation path / public entry; private/quiet facades (and courtyards, Phase 6) face away.
- [ ] Circulation polygons join parking as occupied obstacles for placement.

### 5.2 Validation

- [ ] Notebook `test_notebooks/test_circulation_fire.ipynb`: entries on main road, routed paths to two buildings + parking, fire-access pass/fail coloring, and one deliberately failing layout showing the constraint rejecting it.
- [ ] Regression `benchmarking/test_circulation.py`: entry-on-main-road invariant, fire distance math, constraint sign convention.
- [ ] Docs updated.

---

## Phase 6 — Courtyard Comprehension

When the brief says "courtyard", the agent should understand it as a spatial goal, not a keyword.

- [ ] Brief: `courtyard_requested` + qualities (sunny/quiet/private) extracted in Phase 0 — no new prompt text needed.
- [ ] Strategy selection (deterministic, given the brief): single-building courtyard (`O`/`U`/`H` footprints, already supported by the generator) vs. multi-building courtyard (bars enclosing a shared open space) depending on building count and area.
- [ ] Tool `agent/tools/courtyard.py`:
  - `extract_courtyard(buildings)` → the enclosed/semi-enclosed open polygon (boundary offset / concave region detection for U/H; interior ring for O; inter-building void for clusters).
  - `courtyard_quality(courtyard_polygon, sun_vectors, roads, circulation)` → enclosure ratio, courtyard sun score (reuse Phase 1 — a "sunny courtyard" wants high exposure *inside* the courtyard, the inverse of facade avoidance), quietness (distance from main road / public entry).
  - Orientation rule: U/H opening faces *away* from the worst-sun side or *toward* the sun for "sunny courtyard" — driven by the brief's quality words.
- [ ] Optimizer: courtyard quality joins the objective set with its brief-derived weight.
- [ ] Notebook `test_notebooks/test_courtyard.ipynb`: U-building courtyard extraction, sunny vs. quiet variants producing different orientations, one multi-building enclosure demo.
- [ ] Regression `benchmarking/test_courtyard.py`. Docs updated.

---

## Phase 7 — 3D Visualization with Per-Wing Heights

E.g., a U building with one wing taller than the others.

- [ ] Extend the wing graph model (`building_shape_graph.py` / `generate_building_boundary.py`): each wing carries `storeys`/`height_m`; building height becomes per-wing, defaulting to uniform.
- [ ] Extend `modify_building_wings.py` with a `set_wing_height(wing_index, storeys)` edit so the agent can answer "make the south wing taller".
- [ ] `view_3d.py`: extrude per wing (one prism per wing polygon instead of one prism per footprint); `evaluate_building_views_3d` and Phase-1 sun shading consume per-wing heights (a tall wing shades its own courtyard — connects directly to Phase 6 quality).
- [ ] Optimizer (optional, behind a flag): wing storey counts as discrete NSGA-II variables with a GFA-target constraint, so "same total area, different massing" trade-offs appear on the Pareto front.
- [ ] Notebook `test_notebooks/test_wing_heights_3d.ipynb`: interactive plotly U-building with one tall wing, per-floor view scores, courtyard shadow comparison between uniform and stepped massing.
- [ ] Regression `benchmarking/test_wing_heights.py`. Docs updated.

---

## Phase 8 — Agent Integration: One Brain, All Tools

Wire everything into the LangGraph runtime so a short prompt drives the full pipeline.

- [ ] New/updated graph steps: `extract_brief` (Phase 0) → `read_site` builds the full `SiteModel` (boundary graph + roads + grid + sun + setbacks in one step) → existing generate/check/optimize/place loop consumes it.
- [ ] Register all new tools in `tool_catalog.py` under proper action groups with default tables, so the generalized argument-repair layer covers them.
- [ ] Fitness assembly: one `build_objectives(brief, site_model)` function decides which F objectives and G constraints are active for this run (view, sun, courtyard quality as objectives; site-fit, setbacks, separation, fire access, parking feasibility as hard constraints; alignment as sampling restriction). The LLM never assembles fitness — it only sets weights via the brief.
- [ ] Report node explains decisions in plain language using the model's facts: "placed along the north grid axis, entrance toward Main Street, courtyard opening east away from the low western sun, 42 stalls allocated on the road frontage".
- [ ] End-to-end notebook `test_notebooks/end_to_end_site_intelligence.ipynb`: one short prompt → brief → site model → optimized, aligned, serviced, courtyard-bearing layout, fully visualized 2D + 3D. This is the demo notebook.
- [ ] Full regression sweep: `python -m unittest discover team_04/benchmarking` green.
- [ ] Major `ARCHITECTURE.md` rewrite of the graph diagram + `PROGRESS.md` entry.

---

## Phase 9 — Frontend Connection (Last)

The FastAPI backend (`backend/app.py`, routers for sessions/chat/explorer/tools/decisions) already exists; extend its contracts to expose the new world model.

- [ ] `backend/schemas.py`: add `SiteModelPayload` (boundary, sides, grid lines, roads, setback zone), overlay payloads (sun rays/exposure, parking polygons, circulation paths, fire-access status), per-wing heights in the explorer `object_hierarchy`, and brief + objective weights in session state.
- [ ] `/sessions/{id}/explorer`: include the new layers so the UI tree shows Site → Roads/Grid/Setbacks → Buildings → Wings (with heights) → Parking/Circulation → Saved options (the `option_catalog` pattern already exists — extend, don't replace).
- [ ] `/tools`: direct invocation endpoints for `sun_analysis`, `road_context`, `site_grid`, `parking`, `circulation`, `courtyard` (mirroring the existing view-tool endpoints) so the frontend can run analyses without a chat turn.
- [ ] SSE chat stream: emit structured progress events per plan step (brief extracted, site analyzed, N candidates, Pareto ready) so the UI can animate the pipeline.
- [ ] Notebook `test_notebooks/test_backend_api.ipynb`: start the API, exercise every new endpoint with `httpx`, render returned payloads — this is the frontend team's living contract documentation.
- [ ] Regression `benchmarking/test_backend_schemas.py` for payload shape stability.
- [ ] Final `PROGRESS.md` + `ARCHITECTURE.md` update including the API contract.

---

## Order and Dependencies

```
Phase 0 (brief + site model + prompt diet)   ← do first, everything reads from it
Phase 1 (sun)        — independent after 0
Phase 2 (roads)      — independent after 0
Phase 3 (grid)       — needs 2 (main-road side picks the grid axis)
Phase 4 (parking)    — needs 2 (near-road allocation), brief from 0
Phase 5 (circulation/fire) — needs 2 + 4
Phase 6 (courtyard)  — needs 0 + 1 (sun quality), benefits from 3
Phase 7 (wing 3D)    — needs 1 (sun shading), enriches 6
Phase 8 (integration)— needs all above
Phase 9 (frontend)   — needs 8
```

Suggested team split: sun (1) and roads (2) can run in parallel right after Phase 0 lands.

## Definition of Done (per phase)

1. Tool module merged with docstrings and centralized constants.
2. Notebook runs top-to-bottom on a fresh kernel and the figures show the capability working.
3. Benchmarking regressions pass deterministically (no LLM/MCP needed).
4. `PROGRESS.md` dated entry + `ARCHITECTURE.md` reflect the change.
5. `git diff origin/main --name-only` shows only `team_04/` paths.
