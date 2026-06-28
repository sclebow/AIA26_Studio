// Pure SVG geometry helpers for the floor-plan canvas. Extracted from SensePlan
// so they can be unit-tested and shared across the canvas layer components.
// `fy` is the y-flip the canvas passes in (SVG y grows downward; plans read N-up).

export function polyPoints(geo, fy) {
  return geo.map(([x, y]) => `${x},${fy(y)}`).join(" ");
}

export function centroid(geo) {
  const pts = geo.length > 1 && geo[0][0] === geo.at(-1)[0] && geo[0][1] === geo.at(-1)[1] ? geo.slice(0, -1) : geo;
  let x = 0, y = 0; pts.forEach((p) => { x += p[0]; y += p[1]; });
  return [x / pts.length, y / pts.length];
}

export function dims(geo) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  geo.forEach(([x, y]) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); });
  return { w: x1 - x0, h: y1 - y0, top: y1, cx: (x0 + x1) / 2 };
}

// Ray-casting point-in-polygon. `pts` is [[x,y],…] and (px,py) must be in the SAME
// space (so test screen-space points against a screen-space polygon).
export function pointInPoly(px, py, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if (((yi > py) !== (yj > py)) &&
        (px < ((xj - xi) * (py - yi)) / ((yj - yi) || 1e-12) + xi)) {
      inside = !inside;
    }
  }
  return inside;
}

// Place the comfort ring near a room's top-right corner but GUARANTEED inside the
// room polygon. The ideal corner (from the bbox) is fine for rectangular rooms, but
// for concave / L-shaped rooms it can fall in the bbox notch — i.e. inside a
// neighbouring room — so the ring would render on the wrong cell. When that happens
// we snap to the nearest grid point where the whole ring fits inside (falling back to
// the nearest interior point, then the corner). `screenPts` and `desired` are screen
// space (y already flipped); returns [x, y].
export function ringAnchor(screenPts, desired, ringR) {
  const [dx, dy] = desired;
  // ring "fits" when its centre + 4 cardinal extents all lie inside the polygon.
  const fits = (x, y, pad) =>
    pointInPoly(x, y, screenPts) &&
    pointInPoly(x + pad, y, screenPts) && pointInPoly(x - pad, y, screenPts) &&
    pointInPoly(x, y + pad, screenPts) && pointInPoly(x, y - pad, screenPts);
  if (fits(dx, dy, ringR)) return desired;   // rectangular rooms: unchanged

  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of screenPts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const N = 16;
  const search = (pad) => {
    let best = null, bestD = Infinity;
    for (let i = 0; i <= N; i++) for (let j = 0; j <= N; j++) {
      const x = x0 + ((x1 - x0) * i) / N, y = y0 + ((y1 - y0) * j) / N;
      if (pad > 0 ? !fits(x, y, pad) : !pointInPoly(x, y, screenPts)) continue;
      const d = (x - dx) ** 2 + (y - dy) ** 2;   // nearest to the ideal corner
      if (d < bestD) { bestD = d; best = [x, y]; }
    }
    return best;
  };
  return search(ringR * 0.85) || search(0) || desired;
}

export function swingPath(A, B, fy) {
  const r = Math.hypot(B[0] - A[0], B[1] - A[1]);
  const t0 = Math.atan2(B[1] - A[1], B[0] - A[0]);
  const n = 12, pts = [];
  for (let i = 0; i <= n; i++) { const t = t0 + (Math.PI / 2) * (i / n); pts.push([A[0] + r * Math.cos(t), A[1] + r * Math.sin(t)]); }
  return polyPoints(pts, fy);
}

// Quadratic-Bézier arc between two screen-space points. Returns the path `d`, the
// end-tangent unit vector (for arrowheads), and the curve midpoint (for labels).
// `k` is curvature: the control point is offset perpendicular to the chord by k·|chord|.
export function arc(ax, ay, bx, by, k = 0.18) {
  const mx = (ax + bx) / 2, my = (ay + by) / 2;
  const dx = bx - ax, dy = by - ay;
  const cx = mx - dy * k, cy = my + dx * k;            // control point
  const tx = bx - cx, ty = by - cy;                     // end tangent (control → B)
  const tl = Math.hypot(tx, ty) || 1;
  return {
    d: `M ${ax} ${ay} Q ${cx} ${cy} ${bx} ${by}`,
    edx: tx / tl, edy: ty / tl,                          // unit end-direction
    midx: 0.25 * ax + 0.5 * cx + 0.25 * bx,              // Bézier point at t=0.5
    midy: 0.25 * ay + 0.5 * cy + 0.25 * by,
  };
}
