// Left-panel workflow stepper — the mission-control progress rail.
// Shows the six workflow stages and reflects the live stage from the store.
// Purely a status display; it does not change workflow logic.

import { getState, subscribe } from "../core/store.js";
import { STAGES } from "../core/stages.js";
import { canEnter, enterStage, tryAdvance } from "../core/workflow.js";

// Map a stepper step key to a workflow stage.
const STEP_STAGE = {
  SITE: STAGES.SITE,
  BOUNDARY: STAGES.BOUNDARY,
  SHAPE: STAGES.SHAPES,
  OPTIMIZE: STAGES.OPTIMIZE,
  COMPARE: STAGES.COMPARE,
  EXPORT: STAGES.EXPORT,
};

// Stepper clicks go through the workflow controller's guards, so a later stage
// can't be opened until its prerequisites are met.
async function goToStep(stepKey) {
  const stage = STEP_STAGE[stepKey];
  if (!stage) return;
  // Optimization clicked with a building but no options yet → run the optimizer.
  if (stage === STAGES.OPTIMIZE && canEnter(STAGES.OPTIMIZE) && !getState().optimizationResult) {
    enterStage(STAGES.OPTIMIZE, { announce: false });
    const { optimizeBuilding } = await import("../agentClient.js");
    await optimizeBuilding();
    return;
  }
  tryAdvance(stage); // guarded: enters only if canEnter, else explains why
}

// The six visible workflow steps (Shape == SHAPES/SHAPE_EDIT, etc.)
const STEPS = [
  { key: "SITE", label: "Site", icon: site() },
  { key: "BOUNDARY", label: "Boundary", icon: boundary() },
  { key: "SHAPE", label: "Shape", icon: shape() },
  { key: "OPTIMIZE", label: "Optimization", icon: optimize() },
  { key: "COMPARE", label: "Comparison", icon: compare() },
  { key: "EXPORT", label: "Export", icon: exportIcon() },
];

// Map any backend stage to one of the six steps + an ordinal for progress.
const STAGE_TO_STEP = {
  SITE: 0, BOUNDARY: 1, SHAPES: 2, SHAPE_EDIT: 2,
  OPTIMIZE: 3, COMPARE: 4, EXPORT: 5, EVOLUTION: 5, END: 5,
};

function currentStepIndex() {
  const stage = getState().stage || "SITE";
  return STAGE_TO_STEP[stage] ?? 0;
}

function render() {
  // Render into the floating bottom dock (horizontal). Falls back to the legacy
  // left-panel host id if present, so this is safe regardless of mount point.
  const host = document.getElementById("bottom-dock") || document.getElementById("workflow-stepper");
  if (!host) return;
  const active = currentStepIndex();
  host.className = "dock-glass";
  host.innerHTML = `
    <div class="dock-rail">
      ${STEPS.map((s, i) => {
        const state = i < active ? "done" : i === active ? "active" : "pending";
        // A step is locked (not yet reachable) if its stage's entry guard fails.
        const locked = !canEnter(STEP_STAGE[s.key]);
        return `
        <div class="dock-step ${state}${locked ? " locked" : ""}" data-step="${s.key}" data-locked="${locked}" title="${locked ? s.label + " (complete earlier steps first)" : s.label}" role="button" tabindex="0">
          <span class="dock-ico">${s.icon}</span>
          <span class="dock-label">${s.label}</span>
          ${i < STEPS.length - 1 ? '<span class="dock-connector"></span>' : ""}
        </div>`;
      }).join("")}
    </div>`;

  host.querySelectorAll(".dock-step").forEach((el) => {
    el.style.cursor = el.dataset.locked === "true" ? "not-allowed" : "pointer";
    el.style.opacity = el.dataset.locked === "true" ? "0.45" : "";
    el.addEventListener("click", () => goToStep(el.dataset.step));
  });
}

export function initStepper() {
  render();
  subscribe(render);
}

// ---- inline SVG icons (modern, lightweight) ----
function svg(inner) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
}
function site() { return svg('<path d="M12 21s-6-5.3-6-10a6 6 0 1 1 12 0c0 4.7-6 10-6 10Z"/><circle cx="12" cy="11" r="2.2"/>'); }
function boundary() { return svg('<path d="M4 7l8-3 8 3-8 3-8-3Z"/><path d="M4 7v10l8 3 8-3V7"/>'); }
function shape() { return svg('<path d="M3 9.5 12 4l9 5.5v5L12 20l-9-5.5v-5Z"/><path d="M12 4v16"/><path d="M3 9.5 12 15l9-5.5"/>'); }
function optimize() { return svg('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>'); }
function compare() { return svg('<rect x="3" y="5" width="7" height="14" rx="1.5"/><rect x="14" y="5" width="7" height="14" rx="1.5"/>'); }
function exportIcon() { return svg('<path d="M12 15V3"/><path d="m7 8 5-5 5 5"/><path d="M5 17v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2"/>'); }
