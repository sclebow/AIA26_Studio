# Team 04 Progress

## 2026-06-17 Shape library — fixed the Y and X footprints

User: the Y and X building shapes were malformed (the agent struggled to find a side to align), and supplied reference letter shapes. Rebuilt **only** Y and X in `agent/tools/building_shape_graph.py`.

### Completed

- [x] Replaced the hand-written Y/X template vertex lists (which didn't read as letters) with **uniform-width bar unions**: `_letter_y_polygon` = a vertical stem that splits into two diagonal arms forming a V; `_letter_x_polygon` = two diagonal bars crossing at the centre. Both flat-ended (`buffer(cap_style=2, join_style=2)`), unioned, then scaled to the requested area. `O` is unchanged (`_O_TEMPLATE`); I/L/T/U/H (winged) untouched.
- [x] Verified by rendering: Y is a clean letter Y (stem + V arms, bbox taller than wide so its length axis is the stem), X is a clean letter X (square bbox, symmetric). Both valid polygons, area exact.

### Validation

- [x] Full `team_04/benchmarking` suite still green except the pre-existing unrelated `test_generate_building_boundary` float-boundary failure (150 tests). The all-shapes and grid+sun integration tests build Y/X with the new geometry and pass.

## 2026-06-17 Phase 3 — Straight grid + function-driven orientation (pivot from warping)

User: "It's wrong, not parallel, not following the grid, placed randomly. Just pick a side and draw the grid parallel and perpendicular — do not make it distorted. Place buildings perpendicular on the grid. Ask the user the building's function to decide which wing is perpendicular to the chosen side. Same for all types." Pivoted off the warped/conforming approach to a simple straight grid + rigid, function-oriented placement. (Confirmed via `AskUserQuestion`: rule = **by use**; function supplied as a parameter the agent asks for.)

### Completed

- [x] Added function-driven orientation to `agent/tools/site_grid.py`:
  - `FUNCTION_FRONTAGE` (+ `frontage_for_function`): **commercial/retail/mixed → "parallel"** (long side along the street, max frontage); **residential/office/... → "perpendicular"** (deeper plan, light + privacy). Editable.
  - `building_long_axis_deg` — the footprint's dominant axis = longer side of its axis-aligned bounding box (stable 0/90; the longest-edge proxy ties on symmetric shapes and picks a diagonal on X).
  - `orientation_for_function` / `place_building_by_function` — rotate a footprint to one of the two **grid-aligned** orientations by function (or an explicit `frontage`/`long_axis_deg` override), so its edges end up parallel **and** perpendicular to the chosen side. The agent asks the user the function and passes `function=`.
- [x] The straight grid (`derive_site_grid`) keyed to a chosen side remains the placement grid; the warped `derive_adaptive_site_grid` / `conform_*` stay in the backend but are **no longer used by the notebooks**.

### Validation

- [x] Diagnostic: the rectilinear winged shapes (I L T U H) place **0.0° off-grid** (every edge parallel/perpendicular), commercial → long side parallel, residential → perpendicular. Diagonal-armed Y/X/O keep their inherent arms (a diagonal cross can't be edge-aligned to one side) and orient by their dominant axis.
- [x] Added `FunctionOrientationTests` to `benchmarking/test_site_grid.py` (use→frontage mapping; bbox long axis; winged shapes place perfectly grid-aligned; commercial parallel vs residential perpendicular; orientations differ by 90°; `frontage=` override). 41 grid tests pass.
- [x] Rewrote `test_grid_alignment.ipynb`: §1b places a U by function (commercial vs residential) on the straight grid (`edges 0° off-grid`); §1c places every shape by function; **removed** the warped-grid §1d and the conforming obtuse-corner §3. Updated intro + summary.
- [x] Rewrote `test_sun_analysis.ipynb` §7: straight grid keyed to the **sun-chosen side**, U placed rigidly by function, sun scored. With no obstacles, exposure depends on orientation, so it compares commercial (0.329) vs residential (0.207) worst-sun — the function/orientation drives the sun result. Updated `benchmarking/test_sun_analysis.py` to `GridFunctionSunIntegrationTests` (23 tests pass). Both notebooks smoke-run clean.

## 2026-06-17 Phase 3 — Gentle, size-preserving conforming (the realistic middle ground)

User: "I was happy with the L conforming … but the Y and X are too distorted; I want shapes exactly like the reference and manipulatable like the L — realistic, flexible, responsive to complex sites." So neither the full rubber-sheet (distorts X/Y) nor pure rigid (no flex) is right. Implemented the middle ground.

### Completed

- [x] Added `conform_building_to_grid(base, grid, site_model, node, *, bend=0.6)` to `agent/tools/site_grid.py`: maps the footprint into a **local `(s, t)` window sized to its real extent** via the grid's local **Jacobian**, then **blends rigid↔conformed by `bend`** ∈ [0,1]. The building gently follows the grid's curvature while keeping its width, recognisable shape, and area — no rubber-sheet blow-up. `bend=0` = rigid; on a rectangle (affine patch) conform == rigid (zero distortion). Falls back to rigid when the grid is not adaptive.
- [x] Stored per-node `(s, t)` in the adaptive grid (`node_params`) so a footprint can be conformed at the right local window; re-added the `_clamp01` helper.

### Validation (diagnostic)

- [x] Across all 8 shapes: **rectangle area_ratio = 1.000** at every bend (zero distortion on simple sites); **pentagon area 0.94–0.98 at bend 0.6** with vertex counts preserved exactly — vs. the old 4–9× blow-up. Shapes stay recognisable.
- [x] Added `GentleConformTests` to `benchmarking/test_site_grid.py` (bend=0 equals rigid; rectangle conform has zero distortion at any bend; splayed site preserves vertex count + area 0.8–1.25×; it actually bends a long bar; non-adaptive grid falls back to rigid). 34 grid tests pass.
- [x] Reworked `benchmarking/test_sun_analysis.py` to `GridConformSunIntegrationTests` (conform keeps verts + area within tolerance, valid varying sun score, all 8 shapes). 23 sun tests pass.
- [x] Notebooks back to **conforming** (gentle): `test_grid_alignment.ipynb` §1b/1c/1d/3 conform a U / all shapes / an obtuse L (area % shown per panel, shapes recognisable); `test_sun_analysis.ipynb` §7 conforms a U at each node + scores by worst-sun (40 placements, area ~99%). Both smoke-run clean.

### Placement fix — front the chosen side (was "placed randomly")

- [x] User report: in §1c the building floated in the interior, not aligned to any side. Root cause: the demo placed at the nearest *interior* node where the footprint fit, landing it where the warped grid points a different way. Replaced with `place_on_grid(base, grid, s_frac)`, which places the building **near the chosen side** (smallest `t`) at along-side fraction `s_frac`, oriented to the local grid there (parallel to the side). Verified per side: building **inside, 2–9 m off the chosen side, 0.5–10.7° of parallel**. §1b/1c/1d/3 now all front the chosen side (1b slides the U along the frontage; 1c fronts each side; 1d fronts the road for every shape; 3 tucks into the obtuse corner).
- [x] Added `test_fronting_a_side_places_the_building_near_it` (every side: the near-side placement sits within 18 m of the chosen side). `team_04.benchmarking.test_site_grid` → 35 tests pass.

## 2026-06-17 Phase 3 — Removed footprint conforming; buildings stay rigid (realistic)

User: "the conforming logic for the buildings is wrong — too deformed; X and Y aren't even following the grid, it's not the shape anymore and no realistic building would look like that." Correct. A diagnostic confirmed footprint conforming **blew up area 4–9×** and exploded vertex counts (X→73 verts), while rigid local-grid placement preserves **area_ratio 1.000 and the exact vertex count**.

### Completed

- [x] **Removed** the footprint-conforming functions from `agent/tools/site_grid.py`: `conform_polygon_to_grid`, `conform_world_footprint_to_grid`, `l_region_in_grid_space`, `rect_region_in_grid_space`, `l_region_in_cells`, `rect_region_in_cells`, `grid_world_mapper`, and the now-dead `_clamp01`. They rubber-sheeted the polygon through the Coons patch — unrealistic.
- [x] Kept the adaptive **warped grid** (`derive_adaptive_site_grid`) as an **orientation field**, and `align_building_to_local_grid` / `local_grid_orientation` as the **realistic placement**: the building is a rigid footprint rotated to the local grid direction — straight walls, exact shape/area — so the layout adapts to the site while every building stays real. An L can still bend a free wing (`corner_wing_rotation`) for an obtuse corner.

### Validation

- [x] Rewrote `benchmarking/test_site_grid.py` (dropped the conforming tests; added `RigidLocalPlacementTests`: rigid placement preserves every shape's area + vertex count exactly; long edge follows the local grid; every shape places rigidly inside the site; the building re-orients per chosen side; the optimizer path stays shape-agnostic). 29 tests pass.
- [x] Rewrote `benchmarking/test_sun_analysis.py` integration to `GridRigidSunIntegrationTests` (rigid placement asserts identical vertex count + area, gets a valid worst-sun score, and the score varies across placements). 23 tests pass.
- [x] Rewrote `test_notebooks/test_grid_alignment.ipynb` sections 1b/1c/1d/3 to **rigid** local-grid placement (a U oriented to the local grid; the same U re-orienting per chosen side; all 8 library shapes placed rigidly with area preserved; a rigid obtuse-arm L at the most obtuse corner). Removed the duplicate stale Summary. Smoke-runs clean (shapes preserved, obtuse L inside).
- [x] Rewrote `test_notebooks/test_sun_analysis.ipynb` §7 to place a **rigid** U at each grid node, oriented to the local grid, scored by worst-sun exposure (40 in-site placements, shape preserved, exposure spans 0.138). Fixed the tangled section-7 header / duplicate-summary ordering.

## 2026-06-17 Phase 1×3 — Sun fitness composed with grid conforming on a complex site

User: "try the sun analysis with the more complex site … use the logic from grid alignment and integrate it." Composed the two capabilities so a building reacts to the *site* (grid conforming) and the *sun* (exposure fitness) at once.

### Completed

- [x] Added section "7. Complex site — conforming buildings react to the sun" to `test_notebooks/test_sun_analysis.ipynb`: builds the **adaptive warped grid** on the splayed pentagon, marks the **worst-sun side**, then **conforms** a U at many grid positions (`conform_world_footprint_to_grid`) and scores each by **worst-sun exposure** (`evaluate_sun_exposure`), keeping the placement that both fits the site and dodges the sun (best vs. worst shown side by side, facades coloured by exposure).
- [x] No backend change needed — the integration reuses the existing conforming + sun tools. (The sun NSGA optimizer still uses free-rotation candidates; conforming placement is swept explicitly here, the same pattern as the grid notebook.)

### Validation

- [x] Smoke-ran the section: 11×6 grid, worst-sun side W, 12 conforming U placements inside the site, worst-sun exposure spanning ~0.076 across placements (the signal the agent reacts to).
- [x] Added `GridConformingSunIntegrationTests` to `benchmarking/test_sun_analysis.py` (conforming building gets a valid 0–1 sun score; sun exposure varies across placements; every library shape conforms + scores on the complex site). `python -m unittest team_04.benchmarking.test_sun_analysis` → 23 tests pass.

## 2026-06-17 Phase 3 — Conforming applies to ALL library shapes (I L T U H Y X O)

User check: "is all the logic applicable with all the building shapes, not just the simple L/T/I?" Audited the two logic paths against the full footprint library (winged `I/L/T/U/H` + template `Y/X/O`).

### Findings + Completed

- [x] **Rigid + grid-aligned placement was already shape-agnostic.** `align_building_to_grid`, `sample_valid_placements`, and `optimize_aligned_placement` take any polygon boundary; all 8 shapes produced 75–89 valid grid-aligned candidates. No change needed.
- [x] **Conforming was the gap:** it only had `l_region_*` / `rect_region_*` (L and rectangle authored in `(s,t)`), so it could not deform U/H/T/I/Y/X/O. Added `conform_world_footprint_to_grid(grid, site_model, world_boundary, …)`: normalises any footprint's bounding box into a grid `(s, t)` sub-rectangle and pushes it through the same Coons map, so **every library shape conforms** to the warped grid and stays inside the site.

### Validation

- [x] Verified all 8 shapes conform fully inside both the splayed pentagon and the rectangle, each warping more on the pentagon (higher turning-sum) than on the affine rectangle where it keeps its base corner angles.
- [x] Added `AllShapesConformTests` to `benchmarking/test_site_grid.py` (library = 8 shapes; every shape builds, grid-aligns, conforms inside the site, and warps on the splayed site). `python -m unittest team_04.benchmarking.test_site_grid` → 33 tests pass.
- [x] Added notebook section "1d. Every library shape conforms" — a 2×4 gallery of `I L T U H Y X O` conforming to the warped grid (titles confirm `inside=True`). Notebook smoke-runs end to end.

## 2026-06-17 Phase 3 — Fix: building drifted off the chosen side; cell-snapping

User feedback: the conformed L "is placed randomly on the site … test the grid with different sides to see how the building reacts." Two real issues found and fixed.

### Completed

- [x] **Bug: the grid's bottom edge was not always the chosen side.** `_select_quad_corners` picked the four sharpest corners, so when the chosen side's vertices were not among them (e.g. sides 2 and 3 of the demo pentagon, whose shared apex was the dropped vertex) the Coons patch keyed to *other* corners and a building authored on it landed in an unrelated spot — "random". Rewrote `_select_quad_corners` to **always anchor the bottom (`B`) chain on the chosen side** (`a -> a+1`) and split the opposite arc into ~thirds for the other two corners. Verified `B == chosen side` for all 5 sides.
- [x] **"Looks random" vs. the grid:** added `l_region_in_cells` / `rect_region_in_cells` so a footprint is authored on **whole grid cells** (`i/nu`, `j/nv`); its edges then land *on* the drawn grid lines, so it visibly snaps to the grid like the sketch instead of floating at an arbitrary fraction.

### Validation

- [x] Added 2 regressions to `benchmarking/test_site_grid.py`: `B` chain equals the chosen side for every side of the pentagon; and the same cell-snapped L, built per-side, sits nearer its own side than the opposite side and relocates across the site as the side changes. `python -m unittest team_04.benchmarking.test_site_grid` → 28 tests pass.
- [x] `test_notebooks/test_grid_alignment.ipynb`: section 1b now authors the L by cells (snapped + deforming); new section "1c. The building reacts to the chosen side" re-keys the grid to each side and shows the grid + L rotating to follow it (panel titles show `B = side`). Notebook smoke-runs end to end.

### Reworked section 3 (obtuse corner)

- [x] Replaced the old rigid section-3 demo — which dropped a 700 m² L with `align_building_to_grid` and **no fit check**, so it poked ~2% (~15 m²) outside the splayed boundary — with a **conforming** L tucked into the site's most obtuse corner (122° on the demo pentagon). Authored in grid cells and pushed through the Coons map, its knee opens to the corner's interior angle automatically and it is **fully inside the site by construction** (notebook prints `fully inside site: True`). The old rigid `corner_wing_rotation` path remains available as a tool but is no longer the placement story.

## 2026-06-17 Phase 3 — Conforming footprints: the building deforms to follow the grid

Follow-up to the adaptive grid (user feedback: "the building can never rotate and place freely like this … it should be constantly adapting to the site and have flexibility in manipulation like how I sketched"). A rigid footprint dropped at a single local angle still reads as "placed freely". Now a building is **authored in the grid's own `(s, t)` parameter space and pushed through the same Coons map**, so its edges bend along the warped grid lines and it conforms to the site; manipulation happens in `(s, t)` space and the world footprint re-conforms automatically.

### Completed

- [x] Refactored the Coons patch out of `derive_adaptive_site_grid` into reusable `_coons_inputs`/`_coons_eval` (no behaviour change) so the same map serves both the grid and the building.
- [x] Added to `agent/tools/site_grid.py`: `grid_world_mapper(grid, site_model)` (returns `to_world(s,t)`), `conform_polygon_to_grid(...)` (maps an `(s,t)` footprint into the warped site, densifying edges so straight edges become curves that follow the grid), and `l_region_in_grid_space` / `rect_region_in_grid_space` (author an L or bar in grid space). On a rectangle the map is affine, so edges stay straight — conforming generalises rigid placement.

### Validation

- [x] Added 5 regressions to `benchmarking/test_site_grid.py` (warps on a splayed site but stays straight on a rectangle via a turning-sum metric; conformed footprint stays inside the site; manipulation in `(s,t)` moves the world footprint and every variant stays inside; rect region conforms to a closed quad; a uniform grid has no map and raises). `python -m unittest team_04.benchmarking.test_site_grid` → 26 tests pass.
- [x] Reworked `test_notebooks/test_grid_alignment.ipynb` section 1b: the navy L now **deforms** to follow the warped grid (the sketch), plus a manipulation row (move along road / stretch long arm / deeper+thinner) each re-conforming inside the site. Notebook smoke-runs end to end.

## 2026-06-17 Phase 3 — Adaptive (warped) grid: angle changes to match site complexity

Extends Phase 3 so the grid's **local axis angle adapts to the site's complexity** instead of using one rigid angle (per user request: "the angle between the grid can change to match the complexity of the site … the L-shape building responding to the site"). Additive — the uniform `derive_site_grid` is untouched.

### Completed

- [x] Added `derive_adaptive_site_grid` to `agent/tools/site_grid.py`: fits a **transfinite (Coons) patch** to the site's four principal edge-chains (sharpest-four corners frame the quad; intermediate vertices fall inside chains where the taper lives). Grid lines bend to follow the boundary; returns `angle_range_deg` (how much the local angle swings), `node_orientations` (per-node local direction), warped `grid_lines`, and `corner_indices`.
- [x] Added `local_grid_orientation(grid, point)` (nearest-node local direction) and `align_building_to_local_grid(...)` (drops a footprint oriented to the local grid direction, optionally + a `corner_wing_rotation` obtuse bend) so a building **responds to the site** rather than sitting at one global angle.
- [x] Fixed the orientation-spread metric to measure the smallest covering arc on the circle (a naive max-min folded near 0°/180° and wrongly reported a rectangle as fully warped). A rectangle now correctly reports `angle_range_deg ≈ 0` (degenerates to the uniform grid).

### Validation

- [x] Added 6 regressions to `benchmarking/test_site_grid.py` (rectangle does not warp; splayed pentagon warps `> 8°`; local orientation changes left↔right across the site; nodes stay inside the site; a placed building's long edge follows the local direction within 1°; triangle is unavailable). `python -m unittest team_04.benchmarking.test_site_grid` → 21 tests pass.
- [x] Updated `test_notebooks/test_grid_alignment.ipynb` with section "1b. Adaptive grid — the angle changes to match the site's complexity": uniform vs. warped grid side by side, the warped green net, and a navy L oriented to the local grid direction at the main-road corner (matches the reference image). Notebook smoke-runs end to end; the pentagon reports a 50.8° local-angle swing vs. 0° uniform.
- [x] Full `team_04/benchmarking` discovery: only the pre-existing unrelated `test_generate_building_boundary` float-boundary failure remains.

## 2026-06-17 Phase 3 — Site Grid & Side Alignment (no more random-looking placement)

Implements Phase 3 of `BACKEND_PLAN.md` on a **complex non-orthogonal site**. Real buildings are not dropped at arbitrary rotations inside a plot — they sit on a site grid, **parallel to a preferred boundary**. Placement is now restricted to **grid-node positions × aligned orientations** ({parallel, perpendicular} to a chosen side) instead of a free 5 m sweep + 36 free rotations, with a **use-driven** rule (commercial hugs the frontage) and **obtuse footprints** that follow splayed corners. Deterministic tool + exhaustive optimizer + notebook + regressions + lockstep frontend — all under `team_04/`, conflict-free with `main`. (Phase 3 normally follows Phase 2/roads for the alignment side; built now with the documented **longest-side fallback** + an explicit `alignment_side`, so roads refine it later.)

### Completed

- [x] `agent/tools/site_grid.py` — pure, LLM-free grid + alignment:
  - `derive_site_grid(site_model, spacing, alignment_side=None)` → origin + two axes aligned to a chosen side (default: **longest side**), clipped to the buildable zone; returns `grid_lines` (drawing), `grid_nodes` (seed points), `angle_deg`, and the adjacent sides. Works on arbitrary non-orthogonal polygons.
  - `aligned_orientations(grid)` → the discrete {parallel, perpendicular} orientation set (± optional offsets) — the **only** angles a building may take.
  - `snap_to_grid`, `alignment_score` (1.0 = long edge parallel to a grid axis), `align_building_to_grid` (place a centred footprint at a node with an aligned orientation).
  - `corner_interior_angle` / `corner_wing_rotation` → leaf-wing rotation so an L's free arm follows the *adjacent* site side, spreading the wings to the corner's interior angle (**obtuse on a splayed site**, not a rigid 90°). Reuses the existing `parametric_shape` `end_rot` lever.
- [x] Optimizer integration (`agent/tools/view_optimizer.py`): grid-aware `sample_valid_placements(grid=...)` (grid nodes × aligned orientations, **hard restriction by default**); new `grid_alignment` + `boundary_proximity` objectives in `OBJECTIVE_REGISTRY`; `optimize_aligned_placement(...)` — **exhaustive** ranking over the (small) aligned candidate set with a **use-driven** default objective mix (commercial/office/retail/mixed → strong `boundary_proximity`; residential → view + sun), structurally guaranteeing every result is grid-aligned; `place_buildings_aligned(...)` — greedy sequential placement of two-or-more buildings, each aligned and clearing the rest by `min_separation`.
- [x] Frontend lockstep: `backend/routers/tools.py` exposes `site_grid` / `aligned_placement` / `place_buildings_aligned`; `frontend/site/GridOverlay.tsx` draws grid lines + nodes + the chosen side + ranked aligned options; `frontend/api/{types.ts,client.ts}` add `SiteGrid`/`AlignedOption`/`AlignedPlacementResult` + `api.siteGrid/alignedPlacement`; `decision-graph/CONTRACT.md` §8 + `frontend/README.md` roadmap + `frontend/index.ts` barrel updated.

### Validation

- [x] `benchmarking/test_site_grid.py` — 15 deterministic tests (no LLM/MCP): grid aligns to the longest side, explicit `alignment_side` rotates the axis 90°, nodes lie inside the site, parallel+perpendicular orientation set, alignment score high-when-aligned / low-when-skew, snap returns a node, splayed-pentagon corners are obtuse, wing rotation follows the adjacent side, grid-mode sampling is all-aligned, the new objectives are registered, aligned options are all aligned + fit, **commercial hugs the frontage closer than residential**, and two buildings place without overlap at ≥ separation. All pass.
- [x] Notebook `test_notebooks/test_grid_alignment.ipynb` (to the `test_view_analysis.ipynb` shape): complex splayed pentagon + derived grid, **free (4008 mixed-rotation) vs grid-aligned (98 parallel/perpendicular)** side-by-side, an **obtuse L** (wings spread 113° to follow the site) vs a rigid 90° L, **commercial (11 m from frontage) vs residential (17 m)** use-driven placement, and two buildings placed aligned together. Runs top-to-bottom clean on the py311 kernel (`MPLBACKEND=Agg`); figures not re-saved (no `nbconvert`/`nbclient`).
- [x] `npm run typecheck` (frontend, strict) → 0 errors with `GridOverlay` + grid types/client. `py_compile` clean on the changed backend modules; `git status` shows only `team_04/` paths.

### Active MVP Status

- [x] Placement reads as **intentional**: buildings sit on the grid, parallel to the chosen side, and never at a random angle — the "it doesn't look random anymore" picture.
- [x] Use-driven: commercial buildings line the frontage; residential sits back on view + sun. Footprints can go obtuse to match splayed sites.
- [ ] The alignment side defaults to the longest side / an explicit index; the **main-road side** that should drive it lands with Phase 2 (roads). `derive_site_grid` already accepts `alignment_side` so Phase 2 just feeds it.
- [ ] `read_site` does not yet build the grid into `site_model["grid"]` and the graph does not yet call `optimize_aligned_placement` — that is Phase 8 (agent integration); today the tool is called directly / via `/tools`.

## 2026-06-17 Phase 1 — Sun Analysis Fitness (avoid the worst sun)

Implements Phase 1 of `BACKEND_PLAN.md`: the agent now reasons about the sun as **one dominant diagonal vector** (the team's "single diagonal view" — e.g. the low west-south-west summer sun as the worst case) and can place / orient buildings to *avoid* that worst sun. Deterministic geometry tool, optimizer objective, visualization notebook, regressions, and the lockstep frontend overlay — all under `team_04/`, conflict-free with `main`. Verified with `C:\Users\tuemi\AppData\Local\Programs\Python\Python311\python.exe` (shapely/pymoo/matplotlib).

### Completed

- [x] `agent/tools/sun_analysis.py` — pure, LLM-free sun fitness (mirrors `view_analysis.py`):
  - `compute_sun_vectors(...)` / `worst_case_sun_vector(...)` + `WORST_CASE_PRESETS` — the zero-astronomy "one diagonal" mode (default `summer_west`, az 255° / alt 18°), plus an optional real multi-hour mode (`latitude`/`date`/`hours`, daylight-only, irradiance-weighted) from a lightweight solar-position formula.
  - `evaluate_sun_exposure(boundary, sun_vectors, obstacles)` — reuses `divide_boundary_into_test_points`; per facade point, exposure = Σ `max(0, cos(altitude)·cos(Δ))·weight`, **zeroed when an obstacle (height-projected shadow) blocks the vector**. Returns `sun_exposure_score` (0–1, **lower = better**), `worst_point`, and per-test-point detail. `return_ray_detail=False` fast path for the optimizer inner loop.
  - `identify_worst_sun_side(site_model, sun_vectors)` — names the worst (and best) site edge + compass sector, driving the "turn the building away from that sun" rule.
  - **(practical multi-building 3D, added 2026-06-17 per review):** `evaluate_sun_exposure_3d(boundary, height, sun_vectors, obstacles_with_heights)` — height-aware facade-cell grid (reuses `view_3d.build_facade_cells`) with **real per-floor mutual shading**: an obstacle of height `h` only shades a cell at height `z` when `h > z` (shadow reach `(h-z)/tan(altitude)`), so a 24 m tower shades only the lower floors of a 12 m block, not the floors above it — the behaviour a flat 2D projection cannot represent. `visualize_sun_3d(...)` renders the plotly 3D scene (facades coloured by sun exposure via a continuous heatmap, sun vector at true altitude), mirroring `view_3d.visualize_3d`.
- [x] Optimizer integration (`agent/tools/view_optimizer.py`): new `sun_avoidance` objective in `OBJECTIVE_REGISTRY` (`1 - sun_exposure_score`, so it folds into the higher-is-better combined-score pattern like `attractor_view`). `optimize_view_placement` / `optimize_two_building_placement` take `sun_vectors` + `sun_weight`; single-building runs a true **view-vs-sun** 2-objective Pareto front; two-building combines view + sun **and** gets **mutual shading** for free (each building is already passed as the other's obstacle) → the joint NSGA-II yields a layout optimal for view *and* sun at once. Solutions expose `sun_exposure_score` / `sun_avoidance_score`.
- [x] Frontend lockstep: `backend/routers/tools.py` exposes `sun_vectors` / `sun_exposure` / `sun_exposure_3d` / `worst_sun_side` for direct invocation; `frontend/site/SunOverlay.tsx` draws the sun arrow + facade-exposure points + worst-side highlight; `frontend/api/{types.ts,client.ts}` add `SunVector`/`SunExposureResult`/`WorstSunSide` + `api.sunVectors/sunExposure/worstSunSide`; `decision-graph/CONTRACT.md` §7 + `frontend/README.md` roadmap + `frontend/index.ts` barrel updated.

### Validation

- [x] `benchmarking/test_sun_analysis.py` — 20 deterministic tests (no LLM/MCP): preset vectors, multi-hour afternoon-is-westerly geometry, south-facade-more-exposed-than-north ordering, full-shadow zeroing, fast-path == detail-path score, worst-side identification (south sun → south worst, west preset → W/SW worst), the optimizer's `sun_avoidance` objective, **and the 3D height-aware path** (uniform exposure without obstacles, a tall neighbour shading only the lower floors, per-cell normalized exposure, fast-path omits cells). All pass.
- [x] Notebook `test_notebooks/test_sun_analysis.ipynb` (rebuilt to the `test_view_analysis.ipynb` shape, per review): sun arrow + worst-side, single-building view-vs-sun Pareto, **two-building joint view+sun NSGA-II** with mutual shading and 2D facade-exposure site maps, a **3D per-floor mutual-shading** study (tower floors below 12 m graded in shadow 0.06→0.19, floors above at full 0.31), and the **3D plotly facade heatmap** (`visualize_sun_3d`). Code cells smoke-run clean top-to-bottom on the py311 kernel (`MPLBACKEND=Agg`, `pymoo`+`plotly` present); figures not re-saved (no `nbconvert`/`nbclient` in the kernel).
- [x] `npm run typecheck` (frontend, strict) → 0 errors with `SunOverlay` + sun types/client.
- [x] `py_compile` clean on `sun_analysis.py`, `view_optimizer.py`, `backend/routers/tools.py`; backend registry import needs `fastapi` (absent in this kernel) but the underlying functions are exercised by the tests. `git status` shows only `team_04/` paths.

### Active MVP Status

- [x] The optimizer can now trade outward view against worst-sun avoidance, weighted by the brief's `sun_weight`; the LLM only sets the weight, the geometry is deterministic.
- [x] The worst-sun side is identifiable on the canonical `SiteModel`, ready for Phase 3 grid alignment and Phase 6 courtyard orientation.
- [x] Two-or-more buildings are scored together and shade each other; the 3D path (`evaluate_sun_exposure_3d`) does exact per-floor mutual shading from real building heights and renders in 3D (`visualize_sun_3d`).
- [ ] `read_site` does not yet populate `site_model["sun"]` and the graph does not yet auto-assemble the sun objective — that is Phase 8 (agent integration); today the optimizer takes `sun_vectors` directly.
- [ ] The optimizer's NSGA-II inner loop still scores sun in 2D (fast); the 3D height-aware score is a post-hoc evaluation/visualization, same split as `view_analysis` (2D) vs `view_3d`. Per-wing heights (so one wing shades another) arrive in Phase 7.

## 2026-06-16 Interactive Clarification — the agent asks the user back

Closes the Phase 0 loop where the brief populated `ambiguities` but never acted on them. When a prompt is too vague to place accurately, the agent now pauses and returns a **structured question** (shape / preferred side / view-optimisation side / size / use / count) instead of guessing — the brief's no-invention principle made interactive. Policy (chosen with the user): **ask only on critical gaps** (shape, side, view side); minor gaps fall back to documented defaults. Backend ↔ frontend ↔ notebook all wired. All under `team_04/`, conflict-free with `main`.

### Completed

- [x] `agent/clarify.py` — pure, deterministic clarification engine: `ClarificationField`/`ClarificationRequest` dataclasses, `required_clarifications(brief, layout, site_model)` (returns a structured question only when a critical field is missing), `apply_clarification_answers(...)` (merges answers onto the brief + layout: shape/size/use → brief specs, side → `requested_positions` via `side_to_point`, view side → `view_target_sides`, count → `target_building_count`), and `side_options`/`side_to_point` helpers.
- [x] Graph wiring (`agent/graph.py`): `extract_brief` raises a `clarification_request` when `interactive_clarification` is set and a critical gap remains; new conditional edge `extract_brief → await_human | planner` (`_route_from_brief`). Idempotent resume via `clarification_resolved`. Opt-in flag keeps all existing non-interactive runs unchanged.
- [x] State (`agent/state.py`): added `clarification_request`/`clarification_answers`/`clarification_resolved`; `build_initial_state` honors a pre-seeded `design_brief` + `clarification_resolved` from the layout so a resumed run uses the answered brief.
- [x] Backend API: `backend/schemas.py` (`ClarificationFieldSchema`, `ClarificationRequestSchema`, `ClarificationAnswer`); new `backend/routers/clarify.py` (`GET /sessions/{id}/clarification`, `POST /sessions/{id}/clarify`); `decision_graph.make_clarify_node` + `clarify` node type; `chat.py` emits a `clarify` SSE event + node when the agent pauses; router registered in `app.py`.
- [x] Frontend (lockstep): `clarify/ClarifyPanel.tsx` renders the structured question as chips (multi/single select + custom), disables submit until critical fields are answered, and POSTs answers; `ClarifyNode` for the decision graph (registered in `nodeTypes.ts`); `api/types.ts` + `api/client.ts` (`getClarification`/`submitClarification`); `CONTRACT.md` §3/§3b/§7 + `README.md` updated; barrels updated.
- [x] Notebook `test_notebooks/end_to_end_api_agent.ipynb`: new "Interactive clarification" section — vague prompt → structured question → simulated chip answers → second run places accurately, exercising the real LLM.

### Validation

- [x] `benchmarking/test_clarify.py` — 7 deterministic tests (no LLM): critical-gap detection, no-clarification when fully specified, answer-merge onto brief+layout, post-answer self-sufficiency, side→point mapping, and the interactive graph pausing at `await_human` with no placement.
- [x] Full suite: `python -m unittest discover benchmarking` → 85 pass, 1 pre-existing unrelated failure (`test_generate_building_boundary.test_l_shape_is_translated_and_closed`, the known shapely `50.0 not > 50.0` float issue). No regressions from the graph change.
- [x] **Live LLM** check: vague prompt → Run 1 paused with all 6 fields, 0 placed; answered (L / Main Street / south / ~900 m² / office / 1) → Run 2 placed 1 building using the answered **L** shape and did not re-ask.
- [x] `npm run typecheck` (frontend) → 0 errors with `ClarifyPanel` + `ClarifyNode` + clarify types/client.
- [x] `py_compile` clean on all changed backend modules; `git status` shows only `team_04/` paths.

### Active MVP Status

- [x] The agent interacts: it asks the user back for placement-critical details and resumes with the answers, instead of fabricating values.
- [x] Backend, frontend, and the end-to-end notebook share one clarification contract.
- [ ] `view_side` is recorded (`view_target_sides`) but not yet fed into the optimizer as an attractor — that lands with Phase 2 (roads/attractors). Side answer drives `requested_positions` today.
- [ ] Multi-turn resume in the live API currently needs a follow-up `/chat` call after `/clarify`; auto-resume is a future convenience.

## 2026-06-16 Frontend — Agent Overview Dashboard (full decision graph + site plan + explorer)

Builds the "overall view" of the agent on top of the existing backend contracts so the team can see *what the agent has* and *how it reasoned* in one screen — the full decision graph, the 2D site plan (multi-building layouts, footprint families, view-based Pareto placement), and the explorer tree. No backend changes; everything reads the routes that already exist. All under `team_04/frontend/`, so merges with `main` stay conflict-free.

### Completed

- [x] Completed the decision-graph node set: `decision-graph/BasicNodes.tsx` adds `IntentNode`, `ActionNode`, `BranchNode`, `SelectNode`, `StateNode` (compact accented cards) alongside the Phase 0 `BriefNode`; all six registered in `nodeTypes.ts`. Unknown future types still fall through to the React Flow default node.
- [x] Added a dependency-free `layoutLayered` (depth→row, order→column) to `decision-graph/adapters.ts` so the graph renders without dagre/elkjs.
- [x] `site/SiteCanvas.tsx` + `site/geometry.ts`: a 2D SVG plan that auto-fits north-up and draws the site boundary, the buildable zone (setbacks), every placed building coloured by footprint family (I/L/T/U/H/Y/X/O) with label + view score, and the focused building's Pareto view-placement options as ghosts (selected option highlighted). This surfaces multi-building workflows, generated boundaries, shape transformations, and view-analysis placement.
- [x] `explorer/ExplorerPanel.tsx`: collapsible Site → Buildings → (wings, view score, Pareto placement table with rank/score/rotation/fit) from `GET /sessions/{id}/explorer`.
- [x] `api/types.ts` + `api/client.ts`: TS types mirroring `backend/schemas.py` and a `Team04Api` typed client covering every JSON route (sessions, state, messages, explorer, site, buildings, options, view, decisions, select, tools).
- [x] `dashboard/AgentDashboard.tsx`: composes decision graph + site plan + explorer into one screen; click-to-focus a building overlays its options; `↻ Refresh` re-fetches. Example wiring for the live SSE `decision` stream documented in `frontend/README.md`.
- [x] Extended `decision-graph/CONTRACT.md` (new §6: explorer/geometry payloads) and rewrote `frontend/README.md` (dashboard usage, backend-surface→UI table, file tree). Updated the top-level `frontend/index.ts` barrel.

### Validation

- [x] `npm run typecheck` (`tsc --noEmit`, strict + `noUnusedLocals`/`noUnusedParameters`) passes with **0 errors** across the whole `frontend/` (decision graph, site canvas, explorer, dashboard, API client).
- [x] All wire types cross-checked field-by-field against `backend/schemas.py` (`SiteInfo`, `WingInfo`, `PlacementOption`, `BuildingInfo`, `ExplorerTree`, `SessionInfo`, `ViewAnalysisResult`, `ToolCallResponse`) and the decision-node shape.
- [x] `node_modules/` git-ignored; `git status` shows only `team_04/` paths.

### Active MVP Status

- [x] One dashboard now shows the agent end-to-end: reasoning DAG, the designed site/buildings, and the explorer hierarchy — all from live backend payloads.
- [x] Building footprint families, two-/multi-building layouts, and Pareto view-placement are all visualized from the explorer payload.
- [ ] 3D massing (per-wing heights, `view_3d`) is surfaced only as numbers today; a 3D view is deferred to Phase 7's frontend counterpart.
- [ ] The dashboard refreshes on demand / per turn; full live SSE node-streaming into the graph is wired in the README example but not yet a built-in dashboard mode.

## 2026-06-16 Phase 0 Frontend Lockstep — Decision-Graph Brief Node + `BriefNode` UI

Surfaces the Phase 0 comprehension step (the typed `DesignBrief`) in the live decision graph and ships its React Flow counterpart, establishing the policy that **frontend is updated in the same commit as the backend phase** (the original "frontend last / Phase 9" rule is superseded). All changes stay inside `team_04/`, so merges with `main` stay conflict-free.

### Completed

- [x] Added a first-class `brief` node type to the decision graph: `make_brief_node` in `backend/decision_graph.py` (carries `payload.design_brief` = `DesignBrief.to_state()`), the node-type list in the module docstring, and the `DecisionNodeSchema` comment in `backend/schemas.py`.
- [x] Wired the **live** `extract_brief` graph node into the chat SSE stream: `backend/routers/chat.py` detects the node's `on_chain_end` and emits a `decision` event of `type: "brief"`, hung off the `intent` node and before the first `action`. Guarded to fire once per turn and only when a brief is freshly comprehended (the node is idempotent and returns `{}` on pass-through).
- [x] Fixed a pre-existing blocker that prevented the chat endpoint from ever running: `chat.py` called `build_agent_graph()` with no arguments (it requires `decision_engine`, `tool_client`, `catalog`). Added `backend/agent_runtime.py` — a cached builder mirroring `agent/main.py`'s wiring (settings → LLM engine + local/MCP tools + catalog → compiled app) — and routed `chat.py` through `get_agent_app()`.
- [x] Added the `frontend/` module (new), kept in lockstep:
  - `frontend/decision-graph/CONTRACT.md` — backend↔frontend payload contract (transport, per-type payloads, SSE event order, the no-invention guarantee for the brief, and an "add a node type per phase" checklist).
  - `frontend/decision-graph/BriefNode.tsx` — React Flow custom node rendering the `DesignBrief` (count, shapes, objective-weight bars, courtyard/parking flags, `ambiguities`, `source = llm|fallback`). Self-contained inline styles; tolerant of the payload-less compact SSE node.
  - `frontend/decision-graph/types.ts` (mirror `agent/models.py` + `backend/schemas.py`), `nodeTypes.ts` (React Flow registry, one component per phase), `adapters.ts` (backend `{nodes,edges,head}` + SSE events → React Flow), `index.ts` barrel.
  - `frontend/README.md` — the lockstep policy, dependencies, a `DecisionGraphPanel` usage example (POST-SSE via `fetch-event-source`), and the per-phase frontend roadmap.
- [x] Updated `test_notebooks/test_decision_graph.ipynb` to the Phase 0 reaction flow: each turn now builds a real `brief` node from `extract_brief_fallback` + a `SiteModel` summary, with the DAG viz, selected-path trace, and step-by-step replay all rendering the new `brief` type.
- [x] Updated `ARCHITECTURE.md` (lockstep policy, new "Decision Graph and Frontend" section, refreshed Active Layout tree).

### Validation

- [x] Verified against the **real** compiled graph (local tools + a no-LLM dummy engine, breaking before any LLM/pymoo node) that `astream_events` emits `on_chain_end` named `extract_brief` whose output carries `design_brief` — confirming the SSE detection signal.
- [x] Exercised the router's brief-emission logic against the real graph: produces a `brief` decision node with the correct `intent → brief` parent link and label `Brief: 1x [L] (fallback)`.
- [x] `test_notebooks/test_decision_graph.ipynb` executes top-to-bottom on a fresh kernel (22 nodes; active path `USER → BRIEF → read_site → … → backtrack`).
- [x] `py_compile` clean on `backend/{routers/chat.py,agent_runtime.py,decision_graph.py,schemas.py}`.
- [x] `benchmarking/test_design_brief.py` brief/fallback/model tests pass; the 3 errors observed are all the `pymoo`-dependent full-run/placement tests (environment missing `pymoo`), not introduced by this change.
- [~] Not run here: a full live `POST /chat` round-trip — needs the LLM env + `pymoo` + `fastapi`, none fully available in this kernel. Every isolatable piece (event shape, emission logic, compilation) was verified; the end-to-end SSE should be smoke-tested once the backend runs with credentials configured.

### Active MVP Status

- [x] The agent's comprehension step is now visible end-to-end: prompt → `brief` node (typed `DesignBrief`) → actions, both in the notebook and over the live SSE stream.
- [x] Frontend lockstep policy established; `BriefNode` + payload contract are the Phase 0 deliverable.
- [ ] Dedicated React Flow components for `intent/action/branch/select/state` still fall through to the default node — cosmetic, tracked for follow-up.
- [ ] Phase 1 (sun analysis) remains the next backend target; its frontend counterpart is the sun-vector/facade-exposure overlay (per the roadmap in `frontend/README.md`).

## 2026-06-15 Phase 0 — Reasoning Core (Design Brief + Site Model)

Implements Phase 0 of `BACKEND_PLAN.md`: move comprehension out of long prompt rules and into a typed brief + a structured site model. Tested with `C:\Users\tuemi\AppData\Local\Programs\Python\Python311\python.exe` (has shapely/topologicpy/langgraph/langchain_openai/pymoo).

### Completed

- [x] Added `BuildingSpec` and `DesignBrief` frozen dataclasses to `agent/models.py`, matching the existing `PlanStep` pattern (no Pydantic). `from_payload` validates and clamps junk (weights to [0,1], shapes to the allowed `I/L/T/U/H/Y/X/O/auto` set, count never below the number of explicit specs).
- [x] Added `agent/brief.py` with a deterministic, LLM-free `extract_brief_fallback` (reuses the existing shape/area/rotation regex helpers, improved building-count detection so "two U-shaped buildings" resolves, not just the literal "two building") and `resolve_brief`, which prefers an engine's LLM extractor and falls back to regex on any failure.
- [x] Added `BRIEF_PROMPT` + `OpenAIDecisionEngine.extract_brief` to `agent/decision_engine.py` — one short prompt that returns the typed brief and records `ambiguities` instead of inventing values.
- [x] Added an `extract_brief` graph node at the start of the LangGraph (`START -> extract_brief -> planner`); idempotent, refines `target_building_count`/`building_intents` only when the layout did not set them, and is tolerant of engines without an `extract_brief` method (test stubs fall back to regex).
- [x] Routed `_repair_generate_shape_decision` to read shape/area/rotation from the active building's brief spec first, falling back to prompt regex so existing direct-call tests are unchanged.
- [x] Added `agent/tools/site_model.py` (`build_site_model`) — bundles boundary graph (corners/sides), per-side `adjacent_road` slots, and the setback/buildable zone into one structure with `roads`/`grid`/`sun` placeholders for Phases 1-3. Populated in the `read_site` node; surfaced (summarized) in the supervisor/report state snapshot.
- [x] Prompt diet: shrank `SUPERVISOR_PROMPT` from ~30 rule lines to a short role + active step + design brief + schema (deterministic guards in `_apply_step_guard`/`_repair_generate_shape_decision` already enforce the removed rules).
- [x] Added `design_brief` and `site_model` keys to `AgentState`.

### Validation

- [x] Added `benchmarking/test_design_brief.py` (16 deterministic tests: dataclass round-trip/clamping, fallback extraction across terse/verbose/vague/contradictory prompts, brief consumption in the repair layer, full-run brief-into-state, and site-model build). All pass.
- [x] `test_agent_graph` (15) and `test_boundary_tools` (15) remain green — the new brief node does not regress existing flows.
- [x] Added `test_notebooks/test_intent_extraction.ipynb`: prompt-set table (fallback), no-invention check, optional live-LLM table with `ambiguities`, and a SiteModel visualization (sides/corners/buildable zone). Code cells smoke-run clean.
- [x] Pre-existing unrelated failure noted: `test_generate_building_boundary.test_l_shape_is_translated_and_closed` fails identically on the clean tree (a shapely floating-point centroid boundary, `50.0 not > 50.0`) — not introduced by Phase 0.

### Active MVP Status

- [x] The agent now comprehends short prompts into a typed brief that drives shape/count/area/rotation, instead of scattered regex on the raw prompt at each step.
- [x] One canonical `SiteModel` exists with explicit slots for the next phases.
- [ ] Phase 1 (sun analysis) is the next target; it writes into `site_model["sun"]` and adds a `sun_weight`-driven objective.

## 2026-06-12 Backend Improvement Plan Authored

### Completed

- [x] Wrote `BACKEND_PLAN.md` — the phased checklist for upgrading the agent from view-only placement to a site-intelligent backend: structured design-brief extraction (less prompt, more comprehension), sun analysis fitness via the single-diagonal worst-sun method, road/transportation context, grid and site-side alignment, parking from apartments-per-building, circulation + public/private access + fire-access constraints, courtyard comprehension, per-wing 3D heights, full agent integration, and frontend API connection last.
- [x] Established the per-phase workflow contract: every capability ships as a deterministic tool in `agent/tools/`, with one visualization notebook in `test_notebooks/`, deterministic regressions in `benchmarking/`, and same-commit `PROGRESS.md` + `ARCHITECTURE.md` updates.
- [x] Documented dependencies and parallelization (sun and roads can run in parallel after Phase 0; grid needs roads; circulation needs roads + parking; frontend wiring is last).

### Active MVP Status

- [ ] Phase 0 (typed `DesignBrief` extraction node, canonical `SiteModel`, supervisor prompt diet) is the next implementation target.
- [ ] No sun, road, grid, parking, circulation, courtyard, or per-wing-height tooling exists yet — all tracked in `BACKEND_PLAN.md`.

### Validation

- [x] Confirmed the plan only references paths inside `team_04/` so merges with `main` stay conflict-free.

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