// 3D massing viewer (Three.js): renders generated buildings inside the confirmed
// site boundary, supports orbit/pan/zoom, hover tooltips on building parts, click
// selection with highlight, and eye-toggle visibility for optimization options.
//
// Geometry techniques (ExtrudeGeometry from footprint, orbit camera, raycast
// part classification) are adapted from the legacy frontend/viewer.js.

import { getState, setState, pushMessage } from "../core/store.js";

let scene, camera, renderer, rootGroup, raycaster, pointer, cam;
let inited = false;
let optionMeshes = [];
let vertexMeshes = []; // footprint vertex markers for vertex-level manipulation
let scoreCardSprites = []; // floating score cards above each optimized option
let selectedMesh = null;
let lastOptions = [];
let lastSite = null;
let ghostCandidates = []; // explored-but-not-selected options for the "solution space"
let showGhosts = true;
let showScoreCards = true; // floating per-option score cards in the multi-option preview
let showVertexMarkers = false; // white vertex spheres + pin lines + edge labels (off; clutter)

// Visibility is driven by the store's `visibleOptionIds` (single source of truth).
// `null` there means "no filter / show all"; a Set (even empty) means show exactly
// those ids. This avoids the viewer and explorer ever disagreeing about what's on.
function currentVisibleIds() {
  const v = getState().visibleOptionIds;
  return v instanceof Set ? v : null;
}

const tooltip = () => document.getElementById("part-tooltip");

function init() {
  if (inited) return;
  const container = document.getElementById("view-viewer");
  container.innerHTML = "";

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070b14);
  scene.fog = new THREE.Fog(0x070b14, 340, 1600);

  camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 5000);
  camera.up.set(0, 0, 1);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.domElement.style.touchAction = "none";
  container.appendChild(renderer.domElement);

  cam = {
    target: new THREE.Vector3(0, 0, 0),
    radius: 220, theta: Math.PI * 0.25, phi: Math.PI * 0.32,
    dragging: false, moved: false, button: 0, lastX: 0, lastY: 0,
    minR: 20, maxR: 900,
  };
  updateCamera();

  raycaster = new THREE.Raycaster();
  pointer = new THREE.Vector2();

  renderer.domElement.addEventListener("contextmenu", (e) => e.preventDefault());
  renderer.domElement.addEventListener("pointerdown", onDown);
  renderer.domElement.addEventListener("pointermove", onMove);
  renderer.domElement.addEventListener("pointerup", onUp);
  renderer.domElement.addEventListener("pointerleave", () => hideTooltip());
  renderer.domElement.addEventListener("wheel", onWheel, { passive: false });

  rootGroup = new THREE.Group();
  scene.add(rootGroup);

  scene.add(new THREE.AmbientLight(0xffffff, 0.85));
  const dir = new THREE.DirectionalLight(0xffffff, 1.15);
  dir.position.set(120, 160, 200);
  scene.add(dir);

  const grid = new THREE.GridHelper(400, 40, 0x2a4a6e, 0x14233c);
  grid.rotation.x = Math.PI / 2;
  scene.add(grid);

  // Viewport view toolbar (Rhino-style): Top / Iso / Front + reset. Sits top-left of
  // the 3D window. Each snaps the orbit camera to a preset angle.
  const bar = document.createElement("div");
  bar.id = "view-toolbar";
  bar.innerHTML = `
    <button data-view="iso" class="vt-btn active" title="Isometric view">◈ Iso</button>
    <button data-view="top" class="vt-btn" title="Top-down view">▣ Top</button>
    <button data-view="front" class="vt-btn" title="Front (north) view">▦ Front</button>
    <button data-view="reset" class="vt-btn" title="Reset / fit">⟲ Fit</button>`;
  container.appendChild(bar);
  bar.addEventListener("click", (e) => {
    const b = e.target.closest(".vt-btn"); if (!b) return;
    bar.querySelectorAll(".vt-btn").forEach((x) => x.classList.toggle("active", x === b && b.dataset.view !== "reset"));
    setView(b.dataset.view);
  });

  inited = true;
  animate();
  window.addEventListener("resize", resize);
}

// Snap the orbit camera to a named preset (keeps the current target + radius).
function setView(name) {
  if (!cam) return;
  if (name === "top") {            // straight down (plan view): phi→0
    cam.theta = -Math.PI / 2; cam.phi = 0.001;
  } else if (name === "front") {   // looking from the south toward north, slight tilt
    cam.theta = -Math.PI / 2; cam.phi = Math.PI / 2 - 0.12;
  } else if (name === "iso") {     // the default 3/4 isometric
    cam.theta = Math.PI * 0.25; cam.phi = Math.PI * 0.32;
  } else if (name === "reset") {
    cam.theta = Math.PI * 0.25; cam.phi = Math.PI * 0.32;
    const s = lastSite, opts = lastOptions;
    if (s?.boundary?.length >= 3) centerCameraOn(s.boundary, opts || []);
    return;
  }
  updateCamera();
}

function resize() {
  const c = document.getElementById("view-viewer");
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

// ---- geometry helpers ----
// Build a THREE.Shape from an outer ring, plus optional HOLES (courtyards/patios).
// A hole is a ring [[x,y],...]; it's added as a THREE.Path so ExtrudeGeometry/
// ShapeGeometry carve a real void — this is how an architectural courtyard shows.
function footprintShape(fp, holes) {
  const shape = new THREE.Shape();
  if (!fp || !fp.length) return shape;
  shape.moveTo(fp[0][0], fp[0][1]);
  for (let i = 1; i < fp.length; i++) shape.lineTo(fp[i][0], fp[i][1]);
  shape.lineTo(fp[0][0], fp[0][1]);
  for (const hole of holes || []) {
    if (!hole || hole.length < 3) continue;
    const path = new THREE.Path();
    path.moveTo(hole[0][0], hole[0][1]);
    for (let i = 1; i < hole.length; i++) path.lineTo(hole[i][0], hole[i][1]);
    path.lineTo(hole[0][0], hole[0][1]);
    shape.holes.push(path);
  }
  return shape;
}

// Keep only the holes whose centroid lies INSIDE the given plate footprint, so a
// courtyard void is carved only from plates that actually contain it (a small wing
// plate sitting above the base must not try to cut the building's courtyard — that
// produced the malformed/seamed facade glitch after a per-wing manipulation).
function _holesInside(holes, fp) {
  if (!holes || !holes.length) return holes;
  return holes.filter((h) => {
    if (!h || h.length < 3) return false;
    const cx = h.reduce((s, p) => s + +p[0], 0) / h.length;
    const cy = h.reduce((s, p) => s + +p[1], 0) / h.length;
    return _pointInRing(cx, cy, fp);
  });
}

function _pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = +ring[i][0], yi = +ring[i][1], xj = +ring[j][0], yj = +ring[j][1];
    if (((yi > y) !== (yj > y)) && (x < ((xj - xi) * (y - yi)) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}

function fpBounds(fp) {
  const xs = fp.map((p) => +p[0]), ys = fp.map((p) => +p[1]);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

function clearScene() {
  if (!rootGroup) return;
  while (rootGroup.children.length) {
    const c = rootGroup.children.pop();
    c.geometry?.dispose();
    c.material?.dispose();
  }
  optionMeshes = [];
  selectedMesh = null;
  vertexMeshes = [];
  scoreCardSprites = [];
}

function drawBoundary(boundary) {
  if (!boundary || boundary.length < 3) return;
  const pts = boundary.map((p) => new THREE.Vector3(p[0], p[1], 0.05));
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([...pts, pts[0]]),
    new THREE.LineBasicMaterial({ color: 0x28e0d0, transparent: true, opacity: 0.95 })
  );
  rootGroup.add(line);
  // soft fill
  const fill = new THREE.Mesh(
    new THREE.ShapeGeometry(footprintShape(boundary)),
    new THREE.MeshBasicMaterial({ color: 0x0e2a44, transparent: true, opacity: 0.25, side: THREE.DoubleSide, depthWrite: false })
  );
  fill.position.z = 0.02;
  rootGroup.add(fill);
  // SETBACK line: the buildable area = site inset inward. Drawn as a dotted AMBER line
  // so the user sees exactly where the building may sit (anything between this line and
  // the site edge is the required setback margin).
  drawSetback(boundary);
}

// Inset a (roughly convex) polygon inward by `margin` metres — each vertex moved along
// the average of its two adjacent edge inward-normals. Good enough for the rectangular
// /simple sites here; degenerate results are skipped.
// Proper polygon inset (miter): offset every edge inward by `margin`, then intersect
// each pair of adjacent offset edges to get the new corner. Robust on skewed quads
// (no per-corner bisector approximation → no glitching). Handles a duplicate closing
// vertex and any winding.
function insetRing(ring, margin) {
  // 1) drop a duplicate closing point (first == last) — that degenerate edge was the
  //    source of the broken corner on one side.
  let r = ring.map((p) => [Number(p[0]), Number(p[1])]);
  if (r.length >= 2) {
    const a = r[0], b = r[r.length - 1];
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6) r = r.slice(0, -1);
  }
  const n = r.length;
  if (n < 3) return null;

  // 2) winding → inward normal direction
  let area = 0;
  for (let i = 0; i < n; i++) { const a = r[i], b = r[(i + 1) % n]; area += a[0] * b[1] - b[0] * a[1]; }
  const ccw = area > 0;
  const inwardNormal = (ux, uy) => (ccw ? [-uy, ux] : [uy, -ux]); // unit edge dir → inward unit normal

  // 3) build each edge offset inward by `margin`: a point on the offset line + its direction
  const lines = [];
  for (let i = 0; i < n; i++) {
    const a = r[i], b = r[(i + 1) % n];
    let dx = b[0] - a[0], dy = b[1] - a[1];
    const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
    const [nx, ny] = inwardNormal(dx, dy);
    lines.push({ px: a[0] + nx * margin, py: a[1] + ny * margin, dx, dy });
  }

  // 4) corner i = intersection of offset edge (i-1) and offset edge (i)
  const out = [];
  for (let i = 0; i < n; i++) {
    const L1 = lines[(i - 1 + n) % n], L2 = lines[i];
    const det = L1.dx * (-L2.dy) - L1.dy * (-L2.dx);
    if (Math.abs(det) < 1e-9) { out.push([L2.px, L2.py]); continue; } // parallel → fall back
    const rx = L2.px - L1.px, ry = L2.py - L1.py;
    const t = (rx * (-L2.dy) - ry * (-L2.dx)) / det;
    out.push([L1.px + L1.dx * t, L1.py + L1.dy * t]);
  }

  // 5) sanity: the inset must be smaller than the source (didn't blow up); else skip
  const bb = (rr) => { const xs = rr.map((p) => p[0]), ys = rr.map((p) => p[1]); return [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]; };
  const o = bb(out), s = bb(r);
  if (o[0] < s[0] - 0.5 || o[1] > s[1] + 0.5 || o[2] < s[2] - 0.5 || o[3] > s[3] + 0.5) return null;
  return out;
}

function drawSetback(boundary) {
  // Draw the dashed setback line at the SAME inset the BACKEND enforces (residential
  // rules: 5 m front / 3 m sides), so the line MATCHES where the building is actually
  // allowed to go. Previously this used a dynamic 12%-of-span margin (up to 9 m), which
  // drew the line FURTHER in than the real setback — making a correctly-placed building
  // look like it crossed the line ("move away from noise goes outside the setback").
  const margin = 5;   // matches setback_rules residential max(front,rear,side) ≈ 5 m
  const inset = insetRing(boundary.map((p) => [Number(p[0]), Number(p[1])]), margin);
  if (!inset) return;
  // dotted amber line (LineDashed needs computeLineDistances)
  const pts = inset.map((p) => new THREE.Vector3(p[0], p[1], 0.12));
  pts.push(pts[0].clone());
  const geom = new THREE.BufferGeometry().setFromPoints(pts);
  const mat = new THREE.LineDashedMaterial({ color: 0xffb454, transparent: true, opacity: 0.9, dashSize: 3.2, gapSize: 2.2, linewidth: 1 });
  const dl = new THREE.Line(geom, mat);
  dl.computeLineDistances();
  rootGroup.add(dl);
}

function drawOption(opt, color, opacity = 0.95, selectable = true) {
  if (!opt || !opt.footprint || opt.footprint.length < 3) return;
  const mat = new THREE.MeshStandardMaterial({ color, metalness: 0.1, roughness: 0.68, transparent: true, opacity });

  // Per-floor plate stack: extrude EACH plate at its own Z, so floor-level edits
  // (moved bottom floors, a single taller wing) actually show. Falls back to a
  // single extrusion when the building has no plate stack.
  const plates = opt.floor_plates;
  if (Array.isArray(plates) && plates.length) {
    // Sort by base height so plates stack bottom-up with no z-fighting, and extrude
    // each with a TINY overlap into the plate above (epsilon) so the per-floor seams
    // don't show as gaps on the facade. Holes (courtyards) are only applied to a
    // plate when its footprint actually CONTAINS the hole — a wing plate with a
    // small footprint must NOT carry the building's courtyard hole (that was the
    // glitch: a malformed cut producing a notched/seamed facade).
    const sorted = [...plates].sort((a, b) => (a.z_base || 0) - (b.z_base || 0));
    const SEAM = 0.05; // 5cm overlap to weld floors visually
    for (let i = 0; i < sorted.length; i++) {
      const p = sorted[i];
      const fp = (p.footprint || []).map((q) => [Number(q[0]), Number(q[1])]);
      if (fp.length < 3) continue;
      // Prefer the plate's OWN holes (the backend now writes the courtyard into each
      // plate). Fall back to centroid-filtering the building holes only when the plate
      // has none. This fixes the "courtyard not visible" bug: on a U/notched plate the
      // courtyard centroid can fall outside the plate ring, so _holesInside wrongly
      // dropped it — but the plate's own holes are authoritative.
      const holes = (Array.isArray(p.holes) && p.holes.length)
        ? p.holes.map((h) => h.map((q) => [Number(q[0]), Number(q[1])]))
        : _holesInside(opt.holes, fp);
      const depth = (p.height || 3) + (i < sorted.length - 1 ? SEAM : 0);
      const geo = new THREE.ExtrudeGeometry(footprintShape(fp, holes), { depth, bevelEnabled: false });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.z = p.z_base || 0;
      mesh.userData = { optionId: opt.option_id, option: opt, level: p.level };
      rootGroup.add(mesh);
      if (selectable && (p.level === 0 || i === 0)) optionMeshes.push(mesh); // pick on the base plate
    }
    return;
  }

  const geo = new THREE.ExtrudeGeometry(footprintShape(opt.footprint, opt.holes), { depth: opt.height || 10, bevelEnabled: false });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.userData = { optionId: opt.option_id, option: opt };
  rootGroup.add(mesh);
  if (selectable) optionMeshes.push(mesh);
}

// Ghost shape: a faint translucent massing for an explored candidate, plus a
// glowing wireframe edge. Rejected = red tint, explored-valid = cyan tint.
function drawGhost(opt, rejected) {
  if (!opt || !opt.footprint || opt.footprint.length < 3) return;
  const color = rejected ? 0xff5f6d : 0x7c7bff;
  const geo = new THREE.ExtrudeGeometry(footprintShape(opt.footprint), { depth: opt.height || 10, bevelEnabled: false });
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: rejected ? 0.05 : 0.08, depthWrite: false,
  }));
  rootGroup.add(mesh);
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geo),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity: rejected ? 0.18 : 0.3 })
  );
  rootGroup.add(edges);
}

function centerCameraOn(boundary, options) {
  const all = [];
  (boundary || []).forEach((p) => all.push(p));
  (options || []).forEach((o) => (o.footprint || []).forEach((p) => all.push(p)));
  if (!all.length) return;
  const b = fpBounds(all);
  cam.target.set((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2, 5);
  const span = Math.max(b.maxX - b.minX, b.maxY - b.minY, 30);
  cam.radius = span * 2.1;
  updateCamera();
}

// ---- main render ----
export function renderScene(site, options, { fitCamera = true } = {}) {
  init();
  lastSite = site || lastSite;
  lastOptions = options && options.length ? options : lastOptions;
  clearScene();

  const boundary = lastSite?.boundary || [];
  // Urban context backdrop (roads + nearby OSM buildings) behind the massing, so
  // manipulation happens IN context. Same metric frame now (see resolveSite), so it
  // aligns with the building. Drawn faint; skipped if no context analyzed.
  drawContextBackdrop();
  drawBoundary(boundary);

  // Ghost shapes: the explored solution space behind the chosen options.
  if (showGhosts && ghostCandidates.length) {
    const bestIds = new Set((lastOptions || []).map((o) => o.option_id));
    ghostCandidates.forEach((g) => {
      if (bestIds.has(g.option_id)) return;
      drawGhost(g, g.rejected);
    });
  }

  // Options to draw: the optimization options if present, otherwise the placed
  // buildings themselves (so a freshly GENERATED building is visible AND pickable
  // for the Move/Rotate/Scale tools — without this the scene only had the site).
  let drawList = lastOptions || [];
  let isBuildingFallback = false;
  if (!drawList.length) {
    drawList = buildingsToDrawables(getState().buildings || []);
    lastOptions = drawList.length ? drawList : lastOptions;
    isBuildingFallback = drawList.length > 0;
  }

  // The visibility filter (eye toggles) applies to OPTIMIZATION options. When we're
  // drawing the placed building itself (no options yet), the building's id is not in
  // visibleOptionIds, so applying the filter would hide it — always show it instead.
  // This was the "building invisible after generate/move" bug.
  const filter = isBuildingFallback ? null : currentVisibleIds();
  const shown = (drawList || []).filter((o) => filter === null || filter.has(o.option_id));
  const selectedId = getState().selectedOptionId;
  const hasSelection = shown.some((o) => o.option_id === selectedId);
  // When previewing MULTIPLE options that share the site, draw ONE prominently and the
  // rest as faint ghosts so overlapping placements don't read as a single broken/seamed
  // mass. The prominent one is the selected option, or (before any selection) the first
  // (best-ranked) option. Selecting another via its score card / eye toggle promotes it.
  const multi = shown.length > 1 && !isBuildingFallback;
  const prominentId = selectedId && shown.some((o) => o.option_id === selectedId)
    ? selectedId
    : (shown[0] && shown[0].option_id);
  shown.forEach((opt) => {
    const isProminent = opt.option_id === prominentId;
    if (!multi) {
      // Single building (manual edit) — draw solid.
      drawOption(opt, 0x28e0d0, 1);
    } else if (isProminent) {
      drawOption(opt, 0x28e0d0, 0.95);   // the highlighted option: solid cyan
    } else {
      drawOption(opt, 0x7c7bff, 0.18);   // alternatives: faint violet ghosts (no seam)
    }
  });

  // Floating score cards: when previewing MULTIPLE optimization options on the site,
  // show each option's strategy name + score above it so the user can read the whole
  // optimized set at a glance (without hovering each one). Skipped for a single placed
  // building (nothing to compare) and when scoreCards are explicitly toggled off.
  if (!isBuildingFallback && shown.length > 1 && showScoreCards) {
    drawScoreCards(shown, prominentId);
  }

  // Vertex/edge markers (white spheres + pin lines + N/S/E/W tags) are OFF by default
  // — they cluttered the building and aren't needed for the prompt-driven workflow.
  // Re-enable for vertex-level manipulation with `window.__vertexMarkers(true)`.
  const isMultiOptionPreview = !isBuildingFallback && shown.length > 1;
  const target = shown.find((o) => o.option_id === selectedId) || shown[0];
  if (showVertexMarkers && !isMultiOptionPreview && target && target.footprint && target.footprint.length >= 3) {
    drawVertices(target.footprint, target.height || 12);
  }

  // Compass labels (N/S/E/W) around the scene so the user can orient manipulation
  // commands — "move north", "align to the east edge", "rotate to face south".
  drawCompass(boundary, shown);

  if (fitCamera) centerCameraOn(boundary, shown);
  highlightSelected(getState().selectedOptionId);
}

// Place N / S / E / W text sprites just outside the site, in the metric frame
// (+y = true north, +x = east). They sit flat-ish in the world so they read as
// ground-plane compass markers and always face the camera (sprites billboard).
function drawCompass(boundary, shown) {
  if (!rootGroup) return;
  // Determine the world extent from the site (or the drawn options as fallback).
  const pts = [];
  (boundary || []).forEach((p) => pts.push([Number(p[0]), Number(p[1])]));
  (shown || []).forEach((o) => (o.footprint || o.boundary || []).forEach((p) => pts.push([Number(p[0]), Number(p[1])])));
  if (pts.length < 3) return;
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const ext = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) || 60;
  const R = ext * 0.62 + 18;        // ring radius just outside the site
  const dirs = [
    { t: "N", x: cx,     y: cy + R, c: "#57f2e6" },
    { t: "S", x: cx,     y: cy - R, c: "#8b97ad" },
    { t: "E", x: cx + R, y: cy,     c: "#8b97ad" },
    { t: "W", x: cx - R, y: cy,     c: "#8b97ad" },
  ];
  dirs.forEach((d) => {
    const spr = makeCompassSprite(d.t, d.c);
    if (!spr) return;
    spr.position.set(d.x, d.y, 2);
    rootGroup.add(spr);
  });
}

function makeCompassSprite(letter, color) {
  try {
    const S = 96;
    const cv = document.createElement("canvas");
    cv.width = S; cv.height = S;
    const ctx = cv.getContext("2d");
    // subtle ring + glow so it reads as a marker, not stray text
    ctx.beginPath();
    ctx.arc(S / 2, S / 2, S / 2 - 6, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(10,18,28,0.55)";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    ctx.globalAlpha = letter === "N" ? 0.95 : 0.5;
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.fillStyle = color;
    ctx.font = `bold ${letter === "N" ? 52 : 44}px system-ui, sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(letter, S / 2, S / 2 + 2);
    const tex = new THREE.CanvasTexture(cv);
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
    const sz = letter === "N" ? 16 : 13;     // N a touch bigger (it's the reference)
    spr.scale.set(sz, sz, 1);
    spr.userData = { compass: true };
    return spr;
  } catch {
    return null;
  }
}

// Draw a faint urban-context backdrop (roads + nearby OSM buildings) from
// store.context, in the building's metric frame. Lets the user manipulate the
// massing while seeing the surrounding city.
function drawContextBackdrop() {
  const ctx = getState().context;
  if (!ctx || !ctx.layers) return;
  // roads
  for (const L of Object.values(ctx.layers)) {
    if (L.kind !== "road" || !L.roads?.length) continue;
    const col = parseInt(String(L.style?.color || "#33506e").replace("#", "0x"));
    const mat = new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.5 });
    for (const r of L.roads) {
      if (!r.path || r.path.length < 2) continue;
      rootGroup.add(new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(r.path.map((p) => new THREE.Vector3(p[0], p[1], 0.1))),
        mat
      ));
    }
  }
  // nearby OSM buildings (low, dim) for spatial reference
  const bmat = new THREE.MeshStandardMaterial({ color: 0x16263c, transparent: true, opacity: 0.55, roughness: 0.8 });
  for (const b of (ctx.buildings || [])) {
    if (!b.footprint || b.footprint.length < 3) continue;
    try {
      rootGroup.add(new THREE.Mesh(
        new THREE.ExtrudeGeometry(footprintShape(b.footprint), { depth: Math.min(b.height || 8, 40), bevelEnabled: false }),
        bmat
      ));
    } catch { /* skip bad footprint */ }
  }
}

// 8-point compass from a vector in the metric frame (+y = true north).
// Edge side from the centroid→midpoint vector in the metric frame (x=east, y=north),
// using the SAME convention as overpass.sideLabelFromVector: atan2(vy, vx), 0=East,
// 90=North. So viewer edge tags match the context twin + report + tooltip exactly.
function _dirLabel(vx, vy) {
  if (vx === 0 && vy === 0) return "Center";
  const a = ((Math.atan2(vy, vx) * 180) / Math.PI + 360) % 360;
  const S = ["East", "Northeast", "North", "Northwest", "West", "Southwest", "South", "Southeast"];
  return S[Math.round(a / 45) % 8];
}

// Draw building footprint vertices (numbered spheres) + per-edge direction tags so
// the user can see and reference each corner/edge for vertex-level manipulation.
function drawVertices(fp, height) {
  vertexMeshes = [];
  const z = (height || 12) + 2;
  const cx = fp.reduce((s, p) => s + p[0], 0) / fp.length;
  const cy = fp.reduce((s, p) => s + p[1], 0) / fp.length;
  fp.forEach((p, i) => {
    const v = new THREE.Mesh(
      new THREE.SphereGeometry(2.5, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0xffffff })
    );
    v.position.set(p[0], p[1], z);
    v.userData = { vertexIndex: i };
    rootGroup.add(v);
    vertexMeshes.push(v);
    // small pin down to the footprint
    rootGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(p[0], p[1], 0.1), new THREE.Vector3(p[0], p[1], z)]),
      new THREE.LineBasicMaterial({ color: 0x57f2e6, transparent: true, opacity: 0.4 })
    ));
  });
  // edge midpoint markers, tagged by true geographic side (midpoint vs centroid).
  for (let i = 0; i < fp.length; i++) {
    const a = fp[i], b = fp[(i + 1) % fp.length];
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    const dir = _dirLabel(mx - cx, my - cy);
    const tag = makeTextSprite(`${dir}`);
    if (tag) { tag.position.set(mx, my, z + 4); rootGroup.add(tag); }
  }
}

// A small canvas-text sprite (cheap label) — used for edge direction tags.
function makeTextSprite(text) {
  try {
    const cv = document.createElement("canvas");
    cv.width = 256; cv.height = 64;
    const ctx = cv.getContext("2d");
    ctx.font = "bold 30px monospace";
    ctx.fillStyle = "#57f2e6";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 128, 32);
    const tex = new THREE.CanvasTexture(cv);
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
    spr.scale.set(18, 4.5, 1);
    return spr;
  } catch {
    return null;
  }
}

// A two-line "score card" sprite that floats above an optimized option: the
// strategy name (e.g. "Highest View") on top, the score + a key metric below.
// This is what makes the on-site preview readable WITHOUT hovering every shape.
function makeScoreCardSprite(opt, accent = "#57f2e6") {
  try {
    const name = opt.strategy_name || (opt.shape_type || "Option").toString();
    const score = Number(opt.score ?? opt.combined_score);
    const scoreTxt = Number.isFinite(score) ? `Score ${score.toFixed(0)}` : "Score —";
    // one extra headline metric if available (e.g. view/solar/noise)
    const hm = opt.headline_metrics || opt.objective_scores || {};
    const key = Object.keys(hm)[0];
    const metricTxt = key ? `${key.replace(/_/g, " ")} ${Math.round(Number(hm[key]))}` : "";

    const W = 320, H = 120;
    const cv = document.createElement("canvas");
    cv.width = W; cv.height = H;
    const ctx = cv.getContext("2d");
    // rounded card background
    ctx.fillStyle = "rgba(10,18,28,0.82)";
    const r = 16;
    ctx.beginPath();
    ctx.moveTo(r, 0); ctx.lineTo(W - r, 0); ctx.quadraticCurveTo(W, 0, W, r);
    ctx.lineTo(W, H - r); ctx.quadraticCurveTo(W, H, W - r, H);
    ctx.lineTo(r, H); ctx.quadraticCurveTo(0, H, 0, H - r);
    ctx.lineTo(0, r); ctx.quadraticCurveTo(0, 0, r, 0); ctx.closePath();
    ctx.fill();
    ctx.lineWidth = 3; ctx.strokeStyle = accent; ctx.stroke();
    // name
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 28px system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(name.length > 18 ? name.slice(0, 17) + "…" : name, W / 2, 34);
    // score + metric
    ctx.fillStyle = accent;
    ctx.font = "bold 26px system-ui, sans-serif";
    ctx.fillText(scoreTxt, W / 2, 70);
    if (metricTxt) {
      ctx.fillStyle = "#9fb4c8";
      ctx.font = "22px system-ui, sans-serif";
      ctx.fillText(metricTxt, W / 2, 99);
    }
    const tex = new THREE.CanvasTexture(cv);
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
    spr.scale.set(34, 12.75, 1); // world units; readable but not huge
    spr.userData = { optionId: opt.option_id, scoreCard: true };
    return spr;
  } catch {
    return null;
  }
}

// Place a score card above each shown option at its centroid + top height. The
// prominent (selected/best) option's card is shown solid; the rest are dimmed and
// nudged up so the overlapping cards don't pile on top of each other.
function drawScoreCards(options, prominentId) {
  const selectedId = getState().selectedOptionId;
  const prom = prominentId || (options[0] && options[0].option_id);
  (options || []).forEach((opt, i) => {
    const fp = opt.footprint || [];
    if (fp.length < 3) return;
    const cx = fp.reduce((s, p) => s + p[0], 0) / fp.length;
    const cy = fp.reduce((s, p) => s + p[1], 0) / fp.length;
    const isProminent = opt.option_id === (selectedId || prom);
    const spr = makeScoreCardSprite(opt, isProminent ? "#28e0d0" : "#6c7a90");
    if (!spr) return;
    // Stagger non-prominent cards upward in a tier so they don't overlap each other.
    const top = (opt.height || 12) + 10 + (isProminent ? 6 : (i % 4) * 9);
    spr.position.set(cx, cy, top);
    if (!isProminent) spr.material.opacity = 0.55;
    spr.renderOrder = isProminent ? 1000 : 999;
    rootGroup.add(spr);
    scoreCardSprites.push(spr);
  });
}

// Map placed buildings (from the explorer) into drawable/pickable option objects
// so a generated building (before any optimization) is shown and selectable.
function buildingsToDrawables(buildings) {
  return (buildings || [])
    .map((b) => {
      const fp = (b.boundary || b.building_boundary || []).map((p) => [Number(p[0]), Number(p[1])]);
      if (fp.length < 3) return null;
      return {
        option_id: b.building_id || b.geometry_id || "building",
        building_id: b.building_id || b.geometry_id,
        footprint: fp,
        // Courtyard / patio voids carved by the architectural-intent layer, so the
        // extruded massing shows the opening instead of a solid block.
        holes: (b.holes || []).map((h) => h.map((p) => [Number(p[0]), Number(p[1])])),
        // Per-floor plate stack (each plate extrudes at its own Z) so floor-level
        // edits — moved bottom floors, a single taller wing — render correctly.
        floor_plates: b.floor_plates || [],
        height: b.height_m || 12,
        floors: b.height_m ? Math.max(1, Math.round(b.height_m / 3)) : 0,
        shape_type: b.building_type || b.shape_type || "building",
        // REAL wing roles from the backend geometry (e.g. ['main_bar'] for an I-shape,
        // ['left','connector','right'] for an H). The tooltip uses these so it never
        // labels a part a "wing" that doesn't actually exist on the shape.
        wingRoles: (b.wings || []).map((w) => (w.role || "").toLowerCase()).filter(Boolean),
      };
    })
    .filter(Boolean);
}

// Re-render the scene directly from the current placed buildings (their boundaries
// were just updated server-side by a move/rotate/scale). Resets lastOptions so the
// updated geometry replaces any stale option footprints, making the change visible.
export function renderBuildings(s) {
  init();
  const drawables = buildingsToDrawables(s.buildings || []);
  if (!drawables.length) {
    // Nothing placed — still redraw the site so the view isn't blank.
    renderScene(s.site, [], { fitCamera: false });
    return;
  }
  lastOptions = drawables;            // override stale option footprints
  // Ensure the building's ids are in the visibility set so the eye filter doesn't
  // hide it (it was set for optimization options, not these building ids).
  // GUARD: only setState when ids are actually MISSING. Calling setState here
  // unconditionally caused an infinite loop — setState → store emit → center.render()
  // → viewer.activate() → renderBuildings() → setState → … (page freeze). Skipping the
  // write when nothing changed breaks that cycle.
  const vis = getState().visibleOptionIds;
  if (vis instanceof Set) {
    const missing = drawables.some((d) => !vis.has(d.option_id));
    if (missing) {
      drawables.forEach((d) => vis.add(d.option_id));
      setState({ visibleOptionIds: new Set(vis) });
    }
  }
  setTimeout(() => {
    resize();
    // Fit the camera to the building so a moved/rotated result is always in frame.
    renderScene(s.site, drawables, { fitCamera: true });
  }, 30);
}

function highlightSelected(optionId) {
  if (selectedMesh?.material) { selectedMesh.material.emissive = new THREE.Color(0x000000); }
  selectedMesh = optionMeshes.find((m) => m.userData.optionId === optionId) || null;
  if (selectedMesh?.material) { selectedMesh.material.emissive = new THREE.Color(0x143526); }
}

// ---- part classification (for tooltips + selection) ----
function classifyPart(intersection, mesh) {
  const opt = mesh.userData.option || {};
  const b = fpBounds(opt.footprint || [[0, 0]]);
  const pt = intersection.point;
  const normal = intersection.face?.normal?.clone() || new THREE.Vector3(0, 0, 1);
  normal.transformDirection(mesh.matrixWorld);
  const axis = Math.abs(normal.z) > 0.7 ? "z" : Math.abs(normal.x) > Math.abs(normal.y) ? "x" : "y";
  let surface = "side_face";
  if (axis === "z") surface = normal.z >= 0 ? "roof_face" : "bottom_face";
  else if (axis === "x") surface = normal.x >= 0 ? "right_face" : "left_face";
  else surface = normal.y >= 0 ? "back_face" : "front_face";

  // Name the part from the building's REAL wings, not just screen position. A shape
  // with only one wing (an "I" bar → ['main_bar']) is a single mass — we must NOT
  // call its sides "left/right wing" because the backend has no such wing and the
  // edit would target something that doesn't exist. Only a true multi-wing shape
  // (L/U/T/H) maps the click position to an actual left / right / connector wing.
  const roles = opt.wingRoles || [];
  const hasRealWings = roles.length > 1;
  const midX = (b.minX + b.maxX) / 2, midY = (b.minY + b.maxY) / 2;
  const spanX = Math.max(b.maxX - b.minX, 1), spanY = Math.max(b.maxY - b.minY, 1);
  let part;
  if (hasRealWings) {
    // pick the real wing whose name best matches the click side
    const left = roles.find((r) => /left/.test(r));
    const right = roles.find((r) => /right/.test(r));
    const mid = roles.find((r) => /connect|center|central|main|core/.test(r)) || roles[Math.floor(roles.length / 2)];
    if (pt.x < midX - spanX * 0.18) part = left || roles[0];
    else if (pt.x > midX + spanX * 0.18) part = right || roles[roles.length - 1];
    else part = mid || roles[0];
  } else {
    // single mass — label it honestly as the whole building
    part = roles[0] && roles[0] !== "main_bar" ? roles[0] : "building";
  }

  // rough metrics for the tooltip (divide by however many real parts there are)
  const nParts = hasRealWings ? roles.length : 1;
  const area = Math.round(Math.abs(polyArea(opt.footprint || [])) / Math.max(1, nParts));
  // option number (1-based) + score + selected/alternative status for the tooltip
  const optIndex = (lastOptions || []).findIndex((o) => o.option_id === mesh.userData.optionId);
  const optionNumber = optIndex >= 0 ? optIndex + 1 : null;
  const score = Number(opt.score);
  const isSelected = getState().selectedOptionId === mesh.userData.optionId;
  return {
    optionId: mesh.userData.optionId, part, surface,
    label: _partLabel(part, hasRealWings),
    area, height: Math.round(opt.height || 0), floors: opt.floors || 0,
    optionNumber, score: Number.isFinite(score) ? score : null, isSelected,
    point: [pt.x, pt.y, pt.z],
  };
}

// Human-readable part name. Real wing roles → "Left Wing"; a single mass → "Building".
function _partLabel(part, hasRealWings) {
  if (part === "building" || part === "main_bar") return "Building";
  const nice = part.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  // append "Wing" for left/right/connector style roles so it reads naturally
  if (hasRealWings && /^(left|right|connector|center|central|core|main)$/i.test(part)) {
    return nice + " Wing";
  }
  return nice;
}

function partCount(part) { return part === "central_mass" ? 1 : 3; }
function polyArea(fp) {
  let a = 0;
  for (let i = 0; i < fp.length - 1; i++) a += fp[i][0] * fp[i + 1][1] - fp[i + 1][0] * fp[i][1];
  return a / 2;
}

// ---- tooltip ----
function showTooltip(part, clientX, clientY) {
  const t = tooltip();
  if (!t) return;
  // Lead with the option number + status + score (per request), then the part detail.
  const titleNum = part.optionNumber ? `Option ${part.optionNumber}` : part.label;
  const statusTag = part.optionNumber
    ? `<span class="pt-tag ${part.isSelected ? "sel" : "alt"}">${part.isSelected ? "Selected" : "Alternative"}</span>`
    : "";
  const scoreLine = part.score != null ? `Score: ${part.score.toFixed(2)}<br/>` : "";
  t.innerHTML = `<div class="pt-title">${titleNum} ${statusTag}</div>
    ${scoreLine}
    <span class="pt-dim">${part.label}</span> · ${part.height} m · ${part.floors} fl`;
  t.style.left = clientX + 16 + "px";
  t.style.top = clientY + 12 + "px";
  t.classList.remove("hidden");
}
function hideTooltip() { tooltip()?.classList.add("hidden"); }

// ---- interaction ----
function onDown(e) { cam.dragging = true; cam.moved = false; cam.button = e.button; cam.lastX = e.clientX; cam.lastY = e.clientY; }
function onUp(e) {
  cam.dragging = false;
  if (!cam.moved) performPick(e);
}
function onMove(e) {
  if (cam.dragging) {
    const dx = e.clientX - cam.lastX, dy = e.clientY - cam.lastY;
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) cam.moved = true;
    if (cam.button === 2) {
      const s = Math.max(cam.radius * 0.0018, 0.02);
      cam.target.x -= dx * s; cam.target.y += dy * s;
    } else {
      cam.theta -= dx * 0.006;
      cam.phi = Math.min(Math.PI - 0.1, Math.max(0.1, cam.phi + dy * 0.006));
    }
    cam.lastX = e.clientX; cam.lastY = e.clientY;
    updateCamera();
    hideTooltip();
  } else {
    hoverPick(e);
  }
}
function onWheel(e) {
  e.preventDefault();
  cam.radius = Math.min(cam.maxR, Math.max(cam.minR, cam.radius * (e.deltaY > 0 ? 1.08 : 0.92)));
  updateCamera();
}

function castRay(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  return raycaster.intersectObjects(optionMeshes, false);
}

function hoverPick(e) {
  if (!optionMeshes.length) return hideTooltip();
  const hits = castRay(e);
  if (!hits.length) return hideTooltip();
  showTooltip(classifyPart(hits[0], hits[0].object), e.clientX, e.clientY);
}

function performPick(e) {
  if (!optionMeshes.length) return;
  const hits = castRay(e);
  if (!hits.length) return;
  const mesh = hits[0].object;
  const part = classifyPart(hits[0], mesh);
  // Resolve which placed building this option belongs to so the manipulation tools
  // target the right one (selectedBuildingId is what transformSelectedBuilding uses).
  const s = getState();
  const opt = (s.options || []).find((o) => o.option_id === mesh.userData.optionId);
  const buildings = s.buildings || [];
  const buildingId =
    (opt && opt.building_id) ||
    (buildings[0] && (buildings[0].building_id || buildings[0].geometry_id)) ||
    null;
  setState({
    selectedOptionId: mesh.userData.optionId,
    selectedBuildingId: buildingId,
    selectedPart: { part: part.part, surface: part.surface },
  });
  highlightSelected(mesh.userData.optionId);
  // Offer part selection (whole building + wings) and the edit tools. Wing chips
  // come from the backend /parts endpoint so the user can target an arm.
  surfaceEditTools(buildingId, part);
}

// Build the "selected — pick a part + tool" message. Fetches selectable parts so
// the user can choose the whole building or a specific wing/arm before editing.
async function surfaceEditTools(buildingId, part) {
  let partChips = [];
  try {
    const s = getState();
    if (s.sessionId && buildingId) {
      const { api } = await import("../core/api.js");
      const res = await api.agent.getBuildingParts(s.sessionId, buildingId);
      partChips = (res.parts || []).map((p) => ({
        label: (p.part_id === (getState().selectedPartId || "building") ? "✓ " : "") + p.label,
        message: `select ${p.label}`,
        intent: "select_part",
        partId: p.part_id,
        partLabel: p.label,
      }));
    }
  } catch {
    /* parts endpoint optional — whole-building editing still works */
  }
  pushMessage(
    "assistant",
    `Selected **${part.label}**. Choose a part to edit, then a tool:`,
    [
      ...partChips,
      { label: "Move", message: "Move the selected part", intent: "move" },
      { label: "Rotate", message: "Rotate the selected part", intent: "rotate" },
      { label: "Scale", message: "Scale the selected part", intent: "scale" },
      { label: "Push/Pull", message: "Push or pull the part", intent: "pushpull" },
      { label: "Optimize", message: "Optimize the building placement", intent: "optimize", primary: true },
    ]
  );
}

// ---------------------------------------------------------------------------
// Clear stale module-level draw state so the next render shows ONLY the current
// building (called when a shape is freshly selected, to avoid leftover shapes from
// a previous optimization run lingering in the scene).
export function resetForFreshBuilding() {
  lastOptions = [];
  ghostCandidates = [];
  selectedMesh = null;
}

// BUG 2: briefly glow the building meshes so the user immediately sees what changed
// after a successful manipulation. Pulses the emissive for ~2.5s, then restores.
let _flashTimer = null;
export function flashBuilding() {
  if (!rootGroup) return;
  const meshes = rootGroup.children.filter(
    (m) => m.isMesh && m.material && m.material.emissive && m.userData && m.userData.optionId,
  );
  if (!meshes.length) return;
  if (_flashTimer) { clearInterval(_flashTimer); _flashTimer = null; }
  const orig = meshes.map((m) => m.material.emissive.clone());
  const glow = new THREE.Color(0x57f2e6);
  const start = performance.now();
  const DURATION = 2500;
  _flashTimer = setInterval(() => {
    const t = (performance.now() - start) / DURATION;
    if (t >= 1) {
      meshes.forEach((m, i) => m.material.emissive.copy(orig[i]));
      clearInterval(_flashTimer); _flashTimer = null;
      return;
    }
    // pulse: bright -> fade
    const k = Math.max(0, Math.sin(t * Math.PI * 3)) * (1 - t);
    meshes.forEach((m, i) => m.material.emissive.copy(orig[i]).lerp(glow, k));
  }, 40);
}

export function activate() {
  init();
  setTimeout(resize, 60);
  // re-render from store if we have options but nothing drawn yet — and only
  // when no visibility filter is active, so activating the view never overrides
  // a "hide all / hide some" selection.
  const s = getState();
  if (s.options?.length && !optionMeshes.length) {
    renderScene(s.site, s.options);
  } else if (!s.options?.length && s.buildings?.length) {
    // No optimization options but a building is placed (e.g. just selected a shape):
    // draw EXACTLY that building. renderBuildings resets lastOptions first, so any
    // lingering multi-shape preview from the Shape Library is replaced — not stacked.
    renderBuildings(s);
  } else if (!s.options?.length && s.site?.boundary?.length >= 3) {
    // Only the site so far — wipe stale preview state and draw just the boundary.
    resetForFreshBuilding();
    renderScene(s.site, []);
  }
}

// debug/verification probe: number of building meshes currently in the scene
window.__optionMeshCount = () => optionMeshes.length;
window.__ghostCount = () => ghostCandidates.length;
// Toggle the floating per-option score cards in the optimized-options preview.
window.__scoreCards = (on = true) => {
  showScoreCards = !!on;
  const s = getState();
  if (s.options?.length) renderScene(s.site, s.options, { fitCamera: false });
};
window.__scoreCardCount = () => scoreCardSprites.length;
// Re-enable the vertex spheres + pin lines + edge-direction labels (off by default).
window.__vertexMarkers = (on = true) => {
  showVertexMarkers = !!on;
  const s = getState();
  if (s.options?.length || s.buildings?.length) renderScene(s.site, s.options || []);
};

export async function onAction(payload) {
  init();
  const action = payload.action;
  if (action === "preview_optimized" || action === "preview_saved") {
    // Browsing one optimized variant (shape_001A / B …). Optimize-saved keeps the SAME
    // footprint and only changes WHERE on the site it sits — so to make A vs B visibly
    // different we must frame the WHOLE SITE (fitCamera:true includes the site bounds in
    // centerCameraOn) and draw the site outline + setback, so the user sees this variant
    // sitting north / south / at a corner. Without re-fitting, the camera stayed zoomed
    // on the building and every variant looked identical.
    const s = getState();
    const opts = (s.options && s.options.length) ? s.options : [];
    setTimeout(() => { resize(); renderScene(s.site, opts, { fitCamera: true }); }, 80);
    return;
  }
  if (action === "render_options") {
    const result = payload.result || {};
    const options = result.best_4_options || result.options || [];
    // Capture the explored solution space for ghost shapes: candidates that have
    // a footprint but weren't selected. Marked rejected if they failed constraints.
    const pop = result.population || result.optimization_history || [];
    ghostCandidates = (Array.isArray(pop) ? pop : [])
      .filter((c) => Array.isArray(c.footprint) && c.footprint.length >= 3)
      .slice(0, 24)
      .map((c) => ({
        option_id: c.option_id || `ghost_${Math.random().toString(36).slice(2)}`,
        footprint: c.footprint,
        height: c.height || 10,
        rejected: c.status === "invalid" || c.status === "rejected" || c.valid === false || c.constraint_report?.passed === false,
      }));
    // New options are all visible by default. syncOptionsFromView has already
    // populated visibleOptionIds in the store; ensure it covers these ids.
    setState({ visibleOptionIds: new Set(options.map((o) => o.option_id)) });
    const s = getState();
    setTimeout(() => { resize(); renderScene(s.site, options); }, 80);
  } else if (action === "update_geometry" || action === "restore") {
    const result = payload.result || {};
    const geom = result.updated_geometry || result.restored_geometry;
    if (geom) {
      const s = getState();
      setTimeout(() => { resize(); renderScene(s.site, [geom], { fitCamera: false }); }, 60);
    }
  } else if (action === "set_visibility") {
    setState({ visibleOptionIds: payload.visible_ids ? new Set(payload.visible_ids) : null });
    const s = getState();
    renderScene(s.site, s.options, { fitCamera: false });
  }
}

// expose for optimize/compare slices.
// `ids` semantics:
//   null      -> no filter, show all options
//   []        -> show none (every eye toggled off)
//   [a, b...] -> show exactly these option ids
// Writes the store so the explorer icons and the viewer never diverge.
export function setVisibleOptions(ids) {
  setState({ visibleOptionIds: Array.isArray(ids) ? new Set(ids) : null });
  const s = getState();
  renderScene(s.site, s.options, { fitCamera: false });
}

// STAGE 1 Shape Library preview — draw a set of generated shape footprints in the
// viewer WITHOUT touching the optimization `options` bucket or its visibility
// filter. Used while the user is browsing/selecting shapes (no optimization yet).
export function renderShapePreview(shapes) {
  init();
  const s = getState();
  const drawables = (shapes || [])
    .map((o) => ({
      option_id: o.option_id,
      footprint: (o.footprint || o.boundary || []).map((p) => [Number(p[0]), Number(p[1])]),
      height: o.height_m || 12,
      floors: o.floors || 0,
      shape_type: o.shape_type || "shape",
    }))
    .filter((o) => o.footprint.length >= 3);
  // Pass an explicit (possibly empty) list so renderScene shows exactly these
  // shapes and the eye-filter (which keys off visibleOptionIds) doesn't hide them.
  setState({ visibleOptionIds: new Set(drawables.map((o) => o.option_id)) });
  renderScene(s.site, drawables, { fitCamera: true });
}
