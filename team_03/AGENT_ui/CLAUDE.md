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
│   ├── agent_runner.py         Stub LangGraph pipeline runner
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

## Integration Notes (Phase 2)

- **Agent B**: Replace `agent_runner.py` with real LangGraph pipeline.
- **Agent F**: Complete WebSocket/frontend integration tests.
- **Adapter maintenance**: As new analysis nodes are added, expand adapters in backend/.

---

**Last updated**: 2026-05-23  
**Status**: Phase 1 Complete — Framework ready for integration
