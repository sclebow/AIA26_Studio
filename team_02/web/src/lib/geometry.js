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
