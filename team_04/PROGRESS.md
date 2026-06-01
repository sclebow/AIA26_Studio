# Team 04 Progress

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
- [x] Added a notebook test harness at `test_generate_building_boundary.ipynb` to run the tool and prepare a Grasshopper handoff payload.
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
- [ ] Run `test_generate_building_boundary.ipynb` against live Grasshopper import behavior.
- [ ] Run `test_two_building_workflow.ipynb` against live Grasshopper placement-analysis behavior.
- [ ] Implement `modify_building_boundary_04` and verify move, orientation, rotation, and mirroring preserve closed boundaries.
- [ ] Verify `modify_building_boundary_04` reports whether transformed buildings leave or intersect the site boundary.
- [ ] Run `test_multi_building_shape_transformations.ipynb` against the live Grasshopper manipulation tool.
- [ ] Capture one successful end-to-end two-building MCP session and record the expected input/output payloads.

### Current Active Components

- [x] `agent/graph.py`: canonical LangGraph definition.
- [x] `agent/decision_engine.py`: planner, execution-supervisor, and reporting interfaces.
- [x] `agent/tool_catalog.py`: tool grouping and action-policy enforcement.
- [x] `agent/models.py`: typed routing and plan-step models.
- [x] `agent/state.py`: workflow state including plan, active step, and replanning flags.
- [x] `agent/state.py`: workflow state including plan, active step, replanning flags, and multi-building placement context.
- [x] `agent/mcp_client.py`: HTTP MCP adapter plus local/composite tool support.
- [x] `agent/config.py`: runtime settings and layout loading.
- [x] `agent/tools/generate_building_boundary.py`: local footprint generation tool.
- [x] `agent/tools/modify_building_boundary.py`: local footprint transformation and site-fit classification tool.
- [x] `agent/tools/multi_building_mock.py`: local mock tools for placement import, requested-position checks, and remaining-site analysis.
- [x] `main.py`: top-level entry point.
- [x] `test_generate_building_boundary.ipynb`: notebook-based local tool test and Grasshopper payload prep.
- [x] `test_two_building_workflow.ipynb`: notebook-based two-building workflow and user-requested position test.
- [x] `test_multi_building_shape_transformations.ipynb`: notebook-based multi-building shape, transform, and site-fit stress test.
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