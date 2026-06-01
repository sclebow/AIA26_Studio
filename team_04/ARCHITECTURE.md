# Team 04 Architecture

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
│   ├── config.py
│   ├── decision_engine.py
│   ├── graph.py
│   ├── main.py
│   ├── mcp_client.py
│   ├── models.py
│   ├── state.py
│   └── tool_catalog.py
├── legacy/
│   ├── README.md
│   ├── PY_legacy/
│   └── python_legacy/
├── tests/
│   └── test_agent_graph.py
└── main.py
```

## LangGraph Structure

The graph now separates planning from execution:

```
START
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

- `planner`: builds a typed task sequence from current state and selects the active plan step.
- `central_reason`: now acts as a step-scoped supervisor. It only reasons over the active step, and only calls the LLM for `generate_shape` and `optimize`.
- `read_site`: runs the site/context/legal-reader tool group automatically.
- `generate_shape`: executes only allowed shape-generation tool calls. The local boundary generator now supports `I`, `L`, `T`, `Y`, `H`, `X`, and `O` footprints plus direct translation, mirroring, and orientation or rotation parameters.
- `check_requested_position`: evaluates a user-requested placement point for the current building and records geometric feasibility facts.
- `check_constraints`: runs the full constraint suite automatically and derives violation categories.
- `optimize`: executes only allowed manipulation tool calls and increments the optimization cycle counter. The local manipulation fallback now includes `modify_building_boundary_04` for move, orientation, rotation, mirroring, and site-fit checks before the Grasshopper tool is live.
- `evaluate`: runs the full evaluation suite automatically.
- `place_building`: sends the validated building footprint into Rhino/Grasshopper placement tools.
- `analyze_remaining_positions`: queries the remaining site area for candidate locations before the next building cycle begins.
- `await_human`: exits non-interactively with a clarification question in `final_response`.
- `report`: builds the final narrative response.

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

- `test_generate_building_boundary.ipynb`: single-building boundary generation and Grasshopper handoff.
- `test_two_building_workflow.ipynb`: two-building placement sequencing with requested-point checks and remaining-position analysis.
- `test_multi_building_shape_transformations.ipynb`: many-building stress test across `L`, `I`, `Y`, `T`, `H`, `X`, and `O`, including move, orientation, rotation, mirroring, and site-fit checks.

There is also one live notebook harness under `team_04/tests/` for direct MCP verification:

- `tests/test_context_reader_live.ipynb`: validates Team 04 environment loading, OpenAI connectivity, Swiftlet MCP discovery, and a direct live call to the `context_reader` Grasshopper tool.