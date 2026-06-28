// Orchestrates the Urban Context Analysis stage on the client side.
//
// Triggered automatically once the site boundary is confirmed (see mapView's
// `boundary_saved` handler). It:
//   1. advances the workflow to the CONTEXT stage and switches to the 3D view
//   2. fetches + classifies the 2 km OSM context via core/overpass.js
//   3. stores layers, edges, scores and the report
//   4. posts the AI Context Report into the Copilot chat
//   5. asks the user what to build next, carrying context-aware guidance forward
//
// All of this is self-contained in frontend2 — no backend changes required.

import { getState, setState, pushMessage, setStatus, subscribe } from "./store.js";
import { STAGES } from "./stages.js";
import {
  analyzeContext, designGuidance, CONTEXT_RADIUS_M,
} from "./overpass.js";

let running = false;
let watchInstalled = false;
let started = false; // analysis has been kicked off for this session's boundary

// Install a one-time guard: whenever the boundary becomes confirmed, ensure the
// context analysis runs exactly once. This covers every save path (backend-driven
// or local) without each having to call us explicitly.
export function watchBoundary() {
  if (watchInstalled) return;
  watchInstalled = true;
  subscribe((s) => {
    if (s.boundarySaved && !started && !s.context && !s.contextLoading) {
      started = true;
      runContextAnalysis();
    }
  });
}

// Derive the projection origin + boundary (lng/lat) the analyzer needs.
// IMPORTANT: use the BOUNDARY CENTROID as the projection origin (not the geocoded
// location pin). The viewer's building geometry is projected about the boundary
// centroid (see projectRingToMeters), so using the same origin here makes the
// context twin's metric frame COINCIDE with the building frame — letting context
// and building line up. (Using s.location offset the two frames when the user drew
// the boundary away from the pin.)
function resolveSite() {
  const s = getState();
  const boundary = s.boundary && s.boundary.length >= 3 ? s.boundary : null;
  let center = null;
  if (boundary) {
    const c = boundary.reduce((a, p) => [a[0] + p[0], a[1] + p[1]], [0, 0]);
    center = { lng: c[0] / boundary.length, lat: c[1] / boundary.length };
  } else if (s.location && Number.isFinite(s.location.lat)) {
    center = { lng: s.location.lng, lat: s.location.lat };
  }
  if (!center) return null;
  return { center, boundary: boundary || [] };
}

export async function runContextAnalysis() {
  if (running || getState().context) return;
  started = true;
  const site = resolveSite();
  if (!site) {
    console.warn("[context] no site/boundary available; skipping analysis");
    return;
  }
  running = true;

  // 1) advance stage + show the digital-twin view in its loading state
  setState({ stage: STAGES.CONTEXT, centerView: "context", contextLoading: true, contextError: null });
  setStatus("Analysing urban context…");

  try {
    const { dispatchView } = await import("../panels/center.js");
    await dispatchView({ type: "context", payload: { action: "context_loading" } });
  } catch (e) { /* view may not be mounted yet; fine */ }

  pushMessage(
    "assistant",
    `Site boundary confirmed. Generating a **${(CONTEXT_RADIUS_M / 1000).toFixed(0)} km urban context** ` +
    "from OpenStreetMap — roads, transit, amenities, parks and surrounding buildings…"
  );

  try {
    const ctx = await analyzeContext(site, { radius: CONTEXT_RADIUS_M });

    // 2) default every layer to visible
    const contextVisible = {};
    for (const id of Object.keys(ctx.layers)) contextVisible[id] = true;

    // edge_metadata: the SINGLE canonical store of edge names. All UI reads this
    // (or ctx.edges, which carries the same fields). Nothing recomputes direction.
    const edge_metadata = (ctx.edges || []).map((e) => ({
      edge_id: e.edge_id, label: e.label, display_name: e.display_name,
      midpoint: e.midpoint, angle: e.angle,
    }));
    ctx.edge_metadata = edge_metadata;
    // eslint-disable-next-line no-console
    console.log("[edge_metadata] stored once:", edge_metadata.map((e) => e.display_name).join(", "));

    setState({
      context: ctx,
      contextScores: ctx.scores,
      contextVisible,
      contextLoading: false,
    });
    setStatus("Urban context ready");

    // PERSIST the context to the backend so shape generation / manipulation can use
    // it (edges, edge_context, scores, selected edge). The UI used to only SHOW
    // context — now it becomes usable design intelligence.
    try {
      const { api } = await import("./api.js");
      const sid = getState().sessionId;
      if (sid) {
        await api.agent.storeContext(sid, {
          edges: ctx.edges, edge_metadata: ctx.edge_metadata, scores: ctx.scores,
          layers: ctx.layers, radius: ctx.radius, generatedAt: ctx.generatedAt,
          selectedEdge: getState().selectedEdge,
          // Neighbouring OSM buildings → Density compares proposed massing vs the local
          // height band; Privacy measures distance to the nearest neighbour (overlooking).
          // Send height + a centroid (small payload; full footprints for 400 buildings
          // would bloat the request). Centroid is enough for distance-based privacy.
          buildings: (ctx.buildings || []).map((b) => {
            const fp = b.footprint || [];
            let cx = null, cy = null;
            if (fp.length) {
              cx = fp.reduce((s, p) => s + p[0], 0) / fp.length;
              cy = fp.reduce((s, p) => s + p[1], 0) / fp.length;
            }
            return { height: b.height, cx, cy };
          }),
        });
        // eslint-disable-next-line no-console
        console.log("[context] stored to backend:", (ctx.edges || []).length, "edges");
      }
    } catch (e) { console.warn("[context] backend store failed (non-fatal):", e?.message); }

    // 3) render the 3D twin + overlays
    try {
      const { dispatchView } = await import("../panels/center.js");
      await dispatchView({ type: "context", payload: { action: "render_context" } });
    } catch (e) { console.error("[context] render dispatch", e); }

    // 4) Concise chat line — the FULL report is rendered in the workspace panel,
    //    so we don't repeat it in chat (keeps the assistant terse).
    pushMessage(
      "assistant",
      "Context analysis complete. Key scores and the edge report are shown in the workspace."
    );

    // 5) One clear next-step question.
    pushMessage(
      "assistant",
      "What would you like to build? e.g. *\"a 6-floor commercial building\"* or *\"residential apartments\"*."
    );
  } catch (err) {
    console.error("[context] analysis failed", err);
    setState({ contextLoading: false, contextError: err.message || "context failed" });
    setStatus("Context analysis failed");
    pushMessage("assistant", `⚠️ Urban context analysis failed: ${err.message || err}. You can continue and generate shapes anyway.`);
  } finally {
    running = false;
  }
}

// A compact, machine-friendly summary of context scores + guidance that the
// shape-generation / optimization requests can carry to the backend so designs
// respond to the city, not just the site. Safe to call before context exists.
export function contextPayload() {
  const s = getState();
  if (!s.context || !s.contextScores) return null;
  return {
    scores: s.contextScores,
    guidance: designGuidance(s.contextScores),
    radius_m: s.context.radius,
    edge_intelligence: (s.context.edges || []).map((e) => ({
      edge: e.id, direction: e.direction, nearest: e.nearest,
    })),
  };
}
