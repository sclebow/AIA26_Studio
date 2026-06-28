// Saved Shapes GALLERY — center-panel view that shows each saved manipulated shape
// as a CARD (footprint thumbnail + Type / Footprint / Coverage / Floors / Height /
// Fit), styled like the Shapes view the user referenced. Difference from Shapes:
//   • you can TICK MANY shapes (checkbox) to optimize them together, and
//   • "Preview" loads one in the 3D viewer, "Optimize N selected" runs the optimizer.
// Data comes from the enriched /design-options list (boundary + metrics included).

import { getState, setState } from "../core/store.js";
import { api } from "../core/api.js";

// Run optimization on the selected saved shapes — SELF-CONTAINED here (no dynamic
// import of explorer.js, which was failing because the loader appends a "?v=" version
// to the import path and the gallery sometimes resolved a different/stale copy whose
// export wasn't found → the "Optimize selected" button did nothing).
async function runOptimizeSelected(optionIds) {
  const { sessionId } = getState();
  if (!sessionId || !optionIds?.length) return;
  setState({ optimizationResult: null });
  let res = null;
  try {
    res = await api.agent.optimizeAllSavedShapes(sessionId, optionIds);
  } catch (e) {
    console.error("[saved-shapes] optimize failed", e);
    return;
  }
  const opts = res?.optimized_options || [];
  if (!opts.length) return;
  const baselineOpts = (res.source_shapes || []).map((b) => ({
    option_id: b.shape_option_id, label: b.shape_option_id + " (original)",
    shape_type: b.shape_type, is_baseline: true, source_shape_option_id: b.shape_option_id,
    score: b.scores?.total, objective_scores: b.scores,
  }));
  const variantOpts = opts.map((o) => ({
    option_id: o.optimized_option_id, label: o.optimized_option_id, shape_type: o.shape_type,
    boundary: o.geometry?.boundary || [], footprint: o.geometry?.boundary || [],
    floors: o.geometry?.floors, score: o.scores?.total, holes: o.geometry?.holes || [],
    floor_plates: o.geometry?.floor_plates || [], rotation_degrees: o.placement?.rotation_degrees,
    source_shape_option_id: o.source_shape_option_id, variant_tag: o.variant_tag,
    objective_scores: o.scores, validation_report: o.validation_report, is_optimized: true,
  }));
  const all = [...baselineOpts, ...variantOpts];
  setState({
    options: all, comparisonOptions: all, optimizationResult: res,
    compareSelection: all.map((o) => o.option_id),
    visibleOptionIds: new Set(variantOpts.map((o) => o.option_id)),
    savedOptimized: variantOpts, centerView: "compare",
  });
  try {
    const { dispatchView } = await import("../panels/center.js");
    await dispatchView({ type: "compare", payload: { action: "compare", option_ids: all.map((o) => o.option_id) } });
  } catch (e) { console.error("[saved-shapes] show compare failed", e); }
}

// Preview one saved shape in 3D — self-contained (no explorer import).
async function runPreview(optionId) {
  const { sessionId } = getState();
  if (!sessionId || !optionId) return;
  let resp = null;
  try { resp = await api.agent.selectDesignOption(sessionId, optionId); }
  catch (e) { console.error("[saved-shapes] preview select failed", e); return; }
  setState({
    selectedShapeOptionId: optionId, selectedBuildingId: optionId,
    selectedShapeType: resp?.shape_type || getState().selectedShapeType,
    optimizationResult: null, options: [],
  });
  try {
    const { refreshExplorer, forceViewerRerender } = await import("../agentClient.js");
    await refreshExplorer();
    await forceViewerRerender({ flash: true });
  } catch (e) { console.error("[saved-shapes] preview render failed", e); }
}

// --- footprint thumbnail (same projection as shapesView, site + footprint) ---
function thumbnail(o, site) {
  // Draw the MANIPULATED geometry — overlay every floor-plate footprint, not just the
  // flat outer boundary. A twist shows as a fan of progressively-rotated plates; added
  // floors stack denser; a courtyard shows as a cut hole. (The flat boundary alone
  // never changes on a twist/floor edit, so two different saved shapes looked identical.)
  const plates = (o.floor_plates || []).filter((p) => (p.footprint || []).length >= 3);
  const fp = (o.boundary || o.footprint || []).map((p) => [Number(p[0]), Number(p[1])]);
  const siteRing = (site?.boundary || []).map((p) => [Number(p[0]), Number(p[1])]);
  if (fp.length < 3 && !plates.length) return `<div class="shape-thumb shape-thumb-empty">no preview</div>`;

  // Fit site + boundary + ALL plate footprints into the viewBox.
  const all = [...fp, ...siteRing];
  plates.forEach((p) => p.footprint.forEach((q) => all.push([Number(q[0]), Number(q[1])])));
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  let minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = Math.max(maxX - minX, maxY - minY) * 0.18 || 10;
  minX -= pad; maxX += pad; minY -= pad; maxY += pad;
  const w = maxX - minX || 1, h = maxY - minY || 1;
  const scale = 100 / Math.max(w, h);
  const tx = (p) => ((p[0] - minX) * scale).toFixed(1);
  const ty = (p) => ((maxY - p[1]) * scale).toFixed(1);
  const poly = (ring) => ring.map((p) => `${tx(p)},${ty(p)}`).join(" ");
  const holes = (o.holes || []).filter((hh) => (hh || []).length >= 3);

  // plate stack — bottom plates faint, top plate brightest (reveals twist as a fan)
  let stack = "";
  if (plates.length) {
    const sorted = [...plates].sort((a, b) => (a.z_base || 0) - (b.z_base || 0));
    sorted.forEach((p, i) => {
      const t = i / Math.max(1, sorted.length - 1);
      const op = (0.10 + t * 0.40).toFixed(2);          // 0.10 → 0.50
      const sw = (0.5 + t * 0.8).toFixed(2);
      stack += `<polygon points="${poly(p.footprint.map((q) => [Number(q[0]), Number(q[1])]))}" `
        + `fill="rgba(124,123,255,${op})" stroke="#7cffe6" stroke-width="${sw}" stroke-opacity="${(0.3 + t * 0.7).toFixed(2)}"/>`;
    });
  } else {
    stack = `<polygon points="${poly(fp)}" fill="rgba(124,123,255,0.5)" stroke="#7cffe6" stroke-width="1.1"/>`;
  }

  return `
    <svg class="shape-thumb" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
      ${siteRing.length >= 3 ? `<polygon points="${poly(siteRing)}" fill="rgba(40,224,208,0.08)" stroke="#28e0d0" stroke-width="0.8" stroke-dasharray="2 1.5"/>` : ""}
      ${stack}
      ${holes.map((hh) => `<polygon points="${poly(hh.map((p) => [Number(p[0]), Number(p[1])]))}" fill="rgba(7,11,20,0.92)" stroke="#a9a9ff" stroke-width="0.9"/>`).join("")}
    </svg>`;
}

function card(o, i, site, checked, previewing) {
  const oid = o.shape_option_id || `shape_${i + 1}`;
  const made = o.created_from_prompt || o.label || "";
  const area = o.footprint_area != null ? `${Math.round(o.footprint_area)} m²` : "—";
  const cover = o.site_coverage != null ? `${Math.round(o.site_coverage * 100)}%` : "—";
  const fits = o.fits_within_site !== false;
  const edits = o.manipulation_count ? `${o.manipulation_count} edit${o.manipulation_count > 1 ? "s" : ""}` : "";
  return `
    <div class="opt-card shape-card${previewing ? " selected" : ""}${fits ? "" : " invalid"}${checked ? " ss-checked" : ""}" data-saved="${oid}">
      <div class="opt-card-head">
        <span class="opt-rank">${oid}</span>
        <span class="opt-score">${o.shape_type ?? "—"}${edits ? " · " + edits : ""}</span>
        <button class="ss-check" data-check="${oid}" title="${checked ? "Selected for optimization" : "Tick to optimize"}">${checked ? "☑️" : "⬜"}</button>
      </div>
      ${thumbnail(o, site)}
      <div class="opt-metrics">
        <div><label>Type</label><b>${o.shape_type ?? "—"}</b></div>
        <div><label>Footprint</label><b>${area}</b></div>
        <div><label>Coverage</label><b>${cover}</b></div>
        <div><label>Floors</label><b>${o.floors ?? "—"}</b></div>
        <div><label>Height</label><b>${o.height_m != null ? Math.round(o.height_m) + " m" : "—"}</b></div>
        <div><label>Fit</label><b>${fits ? "✓ fits" : "⚠ outside"}</b></div>
      </div>
      ${made ? `<div class="ss-made" title="${made}">“${made}”</div>` : ""}
      <div class="ss-actions">
        <button class="shape-select-btn ss-optbtn${checked ? " on" : ""}" data-check="${oid}">${checked ? "✓ Selected to Optimize" : "Select to Optimize"}</button>
        <button class="ss-previewbtn" data-preview="${oid}" title="Preview this shape in 3D">👁 Preview</button>
      </div>
    </div>`;
}

function render() {
  const root = document.getElementById("savedshapes-scroll");
  if (!root) return;
  const s = getState();
  const saved = s.savedShapes || [];
  const sel = new Set(s.savedSelection || []);
  const previewing = s.selectedShapeOptionId;
  const site = s.site || s.explorerSite || {};

  if (!saved.length) {
    root.innerHTML = `
      <div class="shapes-head">
        <h2>Saved Shapes</h2>
        <p>No saved shapes yet. Manipulate a building, then <b>Save as new shape option</b> — each version appears here as a card.</p>
      </div>`;
    return;
  }
  root.innerHTML = `
    <div class="shapes-head">
      <h2>Saved Shapes <span class="ss-count">${saved.length}</span></h2>
      <p>Each manipulated version, with its footprint + metrics. <b>Tick ☑</b> the ones to optimize together (pick as many as you like), or <b>Preview</b> one in 3D.</p>
      <div class="ss-bar">
        <button class="ss-optimize${sel.size ? "" : " disabled"}" id="ss-go">⚙ Optimize ${sel.size || 0} selected → 2 variants each</button>
        <button class="ss-clear" id="ss-clear">Clear</button>
      </div>
    </div>
    <div class="shapes-grid">
      ${saved.map((o, i) => card(o, i, site, sel.has(o.shape_option_id), previewing === o.shape_option_id)).join("")}
    </div>`;

  // any [data-check] element (the top checkbox OR the "Select to Optimize" button)
  // toggles this shape's optimization selection.
  root.querySelectorAll("[data-check]").forEach((b) => {
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      const oid = b.dataset.check;
      const next = new Set(getState().savedSelection || []);
      if (next.has(oid)) next.delete(oid); else next.add(oid);
      setState({ savedSelection: [...next] });
      render();
    });
  });
  // clicking the empty card body also toggles selection (big hit target)
  root.querySelectorAll(".shape-card").forEach((c) => {
    c.addEventListener("click", (e) => {
      if (e.target.closest("[data-check]") || e.target.closest("[data-preview]")) return;
      const oid = c.dataset.saved;
      const next = new Set(getState().savedSelection || []);
      if (next.has(oid)) next.delete(oid); else next.add(oid);
      setState({ savedSelection: [...next] });
      render();
    });
  });
  // preview button → load that shape in 3D (local, no fragile dynamic import)
  root.querySelectorAll("[data-preview]").forEach((b) => {
    b.addEventListener("click", (e) => { e.stopPropagation(); runPreview(b.dataset.preview); });
  });
  // optimize selected → runs the optimizer right here
  const go = document.getElementById("ss-go");
  if (go) go.addEventListener("click", () => {
    const ids = [...(getState().savedSelection || [])];
    if (!ids.length) return;
    runOptimizeSelected(ids);
  });
  const clr = document.getElementById("ss-clear");
  if (clr) clr.addEventListener("click", () => { setState({ savedSelection: [] }); render(); });
}

export function activate() { render(); }
export async function onAction() { render(); }
