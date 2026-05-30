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
│   ├── pipeline_bridge.py      build_context (Haiku-forced), StdoutTee, CheckpointParser, MCP probe
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

- **UI Pattern**: Glass morphism with dark theme, cyan accents
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

**Server → Client** (message types, from MessageType enum):
- `chat_message`: User message echoed
- `agent_response`: Final agent response with tool calls
- `agent_event`: Pipeline node started/completed
- `state_update`: Session state changed (layout, graph, scores)
- `selection_sync`: Selection broadcast to all clients

See `backend/websocket_manager.py` for ConnectionManager.

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

**POST** `/api/layouts/{name}/reload`  
Return the **live working layout** and update the session. The agent writes its placements to `team_03/workspace/session_active.json` (never the base file), so this prefers the workspace layout when it's the same layout (matching `layoutId`), falling back to the base file otherwise. The frontend polls this while the agent runs and once when it stops — reading the base file would drop just-added objects (e.g. a new desk), so they'd never appear in the viewport. New/moved elements are surfaced via the diff → `modifiedIds` → `PulseHighlight` accent-purple pulse.

### Do Not Modify

- **team_03/python/**: Read-only. All pipeline code is imported via adapters.
- **team_03/layout/**: Read-only. Layouts are discovered and loaded, not written.
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

**LLM model — cost policy:** `build_context` hard-forces **`claude-haiku-4-5`**
(cheapest Anthropic model) for the `anthropic` provider, regardless of
`ANTHROPIC_MODEL` in `.env`. See `team_03/CLAUDE.md` → Configuration.

**Run the dev backend as a single process** (`python -m uvicorn server:app
--port 3000`); uvicorn `--reload` can leave stale workers serving old code.

---

**Last updated**: 2026-05-29  
**Status**: Chat wired to the real pipeline; live progress + options panel; Haiku-forced.
