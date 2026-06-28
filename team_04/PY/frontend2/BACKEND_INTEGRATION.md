# frontend2 ↔ Backend Integration Report

> Deliverables 1–5 (inventory, contracts, mapping, missing list, plan).
> **Policy applied: Backend-First / Frontend-Fallback.** Nothing is mocked or
> invented. Where no backend route exists, the existing frontend behavior is
> retained and documented.

---

## 0. Key finding (read first) — supersedes the previous version of this doc

There is exactly **ONE real backend**: the **connection layer** FastAPI app at
`team_04/PY/connection/`. It is the notebook-validated Agent API and it also
serves frontend2 at `/`.

```
uvicorn connection.app:app --reload --port 8001
# then open  http://127.0.0.1:8001/
```

The earlier version of this report described a second live backend — **"TerraPilot
Backend A"** at `team_04/PY/backend/main.py`, exposing `/copilot`,
`/set-site-location`, `/generate-options`, `/optimize-site`, `/export/rhino`, etc.
**That backend does not exist** — there is no `backend/` directory anywhere in the
repo and none of those routes are served by anything. The wrappers for it in
`core/api.js` are now marked **DORMANT** and are not called by the live UI.

So the integration is: **drive the whole design conversation through the real
`connection/` backend** (which `agentClient.js` already targets), and treat the
map/geocoding/boundary-draw and export as features the core agent does not expose
over HTTP. For those, the **connection layer** (the integration bridge, *not* the
core agent) was extended with thin routes that **reuse the real agent tools** —
see §1b. No core agent file was modified.

---

## 1a. Endpoint inventory — core Agent API (`connection/`, pre-existing)

| Method | Route | Request | Response | Category |
|---|---|---|---|---|
| GET | `/health` | – | `{status, agent_ready}` | infra |
| GET | `/` | – | serves `frontend2/index.html` | infra |
| POST | `/sessions` | `{layout_payload{user_prompt, site_boundary, building_intents, requested_positions, target_building_count, workflow_mode}, max_optimization_cycles}` | `{session_id, status}` | Site seed + Agent |
| GET | `/sessions` | – | `SessionInfo[]` | Agent |
| GET | `/sessions/{id}` | – | `SessionInfo` | Agent |
| DELETE | `/sessions/{id}` | – | `{deleted}` | Agent |
| GET | `/sessions/{id}/state` | – | full `AgentState` | Agent |
| GET | `/sessions/{id}/messages` | – | `ChatMessage[]` | Copilot |
| POST | `/sessions/{id}/chat` | `{message, tags}` | **SSE**: `token \| tool \| decision \| state \| error \| done` | Copilot / Shape Gen / Manipulation / Optimization |
| GET | `/sessions/{id}/decisions` | – | `{nodes, edges, head}` | Decision Graph |
| GET | `/sessions/{id}/decisions/{node_id}` | – | `{...node, children}` | Decision Graph |
| POST | `/sessions/{id}/decisions/{node_id}/select` | `{reason}` | `{selected_node_id, select_node, graph_head}` | Decision Graph |
| GET | `/sessions/{id}/explorer` | – | `{session_id, site, buildings[]}` | Site / Shape / Comparison |
| GET | `/sessions/{id}/site` | – | `SiteInfo` | Site |
| GET | `/sessions/{id}/buildings` | – | `BuildingInfo[]` | Shape Generation |
| GET | `/sessions/{id}/buildings/{b_id}` | – | `BuildingInfo` | Shape |
| GET | `/sessions/{id}/buildings/{b_id}/options` | – | `PlacementOption[]` | Optimization |
| GET | `/sessions/{id}/buildings/{b_id}/view?height&floor_height&piece_length&ray_length` | – | view-analysis result | Optimization/Analysis |
| GET | `/tools` | – | `{tools[]}` | Tools |
| POST | `/tools/{name}` | `{tool_name, arguments}` | `{success, result\|error}` | Tools |

## 1b. Endpoint inventory — connection-layer additions (this task)

Added under `connection/routers/` to give the frontend's map/boundary/export
stages a real backend. **They delegate to the real agent tools** — no agent logic
was reimplemented, no core agent file touched.

| Method | Route | Reuses | Category |
|---|---|---|---|
| POST | `/site/geocode` `{query, limit}` → `{results[{name,lat,lng}]}` | OpenStreetMap Nominatim (real geocoder proxy) | Site |
| POST | `/site/boundary/analyze` `{boundary}` → `{area_sqm, analysis}` | `agent.tools.site_boundary_graph.analyze_site_boundary` | Boundary |
| POST | `/site/boundary/buildable-zone` `{boundary, setback}` → `{buildable_boundary[], setback_summary}` | `agent.tools.site_setback.setback_summary` | Boundary |
| POST | `/sessions/{id}/site/boundary` `{boundary, center?, location_name?}` → `{site_boundary, area_sqm}` | writes `AgentState.site_boundary` (same field `build_initial_state` sets) | Boundary |
| GET | `/export/{id}/geojson` → FeatureCollection (download) | serializes `AgentState.placed_buildings` + `site_boundary` | Export |
| GET | `/export/{id}/json` → bundle (download) | serializes `AgentState` geometry | Export |
| POST | `/export/{id}/rhino-mcp` `{best_only}` | forwards real geometry to Rhino MCP **if** the tool client exposes a send tool; else reports unavailable | Export |

---

## 2. Payload contracts (the frontend contracts)

### 2a. Building / geometry — `BuildingInfo` (GET `/explorer`, `/buildings`)
```json
{ "building_id": "...", "label": "U building", "building_type": "U",
  "area_sqm": 900.0, "boundary": [[x,y], ...], "centroid": [x,y],
  "height_m": 12, "wings": [WingInfo], "placement_options": [PlacementOption],
  "view_score": 0.0 }
```
Rich raw shape (wings, `building_graph.centerline_graph`, `option_catalog`,
`object_hierarchy`) is in `AgentState.placed_buildings[]` via `/state` — see
`tool_dev_mode_payload.json`.

### 2b. Wing metadata — `WingInfo`
```json
{ "wing_index": 0, "role": "base|left_wing|right_wing", "area_sqm": 743.76,
  "centroid": [x,y] }
```

### 2c. Centerline graph — `AgentState…building_graph.centerline_graph` (via `/state`)
```
{ node_count, edge_count, nodes:[{node_index, kind:"joint|endpoint", point[3], connected_wings[]}],
  edges:[{edge_index, wing_index, role, centerline:[[x,y,z]...], length_m, ...}] }
```

### 2d. Optimization output — `PlacementOption` (GET `/buildings/{id}/options`)
```json
{ "option_id": "placement_option_01", "rank": 1, "combined_score": 0.0,
  "unblocked_view_score": 0.0, "attractor_view_score": 0.0,
  "rotation_degrees": 3.8, "centroid_xy": [x,y], "boundary": [[x,y,z]...],
  "outside_area_sqm": 0.0, "fits_within_site": true }
```

### 2e. Planner / supervisor trace
Streamed live as `decision` + `tool` SSE events during chat, and stored in
`AgentState.decision_trace[]` / `tool_sequence[]` (see
`end_to_end_api_agent_output.json`).

### 2f. Decision graph — GET `/sessions/{id}/decisions`
```json
{ "nodes": [{ "node_id","type","label","parent_id","is_selected","payload" }],
  "edges": [{ "id","source","target" }], "head": "<node_id>" }
```
Types: `intent | action | branch | select | state`.

---

## 3. Frontend-stage → backend mapping (live)

| Stage | Backend route | Viewer component | Status |
|---|---|---|---|
| Site location / geocode | `POST /site/geocode` (Nominatim proxy) | `views/mapView.js` (pin/fly) | ✅ connected |
| Site coordinate input | client parse → map | `mapView.js` | ✅ frontend (no route needed) |
| Boundary draw/edit | client draw → `POST /site/boundary/analyze` + `/buildable-zone` | `mapView.js` | ✅ connected |
| Boundary save | `POST /sessions` (seed) + `POST /sessions/{id}/site/boundary` | `mapView.js` | ✅ connected |
| Shape generation | `POST /sessions/{id}/chat` → `GET /explorer` | `views/viewerView.js` + `panels/explorer.js` | ✅ connected |
| Shape manipulation | agent `chat` (modify_building_* tools) | `viewerView.js` | ✅ connected (agent-driven) |
| Optimization | agent `chat` → `GET /buildings/{id}/options` | `viewerView.js` | ✅ connected |
| Comparison | client table over `/buildings` + `/options` metrics | `views/compareView.js` | ✅ reuses backend data |
| Decision graph | `GET/POST /sessions/{id}/decisions...` | `views/decisionGraphView.js` | ✅ connected |
| Export | `GET /export/{id}/geojson|json`, `POST /export/{id}/rhino-mcp` | download / `agentClient.exportSession` | ✅ connected |
| Copilot chat | `POST /sessions/{id}/chat` (SSE) | `panels/copilot.js` + `copilotClient.js` | ✅ connected |

Real backend geometry (`BuildingInfo.boundary`, `PlacementOption.boundary`) is
projected into the viewer/compare option model by
`agentClient.buildingToViewerOptions()` — a pure projection, no fabricated values.

---

## 4. Missing endpoints (documented, not faked)

1. **Native Rhino `.3dm` / IFC `.ifc` writers** — none exist in the repo (only a
   mock). *Handled:* `/export/{id}/geojson|json` exports the **real** session
   geometry; `/export/{id}/rhino-mcp` forwards to the Rhino MCP server only if the
   tool client exposes a send tool, otherwise returns `501/503` honestly.
2. **Dedicated comparison endpoint** — none by design. Metrics come from
   `BuildingInfo`/`PlacementOption` already returned by `/explorer` + `/options`.
   Not "missing" — intentionally client-side over real data.
3. **Legacy "TerraPilot Backend A" routes** (`/copilot`, `/set-site-location`,
   `/generate-options`, `/optimize-site`, `/export/rhino`, `/state`, `/reset-design`,
   …) — **no server implements these.** The wrappers remain in `core/api.js`,
   marked DORMANT, and the live UI does not call them.

---

## 5. Integration plan (what was implemented)

**Backend (connection layer only — core agent untouched):**
- `connection/routers/site.py` — geocode proxy + boundary analysis + buildable
  zone + persist-boundary, all delegating to real agent tools.
- `connection/routers/export.py` — GeoJSON/JSON/Rhino-MCP export of real state.
- `connection/app.py` — registered the two new routers (additive).

**Frontend:**
- `core/api.js` — added `geocode / analyzeBoundary / buildableZone /
  saveSessionBoundary / exportGeojsonUrl / exportJsonUrl / exportRhinoMcp` under
  `api.agent.*` (real routes). Dormant Backend-A wrappers annotated, not deleted.
- `core/config.js` — single backend; default base = same-origin.
- `core/store.js` — added `buildableBoundary`, `siteAnalysis`, `comparisonOptions`
  (the requested backend-driven fields; the rest already existed).
- `copilotClient.js` — rewritten: SITE/BOUNDARY handled locally with the real
  geocode/boundary routes and seed an agent session with the confirmed boundary;
  SHAPES onward stream through the real agent (`agentClient.streamChat`).
  Compare/Export are client view/download actions over real backend data.
- `agentClient.js` — `refreshExplorer()` now projects real `buildings[]` /
  `placement_options[]` into the viewer/compare option model and re-renders the
  3D viewer; added `exportSession()`.
- Viewer/explorer/compare/decision views already consume these shapes.

**Net effect:** every connected stage uses the real `connection/` backend. The
only frontend-managed pieces are coordinate parsing and the map drawing UX (the
agent owns no map workflow). No mock geometry, no fake optimization, no duplicated
backend logic, no core agent file modified.
