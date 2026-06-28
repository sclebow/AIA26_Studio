// Decision Graph view — an animated DAG of the REAL project timeline
// (store.decisionHistory), rendered on a canvas in the visual style of
// test_decision_graph.ipynb: nodes positioned by stage-depth with branching,
// typed colors/symbols, edges drawn as lines, and a Play/Pause/Restart/Speed
// replay that reveals nodes + edges one-by-one with Copilot narration.

import { getState, setState, subscribe, pushMessage } from "../core/store.js";

// Per-stage visual identity (mirrors the notebook's TYPE_COLORS/SYMBOLS).
const STAGE_META = {
  site:         { color: "#2980b9", symbol: "diamond", label: "Site" },
  boundary:     { color: "#3498db", symbol: "diamond", label: "Boundary" },
  shape:        { color: "#8e44ad", symbol: "star",    label: "Shape" },
  editing:      { color: "#e67e22", symbol: "square",  label: "Edit" },
  optimization: { color: "#16a085", symbol: "hexagon", label: "Optimize" },
  comparison:   { color: "#2980b9", symbol: "square",  label: "Compare" },
  export:       { color: "#f0c674", symbol: "circle",  label: "Export" },
  // self-correction loop nodes (validate_design + design_debug)
  validate:     { color: "#27ae60", symbol: "diamond", label: "Validate" },
  debug:        { color: "#c0392b", symbol: "square",  label: "Self-debug" },
};
const REJECT_COLOR = "#e74c3c";
const FINAL_COLOR = "#f1c40f";

let subscribed = false;
let replay = { playing: false, index: 0, timer: null, speed: 1 };
let canvas = null, ctx = null, dpr = 1;
let autoplayedFor = -1; // history length we last autoplayed at (avoid re-triggering on every re-render)

export function activate() {
  if (!subscribed) {
    subscribe(() => { if (getState().centerView === "decision") draw(); });
    subscribed = true;
  }
  render();
  maybeAutoplay();
}
export async function onAction() { render(); maybeAutoplay(); }

// Autoplay the replay (at the current speed, default 1×) the first time the view
// is opened for a given history — without disabling the manual controls.
function maybeAutoplay() {
  const h = getState().decisionHistory || [];
  if (!h.length || replay.playing) return;
  if (autoplayedFor === h.length) return; // already autoplayed this timeline
  autoplayedFor = h.length;
  replay.index = 0;
  // brief delay so the canvas has laid out before the first frame reveals
  setTimeout(() => { if (getState().centerView === "decision") startReplay(); }, 350);
}

function isRejected(s) { return s.data?.rejected === true || /rejected/.test(s.action || ""); }
function isFinal(s) { return s.action === "final_option_selected"; }
function metaFor(s) { return STAGE_META[s.stage] || { color: "#7f8c8d", symbol: "circle", label: s.stage }; }

// ---- Layout: each step is a node; y = sequence depth, x = branch lane. Rejected
// edits branch to a side lane (like the notebook's rejected fork), accepted steps
// stay on the main spine. Returns [{step, x, y, ...}] in normalized 0..1 coords.
function layout(history) {
  const n = history.length || 1;
  return history.map((step, i) => {
    const rejected = isRejected(step);
    return {
      step, i,
      // main spine at x=0.5; rejected edits fork to x=0.78
      x: rejected ? 0.74 : 0.5,
      y: (i + 0.5) / n,
      rejected,
      final: isFinal(step),
      meta: metaFor(step),
    };
  });
}

// ---- Replay control ----
function stopReplay() { replay.playing = false; if (replay.timer) { clearTimeout(replay.timer); replay.timer = null; } draw(); }
function startReplay() {
  const h = getState().decisionHistory || [];
  if (!h.length) return;
  if (replay.index >= h.length) replay.index = 0;
  replay.playing = true; tick(); renderControls();
}
function tick() {
  const h = getState().decisionHistory || [];
  if (!replay.playing || replay.index >= h.length) { stopReplay(); return; }
  narrate(h[replay.index]);
  replay.index += 1;
  draw(); renderControls();
  replay.timer = setTimeout(tick, 1400 / (replay.speed || 1));
}
function restartReplay() { stopReplay(); replay.index = 0; draw(); renderControls(); }
function setSpeed(m) { replay.speed = m; renderControls(); }

function narrate(step) {
  const m = metaFor(step);
  const tag = isRejected(step) ? "🚫 rejected" : isFinal(step) ? "⭐ final" : "✓";
  pushMessage("assistant", `🎬 ${m.label}: ${tag} — ${step.result || step.action}${step.input ? ` (${step.input})` : ""}`);
}

// ---- Canvas drawing ----
function drawSymbol(sym, x, y, r, fill, stroke, alpha) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = fill; ctx.strokeStyle = stroke; ctx.lineWidth = 2;
  ctx.beginPath();
  if (sym === "circle") ctx.arc(x, y, r, 0, Math.PI * 2);
  else if (sym === "square") ctx.rect(x - r, y - r, r * 2, r * 2);
  else if (sym === "diamond") { ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath(); }
  else if (sym === "hexagon") { for (let k = 0; k < 6; k++) { const a = Math.PI / 3 * k - Math.PI / 6; const px = x + r * Math.cos(a), py = y + r * Math.sin(a); k ? ctx.lineTo(px, py) : ctx.moveTo(px, py); } ctx.closePath(); }
  else if (sym === "star") { for (let k = 0; k < 10; k++) { const rr = k % 2 ? r * 0.45 : r; const a = Math.PI / 5 * k - Math.PI / 2; const px = x + rr * Math.cos(a), py = y + rr * Math.sin(a); k ? ctx.lineTo(px, py) : ctx.moveTo(px, py); } ctx.closePath(); }
  else ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill(); ctx.stroke();
  ctx.restore();
}

function draw() {
  if (!ctx || !canvas) return;
  const h = getState().decisionHistory || [];
  const W = canvas.clientWidth, H = canvas.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  if (!h.length) return;

  const nodes = layout(h);
  const revealed = replay.playing || replay.index > 0 ? replay.index : h.length;
  const padX = 40, padY = 36;
  const px = (nx) => padX + nx * (W - padX * 2);
  const py = (ny) => padY + ny * (H - padY * 2);

  // Edges first (sequence i-1 -> i). Animate: only draw up to revealed.
  for (let i = 1; i < nodes.length; i++) {
    if (i >= revealed) break;
    const a = nodes[i - 1], b = nodes[i];
    const onActive = !b.rejected;
    ctx.save();
    ctx.strokeStyle = b.rejected ? REJECT_COLOR : "#3a4a5a";
    ctx.lineWidth = onActive ? 2.5 : 1.5;
    ctx.globalAlpha = 0.8;
    if (b.rejected) ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(px(a.x), py(a.y)); ctx.lineTo(px(b.x), py(b.y)); ctx.stroke();
    ctx.restore();
  }

  // Nodes
  nodes.forEach((nd, i) => {
    const shown = i < revealed;
    const x = px(nd.x), y = py(nd.y);
    const isActive = replay.playing && i === replay.index - 1;
    const r = nd.final ? 16 : isActive ? 15 : 12;
    const fill = nd.rejected ? REJECT_COLOR : nd.final ? FINAL_COLOR : nd.meta.color;
    const stroke = isActive ? "#ffffff" : nd.final ? "#fff6c2" : "rgba(255,255,255,0.35)";
    drawSymbol(nd.meta.symbol, x, y, r, fill, stroke, shown ? 1 : 0.12);
    if (isActive) { drawSymbol(nd.meta.symbol, x, y, r + 6, "rgba(0,0,0,0)", "#ffffff", 0.5); }
    // Label
    ctx.save();
    ctx.globalAlpha = shown ? 1 : 0.15;
    ctx.fillStyle = "#cfe3f5"; ctx.font = "12px system-ui, sans-serif"; ctx.textBaseline = "middle";
    const label = (nd.step.result || nd.step.action || "").slice(0, 38);
    ctx.fillText(`${nd.rejected ? "🚫 " : nd.final ? "⭐ " : ""}${label}`, x + r + 10, y);
    ctx.fillStyle = "#5f7488"; ctx.font = "10px system-ui";
    ctx.fillText(nd.meta.label, x + r + 10, y + 13);
    ctx.restore();
  });
}

function renderControls() {
  const bar = document.getElementById("dg-controls");
  if (!bar) return;
  const h = getState().decisionHistory || [];
  const revealed = replay.playing || replay.index > 0 ? replay.index : h.length;
  const speedBtns = [0.5, 1, 2, 4].map((m) => `<button class="dg-ctrl ${replay.speed === m ? "on" : ""}" data-speed="${m}">${m}×</button>`).join("");
  bar.innerHTML = `
    <button class="dg-ctrl primary" id="dg-play">${replay.playing ? "⏸ Pause" : "▶ Play"}</button>
    <button class="dg-ctrl" id="dg-restart">⟲ Restart</button>
    <span class="dg-speed-label">Speed:</span>${speedBtns}
    <span class="dg-progress">${Math.min(revealed, h.length)}/${h.length}</span>`;
  bar.querySelector("#dg-play").addEventListener("click", () => (replay.playing ? stopReplay() : startReplay()));
  bar.querySelector("#dg-restart").addEventListener("click", restartReplay);
  bar.querySelectorAll("[data-speed]").forEach((b) => b.addEventListener("click", () => setSpeed(Number(b.dataset.speed))));
}

function render() {
  const root = document.getElementById("decision-scroll");
  if (!root) return;
  root.dataset.ready = "1";
  const h = getState().decisionHistory || [];
  if (!h.length) {
    root.innerHTML = `<div class="center-empty"><div class="big">🌳</div>
      <div>No decisions yet. As you work — pick a site, draw a boundary, generate &
      edit a building, optimize and compare — your design journey animates here.</div></div>`;
    return;
  }
  root.innerHTML = `
    <div class="dg-header">
      <h2>Design Evolution</h2>
      <p>${h.length}-step journey of this project. Press ▶ to replay it.</p>
      <div class="dg-controls" id="dg-controls"></div>
    </div>
    <div class="dg-canvas-wrap"><canvas id="dg-canvas"></canvas></div>`;
  canvas = root.querySelector("#dg-canvas");
  dpr = window.devicePixelRatio || 1;
  ctx = canvas.getContext("2d");
  // Size the canvas to fit the node count (taller graphs scroll).
  const wrap = root.querySelector(".dg-canvas-wrap");
  wrap.style.height = Math.max(360, h.length * 56) + "px";
  renderControls();
  requestAnimationFrame(draw);
}
