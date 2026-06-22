# Team 04 Architecture

## Planned Evolution (2026-06-12)

`BACKEND_PLAN.md` defines the phased roadmap from the current view-only placement agent to a site-intelligent backend. **Phase 0 (reasoning core), Phase 1 (sun analysis fitness), Phase 2 (road context), Phase 2b (urban context), Phase 3 (site grid & side alignment), Phase 4 (parking), and Phase 5 (circulation, access & fire safety) are implemented** — see the 2026-06-15 through 2026-06-22 entries in `PROGRESS.md`. The architectural commitments they introduce:

- **Typed `DesignBrief`**: a one-shot LLM extraction node at graph start converts the user prompt into a typed brief (building count, shapes, areas, storeys, courtyard intent, parking, objective weights, explicit ambiguities). Downstream nodes read the brief, never re-parse the prompt; regex intent helpers in `decision_engine.py` become test-only fallbacks.
- **Canonical `SiteModel`**: `read_site` builds one structured site object (boundary graph, per-side metadata, roads, placement grid, sun context, setbacks/buildable zone) that all tools consume — one source of truth instead of raw coordinate lists.
- **Prompt diet**: supervisor prompt shrinks to role + active step + brief + catalog slice; every enforceable rule moves into deterministic planner guards or the argument-repair layer.
- **Fitness assembly**: a deterministic `build_objectives(brief, site_model)` selects active NSGA-II objectives (view, sun, courtyard quality) and hard constraints (site fit, setbacks, separation, fire access, parking feasibility); grid/side alignment restricts the sampling space. The LLM sets weights only, via the brief.
- **New tool families** under `agent/tools/`: `sun_analysis` (Phase 1), `road_context` (Phase 2), `site_grid` (Phase 3), `parking` (Phase 4), `circulation` (Phase 5), `courtyard` (Phase 6), plus per-wing heights in the wing graph and `view_3d`.
- **Frontend in lockstep (revised 2026-06-16)**: the original "frontend last (Phase 9)" rule is superseded — every backend phase that changes a UI-visible contract (a decision-graph node, a site/explorer overlay, an SSE event) ships its frontend counterpart in the **same commit**, under `team_04/frontend/`. Deeper FastAPI contract work (full site-model payload, analysis overlays, per-wing hierarchy) still lands as its phase does. Phase 0's counterpart is the `frontend/decision-graph/` module (`BriefNode` + payload contract).

Each phase lands with a visualization notebook in `test_notebooks/`, deterministic regressions in `benchmarking/`, and same-commit updates to this file and `PROGRESS.md`.

## Canonical Structure

The Team 04 codebase now has a single active LangGraph implementation in `team_04/agent/`.

Old implementations were archived to `team_04/legacy/` on 2026-05-17:
- `legacy/PY_legacy/`
- `legacy/python_legacy/`

This cleanup removes the previous ambiguity where two different graphs, two entry points, and multiple conflicting documents all claimed to be the active agent.

## Design Goals

- One canonical runtime path.
- One graph with explicit planner plus hub-and-spoke execution routing.
- No blocking `input()` calls inside graph nodes.
- Fixed tool policy by action group.
- Deterministic smoke-test coverage without MCP or live LLM access.

## Active Layout

```
team_04/
├── agent/
│   ├── __init__.py
│   ├── brief.py            # Phase 0: regex-fallback DesignBrief extractor
│   ├── clarify.py          # interactive clarification (ask-back) engine
│   ├── config.py
│   ├── decision_engine.py
│   ├── graph.py            # START → extract_brief → planner → …
│   ├── main.py
│   ├── mcp_client.py
│   ├── models.py           # BuildingSpec / DesignBrief dataclasses
│   ├── state.py
│   ├── tool_catalog.py
│   └── tools/
│       ├── site_model.py   # Phase 0: canonical SiteModel (Phase 2 update: auto-runs road_context)
│       ├── sun_analysis.py # Phase 1: worst-sun vectors, 2D + 3D facade exposure, worst side, 3D viz
│       ├── road_context.py # Phase 2: analyze_roads, main-road id, side tagging, edge_road_widths
│       ├── site_grid.py    # Phase 3: grid from a chosen side (Phase 2: main-road side as default)
│       ├── parking.py      # Phase 4: apartment demand, stall counts, road-frontage parking zones
│       ├── circulation.py  # Phase 5: site entries, drivable corridors, entrance orientation, fire access (G<=0)
│       └── view_optimizer.py # NSGA-II + objective registry (view, attractor, sun, alignment, frontage) + aligned placement
├── backend/                # FastAPI app + decision graph + routers
│   ├── app.py
│   ├── agent_runtime.py    # cached compiled agent app for the chat endpoint
│   ├── decision_graph.py   # DAG + make_*_node (incl. make_brief_node)
│   ├── schemas.py
│   ├── session_store.py
│   └── routers/            # sessions, chat (SSE), explorer, tools, decisions, clarify
├── frontend/               # React Flow UI, kept in lockstep with the backend
│   ├── README.md           # lockstep policy + usage
│   ├── package.json tsconfig.json   # self-contained, node_modules git-ignored
│   ├── dashboard/AgentDashboard.tsx # overall view (graph + plan + explorer)
│   ├── decision-graph/     # BriefNode + BasicNodes (incl. ClarifyNode) + nodeTypes/adapters/types + CONTRACT.md
│   ├── site/               # SiteCanvas.tsx + geometry.ts (2D plan)
│   ├── explorer/           # ExplorerPanel.tsx (object hierarchy)
│   ├── clarify/            # ClarifyPanel.tsx (agent ask-back chips)
│   └── api/                # types.ts (mirror schemas) + client.ts (Team04Api)
├── benchmarking/           # deterministic regressions (no LLM/MCP)
├── test_notebooks/         # one visualization notebook per phase
├── legacy/
└── main.py
```

## LangGraph Structure

The graph now separates planning from execution:

```
START
  ↓
extract_brief        # Phase 0: free text -> typed DesignBrief (LLM or regex fallback)
  ├─ (critical gap + interactive_clarification) ─→ await_human → finish → END   # ask the user back
  ↓
planner
  ↓
central_reason
  ├─ read_site ───────┐
  ├─ generate_shape ──┤
  ├─ check_requested_position ─┤
  ├─ check_constraints┤
  ├─ optimize ────────┤
  ├─ evaluate ────────┤
  ├─ place_building ──┤
  ├─ analyze_remaining_positions ─┤
  ├─ await_human ──→ finish → END
  ├─ report ───────→ finish → END
  └─ finish ───────→ END

All tool spokes return to planner, which rebuilds the remaining task sequence.
```

## Node Responsibilities

- `extract_brief`: one-shot intent comprehension at graph start. Converts the raw prompt into a typed `DesignBrief` (LLM via `OpenAIDecisionEngine.extract_brief`, deterministic regex fallback via `agent/brief.py` otherwise). Idempotent; refines `target_building_count`/`building_intents` only when the layout did not provide them. When the run opted in (`interactive_clarification`) and a **placement-critical** field is missing (shape / preferred side / view side), it raises a structured `clarification_request` (`agent/clarify.py`) and routes to `await_human` so the agent asks the user back instead of guessing. `apply_clarification_answers` merges the user's answers onto the brief + layout; `clarification_resolved` makes the resumed run proceed. Implemented in `agent/brief.py` + `agent/clarify.py` + `_build_extract_brief_node`/`_route_from_brief` in `graph.py`.
- `planner`: builds a typed task sequence from current state and selects the active plan step. Reads brief-derived count/intents from state rather than re-parsing the prompt.
- `central_reason`: now acts as a step-scoped supervisor. It only reasons over the active step, and only calls the LLM for `generate_shape` and `optimize`.
- `read_site`: runs the site/context/legal-reader tool group automatically, then builds the canonical `SiteModel` (`agent/tools/site_model.py`) into `state["site_model"]` — boundary graph (corners/sides), per-side `adjacent_road` slots, and the setback/buildable zone, with `roads`/`grid`/`sun` placeholders for Phases 1-3.
- `generate_shape`: executes only allowed shape-generation tool calls. The local boundary generator now supports `I`, `L`, `T`, `Y`, `H`, `X`, and `O` footprints plus direct translation, mirroring, and orientation or rotation parameters.
- `check_requested_position`: evaluates a user-requested placement point for the current building and records geometric feasibility facts.
- `check_constraints`: runs the full constraint suite automatically and derives violation categories.
- `optimize`: executes only allowed manipulation tool calls and increments the optimization cycle counter. The local manipulation fallback now includes `modify_building_boundary_04` for move, orientation, rotation, mirroring, and site-fit checks before the Grasshopper tool is live.
- `evaluate`: runs the full evaluation suite automatically.
- `place_building`: sends the validated building footprint into Rhino/Grasshopper placement tools.
- `analyze_remaining_positions`: queries the remaining site area for candidate locations before the next building cycle begins.
- `await_human`: exits non-interactively with a clarification question in `final_response`.
- `report`: builds the final narrative response.

## Decision Graph and Frontend (Phase 0 counterpart)

The backend tracks each session's design process as a DAG in `backend/decision_graph.py` and exposes it to the UI:

- Node types: `intent → brief → [clarify] → action → branch → select → state`. The **`brief`** node (Phase 0) sits between the user message and the first tool and carries the typed `DesignBrief` in `payload.design_brief`. The **`clarify`** node appears when the agent pauses to ask the user back; its payload holds the structured `clarification_request` the UI renders as chips (`POST /sessions/{id}/clarify` to answer, then resume with a `/chat` turn).
- `backend/routers/chat.py` streams nodes as SSE `decision` events while the agent runs. The live `extract_brief` graph node's `on_chain_end` is detected and emitted as the `brief` node (right after `intent`, before any `action`); it fires only when a brief is freshly comprehended (the node is idempotent and returns `{}` on pass-through).
- `backend/routers/decisions.py` returns the full `{nodes, edges, head}` for `GET /sessions/{id}/decisions`, edges already React-Flow-ready.
- `backend/agent_runtime.py` builds and caches the compiled agent app (engine + tool client + catalog) for the chat endpoint — previously `build_agent_graph()` was called with no arguments and never ran.

The frontend lives under `team_04/frontend/` and gives an "overall view" of the agent — *what it has* and *how it reasoned* — from the existing backend routes:

- `dashboard/AgentDashboard.tsx` — the composed screen: decision graph (left) + 2D site plan (centre) + explorer tree (right).
- `decision-graph/` — `BriefNode.tsx` (Phase 0 comprehension) + `BasicNodes.tsx` (`intent/action/branch/select/state`), registered in `nodeTypes.ts`; `adapters.ts` converts `{nodes,edges,head}` + SSE events into React Flow inputs and runs a built-in `layoutLayered`; `types.ts` mirrors `agent/models.py` + `backend/schemas.py`; `CONTRACT.md` is the payload contract.
- `site/SiteCanvas.tsx` (+ `geometry.ts`) — 2D plan: site boundary, buildable zone, placed buildings coloured by footprint family (I/L/T/U/H/Y/X/O), and the focused building's Pareto view-placement options as ghosts. This is where multi-building layouts, generated boundaries, shape transformations, and view-based placement become visible.
- `explorer/ExplorerPanel.tsx` — Site → buildings → wings / view scores / Pareto option table, from `GET /sessions/{id}/explorer`.
- `clarify/ClarifyPanel.tsx` — renders the agent's structured ask-back question as chips and POSTs answers to `POST /sessions/{id}/clarify`; `ClarifyNode` shows the pause in the decision graph.
- `api/` — `types.ts` (mirror `backend/schemas.py`) + `client.ts` (`Team04Api`, typed client for every JSON route).

Per the lockstep policy, each later phase adds its node/overlay component and a `CONTRACT.md` row in the same commit it lands the backend capability.

## Sun Analysis Fitness (Phase 1)

`agent/tools/sun_analysis.py` adds the "avoid the worst sun" capability. Per the team decision the sun is **one dominant diagonal vector** (a single azimuth + altitude — the low west-south-west summer sun as the worst case) rather than an annual simulation:

- `compute_sun_vectors` / `worst_case_sun_vector` (+ `WORST_CASE_PRESETS`) returns the dominant vector with zero astronomy, or computes a real multi-hour set from a lightweight solar-position formula when `latitude`/`date`/`hours` are given.
- `evaluate_sun_exposure` reuses `view_analysis.divide_boundary_into_test_points`; each facade point's exposure is `Σ max(0, cos(altitude)·cos(Δ))·weight`, zeroed when an obstacle's height-projected shadow blocks the vector. Returns `sun_exposure_score` ∈ [0,1] where **lower is better**, with a `return_ray_detail=False` fast path mirroring the view tools.
- `identify_worst_sun_side` scores each `SiteModel` side and names the worst/best edge + compass sector — the direction sensitive facades (and Phase 6 courtyards) should turn away from.
- `evaluate_sun_exposure_3d` is the practical multi-building path: it reuses `view_3d.build_facade_cells` to grid each side face by floor and does **real per-floor mutual shading** — an obstacle of height `h` shades a cell at height `z` only when `h > z` (shadow reach `(h-z)/tan(altitude)`), so a tall tower shades just the lower floors of a shorter neighbour. `visualize_sun_3d` renders the plotly 3D scene (facades as a continuous exposure heatmap + the sun vector at its true altitude), mirroring `view_3d.visualize_3d`. The 2D and 3D split mirrors `view_analysis`/`view_3d`: 2D is the optimizer inner loop, 3D is the post-hoc evaluation/visualization.

The optimizer gains a `sun_avoidance` objective in `view_optimizer.OBJECTIVE_REGISTRY` (`1 - sun_exposure_score`, so it folds into the existing higher-is-better combined-score pattern alongside `unblocked_view`/`attractor_view`). `optimize_view_placement`/`optimize_two_building_placement` accept `sun_vectors` + `sun_weight`: single-building runs a true view-vs-sun Pareto front; two-building combines view + sun and inherits **mutual shading** because each building is already passed as the other's obstacle — so the joint NSGA-II returns a layout optimal for view *and* sun together. Consistent with the "Fitness assembly" commitment, the LLM only sets `sun_weight` (via the brief) — the geometry stays deterministic. Graph-node auto-assembly of the objective and populating `site_model["sun"]` are deferred to Phase 8.

The lockstep frontend counterpart is `frontend/site/SunOverlay.tsx` (sun arrow + facade-exposure points + worst-side highlight), fed by the direct-tool endpoints `POST /tools/{sun_vectors,sun_exposure,worst_sun_side}` (see `frontend/decision-graph/CONTRACT.md` §7).

## Road and Transportation Context (Phase 2)

`agent/tools/road_context.py` gives the agent situational awareness: it knows which side of the site faces the street and how big that street is. Road objects (`{type:"road", centerline, width_m, hierarchy:"main"|"secondary"|"path", name?}`) are supplied via `site_objects` in the layout payload and analysed once when `build_site_model` runs:

- `validate_road(road)` normalises and validates a single road dict (unknown hierarchy → `"secondary"`, bad width → `DEFAULT_ROAD_WIDTH_M`, raises on missing centreline).
- `analyze_roads(site_model, roads)` — for each road computes: nearest site side (Shapely distance + **projected-frontage tie-break** so a parallel road wins over one that merely ends near a corner), `distance_m`, and `frontage_m` (projected overlap with the side in the side's own direction). Roads are ranked by `(hierarchy_rank, width_m, frontage_m)` — the **main road** (highest priority) drives placement. Returns:
  - `main_road` + `main_road_side_index` — the single most important road and the site side it fronts.
  - `edge_road_widths` `{side_index: width_m}` — consumed by `site_setback.compute_buildable_zone` so the road-adjacent side's setback is `max(min_setback, width × road_setback_ratio)` instead of the generic default.
  - `updated_sides` — a copy of `site_model["sides"]` with each side's `adjacent_road` slot filled (or `null` when no road is close enough).
  - `ambiguity="no_road_data"` when no roads are provided — the agent records the gap instead of inventing a road.

`build_site_model` (Phase 0 tool, updated Phase 2) now:
1. Extracts `site_objects` of `type == "road"` from `layout_payload`.
2. Calls `analyze_roads` and stores the result in `model["roads"]`.
3. Propagates `updated_sides` back to `model["sides"]`.
4. Merges road-derived `edge_road_widths` with explicit payload overrides before calling `setback_summary`.

`derive_site_grid` (Phase 3 tool, updated Phase 2) now uses **`main_road_side_index`** as the default `alignment_side` when a road is present, so the placement grid is automatically parallel to the real street. Priority: explicit `alignment_side` > main-road side > longest-side fallback.

The lockstep frontend counterpart is `frontend/site/RoadOverlay.tsx` (road centrelines coloured by hierarchy, width buffers, site sides painted by adjacent road colour, main-road side bold), fed by `POST /tools/road_context` (see `frontend/decision-graph/CONTRACT.md` §9). `Team04Api.roadContext(siteModel, roads)` wraps the call; types are `RoadData`, `RoadAnalysis`, `RoadContextResult` in `api/types.ts`.

## Urban Context Analysis (Phase 2b)

`agent/tools/urban_analysis.py` and `agent/tools/osm_context.py` give the agent a full understanding of the **urban condition** of its site — not just which roads are adjacent (Phase 2) but what kind of corner, junction, or frontage situation it is in and what architectural response that demands.

**OSM data layer** (`osm_context.py`):
- `fetch_urban_site(lat, lon, radius_m)` — queries the Overpass API for the road network in a bounding box, converts lat/lon to local metres, and infers intersections from OSM node degree (a node shared by ≥3 ways = junction). Returns roads + intersections in the canonical Phase 2 schema.
- `fetch_or_fallback(…, fallback_index)` — wraps the fetch with graceful degradation to one of three `SYNTHETIC_SITES` on any network failure. The same `build_urban_site` pipeline runs on either path, so offline notebooks and live data are handled identically.
- `SYNTHETIC_SITES` — three offline-safe presets with back roads placed beyond the 20 m adjacency margin so only the street-facing sides get tagged: (0) crossroads corner, (1) T-junction terminal, (2) triangular corner.
- `INTERESTING_SITES` — eight famous real-world presets (Eixample Barcelona, Le Marais Paris, Flatiron New York, Bloomsbury London, Jordaan Amsterdam, Beyoglu Istanbul, Melbourne CBD, Shinjuku Tokyo).

**Classification layer** (`urban_analysis.py`):
- `detect_intersections_from_roads(roads, snap_dist_m)` — pairwise Shapely line intersection + endpoint snap; **arm counting** (pass-through = 2 arms, terminus = 1) gives the correct junction degree so a T-junction is degree 3, not 2.
- `find_frontages(site_model, roads_result)` — reads Phase 2 `updated_sides`; `visibility_score` ∈ [0,1] (hierarchy rank 40% + road width 30% + projected frontage 30%).
- `classify_site_type(frontages, near_ix, site_model)` — 9-way: `corner`, `crossroads_corner`, `t_junction_terminal`, `y_junction`, `triangular_corner` (inter-frontage angle < 45°), `linear`, `back_parcel`, `cul_de_sac`, `complex`.
- `analyze_corner_conditions` — visibility score + `is_gateway` flag (True when a `"main"` road is involved) per shared corner.
- `analyze_access` — vehicle / pedestrian / service access point at each frontage midpoint with `notes`.
- `generate_urban_response(site_type, …)` — 9 architectural response templates per site type: `building_response`, `entry_strategy`, `facade_strategy`, `corner_treatment`, `gateway_corners`.
- `full_urban_analysis(site_model, roads, intersections)` — master function; reads `site_model["roads"]` (Phase 2), detects or uses provided intersections, classifies, runs all sub-analyses.

The lockstep frontend counterpart is `frontend/site/UrbanAnalysisOverlay.tsx` (road centrelines offset outward by hierarchy, site sides heatmapped yellow→teal by visibility score, intersection markers ✕/T/Y/✦ coloured by type, corner condition dots sized by visibility with red border for gateway, access symbols ▶/♟/⚙, urban response badge, legend), fed by `POST /tools/urban_analysis` (see `frontend/decision-graph/CONTRACT.md` §10). `Team04Api.urbanAnalysis()` and `fetchUrbanSite()` wrap the calls; interfaces are in `api/types.ts`.

## Site Grid & Side Alignment (Phase 3)

`agent/tools/site_grid.py` makes placement read as *intentional* instead of random. Real buildings sit on a site grid, parallel to a preferred boundary — so the agent no longer rotates footprints freely inside the plot:

- `derive_site_grid(site_model, spacing, alignment_side=None)` builds a grid from a **chosen side** (priority: explicit `alignment_side` > main-road side from `site_model["roads"]` (Phase 2) > longest-side fallback), with two orthonormal axes, lattice seed nodes clipped to the buildable zone, and grid lines for drawing. It works on arbitrary non-orthogonal polygons.
- `aligned_orientations(grid)` is the discrete {parallel, perpendicular} set — the only orientations a building may take. `alignment_score`/`snap_to_grid`/`align_building_to_grid` support scoring and placement.
- `corner_interior_angle`/`corner_wing_rotation` let a winged footprint (an L) follow a splayed corner: the free wing rotates to the *adjacent* side, so the arms spread to the corner's interior angle (obtuse on a non-orthogonal site) rather than a rigid 90°. This reuses the existing `parametric_shape` `end_rot` lever.
- `derive_adaptive_site_grid(site_model, spacing|divisions, alignment_side=None)` is the **warped** generalisation: a single rigid angle cannot stay parallel to every edge of a splayed plot, so this fits a **transfinite (Coons) patch** to the site's four principal edge-chains (the sharpest four corners frame the quad; extra vertices fall inside the chains, where the taper lives). Grid lines bend to follow the boundary and the **local axis angle varies across the field** (`angle_range_deg` reports the swing; ≈ 0 on a rectangle, where it degenerates to the uniform grid). `local_grid_orientation(grid, point)` returns the per-node local direction and `align_building_to_local_grid` drops a *rigid* footprint oriented to it (optionally + a `corner_wing_rotation` bend).
- **Placement is rigid, grid-aligned, and oriented by function (current default).** On the **straight** grid (`derive_site_grid`, lines exactly parallel/perpendicular to a chosen side), `orientation_for_function` / `place_building_by_function` rotate a footprint to one of the two grid-aligned orientations from its *use*: `FUNCTION_FRONTAGE` maps **commercial/retail → long side parallel** to the chosen side (street frontage) and **residential/office → perpendicular** (deeper plan, light + privacy); `building_long_axis_deg` (bbox long side) gives the stable dominant axis. The agent asks the user the function and passes `function=`. Rectilinear shapes (I/L/T/U/H) sit perfectly square to the side; diagonal-armed Y/X/O keep their inherent arms and align by their dominant axis. The warped-grid modes below remain in the backend but are no longer used by the notebooks (the user rejected the distortion).
- **Buildings flex gently, keeping their shape (deprecated for placement).** Two warped-grid modes use the warped grid as a guide, never a rubber sheet:
  - `align_building_to_local_grid` (rigid) rotates a footprint to the local grid direction at its node, preserving the **exact** shape, area, and vertex count.
  - `conform_building_to_grid` (gentle, default) maps the footprint into a **local `(s, t)` window sized to its real extent** via the grid's local Jacobian, then blends rigid↔conformed by a `bend` knob ∈ [0,1]. The building's arms gently follow the grid's curvature while **keeping their width, recognisable shape, and area (within a few %)** — for every library shape (I/L/T/U/H/Y/X/O). On a rectangle the patch is affine so conform == rigid (zero distortion); `bend=0` is exactly rigid. An L can additionally bend a free wing (`corner_wing_rotation`) for an obtuse corner.
  - (A *full* footprint-conforming experiment that pushed the whole polygon through the global Coons patch with a fixed bbox window was **removed** — it rubber-sheeted X/Y and blew up their area 4–9×. The Jacobian-local + blend approach is the size-preserving replacement.) The building thus *deforms* to fit the plot, and manipulation (move / stretch / reshape) happens in `(s, t)` / cell space with the world footprint re-conforming automatically. On a rectangle the map is affine, so edges stay straight — conforming is a strict generalisation of rigid placement. Internals: `_coons_inputs`/`_coons_eval` are shared by the grid and the mapper. `_select_quad_corners` **always anchors the bottom chain on the chosen alignment side** (the other two corners split the opposite arc into thirds), so re-keying the grid to a different side actually moves the grid — and any building on it — to follow that side, rather than drifting to whichever corners are sharpest.

The optimizer replaces the free 5 m sweep + 36 rotations with grid-aligned placement. `sample_valid_placements(grid=...)` enumerates grid nodes × aligned orientations (hard restriction by default). Because that discrete set is small, `optimize_aligned_placement` ranks it **exhaustively** (exact, deterministic, no NSGA-II) with a use-driven objective mix from `OBJECTIVE_REGISTRY`: the new `grid_alignment` and `boundary_proximity` objectives join view/sun, and commercial/office/retail/mixed buildings get a strong `boundary_proximity` weight so they line the chosen frontage while residential leans on view + sun. `place_buildings_aligned` sequences two-or-more buildings, each aligned and clearing the rest. This is the same "Fitness assembly" pattern (the LLM sets weights/use via the brief; geometry stays deterministic) and the same 2D-now / graph-integration-Phase-8 split as Phases 1. The lockstep frontend counterpart is `frontend/site/GridOverlay.tsx` via `POST /tools/{site_grid,aligned_placement}` (`CONTRACT.md` §8).

## Circulation, Access & Fire Safety (Phase 5)

`agent/tools/circulation.py` makes access placement explain *why* a building sits where it sits, building on the Phase 2 main-road side and the Phase 4 parking zones. Like every other tool family it is pure geometry (Shapely in / dict out), deterministic, no LLM:

- `propose_site_entries(site_model)` places a **public** entry at the midpoint of the main-road side (with an inward normal) and, when a `secondary`/`path` road tags another side, an optional **private/service** entry there. Without road context it falls back to the longest side and reports `ambiguity="no_road_data"` rather than inventing a street.
- `route_internal_circulation(site_model, entries, buildings, parking)` grows a connected tree of straight/L-shaped drivable corridors (`DEFAULT_PATH_WIDTH_M = 6 m`): each target (building entrance point, then each parking zone, nearest first) connects to the nearest point on the network so far, with the L-corner kept inside the site. It returns centreline polylines, buffered corridor polygons (clipped to the site), and `occupied_polygons` so the corridors join parking as obstacles for subsequent placement.
- `building_entrance_orientation(buildings, entries, circulation)` is the entrance heuristic: the entrance facade faces the nearest circulation path (or nearest public entry when no path exists), and the private/quiet facade (and, in Phase 6, the courtyard) faces the opposite `private_direction`.
- `check_fire_access(buildings, circulation, max_distance=50, min_path_width=4)` is the hard fire-safety constraint. Only paths ≥ `min_path_width` qualify as appliance access; each building reports its nearest-point distance to the drivable network, a reachable-perimeter ratio, and `constraint_value = distance − max_distance`. Following the optimizer's `G ≤ 0` convention, ≤ 0 means reachable; `all_pass` / `max_constraint_value` summarise feasibility so Phase 8 can fold it in as a hard constraint that rejects any layout with an unreachable building.

Same 2D-now / graph-integration-Phase-8 split as Phases 1–4: the tools and the four direct-tool endpoints (`POST /tools/{site_entries,route_circulation,entrance_orientation,fire_access}`) are ready; wiring fire access into `build_objectives` as a hard `G` and feeding `occupied_polygons` back into `sample_valid_placements` lands in Phase 8.

## Why This Structure

This rewrite keeps LLM work where it adds value and removes it where policy should be deterministic:

- global sequencing is handled by the planner;
- per-building architectural intent can now be carried in state, so the planner can distinguish the narrative goals of building 1 vs building 2;
- local repair and generation choices stay in the execution supervisor;
- constraint and evaluation bundles are automatic spokes;
- user-requested positions are treated as a first-class workflow step rather than an ad hoc prompt detail;
- tool permissions are enforced by action group rather than prompt wording alone;
- the supervisor only sees the active step's tool family, which reduces prompt bloat as the MCP tool surface grows;
- human clarification is represented as graph state, not terminal I/O.

## Workflow Guardrails

The graph enforces several invariants even if the LLM chooses poorly:

- site context must exist before geometry work;
- geometry must exist before constraint or evaluation work;
- requested position checks use stable site-boundary state rather than transient tool output state;
- every new geometry revision must pass through constraints before evaluation;
- in multi-building mode, the planner now sequences `generate -> requested position check -> constraints -> optimize if needed -> evaluate -> place -> analyze remaining positions -> repeat/report`;
- active violations force optimization until the cycle limit is reached;
- explicit `replan_required` conditions are raised after major state changes so the planner refreshes the remaining task sequence;
- evaluation must happen before final reporting when the design is valid.

## Entry Points

- `team_04/main.py`: top-level convenience entry point.
- `team_04/agent/main.py`: canonical runtime entry point.

## Validation

The rewrite includes a deterministic smoke test in `team_04/tests/test_agent_graph.py`.

Focused geometry regression coverage also lives in `team_04/tests/test_boundary_tools.py`.

Live Rhino or Grasshopper connectivity for the context-reader surface can now be checked with `team_04/tests/test_context_reader_live.ipynb`.

It validates:
- planner plus supervisor completion through shape generation, constraint repair, evaluation, and reporting;
- non-blocking `await_human` behavior;
- multi-building sequencing through requested-position checks, placement, and remaining-site analysis.
- all requested local shape families (`I`, `L`, `T`, `Y`, `H`, `X`, `O`) keep the requested footprint area;
- the new boundary-transformation tool can move, orient, rotate, and mirror a building, then classify whether the transformed footprint still fits inside the site boundary.
- notebook-level OpenAI credential loading, MCP reachability, live `context_reader` tool discovery, and direct tool execution against Rhino or Grasshopper.

## Local Geometry Tooling

The active local geometry tool surface now includes two complementary Python tools before the Grasshopper equivalents are complete:

- `agent/tools/generate_building_boundary.py`: generates one closed footprint boundary at the origin, with optional direct rotation, orientation, mirroring, and translation parameters.
- `agent/tools/modify_building_boundary.py`: transforms an existing boundary by centroid move, relative translation, rotation, orientation, and mirroring, then reports whether the transformed polygon leaves or intersects the site boundary.

These tools are exposed through the canonical local tool client in `agent/mcp_client.py`, so notebooks and planner flows can exercise generation and transformation logic without waiting for the Swiftlet bridge.

## Notebook Coverage

Team 04 now has three active notebook harnesses for geometry workflows:

- `notebooks/test_generate_building_boundary.ipynb`: single-building boundary generation and Grasshopper handoff.
- `notebooks/test_two_building_workflow.ipynb`: two-building placement sequencing with requested-point checks and remaining-position analysis.
- `notebooks/test_multi_building_shape_transformations.ipynb`: many-building stress test across `L`, `I`, `Y`, `T`, `H`, `X`, and `O`, including move, orientation, rotation, mirroring, and site-fit checks.

There is also one live notebook harness under `team_04/tests/` for direct MCP verification:

- `tests/test_context_reader_live.ipynb`: validates Team 04 environment loading, OpenAI connectivity, Swiftlet MCP discovery, and a direct live call to the `context_reader` Grasshopper tool.