// Shape Library view — STAGE 1 of the workflow. Shows the generated typology
// options (Rectangle / L / U / H / Courtyard / Linear Bar / Twin Block …) the
// user chooses FROM, before any optimization runs. Every footprint comes from the
// REAL backend /generate-options route (already scaled to fit the site). The user
// can toggle each shape's visibility in the 3D viewer, preview it, and SELECT one.
//
// Selecting a shape is the ONLY way forward to optimization — see selectShape()
// and the OPTIMIZE guard in core/workflow.js.

import { getState, setState } from "../core/store.js";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

function num(v, d = 2) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(d) : "—";
}

// Friendly typology name for the card subtitle.
function typeLabel(t) {
  const map = {
    I: "Linear Bar", L: "L Shape", U: "U Shape", H: "H Shape",
    T: "T Shape", X: "Cross", Y: "Y Shape", O: "Courtyard",
    rectangle: "Rectangle", bar: "Linear Bar", twin: "Twin Block",
  };
  if (!t) return "Shape";
  return map[t] || map[String(t).toUpperCase()] || `${t} Shape`;
}

async function toggleVisibility(shapeId) {
  const s = getState();
  const visible = new Set(s.visibleShapeIds || []);
  if (visible.has(shapeId)) visible.delete(shapeId);
  else visible.add(shapeId);
  setState({ visibleShapeIds: visible, selectedShapeId: shapeId });
  await previewInViewer([...visible]);
}

// Preview the toggled shapes in the 3D viewer (footprints only — no optimization).
// The plain viewer uses the backend's metric frame (the same frame the generated
// shape footprints are in), so the preview is always aligned to the site.
async function previewInViewer(visibleIds) {
  const s = getState();
  const shown = (s.shapeOptions || []).filter((o) => visibleIds.includes(o.option_id));
  try {
    const viewer = await import("./viewerView.js");
    viewer.renderShapePreview(shown);
  } catch {
    /* viewer mounts later */
  }
}

// Commit to a shape: promote it to the single placed building and advance to
// SHAPE_EDIT (manipulation). This is what unlocks OPTIMIZE.
async function selectShape(shapeId) {
  const s = getState();
  const opt = (s.shapeOptions || []).find((o) => o.option_id === shapeId);
  if (!opt) return;
  const { confirmShapeSelection } = await import("../copilotClient.js");
  await confirmShapeSelection(opt);
}

export function activate() {
  render();
}
export async function onAction() {
  render();
}

// Build a small SVG thumbnail of this shape's footprint inside the site boundary
// (and, when available, the nearby road context) so every card shows a visual
// preview, not just numbers. All polygons are in the backend metric frame.
function thumbnail(o, site, context) {
  const fp = (o.footprint || o.boundary || []).map((p) => [Number(p[0]), Number(p[1])]);
  const siteRing = (site?.boundary || []).map((p) => [Number(p[0]), Number(p[1])]);
  if (fp.length < 3) return `<div class="shape-thumb shape-thumb-empty">no preview</div>`;

  // Fit everything (site + footprint + a margin of context) into a 0..100 viewBox.
  const all = [...fp, ...siteRing];
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  let minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = Math.max(maxX - minX, maxY - minY) * 0.18 || 10;
  minX -= pad; maxX += pad; minY -= pad; maxY += pad;
  const w = maxX - minX || 1, h = maxY - minY || 1;
  const scale = 100 / Math.max(w, h);
  // y is north (+), SVG y grows downward → flip so north is up in the thumbnail.
  const tx = (p) => ((p[0] - minX) * scale).toFixed(1);
  const ty = (p) => ((maxY - p[1]) * scale).toFixed(1);
  const poly = (ring) => ring.map((p) => `${tx(p)},${ty(p)}`).join(" ");

  // Optional faint road context (frames differ slightly, so this is a backdrop hint).
  let roads = "";
  const roadLayers = context?.layers
    ? Object.values(context.layers).filter((L) => L.kind === "road")
    : [];
  for (const L of roadLayers) {
    for (const r of (L.roads || []).slice(0, 30)) {
      if (!r.path || r.path.length < 2) continue;
      const pts = r.path.filter((p) => p[0] >= minX && p[0] <= maxX && p[1] >= minY && p[1] <= maxY);
      if (pts.length < 2) continue;
      roads += `<polyline points="${poly(pts)}" fill="none" stroke="${L.style.color}" stroke-width="0.6" opacity="0.35"/>`;
    }
  }

  return `
    <svg class="shape-thumb" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
      ${roads}
      ${siteRing.length >= 3 ? `<polygon points="${poly(siteRing)}" fill="rgba(40,224,208,0.08)" stroke="#28e0d0" stroke-width="0.8" stroke-dasharray="2 1.5"/>` : ""}
      <polygon points="${poly(fp)}" fill="rgba(124,123,255,0.5)" stroke="#7cffe6" stroke-width="1.1"/>
    </svg>`;
}

function card(o, i, visible, selected, site, context) {
  const label = `Shape ${LETTERS[i] || i + 1}`;
  const sub = typeLabel(o.shape_type);
  const fits = o.validation_report?.fits_within_site !== false;
  const area = o.footprint_area != null ? `${Math.round(o.footprint_area)} m²` : "—";
  const cover = o.site_coverage != null ? `${Math.round(o.site_coverage * 100)}%` : "—";
  return `
    <div class="opt-card shape-card${selected ? " selected" : ""}${fits ? "" : " invalid"}" data-shape="${o.option_id}">
      <div class="opt-card-head">
        <span class="opt-rank">${label}</span>
        <span class="opt-score">${sub}</span>
        <button class="opt-eye" data-toggle="${o.option_id}" title="${visible ? "Hide" : "Show"} in viewer">${visible ? "👁️" : "🚫"}</button>
      </div>
      ${thumbnail(o, site, context)}
      <div class="opt-metrics">
        <div><label>Type</label><b>${o.shape_type ?? "—"}</b></div>
        <div><label>Footprint</label><b>${area}</b></div>
        <div><label>Coverage</label><b>${cover}</b></div>
        <div><label>Floors</label><b>${o.floors ?? "—"}</b></div>
        <div><label>Height</label><b>${o.height_m != null ? Math.round(o.height_m) + " m" : "—"}</b></div>
        <div><label>Fit</label><b>${fits ? "✓ fits" : "⚠ outside"}</b></div>
      </div>
      <button class="shape-select-btn" data-select="${o.option_id}">Select ${label}</button>
    </div>`;
}

function render() {
  const root = document.getElementById("shapes-scroll");
  if (!root) return;
  const s = getState();
  const opts = s.shapeOptions || [];
  if (!opts.length) {
    root.innerHTML = `<div class="center-empty"><div class="big">⬡</div><div>Tell me what you'd like to build and I'll generate shape options to choose from.</div></div>`;
    return;
  }
  const visibleSet = s.visibleShapeIds || new Set();
  const site = s.site;
  const context = s.context;
  root.innerHTML = `
    <div class="opt-header">
      <h2>Shape Library</h2>
      <p>${opts.length} massing options scaled to fit your site. Each card previews the footprint on the site; toggle 👁 to view a shape in 3D, then <b>Select</b> one to optimize.</p>
    </div>
    <div class="opt-grid">
      ${opts.map((o, i) => card(o, i, visibleSet.has(o.option_id), s.selectedShapeId === o.option_id, site, context)).join("")}
    </div>`;

  root.querySelectorAll(".opt-eye").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleVisibility(btn.dataset.toggle);
    });
  });
  root.querySelectorAll(".shape-select-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      selectShape(btn.dataset.select);
    });
  });
  root.querySelectorAll(".shape-card").forEach((c) => {
    c.addEventListener("click", () => {
      setState({ selectedShapeId: c.dataset.shape });
      previewInViewer([c.dataset.shape]);
    });
  });
}
