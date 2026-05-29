# AGENT_ui Build Summary — Phase 1

## What Was Built

A full-stack web application for visualizing and analyzing industrial spatial layouts. Five agents contributed:

| Agent | Component | Status |
|-------|-----------|--------|
| **A** | Backend core (FastAPI, WebSocket, API) | Complete |
| **C** | Frontend UI (React, Vite, TypeScript) | Complete |
| **D** | 3D visualization (Three.js, floor plan renderer) | Complete |
| **E** | Dashboard & analysis visualization (vis.js, recharts) | Complete |
| **F** | Integration & testing | In Progress (Phase 2) |

**Timeline**: Phase 1 complete as of 2026-05-23. Phase 2 integration in progress.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (Client)                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ React App (Vite, TypeScript)                           │ │
│  │ ┌──────────────┬──────────────┬──────────────────────┐ │ │
│  │ │ ThreeViewport│ GraphPanel   │ ChatPanel            │ │ │
│  │ │ (3D floor)   │ (vis.js net) │ (messages, tool card)│ │ │
│  │ └──────────────┴──────────────┴──────────────────────┘ │ │
│  │ ┌──────────────┬──────────────┬──────────────────────┐ │ │
│  │ │ Dashboard    │ ProcessPanel │ LayoutLoader         │ │ │
│  │ │ (gauges,badge)│ (pipeline)   │ (upload, dropdown)   │ │ │
│  │ └──────────────┴──────────────┴──────────────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
│                          │ HTTP/WS                          │
└──────────────────────────┼──────────────────────────────────┘
                           │
                    localhost:3000
                           │
┌──────────────────────────┼──────────────────────────────────┐
│          Backend (Python, FastAPI)                          │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ server.py (Uvicorn, CORS, static file serving)         │ │
│  │ ┌──────────────────────────────────────────────────┐   │ │
│  │ │ API Routes                                       │   │ │
│  │ │ GET  /api/layouts          → list_layouts()     │   │ │
│  │ │ GET  /api/layouts/{name}   → load_layout()      │   │ │
│  │ │ POST /api/layouts/upload   → upload_layout()    │   │ │
│  │ │ GET  /api/session          → get_session()      │   │ │
│  │ │ POST /api/session          → create_session()   │   │ │
│  │ │ GET  /api/graph            → get_graph()        │   │ │
│  │ │ POST /api/graph            → rebuild_graph()    │   │ │
│  │ │ GET  /api/scores           → get_scores()       │   │ │
│  │ │ POST /api/scores           → update_scores()    │   │ │
│  │ └──────────────────────────────────────────────────┘   │ │
│  │ ┌──────────────────────────────────────────────────┐   │ │
│  │ │ WebSocket Handler (/ws)                          │   │ │
│  │ │ • chat_message → run_agent() in background      │   │ │
│  │ │ • selection_sync → broadcast to all clients     │   │ │
│  │ └──────────────────────────────────────────────────┘   │ │
│  │ ┌──────────────────────────────────────────────────┐   │ │
│  │ │ Session Manager (in-memory state)                │   │ │
│  │ │ • layout, layout_name, graph, scores             │   │ │
│  │ └──────────────────────────────────────────────────┘   │ │
│  │ ┌──────────────────────────────────────────────────┐   │ │
│  │ │ Adapters (wrap team_03/python code)              │   │ │
│  │ │ • graph_adapter.py        (spatial_graph)        │   │ │
│  │ │ • analysis_adapter.py     (5 analysis nodes)     │   │ │
│  │ │ • height_resolver.py      (furniture heights)    │   │ │
│  │ └──────────────────────────────────────────────────┘   │ │
│  │ ┌──────────────────────────────────────────────────┐   │ │
│  │ │ Layout Loader (discovers team_03/layout/)        │   │ │
│  │ └──────────────────────────────────────────────────┘   │ │
│  │ ┌──────────────────────────────────────────────────┐   │ │
│  │ │ Agent Runner (stub; real LangGraph in Phase 2)   │   │ │
│  │ └──────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────┘ │
│                          │                                  │
└──────────────────────────┼──────────────────────────────────┘
                           │
                 team_03/python/ (read-only)
                 • spatial_graph.py
                 • 5 analysis nodes
                 • Rhino/MCP integration
```

## Key Decisions

### 1. Adapter Pattern for Python Integration
- **Why**: team_03/python/ is mature, tested, and read-only. Adapters wrap it so the web app can use it without modification.
- **How**: `graph_adapter.py` and `analysis_adapter.py` import from team_03/python/, handle exceptions gracefully, and return JSON.
- **Benefit**: Clean separation; pipeline can evolve independently.

### 2. vis.js for Spatial Graph Visualization
- **Why**: vis-network provides interactive force-directed layout, perfect for spatial relationship visualization.
- **How**: GraphPanel converts spatial graph (node-link JSON) to vis.js nodes/edges; users can pan, zoom, click.
- **Benefit**: Lightweight, real-time updates, industrial aesthetic.

### 3. Three.js for 3D Floor Plan
- **Why**: Native WebGL rendering, supports 7-layer visualization, smooth interaction, fast performance.
- **How**: ThreeViewport converts layout JSON to Three.js geometries; layers togglable, selection via raycasting.
- **Benefit**: Immersive 3D visualization; scales to large layouts.

### 4. FastAPI + WebSocket
- **Why**: Async-first, WebSocket-native, lightweight.
- **How**: Single entry point (server.py); ConnectionManager handles broadcast/personal messages; agent_runner spawns tasks.
- **Benefit**: Real-time updates, scalable; production-ready.

### 5. In-Memory Session State
- **Why**: Phase 1 focus is on getting the UI working; simplicity over persistence.
- **How**: SessionManager holds layout, graph, scores; survives across requests during server uptime.
- **Benefit**: No database setup; quick iteration.
- **Note**: Will need persistent storage (DB) in Phase 2+.

### 6. Vite + React 19
- **Why**: Fast HMR, minimal config, modern JavaScript.
- **How**: Single SPA (client-side routing ready); TypeScript strict mode; no build artifact bloat.
- **Benefit**: Dev experience, rapid prototyping.

## API Reference

All endpoints return JSON. Base URL: `http://localhost:3000`

### Layouts

```
GET /api/layouts
Returns: [{ layoutId, outline, rooms, doors, windows, furniture, mep, structure }, ...]

GET /api/layouts/{name}
Params: name (stem of layout file, e.g., "industrial_005")
Returns: { layoutId, outline, rooms, ... }
Error: 404 if not found

POST /api/layouts/upload
Body: multipart form-data (file: JSON layout)
Returns: { status, tmp_path, name, layout }
Error: 400 if not JSON, 422 if missing required keys
```

### Session

```
GET /api/session
Returns: { layout, layout_name, graph, scores } or null

POST /api/session
Body: { layout_name: "string" }
Returns: { layout, layout_name, graph, scores }
```

### Graph

```
GET /api/graph
Returns: { nodes: [...], links: [...] } (node-link JSON)

POST /api/graph
Body: { layout, collision_results?, visibility_results?, ... }
Returns: { nodes, links } (enriched spatial graph)
```

### Scores

```
GET /api/scores
Returns: { grade, radial_scores: { collision, visibility, path, ... }, ... } or null

POST /api/scores
Body: { grade, radial_scores, histograms, ... }
Returns: Same
```

## WebSocket Protocol

**Endpoint**: `ws://localhost:3000/ws`

### Client → Server

```json
{
  "type": "chat_message",
  "content": "Analyze the layout for collision issues"
}
```

```json
{
  "type": "selection_sync",
  "selectedId": "room_01",
  "timestamp": 1234567890
}
```

### Server → Client

```json
{
  "type": "agent_event",
  "node": "collision",
  "status": "started"
}
```

```json
{
  "type": "agent_event",
  "node": "collision",
  "status": "completed"
}
```

```json
{
  "type": "agent_response",
  "content": "Analysis complete. Collision detected in room_02.",
  "tool_calls": [
    { "tool": "flag_collision", "params": { "roomId": "room_02" } }
  ]
}
```

```json
{
  "type": "state_update",
  "layout": { ... },
  "graph": { ... },
  "scores": { ... }
}
```

```json
{
  "type": "selection_sync",
  "selectedId": "room_01",
  "timestamp": 1234567890
}
```

## How to Run (Full Stack)

### Prerequisites
- Python 3.10+
- Node 18+

### Terminal 1: Backend
```bash
cd AGENT_ui/backend
pip install -r requirements.txt
python server.py
# Listening on http://localhost:3000
```

### Terminal 2: Frontend (Development)
```bash
cd AGENT_ui/frontend
npm install
npm run dev
# Vite dev server on http://localhost:5173
# Proxied API calls to http://localhost:3000
```

### Access
Open http://localhost:5173 in your browser.

### Production Build
```bash
cd frontend
npm run build
# Outputs to frontend/dist/
# Backend will serve static files from dist/ if present
```

## File Manifest — Phase 1 Complete

### Backend
- ✓ `server.py` — Entry point, CORS, static serving, WS handler
- ✓ `api_routes.py` — REST endpoints for layouts, session, graph, scores
- ✓ `websocket_manager.py` — ConnectionManager, MessageType enum
- ✓ `session_manager.py` — In-memory session state
- ✓ `agent_runner.py` — Stub LangGraph runner (12 nodes)
- ✓ `layout_loader.py` — Load from team_03/layout/
- ✓ `adapters/graph_adapter.py` — Wraps spatial_graph.py
- ✓ `adapters/analysis_adapter.py` — Wraps analysis nodes
- ✓ `adapters/height_resolver.py` — Furniture height resolution
- ✓ `requirements.txt` — Dependencies (fastapi, uvicorn, websockets, etc.)

### Frontend
- ✓ `App.tsx` — Main container, layout loading, selection state
- ✓ `types.ts` — LayoutJSON, LayerVisibility interfaces
- ✓ `components/ThreeViewport/` — 3D floor plan (7 layers, selection, raycasting)
- ✓ `components/GraphPanel/` — vis.js spatial graph visualization
- ✓ `components/ChatPanel/` — Message list, tool call cards
- ✓ `components/Dashboard/` — 5 radial gauges, grade badge, histograms, weight bar
- ✓ `components/ProcessPanel/` — Pipeline flow, tool status cards
- ✓ `components/LayoutLoader/` — Dropdown + drag-and-drop upload
- ✓ `components/LayerToggle.tsx` — Toggle visibility
- ✓ `components/common/` — GlassPanel, ThemeToggle
- ✓ `package.json`, `tsconfig.json`, `vite.config.ts`
- ✓ Built output: `frontend/dist/` (production only)

### Documentation
- ✓ `CLAUDE.md` — Project overview, conventions, how to run
- ✓ `docs/build-summary.md` — This file (architecture, decisions, API)
- ✓ `tests/report.md` — Component status and integration notes

## Next Steps (Phase 2)

1. **Agent B**: Replace `agent_runner.py` with real LangGraph integration.
2. **Agent F**: Complete WebSocket→UI integration tests; verify all message flows.
3. **Database**: Replace SessionManager with persistent storage (PostgreSQL, SQLite, etc.).
4. **Error Handling**: Add granular error messages, logging, and monitoring.
5. **Authentication**: Secure WebSocket and API endpoints (Phase 3).

---

**Build Date**: 2026-05-23  
**Status**: Phase 1 Complete  
**Next Phase**: Integration & Real LangGraph
