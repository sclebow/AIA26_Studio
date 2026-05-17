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
- `generate_shape`: executes only allowed shape-generation tool calls.
- `check_requested_position`: evaluates a user-requested placement point for the current building and records geometric feasibility facts.
- `check_constraints`: runs the full constraint suite automatically and derives violation categories.
- `optimize`: executes only allowed manipulation tool calls and increments the optimization cycle counter.
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

It validates:
- planner plus supervisor completion through shape generation, constraint repair, evaluation, and reporting;
- non-blocking `await_human` behavior;
- multi-building sequencing through requested-position checks, placement, and remaining-site analysis.