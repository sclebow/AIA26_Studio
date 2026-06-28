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
  analyzeContext, reportToMarkdown, designGuidance, CONTEXT_RADIUS_M,
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

// Derive the site centroid + boundary (lng/lat) the analyzer needs.
function resolveSite() {
  const s = getState();
  const boundary = s.boundary && s.boundary.length >= 3 ? s.boundary : null;
  let center = null;
  if (s.location && Number.isFinite(s.location.lat)) {
    center = { lng: s.location.lng, lat: s.location.lat };
  } else if (boundary) {
    const c = boundary.reduce((a, p) => [a[0] + p[0], a[1] + p[1]], [0, 0]);
    center = { lng: c[0] / boundary.length, lat: c[1] / boundary.length };
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

    setState({
      context: ctx,
      contextScores: ctx.scores,
      contextVisible,
      contextLoading: false,
    });
    setStatus("Urban context ready");

    // 3) render the 3D twin + overlays
    try {
      const { dispatchView } = await import("../panels/center.js");
      await dispatchView({ type: "context", payload: { action: "render_context" } });
    } catch (e) { console.error("[context] render dispatch", e); }

    // 4) AI Context Report into chat
    pushMessage("assistant", reportToMarkdown(ctx));

    // 5) context-aware follow-up question (guidance attached for shape gen)
    const guidance = designGuidance(ctx.scores);
    const guidanceLine = guidance.length
      ? "\n\nGiven the scores, I'd lean toward: " + guidance.join("; ") + "."
      : "";
    pushMessage(
      "assistant",
      "I've analyzed the surrounding urban context. Based on the site's accessibility, " +
      "amenities, transportation network, and context scores, what type of building " +
      "would you like me to generate?" + guidanceLine,
      [
        { label: "Generate Shapes", message: "generate options", primary: true },
        { label: "Office Tower", message: "generate a high-density office tower" },
        { label: "Mixed-Use", message: "generate a mixed-use development" },
        { label: "Residential", message: "generate a residential building" },
      ]
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
