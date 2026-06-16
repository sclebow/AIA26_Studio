# Team 04 Architecture

## Planned Evolution (2026-06-12)

`BACKEND_PLAN.md` defines the phased roadmap from the current view-only placement agent to a site-intelligent backend. **Phase 0 (reasoning core) is implemented** — see the 2026-06-15 entry in `PROGRESS.md`. The architectural commitments it introduces:

- **Typed `DesignBrief`**: a one-shot LLM extraction node at graph start converts the user prompt into a typed brief (building count, shapes, areas, storeys, courtyard intent, parking, objective weights, explicit ambiguities). Downstream nodes read the brief, never re-parse the prompt; regex intent helpers in `decision_engine.py` become test-only fallbacks.
- **Canonical `SiteModel`**: `read_site` builds one structured site object (boundary graph, per-side metadata, roads, placement grid, sun context, setbacks/buildable zone) that all tools consume — one source of truth instead of raw coordinate lists.
- **Prompt diet**: supervisor prompt shrinks to role + active step + brief + catalog slice; every enforceable rule moves into deterministic planner guards or the argument-repair layer.
- **Fitness assembly**: a deterministic `build_objectives(brief, site_model)` selects active NSGA-II objectives (view, sun, courtyard quality) and hard constraints (site fit, setbacks, separation, fire access, parking feasibility); grid/side alignment restricts the sampling space. The LLM sets weights only, via the brief.
- **New tool families** under `agent/tools/`: `sun_analysis`, `road_context`, `site_grid`, `parking`, `circulation`, `courtyard`, plus per-wing heights in the wing graph and `view_3d`.
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
│       └── site_model.py   # Phase 0: canonical SiteModel
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