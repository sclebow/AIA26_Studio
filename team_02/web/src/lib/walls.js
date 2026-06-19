// Derive the wall network for the floor plan.
//
// The layout's `structure` array is sparse (a few named partitions), so it is NOT a
// reliable source of interior walls. The complete partition set is implicit in the
// SHARED EDGES of the room polygons: rooms tile the outline, so every interior wall is
// an edge shared by two rooms (or a room edge facing unfilled space), and every
// exterior wall is a room/outline edge on the building perimeter.
//
// deriveWalls() collects every room + outline edge, classifies orientation, and merges
// COLLINEAR-OVERLAPPING edges into one wall segment per unique wall line (so a partition
// shared by N rooms — or quoted in pieces — becomes a single band). Each segment is
// addressable (stable id) so later edit tools (B3) can target a wall.
//
// All coordinates are MODEL metres (y NOT flipped) — the layer applies `fy` at render
// time, exactly like geometry.js helpers.

export const WALL_TOL = 0.02; // metres; matches the python geometry checker's tolerance

const quant = (v) => Math.round(v / WALL_TOL); // bucket key — collapses float drift

// Edges of a ring [[x,y],…]. Closes the polygon; drops a duplicate trailing vertex.
export function edgesOf(poly = []) {
  if (!poly || poly.length < 2) return [];
  const closed = poly[0][0] === poly.at(-1)[0] && poly[0][1] === poly.at(-1)[1];
  const pts = closed ? poly.slice(0, -1) : poly.slice();
  const out = [];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    if (a && b) out.push({ x1: a[0], y1: a[1], x2: b[0], y2: b[1] });
  }
  return out;
}

// 'h' = horizontal (constant y), 'v' = vertical (constant x), 'd' = diagonal, null = point.
export function classifyOrient(e, tol = WALL_TOL) {
  const dx = Math.abs(e.x1 - e.x2), dy = Math.abs(e.y1 - e.y2);
  if (dx <= tol && dy <= tol) return null;
  if (dy <= tol) return "h";
  if (dx <= tol) return "v";
  return "d";
}

// 1D interval union over one wall line. Sweeps the snapped endpoints; for each
// elementary sub-interval records which rooms cover it and whether the outline does,
// then coalesces adjacent sub-intervals of the same exterior/interior class.
function unionIntervals(spans, tol) {
  const coords = [];
  for (const s of spans) { coords.push(s.lo, s.hi); }
  coords.sort((a, b) => a - b);
  const cuts = [];
  for (const c of coords) { if (!cuts.length || c - cuts.at(-1) > tol) cuts.push(c); }

  const out = [];
  for (let k = 0; k < cuts.length - 1; k++) {
    const a = cuts[k], b = cuts[k + 1];
    if (b - a <= tol) continue;
    const mid = (a + b) / 2;
    let ext = false;
    const rooms = new Set();
    for (const s of spans) {
      if (s.lo - tol <= mid && mid <= s.hi + tol) {
        if (s.isOutline) ext = true;
        if (s.room) rooms.add(s.room);
      }
    }
    if (!ext && rooms.size === 0) continue; // a gap on this wall line (e.g. a doorway run)
    const prev = out.at(-1);
    if (prev && prev.ext === ext && Math.abs(prev.hi - a) <= tol) {
      prev.hi = b;
      for (const r of rooms) prev.rooms.add(r);
    } else {
      out.push({ lo: a, hi: b, ext, rooms: new Set(rooms) });
    }
  }
  return out;
}

// Attach a material from the (optional) structure array when a named partition overlaps.
function matchStructure(structure, orient, coord, lo, hi, tol) {
  for (const w of structure || []) {
    const g = w.geometry || [];
    if (g.length < 2) continue;
    const a = g[0], b = g[g.length - 1];
    if (classifyOrient({ x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, tol) !== orient) continue;
    const c = orient === "v" ? (a[0] + b[0]) / 2 : (a[1] + b[1]) / 2;
    if (Math.abs(c - coord) > tol) continue;
    const wlo = orient === "v" ? Math.min(a[1], b[1]) : Math.min(a[0], b[0]);
    const whi = orient === "v" ? Math.max(a[1], b[1]) : Math.max(a[0], b[0]);
    if (Math.min(hi, whi) - Math.max(lo, wlo) > tol) return (w.attributes || {}).material || null;
  }
  return null;
}

// → { segments: [{ id, orient, kind:'ext'|'int', x1,y1,x2,y2, coord, lo, hi, rooms[], material }], byId }
export function deriveWalls({ outline = [], rooms = [], structure = [] } = {}, opts = {}) {
  const tol = opts.tol ?? WALL_TOL;
  const buckets = new Map(); // "orient|quant(coord)" -> { orient, spans, coordSum, n }
  const diagonals = [];

  const addEdge = (e, room, isOutline) => {
    const o = classifyOrient(e, tol);
    if (!o) return;
    if (o === "d") { diagonals.push({ e, isOutline, room }); return; }
    const coord = o === "v" ? (e.x1 + e.x2) / 2 : (e.y1 + e.y2) / 2;
    const lo = Math.min(o === "v" ? e.y1 : e.x1, o === "v" ? e.y2 : e.x2);
    const hi = Math.max(o === "v" ? e.y1 : e.x1, o === "v" ? e.y2 : e.x2);
    if (hi - lo <= tol) return;
    const key = o + "|" + quant(coord);
    let bk = buckets.get(key);
    if (!bk) { bk = { orient: o, spans: [], coordSum: 0, n: 0 }; buckets.set(key, bk); }
    bk.spans.push({ lo, hi, room, isOutline });
    bk.coordSum += coord; bk.n += 1;
  };

  for (const e of edgesOf(outline)) addEdge(e, null, true);
  for (const room of rooms) for (const e of edgesOf(room.geometry || [])) addEdge(e, room.id, false);

  const segments = [];
  for (const bk of buckets.values()) {
    const coord = bk.coordSum / bk.n; // representative — averages tiny float disagreement
    for (const m of unionIntervals(bk.spans, tol)) {
      const pos = bk.orient === "v"
        ? { x1: coord, y1: m.lo, x2: coord, y2: m.hi }
        : { x1: m.lo, y1: coord, x2: m.hi, y2: coord };
      segments.push({
        id: `${bk.orient}@${coord.toFixed(2)}:${m.lo.toFixed(2)}-${m.hi.toFixed(2)}`,
        orient: bk.orient, kind: m.ext ? "ext" : "int", ...pos,
        coord, lo: m.lo, hi: m.hi, rooms: [...m.rooms],
        material: matchStructure(structure, bk.orient, coord, m.lo, m.hi, tol),
      });
    }
  }

  // Diagonal fallback (unexercised by the rectilinear example data): emit verbatim, no
  // merge, deduped by undirected-endpoint key, so non-axis-aligned input never throws.
  const seen = new Set();
  for (const { e, isOutline, room } of diagonals) {
    const key = [e.x1, e.y1, e.x2, e.y2].map((v) => Math.round(v / tol)).sort((a, b) => a - b).join(",");
    if (seen.has(key)) continue;
    seen.add(key);
    segments.push({
      id: `d@${e.x1.toFixed(2)},${e.y1.toFixed(2)}-${e.x2.toFixed(2)},${e.y2.toFixed(2)}`,
      orient: "d", kind: isOutline ? "ext" : "int",
      x1: e.x1, y1: e.y1, x2: e.x2, y2: e.y2,
      coord: null, lo: null, hi: null, rooms: room ? [room] : [], material: null,
    });
    if (typeof console !== "undefined") console.warn("[walls] non-axis-aligned edge passed through verbatim", e);
  }

  const byId = {};
  for (const s of segments) byId[s.id] = s;
  return { segments, byId };
}
