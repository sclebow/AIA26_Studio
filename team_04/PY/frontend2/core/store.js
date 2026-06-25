// Minimal observable app store. One state object, subscribe()/setState() with
// shallow merge. Panels subscribe and re-render on change. No framework needed.

import { STAGES } from "./stages.js";
import { shortenCopilotResponse } from "./responseFormatter.js";

const listeners = new Set();

const state = {
  stage: STAGES.SITE,
  status: "Ready",

  // chat transcript: { role: 'assistant'|'user', text, actions?, ts }
  messages: [],
  // action buttons currently offered by the copilot
  actions: [],

  // which center view is shown: 'map' | 'viewer' | 'compare' | 'evolution'
  centerView: "map",

  // site
  site: null, // serialized SiteContext from backend
  location: null, // { name, lat, lng } once a location is set (not yet saved)
  locationSaved: false,
  boundary: [], // [[lng,lat], ...] working polygon
  boundarySaved: false,
  // buildable zone + boundary analysis from the real backend (routers/site.py).
  // Populated only by api.agent.analyzeBoundary / buildableZone responses.
  buildableBoundary: null, // [[x,y,z], ...] inset polygon from setback_summary
  siteAnalysis: null, // analyze_site_boundary result (graph + hierarchy)

  // urban context (the Context Analysis stage) — client-side overpass.js shape.
  // `context` holds the full analyzeContext() result: layers{group.key→{roads,
  // points,polys,count,nearest,style}}, buildings[], edges[], scores{}, report{}.
  context: null,
  contextScores: null,         // = context.scores (10× 0-100), surfaced for KPIs
  contextVisible: null,        // {layerId: bool} visibility for explorer + twin
  contextLoading: false,
  contextError: null,
  selectedEdge: null,          // currently selected edge from Urban Context {edge_id, label, direction, ...}
  selectedEdges: [],           // F2: multi-selected edges (shift+click) for "selected edge(s)" prompts
  selectedCorner: null,        // F3: selected site corner {name:"northeast", x, y} for "selected corner" prompts

  // shapes / designs
  // Stage 1 SHAPE LIBRARY: the generated typology options the user picks FROM
  // (Rectangle / L / U / H / Courtyard / …). Distinct from `options` (which holds
  // OPTIMIZATION results) so shape generation never gets mistaken for optimization.
  shapeOptions: [], // generated shape candidates awaiting selection
  visibleShapeIds: new Set(), // eye-toggled shapes shown in the viewer
  selectedShapeId: null, // the shape the user previewed/highlighted
  selectedShapeType: null, // the typology the user committed to (gates OPTIMIZE)
  options: [], // best_4_options or generated options (GeometryObject[])
  shapesByType: {}, // { "H Shape": [GeometryObject], ... } for the explorer
  currentDesign: null,
  selectedOptionId: null,
  selectedPart: null, // { part, surface } from viewer pick
  selectedPartId: "building", // "building" | "wing_<index>" — manipulation target
  selectedPartLabel: "building", // human label for the selected part
  pendingTool: null, // armed manipulation tool awaiting a typed amount ('move'|'rotate'|'scale')
  activeTool: null, // 'move' | 'rotate' | 'scale' | 'push_pull'

  // optimization
  optimizationScore: null,
  optimizationResult: null, // full backend optimize response (algorithm, options, site_area)
  visibleOptionIds: new Set(), // eye-toggled options shown in viewer

  // compare
  compareIds: [],
  compareRows: [],
  compareSelection: [], // option_ids the user ticked for the comparison table
  comparisonOptions: [], // options fed into the comparison table (from backend data)

  // ---- Backend B (Team-04 Agent API) session-driven state ----
  // All fields below populate ONLY from backend B responses; empty until then.
  sessionId: null, // active /sessions/{id}
  agentAvailable: null, // null=unknown, true/false after a ping
  // explorer tree from GET /sessions/{id}/explorer
  explorerSite: null, // SiteInfo
  buildings: [], // BuildingInfo[] (each has wings[], placement_options[])
  selectedBuildingId: null,
  // decision graph from GET /sessions/{id}/decisions
  decisionGraph: { nodes: [], edges: [], head: null },
  // Real project timeline — every workflow action appends here (see recordDecision).
  decisionHistory: [],
  selectedFinalOption: null, // the option chosen for export
  // agent traces (derived live from the SSE stream + final state)
  plannerTrace: [], // planner decisions
  supervisorTrace: [], // supervisor decisions
  toolTrace: [], // tool calls fired this turn
  agentState: null, // last AgentState snapshot (placed_buildings, violations, …)
  errors: [], // [{ at, message }]
  loadingState: {}, // { sessions:bool, chat:bool, decisions:bool, explorer:bool }

  // map runtime handles (not serialized)
  map: null,

  // ---- scanning state machine (drives the center scan-line HUD) ----
  isCopilotThinking: false,
  isLocatingSite: false,
  isBoundaryActivating: false,
  isAnalyzingBoundary: false,
  isOptimizing: false,
};

// Combined scan flag — true while any processing phase is active.
export function isScanning(s = state) {
  return Boolean(
    s.isCopilotThinking ||
      s.isLocatingSite ||
      s.isBoundaryActivating ||
      s.isAnalyzingBoundary ||
      s.isOptimizing
  );
}

export function getState() {
  return state;
}

export function setState(patch) {
  Object.assign(state, typeof patch === "function" ? patch(state) : patch);
  emit();
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

let _emitting = false;
let _emitQueued = false;
function emit() {
  // Re-entrancy guard: if a listener calls setState() (which calls emit) while we're
  // already notifying listeners, don't recurse — just flag that another pass is needed
  // and run it once after the current one finishes. Prevents infinite render loops
  // (e.g. center.render → viewer → renderBuildings → setState → emit → …).
  if (_emitting) { _emitQueued = true; return; }
  _emitting = true;
  let passes = 0;
  try {
    do {
      _emitQueued = false;
      for (const fn of listeners) {
        try { fn(state); }
        catch (err) { console.error("[store] listener error", err); }
      }
      // Hard cap: a listener that keeps re-triggering setState can never hang the page.
      if (++passes > 5) {
        if (_emitQueued) console.warn("[store] emit re-entrancy capped — a listener keeps calling setState");
        break;
      }
    } while (_emitQueued);
  } finally {
    _emitting = false;
  }
}

// Convenience: append a chat message and re-render.
export function pushMessage(role, text, actions = [], meta = null) {
  // Keep the chat concise: shorten verbose/duplicated assistant text before it is
  // stored (detailed reports stay in the workspace panels). User text is untouched.
  const body = role === "assistant" ? shortenCopilotResponse(text) : text;
  // `meta` (optional) carries the AI reasoning trace for the "How I understood this"
  // panel — purely additive; messages without it render exactly as before.
  state.messages = [...state.messages, { role, text: body, actions, meta, ts: Date.now() }];
  state.actions = role === "assistant" ? actions : state.actions;
  emit();
}

export function setStatus(status) {
  state.status = status;
  emit();
}

// ---- Backend B helpers ----------------------------------------------------

// Record a backend error without throwing — surfaced in the UI, never swallowed.
export function pushError(message) {
  state.errors = [...state.errors, { at: Date.now(), message: String(message) }];
  emit();
}

// Toggle a named loading flag (e.g. setLoading("chat", true)).
export function setLoading(key, value) {
  state.loadingState = { ...state.loadingState, [key]: Boolean(value) };
  emit();
}

