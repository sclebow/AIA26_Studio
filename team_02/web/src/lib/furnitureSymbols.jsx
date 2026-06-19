// Recognizable plan symbols for furniture, drawn in Sensi's thin luminous line.
//
// Each piece's footprint polygon gives a bounding cell; a symbol is authored in
// normalized cell coords (u,v) ∈ [0,1]² (u→right/+x, v→up/+north) and mapped into the
// cell via `frame()`. `fy` (the canvas y-flip) is applied so v=1 reads visually north.
//
// Directional pieces (bed/sofa/toilet/vanity/desk/fridge) are authored facing SOUTH
// (front/open side toward v=0); `facingOf()` picks the cardinal pointing into the room,
// and TRANSFORM rotates the cell coords to match. Unknown types return null so the layer
// falls back to the labelled footprint (previous behaviour).

import { centroid } from "./geometry.js";

const DIRECTIONAL = new Set(["bed", "sofa", "toilet", "vanity", "desk", "fridge"]);

// Quarter-turn maps of canonical (front = south) onto each facing.
const TRANSFORM = {
  S: (u, v) => [u, v],
  N: (u, v) => [1 - u, 1 - v],
  E: (u, v) => [1 - v, u],
  W: (u, v) => [v, 1 - u],
};

// Front faces the room interior; snap the piece→room-centroid vector to a cardinal.
export function facingOf(geo, roomCentroid) {
  const [pcx, pcy] = centroid(geo);
  const [rcx, rcy] = roomCentroid || [pcx, pcy];
  const dx = rcx - pcx, dy = rcy - pcy;
  if (Math.abs(dx) >= Math.abs(dy)) return dx >= 0 ? "E" : "W";
  return dy >= 0 ? "N" : "S";
}

function frame(geo, fy) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of geo) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  const w = x1 - x0, h = y1 - y0;
  return { x0, y0, w, h, s: Math.min(w, h), X: (u) => x0 + u * w, Yv: (v) => fy(y0 + v * h) };
}

// Drawing builder: normalized coords in, theme-classed SVG out (with the facing transform).
function builder(F, t, base = "spln-furn-sym") {
  const els = [];
  let k = 0;
  const P = (u, v) => { const [a, b] = t(u, v); return [F.X(a), F.Yv(b)]; };
  return {
    els,
    rect(u0, v0, u1, v1, { rx = 0, c = base } = {}) {
      const p = t(u0, v0), q = t(u1, v1);
      const a0 = Math.min(p[0], q[0]), a1 = Math.max(p[0], q[0]);
      const b0 = Math.min(p[1], q[1]), b1 = Math.max(p[1], q[1]);
      els.push(<rect key={k++} className={c} x={F.X(a0)} y={F.Yv(b1)} width={(a1 - a0) * F.w}
        height={(b1 - b0) * F.h} rx={rx} fill="none" vectorEffect="non-scaling-stroke" />);
    },
    line(u0, v0, u1, v1, { c = base } = {}) {
      const [x1, y1] = P(u0, v0), [x2, y2] = P(u1, v1);
      els.push(<line key={k++} className={c} x1={x1} y1={y1} x2={x2} y2={y2} vectorEffect="non-scaling-stroke" />);
    },
    circle(uc, vc, rFrac, { c = base, fill = "none" } = {}) {
      const [cx, cy] = P(uc, vc);
      els.push(<circle key={k++} className={c} cx={cx} cy={cy} r={rFrac * F.s} fill={fill} vectorEffect="non-scaling-stroke" />);
    },
    ellipse(uc, vc, rxFrac, ryFrac, { c = base } = {}) {
      const [cx, cy] = P(uc, vc);
      els.push(<ellipse key={k++} className={c} cx={cx} cy={cy} rx={rxFrac * F.w} ry={ryFrac * F.h} fill="none" vectorEffect="non-scaling-stroke" />);
    },
  };
}

const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

const SYMBOLS = {
  bed(b, F) {
    const r = F.s * 0.06;
    b.rect(0.03, 0.03, 0.97, 0.97, { rx: r });
    b.rect(0.03, 0.84, 0.97, 0.98, { rx: r * 0.6 }); // headboard band (back)
    if (F.w >= 1.3) { b.rect(0.10, 0.64, 0.46, 0.81, { rx: r }); b.rect(0.54, 0.64, 0.90, 0.81, { rx: r }); }
    else b.rect(0.28, 0.64, 0.72, 0.81, { rx: r });
    b.line(0.03, 0.42, 0.97, 0.42, { c: "spln-furn-sym-faint" });   // blanket fold
  },
  sofa(b, F) {
    const r = F.s * 0.12;
    b.rect(0.02, 0.02, 0.98, 0.98, { rx: r });
    b.rect(0.02, 0.72, 0.98, 0.98, { rx: r * 0.5 });                // backrest
    b.rect(0.02, 0.06, 0.16, 0.86, { rx: r * 0.5 });                // arms
    b.rect(0.84, 0.06, 0.98, 0.86, { rx: r * 0.5 });
    const n = clamp(Math.round(F.w / 0.9), 1, 4);
    for (let i = 1; i < n; i++) { const x = 0.16 + (0.68 * i) / n; b.line(x, 0.06, x, 0.66, { c: "spln-furn-sym-faint" }); }
  },
  table(b, F) {
    b.rect(0.04, 0.04, 0.96, 0.96, { rx: F.s * 0.05 });
    b.rect(0.18, 0.18, 0.82, 0.82, { c: "spln-furn-sym-faint" });
  },
  plant(b) {
    b.circle(0.5, 0.5, 0.34, { c: "spln-furn-plant" });
    for (let i = 0; i < 5; i++) {
      const a = (Math.PI * 2 * i) / 5 - Math.PI / 2;
      b.line(0.5 + 0.30 * Math.cos(a), 0.5 + 0.30 * Math.sin(a),
        0.5 + 0.46 * Math.cos(a), 0.5 + 0.46 * Math.sin(a), { c: "spln-furn-plant-leaf" });
    }
  },
  island(b, F) {
    b.rect(0.04, 0.06, 0.96, 0.94, { rx: F.s * 0.04 });
    const two = F.w <= 1.2;
    const xs = two ? [0.34, 0.66] : [0.22, 0.46, 0.54, 0.78];
    const ys = two ? [0.5, 0.5] : [0.68, 0.68, 0.34, 0.34];
    xs.forEach((x, i) => b.circle(x, ys[i], 0.10, { c: "spln-furn-sym-faint" }));
  },
  counter(b, F) {
    b.rect(0.04, 0.08, 0.96, 0.92, { rx: F.s * 0.04 });
    if (F.w >= F.h) b.line(0.04, 0.5, 0.96, 0.5, { c: "spln-furn-sym-faint" });
    else b.line(0.5, 0.08, 0.5, 0.92, { c: "spln-furn-sym-faint" });
  },
  sink(b, F) {
    b.rect(0.08, 0.08, 0.92, 0.92, { rx: F.s * 0.06 });
    b.ellipse(0.5, 0.46, 0.30, 0.30);
    b.circle(0.5, 0.46, 0.04, { c: "spln-furn-sym-faint" });
  },
  fridge(b, F) {
    b.rect(0.06, 0.04, 0.94, 0.96, { rx: F.s * 0.05 });
    b.line(0.06, 0.58, 0.94, 0.58, { c: "spln-furn-sym-faint" });   // freezer split
    b.line(0.84, 0.18, 0.84, 0.46);                                 // handle
  },
  nightstand(b, F) {
    b.rect(0.1, 0.1, 0.9, 0.9, { rx: F.s * 0.08 });
    b.line(0.1, 0.5, 0.9, 0.5, { c: "spln-furn-sym-faint" });
  },
  dresser(b, F) {
    b.rect(0.05, 0.08, 0.95, 0.92, { rx: F.s * 0.05 });
    for (let i = 1; i < 4; i++) b.line(i / 4, 0.08, i / 4, 0.92, { c: "spln-furn-sym-faint" });
  },
  desk(b, F) {
    b.rect(0.05, 0.08, 0.95, 0.92, { rx: F.s * 0.05 });
    b.line(0.05, 0.72, 0.95, 0.72, { c: "spln-furn-sym-faint" });   // back panel
  },
  bookshelf(b, F) {
    b.rect(0.1, 0.04, 0.9, 0.96, { rx: F.s * 0.04 });
    const tall = F.h >= F.w;
    for (let j = 1; j < 5; j++) {
      if (tall) b.line(0.1, j / 5, 0.9, j / 5, { c: "spln-furn-sym-faint" });
      else b.line(j / 5, 0.04, j / 5, 0.96, { c: "spln-furn-sym-faint" });
    }
  },
  toilet(b) {
    b.rect(0.18, 0.80, 0.82, 0.98, { rx: 0 });                      // tank (back)
    b.ellipse(0.5, 0.42, 0.30, 0.40);                               // bowl
  },
  vanity(b, F) {
    b.rect(0.05, 0.05, 0.95, 0.95, { rx: F.s * 0.06 });
    b.ellipse(0.5, 0.58, 0.30, 0.22);                               // basin
    b.circle(0.5, 0.86, 0.04, { c: "spln-furn-sym-faint" });        // tap
  },
  shower(b, F) {
    b.rect(0.05, 0.05, 0.95, 0.95, { rx: F.s * 0.03 });
    b.line(0.05, 0.05, 0.95, 0.95, { c: "spln-furn-sym-faint" });   // glass diagonal
    b.circle(0.5, 0.5, 0.06, { c: "spln-furn-sym-faint" });         // drain
  },
};

export function hasSymbol(type) { return !!SYMBOLS[type]; }

export function furnitureSymbol(geo, fy, u, { type, facing = "S" } = {}) {
  const fn = SYMBOLS[type];
  if (!fn) return null;
  const F = frame(geo, fy);
  const t = TRANSFORM[DIRECTIONAL.has(type) ? facing : "S"] || TRANSFORM.S;
  const b = builder(F, t);
  fn(b, F);
  return b.els;
}
