// Urban Context view — a futuristic "digital twin" of the 2 km city fabric around
// the confirmed site, rendered with Three.js. It draws:
//   • extruded OSM building footprints (the surrounding city)
//   • the road network, colour/style-coded by hierarchy
//   • parks / open spaces as glowing ground patches
//   • amenity markers (metro, schools, grocery, …) as billboarded pins
//   • the confirmed site highlighted, with labelled edges + vertices
//   • a 2 km context radius ring
// plus an interactive overlay: KPI score cards, the AI context report, and a
// Site Edge Intelligence HUD that appears when hovering near a site edge.
//
// Geometry/camera patterns follow viewerView.js so the two 3D views feel native.

import { getState, setState } from "../core/store.js";
import { SCORE_META, scoreColor, LAYER_DEFS } from "../core/overpass.js";

let scene, camera, renderer, rootGroup, raycaster, pointer, cam;
let inited = false;
let edgePickables = []; // line meshes for edge hover-picking
let lastCtxStamp = null;
let hudEl, scoresEl, reportEl;

function init() {
  if (inited) return;
  const container = document.getElementById("view-context");
  container.innerHTML = "";

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05080f);
  scene.fog = new THREE.Fog(0x05080f, 1200, 4200);

  camera = new THREE.PerspectiveCamera(48, container.clientWidth / container.clientHeight, 1, 20000);
  camera.up.set(0, 0, 1);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.domElement.style.touchAction = "none";
  container.appendChild(renderer.domElement);

  cam = {
    target: new THREE.Vector3(0, 0, 0),
    radius: 2600, theta: Math.PI * 0.25, phi: Math.PI * 0.34,
    dragging: false, moved: false, button: 0, lastX: 0, lastY: 0,
    minR: 200, maxR: 7000,
  };
  updateCamera();

  raycaster = new THREE.Raycaster();
  raycaster.params.Line = { threshold: 60 };
  pointer = new THREE.Vector2();

  renderer.domElement.addEventListener("contextmenu", (e) => e.preventDefault());
  renderer.domElement.addEventListener("pointerdown", onDown);
  renderer.domElement.addEventListener("pointermove", onMove);
  renderer.domElement.addEventListener("pointerup", onUp);
  renderer.domElement.addEventListener("pointerleave", hideEdgeHud);
  renderer.domElement.addEventListener("wheel", onWheel, { passive: false });

  rootGroup = new THREE.Group();
  scene.add(rootGroup);

  scene.add(new THREE.AmbientLight(0x8aa0c0, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 1.0);
  dir.position.set(800, 1200, 1600);
  scene.add(dir);
  const fill = new THREE.DirectionalLight(0x57f2e6, 0.35);
  fill.position.set(-900, -600, 400);
  scene.add(fill);

  buildOverlay(container);

  inited = true;
  animate();
  window.addEventListener("resize", resize);
}

// HTML overlay: scores rail (left), report (right), edge HUD (floating).
function buildOverlay(container) {
  const ov = document.createElement("div");
  ov.className = "ctx-overlay";
  ov.innerHTML = `
    <div class="ctx-scores" id="ctx-scores"></div>
    <div class="ctx-report" id="ctx-report"></div>
    <div class="ctx-edge-hud hidden" id="ctx-edge-hud"></div>
    <div class="ctx-legend" id="ctx-legend"></div>
    <div class="ctx-loading hidden" id="ctx-loading">
      <div class="ctx-scan"></div>
      <div class="ctx-loading-text">ANALYSING URBAN CONTEXT<span>·</span><span>·</span><span>·</span></div>
    </div>`;
  container.appendChild(ov);
  scoresEl = ov.querySelector("#ctx-scores");
  reportEl = ov.querySelector("#ctx-report");
  hudEl = ov.querySelector("#ctx-edge-hud");
}

function resize() {
  const c = document.getElementById("view-context");
  if (!renderer || !camera || !c) return;
  camera.aspect = c.clientWidth / c.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(c.clientWidth, c.clientHeight);
}

function animate() {
  requestAnimationFrame(animate);
  if (camera && cam) camera.lookAt(cam.target);
  if (renderer && scene && camera) renderer.render(scene, camera);
}

function updateCamera() {
  const r = cam.radius, s = Math.sin(cam.phi);
  camera.position.set(
    cam.target.x + r * s * Math.cos(cam.theta),
    cam.target.y + r * s * Math.sin(cam.theta),
    cam.target.z + r * Math.cos(cam.phi)
  );
}

function clearScene() {
  if (!rootGroup) return;
  while (rootGroup.children.length) {
    const c = rootGroup.children.pop();
    c.traverse?.((o) => { o.geometry?.dispose?.(); o.material?.dispose?.(); });
    c.geometry?.dispose?.();
    c.material?.dispose?.();
  }
  edgePickables = [];
}

function hexInt(hex) { return parseInt(hex.replace("#", "0x")); }

// ---- builders ----
function shapeFromFootprint(fp) {
  const shape = new THREE.Shape();
  shape.moveTo(fp[0][0], fp[0][1]);
  for (let i = 1; i < fp.length; i++) shape.lineTo(fp[i][0], fp[i][1]);
  return shape;
}

function addBuildings(buildings) {
  if (!buildings?.length) return;
  // batch into a few merged-ish groups by reusing material; keep meshes light
  const mat = new THREE.MeshStandardMaterial({
    color: 0x223451, metalness: 0.25, roughness: 0.55,
    transparent: true, opacity: 0.92, emissive: 0x0a1422, emissiveIntensity: 0.6,
  });
  for (const b of buildings) {
    if (!b.footprint || b.footprint.length < 3) continue;
    const geo = new THREE.ExtrudeGeometry(shapeFromFootprint(b.footprint), { depth: b.height, bevelEnabled: false });
    const mesh = new THREE.Mesh(geo, mat);
    rootGroup.add(mesh);
    // glowing rooftop edge for the digital-twin look
    const top = b.footprint.map((p) => new THREE.Vector3(p[0], p[1], b.height + 0.5));
    const edge = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(top),
      new THREE.LineBasicMaterial({ color: 0x2f5d7a, transparent: true, opacity: 0.5 })
    );
    rootGroup.add(edge);
  }
}

function addRoads(layers, visible) {
  for (const id of Object.keys(layers)) {
    const L = layers[id];
    if (L.kind !== "road" || !L.roads.length) continue;
    if (visible[id] === false) continue;
    const col = hexInt(L.style.color);
    const mat = new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.9, linewidth: L.style.width });
    for (const r of L.roads) {
      if (r.path.length < 2) continue;
      const pts = r.path.map((p) => new THREE.Vector3(p[0], p[1], 1.5));
      // dashed for tertiary/local via segment sampling
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat);
      rootGroup.add(line);
    }
  }
}

function addParks(layers, visible) {
  const L = layers["parks.parks"];
  if (!L || visible["parks.parks"] === false) return;
  const mat = new THREE.MeshBasicMaterial({ color: 0x1f7a44, transparent: true, opacity: 0.45, side: THREE.DoubleSide });
  for (const p of L.polys) {
    if (!p.poly || p.poly.length < 3) continue;
    const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shapeFromFootprint(p.poly)), mat);
    mesh.position.z = 0.6;
    rootGroup.add(mesh);
    const ring = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(p.poly.map((pt) => new THREE.Vector3(pt[0], pt[1], 0.8))),
      new THREE.LineBasicMaterial({ color: 0x57e08a, transparent: true, opacity: 0.8 })
    );
    rootGroup.add(ring);
  }
}

// amenity pins as upright glowing markers (billboard sprite-like via small cones)
function addAmenities(layers, visible) {
  for (const id of Object.keys(layers)) {
    const L = layers[id];
    if ((L.kind !== "amenity") || !L.points.length) continue;
    if (visible[id] === false) continue;
    const col = hexInt(L.style.color);
    const headMat = new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.7 });
    const stemMat = new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.7 });
    const H = id.startsWith("transport") ? 60 : 38;
    for (const p of L.points) {
      const stem = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(p.x, p.y, 0), new THREE.Vector3(p.x, p.y, H)]),
        stemMat
      );
      rootGroup.add(stem);
      const head = new THREE.Mesh(new THREE.SphereGeometry(9, 12, 12), headMat);
      head.position.set(p.x, p.y, H);
      rootGroup.add(head);
    }
  }
}

function addSite(ctx) {
  const b = ctx.siteBoundaryLocal;
  if (!b || b.length < 3) return;
  // glowing fill
  const fill = new THREE.Mesh(
    new THREE.ShapeGeometry(shapeFromFootprint(b)),
    new THREE.MeshBasicMaterial({ color: 0x28e0d0, transparent: true, opacity: 0.18, side: THREE.DoubleSide })
  );
  fill.position.z = 2;
  rootGroup.add(fill);
  // upward light beam column to make the site pop in the twin
  const colHeight = 220;
  const beam = new THREE.Mesh(
    new THREE.CylinderGeometry(4, 4, colHeight, 8, 1, true),
    new THREE.MeshBasicMaterial({ color: 0x57f2e6, transparent: true, opacity: 0.16, side: THREE.DoubleSide })
  );
  const c = ctx.siteCentroidLocal;
  beam.position.set(c[0], c[1], colHeight / 2);
  beam.rotation.x = Math.PI / 2;
  rootGroup.add(beam);

  // edges (pickable) + vertices
  for (const e of ctx.edges) {
    const pts = [new THREE.Vector3(e.a[0], e.a[1], 3), new THREE.Vector3(e.b[0], e.b[1], 3)];
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0x57f2e6, transparent: true, opacity: 0.95 })
    );
    line.userData = { edge: e };
    rootGroup.add(line);
    edgePickables.push(line);
  }
  // vertices
  const vmat = new THREE.MeshBasicMaterial({ color: 0xffffff });
  for (const p of b) {
    const v = new THREE.Mesh(new THREE.SphereGeometry(7, 10, 10), vmat);
    v.position.set(p[0], p[1], 3);
    rootGroup.add(v);
  }
}

function addRadiusRing(radius) {
  const pts = [];
  for (let i = 0; i <= 96; i++) {
    const a = (i / 96) * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 1));
  }
  const ring = new THREE.LineLoop(
    new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineDashedMaterial({ color: 0x7c7bff, dashSize: 40, gapSize: 26, transparent: true, opacity: 0.7 })
  );
  ring.computeLineDistances();
  rootGroup.add(ring);
  // ground disc
  const disc = new THREE.Mesh(
    new THREE.CircleGeometry(radius, 96),
    new THREE.MeshBasicMaterial({ color: 0x0a1326, transparent: true, opacity: 0.55, side: THREE.DoubleSide })
  );
  disc.position.z = -0.5;
  rootGroup.add(disc);
}

// ---- main render from store.context ----
function renderContext() {
  const ctx = getState().context;
  if (!ctx) return;
  init();
  clearScene();
  const visible = getState().contextVisible || {};

  addRadiusRing(ctx.radius);
  addParks(ctx.layers, visible);
  addRoads(ctx.layers, visible);
  addBuildings(ctx.buildings);
  addAmenities(ctx.layers, visible);
  addSite(ctx);

  // frame the whole context
  cam.target.set(ctx.siteCentroidLocal[0], ctx.siteCentroidLocal[1], 0);
  cam.radius = ctx.radius * 1.4;
  updateCamera();

  renderScores(ctx.scores);
  renderReport(ctx);
  renderLegend(ctx.layers, visible);
  lastCtxStamp = ctx.generatedAt;
}

function renderScores(scores) {
  if (!scoresEl || !scores) return;
  scoresEl.innerHTML = `<div class="ctx-panel-title">Context Scores</div>` +
    SCORE_META.map((sm) => {
      const v = scores[sm.key] ?? 0;
      const col = scoreColor(v);
      return `<div class="kpi-card" style="--kc:${col}">
        <div class="kpi-top"><span class="kpi-glyph">${sm.glyph}</span><span class="kpi-label">${sm.label}</span></div>
        <div class="kpi-value" style="color:${col}">${v}</div>
        <div class="kpi-bar"><i style="width:${v}%;background:${col}"></i></div>
      </div>`;
    }).join("");
}

function renderReport(ctx) {
  if (!reportEl) return;
  const r = ctx.report;
  reportEl.innerHTML = `
    <div class="ctx-panel-title">AI Context Report</div>
    <div class="ctx-report-body">
      <div class="crh">Urban Context Summary</div>
      ${r.edgeLines.map((e) => `
        <div class="cr-edge">
          <div class="cr-edge-title">${e.title}</div>
          <ul>${e.items.map((it) => `<li>${it}</li>`).join("")}</ul>
        </div>`).join("")}
      <div class="crh">Opportunities</div>
      <ul class="cr-opps">${r.opportunities.map((o) => `<li>${o}</li>`).join("")}</ul>
      ${ctx.note ? `<div class="cr-note">⚠ ${ctx.note} — sample context shown.</div>` : ""}
    </div>`;
}

function renderLegend(layers, visible) {
  const el = document.getElementById("ctx-legend");
  if (!el) return;
  const roadIds = Object.keys(layers).filter((id) => layers[id].kind === "road");
  el.innerHTML = `<div class="ctx-legend-title">Road Network</div>` +
    roadIds.map((id) => {
      const L = layers[id];
      const off = visible[id] === false;
      return `<div class="lg-row${off ? " off" : ""}"><span class="lg-swatch" style="background:${L.style.color}"></span>${L.label} <b>${L.roads.length}</b></div>`;
    }).join("");
}

// re-apply visibility without rebuilding everything heavy: simplest is a full
// rebuild (scene isn't huge). Called by the explorer toggles.
export function refreshVisibility() {
  if (getState().context) renderContext();
}

// ---- edge intelligence hover ----
function onDown(e) { cam.dragging = true; cam.moved = false; cam.button = e.button; cam.lastX = e.clientX; cam.lastY = e.clientY; }
function onUp() { cam.dragging = false; }
function onMove(e) {
  if (cam.dragging) {
    const dx = e.clientX - cam.lastX, dy = e.clientY - cam.lastY;
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) cam.moved = true;
    if (cam.button === 2) {
      const s = Math.max(cam.radius * 0.0016, 0.4);
      cam.target.x -= dx * s; cam.target.y += dy * s;
    } else {
      cam.theta -= dx * 0.006;
      cam.phi = Math.min(Math.PI - 0.08, Math.max(0.08, cam.phi + dy * 0.006));
    }
    cam.lastX = e.clientX; cam.lastY = e.clientY;
    updateCamera();
    hideEdgeHud();
  } else {
    edgeHover(e);
  }
}
function onWheel(e) {
  e.preventDefault();
  cam.radius = Math.min(cam.maxR, Math.max(cam.minR, cam.radius * (e.deltaY > 0 ? 1.08 : 0.92)));
  updateCamera();
}

function edgeHover(e) {
  if (!edgePickables.length) return hideEdgeHud();
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(edgePickables, false);
  if (!hits.length) return hideEdgeHud();
  showEdgeHud(hits[0].object.userData.edge, e.clientX, e.clientY);
}

const HUD_ORDER = ["Metro", "Train Station", "Bus Stop", "Park", "Primary Road", "School", "University", "Grocery Store", "Shopping", "Hospital"];
function showEdgeHud(edge, x, y) {
  if (!hudEl || !edge) return;
  const rows = HUD_ORDER
    .filter((k) => edge.nearest[k] != null)
    .slice(0, 5)
    .map((k) => `<div class="hud-row"><span>Nearest ${k}</span><b>${edge.nearest[k]}m</b></div>`)
    .join("");
  hudEl.innerHTML = `<div class="hud-title">Edge ${edge.id} · ${edge.direction}</div>${rows || '<div class="hud-row">No nearby features</div>'}`;
  hudEl.style.left = Math.min(x + 16, window.innerWidth - 230) + "px";
  hudEl.style.top = (y + 12) + "px";
  hudEl.classList.remove("hidden");
}
function hideEdgeHud() { hudEl?.classList.add("hidden"); }

// loading shimmer toggled by the orchestrator flow
export function setLoading(on) {
  init();
  const el = document.getElementById("ctx-loading");
  if (el) el.classList.toggle("hidden", !on);
}

// ---------------------------------------------------------------------------
export function activate() {
  init();
  setTimeout(resize, 60);
  const ctx = getState().context;
  if (ctx && ctx.generatedAt !== lastCtxStamp) renderContext();
  else if (ctx && !rootGroup?.children.length) renderContext();
}

export async function onAction(payload) {
  init();
  if (payload.action === "render_context") {
    setLoading(false);
    renderContext();
  } else if (payload.action === "context_loading") {
    setLoading(true);
  }
}

// debug probe for verification
window.__ctxObjectCount = () => (rootGroup ? rootGroup.children.length : 0);
