// Map view: MapLibre OSM base map with a draggable location pin and Google-Earth
// style boundary drawing/editing. Reacts to orchestrator payloads via onAction().
//
// Patterns (OSM raster style, geojson sources/layers, vertex markers) are adapted
// from the legacy frontend/app.js.

import { getState, setState, subscribe, isScanning } from "../core/store.js";

let map = null;
let ready = false;
let sourcesReady = false;
let pin = null;
let drawing = false;
let draft = []; // [[lng,lat], ...] open ring while drawing
let vertexMarkers = [];

// Toggle the center scan HUD purely from the combined isScanning() store flag.
function syncScan() {
  const hud = document.getElementById("map-hud");
  if (hud) hud.classList.toggle("scanning", isScanning());
}
let scanSubscribed = false;

// Dark OpenStreetMap with clear building/boundary visibility
// Uses raster OSM with dark overlay to match theme while keeping plots visible
const TILE_STYLE = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: [
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#05080f" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.7, "raster-fade-duration": 0 } },
    // Dark overlay to reduce brightness while keeping details visible
    { id: "dark-overlay", type: "background", paint: { "background-color": "rgba(5, 8, 15, 0.4)" } },
  ],
};

function closeRing(points) {
  const ring = points.map((p) => [Number(p[0]), Number(p[1])]);
  if (ring.length >= 1) {
    const a = ring[0];
    const b = ring[ring.length - 1];
    if (a[0] !== b[0] || a[1] !== b[1]) ring.push([a[0], a[1]]);
  }
  return ring;
}

function ensureMap() {
  if (map) return map;
  const el = document.getElementById("view-map");
  el.innerHTML = ""; // clear placeholder
  map = new maplibregl.Map({
    container: el,
    style: TILE_STYLE,
    center: [77.5946, 12.9716],
    zoom: 12,
    attributionControl: false,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.on("load", () => {
    ready = true;
    ensureSources();
    bindDrawHandlers();
  });
  // Futuristic HUD overlay above the map canvas: radar grid + scanning line.
  // pointer-events:none so all map interaction (pan/zoom/draw) is unaffected.
  // The scan only animates when the `.scanning` class is set (see syncScan()).
  const hud = document.createElement("div");
  hud.id = "map-hud";
  hud.innerHTML = `
    <div class="map-grid"></div>
    <div class="map-radar"></div>
    <div class="map-scan">
      <div class="scan-glow"></div>
      <div class="scan-line"></div>
    </div>
    <div class="map-vignette"></div>`;
  el.appendChild(hud);
  if (!scanSubscribed) { subscribe(syncScan); scanSubscribed = true; }
  syncScan();
  return map;
}

function ensureSources() {
  if (!map || sourcesReady) return;
  sourcesReady = true;
  const add = (name) => {
    if (!map.getSource(name)) map.addSource(name, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  };
  ["site-boundary", "draft-boundary", "draw-preview"].forEach(add);
  const layers = [
    { id: "site-boundary-fill", type: "fill", source: "site-boundary", paint: { "fill-color": "#28e0d0", "fill-opacity": 0.16 } },
    { id: "site-boundary-line", type: "line", source: "site-boundary", paint: { "line-color": "#28e0d0", "line-width": 3 } },
    { id: "draft-fill", type: "fill", source: "draft-boundary", paint: { "fill-color": "#7c7bff", "fill-opacity": 0.2 } },
    { id: "draft-line", type: "line", source: "draft-boundary", paint: { "line-color": "#7c7bff", "line-width": 2.5 } },
    { id: "preview-line", type: "line", source: "draw-preview", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": "#7c7bff", "line-width": 2, "line-dasharray": [4, 3] } },
  ];
  layers.forEach((l) => { if (!map.getLayer(l.id)) map.addLayer(l); });
}

function setSource(name, geometry) {
  if (!map || !map.getSource(name)) return;
  const features = geometry && geometry.coordinates && geometry.coordinates.length
    ? [{ type: "Feature", geometry, properties: {} }]
    : [];
  map.getSource(name).setData({ type: "FeatureCollection", features });
}

// ---- location pin ----
function placePin(lng, lat, draggable = true) {
  if (!pin) {
    pin = new maplibregl.Marker({ color: "#28e0d0", draggable });
    pin.setLngLat([lng, lat]).addTo(map);
    pin.on("dragend", () => {
      const ll = pin.getLngLat();
      const loc = getState().location || {};
      setState({ location: { ...loc, lng: ll.lng, lat: ll.lat } });
    });
  } else {
    pin.setLngLat([lng, lat]);
  }
}

// Boundary action buttons shown in the Copilot once a polygon is complete.
const BOUNDARY_ACTIONS = [
  { label: "Save Boundary", intent: "save_boundary", primary: true },
  { label: "Edit Boundary", intent: "draw_boundary" },
  { label: "Reset Boundary", intent: "reset_boundary" },
];

// ---- boundary drawing (Google-Earth style) ----
function refreshDraft() {
  setSource("draft-boundary", draft.length >= 3 ? { type: "Polygon", coordinates: [closeRing(draft)] } : null);
  setSource("draw-preview", draft.length >= 1 ? { type: "LineString", coordinates: draft } : null);
  renderVertexMarkers();

  const complete = draft.length >= 3;
  const patch = { boundary: draft.slice(), boundarySaved: false };
  // Surface Save/Edit/Reset once the polygon closes; clear them while it's
  // still being outlined, so the user is guided without manual navigation.
  if (drawing) {
    const current = getState().actions || [];
    const showing = current.some((a) => a.intent === "save_boundary");
    if (complete && !showing) patch.actions = BOUNDARY_ACTIONS;
    else if (!complete && showing) patch.actions = [];
  }
  setState(patch);
}

function clearVertexMarkers() {
  vertexMarkers.forEach((m) => m.remove());
  vertexMarkers = [];
}

function renderVertexMarkers() {
  clearVertexMarkers();
  if (!drawing) return;
  draft.forEach((pt, i) => {
    const el = document.createElement("div");
    el.style.cssText = "width:14px;height:14px;border-radius:50%;background:#7c7bff;border:2px solid #fff;cursor:grab;box-shadow:0 0 10px rgba(124,123,255,0.8);";
    const m = new maplibregl.Marker({ element: el, draggable: true }).setLngLat(pt).addTo(map);
    m.on("drag", () => { const ll = m.getLngLat(); draft[i] = [ll.lng, ll.lat]; });
    m.on("dragend", () => refreshDraft());
    // right-click a vertex to delete it
    el.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      if (draft.length > 3) { draft.splice(i, 1); refreshDraft(); }
    });
    vertexMarkers.push(m);
  });
}

let handlersBound = false;
function bindDrawHandlers() {
  if (handlersBound || !map) return;
  handlersBound = true;
  map.on("click", (e) => {
    if (!drawing) return;
    draft.push([e.lngLat.lng, e.lngLat.lat]);
    refreshDraft();
  });
  map.getCanvas().addEventListener("contextmenu", (e) => e.preventDefault());
}

function startDrawing(reset = true) {
  drawing = true;
  if (reset) draft = [];
  if (map) map.getCanvas().style.cursor = "crosshair";
  refreshDraft();
  // The Copilot reply already explains how to draw; no duplicate chat message.
}

function stopDrawing() {
  drawing = false;
  if (map) map.getCanvas().style.cursor = "";
  clearVertexMarkers();
}

// ---------------------------------------------------------------------------
export function activate() {
  ensureMap();
  // map needs a resize when its container becomes visible
  setTimeout(() => { if (map) map.resize(); }, 60);
}

export async function onAction(payload) {
  ensureMap();
  const run = () => {
    const action = payload.action;
    if (action === "fly_to") {
      const c = payload.site?.center || {};
      const lng = Number(c.lng), lat = Number(c.lat);
      if (Number.isFinite(lng) && Number.isFinite(lat) && (lng || lat)) {
        map.easeTo({ center: [lng, lat], zoom: 16, duration: 800 });
        placePin(lng, lat, true);
        // location detected & map is flying -> stop the "locating" scan phase
        setState({ location: { name: payload.site?.location_name || "", lng, lat }, locationSaved: false, isLocatingSite: false });
      }
    } else if (action === "show_boundary") {
      const site = payload.site || {};
      const geo = site.confirmed_site_boundary?.coordinates?.length
        ? site.confirmed_site_boundary
        : site.boundary_geojson?.coordinates?.length
          ? site.boundary_geojson
          : null;
      if (geo) setSource("site-boundary", geo);
      setState({ locationSaved: true });
      if (pin) pin.setDraggable(false);
      // auto-enter drawing if no boundary exists yet
      if (!geo) startDrawing(true);
    } else if (action === "enable_draw") {
      startDrawing(true);
      // boundary drawing tool is now active -> stop the "activating" scan phase
      setState({ isBoundaryActivating: false });
    } else if (action === "boundary_saved") {
      stopDrawing();
      const geo = payload.site?.confirmed_site_boundary || (draft.length >= 3 ? { type: "Polygon", coordinates: [closeRing(draft)] } : null);
      if (geo) setSource("site-boundary", geo);
      setSource("draft-boundary", null);
      setSource("draw-preview", null);
      setState({ boundarySaved: true, site: payload.site || getState().site });
    }
  };
  if (ready) run();
  else map.once("load", run);
}
