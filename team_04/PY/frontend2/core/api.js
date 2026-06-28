// Thin fetch wrappers over the project's backends. Panels/views never build URLs
// by hand.
//
// Two backends are exposed (see core/config.js + BACKEND_INTEGRATION.md):
//   * api.*        → Backend A (TerraPilot, same-origin, serves frontend2)
//   * api.agent.*  → Backend B (Team-04 Agent API — the notebook-validated
//                    /sessions, SSE chat, /decisions, /explorer, /tools routes),
//                    reached via the configurable AGENT_BASE in config.js.
//
// Backend First / Frontend Fallback: where Backend B validates a capability we
// call it; the Backend A wrappers remain for capabilities B does not cover.
// Nothing here mocks a response or invents a payload.

import { agentUrl, config } from "./config.js";

async function request(path, { method = "GET", body, signal } = {}) {
  const opts = { method, signal, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }
  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || res.statusText;
    const err = new Error(detail || `Request failed: ${path}`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// ===========================================================================
// Backend B — Team-04 Agent API (notebook-validated). Base URL from config.
// Route contracts confirmed against team_04/backend/routers/*.py.
// ===========================================================================
const agent = {
  // ---- sessions (routers/sessions.py) ----
  // POST /sessions  body:{layout_payload, max_optimization_cycles} -> {session_id, status}
  createSession: (layout_payload = {}, max_optimization_cycles = 6) =>
    request(agentUrl("/sessions"), {
      method: "POST",
      body: { layout_payload, max_optimization_cycles },
    }),
  listSessions: () => request(agentUrl("/sessions")),
  getSession: (id) => request(agentUrl(`/sessions/${id}`)),
  deleteSession: (id) => request(agentUrl(`/sessions/${id}`), { method: "DELETE" }),
  // GET /sessions/{id}/state -> full AgentState snapshot
  getSessionState: (id) => request(agentUrl(`/sessions/${id}/state`)),
  // GET /sessions/{id}/messages -> ChatMessage[]
  getMessages: (id) => request(agentUrl(`/sessions/${id}/messages`)),

  // ---- chat (routers/chat.py) ----
  // POST /sessions/{id}/chat is an SSE stream, NOT plain JSON. Use streamChat()
  // below (in copilotClient) to consume token/tool/decision/state/error/done
  // events. This URL helper is provided so the stream consumer stays declarative.
  chatUrl: (id) => agentUrl(`/sessions/${id}/chat`),

  // ---- decision graph (routers/decisions.py) ----
  // GET /sessions/{id}/decisions -> {nodes, edges, head}
  getDecisionGraph: (id) => request(agentUrl(`/sessions/${id}/decisions`)),
  // GET /sessions/{id}/decisions/{node_id} -> {...node, children:[...]}
  getDecisionNode: (id, nodeId) =>
    request(agentUrl(`/sessions/${id}/decisions/${nodeId}`)),
  // POST /sessions/{id}/decisions/{node_id}/select body:{reason}
  //   -> {selected_node_id, select_node, graph_head}
  selectDecisionNode: (id, nodeId, reason = "") =>
    request(agentUrl(`/sessions/${id}/decisions/${nodeId}/select`), {
      method: "POST",
      body: { reason },
    }),

  // ---- explorer tree (routers/explorer.py) ----
  // GET /sessions/{id}/explorer -> {session_id, site, buildings[]}
  getExplorer: (id) => request(agentUrl(`/sessions/${id}/explorer`)),
  getExplorerSite: (id) => request(agentUrl(`/sessions/${id}/site`)),
  getBuildings: (id) => request(agentUrl(`/sessions/${id}/buildings`)),
  getBuilding: (id, buildingId) =>
    request(agentUrl(`/sessions/${id}/buildings/${buildingId}`)),
  // GET .../buildings/{b}/options -> PlacementOption[] (Pareto option catalog)
  getBuildingOptions: (id, buildingId) =>
    request(agentUrl(`/sessions/${id}/buildings/${buildingId}/options`)),
  // POST .../buildings/{b}/transform {translate_by_xy, rotation_degrees, scale}
  //   -> moves/rotates/scales the placed building via modify_building_boundary and
  //   persists the new boundary. Rejects (and restores) if it leaves the site.
  transformBuilding: (id, buildingId, { translate_by_xy = [0, 0], rotation_degrees = 0, scale = 1, part_id = "building" } = {}) =>
    request(agentUrl(`/sessions/${id}/buildings/${buildingId}/transform`), {
      method: "POST",
      body: { translate_by_xy, rotation_degrees, scale, part_id },
    }),
  // GET selectable parts (whole building + wings) for part selection.
  getBuildingParts: (id, buildingId) =>
    request(agentUrl(`/sessions/${id}/buildings/${buildingId}/parts`)),
  // POST .../buildings/{b}/feedback {feedback, apply} — the AI architectural-
  //   feedback layer: translates design intent ("I want more daylight") into
  //   move/rotate/scale/floor actions and executes them through the SAME geometry
  //   backend as transformBuilding. Returns {reason, observations, actions[], metrics}.
  // part_id / part_name target a specific building element (wing/tower/central mass)
  // so the manipulation modifies ONLY the selected geometry, not another wing.
  buildingFeedback: (id, buildingId, feedback, apply = true, part_id = null, part_name = null) =>
    request(agentUrl(`/sessions/${id}/buildings/${buildingId}/feedback`), {
      method: "POST",
      body: { feedback, apply, part_id, part_name },
    }),

  // ---- saved design options (manipulated shape versions) ----
  // Persist the client-computed urban context so the BACKEND can use it for
  // context-aware shape generation ("long facade on east", "near metro edge").
  storeContext: (id, ctx) =>
    request(agentUrl(`/sessions/${id}/context/store`), { method: "POST", body: ctx }),
  // Persist edge/corner SELECTION so "align to selected edge" can validate + use it.
  storeSelection: (id, sel) =>
    request(agentUrl(`/sessions/${id}/context/selection`), { method: "POST", body: sel }),

  saveDesignOption: (id, { building_id = null, prompt = null, label = null } = {}) =>
    request(agentUrl(`/sessions/${id}/design-options/save`), {
      method: "POST",
      body: { building_id, prompt, label },
    }),
  listDesignOptions: (id) => request(agentUrl(`/sessions/${id}/design-options`)),
  selectDesignOption: (id, optionId) =>
    request(agentUrl(`/sessions/${id}/design-options/${optionId}/select`), { method: "POST" }),
  // optionIds: optimize only these saved shapes; omit/empty = all of them.
  optimizeAllSavedShapes: (id, optionIds = null) =>
    request(agentUrl(`/sessions/${id}/design-options/optimize-all`), {
      method: "POST",
      body: optionIds && optionIds.length ? { option_ids: optionIds } : {},
    }),
  // F6: analysis-only evaluation of the current building (no geometry change).
  evaluateDesign: (id) =>
    request(agentUrl(`/sessions/${id}/evaluate-design`), { method: "POST" }),
  // F9: optimization + evaluation history (feeds comparison).
  optimizationHistory: (id) => request(agentUrl(`/sessions/${id}/optimization-history`)),

  // ---- decision history + final selection (real project timeline) ----
  addDecision: (id, entry) =>
    request(agentUrl(`/sessions/${id}/decision`), { method: "POST", body: entry }),
  getDecisionHistory: (id) => request(agentUrl(`/sessions/${id}/decision-history`)),
  selectFinalOption: (id, option_id, option = {}) =>
    request(agentUrl(`/sessions/${id}/select-final`), { method: "POST", body: { option_id, option } }),
  getSelectedFinal: (id) => request(agentUrl(`/sessions/${id}/selected-final`)),

  // ---- final-option export (real .3dm / Revit-compatible .ifc) ----
  exportSelectedRhinoUrl: (id) => agentUrl(`/sessions/${id}/export/selected/rhino`),
  exportSelectedIfcUrl: (id) => agentUrl(`/sessions/${id}/export/selected/ifc`),
  // POST /sessions/{id}/optimize -> top-ranked options from the REAL view_optimizer
  //   NSGA-II pipeline (score, objective breakdown, FAR, coverage, setback, floors).
  optimizeSession: (id, opts = {}) =>
    request(agentUrl(`/sessions/${id}/optimize`), { method: "POST", body: opts }),
  // POST /sessions/{id}/generate-options -> multi-typology options (I/L/U/H/T/O)
  //   at distinct positions when the prompt doesn't name a shape.
  generateOptions: (id, prompt, opts = {}) =>
    request(agentUrl(`/sessions/${id}/generate-options`), { method: "POST", body: { prompt, ...opts } }),
  // POST /sessions/{id}/select-shape {option_id} — STAGE 2: promote one generated
  //   typology to the session's placed building so optimization runs on it.
  selectShape: (id, option_id) =>
    request(agentUrl(`/sessions/${id}/select-shape`), { method: "POST", body: { option_id } }),
  // ---- urban context (Context Analysis stage) ----
  // POST /sessions/{id}/context — live Overpass fetch (cached on the session):
  //   roads/amenities/buildings (projected), per-edge distances, 10 scores, report.
  analyzeContext: (id, opts = {}) =>
    request(agentUrl(`/sessions/${id}/context`), { method: "POST", body: opts }),
  getContext: (id) => request(agentUrl(`/sessions/${id}/context`)),
  // GET .../buildings/{b}/view?height&floor_height&piece_length&ray_length
  getBuildingView: (id, buildingId, params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null)
    ).toString();
    return request(
      agentUrl(`/sessions/${id}/buildings/${buildingId}/view${qs ? `?${qs}` : ""}`)
    );
  },

  // ---- site + boundary (routers/site.py) ----
  // POST /site/geocode {query,limit} -> {results:[{name,lat,lng,...}]}
  //   Real geocoder proxy (OpenStreetMap Nominatim). The map view falls back to
  //   its own client-side geocoding if this route or the upstream is unavailable.
  geocode: (query, limit = 5) =>
    request(agentUrl("/site/geocode"), { method: "POST", body: { query, limit } }),
  // POST /site/boundary/analyze {boundary} -> {area_sqm, analysis{...}}  (real agent tool)
  analyzeBoundary: (boundary) =>
    request(agentUrl("/site/boundary/analyze"), { method: "POST", body: { boundary } }),
  // POST /site/boundary/buildable-zone {boundary,setback} -> {buildable_boundary[], setback_summary}
  buildableZone: (boundary, setback = 3) =>
    request(agentUrl("/site/boundary/buildable-zone"), {
      method: "POST",
      body: { boundary, setback },
    }),
  // POST /sessions/{id}/site/boundary {boundary,center?,location_name?} -> persists onto AgentState
  saveSessionBoundary: (id, boundary, { center, location_name } = {}) =>
    request(agentUrl(`/sessions/${id}/site/boundary`), {
      method: "POST",
      body: { boundary, center, location_name },
    }),

  // ---- export (routers/export.py) — real session geometry, no fabricated files ----
  exportGeojsonUrl: (id) => agentUrl(`/export/${id}/geojson`),
  exportJsonUrl: (id) => agentUrl(`/export/${id}/json`),
  // POST /export/{id}/rhino-mcp {best_only} -> forwards real geometry to Rhino MCP if present
  exportRhinoMcp: (id, best_only = false) =>
    request(agentUrl(`/export/${id}/rhino-mcp`), { method: "POST", body: { best_only } }),

  // ---- direct tools (routers/tools.py) ----
  // GET /tools -> {tools:[...]}
  listTools: () => request(agentUrl("/tools")),
  // POST /tools/{name} body:{tool_name, arguments} -> {tool_name, success, result|error}
  callTool: (toolName, args = {}) =>
    request(agentUrl(`/tools/${toolName}`), {
      method: "POST",
      body: { tool_name: toolName, arguments: args },
    }),

  // Liveness probe for Backend B so the UI can detect availability and fall back.
  ping: () => request(agentUrl("/")),
};

// ===========================================================================
// Runtime API — the /api/* routes that wrap connection/notebook_logic, the
// SINGLE shared implementation used by the notebooks too. The frontend never
// implements this logic itself; it always goes through these routes:
//   frontend2 → /api/* → connection/notebook_logic → agent.* / connection.*
// ===========================================================================
const runtime = {
  // ---- site (single source of truth: confirmed_site.json) ----
  // POST /api/site/confirm {boundary, project, location_name, origin} -> {saved, site}
  //   project=true means boundary is lng/lat and is projected to meters server-side.
  confirmSite: (boundary, { project = true, location_name, origin } = {}) =>
    request(agentUrl("/api/site/confirm"), {
      method: "POST",
      body: { boundary, project, location_name, origin },
    }),
  getConfirmedSite: () => request(agentUrl("/api/site/confirmed")),
  clearConfirmedSite: () => request(agentUrl("/api/site/confirmed"), { method: "DELETE" }),

  // ---- geometry (tool_dev_runtime) ----
  // POST /api/geometry/generate {area, building_type, site_boundary?, options} -> {result, payload}
  generateGeometry: (area, { building_type = "I", site_boundary, options = {} } = {}) =>
    request(agentUrl("/api/geometry/generate"), {
      method: "POST",
      body: { area, building_type, site_boundary, options },
    }),
  modifyGeometry: (geometry_id, boundary, { site_boundary, options = {} } = {}) =>
    request(agentUrl("/api/geometry/modify"), {
      method: "POST",
      body: { geometry_id, boundary, site_boundary, options },
    }),
  modifyWings: (geometry_id, wings, building_graph, edits, { shape_type = "CUSTOM", site_boundary, options = {} } = {}) =>
    request(agentUrl("/api/geometry/wings"), {
      method: "POST",
      body: { geometry_id, wings, building_graph, edits, shape_type, site_boundary, options },
    }),

  // ---- agent (agent_runtime) — one-shot prompt-to-design (JSON, non-streaming) ----
  // POST /api/agent/run {prompt, layout?, use_confirmed_site} -> {state, geometry, *_trace, tool_sequence}
  runAgent: (prompt, { layout, max_optimization_cycles = 3, use_confirmed_site = true } = {}) =>
    request(agentUrl("/api/agent/run"), {
      method: "POST",
      body: { prompt, layout, max_optimization_cycles, use_confirmed_site },
    }),

  // ---- optimization (view_optimization_runtime) ----
  objectives: () => request(agentUrl("/api/optimize/objectives")),
  optimize: (boundary, { obstacles = [], site_boundary, options = {} } = {}) =>
    request(agentUrl("/api/optimize"), {
      method: "POST",
      body: { boundary, obstacles, site_boundary, options },
    }),
  optimizeTwo: (boundary_1, boundary_2, { external_obstacles = [], site_boundary, options = {} } = {}) =>
    request(agentUrl("/api/optimize/two"), {
      method: "POST",
      body: { boundary_1, boundary_2, external_obstacles, site_boundary, options },
    }),
  rankPlacements: (boundary, { obstacles = [], site_boundary, sample_options = {}, rank_options = {} } = {}) =>
    request(agentUrl("/api/optimize/rank"), {
      method: "POST",
      body: { boundary, obstacles, site_boundary, sample_options, rank_options },
    }),

  // ---- decision graph (decision_graph_runtime) ----
  getDecisionGraph: () => request(agentUrl("/api/decision-graph")),
  resetDecisionGraph: () => request(agentUrl("/api/decision-graph"), { method: "DELETE" }),
  addDecisionOption: (options, parent_id = null) =>
    request(agentUrl("/api/decision-graph/option"), {
      method: "POST",
      body: { options, parent_id },
    }),
  selectDecisionNode: (node_id) =>
    request(agentUrl("/api/decision-graph/select"), {
      method: "POST",
      body: { node_id },
    }),
};

export const api = {
  // Configurable base for Backend B (read by copilotClient for the SSE stream).
  agentBase: config.agentBase,
  agent,
  // Runtime routes (/api/*) over the shared connection/notebook_logic modules.
  runtime,

  // =========================================================================
  // DORMANT — legacy "TerraPilot Backend A" wrappers. NO server in this repo
  // implements these routes (there is no backend/main.py). They are retained,
  // not deleted, but the live integration does NOT call them: site/boundary now
  // use api.agent.geocode/analyzeBoundary/saveSessionBoundary, export uses
  // api.agent.exportGeojsonUrl/exportRhinoMcp, and the design conversation runs
  // through api.agent chat/explorer/decisions. Calling anything below will hit a
  // 404 unless such a server is added later. See BACKEND_INTEGRATION.md §Missing.
  // =========================================================================

  // ---- copilot orchestrator (Backend A stage machine) ----
  copilot: (message, stage, context = {}) =>
    request("/copilot", { method: "POST", body: { message, stage, context } }),

  // ---- global state ----
  getState: () => request("/state"),
  resetDesign: (reason = "reset") =>
    request("/reset-design", { method: "POST", body: { reason } }),

  // ---- stage 1: site ----
  setSiteLocation: (payload) =>
    request("/set-site-location", { method: "POST", body: payload }),
  loadSiteContext: () => request("/load-site-context", { method: "POST", body: {} }),
  siteState: () => request("/site-state"),
  siteContext: (forceRefresh = false) =>
    request(`/site-context${forceRefresh ? "?force_refresh=true" : ""}`),

  // ---- stage 2: boundary ----
  validateBoundary: (boundary_geojson) =>
    request("/validate-site-boundary", { method: "POST", body: { boundary_geojson } }),
  editBoundary: (payload) =>
    request("/edit-site-boundary", { method: "POST", body: payload }),
  confirmBoundary: (payload) =>
    request("/confirm-site-boundary", { method: "POST", body: payload }),

  // ---- stage 3: shapes ----
  generateOptions: (prompt) =>
    request("/generate-options", { method: "POST", body: { prompt } }),

  // ---- shape edit / manipulation ----
  promptEditDesign: (payload) =>
    request("/prompt-edit-design", { method: "POST", body: payload }),
  manipulateDesign: (payload) =>
    request("/manipulate-current-design", { method: "POST", body: payload }),
  acceptOption: (option_id) =>
    request("/accept-option", { method: "POST", body: { option_id } }),

  // ---- stage 4: optimize ----
  optimizeSite: (prompt, candidate_count) =>
    request("/optimize-site", { method: "POST", body: { prompt, candidate_count } }),
  optimizationState: () => request("/optimization-state"),
  optimizationHistory: () => request("/optimization-history"),
  bestOptions: () => request("/best-options"),

  // ---- export ----
  exportRhinoUrl: () => "/export/rhino",
  exportIfcUrl: () => "/export/ifc",
  sendToMcp: (best_only = false) =>
    request("/send-to-mcp", { method: "POST", body: { best_only } }),
};
