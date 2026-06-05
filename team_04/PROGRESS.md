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

### Notebook Direction

- [ ] Create a final test notebook where the controlling loop is framed as a React-style agent node test for the LangGraph runtime, repeatedly inspecting site-fit feedback and calling placement or modification tools until the footprint fits the site boundary.
- [ ] In that final notebook, log each attempted action, the returned site-fit summary, and the final accepted placement so the placement loop is visually inspectable.
- [ ] In that final notebook, keep the focus on one LangGraph node behavior at a time: take the current prompt and state, choose one action, call one tool family, inspect the result, and decide whether to loop, stop, or escalate to another modification strategy.
- [ ] Extend that node-test notebook toward two-building placement by adding a second-building pass after the first footprint is accepted inside the site boundary.
- [ ] Add site objects such as streets, edges, or alignment guides into the notebook input payload so later prompts can request building alignment to those site objects.
- [ ] Keep `tool_dev_mode.ipynb` focused on deterministic local tool and geometry debugging, and reserve the final loop notebook for iterative agent-style placement behavior.

### Current Next Notebook Target

- [x] Reworked `test_notebooks/end_to_end_api_agent.ipynb` into the current prompt-driven LangGraph node harness with scenario selection, two-building intent, and notebook-local site-object inputs.

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