# AGENT_ui — Industrial Spatial Layout Agent

## Overview

A full-stack web application for visualizing and analyzing industrial spatial layouts using a LangGraph-based agent pipeline. The app integrates spatial reasoning, collision detection, visibility analysis, path finding, and automated scoring.

**Phase 1 (Complete)**: Core UI framework, backend API, WebSocket real-time communication, and visualization components.

## Directory Structure

```
AGENT_ui/
├── backend/
│   ├── server.py              FastAPI app entry point (port 3000)
│   ├── api_routes.py          REST endpoints for layouts, sessions
│   ├── websocket_manager.py    WebSocket ConnectionManager
│   ├── session_manager.py      In-memory session state
│   ├── agent_runner.py         Real LangGraph runner (threaded app.astream_events + input() bridge)
│   ├── pipeline_bridge.py      build_context (provider+model toggle), StdoutTee, CheckpointParser, MCP probe
│   ├── layout_loader.py        Loads layout JSONs from team_03/layout/
│   ├── adapters/
│   │   ├── graph_adapter.py    Wraps spatial_graph.py from team_03/python/
│   │   ├── analysis_adapter.py Wraps 5 analysis nodes (collision, visibility, etc.)
│   │   └── height_resolver.py  Resolves furniture heights
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx             Main app container
│   │   ├── main.tsx            React entry point
│   │   ├── types.ts            TypeScript interfaces (LayoutJSON, layers, etc.)
│   │   └── components/
│   │       ├── ThreeViewport/  3D floor plan renderer (7 layers, Three.js)
│   │       ├── GraphPanel/     Spatial graph vis.js visualization
│   │       ├── ChatPanel/      Message list, tool call cards
│   │       ├── Dashboard/      5 radial gauges, grade badge, histograms
│   │       ├── ProcessPanel/   Pipeline flow, tool status cards
│   │       ├── LayoutLoader/   Dropdown + drag-and-drop upload
│   │       ├── LayerToggle.tsx Toggle visibility of layers
│   │       └── common/         GlassPanel, ThemeToggle
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── dist/                   Built static files (production)
├── docs/                       This directory
├── tests/                      Test reports
└── sample_layout.json          Example layout for development
```

## How to Run

### Backend

```bash
cd backend
pip install -r requirements.txt
python server.py
# or: uvicorn server:app --port 3000 --reload
```

**Port**: 3000
**CORS**: Enabled for all origins (local development)
**Static files**: Serves frontend/dist/ if it exists (production mode)

### Frontend

```bash
cd frontend
npm install
npm run dev
# Dev server: http://localhost:5173
# Proxied API calls go to http://localhost:3000
```

**Port**: 5173 (dev), proxied to backend on 3000
**Build**: `npm run build` → frontend/dist/

### Running Both (Development)

Terminal 1:
```bash
cd backend && python server.py
```

Terminal 2:
```bash
cd frontend && npm run dev
```

Then open http://localhost:5173

## Tech Stack

| Layer     | Tech                                   | Version |
|-----------|----------------------------------------|---------|
| **Backend** | Python, FastAPI, uvicorn, WebSockets | 3.10+   |
| **Frontend** | React 19, Vite, TypeScript            | Latest  |
| **3D View** | Three.js, @react-three/fiber/@drei    | ^0.184  |
| **Graph** | vis-network, vis-data                  | ^10.1   |
| **Charts** | recharts                               | ^3.8    |
| **Pipeline** | LangGraph (team_03/python/, read-only) | Existing |
| **MCP/Rhino** | Kept intact, runs in background      | Existing |

## Key Conventions

### Styling & Theme

- **Colors**:
  - Background: `#0a0e17` (dark navy)
  - Accent: `#00E5FF` (cyan)
  - Room: `#1A4A6B` (dark blue)
  - Door: `#FF8C42` (orange)
  - Wall: `#2D3A45` (dark gray)
  - Window: `#00E5FF` (cyan)
  - Furniture: `#00CED1` (turquoise)
  - MEP: `#39FF14` (neon green)

- **UI Pattern**: Glass morphism with cyan accents
- **Default theme**: `light` (white background at startup) — set in `ThemeToggle.tsx`
  (`ThemeProvider` initial state), toggle persists in `localStorage`. The color list
  above is the dark-theme palette; the light theme uses its own palette.
- **No emojis** in code or UI text
- **Font**: Monospace (development mode), sans-serif (production)

### TypeScript

- Strict mode enabled (`tsconfig.json`)
- All React components are functional with hooks
- No `any` types; use proper interfaces
- See `frontend/src/types.ts` for data models

### WebSocket Protocol

**Client → Server** (message types):
- `chat_message`: `{ type: "chat_message", content: "..." }`
- `selection_sync`: `{ type: "selection_sync", selectedId: "...", timestamp: ... }`
- `provider_switch`: `{ type: "provider_switch", provider: "anthropic" | "google", model: "<key>" }` — switch the **pipeline** provider + model at runtime (`model` is a key from `PIPELINE_MODELS`: haiku/sonnet for Anthropic, flash/pro for Google). Applies to the next chat session. See "LLM model" below.
- `pure_chat`: `{ type: "pure_chat", content: "...", history: [{role, content}, ...] }` — pure chatbot: a direct Anthropic call, **no pipeline / no LangGraph**.

**Server → Client** (message types, from MessageType enum):
- `chat_message`: User message echoed
- `agent_response`: Final agent response with tool calls
- `agent_event`: Pipeline node started/completed
- `state_update`: Session state changed (layout, graph, scores)
- `selection_sync`: Selection broadcast to all clients
- `provider_switch_ack`: on success `{ provider, model, full_model, status: "ok" }`; on a missing API key `{ provider, status: "error", missingKey, envPath, detail }` (the active provider is left unchanged so the pipeline keeps working).
- `pure_chat_response`: `{ content, model }` — reply to a `pure_chat` message.

See `backend/websocket_manager.py` for ConnectionManager.

**GET `/api/llm-config`** (REST, not WS): returns the active pipeline `{ provider, model }`,
the selectable `available` models (`PIPELINE_MODELS`), which providers have credentials
(`credentials: { anthropic, google }`), and the repo-root `.env` path (`envPath`). The chat
panel calls it on mount to render the provider toggle synced to the real `.env` and to dim a
provider whose key is missing.

### API Endpoints

**GET** `/api/layouts`  
List all available layout JSONs from team_03/layout/

**GET** `/api/layouts/{name}`  
Load layout by stem name (e.g., `industrial_005`)

**POST** `/api/layouts/upload`  
Upload a layout JSON file; validates required keys

**GET** `/api/session`  
Get current session state (layout, graph, scores) or null

**POST** `/api/session`  
Create session with layout_name; initializes graph

**GET** `/api/graph`  
Retrieve the current spatial graph (node-link JSON)

**POST** `/api/graph`  
Rebuild graph with optional analysis results

**GET** `/api/scores`  
Get current scoring results

**POST** `/api/scores`  
Update scoring results

**POST** `/api/profile`  
Persist the onboarding User/Space profile to the global `team_03/memory/user_profile.md`. `build_context` later merges it into the active layout's memory under `## User Rules`. See `team_03/CLAUDE.md` → Conversational Memory → "Onboarding profile → memory".

**POST** `/api/analyze`  
Run the 5 analysis tools + scoring on a layout (`{ layout, profile_config?, space_config? }`) via `adapters/analysis_adapter.run_all` and return Dashboard `ScoreData`. Deterministic — no LLM/MCP. Drives the Dashboard "Analyze" button; the chat path also backfills scores via this same `run_all` when a turn answers without running the tools (`agent_runner`).

**POST** `/api/layouts/generate`  
**AI Layout Generator** — generate ONE floor plan with **Anthropic Sonnet** from the
panel form (`{ layoutType, areaMin, areaMax, programs:[{name,count}], brief, variantIndex }`)
and return `{ layout }`. The frontend calls this once per "Generate" click and accumulates
results into its in-memory library (max 4). The system prompt is
`backend/prompts/layout_generator_context.txt` (the schema/context doc) plus an industrial
addendum and a strict output contract; see `backend/layout_generator.py`. Model is
`LAYOUT_GEN_MODEL` (default `claude-sonnet-4-6`).

**POST** `/api/layouts/generated/save`  
Persist an accepted generated layout (`{ name, layout }`) to
`team_03/layout/AI_GENERATED/<name>.json` (`layout_loader.save_generated_layout`), so it
appears in the Layout Loader dropdown under the **AI_GENERATED** group. The user can save
several. `layoutId` is set to the sanitized file stem.

**POST** `/api/layouts/{name}/reload`  
Return the **live working layout** and update the session. The agent writes its placements to `team_03/workspace/session_active.json` (never the base file), so this prefers the workspace layout when it's the same layout (matching `layoutId`), falling back to the base file otherwise. The frontend polls this while the agent runs and once when it stops — reading the base file would drop just-added objects (e.g. a new desk), so they'd never appear in the viewport. New/moved elements are surfaced via the diff → `modifiedIds` → `PulseHighlight` accent-purple pulse.

### Do Not Modify

- **team_03/python/**: Read-only. All pipeline code is imported via adapters.
- **team_03/layout/**: Read-only **except** the `AI_GENERATED/` subfolder, where the AI
  Layout Generator writes accepted plans (`/api/layouts/generated/save`). The existing
  layouts (`industrial_100/`, `residential_100/`, …) are discovered and loaded, not written.
- **Rhino/MCP integration**: Kept intact; runs in background.

### File Structure Notes

- Backend adapters allow the web app to use team_03/python/ code without modifying it.
- Frontend components are self-contained; import from common/ for shared utilities.
- Session state is in-memory (no database); persists only during a single server run.
- Static files served from frontend/dist/ in production.

## Layout JSON Schema

Each layout must contain:
```json
{
  "layoutId": "string (unique)",
  "outline": [[x, y], ...],
  "rooms": [{ "id", "name", "geometry", "attributes" }],
  "doors": [{ "id", "type", "name", "geometry", "attributes" }],
  "windows": [{ "id", "type", "name", "geometry", "attributes" }],
  "furniture": [{ "id", "name", "geometry", "attributes" }],
  "mep": [{ "id", "name", "geometry", "attributes" }],
  "structure": [{ "id", "name", "geometry", "attributes" }]
}
```

Each item's `geometry` is a list of [x, y] coordinate pairs (2D).

## Development Notes

- **CORS**: Enabled globally; restrict in production.
- **WebSocket**: Uses JSON serialization; ensure all objects are JSON-serializable.
- **Layer System**: 7 toggleable layers (outline, rooms, doors, windows, furniture, mep, structure).
- **Selection**: Objects selected in 3D view; selection synced across all clients via WebSocket.
- **Adapters**: Gracefully handle missing optional dependencies (networkx, shapely); fail with error dict.

## Port Configuration

- **Backend API**: 3000
- **Frontend dev**: 5173 (proxied to backend on 3000)
- **Frontend prod**: Served from backend on 3000

## Chat ↔ real pipeline (wired)

The chat runs the **real** `team_03/python/` LangGraph pipeline — "the terminal, in
the browser". No demo/stub anymore.

- `agent_runner.start_session` builds a `Context` (`pipeline_bridge.build_context`)
  and runs `app.astream_events(version="v2")` in a worker thread, emitting
  `agent_event(node, started|completed|error)` per graph node → the **Pipeline panel
  + Log show live progress**. The stream is run with `recursion_limit=100`
  (`GRAPH_RECURSION_LIMIT` env) — LangGraph's default of 25 is too low for a full
  placement run (reason↔tool loops + the 5-tool analysis fan-out + up to
  `MAX_ADJUSTMENTS` re-placement loops) and aborts mid-run with a recursion error.
- The checkpoint's blocking `input("Your decision: ")` is bridged to the WebSocket:
  a monkeypatched `input()` blocks on a per-session queue fed by `chat_message` /
  `chat_decision`. On each `input()` the printed menu is parsed (`CheckpointParser`)
  into `agent_checkpoint` (agent message + score + suggestions + memory rules +
  actions) for the chat's right-side options panel.
- **One `app.invoke`/stream = one multi-turn session.** Session is owned by the
  websocket; on disconnect/refresh `abort_session()` unblocks the checkpoint
  (`_ABORT` sentinel) so the next connection starts fresh (no orphaned session).
- `build_context` does a fast TCP `_probe_mcp` and emits setup progress, so a
  down Swiftlet/Rhino fails fast with a clear chat error instead of hanging.

**LLM provider + model — runtime switch (pipeline only):** the chat panel has a two-row
selector — **Provider** (`Anthropic` | `Google`) and **Model** (haiku/sonnet or flash/pro,
depending on the provider). It controls **only the LangGraph pipeline**; the Anthropic
auxiliary features (`pure_chat`, `spatial_assistant`, `layout_generator`) are unaffected.

- A `provider_switch` WebSocket message calls `pipeline_bridge.set_pipeline_llm(provider,
  model_key)`, which validates the provider's API key (via `resolve_provider_credentials`)
  before mutating the process-global `_pipeline_provider` / `_pipeline_model`. On a missing key
  it raises and the server replies `provider_switch_ack status:"error"` with `missingKey` +
  `envPath` — the active provider stays as-is, so the pipeline keeps working.
- `build_context` reads `get_pipeline_provider() or settings.llm_provider`; when the active
  provider differs from the `.env` one it resolves that provider's own key/base_url/model via
  `resolve_provider_credentials`, and passes `provider=` explicitly to `create_chat_llm` /
  `get_llm_response_format` so the right model id and JSON format are used (no `claude-...`
  sent to the Gemini endpoint).
- The switch applies to the **next chat session** (`build_context` runs at `start_session`),
  not the run in progress.
- **Cerebro vs manos:** the toggle only changes *which LLM generates the decision* — it does
  **not** touch the JSON-writing / geometry-moving machinery (`place_objects` MCP →
  `add_objects.py` → `workspace/session_active.json` → `output.py`), which is identical for
  both providers. See `team_03/CLAUDE.md` → Configuration.

**Cost note:** Sonnet (and Gemini Pro) are selectable from the UI — mind the cost.

**Run the dev backend as a single process** (`python -m uvicorn server:app
--port 3000`); uvicorn `--reload` can leave stale workers serving old code. Note its
`--reload` watcher only watches `AGENT_ui/backend/` — edits to `team_03/python/`
(e.g. `_runtime/llm.py`) need a manual backend restart to load.

## Agent Log panel (`components/ReasoningLog/ReasoningLog.tsx`)

The floating **Agent Log** panel renders `agentState.logEntries` (pipeline
`node_start`/`node_complete`/`tool_call`/`reasoning`/`info` events). The on-screen
message is abridged (data truncated to ~120 chars, reasoning to ~150). Two header
buttons export the **full** content to the clipboard:

- **COPY LOG** — `buildDetailedLog(entries)`: every event with ms-precision timestamp,
  raw node name, the complete untruncated message, **and the entry's `data` payload**
  (pretty-printed JSON), which the panel itself never displays.
- **COPY CHAT** — `buildChatTranscript(messages)`: the conversation (user prompts +
  agent replies) in order, with timestamps and any `toolCalls` attached to a message.
  `messages` is passed in from `App.tsx` (`agentState.messages`).

Both use `navigator.clipboard.writeText` with a hidden-`textarea` + `execCommand`
fallback for non-secure contexts, and flash **COPIED** for 1.5s. Each is disabled when
its source is empty. All logic is self-contained in `ReasoningLog.tsx`.

## AI Layout Generator (UI)

A full-panel tool that swaps the entire left sidebar (button under the Layout Loader,
`App.tsx` `generatorMode`). Frontend in `frontend/src/components/AILayoutGenerator/`
(`AILayoutGenerator.tsx` + `MiniPlan.tsx` SVG thumbnails).

- **Form**: layout type (residential/industrial segmented control), an **ideal total
  area** dual-thumb range slider (single track, start/end handles — `.dual-range` in
  `styles/index.css`), program **pills** with per-item counts (+ user-added pills), and a
  free-text brief.
- **Generate** → `POST /api/layouts/generate` (one Sonnet call per click). Each result is
  appended to an in-memory **library capped at 4**; at 4/4 Generate is disabled until a
  candidate is discarded. A shimmer + spinner loading card shows while generating.
- Clicking a library card **previews it live** in the ThreeViewport
  (`useLayoutState.previewLayout` / `endPreview`). **Accept & use** → `saveAndLoadGenerated`
  → `POST /api/layouts/generated/save` writes `team_03/layout/AI_GENERATED/<name>.json`,
  refreshes the dropdown, and loads it as the active project layout. Several can be saved.
- **Theme**: solid accent fills in dark mode; translucent accent (matching the Analyze
  button / view pills) in light mode. The nav brand title is theme-aware too.

---

## Chat ↔ terminal parity (checkpoint options)

The chat's right-side **Options panel** (`ChatPanel/ChatOptionsPanel.tsx`) mirrors the
terminal checkpoint (`team_03/python/nodes/checkpoint.py`) command set. The backend bridge
(`agent_runner` + `pipeline_bridge.CheckpointParser`) forwards any chip/text token to the
real `input("Your decision:")`, so these all drive the *same* pipeline:

- **Suggestions** `s1..s5`, **memory rules** (`rule:` add / `forget:` remove / list),
  **actions** (approve / end / next-zone) — chips + free text.
- **Detailed report** — `CheckpointParser` now also captures the **score delta** vs the
  previous checkpoint (▲/▼), **collision violations**, **furniture changes** (ADDED/MOVED +
  coords) and **door changes**, surfaced as sections in the Options panel
  (`agent_checkpoint` payload fields: `prevScore`, `violations`, `changes`, `doorChanges`).
- **Viewport view controls** (UI-adapted toggles, `App.handleView`): `Before` shows the
  original base layout in the 3D viewport (`previewLayout` of `GET /api/layouts/{name}`),
  `After` restores the live workspace layout (`endPreview`), `Collision/Visibility/Paths`
  run `/api/analyze` and highlight that Dashboard gauge (`Dashboard focusMetric`), `Clear`
  resets. Typing a bare `0`–`5` while a checkpoint is open triggers the matching view
  (terminal muscle-memory). These are **frontend-only** (they do NOT push to Grasshopper as
  the terminal does, because the UI shows the layout + Dashboard simultaneously).

## Spatial assistant — observer / visibility / path in chat (Rhino-free)

The Agent chat **auto-routes** observer/visibility/path questions to a lightweight assistant
(`backend/spatial_assistant.py`) instead of the LangGraph pipeline. This analysis is pure
Python (`isovist.py` + `adapters/analysis_adapter.py`) so it **works even when Rhino/Swiftlet
is down** and answers in real time, drawing the result in the 3D viewport.

- **Routing** (`server.py` `/ws` `chat_message`) is two-tier so a paused pipeline run can't
  monopolize the chat:
  - **Strong** observer intent (`is_strong_spatial_query`: person/observer/isovist/sightline)
    is always handled by the assistant, and if a pipeline run is paused at a checkpoint it is
    **aborted** first (the user switched to observer work).
  - **Weak** wording (`is_spatial_query` adds visibil/vista/view/obstru/path/camino/ruta…) is
    routed to the assistant only when **no** pipeline run is active — otherwise it stays a
    checkpoint decision (so "make the path wider" isn't hijacked).
  - Everything else starts/feeds the LangGraph pipeline ("place a cnc in the workshop").
- **Tools** (Anthropic tool-use, active model): `place_person(location)` (also **moves/
  re-places** the existing person), `start_path(from,to)`, `analyze_visibility()` (uses the
  observer already placed), `analyze_collisions()`, `analyze_path()`. Locations are resolved
  from layout geometry (`resolve_location`): room centroid, door/entrance, **furniture/MEP
  item by name** ("near assembly station 1", "the toilet" → a point ~1.2 m beside it, not
  inside its footprint), and ES/EN synonyms (baño→bathroom, almacén→warehouse, …).
- **Obstruction analysis** (`isovist.analyze_obstructions` / `_path`): from an observer,
  classifies every furniture/MEP as **visible** or **hidden**, and reports the movable
  **blockers** that occlude others (e.g. "Conveyor Section 10 hides Assembly Station 1").
- **Live viewport**: the assistant emits the same `observer_result` message the manual
  observer uses, plus an `agentObserver` field ({mode, point|path}) → `App` draws the isovist
  surface + a read-only ghost `ObserverMarker` and auto-switches to the 3D view.
- **Observer memory**: `SessionManager.observer` stores the last observer placed (manually in
  the viewport OR by the agent) + its isovist, so "I just placed the person — which furniture
  blocks the view?" works on the already-placed observer. (`server.py` records it on
  `observer_point`/`observer_path`; the assistant reads/updates it.)
- **Caveat**: the conversational answer uses Anthropic tool-use (like `pure_chat`) → needs
  `LLM_PROVIDER=anthropic` + a valid key. The analysis + viewport drawing need no Rhino.

## Export 3D model (OBJ + MTL)

The 3D viewport has an **OBJ** button (top-right compact controls row, next to
Center/Labels, `ThreeViewport.tsx` `handleExportObj`) that downloads the **currently
visible layers** as a 3D model — `<layoutId>_<timestamp>.obj` + a matching `.mtl`.

- **Source of truth:** the OBJ is generated **from the live layout JSON** (`layoutState.layout`
  — i.e. whatever the agent has placed), not from the Three.js scene, so it's clean and
  deterministic. The shared geometry rules live in `ThreeViewport/geometry.ts` (extracted from
  `FloorPlanRenderer.tsx` — constants `WALL_HEIGHT`/`DOOR_HEIGHT`/…, `resolveHeight`,
  `assignOpenings`, `buildWallPieces`, `wallRectFromLine`), imported by **both** the renderer
  and the exporter so they can't drift.
- **Coordinate basis — Z-up, metres, real origin:** OBJ vertex = `(layout.x, layout.y, height)`.
  The floor plan stays in the XY plane and Z is vertical (the basis the JSON / Rhino / GH were
  authored in), un-centered — so a re-import lands exactly on the original plan, right way up.
  (The viewport itself is Y-up + centered; the exporter deliberately does NOT use that.)
- **Per-layer geometry** (`utils/objExporter.ts` `layoutToObj`): rooms = flat floor faces at
  Z=0; structure = wall pieces with door/window openings cut out, extruded; doors = boxes Z
  0→2.2; windows = boxes Z 1.0→2.0; furniture/mep = polygons extruded to `resolveHeight`;
  outline = a closed polyline (`l`). Concave polygons are triangulated via
  `THREE.ShapeUtils.triangulateShape`. Each layer is an OBJ group (`g <layer>`) with one object
  (`o <id>_<name>`) per element; the `.mtl` assigns each layer a color.
- **WYSIWYG:** only layers toggled on in the viewport are exported. Two files download per click
  (`.obj` then `.mtl`) — the browser may ask to allow multiple downloads once.

## Benchmark dashboard (model performance + workflow)

A third top-nav view (`3D Viewport` | `Spatial Graph` | **`Benchmark`**, `App.tsx`
`ViewMode='benchmark'`) that records and compares every pipeline run — built from the
`ramon_experiments/benchmarking_ramy` prototype, re-themed and made **data-driven**.

**Auto-recording (backend).** Each chat session = one **BenchRun**, captured by
`backend/benchmark.py` (`BenchRunRecorder`) and hooked into `agent_runner.run()` — it
reuses the events the runner already streams, so `team_03/python/` (read-only) is untouched:
- `emit_event(node, started|completed|error)` → per-node timings (Gantt) + API-call
  categories (`_NODE_CATEGORY`: profile/space/populate/memory/reason/tools/analysis/other) +
  `reason` turn count. `setup` is skipped (it streams repeated progress lines).
- `emit_scores(overall, grade, breakdown)` → final scoring (overall + grade + 5 weighted metrics).
- `patched_input` → checkpoint count; a `recursion`-flagged exception → `recursion_hits`.
- Provider/model resolved at run start from `pipeline_bridge.get_pipeline_provider/model`
  (UI toggle) falling back to `.env` → `model_label` (`Gemini Flash`/`Gemini Pro`/`Haiku`/
  `Sonnet`/…), so runs are attributed to the right model.

Runs persist to `backend/benchmarks/runs.json` (append, capped at 500, survives restarts).
On finalize the runner emits a `benchmark_update` WS message → the UI re-fetches.

**REST + WS.**
- `GET /api/benchmarks` → `{ runs (newest-first), aggregate.models (per-model averages), count }`.
- `DELETE /api/benchmarks` → wipe history.
- `benchmark_update` (added to `MessageType` + `wsProtocol.ts`) → live refresh signal.

**Frontend.** `hooks/useBenchmarkState.ts` (fetch on mount + on `benchmark_update`, `clear`)
feeds `components/Benchmark/BenchmarkDashboard.tsx`. Two internal tabs, a model filter, and a
scope summary KPI row:
- **Models & Scores** (prototype module 02) — score trend over runs (points colored by model),
  per-metric model comparison bars, and a per-model leaderboard table. This is where the
  **Google Gemini Flash/Pro vs Anthropic Haiku/Sonnet** performance comparison lands.
- **Workflow** (prototype module 03) — turns/zone, API calls, time, recursion KPIs; a Gantt of
  per-node durations + an API-calls-by-category breakdown for the latest run; an event-log
  timeline; and a multi-run turns/duration trend.

**Status / next iterations:** module 01 (Placement Quality — req/placed, zone assignment,
collision-free, wall violations, heatmap) is scaffolded in `benchmark.py`
(`set_placement_quality`, `run["placement"]`) but not yet wired — planned next, derived from
`collision_results` + the base→final layout diff.

---

**Last updated**: 2026-06-20  
**Status**: Chat wired to the real pipeline; live progress + options panel. Default theme
now **light** (white startup background), favicon + new logo, StrictMode disabled. **Runtime
model switch** (Haiku/Sonnet via `model_switch` WS) replaces the old Haiku-force; added a
**pure-chat** mode (`pure_chat` WS, direct Anthropic call, no pipeline) and a **resizable
chat strip** (drag handle, 180–600px). AI Layout Generator panel (Sonnet) → generates plans
one at a time, library of 4, live preview, saves accepted plans to AI_GENERATED.
**Chat↔terminal parity** in the Options panel (viewport view chips + detailed checkpoint
report: delta/violations/changes/door changes). **Spatial assistant** auto-routes
observer/visibility/path questions to a Rhino-free agent (place a person / start a path /
"which furniture blocks the view") that draws the isovist live and answers in chat.
