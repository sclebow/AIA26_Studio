// Left panel: VS Code-style project explorer. Top-level folders Site / Urban Context /
// Shapes / Saved Shapes / Optimization / Comparison / Decisions, each filled from the
// store as the workflow advances. "Saved Shapes" holds manipulated shapes saved as
// Shape Library versions (between Shapes and Optimization).

import { getState, setState, subscribe } from "../core/store.js";
import { api } from "../core/api.js";

const collapsed = new Set(); // folder ids the user has collapsed

// Preview a SAVED manipulated shape from the left-panel "Saved Shapes" explorer:
// make it the active building (its twist/courtyard/added-floors preserved), render it
// in the 3D viewer, and arm it for "optimize this shape". Mirrors the Copilot's
// preview_saved flow so both entry points behave the same. Best-effort & non-blocking.
let _previewing = false;   // guard: never let overlapping preview clicks pile up
export async function previewSavedShape(optionId) {
  const { sessionId } = getState();
  if (!sessionId || !optionId || _previewing) return;
  _previewing = true;
  try {
    await api.agent.selectDesignOption(sessionId, optionId);
    // mark which saved shape is active (highlights its row + arms the optimizer)
    setState({ selectedShapeOptionId: optionId, selectedBuildingId: optionId });
    // load the saved geometry into the store, then render it in the 3D viewer.
    // Done sequentially with awaits — no fan-out of setState calls that could storm
    // the explorer's store subscription (that was the freeze).
    const { refreshExplorer, forceViewerRerender } = await import("../agentClient.js");
    await refreshExplorer();
    await forceViewerRerender({ flash: true });
  } catch (e) {
    console.error("[explorer] preview saved shape failed", e);
  } finally {
    _previewing = false;
  }
}

// Optimize the SELECTED saved shapes together (multi-select — unlike manipulation's
// single pick). Calls optimize-all-saved with the chosen ids, feeds the ranked results
// into the options store, and opens the comparison view. Manipulated geometry (twist /
// courtyard / added floors) is retained per shape; placement is optimized.
export async function optimizeSavedSelection(optionIds) {
  const { sessionId } = getState();
  if (!sessionId || !optionIds?.length) return;
  // Do NOT flash the Optimization view here — it shows the stale Pareto card from a
  // previous main-optimize run ("1 distinct option · 0.00"), which made it look like
  // only one option came back. Clear any stale result and show a busy status; we jump
  // straight to the comparison view once the variants are in.
  try { const { setStatus } = await import("../agentClient.js"); if (setStatus) setStatus("Optimizing saved shapes…"); } catch {}
  setState({ optimizationResult: null });
  let res = null;
  try {
    res = await api.agent.optimizeAllSavedShapes(sessionId, optionIds);
  } catch (e) {
    console.error("[explorer] optimize saved selection failed", e);
    return;
  }
  const opts = res?.optimized_options || [];
  if (!opts.length) return;
  // Register BOTH the original saved shapes (S01, S02…) AND their optimized variants
  // (S01A, S01B…) in the comparison set, so the user can compare any combination
  // (S01 vs S01A vs S01B, or S01A vs S02A, etc.).
  const baselineOpts = (res.source_shapes || []).map((b) => ({
    option_id: b.shape_option_id,
    label: b.shape_option_id,
    shape_type: b.shape_type,
    is_baseline: true,
    source_shape_option_id: b.shape_option_id,
    score: b.scores?.total,
    objective_scores: b.scores,
    // geometry so the baseline column shows floors/footprint/preview, not N/A
    boundary: b.geometry?.boundary,
    footprint: b.geometry?.boundary,
    holes: b.geometry?.holes || [],
    floor_plates: b.geometry?.floor_plates || [],
    floors: b.floors ?? b.geometry?.floors,
    footprint_area: b.footprint_area,
  }));
  const variantOpts = opts.map((o) => ({
    option_id: o.optimized_option_id,
    label: o.optimized_option_id,         // e.g. shape_001A
    shape_type: o.shape_type,
    boundary: o.geometry.boundary,
    footprint: o.geometry.boundary,
    floors: o.geometry.floors,
    score: o.scores.total,
    holes: o.geometry.holes || [],
    floor_plates: o.geometry.floor_plates || [],
    rotation_degrees: o.placement.rotation_degrees,
    source_shape_option_id: o.source_shape_option_id,
    variant_tag: o.variant_tag,
    objective_scores: o.scores,
    validation_report: o.validation_report,
    is_optimized: true,                   // marks it for the Optimization Explorer folder
  }));
  const options = [...baselineOpts, ...variantOpts];
  // CRITICAL FIX: the Optimization Explorer folder renders from `savedOptimized` (the
  // PERSISTENT optimized-variant store, reloaded from optimization_history so it survives
  // tab navigation + refresh). optimizeSavedSelection previously set only `options`/
  // `comparisonOptions` and never `savedOptimized`, so the folder stayed empty ("tick
  // saved shapes → Optimize to populate") even though the run succeeded. Populate it
  // here immediately (so it shows without a round-trip), MERGING with any prior run so
  // multiple optimize sessions ACCUMULATE rather than replace each other.
  const priorOptimized = getState().savedOptimized || [];
  const mergedById = new Map(priorOptimized.map((o) => [o.option_id, o]));
  variantOpts.forEach((o) => mergedById.set(o.option_id, o));
  const savedOptimized = [...mergedById.values()];
  setState({
    options,
    comparisonOptions: options,
    optimizationResult: res,
    savedOptimized,                       // ← persistent source the explorer reads
    // pre-select all of them for comparison so the table is ready to read
    compareSelection: options.map((o) => o.option_id),
    visibleOptionIds: new Set(variantOpts.map((o) => o.option_id)),
    centerView: "compare",
  });
  try {
    const { dispatchView } = await import("./center.js");
    await dispatchView({ type: "compare", payload: { action: "compare", option_ids: options.map((o) => o.option_id) } });
  } catch { /* view mounts later */ }
  // NOTE: do NOT call refreshExplorer() here. The setState above already populated
  // savedOptimized + comparisonOptions from the FRESH optimize response (the most
  // authoritative source). refreshExplorer re-reads /optimization-history and
  // unconditionally re-writes savedOptimized — a redundant round-trip that can race the
  // just-completed run and blank the folder. Persistence across a hard refresh is handled
  // by refreshExplorer on the NEXT load, which reads the same history we just wrote.
}

// Preview a persisted OPTIMIZED variant (S01A, S02B…) in the 3D viewer — renders its
// saved geometry (footprint + holes + floor plates) like a live option.
async function previewOptimizedOption(opt) {
  if (!opt) return;
  setState({
    selectedOptionId: opt.option_id,
    options: [opt],
    visibleOptionIds: new Set([opt.option_id]),
    centerView: "viewer",
  });
  try {
    const { dispatchView } = await import("./center.js");
    await dispatchView({ type: "viewer", payload: { action: "preview_optimized", option_id: opt.option_id } });
    const viewer = await import("../views/viewerView.js");
    if (typeof viewer.flashBuilding === "function") viewer.flashBuilding();
  } catch (e) { console.error("[explorer] preview optimized failed", e); }
}

async function toggleOptionVisibility(optionId) {
  const s = getState();
  const visible = new Set(s.visibleOptionIds || []);
  if (visible.has(optionId)) visible.delete(optionId);
  else visible.add(optionId);
  setState({ centerView: "viewer" });
  try {
    const viewer = await import("../views/viewerView.js");
    viewer.activate();
    // setVisibleOptions writes visibleOptionIds into the store (single source of
    // truth) and re-renders. Always pass an array — empty means "hide all",
    // which is distinct from null (no filter / show all).
    viewer.setVisibleOptions([...visible]);
  } catch (e) {
    console.error("[explorer] toggle visibility failed", e);
  }
}

function row({ id, label, icon, twisty = "", badge = "", active = false, depth = 0, onClick }) {
  const el = document.createElement("div");
  el.className = "tree-row" + (active ? " active" : "");
  el.style.paddingLeft = `${8 + depth * 14}px`;
  el.innerHTML = `
    <span class="twisty">${twisty}</span>
    <span class="ico">${icon}</span>
    <span class="label">${label}</span>
    ${badge ? `<span class="badge">${badge}</span>` : ""}`;
  if (onClick) el.addEventListener("click", onClick);
  return el;
}

function folder(container, id, label, icon, childCount, renderChildren) {
  const isCollapsed = collapsed.has(id);
  const head = row({
    id,
    label,
    icon,
    twisty: isCollapsed ? "▶" : "▼",
    badge: childCount ? String(childCount) : "",
    onClick: () => {
      if (collapsed.has(id)) collapsed.delete(id);
      else collapsed.add(id);
      render();
    },
  });
  head.classList.add("tree-folder");
  container.appendChild(head);
  const kids = document.createElement("div");
  kids.className = "tree-children" + (isCollapsed ? " collapsed" : "");
  renderChildren(kids);
  container.appendChild(kids);
}

function leaf(kids, label, icon, extra = "") {
  kids.appendChild(row({ label, icon, depth: 1, badge: extra }));
}

// Toggle one urban-context layer's visibility in the 3D twin.
async function toggleContextLayer(key) {
  const s = getState();
  const cur = s.contextVisible || {};
  const next = { ...cur, [key]: cur[key] === false ? true : false };
  setState({ contextVisible: next });
  try {
    const cv = await import("../views/contextView.js");
    cv.refreshVisibility && cv.refreshVisibility();
  } catch { /* not mounted */ }
}

function contextLayerOn(key) {
  const v = getState().contextVisible;
  return !v || v[key] !== false;
}

// A context layer row: colored swatch + label + count + nearest distance + eye.
function contextLeaf(kids, key, label, color, count, nearestM, depth = 2) {
  const on = contextLayerOn(key);
  const el = document.createElement("div");
  el.className = "tree-row context-layer";
  el.style.paddingLeft = `${8 + depth * 14}px`;
  const dist = nearestM != null ? `${nearestM}m` : "—";
  el.innerHTML = `
    <span class="ctx-swatch" style="background:${color}"></span>
    <span class="label">${label}</span>
    <span class="ctx-count">${count ?? 0}</span>
    <span class="ctx-dist" title="nearest">${dist}</span>
    <button class="ctx-eye" title="${on ? "Hide" : "Show"}">${on ? "👁️" : "🚫"}</button>`;
  el.querySelector(".ctx-eye").addEventListener("click", (e) => { e.stopPropagation(); toggleContextLayer(key); });
  kids.appendChild(el);
}

function emptyHint(kids, text) {
  const e = document.createElement("div");
  e.className = "tree-empty";
  e.textContent = text;
  kids.appendChild(e);
}

function render() {
  const root = document.getElementById("explorer-tree");
  if (!root) return;
  const s = getState();
  root.innerHTML = `<div class="explorer-header">Project Explorer · v2 (context)</div>`;
  const tree = document.createElement("div");
  tree.className = "tree";

  // --- Site ---
  folder(tree, "site", "Site", "📍", 0, (kids) => {
    if (s.locationSaved && s.location) {
      leaf(kids, s.location.name || "Location", "📌");
      leaf(kids, `${s.location.lat.toFixed(5)}, ${s.location.lng.toFixed(5)}`, "🌐");
    }
    if (s.boundarySaved && s.boundary.length) {
      const area = s.site?.site_area ? `${Math.round(s.site.site_area)} m²` : "";
      leaf(kids, "Site Boundary", "⬡", area);
    }
    if (!s.locationSaved && !s.boundarySaved) emptyHint(kids, "no location saved yet");
  });

  // --- Urban Context --- (roads + amenities classified into the Context Explorer
  // tree from the client-side overpass.js shape: layers keyed "group.key", each
  // with style.color, count, nearest (m). Every layer row has a toggle/count/dist).
  const ctx = s.context;
  const layers = ctx?.layers || {};
  const ctxCount = Object.values(layers).reduce((a, l) => a + (l.count || 0), 0);
  folder(tree, "context", "Urban Context", "🛰️", ctxCount, (kids) => {
    if (s.contextLoading) { emptyHint(kids, "analyzing context…"); return; }
    if (!ctx) {
      emptyHint(kids, s.contextError ? "context unavailable" : "no context analyzed yet");
      return;
    }
    // Group the layers by their `group` field, in display order. Hidden-in-tree
    // layers (restaurants/public) are still counted by their group total.
    const groupsOrder = ["Roads", "Education", "Transportation", "Retail", "Parks", "Healthcare"];
    const catIcon = { Roads: "🛣️", Education: "🎓", Transportation: "🚇", Retail: "🛍️", Parks: "🌳", Healthcare: "🏥" };
    const byGroup = {};
    Object.entries(layers).forEach(([id, l]) => {
      (byGroup[l.group] = byGroup[l.group] || []).push([id, l]);
    });
    groupsOrder.forEach((grp) => {
      const items = byGroup[grp];
      if (!items) return;
      const total = items.reduce((a, [, l]) => a + (l.count || 0), 0);
      const shown = items.filter(([, l]) => !l.hiddenInTree);
      folder(kids, `ctx-${grp}`, grp, catIcon[grp] || "•", total, (ck) => {
        shown.forEach(([id, l]) => contextLeaf(ck, id, l.label, l.style?.color || "#9fb4cc", l.count, l.nearest, 2));
      });
    });
  });

  // --- Shapes (placed buildings + shape-type rollups live here together) ---
  // The agent's generated/placed buildings belong under Shapes, not a separate
  // top-level folder, so the explorer reads top→bottom: Site → Shapes(buildings)
  // → Optimization → Comparison → Decisions.
  const shapeTypes = Object.keys(s.shapesByType || {});
  const agentBuildings = s.buildings || [];
  const shapeCount = agentBuildings.length || shapeTypes.length;
  folder(tree, "shapes", "Shapes", "🏗️", shapeCount, (kids) => {
    if (!agentBuildings.length && !shapeTypes.length) {
      emptyHint(kids, "no shapes generated yet");
      return;
    }
    // Placed buildings from the agent (each with wings + placement options).
    agentBuildings.forEach((b) => {
      const area = b.area_sqm ? `${Math.round(b.area_sqm)} m²` : "";
      const floors = b.height_m ? `${Math.round(b.height_m / 3)}f` : "";
      const r = row({
        label: b.label || b.building_id,
        icon: "🏢",
        depth: 1,
        badge: [floors, area].filter(Boolean).join(" · "),
        active: s.selectedBuildingId === b.building_id,
        onClick: () => setState({ selectedBuildingId: b.building_id }),
      });
      kids.appendChild(r);
      (b.wings || []).forEach((w) => {
        const dims = w.length_m && w.width_m ? ` · ${Math.round(w.length_m)}×${Math.round(w.width_m)}m` : "";
        leaf(kids, `${w.role} wing`, "📐", `${Math.round(w.area_sqm || 0)} m²${dims}`);
      });
      const opts = b.placement_options || [];
      if (opts.length) leaf(kids, `${opts.length} placement option(s)`, "🎯");
    });
    // Shape-type rollups (Backend-A style) when present and no agent buildings.
    if (!agentBuildings.length) {
      for (const t of shapeTypes) {
        const arr = s.shapesByType[t] || [];
        leaf(kids, t, "📐", String(arr.length));
      }
    }
  });

  // --- Saved Shapes --- (manipulated shapes saved as Shape Library versions).
  // Sits between Shapes and Optimization: you generate → select → manipulate → save,
  // and each saved version lands here to preview/select again or optimize.
  const savedShapes = s.savedShapes || [];
  const savedSel = new Set(s.savedSelection || []);
  folder(tree, "saved-shapes", "Saved Shapes", "💾", savedShapes.length, (kids) => {
    if (!savedShapes.length) {
      emptyHint(kids, "manipulate a shape, then Save");
      return;
    }
    // Open the visual gallery (cards with footprint thumbnails + metrics).
    const gallery = row({
      label: "Open gallery view", icon: "🖼️", depth: 1,
      onClick: async () => {
        setState({ centerView: "savedshapes" });
        const { dispatchView } = await import("./center.js");
        await dispatchView({ type: "savedshapes", payload: { action: "open" } });
      },
    });
    gallery.style.color = "var(--accent)";
    kids.appendChild(gallery);
    emptyHint(kids, "click a shape to PREVIEW it · tick the box ☑ to optimize");
    savedShapes.forEach((sv, i) => {
      const oid = sv.shape_option_id || `shape_${i + 1}`;
      const made = sv.created_from_prompt ? `“${sv.created_from_prompt}”` : "";
      const checked = savedSel.has(oid);
      const isPreviewed = s.selectedShapeOptionId === oid;
      // badge: type + (manipulation count if known)
      const badgeBits = [sv.shape_type, sv.manipulation_count ? `${sv.manipulation_count} edit${sv.manipulation_count > 1 ? "s" : ""}` : ""].filter(Boolean);
      const r = row({
        label: sv.label || oid,
        icon: checked ? "☑️" : "⬜",
        depth: 1,
        badge: badgeBits.join(" · "),
        active: isPreviewed,           // highlight the shape currently previewed
        onClick: () => previewSavedShape(oid),   // CLICK = preview the geometry (Issue 1)
      });
      r.title = `${oid}${made ? " — " + made : ""}  ·  click to preview · tick ☑ to optimize`;
      // the checkbox (icon) is its own click zone → toggles selection without previewing
      const ico = r.querySelector(".ico");
      if (ico) {
        ico.style.cursor = "pointer";
        ico.addEventListener("click", (e) => {
          e.stopPropagation();
          const next = new Set(getState().savedSelection || []);
          if (next.has(oid)) next.delete(oid); else next.add(oid);
          setState({ savedSelection: [...next] });
        });
      }
      kids.appendChild(r);
    });
    // "Optimize N selected" action (multi-select — unlike manipulation's single pick).
    // The button click IS the confirmation — runs optimization immediately, no chat ask.
    if (savedSel.size >= 1) {
      const go = row({
        label: `⚙ Optimize ${savedSel.size} selected → 2 variants each`,
        icon: "▶", depth: 1,
        onClick: () => optimizeSavedSelection([...savedSel]),
      });
      go.style.color = "var(--accent)";
      go.style.fontWeight = "600";
      kids.appendChild(go);
    } else {
      emptyHint(kids, "tick at least one shape to enable optimization");
    }
  });

  // --- Optimization --- (only shows REAL scored options from the /optimize run,
  // never the generation placement candidates which have no view scores)
  // Persisted optimized variants (survive refresh) grouped by their source saved shape:
  //   S01 → S01A, S01B ;  S02 → S02A, S02B …  — preview + tick to compare.
  const savedOptimized = s.savedOptimized || [];
  // also surface live (un-persisted) optimize results if a run just happened
  const liveOptimized = s.optimizationResult ? (s.options || []).filter((o) => o.is_optimized || o.source_shape_option_id) : [];
  const allOptimized = savedOptimized.length ? savedOptimized : liveOptimized;
  const cmpSel = new Set(s.compareSelection || []);
  folder(tree, "optimization", "Optimization", "⚙️", allOptimized.length, (kids) => {
    if (!allOptimized.length) {
      emptyHint(kids, "tick saved shapes → Optimize to populate");
      return;
    }
    emptyHint(kids, "click to PREVIEW · tick ☑ to add to comparison");
    // group by source shape so the tree reads S01 ▸ S01A, S01B
    const groups = {};
    allOptimized.forEach((o) => {
      const src = o.source_shape_option_id || "—";
      (groups[src] = groups[src] || []).push(o);
    });
    Object.entries(groups).forEach(([src, variants]) => {
      // a faint group header (the original saved shape)
      const hdr = row({ label: src, icon: "🧩", depth: 1, badge: `${variants.length} variant${variants.length > 1 ? "s" : ""}` });
      hdr.style.opacity = "0.75";
      kids.appendChild(hdr);
      variants.forEach((opt) => {
        const score = Number.isFinite(Number(opt.score)) ? Number(opt.score).toFixed(1) : "-";
        const checked = cmpSel.has(opt.option_id);
        const r = row({
          label: opt.label || opt.option_id,        // e.g. shape_001A
          icon: checked ? "☑️" : "⬜",
          depth: 2,
          badge: score,
          active: s.selectedOptionId === opt.option_id,
          onClick: () => previewOptimizedOption(opt),   // CLICK = preview in 3D
        });
        // checkbox zone → toggle comparison membership
        const ico = r.querySelector(".ico");
        if (ico) {
          ico.style.cursor = "pointer";
          ico.addEventListener("click", (e) => {
            e.stopPropagation();
            const next = new Set(getState().compareSelection || []);
            if (next.has(opt.option_id)) next.delete(opt.option_id); else next.add(opt.option_id);
            setState({ compareSelection: [...next] });
          });
        }
        r.title = `${opt.option_id} — score ${score} · click to preview · tick ☑ to compare`;
        kids.appendChild(r);
      });
    });
  });

  // --- Comparison --- compare ANY combination: original saved shapes (baselines) AND
  // their optimized variants (S01 vs S01A vs S01B, or S01A vs S02A, …). The pool is the
  // persisted optimized variants + the saved shapes, so it survives a refresh.
  const cmpPool = [
    ...(s.savedShapes || []).map((sv) => ({
      option_id: sv.shape_option_id, label: sv.shape_option_id + " (original)",
      shape_type: sv.shape_type, boundary: sv.boundary || [], footprint: sv.boundary || [],
      holes: sv.holes || [], floor_plates: sv.floor_plates || [], floors: sv.floors,
      objective_scores: {}, score: null, is_baseline: true,
    })),
    ...allOptimized,
  ];
  folder(tree, "comparison", "Comparison", "📊", (s.compareSelection || []).length, (kids) => {
    if (!cmpPool.length) {
      emptyHint(kids, "save + optimize shapes first, then pick options to compare");
      return;
    }
    const sel = new Set(s.compareSelection || []);
    emptyHint(kids, "tick any mix of originals + optimized, then Compare");
    cmpPool.forEach((opt) => {
      const checked = sel.has(opt.option_id);
      const score = Number.isFinite(Number(opt.score)) ? Number(opt.score).toFixed(1) : (opt.is_baseline ? "orig" : "");
      const r = row({
        label: opt.label || opt.option_id,
        icon: checked ? "☑️" : "⬜",
        depth: 1,
        badge: score,
        onClick: () => {
          const next = new Set(getState().compareSelection || []);
          if (next.has(opt.option_id)) next.delete(opt.option_id); else next.add(opt.option_id);
          setState({ compareSelection: [...next] });
        },
      });
      r.title = checked ? "Selected — click to remove" : "Click to add to comparison";
      kids.appendChild(r);
    });
    if (sel.size >= 2) {
      const go = row({
        label: `📋 Compare ${sel.size} options`, icon: "▶", depth: 1,
        onClick: async () => {
          const ids = [...sel];
          const chosen = cmpPool.filter((o) => ids.includes(o.option_id));
          setState({ centerView: "compare", comparisonOptions: chosen });
          const { dispatchView } = await import("./center.js");
          await dispatchView({ type: "compare", payload: { action: "compare", option_ids: ids } });
        },
      });
      go.style.color = "var(--accent)";
      go.style.fontWeight = "600";
      kids.appendChild(go);
    } else {
      emptyHint(kids, "select at least 2 to compare");
    }
  });

  // --- Decisions (real project timeline → Design Evolution replay) ---
  if (s.sessionId || (s.buildings && s.buildings.length)) {
    const histCount = (s.decisionHistory || []).length;
    folder(tree, "decisions", "Decisions", "🌳", histCount, (kids) => {
      if (!histCount) {
        emptyHint(kids, "your design actions will appear here");
        return;
      }
      const r = row({
        label: "Design Evolution (replay)",
        icon: "🎬",
        depth: 1,
        badge: `${histCount} steps`,
        onClick: () => setState({ centerView: "decision" }),
      });
      kids.appendChild(r);
    });
  }

  root.appendChild(tree);
}

export function initExplorer() {
  // Left panel hosts only the project/site/KPI explorer. The workflow dock is a
  // global, full-width bar in the app grid (see index.html #bottom-dock).
  const panel = document.getElementById("explorer");
  if (panel && !document.getElementById("explorer-tree")) {
    panel.innerHTML = `<div id="explorer-tree"></div>`;
  }
  render();
  subscribe(render);
}
