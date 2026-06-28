// Live Design Health dashboard — a floating, DRAGGABLE, MINIMIZABLE panel over the
// 3D window that shows the current building's performance scores as animated bars and
// UPDATES LIVE after every manipulation, with ↑/↓ deltas so the user sees the
// trade-offs of each design decision.
//
// Fully ADDITIVE + self-contained: it mounts its own DOM into #center, subscribes to
// the store, and calls the existing /evaluate-design endpoint (which scores the
// current building WITHOUT changing it). Nothing else in the app depends on it — if it
// errors, it hides itself and the app is unaffected.

import { getState, subscribe } from "../core/store.js";
import { api } from "../core/api.js";

// The objectives shown, in order, with glyph + label + color.
const METRICS = [
  { key: "solar", label: "Solar", glyph: "☀", color: "#ffd166" },
  { key: "view", label: "View", glyph: "👁", color: "#57f2e6" },
  { key: "noise", label: "Noise", glyph: "🔊", color: "#7c7bff" },
  { key: "wind", label: "Wind", glyph: "💨", color: "#38bdf8" },
  { key: "open_space", label: "Open Space", glyph: "🌳", color: "#57e08a" },
  { key: "density", label: "Density", glyph: "🏢", color: "#ff8fa3" },
  { key: "road_access", label: "Access", glyph: "🛣", color: "#ffb454" },
];

// Stages where the dashboard is relevant (a building exists to score). NOT in
// "compare": it floated over the comparison TABLE and cluttered it — the compare view
// shows per-option scores in the table itself, so the live panel is redundant there.
const ACTIVE_VIEWS = new Set(["viewer", "optimize"]);

let el = null;            // the panel root
let mounted = false;
let lastScores = {};      // previous scores → compute deltas
let lastSig = "";         // geometry signature → only re-evaluate when it changes
let evaluating = false;
let collapsed = false;
let dragState = null;

function ensureMounted() {
  if (mounted) return;
  // Mount on <body> (NOT inside #center) so the panel can be dragged ANYWHERE on the
  // whole screen — #center has overflow:hidden which was clipping it when dragged out.
  el = document.createElement("div");
  el.id = "health-dash";
  el.className = "health-dash hidden";
  el.innerHTML = `
    <div class="hd-head" id="hd-head">
      <span class="hd-title"><span class="hd-pulse"></span> Design Health</span>
      <div class="hd-actions">
        <span class="hd-overall" id="hd-overall">—</span>
        <button class="hd-btn" id="hd-min" title="Minimize">▁</button>
      </div>
    </div>
    <div class="hd-body" id="hd-body">
      ${METRICS.map((m) => {
        const envCapable = ["wind", "noise", "view", "solar", "density", "road_access"].includes(m.key);
        return `
        <div class="hd-row" data-k="${m.key}">
          <span class="hd-glyph">${m.glyph}</span>
          <span class="hd-label">${m.label}${envCapable ? ` <span class="hd-envbadge" id="hd-${m.key}-badge">proxy</span>` : ""}</span>
          <span class="hd-track"><i style="--c:${m.color}" id="hd-bar-${m.key}"></i></span>
          <span class="hd-val" id="hd-val-${m.key}">—</span>
          <span class="hd-delta" id="hd-delta-${m.key}"></span>
        </div>${envCapable ? `<div class="hd-wind-env hidden" id="hd-${m.key}-env"></div>` : ""}`;
      }).join("")}
      <div class="hd-foot">Live scores · updates as you edit the shape</div>
    </div>`;
  document.body.appendChild(el);
  mounted = true;

  // Minimize / restore.
  el.querySelector("#hd-min").addEventListener("click", (e) => {
    e.stopPropagation();
    collapsed = !collapsed;
    el.classList.toggle("collapsed", collapsed);
    el.querySelector("#hd-min").textContent = collapsed ? "▢" : "▁";
    el.querySelector("#hd-min").title = collapsed ? "Expand" : "Minimize";
  });

  // Drag anywhere on screen by the header.
  const head = el.querySelector("#hd-head");
  head.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".hd-btn")) return;
    const r = el.getBoundingClientRect();
    dragState = { dx: e.clientX - r.left, dy: e.clientY - r.top };
    el.classList.add("dragging");
    head.setPointerCapture(e.pointerId);
  });
  head.addEventListener("pointermove", (e) => {
    if (!dragState) return;
    // Clamp so it never leaves the viewport.
    const w = el.offsetWidth, h = el.offsetHeight;
    const x = Math.max(4, Math.min(window.innerWidth - w - 4, e.clientX - dragState.dx));
    const y = Math.max(4, Math.min(window.innerHeight - h - 4, e.clientY - dragState.dy));
    el.style.left = x + "px";
    el.style.top = y + "px";
    el.style.right = "auto";
  });
  const endDrag = () => { dragState = null; el.classList.remove("dragging"); };
  head.addEventListener("pointerup", endDrag);
  head.addEventListener("pointercancel", endDrag);

  // Double-click the header to snap back to the default position (rescue if dragged
  // somewhere awkward).
  head.addEventListener("dblclick", () => {
    el.style.left = "auto"; el.style.top = "92px"; el.style.right = "410px";
  });

  subscribe(onState);
  onState();
}

// Geometry signature of the current building — so we only re-evaluate when it changes
// (not on every unrelated store update).
function _sig(s) {
  const b = (s.buildings || [])[0] || {};
  const ring = b.boundary || b.building_boundary || [];
  const holes = (b.holes || []).length;
  const floors = b.floors || b.height_m || 0;
  let acc = `${ring.length}:${holes}:${floors}:`;
  for (let i = 0; i < ring.length; i += 2) acc += `${Math.round(ring[i]?.[0] || 0)},${Math.round(ring[i]?.[1] || 0)};`;
  return acc;
}

function onState() {
  if (!el) return;
  const s = getState();
  const relevant = ACTIVE_VIEWS.has(s.centerView) && (s.buildings || []).length > 0 && s.sessionId;
  el.classList.toggle("hidden", !relevant);
  if (!relevant) return;

  const sig = _sig(s);
  if (sig !== lastSig && !evaluating) {
    lastSig = sig;
    refresh(s.sessionId);
  }
}

async function refresh(sessionId) {
  evaluating = true;
  try {
    const res = await api.agent.evaluateDesign(sessionId);
    const scores = res?.scores || {};
    paint(scores, res?.env_analysis || {});
    lastScores = scores;
  } catch {
    /* leave last values; the panel never blocks the app */
  } finally {
    evaluating = false;
  }
}

// Environmental detail for an upgraded metric: a badge on its row (proxy / ● live) +
// a comparison line (geometry score → real score) when Environmental Mode is active.
// `detail(rec)` builds the metric-specific descriptor text. Geometry mode → just "proxy".
function paintEnvRow(key, rec, detail) {
  const badge = el.querySelector(`#hd-${key}-badge`);
  const info = el.querySelector(`#hd-${key}-env`);
  if (!badge || !info) return;
  if (rec && rec.mode === "environmental") {
    badge.textContent = "● live";
    badge.className = "hd-envbadge on";
    badge.title = "Scored against real site data";
    const proxy = rec.proxy_score != null ? Math.round(rec.proxy_score) : "—";
    const env = rec.env_score != null ? Math.round(rec.env_score) : "—";
    info.innerHTML = `${detail(rec)} <span class="hd-cmp">geometry ${proxy} → <b>real ${env}</b></span>`;
    info.classList.remove("hidden");
  } else {
    badge.textContent = "proxy";
    badge.className = "hd-envbadge";
    badge.title = "Geometry estimate. Turn on Environmental Mode for real site data.";
    info.classList.add("hidden");
  }
}

function paint(scores, envAnalysis = {}) {
  if (!el) return;
  paintEnvRow("wind", envAnalysis.wind, (w) =>
    `<b>${w.prevailing_wind || "?"}</b> · ${w.wind_speed_ms ?? "?"} m/s · exposure ${w.facade_exposure_pct ?? "?"}%`);
  paintEnvRow("noise", envAnalysis.noise, (n) =>
    `day ~${n.day_noise_db ?? "?"} dB · night ~${n.night_noise_db ?? "?"} dB · ${n.loudest_source || "road"}`);
  paintEnvRow("view", envAnalysis.view, (v) =>
    `${v.positive_features ?? 0} good · ${v.negative_features ?? 0} poor features nearby`);
  paintEnvRow("solar", envAnalysis.solar, (s) =>
    `${s.annual_radiation_kwh_m2_day ?? "?"} kWh/m²/day · ${s.summer_max_temp_c ?? "?"}°C · overheating ${s.overheating_risk_pct ?? "?"}%`);
  paintEnvRow("density", envAnalysis.density, (d) =>
    `<b>${d.proposed_height_m ?? "?"}m</b> vs local ${d.context_median_height_m ?? "?"}m · fit ${d.context_fit_pct ?? "?"}%`);
  paintEnvRow("road_access", envAnalysis.road_access, (a) =>
    `${a.amenities_within_walk ?? 0}/5 amenity types within walk`);
  const ov = el.querySelector("#hd-overall");
  if (ov && scores.overall_score != null) {
    const o = Math.round(scores.overall_score);
    ov.textContent = o;
    ov.style.color = o >= 70 ? "#57e08a" : o >= 45 ? "#ffd166" : "#ff8fa3";
  }
  METRICS.forEach((m) => {
    const v = Number(scores[m.key]);
    const bar = el.querySelector(`#hd-bar-${m.key}`);
    const val = el.querySelector(`#hd-val-${m.key}`);
    const del = el.querySelector(`#hd-delta-${m.key}`);
    if (!bar || !val) return;
    if (!Number.isFinite(v)) {
      bar.style.width = "0%"; val.textContent = "—";
      val.classList.add("na"); if (del) del.textContent = "";
      return;
    }
    val.classList.remove("na");
    bar.style.width = Math.max(0, Math.min(100, v)) + "%";  // CSS transition animates it
    val.textContent = Math.round(v);
    // delta vs the previous evaluation
    const prev = Number(lastScores[m.key]);
    if (del) {
      if (Number.isFinite(prev) && Math.abs(v - prev) >= 1) {
        const d = Math.round(v - prev);
        del.textContent = (d > 0 ? "▲" : "▼") + Math.abs(d);
        del.className = "hd-delta " + (d > 0 ? "up" : "down");
        del.classList.add("flash");
        setTimeout(() => del && del.classList.remove("flash"), 1200);
      } else {
        del.textContent = "";
      }
    }
  });
}

// Public entry — called once at app init. Safe to call repeatedly.
export function initHealthDashboard() {
  try { ensureMounted(); } catch { /* never block app init */ }
}
