// Optimization view — rich cards for the top-ranked options returned by the REAL
// backend view-optimizer (NSGA-II). Every value comes from the backend option
// metrics (score, objective breakdown, view score, setback, FAR, coverage,
// height, floors, reasoning). Eye toggles show/hide each option in the 3D viewer.

import { getState, setState } from "../core/store.js";

function num(v, d = 2) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(d) : "—";
}
function metric(o, key) {
  return o?.constraint_report?.metrics?.[key];
}

async function toggleVisibility(optionId) {
  const s = getState();
  const visible = new Set(s.visibleOptionIds || []);
  if (visible.has(optionId)) visible.delete(optionId);
  else visible.add(optionId);
  setState({ visibleOptionIds: visible, centerView: "viewer", selectedOptionId: optionId });
  try {
    const viewer = await import("./viewerView.js");
    viewer.activate();
    viewer.setVisibleOptions([...visible]);
  } catch {
    /* viewer not mounted */
  }
}

export function activate() {
  render();
}

export async function onAction() {
  render();
}

function objectiveBars(breakdown) {
  const entries = Object.entries(breakdown || {});
  if (!entries.length) return "";
  return `<div class="opt-objectives">${entries
    .map(([name, val]) => {
      const pct = Math.max(0, Math.min(100, Number(val) * 100));
      return `<div class="opt-obj-row">
        <span class="opt-obj-name">${name.replace(/_/g, " ")}</span>
        <span class="opt-obj-bar"><i style="width:${pct}%"></i></span>
        <span class="opt-obj-val">${num(val)}</span>
      </div>`;
    })
    .join("")}</div>`;
}

function card(o, i, visible, selected) {
  const m = o.constraint_report?.metrics || {};
  const fits = o.constraint_report?.passed !== false;
  const far = m.far != null ? num(m.far) : "—";
  const cover = m.site_coverage != null ? `${Math.round(m.site_coverage * 100)}%` : "—";
  const setback = m.setback_ok === false ? "⚠ violation" : "✓ ok";
  // Multi-objective strategy framing: lead with the strategy NAME + the headline
  // metrics the engine picked for this priority + the 'why selected' reason.
  const stratName = o.strategy_name || "Option";
  const stratLetter = String.fromCharCode(65 + i); // A, B, C…
  const headline = o.headline_metrics || {};
  const headlineRows = Object.entries(headline).slice(0, 3)
    .map(([k, v]) => `<div><label>${prettyMetric(k)}</label><b>${fmtMetric(v)}</b></div>`)
    .join("");
  const reason = o.reason || o.reasoning || "";
  return `
    <div class="opt-card${selected ? " selected" : ""}${fits ? "" : " invalid"}" data-opt="${o.option_id}">
      <div class="opt-card-head">
        <span class="opt-rank">${o.strategy_name ? `Option ${stratLetter}` : `#${o.rank || i + 1}`}</span>
        <span class="opt-score">${num(o.score)}</span>
        <button class="opt-eye" data-toggle="${o.option_id}" title="${visible ? "Hide" : "Show"} in viewer">${visible ? "👁️" : "🚫"}</button>
      </div>
      ${o.strategy_name ? `<div class="opt-strategy">${stratName}</div>` : ""}
      <div class="opt-metrics">
        ${headlineRows || `
          <div><label>View</label><b>${num(metric(o, "view_score") ?? metric(o, "unblocked_view_score"))}</b></div>
          <div><label>FAR</label><b>${far}</b></div>
          <div><label>Coverage</label><b>${cover}</b></div>`}
        <div><label>Height</label><b>${m.height_m != null ? Math.round(m.height_m) + " m" : "—"}</b></div>
        <div><label>Floors</label><b>${m.floors ?? "—"}</b></div>
        <div><label>Setback</label><b>${setback}</b></div>
      </div>
      ${objectiveBars(o.objective_breakdown || o.objective_scores)}
      ${reason ? `<div class="opt-reason"><b>Reason:</b> ${reason}</div>` : ""}
    </div>`;
}

function prettyMetric(k) {
  return String(k)
    .replace(/_pct$/, " %").replace(/_m$/, " (m)").replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
function fmtMetric(v) {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

function render() {
  const root = document.getElementById("optimize-scroll");
  if (!root) return;
  const s = getState();
  const opts = s.options || [];
  if (!opts.length) {
    root.innerHTML = `<div class="center-empty"><div class="big">⚙️</div><div>Run optimization to see the top-ranked options here.</div></div>`;
    return;
  }
  const visibleSet = s.visibleOptionIds || new Set();
  const res = s.optimizationResult || {};
  root.innerHTML = `
    <div class="opt-header">
      <h2>Optimization — Multi-Objective Pareto Analysis</h2>
      <p>${opts.length} distinct options across Solar · View · Noise · Open Space · Density · Wind · Balanced · Landmark. Toggle 👁 to show/hide in the 3D viewer.</p>
    </div>
    <div class="opt-grid">
      ${opts.map((o, i) => card(o, i, visibleSet.has(o.option_id), s.selectedOptionId === o.option_id)).join("")}
    </div>`;

  root.querySelectorAll(".opt-eye").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleVisibility(btn.dataset.toggle);
    });
  });
  root.querySelectorAll(".opt-card").forEach((c) => {
    c.addEventListener("click", () => setState({ selectedOptionId: c.dataset.opt }));
  });
}
