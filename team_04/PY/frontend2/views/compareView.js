// Comparison table view. Builds a metric-by-option table from the stored options,
// highlighting the best value in each row. Driven by the orchestrator's "compare"
// intent (option_ids) or, if none given, compares all current options.

import { getState } from "../core/store.js";

// metric definitions: [label, accessor, higherIsBetter, formatter]
// All values come from the REAL backend option metrics (set by the optimizer /
// explorer projection) — no mock data.
// Metrics that actually DISTINGUISH placement options come first (score + the
// view metrics that drove ranking + position/rotation). Fixed-shape program
// metrics (FAR/footprint/height/floors) are the same for every option — they're
// shown after, clearly, so the table doesn't look "fake" when only placement varies.
// BUG 3 fix: surface ALL optimization metrics. The objective scores live in
// o.objective_scores (from the multi-objective engine). A metric that's truly
// absent shows N/A — never fabricated. Higher-is-better unless noted.
const NA = Symbol("N/A");
const METRICS = [
  ["Strategy", (o) => o.strategy_name || "—", true, (v) => v, { text: true }],
  ["Overall Score", (o) => num(o.score), true, (v) => v.toFixed(1)],
  ["Solar", (o) => obj(o, "solar"), true, fmt0],
  ["View", (o) => obj(o, "view") ?? (metric(o, "view_score") || num(o.view_score) || NA), true, fmt0],
  ["Noise", (o) => obj(o, "noise"), true, fmt0],
  ["Wind", (o) => obj(o, "wind"), true, fmt0],
  ["Density", (o) => obj(o, "density"), true, fmt0],
  ["Open Space", (o) => obj(o, "open_space"), true, fmt0],
  ["Access", (o) => obj(o, "road_access"), true, fmt0],
  ["Walkability", (o) => obj(o, "walkability"), true, fmt0],
  ["Privacy", (o) => obj(o, "privacy"), true, fmt0],
  ["Setback", (o) => obj(o, "setback"), true, fmt0],
  ["Structural", (o) => obj(o, "structural"), true, fmt0],
  ["Position", (o) => posKey(o), true, (v) => posLabel(v), { text: true }],
  ["Rotation", (o) => num(o.rotation_degrees), true, (v) => Math.round(v) + "°", { text: true }],
  ["FAR", (o) => obj(o, "density") != null ? (metric(o, "far") || num(o.far) || NA) : (num(o.far) || NA), true, (v) => v.toFixed(2)],
  ["Site coverage", (o) => num(o.site_coverage) || NA, false, (v) => (v * 100).toFixed(0) + "%"],
  ["Footprint", (o) => num(o.footprint_area) || NA, true, (v) => Math.round(v).toLocaleString() + " m²"],
  ["Height", (o) => num(o.height) || num(o.height_m) || NA, true, (v) => Math.round(v) + " m"],
  ["Floors", (o) => num(o.floors) || NA, true, (v) => String(Math.round(v))],
];

function fmt0(v) { return String(Math.round(v)); }
function num(v) { const n = Number(v); return Number.isFinite(n) ? n : 0; }
// Read an objective score from the engine's per-option output. Returns NA when the
// metric was not produced (e.g. excluded as unavailable) — never a fake value.
function obj(o, key) {
  const os = o.objective_scores || o.objective_breakdown || {};
  const v = os[key] ?? o.headline_metrics?.[key];
  return (v == null || Number.isNaN(Number(v))) ? NA : Number(v);
}
function metric(o, key) { return num(o?.constraint_report?.metrics?.[key]); }
function setbackVal(o) { return o?.constraint_report?.metrics?.setback_ok === false ? 0 : 1; }
function openSpace(o) {
  const cover = o?.constraint_report?.metrics?.site_coverage ?? o?.site_coverage;
  return Number.isFinite(Number(cover)) ? Math.max(0, 1 - Number(cover)) : 0;
}
// Position encoded as a sortable number (for "best" highlight it's neutral) but
// rendered as the option centroid so each option's distinct placement is visible.
function posKey(o) {
  const b = o.boundary || o.footprint || [];
  if (!b.length) return 0;
  const cx = b.reduce((s, p) => s + Number(p[0]), 0) / b.length;
  const cy = b.reduce((s, p) => s + Number(p[1]), 0) / b.length;
  return Math.round(cx) * 1000 + Math.round(cy); // pack for storage
}
function posLabel(v) {
  const cx = Math.floor(v / 1000);
  const cy = v - cx * 1000;
  return `${cx}, ${cy} m`;
}

let pendingIds = null;

export function activate() {
  render(pendingIds);
}

export async function onAction(payload) {
  if (payload.action === "compare") {
    pendingIds = (payload.option_ids && payload.option_ids.length) ? payload.option_ids : null;
    render(pendingIds);
  }
}

function resolveOptions(ids) {
  // Prefer the explicit comparison set (carries the optimization strategy + metrics),
  // fall back to the live options. Both come from the optimizer via optionToViewer.
  const all = (getState().comparisonOptions?.length ? getState().comparisonOptions : getState().options) || [];
  if (!ids || !ids.length) return all;
  // ids like "option_1" map to positional index; also match real option_id
  const picked = [];
  ids.forEach((id) => {
    const m = /option[_ ]?(\d+)/i.exec(id);
    if (m) {
      const idx = Number(m[1]) - 1;
      if (all[idx]) { picked.push(all[idx]); return; }
    }
    const direct = all.find((o) => o.option_id === id);
    if (direct) picked.push(direct);
  });
  return picked.length ? picked : all;
}

function render(ids) {
  const root = document.getElementById("compare-scroll");
  if (!root) return;
  root.dataset.ready = "1";
  let opts = resolveOptions(ids);
  if (!opts.length) {
    root.innerHTML = `<div class="center-empty"><div class="big">📊</div><div>Generate or optimize options first, then compare.</div></div>`;
    return;
  }
  // Drop baseline ORIGINAL columns that carry no scores (score null / empty objective
  // scores) — they showed as confusing "0.0 / N/A" columns. Only do this when there ARE
  // scored optimized variants to compare; otherwise keep whatever we have so the table is
  // never empty. The originals remain browsable in Saved Shapes.
  const _hasScore = (o) => Number.isFinite(Number(o?.score))
    || (o?.objective_scores && Object.keys(o.objective_scores).length > 0);
  const scored = opts.filter(_hasScore);
  if (scored.length >= 2) opts = scored;

  const isNum = (v) => v !== NA && Number.isFinite(Number(v));
  // Best/worst value per metric over the AVAILABLE (numeric, non-NA) values only.
  const best = METRICS.map(([, get, higher, , opt]) => {
    if (opt && opt.text) return null;
    const vals = opts.map(get).filter(isNum);
    if (!vals.length) return null;
    return higher ? Math.max(...vals) : Math.min(...vals);
  });
  const worst = METRICS.map(([, get, higher, , opt]) => {
    if (opt && opt.text) return null;
    const vals = opts.map(get).filter(isNum);
    if (!vals.length) return null;
    return higher ? Math.min(...vals) : Math.max(...vals);
  });

  // Header: name each column by its REAL option id (shape_001A) so the user can tell
  // which parent shape + variant it is — "Option A/B/C" was ambiguous. Subtitle shows
  // whether it's the original or which variant of which parent.
  const head = `<tr><th>Metric</th>${opts.map((o) => {
    const id = o.option_id || o.label || "";
    let sub;
    if (o.is_baseline) {
      sub = "original";
    } else if (o.source_shape_option_id) {
      // e.g. shape_001A → "variant A of shape_001"
      const tag = o.variant_tag || (id.match(/([A-Z])$/) || [])[1] || "";
      sub = `variant ${tag} of ${o.source_shape_option_id}`;
    } else {
      sub = (o.shape_type || "").replace(/_/g, " ");
    }
    return `<th>${id}<br/><span style="font-weight:400;color:var(--text-dim);font-size:11px">${sub}</span></th>`;
  }).join("")}</tr>`;
  // Hide metric rows that are N/A for EVERY column — a wall of N/A (View/Noise/Access the
  // optimizer doesn't compute) just adds noise. Always keep the structural rows (Strategy,
  // Overall Score) and any row with at least one real value. Honest: a hidden row = a
  // metric the backend produced for nobody, not a fabricated one.
  const ALWAYS = new Set(["Strategy", "Overall Score"]);
  const rows = METRICS.map(([label, get, , fmt, opt], r) => {
    const isText = opt && opt.text;
    const vals = opts.map(get);
    const allNA = vals.every((v) => v === NA);
    if (allNA && !ALWAYS.has(label)) return "";   // drop the row entirely
    const cells = vals.map((v) => {
      if (v === NA) {
        // BUG 3: never fabricate — show N/A with an explanatory title.
        return `<td title="Metric unavailable from optimization backend." style="color:var(--text-dim);opacity:.6">N/A</td>`;
      }
      const isBest = !isText && best[r] !== null && Math.abs(v - best[r]) < 1e-9 && opts.length > 1 && best[r] !== worst[r];
      const isWorst = !isText && worst[r] !== null && Math.abs(v - worst[r]) < 1e-9 && opts.length > 1 && best[r] !== worst[r];
      const cls = isBest ? "best" : (isWorst ? "worst" : "");
      return `<td class="${cls}">${fmt(v)}</td>`;
    }).join("");
    return `<tr><td>${label}</td>${cells}</tr>`;
  }).join("");

  root.innerHTML = `
    <h2 style="margin:0 0 14px;color:var(--text-bright);font-size:18px;">Option Comparison</h2>
    <p style="margin:0 0 16px;color:var(--text-dim);font-size:13px;">Each option is an optimization strategy. <span style="color:var(--good)">Best</span> and <span style="color:var(--warn)">worst</span> value per metric are highlighted. <b>N/A</b> = metric unavailable from the optimization backend (no fabricated scores).</p>
    <table class="compare-table"><thead>${head}</thead><tbody>${rows}</tbody></table>`;
}
