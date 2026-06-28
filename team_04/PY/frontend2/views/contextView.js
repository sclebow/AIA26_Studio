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
// Merged from the urban-context port reference (richer overlay + offline-aware
// data shape `store.context`) with this project's additions: a container-mount
// retry (so dispatchView-driven rendering never lands on a blank canvas) and a
// shape-preview overlay so the Shape Library can show a candidate massing IN the
// real urban context.
//
// Geometry/camera patterns follow viewerView.js so the two 3D views feel native.

import { getState, setState } from "../core/store.js";
import { SCORE_META, scoreColor } from "../core/overpass.js";

let scene, camera, renderer, rootGroup, raycaster, pointer, cam;
let inited = false;
let _ctxDebugOn = false;            // BUG 4: debug overlay OFF by default (no duplicate labels)
let showContextMarkers = true;      // BUG 4: toggle for the single clean edge labels
let edgePickables = []; // line meshes for edge hover-picking
let edgeRegistry = {}; // SINGLE SOURCE OF TRUTH: edge_id → {all edge data}
let lastCtxStamp = null;
let hudEl, scoresEl, reportEl;

// Debug flags (expose to window for console access)
window.__ctxHoverDebug = false;  // Set to true to log hover edge selection
window.__ctxHoverOverlay = false; // Set to true to show debug overlay on hover

function viewEl() {
  return document.getElementById("view-context");
}

function init() {
  if (inited) return;
  const container = viewEl();
  if (!container || container.clientWidth < 10) return; // not mounted/sized yet
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
    // theta = -π/2 puts the camera at -y (geographic SOUTH of the site) looking
    // toward +y (north), so the default view is genuinely NORTH-UP: screen-up =
    // true north, north edge at the top. (theta=+π/2 was the opposite — camera
    // north of the site looking south — which made the compass read S-up.)
    radius: 2600, theta: -Math.PI * 0.5, phi: Math.PI * 0.34,
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
  // Edge detail panel only shows on click, not hover
  renderer.domElement.addEventListener("click", onCanvasClick);

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
    <div class="ctx-compass" id="ctx-compass" title="True north — edge directions are geographic, not screen-relative">
      <div class="ctx-compass-dial" id="ctx-compass-dial">
        <span class="ctx-compass-n">N</span><span class="ctx-compass-e">E</span>
        <span class="ctx-compass-s">S</span><span class="ctx-compass-w">W</span>
        <div class="ctx-compass-needle"></div>
      </div>
    </div>
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
  const c = viewEl();
  if (!renderer || !camera || !c) return;
  camera.aspect = c.clientWidth / c.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(c.clientWidth, c.clientHeight);
}

function animate() {
  requestAnimationFrame(animate);
  if (camera && cam) camera.lookAt(cam.target);
  if (renderer && scene && camera) renderer.render(scene, camera);
  updateCompass();
}

// Rotate the on-screen compass so its "N" points where TRUE geographic north
// actually projects on screen, for the CURRENT camera. We project two world
// points — the site center and a point 100 m due north (+y) — through the live
// camera, then measure the angle of that screen vector. This is exactly the same
// geographic north the edge labels use (computed from atan2(vy, vx) in overpass.js),
// so compass and labels always agree.
const _np0 = new THREE.Vector3();
const _np1 = new THREE.Vector3();
function updateCompass() {
  const dial = document.getElementById("ctx-compass-dial");
  if (!dial || !camera || !cam) return;

  // Project site centroid and a point 100m due north (+y) through camera
  _np0.set(cam.target.x, cam.target.y, 0).project(camera);
  _np1.set(cam.target.x, cam.target.y + 100, 0).project(camera); // +y = true north

  // Screen-space vector from centroid to north point
  // NDC y is up; CSS rotation is clockwise from 12 o'clock
  const sx = _np1.x - _np0.x;
  const sy = -(_np1.y - _np0.y); // flip to screen-down-positive

  // Angle clockwise from straight-up (where "N" sits on dial)
  // This measures the screen angle of the +y (north) vector
  const screenNorthAngle = Math.atan2(sx, -sy) * (180 / Math.PI);
  dial.style.transform = `rotate(${screenNorthAngle}deg)`;

  // DEBUG: Log compass calculation periodically
  if (window.__ctxCompassDebug) {
    console.log("[compass] screen-north angle:", Math.round(screenNorthAngle) + "°",
      "from centroid:", [Math.round(_np0.x * 100) / 100, Math.round(_np0.y * 100) / 100],
      "to north:", [Math.round(_np1.x * 100) / 100, Math.round(_np1.y * 100) / 100]);
  }
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
  edgeRegistry = {};
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
  // Brighter context buildings: the old fill (0x223451) was nearly invisible on the dark
  // map ("no context buildings" — they WERE there, just too dark). Lighter steel-blue
  // fill + a stronger emissive glow + bright cyan top edges make the surrounding city
  // clearly visible, while still reading as CONTEXT (not the user's teal design building).
  const mat = new THREE.MeshStandardMaterial({
    color: 0x3d5878, metalness: 0.25, roughness: 0.5,
    transparent: true, opacity: 0.95, emissive: 0x1b3a5c, emissiveIntensity: 0.9,
  });
  for (const b of buildings) {
    if (!b.footprint || b.footprint.length < 3) continue;
    const geo = new THREE.ExtrudeGeometry(shapeFromFootprint(b.footprint), { depth: b.height, bevelEnabled: false });
    const mesh = new THREE.Mesh(geo, mat);
    rootGroup.add(mesh);
    const top = b.footprint.map((p) => new THREE.Vector3(p[0], p[1], b.height + 0.5));
    const edge = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints(top),
      new THREE.LineBasicMaterial({ color: 0x6fb6dd, transparent: true, opacity: 0.85 })
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
  const fill = new THREE.Mesh(
    new THREE.ShapeGeometry(shapeFromFootprint(b)),
    new THREE.MeshBasicMaterial({ color: 0x28e0d0, transparent: true, opacity: 0.18, side: THREE.DoubleSide })
  );
  fill.position.z = 2;
  rootGroup.add(fill);
  const colHeight = 220;
  const beam = new THREE.Mesh(
    new THREE.CylinderGeometry(4, 4, colHeight, 8, 1, true),
    new THREE.MeshBasicMaterial({ color: 0x57f2e6, transparent: true, opacity: 0.16, side: THREE.DoubleSide })
  );
  const c = ctx.siteCentroidLocal;
  beam.position.set(c[0], c[1], colHeight / 2);
  beam.rotation.x = Math.PI / 2;
  rootGroup.add(beam);

  // BUILD EDGE REGISTRY (SINGLE SOURCE OF TRUTH)
  // Each edge gets a permanent entry that hover system uses
  for (const e of ctx.edges) {
    const edgeId = e.edge_id || e.id;

    // Create registry entry with all edge data
    const registryEntry = {
      edge_id: edgeId,
      label: e.display_name || e.label || "Unknown",
      direction: e.direction,
      angle: e.compassAngle || e.angle,
      sector: e.compassSector || e.direction,
      start_point: [e.a[0], e.a[1]],
      end_point: [e.b[0], e.b[1]],
      midpoint: [e.mid[0] || e.midpoint[0], e.mid[1] || e.midpoint[1]],
      nearest: e.nearest || {},
      edge_context: e.edge_context || [],   // filtered, per-edge relevant amenities
      centroid: e.centroid,
      vx: e.vx,
      vy: e.vy
    };
    edgeRegistry[edgeId] = registryEntry;

    // Draw edge line on ground plane (z=0)
    const pts = [new THREE.Vector3(e.a[0], e.a[1], 0), new THREE.Vector3(e.b[0], e.b[1], 0)];
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0x57f2e6, transparent: true, opacity: 0.95 })
    );

    // Store ONLY the edge_id (reference to registry)
    // Do NOT store full metadata — hover system will look it up in registry
    line.userData = {
      edge_id: edgeId
    };

    rootGroup.add(line);
    edgePickables.push(line);
  }
  // BUG 4: smaller, subtler vertex markers (were oversized white circles). Only one
  // marker per actual boundary vertex.
  const vmat = new THREE.MeshBasicMaterial({ color: 0x9fe8ff, transparent: true, opacity: 0.85 });
  for (const p of b) {
    const v = new THREE.Mesh(new THREE.SphereGeometry(3, 10, 10), vmat);
    v.position.set(p[0], p[1], 3);
    rootGroup.add(v);
  }

  // BUG 4: the debug overlay (centroid + midpoint markers + arrows + a SECOND set of
  // edge labels) is what produced the duplicate labels. It's off by default now;
  // enable with window.__ctxDebug(true). The single canonical edge labels are drawn
  // by addEdgeLabels below.
  if (_ctxDebugOn) addEdgeSideDebug(ctx);
  if (showContextMarkers) addEdgeLabels(ctx);
}

// ONE clean label per edge, placed OUTSIDE the footprint, toggleable.
function addEdgeLabels(ctx) {
  const c = ctx.siteCentroidLocal || [0, 0];
  for (const e of ctx.edges || []) {
    const mid = e.mid || [(e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2];
    const vx = mid[0] - c[0], vy = mid[1] - c[1];
    const d = Math.hypot(vx, vy) || 1;
    // push the label well outside the footprint so it never overlaps geometry
    const lx = c[0] + (vx / d) * (d + 14);
    const ly = c[1] + (vy / d) * (d + 14);
    const tag = _debugTextSprite(e.direction || e.display_name || "?");
    if (tag) { tag.position.set(lx, ly, 2); rootGroup.add(tag); }
  }
}

// Debug overlay proving edge labels come from real geographic position: a marker
// at the site centroid, markers at each edge midpoint, arrows from centroid →
// midpoint per edge, and TRUE NORTH/EAST axis arrows in the SAME local frame
// (x=east, y=north) that the edge labels use. This ensures compass widget,
// axis visualization, and edge labels all agree on true north. Toggle with
// window.__ctxDebug(false) or check alignment with window.__ctxCompareDebug().
// Expose a runtime toggle so users can hide/show context markers (BUG 4 requirement).
window.__ctxMarkers = (on = true) => {
  showContextMarkers = !!on;
  try { if (getState().context) renderContext(); } catch { /* not mounted */ }
  return `context markers ${showContextMarkers ? "ON" : "OFF"}`;
};
function addEdgeSideDebug(ctx) {
  if (!_ctxDebugOn || !ctx.edges?.length) return;
  const c = ctx.siteCentroidLocal || [0, 0];

  // COORDINATE SYSTEM MAPPING (CRITICAL FIX):
  // Local coords: x=east, y=north (from makeProjector equirectangular projection)
  // Three.js: X=right, Y=backward (north is -Y), Z=up (camera.up=[0,0,1])
  // Camera at theta=-π/2 means camera is at -Y (south) looking toward +Y (north)
  // So:
  //   local.x (east) → Three.js.X ✓
  //   local.y (north) → Three.js.Y ✓ (not Z!)
  //   ground plane: XY with Z=0
  // This ensures labels sit on ground plane and angles match compass.
  const toWorld = (lx, ly) => [lx, ly, 0];  // Project 2D local → 3D ground plane (XY)

  // Size the axis arrows proportionally to the site
  const span = Math.max(40, ...ctx.edges.map((e) => {
    const m = e.mid || [(e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2];
    return Math.hypot(m[0] - c[0], m[1] - c[1]);
  })) * 1.6;

  // TRUE NORTH axis (+y, green) and TRUE EAST axis (+x, red) from centroid.
  // These are in the SAME coordinate system as edge angles (atan2(vy, vx)).
  const axis = (dx, dy, color, label) => {
    const [wx0, wy0, wz0] = toWorld(c[0], c[1]);
    const [wx1, wy1, wz1] = toWorld(c[0] + dx, c[1] + dy);
    rootGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(wx0, wy0, wz0),
        new THREE.Vector3(wx1, wy1, wz1)
      ]),
      new THREE.LineBasicMaterial({ color, linewidth: 2 })
    ));
    const t = _debugTextSprite(label);
    // Place label on ground plane (z=0) at arrow end
    if (t) { t.position.set(wx1, wy1, 0); rootGroup.add(t); }
  };

  // Draw cardinal axes in world space (ground plane)
  // +y=North (green), -y=South (dark)
  // +x=East (red), -x=West (dark)
  axis(0, span, 0x57e08a, "TRUE N\n(+Y)");
  axis(0, -span, 0x335544, "TRUE S\n(-Y)");
  axis(span, 0, 0xff5f6d, "TRUE E\n(+X)");
  axis(-span, 0, 0x553333, "TRUE W\n(-X)");

  // Centroid marker (bright yellow) — origin of all angle calculations
  const [wcx, wcy, wcz] = toWorld(c[0], c[1]);
  const cm = new THREE.Mesh(new THREE.SphereGeometry(12, 16, 16),
    new THREE.MeshBasicMaterial({ color: 0xffe04a }));
  cm.position.set(wcx, wcy, wcz);
  rootGroup.add(cm);
  const centroidLabel = _debugTextSprite("CENTROID");
  // Centroid label on ground plane
  if (centroidLabel) { centroidLabel.position.set(wcx, wcy, 0); rootGroup.add(centroidLabel); }

  // Process each edge: midpoint + vector + label with angle & sector
  for (const e of ctx.edges) {
    const mid = e.mid || [(e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2];
    const vx = mid[0] - c[0];
    const vy = mid[1] - c[1];
    const dist = Math.hypot(vx, vy);

    // Midpoint marker (bright magenta) on ground plane
    const [wmx, wmy, wmz] = toWorld(mid[0], mid[1]);
    const mm = new THREE.Mesh(new THREE.SphereGeometry(8, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0xff5fff }));
    mm.position.set(wmx, wmy, wmz);
    rootGroup.add(mm);

    // Vector from centroid to midpoint (cyan arrow) on ground plane
    rootGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(wcx, wcy, wcz),
        new THREE.Vector3(wmx, wmy, wmz),
      ]),
      new THREE.LineBasicMaterial({ color: 0x28e0d0, linewidth: 2 })
    ));

    // Label positioned outward from centroid on ground plane
    // Offset label further out so it doesn't overlap the polygon
    const labelDist = dist * 1.3;  // Extend label beyond the edge midpoint
    const labelX = c[0] + (vx / dist) * labelDist;
    const labelY = c[1] + (vy / dist) * labelDist;
    const [labelWx, labelWy, labelWz] = toWorld(labelX, labelY);

    const compassAng = Math.round(e.compassAngle || 0);
    const sector = e.compassSector || e.direction || "?";
    const edgeLabel = e.direction || "?";
    const tag = _debugTextSprite(
      `${e.id}: ${edgeLabel}\n${compassAng}° [${sector}]\nvx=${Math.round(vx)} vy=${Math.round(vy)}`
    );
    // Place label on ground plane (z=0) at extended position
    if (tag) { tag.position.set(labelWx, labelWy, 0); rootGroup.add(tag); }
  }

  // Log all edge calculations for verification
  const edgeReport = ctx.edges.map((e) => {
    const mid = e.mid || [(e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2];
    const vx = mid[0] - c[0];
    const vy = mid[1] - c[1];
    const ang = Math.round(e.compassAngle || 0);
    const sector = e.compassSector || "?";
    const dir = e.direction || "?";
    return `${e.id}: [vx=${Math.round(vx)}, vy=${Math.round(vy)}] → ${ang}° → ${sector} → ${dir}`;
  }).join("\n  ");

  // eslint-disable-next-line no-console
  console.log("[ctx-debug-alignment] TRUE-NORTH EDGE VERIFICATION (GROUND PLANE)");
  console.log("[ctx-debug-alignment] Centroid:", c.map((v) => Math.round(v)), "(x=east, y=north)");
  console.log("[ctx-debug-alignment] LOCAL AXES: +X=EAST(red), +Y=NORTH(green), -X=WEST, -Y=SOUTH");
  console.log("[ctx-debug-alignment] 3D MAPPING: local.x → World.X(right), local.y → World.Y(north), z=0(ground)");
  console.log("[ctx-debug-alignment] Camera: up=[0,0,1], positioned at -Y looking toward +Y, ground plane=XY");
  console.log("[ctx-debug-alignment] Result: On screen, +Y(north) appears BACK, +X(east) appears RIGHT, labels on ground");
  console.log("[ctx-debug-alignment] Compass angle formula: atan2(vy, vx) where vx=east, vy=north");
  console.log("[ctx-debug-alignment] Edge vectors & compass assignment:");
  console.log("  " + edgeReport);
  console.log("[ctx-debug-alignment] VERIFY: Northwest edge should have vx<0 (west) and vy>0 (north), never be Southeast");
}

function _debugTextSprite(text) {
  try {
    const cv = document.createElement("canvas");
    cv.width = 256; cv.height = 48;
    const g = cv.getContext("2d");
    g.font = "bold 26px monospace"; g.fillStyle = "#ffe04a";
    g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(text, 128, 24);
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv), transparent: true, depthTest: false }));
    spr.scale.set(60, 11, 1);
    return spr;
  } catch { return null; }
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
  const disc = new THREE.Mesh(
    new THREE.CircleGeometry(radius, 96),
    new THREE.MeshBasicMaterial({ color: 0x0a1326, transparent: true, opacity: 0.55, side: THREE.DoubleSide })
  );
  disc.position.z = -0.5;
  rootGroup.add(disc);
}

// ---- main render from store.context ----
function renderContext() {
  init();
  // Container may still be mounting (dispatchView morph) — retry until it's sized.
  if (!inited || !viewEl() || viewEl().clientWidth < 10) {
    setTimeout(renderContext, 120);
    return;
  }
  resize();
  const ctx = getState().context;
  if (!ctx) return;
  setLoading(false); // data is here — never leave the scanning overlay up

  // Save current camera state to avoid resetting zoom on re-renders
  const savedRadius = cam.radius;
  const savedTheta = cam.theta;
  const savedPhi = cam.phi;
  const savedTarget = cam.target.clone();

  clearScene();
  const visible = getState().contextVisible || {};

  addRadiusRing(ctx.radius);
  addParks(ctx.layers, visible);
  addRoads(ctx.layers, visible);
  addBuildings(ctx.buildings);
  addAmenities(ctx.layers, visible);
  addSite(ctx);

  // Only reset camera if this is the first render or context changed significantly
  if (lastCtxStamp === ctx.generatedAt && savedRadius !== undefined) {
    // Restore camera state (user zoomed/panned, don't reset)
    cam.radius = savedRadius;
    cam.theta = savedTheta;
    cam.phi = savedPhi;
    cam.target.copy(savedTarget);
  } else {
    // First render or context changed — use default view
    cam.target.set(ctx.siteCentroidLocal[0], ctx.siteCentroidLocal[1], 0);
    cam.radius = ctx.radius * 1.4;
  }
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

// Re-apply visibility (called by the explorer toggles). Full rebuild — scene is light.
export function refreshVisibility() {
  if (getState().context) renderContext();
}

// ---- edge intelligence hover ----
function onDown(e) { cam.dragging = true; cam.moved = false; cam.button = e.button; cam.lastX = e.clientX; cam.lastY = e.clientY; }
function onUp() { cam.dragging = false; cam.moved = false; }
function onMove(e) {
  if (cam.dragging) {
    const dx = e.clientX - cam.lastX, dy = e.clientY - cam.lastY;
    // Require meaningful movement before marking as "moved" (threshold = 5px to allow clicks)
    if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
      cam.moved = true;
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
    }
  }
  // Edge detail panel only shows on click, not on hover/mousemove
}
function onWheel(e) {
  e.preventDefault();
  cam.radius = Math.min(cam.maxR, Math.max(cam.minR, cam.radius * (e.deltaY > 0 ? 1.08 : 0.92)));
  updateCamera();
}

function edgeHover(e) {
  if (!edgeRegistry || Object.keys(edgeRegistry).length === 0) {
    return hideEdgeHud();
  }

  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

  // ===== PRIMARY METHOD: DISTANCE-TO-SEGMENT =====
  // Project mouse to ground plane (z=0)
  raycaster.setFromCamera(pointer, camera);
  const t = -raycaster.ray.origin.z / raycaster.ray.direction.z;
  const mouseWorldPos = raycaster.ray.origin.clone().addScaledVector(raycaster.ray.direction, t);

  let selectedEdgeId = null;
  let closestDist = Infinity;
  let segmentDistances = [];

  // Iterate through registry (not edgePickables) to ensure consistency
  for (const edgeId in edgeRegistry) {
    const entry = edgeRegistry[edgeId];
    const a = new THREE.Vector3(entry.start_point[0], entry.start_point[1], 0);
    const b = new THREE.Vector3(entry.end_point[0], entry.end_point[1], 0);

    const dist = distancePointToSegment(mouseWorldPos, a, b);

    if (window.__ctxHoverDebug) {
      segmentDistances.push({
        edge_id: edgeId,
        label: entry.label,
        distance: dist.toFixed(1)
      });
    }

    if (dist < closestDist) {
      closestDist = dist;
      selectedEdgeId = edgeId;
    }
  }

  // Only show tooltip if pointer is close enough
  const HOVER_THRESHOLD = 100;
  if (closestDist > HOVER_THRESHOLD) {
    if (window.__ctxHoverDebug) {
      console.log("[hover] Too far from all edges. closestDist=", closestDist.toFixed(1));
    }
    return hideEdgeHud();
  }

  // ===== VALIDATE SELECTION =====
  if (!selectedEdgeId || !edgeRegistry[selectedEdgeId]) {
    if (window.__ctxHoverDebug) {
      console.error("[hover] No valid edge selected. selectedEdgeId=", selectedEdgeId);
    }
    return hideEdgeHud();
  }

  const registryEntry = edgeRegistry[selectedEdgeId];

  // ===== DEBUG OUTPUT =====
  if (window.__ctxHoverDebug) {
    console.log("[hover-distance] mouse:", {
      x: mouseWorldPos.x.toFixed(1),
      y: mouseWorldPos.y.toFixed(1),
      z: mouseWorldPos.z.toFixed(1)
    });
    console.log("[hover-selected]", {
      edge_id: selectedEdgeId,
      label: registryEntry.label,
      distance: closestDist.toFixed(1),
      sector: registryEntry.sector,
      angle: registryEntry.angle + "°"
    });
    console.table(segmentDistances);
  }

  // ===== DISPLAY TOOLTIP =====
  showEdgeHud(registryEntry, e.clientX, e.clientY);
  // Store in app state for copilot (for hover, state updates but HUD shows via hover only)
  setState({ selectedEdge: registryEntry });
}

// Calculate shortest distance from point to line segment
function distancePointToSegment(point, segStart, segEnd) {
  const dx = segEnd.x - segStart.x;
  const dy = segEnd.y - segStart.y;
  const len2 = dx * dx + dy * dy;

  if (len2 === 0) {
    // Segment is a point
    return point.distanceTo(segStart);
  }

  // Project point onto line, clamped to segment
  const t = Math.max(0, Math.min(1, ((point.x - segStart.x) * dx + (point.y - segStart.y) * dy) / len2));
  const closest = new THREE.Vector3(
    segStart.x + t * dx,
    segStart.y + t * dy,
    0
  );

  return point.distanceTo(closest);
}

function showEdgeHud(registryEntry, x, y) {
  if (!hudEl || !registryEntry) return;

  // Use the SAME filtered, per-edge data as the AI Context Report: only amenities
  // within their threshold of THIS edge — not the global nearest list. This is why
  // the tooltip no longer repeats Train Station / Park on every edge.
  const ctx = registryEntry.edge_context || [];
  const displayName = registryEntry.label || "Unknown";

  const rows = ctx
    .slice(0, 5)
    .map((c) => `<div class="hud-row"><span>${c.label}</span><b>${c.distance}m</b></div>`)
    .join("");

  // Show the geographic direction and vector information
  const compassAng = Math.round(registryEntry.angle || 0);
  const compassSector = registryEntry.sector || "?";
  const vx = registryEntry.vx || 0;
  const vy = registryEntry.vy || 0;

  const diag = `<div class="hud-row" style="opacity:.7;border-top:1px solid #2a3a52;margin-top:4px;padding-top:4px">`
    + `<span>${compassAng}° → ${compassSector}</span><b>E${vx >= 0 ? "+" : ""}${vx} N${vy >= 0 ? "+" : ""}${vy}</b></div>`;

  // Display the tooltip — "No major amenities within close range." when nothing is close.
  const body = rows || '<div class="hud-row" style="opacity:.7">No major amenities within close range.</div>';
  hudEl.innerHTML = `<div class="hud-title">${displayName}</div>${body}${diag}`;
  hudEl.style.left = Math.min(x + 16, window.innerWidth - 230) + "px";
  hudEl.style.top = (y + 12) + "px";
  hudEl.classList.remove("hidden");
}
function hideEdgeHud() { hudEl?.classList.add("hidden"); }

function onCanvasClick(e) {
  e.stopPropagation();
  e.preventDefault();
  // Only show edge details on click, not on hover
  if (cam.dragging || cam.moved) {
    cam.moved = false;
    return; // Was a drag or pan, not a click
  }

  // Perform edge detection and show HUD on click
  edgeClick(e);
}

function edgeClick(e) {
  if (!edgeRegistry || Object.keys(edgeRegistry).length === 0) {
    return hideEdgeHud();
  }

  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

  // Project mouse to ground plane (z=0)
  raycaster.setFromCamera(pointer, camera);
  const t = -raycaster.ray.origin.z / raycaster.ray.direction.z;
  const mouseWorldPos = raycaster.ray.origin.clone().addScaledVector(raycaster.ray.direction, t);

  let selectedEdgeId = null;
  let closestDist = Infinity;

  // Find closest edge to click
  for (const edgeId in edgeRegistry) {
    const entry = edgeRegistry[edgeId];
    const a = new THREE.Vector3(entry.start_point[0], entry.start_point[1], 0);
    const b = new THREE.Vector3(entry.end_point[0], entry.end_point[1], 0);

    const dist = distancePointToSegment(mouseWorldPos, a, b);

    if (dist < closestDist) {
      closestDist = dist;
      selectedEdgeId = edgeId;
    }
  }

  // Show HUD if within click threshold (larger than hover threshold for easier clicking)
  const CLICK_THRESHOLD = 150;
  if (closestDist > CLICK_THRESHOLD) {
    return hideEdgeHud();
  }

  // Show the selected edge details
  if (!selectedEdgeId || !edgeRegistry[selectedEdgeId]) {
    return hideEdgeHud();
  }

  const registryEntry = edgeRegistry[selectedEdgeId];
  showEdgeHud(registryEntry, e.clientX, e.clientY);
  // F2: single click = select edge; Shift+click = add to multi-selection. Both are
  // stored so AI prompts can reference "the selected edge(s)".
  let nextEdges;
  if (e.shiftKey) {
    const cur = getState().selectedEdges || [];
    const exists = cur.some((x) => x.edge_id === registryEntry.edge_id);
    nextEdges = exists ? cur.filter((x) => x.edge_id !== registryEntry.edge_id) : [...cur, registryEntry];
    // eslint-disable-next-line no-console
    console.log("[edge-select] multi:", nextEdges.map((x) => x.label).join(", "));
  } else {
    nextEdges = [registryEntry];
    // eslint-disable-next-line no-console
    console.log("[edge-select]", registryEntry.label);
  }
  setState({ selectedEdge: registryEntry, selectedEdges: nextEdges });
  // Persist the selection to the backend so "align to selected edge" can use it.
  (async () => {
    try {
      const { api } = await import("../core/api.js");
      const sid = getState().sessionId;
      if (sid) await api.agent.storeSelection(sid, { selected_edge: registryEntry, selected_edges: nextEdges });
    } catch { /* non-fatal */ }
  })();
}

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
  if (ctx) {
    // Context data exists → render it and drop the scanning overlay. Only show the
    // scanner while we're genuinely still fetching (contextLoading && no data).
    renderContext();
  } else if (getState().contextLoading) {
    setLoading(true);
  }
}

export async function onAction(payload) {
  init();
  if (!payload || payload.action === "render_context" || payload.action === "render") {
    setLoading(false);
    renderContext();
  } else if (payload.action === "context_loading") {
    setLoading(true);
  }
}

// debug probes for verification (run in the browser console)
window.__ctxObjectCount = () => (rootGroup ? rootGroup.children.length : 0);
// Enable per-frame compass calculation logging: window.__ctxCompassDebug = true
window.__ctxCompassDebug = false;
// __ctxEdges() prints, per edge: the label + the LOCAL midpoint y (north is +y, so
// a "North" edge should have the LARGEST y; "South" the smallest). If a top-of-
// screen edge shows large +y but says "South", the label/geometry are inconsistent.
window.__ctxEdges = () => {
  const ctx = getState().context;
  if (!ctx) return "no context analyzed yet";
  const c = ctx.siteCentroidLocal || [0, 0];
  return (ctx.edges || []).map((e) => {
    const mx = (e.a[0] + e.b[0]) / 2, my = (e.a[1] + e.b[1]) / 2;
    const compassAng = Math.round(e.compassAngle || 0);
    const sector = e.compassSector || "?";
    return `Edge ${e.id}: ${e.direction} (compass ${compassAng}° → ${sector})  mid=[east:${(mx - c[0]).toFixed(0)}, north:${(my - c[1]).toFixed(0)}]`;
  });
};
// Debug: Print edge registry contents
window.__ctxRegistry = () => {
  const report = [];
  for (const edgeId in edgeRegistry) {
    const e = edgeRegistry[edgeId];
    report.push({
      "edge_id": edgeId,
      "label": e.label,
      "angle(°)": Math.round(e.angle || 0),
      "sector": e.sector,
      "vx": Math.round(e.vx || 0),
      "vy": Math.round(e.vy || 0),
    });
  }
  console.table(report);
  return report;
};

// Debug: Check for mismatches between backend ctx.edges and registry
window.__ctxVerifyRegistry = () => {
  const ctx = getState().context;
  if (!ctx || !ctx.edges) {
    console.log("[ERROR] No context data available");
    return;
  }

  console.log("[REGISTRY-VERIFY] Comparing backend ctx.edges vs edgeRegistry:");
  const issues = [];

  for (const e of ctx.edges) {
    const edgeId = e.edge_id || e.id;
    const registryEntry = edgeRegistry[edgeId];

    if (!registryEntry) {
      issues.push(`MISSING in registry: ${edgeId}`);
      continue;
    }

    // Check label mismatch
    const backendLabel = e.display_name || e.label;
    const registryLabel = registryEntry.label;
    if (backendLabel !== registryLabel) {
      issues.push(`Label mismatch ${edgeId}: backend="${backendLabel}" registry="${registryLabel}"`);
    }

    // Check angle mismatch
    const backendAngle = Math.round(e.compassAngle || 0);
    const registryAngle = Math.round(registryEntry.angle || 0);
    if (backendAngle !== registryAngle) {
      issues.push(`Angle mismatch ${edgeId}: backend=${backendAngle}° registry=${registryAngle}°`);
    }

    // Check sector mismatch
    const backendSector = e.compassSector || e.direction;
    const registrySector = registryEntry.sector;
    if (backendSector !== registrySector) {
      issues.push(`Sector mismatch ${edgeId}: backend="${backendSector}" registry="${registrySector}"`);
    }

    // Check vector mismatch
    const backendVx = Math.round(e.vx || 0);
    const registryVx = Math.round(registryEntry.vx || 0);
    if (backendVx !== registryVx) {
      issues.push(`Vector vx mismatch ${edgeId}: backend=${backendVx} registry=${registryVx}`);
    }
  }

  if (issues.length === 0) {
    console.log("[REGISTRY-VERIFY] ✓ All entries match! Registry is consistent.");
  } else {
    console.error("[REGISTRY-VERIFY] ✗ Found issues:");
    console.table(issues);
  }

  return issues;
};

// Debug: Detailed hover state report
window.__ctxHoverState = () => {
  console.log("[HOVER-STATE] Edge pickables count:", edgePickables.length);
  console.log("[HOVER-STATE] Edge registry count:", Object.keys(edgeRegistry).length);

  for (let i = 0; i < edgePickables.length; i++) {
    const line = edgePickables[i];
    const edgeId = line.userData.edge_id;
    const registryEntry = edgeRegistry[edgeId];
    console.log(`  Pickable[${i}]: edge_id="${edgeId}" → label="${registryEntry?.label || 'MISSING'}"`);
  }
};

// Debug: Simulate hover at specific registry entry
window.__ctxSimulateHover = (edgeId) => {
  const entry = edgeRegistry[edgeId];
  if (!entry) {
    console.error(`[SIMULATE] No registry entry for edge_id="${edgeId}"`);
    return;
  }
  console.log("[SIMULATE] Showing tooltip for:", entry.label);
  showEdgeHud(entry, 100, 100);  // Show at fixed position
};

// Toggle the centroid/midpoint/arrow debug overlay in the 3D twin.
window.__ctxDebug = (on = true) => {
  _ctxDebugOn = !!on;
  if (getState().context) renderContext();
  return `edge-side debug overlay ${_ctxDebugOn ? "ON" : "OFF"}`;
};

// COMPASS-EDGE ALIGNMENT VERIFICATION: Check that compass widget, 3D axes,
// and edge labels all agree on true north. Run this after context loads.
window.__ctxCompareDebug = () => {
  const ctx = getState().context;
  if (!ctx || !ctx.edges?.length) return "No context to verify";

  const c = ctx.siteCentroidLocal || [0, 0];
  console.log("\n%c=== COMPASS-EDGE ALIGNMENT VERIFICATION ===", "color:#ff5f6d; font-weight:bold");
  console.log("%c[System Coordinate Frame]", "color:#57f2e6; font-weight:bold");
  console.log("  Centroid:", c);
  console.log("  +X = TRUE EAST (red axis)");
  console.log("  +Y = TRUE NORTH (green axis)");
  console.log("  This is the SAME frame where atan2(vy, vx) calculates edge angles");

  console.log("\n%c[Compass Widget Calculation]", "color:#7c7bff; font-weight:bold");
  if (camera && cam) {
    const _np0 = new THREE.Vector3().set(cam.target.x, cam.target.y, 0).project(camera);
    const _np1 = new THREE.Vector3().set(cam.target.x, cam.target.y + 100, 0).project(camera);
    const sx = _np1.x - _np0.x;
    const sy = -(_np1.y - _np0.y);
    const screenNorthAngle = Math.atan2(sx, -sy) * (180 / Math.PI);
    console.log("  Projects: centroid →", [_np0.x.toFixed(2), _np0.y.toFixed(2)]);
    console.log("  Projects: north (+y) →", [_np1.x.toFixed(2), _np1.y.toFixed(2)]);
    console.log("  Screen vector: [sx=" + sx.toFixed(3) + ", sy=" + sy.toFixed(3) + "]");
    console.log("  Screen rotation angle:", Math.round(screenNorthAngle) + "°");
    console.log("  Compass dial CSS: rotate(" + Math.round(screenNorthAngle) + "deg)");
  } else {
    console.log("  Camera/target not available");
  }

  console.log("\n%c[Edge Angle Calculations]", "color:#57f2e6; font-weight:bold");
  const edgeDebug = ctx.edges.map((e) => {
    const mid = e.mid || [(e.a[0] + e.b[0]) / 2, (e.a[1] + e.b[1]) / 2];
    const vx = mid[0] - c[0];  // east component
    const vy = mid[1] - c[1];  // north component
    // This is exactly what compassAngle() does:
    let ang = Math.atan2(vy, vx) * (180 / Math.PI);
    if (ang < 0) ang += 360;
    const sector = e.compassSector || "?";
    const label = e.direction || "?";
    const vecMagnitude = Math.hypot(vx, vy);
    return {
      edge: e.id,
      vx: Math.round(vx),
      vy: Math.round(vy),
      magnitude: Math.round(vecMagnitude),
      angle: Math.round(ang) + "°",
      sector: sector,
      label: label,
      correct: (
        (label === "North" && vy > 0 && Math.abs(vx) < vy) ||
        (label === "South" && vy < 0 && Math.abs(vx) < -vy) ||
        (label === "East" && vx > 0 && Math.abs(vy) < vx) ||
        (label === "West" && vx < 0 && Math.abs(vy) < -vx) ||
        (label === "Northeast" && vx > 0 && vy > 0) ||
        (label === "Northwest" && vx < 0 && vy > 0) ||
        (label === "Southeast" && vx > 0 && vy < 0) ||
        (label === "Southwest" && vx < 0 && vy < 0)
      ) ? "✓" : "✗ MISMATCH"
    };
  });
  console.table(edgeDebug);

  console.log("\n%c[Sanity Check]", "color:#57e08a; font-weight:bold");
  const allCorrect = edgeDebug.every(e => e.correct === "✓");
  if (allCorrect) {
    console.log("✓ All edge labels match their vector directions");
    console.log("✓ Compass widget, 3D axes, and edge labels are ALIGNED");
  } else {
    console.log("✗ MISMATCH DETECTED: Some edges don't match their directions");
    console.log("✗ Check if edge angles are calculated in the same frame as compass");
    edgeDebug.filter(e => e.correct !== "✓").forEach(e => {
      console.log(`  Edge ${e.edge}: says "${e.label}" but vector is [${e.vx}, ${e.vy}]`);
    });
  }
  console.log("\n");

  return allCorrect ? "✓ All aligned" : "✗ Misalignment detected — see console";
};

// HOVER TOOLTIP DEBUG: Verify that visible label matches what would appear in hover tooltip
window.__ctxHoverDebugVerify = () => {
  const ctx = getState().context;
  if (!ctx || !ctx.edges?.length) return "No context to verify";

  console.log("\n%c=== HOVER TOOLTIP VERIFICATION ===", "color:#57f2e6; font-weight:bold");
  console.log("Comparing visible labels with hover tooltip metadata...\n");

  const verification = ctx.edges.map((e) => {
    const edgeId = e.edge_id || e.id;
    const visibleLabel = e.display_name || e.label;
    const direction = e.direction;
    const nearest = e.nearest || {};
    const nearestCount = Object.keys(nearest).length;

    return {
      edge_id: edgeId,
      visible_label: visibleLabel,
      direction: direction,
      nearest_features: nearestCount,
      has_metadata: {
        compassAngle: e.compassAngle !== undefined,
        compassSector: e.compassSector !== undefined,
        midpoint: e.midpoint !== undefined,
        centroid: e.centroid !== undefined,
        nearest: e.nearest !== undefined
      }
    };
  });

  console.table(verification);

  const allHaveMetadata = verification.every(e =>
    e.has_metadata.compassAngle &&
    e.has_metadata.compassSector &&
    e.has_metadata.midpoint &&
    e.has_metadata.centroid &&
    e.has_metadata.nearest
  );

  if (allHaveMetadata) {
    console.log("✓ All edges have complete metadata for hover tooltip");
  } else {
    console.log("✗ Some edges missing metadata:");
    verification.filter(e => !Object.values(e.has_metadata).every(v => v)).forEach(e => {
      console.log(`  Edge ${e.edge_id}: missing:`, Object.entries(e.has_metadata).filter(([k,v]) => !v).map(([k]) => k));
    });
  }

  console.log("\nTo test hover, enable logging:");
  console.log("  window.__ctxHoverDebug = true;");
  console.log("Then hover over edges to see tooltip metadata being read.\n");

  return allHaveMetadata ? "✓ All metadata present" : "✗ Missing metadata — see console";
};
