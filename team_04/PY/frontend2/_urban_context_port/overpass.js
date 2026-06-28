// Urban Context Analysis — fetches OpenStreetMap data for a 2 km radius around the
// confirmed site directly from the public Overpass API (browser → Overpass), then
// classifies it into road/amenity layers, computes per-edge proximity intelligence,
// derives 0–100 context scores, and produces an AI-style narrative report.
//
// Everything here is client-side and self-contained: no backend changes required.
// Coordinates are kept in two spaces:
//   • lng/lat (WGS84)  — for the Overpass query + raw OSM features
//   • local x/y metres — equirectangular projection around the site centroid, used
//     by the 3D digital-twin view and all distance maths.

export const CONTEXT_RADIUS_M = 2000;

// Public Overpass mirrors — tried in order so a single rate-limited/overloaded host
// doesn't break the feature.
const OVERPASS_ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
  "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
];

// ---------------------------------------------------------------------------
// Layer taxonomy. `id` is "group.key"; this drives the Context Explorer tree,
// the 3D view styling, and the scores. `style` carries the road color/dash and
// the marker color for amenities.
// ---------------------------------------------------------------------------
export const LAYER_DEFS = {
  // --- Roads (different color + line style per hierarchy) ---
  "roads.primary": { group: "Roads", label: "Primary", kind: "road", style: { color: "#ff5f6d", width: 4, dash: null } },
  "roads.secondary": { group: "Roads", label: "Secondary", kind: "road", style: { color: "#ffb454", width: 3, dash: [10, 0] } },
  "roads.tertiary": { group: "Roads", label: "Tertiary", kind: "road", style: { color: "#ffe27a", width: 2.5, dash: [8, 4] } },
  "roads.local": { group: "Roads", label: "Local", kind: "road", style: { color: "#7d8aa6", width: 1.5, dash: [3, 3] } },

  // --- Education ---
  "education.schools": { group: "Education", label: "Schools", kind: "amenity", style: { color: "#57f2e6", glyph: "🏫" } },
  "education.universities": { group: "Education", label: "Universities", kind: "amenity", style: { color: "#38bdf8", glyph: "🎓" } },

  // --- Transportation ---
  "transport.bus": { group: "Transportation", label: "Bus Stops", kind: "amenity", style: { color: "#a0f0c0", glyph: "🚌" } },
  "transport.metro": { group: "Transportation", label: "Metro Stations", kind: "amenity", style: { color: "#7c7bff", glyph: "🚇" } },
  "transport.train": { group: "Transportation", label: "Train Stations", kind: "amenity", style: { color: "#c08bff", glyph: "🚆" } },

  // --- Retail ---
  "retail.grocery": { group: "Retail", label: "Grocery", kind: "amenity", style: { color: "#ffd166", glyph: "🛒" } },
  "retail.shopping": { group: "Retail", label: "Shopping", kind: "amenity", style: { color: "#ff9f68", glyph: "🛍️" } },

  // --- Standalone groups (rendered as single leaves in the tree) ---
  "parks.parks": { group: "Parks", label: "Parks", kind: "park", style: { color: "#57e08a", glyph: "🌳" } },
  "healthcare.hospitals": { group: "Healthcare", label: "Hospitals", kind: "amenity", style: { color: "#ff5f6d", glyph: "🏥" } },

  // --- Extra amenities requested (counted + shown, no dedicated tree leaf row) ---
  "extra.restaurants": { group: "Retail", label: "Restaurants", kind: "amenity", style: { color: "#ffb4a0", glyph: "🍽️" }, hiddenInTree: true },
  "extra.public": { group: "Healthcare", label: "Public Facilities", kind: "amenity", style: { color: "#9fd0ff", glyph: "🏛️" }, hiddenInTree: true },
};

export const LAYER_IDS = Object.keys(LAYER_DEFS);

// ---------------------------------------------------------------------------
// Geo helpers (equirectangular local projection — accurate enough at 2 km).
// ---------------------------------------------------------------------------
const R_EARTH = 6378137;
const DEG = Math.PI / 180;

export function makeProjector(center) {
  const cosLat = Math.cos(center.lat * DEG);
  return {
    toLocal(lng, lat) {
      return [
        (lng - center.lng) * DEG * R_EARTH * cosLat,
        (lat - center.lat) * DEG * R_EARTH,
      ];
    },
  };
}

function haversine(a, b) {
  const dLat = (b.lat - a.lat) * DEG;
  const dLng = (b.lng - a.lng) * DEG;
  const la1 = a.lat * DEG, la2 = b.lat * DEG;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) ** 2;
  return 2 * R_EARTH * Math.asin(Math.sqrt(h));
}

function centroid(ring) {
  let x = 0, y = 0;
  for (const p of ring) { x += p[0]; y += p[1]; }
  return { lng: x / ring.length, lat: y / ring.length };
}

// distance (m) from point P to segment AB, all in local metres
function pointToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  const len2 = dx * dx + dy * dy || 1e-9;
  let t = ((px - ax) * dx + (py - ay) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  const cx = ax + t * dx, cy = ay + t * dy;
  return Math.hypot(px - cx, py - cy);
}

// ---------------------------------------------------------------------------
// Overpass query for everything we need inside the radius.
// ---------------------------------------------------------------------------
function buildQuery(center, radius) {
  const c = `${center.lat},${center.lng}`;
  return `
[out:json][timeout:50];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street|service)$"](around:${radius},${c});
  node["amenity"~"^(school|college|university|hospital|clinic|restaurant|fast_food|cafe|townhall|library|community_centre|police|fire_station)$"](around:${radius},${c});
  way["amenity"~"^(school|college|university|hospital)$"](around:${radius},${c});
  node["shop"~"^(supermarket|convenience|grocery|mall|department_store)$"](around:${radius},${c});
  way["shop"~"^(supermarket|mall|department_store)$"](around:${radius},${c});
  node["highway"="bus_stop"](around:${radius},${c});
  node["railway"~"^(station|subway_entrance|halt|tram_stop)$"](around:${radius},${c});
  node["station"~"^(subway|light_rail)$"](around:${radius},${c});
  way["leisure"="park"](around:${radius},${c});
  way["leisure"~"^(garden|recreation_ground)$"](around:${radius},${c});
  way["building"](around:${Math.min(radius, 900)},${c});
);
out body geom;
`.trim();
}

async function runOverpass(query) {
  let lastErr;
  for (const url of OVERPASS_ENDPOINTS) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "data=" + encodeURIComponent(query),
      });
      if (!res.ok) { lastErr = new Error(`Overpass ${res.status}`); continue; }
      return await res.json();
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("All Overpass endpoints failed");
}

// ---------------------------------------------------------------------------
// Classification — map raw OSM elements into our layer buckets.
// ---------------------------------------------------------------------------
function classifyRoad(tags) {
  const hw = tags.highway;
  if (hw === "motorway" || hw === "trunk" || hw === "primary") return "roads.primary";
  if (hw === "secondary") return "roads.secondary";
  if (hw === "tertiary") return "roads.tertiary";
  if (["residential", "unclassified", "living_street", "service"].includes(hw)) return "roads.local";
  return null;
}

function classifyPoint(tags) {
  const a = tags.amenity, shop = tags.shop, rail = tags.railway, st = tags.station;
  if (a === "school") return "education.schools";
  if (a === "college" || a === "university") return "education.universities";
  if (a === "hospital" || a === "clinic") return "healthcare.hospitals";
  if (a === "restaurant" || a === "fast_food" || a === "cafe") return "extra.restaurants";
  if (["townhall", "library", "community_centre", "police", "fire_station"].includes(a)) return "extra.public";
  if (shop === "supermarket" || shop === "convenience" || shop === "grocery") return "retail.grocery";
  if (shop === "mall" || shop === "department_store") return "retail.shopping";
  if (tags.highway === "bus_stop") return "transport.bus";
  if (st === "subway" || st === "light_rail" || rail === "subway_entrance" || rail === "tram_stop") return "transport.metro";
  if (rail === "station" || rail === "halt") {
    // a station tagged subway/light_rail is metro; otherwise treat as train
    if (st === "subway" || st === "light_rail") return "transport.metro";
    return "transport.train";
  }
  return null;
}

// ---------------------------------------------------------------------------
// Main entry: fetch + classify + project + score + report.
// `site` = { center:{lng,lat}, boundary:[[lng,lat],...] }
// Returns the `context` object stored in state.
// ---------------------------------------------------------------------------
export async function analyzeContext(site, { radius = CONTEXT_RADIUS_M } = {}) {
  const center = site.center;
  const proj = makeProjector(center);

  let json;
  try {
    json = await runOverpass(buildQuery(center, radius));
  } catch (e) {
    // Overpass unavailable (offline / CORS / rate limit). Fall back to a
    // procedurally-generated sample context so the stage is still demoable.
    return synthContext(site, proj, radius, e.message);
  }

  const layers = {};
  for (const id of LAYER_IDS) layers[id] = { id, ...LAYER_DEFS[id], roads: [], points: [], polys: [] };

  const buildings = [];

  for (const el of json.elements || []) {
    const tags = el.tags || {};

    // Roads (ways with geometry)
    if (el.type === "way" && tags.highway && el.geometry) {
      const lid = classifyRoad(tags);
      if (lid) {
        const path = el.geometry.map((g) => proj.toLocal(g.lon, g.lat));
        const lnglat = el.geometry.map((g) => [g.lon, g.lat]);
        layers[lid].roads.push({ path, lnglat, name: tags.name || "" });
        continue;
      }
    }

    // Building footprints (extruded in the 3D view)
    if (el.type === "way" && tags.building && el.geometry && el.geometry.length >= 3) {
      const fp = el.geometry.map((g) => proj.toLocal(g.lon, g.lat));
      const lvls = parseFloat(tags["building:levels"]) || 0;
      const h = parseFloat(tags.height) || (lvls ? lvls * 3.2 : 8 + Math.random() * 22);
      buildings.push({ footprint: fp, height: h });
      continue;
    }

    // Amenity / area features
    const center2 = el.type === "way" && el.geometry
      ? centroid(el.geometry.map((g) => [g.lon, g.lat]))
      : { lng: el.lon, lat: el.lat };

    // Parks (areas) — keep polygon + centroid
    if (el.type === "way" && (tags.leisure === "park" || tags.leisure === "garden" || tags.leisure === "recreation_ground") && el.geometry) {
      const poly = el.geometry.map((g) => proj.toLocal(g.lon, g.lat));
      const [x, y] = proj.toLocal(center2.lng, center2.lat);
      layers["parks.parks"].polys.push({ poly, x, y, name: tags.name || "Park" });
      continue;
    }

    if (center2.lng == null || center2.lat == null) continue;
    const lid = classifyPoint(tags);
    if (lid && layers[lid]) {
      const [x, y] = proj.toLocal(center2.lng, center2.lat);
      layers[lid].points.push({ x, y, lng: center2.lng, lat: center2.lat, name: tags.name || LAYER_DEFS[lid].label });
    }
  }

  return assemble(site, proj, radius, layers, buildings, null);
}

// Build the final context object: counts, nearest-distances, edges, scores, report.
function assemble(site, proj, radius, layers, buildings, note) {
  const boundaryLocal = (site.boundary || []).map((p) => proj.toLocal(p[0], p[1]));
  const siteCentroidLocal = boundaryLocal.length
    ? boundaryLocal.reduce((a, p) => [a[0] + p[0], a[1] + p[1]], [0, 0]).map((v) => v / boundaryLocal.length)
    : [0, 0];

  // Per-layer count + nearest distance to the site (centroid-based).
  for (const id of LAYER_IDS) {
    const L = layers[id];
    L.count = L.roads.length + L.points.length + L.polys.length;
    L.nearest = nearestDistanceToSite(L, boundaryLocal, siteCentroidLocal);
  }

  const edges = computeEdgeIntelligence(boundaryLocal, layers, site.boundary);
  const scores = computeScores(layers, edges);
  const report = buildReport(edges, scores, layers, note);

  return {
    center: site.center,
    radius,
    siteBoundaryLocal: boundaryLocal,
    siteCentroidLocal,
    layers,
    buildings,
    edges,
    scores,
    report,
    note, // non-null when we fell back to synthetic data
    generatedAt: Date.now(),
  };
}

function nearestDistanceToSite(layer, boundaryLocal, siteC) {
  let min = Infinity;
  const measure = (x, y) => {
    // distance from point to nearest boundary edge (0 if effectively adjacent)
    if (boundaryLocal.length >= 2) {
      for (let i = 0; i < boundaryLocal.length; i++) {
        const a = boundaryLocal[i], b = boundaryLocal[(i + 1) % boundaryLocal.length];
        min = Math.min(min, pointToSegment(x, y, a[0], a[1], b[0], b[1]));
      }
    } else {
      min = Math.min(min, Math.hypot(x - siteC[0], y - siteC[1]));
    }
  };
  layer.points.forEach((p) => measure(p.x, p.y));
  layer.polys.forEach((p) => measure(p.x, p.y));
  layer.roads.forEach((r) => r.path.forEach((pt) => measure(pt[0], pt[1])));
  return Number.isFinite(min) ? Math.round(min) : null;
}

// ---------------------------------------------------------------------------
// Site Edge Intelligence — for each boundary edge, nearest feature of each type.
// Edges are labelled A, B, C… and tagged with a compass direction.
// ---------------------------------------------------------------------------
const EDGE_LABELS = "ABCDEFGHIJKLMNOP".split("");

function bearingToCompass(dx, dy) {
  // dy points north (+y). Angle measured from north, clockwise.
  const ang = (Math.atan2(dx, dy) * 180) / Math.PI;
  const a = (ang + 360) % 360;
  if (a >= 315 || a < 45) return "North";
  if (a < 135) return "East";
  if (a < 225) return "South";
  return "West";
}

const NEAREST_OF = [
  { layer: "transport.metro", label: "Metro" },
  { layer: "transport.bus", label: "Bus Stop" },
  { layer: "transport.train", label: "Train Station" },
  { layer: "parks.parks", label: "Park" },
  { layer: "roads.primary", label: "Primary Road" },
  { layer: "education.schools", label: "School" },
  { layer: "education.universities", label: "University" },
  { layer: "retail.grocery", label: "Grocery Store" },
  { layer: "retail.shopping", label: "Shopping" },
  { layer: "healthcare.hospitals", label: "Hospital" },
];

function computeEdgeIntelligence(boundaryLocal, layers, boundaryLngLat) {
  const edges = [];
  if (boundaryLocal.length < 2) return edges;
  const n = boundaryLocal.length;
  for (let i = 0; i < n; i++) {
    const a = boundaryLocal[i];
    const b = boundaryLocal[(i + 1) % n];
    const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    // outward normal direction ≈ midpoint relative to centroid
    const dir = bearingToCompass(mid[0], mid[1]);
    const nearest = {};
    for (const { layer, label } of NEAREST_OF) {
      const d = nearestFeatureToSegment(layers[layer], a, b);
      if (d != null) nearest[label] = d;
    }
    edges.push({
      id: EDGE_LABELS[i] || `E${i + 1}`,
      direction: dir,
      a, b, mid,
      lnglat: boundaryLngLat ? [boundaryLngLat[i], boundaryLngLat[(i + 1) % n]] : null,
      nearest, // { "Metro": 320, "Park": 180, ... } metres
    });
  }
  return edges;
}

function nearestFeatureToSegment(layer, a, b) {
  if (!layer) return null;
  let min = Infinity;
  const test = (x, y) => { min = Math.min(min, pointToSegment(x, y, a[0], a[1], b[0], b[1])); };
  layer.points.forEach((p) => test(p.x, p.y));
  layer.polys.forEach((p) => test(p.x, p.y));
  layer.roads.forEach((r) => r.path.forEach((pt) => test(pt[0], pt[1])));
  return Number.isFinite(min) ? Math.round(min) : null;
}

// ---------------------------------------------------------------------------
// Context scores (0–100). Each combines a count signal (how much is nearby) and
// a proximity signal (how close the nearest one is). Tuned for a 2 km radius.
// ---------------------------------------------------------------------------
function proxScore(dist, good, far) {
  // 100 at <=good metres, 0 at >=far metres, linear between.
  if (dist == null) return 0;
  if (dist <= good) return 100;
  if (dist >= far) return 0;
  return Math.round(100 * (1 - (dist - good) / (far - good)));
}
function countScore(n, target) {
  return Math.round(100 * (1 - Math.exp(-n / target)));
}
function clamp(v) { return Math.max(0, Math.min(100, Math.round(v))); }
function cnt(L, id) { return L[id]?.count || 0; }
function near(L, id) { return L[id]?.nearest; }

export function computeScores(L, edges) {
  const transit = clamp(
    0.5 * proxScore(Math.min(near(L, "transport.metro") ?? 9e9, near(L, "transport.train") ?? 9e9), 200, 1500) +
    0.3 * countScore(cnt(L, "transport.bus"), 12) +
    0.2 * countScore(cnt(L, "transport.metro") + cnt(L, "transport.train"), 2)
  );
  const greenSpace = clamp(
    0.6 * proxScore(near(L, "parks.parks"), 120, 1200) +
    0.4 * countScore(cnt(L, "parks.parks"), 4)
  );
  const education = clamp(
    0.4 * proxScore(near(L, "education.schools"), 200, 1500) +
    0.3 * countScore(cnt(L, "education.schools"), 4) +
    0.3 * proxScore(near(L, "education.universities"), 500, 2000)
  );
  const retail = clamp(
    0.4 * proxScore(near(L, "retail.grocery"), 150, 1000) +
    0.3 * countScore(cnt(L, "retail.grocery"), 6) +
    0.3 * (countScore(cnt(L, "retail.shopping"), 2) * 0.6 + countScore(cnt(L, "extra.restaurants"), 15) * 0.4)
  );
  const healthcare = clamp(
    0.6 * proxScore(near(L, "healthcare.hospitals"), 400, 2000) +
    0.4 * countScore(cnt(L, "healthcare.hospitals"), 2)
  );
  // road hierarchy access → connectivity
  const connectivity = clamp(
    0.4 * proxScore(near(L, "roads.primary"), 60, 800) +
    0.3 * countScore(cnt(L, "roads.primary") + cnt(L, "roads.secondary"), 6) +
    0.3 * countScore(cnt(L, "roads.tertiary") + cnt(L, "roads.local"), 30)
  );
  const amenityTotal = cnt(L, "retail.grocery") + cnt(L, "retail.shopping") + cnt(L, "extra.restaurants") +
    cnt(L, "education.schools") + cnt(L, "education.universities") + cnt(L, "healthcare.hospitals") + cnt(L, "extra.public");
  const amenity = clamp(countScore(amenityTotal, 25));
  // walkability blends nearby amenities, density of local roads, parks proximity
  const walkability = clamp(0.45 * amenity + 0.3 * greenSpace + 0.25 * connectivity);
  const accessibility = clamp(0.55 * transit + 0.45 * connectivity);
  const urbanVitality = clamp(0.3 * amenity + 0.25 * transit + 0.2 * walkability + 0.15 * retail + 0.1 * greenSpace);

  return {
    transit, walkability, education, greenSpace, retail,
    healthcare, accessibility, connectivity, amenity, urbanVitality,
  };
}

// Display metadata for KPI cards + optimization weighting.
export const SCORE_META = [
  { key: "transit", label: "Transit", glyph: "🚇" },
  { key: "walkability", label: "Walkability", glyph: "🚶" },
  { key: "education", label: "Education", glyph: "🎓" },
  { key: "greenSpace", label: "Green Space", glyph: "🌳" },
  { key: "retail", label: "Retail", glyph: "🛍️" },
  { key: "healthcare", label: "Healthcare", glyph: "🏥" },
  { key: "accessibility", label: "Accessibility", glyph: "♿" },
  { key: "connectivity", label: "Connectivity", glyph: "🛣️" },
  { key: "amenity", label: "Amenity", glyph: "✨" },
  { key: "urbanVitality", label: "Urban Vitality", glyph: "🌆" },
];

export function scoreColor(v) {
  if (v >= 80) return "#57e08a";
  if (v >= 60) return "#28e0d0";
  if (v >= 40) return "#ffb454";
  return "#ff5f6d";
}

// ---------------------------------------------------------------------------
// AI-style narrative report. Deterministic, derived from edges + scores so it
// reads like the Copilot summarised the context.
// ---------------------------------------------------------------------------
function m(v) { return v == null ? null : `${v}m`; }

function buildReport(edges, scores, layers, note) {
  const edgeLines = edges.map((e) => {
    const bits = [];
    const n = e.nearest;
    if (n.Metro != null) bits.push(`${m(n.Metro)} from Metro Station`);
    else if (n["Train Station"] != null) bits.push(`${m(n["Train Station"])} from Train Station`);
    if (n.Park != null) bits.push(`${m(n.Park)} from Public Park`);
    if (n["Primary Road"] != null && n["Primary Road"] <= 40) bits.push("Adjacent to Primary Road");
    else if (n["Primary Road"] != null && n["Primary Road"] <= 150) bits.push("Strong visibility corridor");
    if (n["Grocery Store"] != null && n["Grocery Store"] <= 400) bits.push("Near mixed-use retail district");
    if (n.School != null && n.School <= 400) bits.push("Close to educational facilities");
    if (n["Bus Stop"] != null && bits.length < 2) bits.push(`${m(n["Bus Stop"])} from Bus Stop`);
    return { title: `${e.direction} Edge (${e.id})`, items: bits.length ? bits : ["Limited nearby context"] };
  });

  const opportunities = [];
  if (scores.transit >= 75) opportunities.push("Strong transit-oriented development potential");
  if (scores.walkability >= 70) opportunities.push("High walkability");
  if (scores.accessibility >= 75) opportunities.push("Excellent public transport access");
  if (scores.greenSpace >= 70) opportunities.push("Preserve view corridors toward green space");
  if (scores.retail >= 70) opportunities.push("Activate street-facing retail edges");
  if (scores.healthcare >= 70) opportunities.push("Proximity to healthcare supports mixed-use / senior living");
  if (!opportunities.length) opportunities.push("Balanced site — flexible programming options");

  return { edgeLines, opportunities, scores };
}

// Markdown version for the Copilot chat bubble.
export function reportToMarkdown(ctx) {
  const { report, scores } = ctx;
  const lines = ["**Urban Context Summary**", ""];
  for (const e of report.edgeLines) {
    lines.push(`**${e.title}:**`);
    for (const it of e.items) lines.push(`• ${it}`);
    lines.push("");
  }
  lines.push("**Context Scores**");
  for (const sm of SCORE_META) lines.push(`• ${sm.label} Score: ${scores[sm.key]}`);
  lines.push("");
  lines.push("**Opportunities:**");
  for (const o of report.opportunities) lines.push(`• ${o}`);
  if (ctx.note) lines.push("", `*(${ctx.note} — showing representative sample context.)*`);
  return lines.join("\n");
}

// Context-aware design guidance fed into shape generation / optimization.
export function designGuidance(scores) {
  const g = [];
  if (scores.transit >= 75) g.push("high transit access → favour higher-density development");
  if (scores.greenSpace >= 70) g.push("strong green space → preserve view corridors and maximise landscape integration");
  if (scores.accessibility >= 75) g.push("high accessibility → favour mixed-use development");
  if (scores.retail >= 70) g.push("strong retail context → activate street-facing edges");
  if (scores.walkability >= 70) g.push("high walkability → permeable ground floor, pedestrian frontage");
  return g;
}

// ---------------------------------------------------------------------------
// Synthetic fallback when Overpass is unreachable. Produces a believable city
// fabric around the site so the whole stage (3D view, scores, report) works
// offline / behind CORS. Flagged via `note` so the UI can say so.
// ---------------------------------------------------------------------------
function synthContext(site, proj, radius, why) {
  const layers = {};
  for (const id of LAYER_IDS) layers[id] = { id, ...LAYER_DEFS[id], roads: [], points: [], polys: [] };
  const rnd = mulberry32(0x7e44a1);
  const R = radius * 0.92;

  // radial + ring road grid
  const ringR = [350, 800, 1400];
  for (const rr of ringR) {
    const path = [];
    const ll = [];
    for (let t = 0; t <= 64; t++) {
      const ang = (t / 64) * Math.PI * 2;
      path.push([Math.cos(ang) * rr, Math.sin(ang) * rr]);
    }
    const lid = rr === 800 ? "roads.primary" : rr === 1400 ? "roads.secondary" : "roads.tertiary";
    layers[lid].roads.push({ path, lnglat: ll, name: "Ring" });
  }
  for (let i = 0; i < 10; i++) {
    const ang = (i / 10) * Math.PI * 2;
    const path = [[0, 0], [Math.cos(ang) * R, Math.sin(ang) * R]];
    const lid = i % 3 === 0 ? "roads.primary" : i % 3 === 1 ? "roads.secondary" : "roads.local";
    layers[lid].roads.push({ path, lnglat: [], name: "Radial" });
  }
  // a denser local-road grid
  for (let gx = -R; gx <= R; gx += 220) {
    layers["roads.local"].roads.push({ path: [[gx, -R], [gx, R]], lnglat: [], name: "" });
    layers["roads.local"].roads.push({ path: [[-R, gx], [R, gx]], lnglat: [], name: "" });
  }

  const scatter = (id, n, glyphName) => {
    for (let i = 0; i < n; i++) {
      const ang = rnd() * Math.PI * 2;
      const d = Math.sqrt(rnd()) * R;
      layers[id].points.push({ x: Math.cos(ang) * d, y: Math.sin(ang) * d, lng: null, lat: null, name: glyphName });
    }
  };
  scatter("transport.bus", 18, "Bus Stop");
  scatter("transport.metro", 3, "Metro");
  scatter("transport.train", 1, "Train Station");
  scatter("education.schools", 6, "School");
  scatter("education.universities", 2, "University");
  scatter("retail.grocery", 9, "Grocery");
  scatter("retail.shopping", 3, "Mall");
  scatter("healthcare.hospitals", 2, "Hospital");
  scatter("extra.restaurants", 22, "Restaurant");
  scatter("extra.public", 5, "Public Facility");

  // parks
  for (let i = 0; i < 5; i++) {
    const ang = rnd() * Math.PI * 2, d = 200 + rnd() * (R - 300);
    const cx = Math.cos(ang) * d, cy = Math.sin(ang) * d;
    const w = 120 + rnd() * 260, h = 120 + rnd() * 260;
    layers["parks.parks"].polys.push({
      x: cx, y: cy, name: "Park",
      poly: [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]],
    });
  }

  // surrounding buildings
  const buildings = [];
  for (let i = 0; i < 220; i++) {
    const ang = rnd() * Math.PI * 2, d = 120 + Math.sqrt(rnd()) * (R - 200);
    const cx = Math.cos(ang) * d, cy = Math.sin(ang) * d;
    const w = 14 + rnd() * 30, h2 = 14 + rnd() * 30;
    buildings.push({
      footprint: [[cx - w / 2, cy - h2 / 2], [cx + w / 2, cy - h2 / 2], [cx + w / 2, cy + h2 / 2], [cx - w / 2, cy + h2 / 2]],
      height: 8 + rnd() * (d < 600 ? 70 : 28),
    });
  }

  return assemble(site, proj, radius, layers, buildings,
    `Live OpenStreetMap data unavailable (${why})`);
}

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
