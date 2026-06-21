# Team 04 Progress

## 2026-06-04 Remaining-Area-Driven Second Building Seed

### Completed

- [x] Updated the `generate_shape` repair path so later buildings now consume `remaining_candidate_positions` as a concrete `location_xy` hint instead of only waiting for the remaining-area analysis to exist.
- [x] Made the later-building seed selection prefer the candidate nearest the active requested position when one exists, and otherwise choose the candidate that stays farthest from already placed building centroids.
- [x] Added a focused regression that proves building 2 inherits a remaining-area centroid hint during `generate_building_boundary` repair.
- [x] Added a deterministic dev-notebook section that visualizes remaining centroid candidates and the selected seed point for building 2.

### Active MVP Status

- [x] Building 2 generation is now biased toward the analyzed remaining site area rather than regenerating from the site-wide default origin.
- [ ] Remaining-area analysis is still grid-sampled and centroid-based; it is not yet a true remaining-polygon clustering or packing strategy.

### Validation

- [x] Ran `C:/Users/baoqt/miniconda3/python.exe -m unittest team_04.benchmarking.test_agent_graph` after the planner repair patch and all 14 tests passed.
- [x] Executed the new dev-notebook remaining-area seed demo and confirmed it produced 12 feasible candidates with the selected seed at `[69.0, 51.0]` for the requested second-building position `[92.0, 44.0]`.

## 2026-06-04 Site Boundary Graph And Proximity Tools

### Completed

- [x] Added `analyze_site_boundary` so site boundaries are broken into stable corner nodes and side edges that prompts, tools, and explorer-style UI can reference explicitly.
- [x] Added `measure_boundary_proximity` so the backend can report nearest site side, nearest corner, and explicit side-by-side proximity distances from a building boundary to the site boundary.
- [x] Extended `modify_building_boundary` with a side-directed move mode that can move a building toward a named site side using either a target side label or side index.
- [x] Extended `modify_building_boundary` again so the building's longest edge can align to a preferred site side before the side-directed move is applied.
- [x] Added site-boundary graph context into the notebook-local site readers so notebook-driven runtime tests can reference named site corners and sides.
- [x] Added a deterministic dev-notebook demo that moves a building toward `side_0`, labels the site corners, and shows before/after proximity to the selected site side.
- [x] Updated the dev-notebook demo to use a harder diagonal-sided site, draw very thin before-and-after proximity lines, and align the building's main edge to the preferred diagonal side while keeping the moved result inside the site.

### Validation

- [x] Ran `C:/Users/baoqt/miniconda3/python.exe -m unittest team_04.benchmarking.test_boundary_tools` and all 15 tests passed.
- [x] Ran `C:/Users/baoqt/miniconda3/python.exe -m unittest team_04.benchmarking.test_agent_graph` and all 13 tests passed.
- [x] Executed the new dev-notebook summary cell and confirmed the selected site-side clearance changed from about `12.83 m` to `4.0 m`.
- [x] Executed the new dev-notebook figure cell and confirmed the named site side, site corners, original boundary, and moved boundary render together.
- [x] Added a regression that checks longest-edge alignment against a diagonal site side.
- [x] Executed the updated dev-notebook diagonal-side demo and confirmed the selected side clearance changes from about `18.17 m` to `10.0 m` while `fits_within_site_boundary` remains true.

## 2026-06-04 Backend Explorer Payloads And Saved Optimization Options

### Completed

- [x] Extended `generate_building_boundary` so optimization runs persist a small catalog of saved placement options instead of returning only the single selected solution.
- [x] Added `option_catalog` and `object_hierarchy` to the generated building payload so a frontend explorer sidebar can browse buildings, wings, graph objects, and saved placement options without reconstructing them from raw geometry.
- [x] Propagated the same sidebar-ready snapshot into `placed_buildings` so placed results keep their saved options and hierarchy metadata.
- [x] Added focused regression coverage for saved options, explorer hierarchy payloads, and placement snapshot propagation.

### Validation

- [x] Ran `C:/Users/baoqt/miniconda3/python.exe -m unittest team_04.benchmarking.test_boundary_tools team_04.benchmarking.test_agent_graph` and all 24 tests passed.
- [x] Confirmed no language-server errors in the touched backend and regression files.

## 2026-06-04 Shape Edit Test Matrix And Final Notebook Direction

### Completed

- [x] Clarified the current dev notebook so the end-wing rotation demo only edits the intended wing.
- [x] Added labeled notebook views for wing indices, graph node degrees, edge labels, and the selected rotation pivot.
- [x] Extended the notebook-local site context helpers so end-to-end notebook scenarios can include site objects such as streets and alignment guides.
- [x] Reworked `test_notebooks/end_to_end_api_agent.ipynb` into a prompt-driven LangGraph node notebook with scenario selection, notebook-local site objects, and a two-building scenario.

### Active MVP Status

- [x] Team 04 now has a concrete wing-edit demo that rotates a leaf wing around its graph-derived base node.
- [ ] Team 04 still needs a broader test matrix across more footprint families and more wing-local edit types.
- [ ] The final notebook target is now a React-style agent-node loop that keeps trying placement actions until the generated building footprint fits inside the site boundary.

### Next Test Coverage

- [ ] Test additional shapes through the same graph-backed workflow, starting with `L`, `T`, `H`, `I`, and at least one non-winged fallback shape such as `Y` or `X`.
- [ ] Add notebook and regression coverage for single-wing edits on both left and right end wings so pivot behavior is checked on both sides.
- [ ] Add coverage for sequential edits on one building, such as rotate then extend, or thicken then rotate, so graph updates are checked after each step.
- [ ] Add explicit tests for no-op edits and invalid edit requests so the tool surface fails clearly when a wing index or parameter is unsupported.

### Next Modification Coverage

- [ ] Add wing length extension tests.
- [ ] Add edge-angle or bend-style rotation tests anchored to graph nodes.
- [ ] Add joint-aware width changes so edits near shared nodes do not create ambiguous overlap behavior.
- [ ] Add mixed modification tests that combine wing-local edits with whole-boundary placement or orientation changes.
- [ ] Add explicit building-level modification coverage for whole-footprint rotation, orientation changes, mirroring, and translate-plus-rotate sequences through `modify_building_boundary`.
- [ ] Add notebook demos for building-level rotation requests, building-level mirror requests, and alignment-oriented transforms so user prompts that target the whole footprint have a clear validation path.
- [ ] Add notebook coverage that compares wing-local edits against building-level edits so Team 04 can see when a request should stay at the wing graph level versus when it should switch to the whole-building tool.

## 2026-06-04 End-to-End Notebook Validation

### Plan

- [x] Re-run `test_notebooks/end_to_end_api_agent.ipynb` with live Team 04 LLM settings.
- [x] Fix the first end-to-end runtime error in the active LangGraph execution path.
- [ ] Re-run the live agent cell to completion after valid Cloudflare account configuration is present.

### Completed

- [x] Fixed Team 04 graph tool-call hydration so site-aware tools receive `site_boundary` when it already exists in agent state.
- [x] Restarted the notebook kernel and re-ran the end-to-end notebook through the main agent cell.
- [x] Confirmed the notebook now gets past the earlier `analyze_site_boundary()` missing-argument failure.

### Active MVP Status

- [x] The end-to-end notebook now clears the local graph wiring failure that blocked the `read_site` step.
- [ ] The live Cloudflare-backed planner/supervisor call is still blocked by placeholder account configuration in Team 04 `.env`.

### Validation

- [x] Executed the notebook bootstrap, settings, helper, scenario, and main agent cells after the graph fix.
- [x] Confirmed [team_04/agent/graph.py](c:/Users/baoqt/OneDrive/Documents/GitHub/AIA26_Studio/team_04/agent/graph.py) reports no static errors after the patch.
- [x] Observed the main agent cell fail later at the LLM call with a Cloudflare `404` route error for `accounts/your_cloudflare_account_id`.

### Deferred

- [ ] Replace the placeholder `CF_ACCOUNT_ID` and provider credentials in Team 04 environment config, then rerun the live notebook agent cell.

## 2026-06-06 End-to-End Recursion Fix

### Plan

- [x] Reproduce the notebook `GraphRecursionError` on the current Team 04 runtime.
- [x] Patch the planner and graph state so empty remaining-position analyses do not stay pending forever.
- [x] Re-run focused tests and the live notebook scenario.

### Completed

- [x] Identified the looping branch at `analyze_remaining_positions` after the first placement when no candidate positions were returned for the second building.
- [x] Added explicit state tracking so remaining-site analysis is considered complete even when it returns an empty list.
- [x] Reset that analysis marker when a new placement cycle starts.

### Validation

- [x] Ran `C:/Users/baoqt/miniconda3/python.exe -m unittest team_04.benchmarking.test_agent_graph` and all 15 tests passed.
- [x] Added a regression that covers the empty remaining-position case for the planner.
- [x] Re-ran the live end-to-end Team 04 scenario and confirmed it now exits cleanly instead of hitting `GraphRecursionError`.

### Active MVP Status

- [x] `test_notebooks/end_to_end_api_agent.ipynb` main agent cell now completes on the current two-building scenario.
- [ ] The current scenario still places only one building because the remaining-site analysis returns no viable second-building positions, so the workflow exits without a second placement.

### Notebook Direction

- [ ] Create a final test notebook where the controlling loop is framed as a React-style agent node test for the LangGraph runtime, repeatedly inspecting site-fit feedback and calling placement or modification tools until the footprint fits the site boundary.
- [ ] In that final notebook, log each attempted action, the returned site-fit summary, and the final accepted placement so the placement loop is visually inspectable.
- [ ] In that final notebook, keep the focus on one LangGraph node behavior at a time: take the current prompt and state, choose one action, call one tool family, inspect the result, and decide whether to loop, stop, or escalate to another modification strategy.
- [ ] Extend that node-test notebook toward two-building placement by adding a second-building pass after the first footprint is accepted inside the site boundary.
- [ ] Add site objects such as streets, edges, or alignment guides into the notebook input payload so later prompts can request building alignment to those site objects.
- [ ] Keep `tool_dev_mode.ipynb` focused on deterministic local tool and geometry debugging, and reserve the final loop notebook for iterative agent-style placement behavior.

### Current Next Notebook Target

- [x] Reworked `test_notebooks/end_to_end_api_agent.ipynb` into the current prompt-driven LangGraph node harness with scenario selection, two-building intent, and notebook-local site-object inputs.

## 2026-06-06 View Analysis and Multi-Objective Placement Optimization

### Completed

- [x] Created `team_04/agent/tools/view_analysis.py` — perpendicular ray casting evaluation tool.
  - `divide_boundary_into_test_points`: splits each boundary segment into `round(len / piece_length)` pieces, places a test point at each midpoint, computes outward normal via CCW right-perpendicular `(dy/len, -dx/len)`.
  - `evaluate_building_views`: casts one ray per test point in the outward-normal direction (no diagonal fan), checks intersection against all obstacles using `unary_union` fast path in optimization mode, returns `view_score` (0–1) and per-test-point detail.
  - Supports `return_ray_detail=False` for fast optimizer inner loops.

- [x] Created `team_04/agent/tools/view_optimizer.py` — seed-point model + NSGA-II optimizer.
  - `sample_valid_placements`: grid sweep (5 m step) × 36 discrete rotations (10° steps), keeps only positions where `site.contains(building)` — the "seed points" step before any view analysis.
  - `rank_placements_by_view`: evaluates each valid seed candidate and sorts by `view_score` descending.
  - `optimize_view_placement`: single-building NSGA-II, F=[-view_score, -clearance], G=[outside_area<=0].
  - `optimize_two_building_placement`: joint two-building NSGA-II.
    - F[0]=-view_score_1, F[1]=-view_score_2 (Pareto shows trade-off between buildings).
    - G[0]=outside_area_1<=0, G[1]=outside_area_2<=0, G[2]=overlap<=0 (hard constraints — infeasible solutions never appear in results).
    - Each building's boundary is passed as obstacle to the other's `evaluate_building_views` call.
    - Post-processing filter `oa > 0.5` additionally drops any outside-site solutions that leak through.
  - Rotation: discrete `int(x[rot_idx]) * 10°`, 36 options, reduces parameter space vs. continuous.

- [x] Created `team_04/test_notebooks/test_view_analysis.ipynb` — full end-to-end test notebook.
  - Scene: 100×100 m site, L-shape building 1, rectangle building 2, 2 external obstacles (East, North).
  - Section 2: raw `evaluate_building_views` comparisons (no obstacle → ext obstacles → mutual obstruction).
  - Section 3: visualization with perpendicular arrow rays (green = clear, red = blocked).
  - Section 4: `sample_valid_placements` demo — all valid seed centroids scatter-plotted by view score, best seed highlighted.
  - Section 5: NSGA-II run with correct formulation (F=view trade-off, G=hard constraints).
  - Section 6: Pareto front plotted as B1 view score vs. B2 view score (not avg vs. outside area).
  - Section 7: top 3 Pareto solutions rendered as site maps with rays.

### Design Decisions

- **No auto-alteration**: optimizer presents options; the LLM or user selects which placement to keep. The system never silently relocates a placed building.
- **Hard site-fit constraint**: `outside_area` is in G (hard inequality), never in F (Pareto objective). NSGA-II constraint-domination ensures all returned solutions are fully inside the site.
- **Perpendicular rays only**: single outward-normal ray per test point, no diagonal fan. Matches the intent of "view to outside" from each facade piece.
- **Seed-point model**: `sample_valid_placements` pre-computes all valid discrete positions before any view analysis begins. These are the only positions the system ever works with.

### Active MVP Status

- [x] `view_analysis.py` — perpendicular ray evaluation working, tested manually.
- [x] `view_optimizer.py` — site-fit hard constraint enforced, seed-point precomputation working.
- [x] `test_view_analysis.ipynb` — complete notebook with seed-point demo, correct Pareto front formulation.
- [x] Attractor view objective added (2026-06-06) — see below.
- [ ] `view_analysis.py` and `view_optimizer.py` are not yet wired into the LangGraph MCP tool catalog (agent cannot call them via LLM prompt yet).
- [ ] No regression tests for view analysis tools in `benchmarking/`.

## 2026-06-06 Site Setbacks, Building Clearance, and 3D View Analysis

### Completed

- [x] Created `team_04/agent/tools/site_setback.py` — per-edge setback computation.
  - `compute_buildable_zone(site_boundary, *, default_setback, edge_setbacks, edge_road_widths, road_setback_ratio, min_setback)` — cuts the site polygon inward per-edge using the CCW inward normal `(-dy/L, dx/L)`. Returns a Shapely `Polygon` (the buildable zone).
  - Priority: `edge_setbacks[i]` > `road_width × ratio` > `default_setback`.
  - Heuristic: `setback = max(min_setback, road_width × 0.4)` — 20 m road → 8 m setback.
  - `setback_summary()` returns edge table + area stats + `buildable_boundary` for plotting.
  - `clearance_constraint_value(bld1, bld2, min_sep)` → G = `min_sep - distance(bld1, bld2)` — positive when buildings are too close (hard constraint violation).

- [x] Updated `team_04/agent/tools/view_optimizer.py` to integrate setbacks and clearance:
  - `sample_valid_placements` now accepts `site_setbacks` dict — uses `buildable_zone` instead of raw site for seed-point filtering.
  - `optimize_view_placement` accepts `site_setbacks` — NSGA-II constraint uses `buildable_zone.contains(building)`.
  - `optimize_two_building_placement` accepts `site_setbacks` and `min_building_separation`:
    - If `min_building_separation > 0`: adds G[3] = `clearance_constraint_value(bld1, bld2, min_sep)` as a 4th hard constraint.
    - Results now include `clearance_between_buildings_m` in each solution.
    - `site_setbacks_used` and `min_building_separation_m` in the result dict.

- [x] Created `team_04/agent/tools/view_3d.py` — height-aware 3D analysis and plotly visualization.
  - `evaluate_building_views_3d(boundary, height, obstacles_with_heights, *, floor_height, ...)`:
    - Floor levels: z = 0.5h, 1.5h, 2.5h, ... up to building height.
    - At each z, filters obstacles to those with `height >= z` — upper floors see over shorter obstacles.
    - `view_score_3d = total_unblocked / (n_floors × n_test_pts)`.
    - `per_floor` list with `view_score`, `unblocked`, `total` per floor level.
  - `visualize_3d(site_boundary, buildings, obstacles, *, buildable_zone_boundary, attractors, view_results, ...)`:
    - Pure plotly (no topologicpy dependency).
    - Buildings / obstacles: `go.Mesh3d` extruded prisms with fan triangulation.
    - Site: flat `go.Mesh3d` ground plane.
    - Buildable zone: `go.Scatter3d` dashed outline at z=0.05.
    - Rays: `go.Scatter3d` (green = clear, red = blocked) at actual floor z-levels.
    - Attractors: `go.Scatter3d` horizontal line.

- [x] Updated `test_view_analysis.ipynb` with four new sections:
  - Section 10: setback demo — visualizes buildable zone with per-edge setback annotations.
  - Section 11: two-building optimization with setbacks + 6 m minimum clearance constraint.
  - Section 12: height-aware 3D view score comparison (3, 6, 10 storeys) showing per-floor score improvement.
  - Section 13: interactive plotly 3D scene with two buildings, obstacles at different heights, multi-floor rays.

### Design Decisions

- **Building clearance terminology**: the minimum separation between building footprints is called `min_building_separation` (or "building clearance" / "daylight gap"). The offset zone around a single building (preventing it from being too close to its own perimeter) is not implemented — `min_building_separation` governs pair-wise inter-building distance.
- **Setback as a buildable zone**: setbacks affect where buildings can be placed (seed points and NSGA-II constraint), not view rays. Rays still cast from the placed building boundary to measure what the occupants actually see.
- **Height-aware 3D vs 2D analysis**: `evaluate_building_views_3d` is a richer metric accounting for building height. The 2D `evaluate_building_views` remains the optimizer's inner loop for speed; 3D can be run as a post-hoc evaluation on selected solutions.
- **No topologicpy Plotly**: topologicpy has no Plotly module in this codebase. `view_3d.py` uses pure `plotly.graph_objects`.

### Active MVP Status

- [x] Site setback and buildable zone computation working.
- [x] Building clearance hard constraint integrated into two-building NSGA-II.
- [x] 3D height-aware view analysis working.
- [x] 3D plotly visualization working (interactive in notebook).
- [ ] `view_3d.py` functions not yet wired into LangGraph MCP tool catalog.
- [ ] Height is not yet a variable in NSGA-II (optimizer still works in 2D; height is set manually).

## 2026-06-06 Attractor View Objective and Free-Shape Optimization

### Completed

- [x] Added `evaluate_attractor_views()` to `view_analysis.py`:
  - Input: building boundary, list of attractor dicts (`{"type":"line"/"point","geometry":[...]}`) and obstacle polygons.
  - For each test point × attractor pair: casts a ray from the test point toward the **nearest point on the attractor geometry** (not perpendicular — aimed at the target).
  - Counts unblocked rays / total rays → `attractor_score` (0–1).
  - Fast path (`return_ray_detail=False`) uses `unary_union` obstacle check for optimizer speed.
  - Added `_nearest_point_on_attractor` helper for line (Shapely `project`/`interpolate`) and point attractors.

- [x] Added area-preserving free-shape (`optimize_shape`) to both optimizers:
  - `_stretch_polygon(polygon, s)`: `scale(x=s, y=1/s)` — area unchanged.
  - Single-building: adds `stretch_factor ∈ [0.4, 2.5]` as a 4th optimization variable.
  - Two-building: adds `s1, s2` → 8 total variables.
  - No existing tool (e.g. `modify_building_boundary`) does this; the stretch variable is the only current path for shape variation during optimization.

- [x] Updated `optimize_view_placement` (single building):
  - With attractors: F[0]=-unblocked, F[1]=-attractor (true 2-objective Pareto).
  - Without attractors: original F[0]=-unblocked, F[1]=-clearance.
  - `attractor_weight` used only for result ranking, not during NSGA-II search.

- [x] Updated `optimize_two_building_placement` (two buildings):
  - Combined score per building: `(1-w)*unblocked + w*attractor`.
  - F[0]=-combined_1, F[1]=-combined_2 (Pareto between buildings).
  - Result dict now includes `unblocked_view_score`, `attractor_view_score`, `combined_score` for each building.

- [x] Updated notebook `test_view_analysis.ipynb`:
  - South-street attractor line added to scene (`y = -25`).
  - Section 3: side-by-side visualisation of perpendicular rays (green/red) and attractor rays (blue/orange).
  - Section 5: single-building NSGA-II with 2-objective Pareto (unblocked vs attractor); iso-combined-score dashed contours shown.
  - Section 6: free-shape (`optimize_shape=True`) run with stretch factor in results table.
  - Section 7-9: two-building joint optimization with attractor, full results table, combined-score Pareto + per-building breakdown scatter.

### Design Decisions

- **Two different ray directions**: Unblocked = perpendicular (outward normal); Attractor = aimed at nearest point on attractor geometry.  These capture genuinely different spatial qualities.
- **Weight only for ranking**: Inside NSGA-II both objectives are free; the Pareto front is fully explored.  `attractor_weight` only controls result sort order and the combined-score contours displayed in the notebook.
- **Attractor is not an obstacle**: The attractor geometry is only a target for rays, never subtracted from the valid view field.
- **Area-preserving stretch**: `scale(s, 1/s)` preserves area exactly.  Applied before rotation, centred at origin (base polygons are origin-centred).

### Validation

- [x] Ran the rewritten end-to-end notebook through bootstrap, import, helper, and scenario-selection cells.
- [x] Confirmed the rewritten notebook exposes site-object-aware scenarios, including a two-building prompt path.
- [ ] Run the live agent cell once `LLM_PROVIDER` and provider credentials are available in the selected notebook kernel.

## 2026-06-03 Notebook Split For Dev And End-To-End Runs

### Completed

- [x] Added `test_notebooks/tool_dev_mode.ipynb` as the deterministic Team 04 notebook for local tool and geometry iteration.
- [x] Added `test_notebooks/end_to_end_api_agent.ipynb` as the live-LLM notebook for the current planner plus supervisor flow without requiring a live MCP server.
- [x] Kept both notebooks aligned to the active Team 04 runtime under `agent/` and the current graph-backed building workflow.
- [x] Added notebook-local guidance so missing LLM environment settings are reported cleanly instead of crashing the setup cell.

### Validation

- [x] Configured both notebooks on the Team 04 `311` kernel.
- [x] Executed the dev notebook bootstrap, import, generation, and transform cells successfully.
- [x] Installed `pymoo` into the notebook kernel after the dev notebook exposed the missing dependency.
- [x] Executed the end-to-end notebook bootstrap cell and confirmed the runtime-settings cell now reports missing `LLM_PROVIDER` cleanly when no `.env` is loaded.

### Deferred

- [ ] Run the full end-to-end notebook agent cell once Team 04 LLM environment variables are present in the selected notebook kernel.

## 2026-06-03 Graph-Backed Shape And GA Placement Pivot

### Completed

- [x] Removed the repo-root layout bootstrap from the active Team 04 runtime.
- [x] Rebuilt `generate_building_boundary` around graph-backed shape generation with stable wing indices.
- [x] Added `U` shape support and kept the broader `I`, `L`, `T`, `Y`, `H`, `X`, and `O` family in the active generator.
- [x] Added TopologicPy-backed shape serialization so generated footprints carry both polygon geometry and graph data.
- [x] Added `pymoo` placement optimization for fitting generated footprints inside a supplied site boundary.
- [x] Switched the active output artifact to `team_04_placement_result.json`.
- [x] Added Team 04-local `requirements.txt` coverage for the active LangGraph and geometry stack.
- [x] Updated the focused tests for graph-backed output, placement optimization, and result logging.

### Active MVP Status

- [x] Team 04 is now Python-tool-first for shape generation and placement.
- [x] The active generator returns wing data, adjacency data, TopologicPy geometry, and placement summaries.
- [x] Added a first wing-level edit tool for indexed thickness changes and end-wing rotation around graph joints.

### Validation

- [x] Confirmed direct local `U`-shape generation produces three wings with stable adjacency.
- [x] Added a focused regression for wing-thickness edits plus 180-degree end-wing rotation through the local tool surface.
- [x] Refined wing rotation pivots so leaf-wing rotations use the higher-degree graph node as the base point.
- [x] Ran `C:/Users/baoqt/miniconda3/python.exe -m unittest team_04.tests.test_boundary_tools team_04.tests.test_agent_graph team_04.tests.test_benchmark_logger` and all 23 tests passed.

### Deferred

- [ ] Rename remaining internal `layout_json`-style state keys if Team 04 wants the runtime state wording to fully match the new placement-first workflow.
- [ ] Expand the first wing-level edit tool beyond thickness and wing rotation into more exact edge-angle, extension, and joint-aware edits.
- [ ] Upgrade the centerline graph joints from the current endpoint-and-intersection heuristic to a clipper-like jointing pass when Team 04 is ready for more exact building-graph topology.
- [ ] Run the active notebooks interactively in the now-aligned environment.

## 2026-06-03 Notebook And Example Folder Cleanup

### Completed

- [x] Moved the active Team 04 top-level notebooks into `notebooks/`.
- [x] Updated the moved notebooks so they can still resolve `team_04/agent/` when run from the workspace root, the `team_04/` folder, or `team_04/notebooks/`.
- [x] Archived redundant example folders `JSON_Tools_Example/` and `llm_call/` under `legacy/fresh_start_2026-06-03/reference_examples/`.
- [x] Cleaned the active docs so they refer to `notebooks/` instead of leaving notebook files scattered at the Team 04 top level.

### Validation

- [x] Confirmed the Team 04 top level now keeps notebooks inside `notebooks/`.
- [x] Confirmed the archived example folders no longer occupy the Team 04 top level.

### Deferred

- [ ] Run the moved notebooks interactively after the Python environment is fully aligned with `team_04/requirements.txt`.

## 2026-06-03 Fresh Start Reorganization
- [x] Added a notebook test harness at `notebooks/test_generate_building_boundary.ipynb` to run the tool and prepare a Grasshopper handoff payload.
- [x] Added a two-building mock workflow with local placement-analysis tools and a notebook test harness.
- [ ] Run `notebooks/test_generate_building_boundary.ipynb` against live Grasshopper import behavior.
- [ ] Run `notebooks/test_two_building_workflow.ipynb` against live Grasshopper placement-analysis behavior.
- [ ] Run `notebooks/test_multi_building_shape_transformations.ipynb` against the live Grasshopper manipulation tool.

### Completed

- [x] Archived the extra `PY/` runtime tree, `agent prototype/`, and stale planning and workflow-visualization files under `legacy/fresh_start_2026-06-03/`.
- [x] Replaced the old Grasshopper-first quick start with a Python-tool-first `QUICK_START.md` centered on `agent/` and `agent/tools/`.
- [x] Replaced the old tool checklist with a Python-tool-focused `TOOLS_CHECKLIST.md`.
- [x] Updated Team 04 instructions and the local Team 04 skill so future reorganization keeps redundant material in `legacy/` and preserves `agent/` as the only active runtime tree.

### Active MVP Status

- [x] One active LangGraph runtime remains at `main.py` -> `agent/main.py`.
- [x] Local Python tools remain the primary implementation focus.
- [ ] Live Swiftlet and Grasshopper parity is still deferred behind the Python-tool-first path.

### Validation

- [x] Confirmed the redundant trees and stale planning docs no longer occupy the Team 04 top level.
- [x] Installed the Team 04-local runtime dependencies and reran the focused Team 04 test slice in the target interpreter.

### Deferred

- [ ] Continue reducing dependency on mock placement-analysis tools as the Python-tool surface matures.

## 2026-06-03 Coordination Contract Refresh

### Completed

- [x] Added `agent.md` as a top-level Team 04 agent contract so Team 04 now exposes the same concise comparison surface most other teams already publish.
- [x] Added `team_04/.env.example` as a Team 04-local runtime settings template aligned to the canonical runtime in `agent/config.py`.
- [x] Expanded `AGENTS.md` and the local Team 04 skill so future work preserves both the Team 04 boundary and the coordination files that support multi-agent handoff.

### Validation

- [x] Confirmed the canonical runtime loads repository root `.env` first and falls back to `team_04/.env`.
- [x] Confirmed the canonical runtime loads repository root `mcp.json` first and falls back to `team_04/mcp.example.json`.

### Deferred

- [ ] Decide whether Team 04 also wants a dedicated top-level `README.md` once the live Swiftlet tool surface and operator workflow stop changing.

## 2026-05-17 Rewrite Reset

The codebase was cleaned up and reset around one canonical LangGraph implementation.

### Completed

- [x] Archived both conflicting Python implementations into `legacy/`.
- [x] Created a new canonical agent package in `agent/`.
- [x] Replaced interactive in-graph human feedback with non-blocking `await_human` state.
- [x] Rebuilt the workflow as a planner plus hub-and-spoke execution graph.
- [x] Added grouped MCP tool policy enforcement by action.
- [x] Added typed `PlanStep` state, planner-owned task sequencing, and explicit `replan_required` conditions.
- [x] Narrowed the execution supervisor to the active plan step and its relevant tool family.
- [x] Added deterministic smoke tests in `tests/test_agent_graph.py`.
- [x] Rewrote `ARCHITECTURE.md` to match the active codebase.
- [x] Implemented the local Python `generate_building_boundary` tool that returns footprint polyline coordinates and metrics.
- [x] Integrated the local boundary tool into the runtime with a composite tool client instead of routing initial shape generation through MCP.
- [x] Added focused geometry tests for the local boundary tool and kept the full Team 04 test suite passing.
- [x] Added a notebook test harness at `notebooks/test_generate_building_boundary.ipynb` to run the tool and prepare a Grasshopper handoff payload.
- [x] Added a two-building mock workflow with local placement-analysis tools and a notebook test harness.
- [x] Extended the canonical planner/runtime with multi-building steps for requested-position checks, placement, and remaining-site analysis.
- [x] Added per-building intent state so planner goals can carry different architectural narratives for building 1 and building 2.
- [x] Expanded the local boundary generator to support `I`, `L`, `T`, `Y`, `H`, `X`, and `O` building footprints.
- [x] Added direct local boundary manipulation for move, orientation, rotation, and mirroring with site-boundary fit checks.
- [x] Added a many-building notebook harness to stress-test multiple shapes and transformations on one site.
- [x] Added a Grasshopper tool-definition spec for `modify_building_boundary_04`.
- [x] Added a live notebook harness at `tests/test_context_reader_live.ipynb` to validate OpenAI settings, MCP reachability, Rhino or Grasshopper tool discovery, and direct `context_reader` execution.

### In Progress

- [ ] Grasshopper-side `import_building_boundary_04` implementation in Swiftlet/Grasshopper.
- [ ] Live Rhino or Swiftlet validation of `context_reader_04` against the updated `test_gh/test.gh` Grasshopper definition.
- [ ] Grasshopper-side `remaining_buildable_positions_04` implementation in Swiftlet/Grasshopper.
- [ ] Grasshopper-side `requested_position_checker_04` implementation in Swiftlet/Grasshopper.
- [ ] Grasshopper-side `modify_building_boundary_04` implementation in Swiftlet/Grasshopper.
- [ ] Live Rhino/Swiftlet validation of the one-building JSON handoff from the local Python tool into Grasshopper.
- [ ] Live Rhino/Swiftlet validation of the two-building workflow: place building A, analyze remaining positions, check a requested point for building B, then place building B.
- [ ] Live Rhino/Swiftlet validation of multi-building shape transforms and site-boundary checks through `modify_building_boundary_04`.
- [ ] Wire per-building intent into the production supervisor prompts once the live Swiftlet tools are connected.

### Grasshopper Test Plan

- [ ] Confirm Rhino 8 + Swiftlet bridge are running and the MCP endpoint is reachable.
- [ ] Run `tests/test_context_reader_live.ipynb` and verify the notebook reaches OpenAI, discovers the live context-reader tool, and receives a structured response.
- [ ] Implement `import_building_boundary_04` and verify it creates a closed curve from Python boundary coordinates.
- [ ] Verify `import_building_boundary_04` returns stable Rhino GUIDs and target layer information.
- [ ] Implement `remaining_buildable_positions_04` and verify site pixelization excludes occupied building footprints.
- [ ] Verify `remaining_buildable_positions_04` returns candidate centroid points for the second building.
- [ ] Implement `requested_position_checker_04` and verify it translates the proposed footprint to the requested point.
- [ ] Verify `requested_position_checker_04` reports geometric reasons for rejection and nearby feasible alternatives.
- [ ] Run `notebooks/test_generate_building_boundary.ipynb` against live Grasshopper import behavior.
- [ ] Run `notebooks/test_two_building_workflow.ipynb` against live Grasshopper placement-analysis behavior.
- [ ] Implement `modify_building_boundary_04` and verify move, orientation, rotation, and mirroring preserve closed boundaries.
- [ ] Verify `modify_building_boundary_04` reports whether transformed buildings leave or intersect the site boundary.
- [ ] Run `notebooks/test_multi_building_shape_transformations.ipynb` against the live Grasshopper manipulation tool.
- [ ] Capture one successful end-to-end two-building MCP session and record the expected input/output payloads.

### Current Active Components

- [x] `agent/graph.py`: canonical LangGraph definition.
- [x] `agent/decision_engine.py`: planner, execution-supervisor, and reporting interfaces.
- [x] `agent/tool_catalog.py`: tool grouping and action-policy enforcement.
- [x] `agent/models.py`: typed routing and plan-step models.
- [x] `agent/state.py`: workflow state including plan, active step, and replanning flags.
- [x] `agent/state.py`: workflow state including plan, active step, replanning flags, and multi-building placement context.
- [x] `agent/mcp_client.py`: HTTP MCP adapter plus local/composite tool support.
- [x] `agent/config.py`: runtime settings and result-output handling.
- [x] `agent/tools/generate_building_boundary.py`: local footprint generation tool.
- [x] `agent/tools/modify_building_boundary.py`: local footprint transformation and site-fit classification tool.
- [x] `agent/tools/multi_building_mock.py`: local mock tools for placement import, requested-position checks, and remaining-site analysis.
- [x] `main.py`: top-level entry point.
- [x] `notebooks/test_generate_building_boundary.ipynb`: notebook-based local tool test and Grasshopper payload prep.
- [x] `notebooks/test_two_building_workflow.ipynb`: notebook-based two-building workflow and user-requested position test.
- [x] `notebooks/test_multi_building_shape_transformations.ipynb`: notebook-based multi-building shape, transform, and site-fit stress test.
- [x] `tests/test_context_reader_live.ipynb`: notebook-based live OpenAI plus MCP connectivity check and direct `context_reader` tool invocation.

### Explicitly Archived

- [x] `legacy/PY_legacy/`
- [x] `legacy/python_legacy/`

### Remaining Work

- [ ] Connect the new planner and supervisor prompts to production Swiftlet tool behavior.
- [ ] Add integration tests against a live Swiftlet MCP server.
- [ ] Decide whether to keep one execution supervisor or split it further into shape-generation and optimization reasoners once the live tool surface is stable.
- [ ] Reconcile or refresh the remaining handoff documents that still describe the pre-rewrite system.
- [ ] Add a production Grasshopper import tool for local Python-generated footprint coordinates.
- [ ] Add production Grasshopper versions of `remaining_buildable_positions_04` and `requested_position_checker_04`.
- [ ] Add a production Grasshopper version of `modify_building_boundary_04` for boundary transforms and site-boundary checks.
- [ ] Replace the local mock placement-analysis tools with live Swiftlet tool calls in the canonical runtime.