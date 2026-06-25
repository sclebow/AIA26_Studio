// Center panel: routes between map / viewer / compare / evolution views based on
// store.centerView. Each view owns its own DOM subtree; we just toggle visibility
// so heavy contexts (MapLibre, Three.js) are created once and kept alive.

import { getState, subscribe } from "../core/store.js";

const VIEWS = ["map", "viewer", "context", "shapes", "savedshapes", "optimize", "compare", "evolution", "decision"];
let mounted = false;
let lastView = null;
let currentView = null; // the view currently shown (drives morph direction)

// view modules are lazily imported to keep slice boundaries clean
const viewModules = {};
async function loadView(name) {
  if (viewModules[name]) return viewModules[name];
  let mod;
  if (name === "map") mod = await import("../views/mapView.js");
  else if (name === "viewer") mod = await import("../views/viewerView.js");
  else if (name === "context") mod = await import("../views/contextView.js");
  else if (name === "shapes") mod = await import("../views/shapesView.js");
  else if (name === "savedshapes") mod = await import("../views/savedShapesView.js");
  else if (name === "optimize") mod = await import("../views/optimizeView.js");
  else if (name === "compare") mod = await import("../views/compareView.js");
  else if (name === "evolution") mod = await import("../views/evolutionView.js");
  else if (name === "decision") mod = await import("../views/decisionGraphView.js");
  viewModules[name] = mod;
  return mod;
}

function ensureMounted() {
  if (mounted) return;
  const root = document.getElementById("center");
  root.innerHTML = `
    <div id="view-map" class="center-view hidden"></div>
    <div id="view-viewer" class="center-view hidden"></div>
    <div id="view-context" class="center-view hidden"></div>
    <div id="view-shapes" class="center-view hidden"><div class="view-scroll" id="shapes-scroll"></div></div>
    <div id="view-savedshapes" class="center-view hidden"><div class="view-scroll" id="savedshapes-scroll"></div></div>
    <div id="view-optimize" class="center-view hidden"><div class="view-scroll" id="optimize-scroll"></div></div>
    <div id="view-compare" class="center-view hidden"><div class="view-scroll" id="compare-scroll"></div></div>
    <div id="view-evolution" class="center-view hidden"><div class="view-scroll" id="evolution-scroll"></div></div>
    <div id="view-decision" class="center-view hidden"><div class="view-scroll" id="decision-scroll"></div></div>
    <div id="center-processing" class="hidden">
      <div class="proc-scanner"></div>
      <div class="proc-label">PROCESSING<span>·</span><span>·</span><span>·</span></div>
    </div>
    <div id="morph-overlay" class="hidden">
      <div class="morph-sweep"></div>
      <div class="morph-grid"></div>
      <div class="morph-particles">${Array.from({ length: 14 }).map(() => "<i></i>").join("")}</div>
    </div>
    <div id="kpi-cards" class="hidden"></div>`;
  mounted = true;
  subscribe(renderKpis);
  renderKpis();
}

// Floating glass KPI cards over the stage — live metrics that appear as the
// workflow produces data. Read-only display; no workflow change.
function renderKpis() {
  const host = document.getElementById("kpi-cards");
  if (!host) return;
  const s = getState();
  const view = s.centerView;
  const cards = [];

  const area = s.site?.site_area || (s.boundarySaved ? null : null);
  if (area) cards.push({ label: "Site Area", value: `${Math.round(area).toLocaleString()}`, unit: "m²", icon: "▦" });

  // Context score KPIs are rendered INSIDE the context view's own HTML overlay
  // (views/contextView.js → #ctx-scores), so the floating KPI dock stays hidden on
  // the context view to avoid duplicate score cards.
  if (view === "context") { host.classList.add("hidden"); return; }

  if ((view === "viewer" || view === "compare") && s.options?.length) {
    cards.push({ label: "Options", value: String(s.options.length), unit: "", icon: "◈" });
    const top = Math.max(...s.options.map((o) => Number(o.score) || 0));
    if (Number.isFinite(top) && top > 0) cards.push({ label: "Top Score", value: top.toFixed(2), unit: "", icon: "★", glow: true });
    const sel = s.options.find((o) => o.option_id === s.selectedOptionId) || s.options[0];
    const far = sel?.constraint_report?.metrics?.far;
    if (Number.isFinite(Number(far))) cards.push({ label: "FAR", value: Number(far).toFixed(2), unit: "", icon: "⬚" });
  }

  // only show KPIs on the spatial stages (map/viewer), not tables
  const show = cards.length && (view === "map" || view === "viewer");
  host.classList.toggle("hidden", !show);
  if (!show) return;
  host.innerHTML = cards.map((c, i) => `
    <div class="kpi-card${c.glow ? " glow" : ""}" style="animation-delay:${i * 70}ms">
      <span class="kpi-ico">${c.icon}</span>
      <div class="kpi-body">
        <span class="kpi-value">${c.value}<small>${c.unit}</small></span>
        <span class="kpi-label">${c.label}</span>
      </div>
    </div>`).join("");
}

// Apply the active-view toggle. When the view actually changes, play a futuristic
// morph: blur/scale/fade the outgoing view, run a holographic sweep + particles,
// then glow-reveal the incoming one. Heavy WebGL/Map DOM is never destroyed — we
// only animate via CSS classes, so live contexts survive the transition.
let transitioning = false;
function applyViewToggle(view) {
  const changed = view !== currentView;
  const outgoing = currentView ? document.getElementById(`view-${currentView}`) : null;

  if (!changed || !outgoing || transitioning) {
    for (const v of VIEWS) {
      const el = document.getElementById(`view-${v}`);
      if (el) el.classList.toggle("hidden", v !== view);
    }
    currentView = view;
    return;
  }

  transitioning = true;
  const incoming = document.getElementById(`view-${view}`);
  const overlay = document.getElementById("morph-overlay");

  // 1) animate the outgoing view out
  outgoing.classList.add("view-morph-out");
  if (overlay) { overlay.classList.remove("hidden"); overlay.classList.add("playing"); }

  // 2) at the midpoint, swap visibility and reveal the incoming view
  setTimeout(() => {
    outgoing.classList.add("hidden");
    outgoing.classList.remove("view-morph-out");
    for (const v of VIEWS) {
      if (v === view) continue;
      const el = document.getElementById(`view-${v}`);
      if (el) el.classList.add("hidden");
    }
    if (incoming) {
      incoming.classList.remove("hidden");
      incoming.classList.add("view-morph-in");
      // notify the incoming view it became visible (map/viewer need a resize)
      const mod = viewModules[view];
      if (mod && typeof mod.activate === "function") {
        try { mod.activate(); } catch (e) { /* noop */ }
      }
      incoming.addEventListener("animationend", function done() {
        incoming.classList.remove("view-morph-in");
        incoming.removeEventListener("animationend", done);
      });
    }
    currentView = view;
  }, 260);

  // 3) clean up the overlay after the full sweep
  setTimeout(() => {
    if (overlay) { overlay.classList.add("hidden"); overlay.classList.remove("playing"); }
    transitioning = false;
  }, 720);
}

async function render() {
  ensureMounted();
  const view = getState().centerView || "map";
  // ensure the module is loaded before the morph swaps to it (so activate exists)
  try {
    await loadView(view);
  } catch (err) {
    console.error("[center] view load failed", view, err);
  }
  applyViewToggle(view);
  lastView = view;
  // for same-view refreshes, applyViewToggle already re-activated; for changed
  // views the morph re-activates at its midpoint.
  if (view === currentView) {
    const mod = viewModules[view];
    if (mod && typeof mod.activate === "function") {
      try { mod.activate(); } catch (e) { /* noop */ }
    }
  }
}

export function initCenter() {
  ensureMounted();
  render();
  subscribe(render);
}

// Forward a view payload from the orchestrator to the relevant view module.
// Switches the center view first, then calls that module's onAction(payload).
export async function dispatchView(view) {
  if (!view || !view.type) return;
  const { setState } = await import("../core/store.js");
  setState({ centerView: view.type });
  ensureMounted();
  let mod;
  try {
    mod = await loadView(view.type);
  } catch (err) {
    console.error("[center] dispatchView load failed", view, err);
  }
  applyViewToggle(view.type);
  try {
    // onAction renders the payload into the (now visible / morphing-in) view.
    if (mod && typeof mod.onAction === "function" && view.payload) {
      await mod.onAction(view.payload);
    }
  } catch (err) {
    console.error("[center] dispatchView action failed", view, err);
  }
}
