import { SC, SI } from "../lib/constants.js";
import { TRANSMISSIVE } from "../lib/senseModel.js";

// Transmissive bleed as a directed GRAPH lens. For each door, each failing
// transmissive sense draws an arrow from the WORSE room into the better one —
// in the sense's hue, thickness = severity (how low the worse score is), with a
// glyph+score label and a marching-dash animation. Nodes are the shared RoomGraph.
export default function FlowLayer({ doors = [], roomById, focusSense, fy, u }) {
  const arrows = [];
  doors.forEach((d, i) => {
    const g = d.geometry || [];
    if (g.length < 2) return;
    const conn = d.attributes?.connectsRooms || [];
    const a = roomById[conn[0]], b = roomById[conn[1]];
    if (!a || !b) return;
    const A = g[0], B = g[g.length - 1];
    const mx = (A[0] + B[0]) / 2, my = (fy(A[1]) + fy(B[1])) / 2;
    const dl = Math.hypot(B[0] - A[0], fy(B[1]) - fy(A[1])) || 1;
    const ax = (B[0] - A[0]) / dl, ay = (fy(B[1]) - fy(A[1])) / dl;

    const senses = TRANSMISSIVE.filter((s) => {
      const sa = a.scored?.comfortScores?.[s] ?? 1, sb = b.scored?.comfortScores?.[s] ?? 1;
      return Math.min(sa, sb) < 0.5;
    });
    senses.forEach((s, k) => {
      const sa = a.scored?.comfortScores?.[s] ?? 1, sb = b.scored?.comfortScores?.[s] ?? 1;
      const worse = Math.min(sa, sb);
      let dx = (sa <= sb ? b : a).c[0] - (sa <= sb ? a : b).c[0];
      let dy = fy((sa <= sb ? b : a).c[1]) - fy((sa <= sb ? a : b).c[1]);
      const dn = Math.hypot(dx, dy) || 1; dx /= dn; dy /= dn;
      const off = (k - (senses.length - 1) / 2) * u * 1.1;
      const cxp = mx + ax * off, cyp = my + ay * off;
      const len = u * 3;
      arrows.push({
        key: `fl${i}-${s}`, sense: s, worse, color: SC[s], loud: !focusSense || focusSense === s,
        cxp, cyp, dx, dy,
        x1: cxp - dx * len * 0.5, y1: cyp - dy * len * 0.5,
        x2: cxp + dx * len * 0.5, y2: cyp + dy * len * 0.5,
      });
    });
  });

  return (
    <>
      {arrows.map((ar) => {
        const op = ar.loud ? 0.92 : 0.1;
        const sevW = ar.loud ? (2 + (1 - ar.worse) * 3) : 1.5;     // thicker = more severe
        const hh = u * (0.7 + (1 - ar.worse) * 0.4);
        const px = -ar.dy, py = ar.dx;
        const b1x = ar.x2 - ar.dx * hh + px * hh * 0.55, b1y = ar.y2 - ar.dy * hh + py * hh * 0.55;
        const b2x = ar.x2 - ar.dx * hh - px * hh * 0.55, b2y = ar.y2 - ar.dy * hh - py * hh * 0.55;
        const lx = ar.cxp + px * u * 1.0, ly = ar.cyp + py * u * 1.0;  // label off to the side
        return (
          <g key={ar.key} opacity={op}>
            <line className="spln-flow-arrow" x1={ar.x1} y1={ar.y1} x2={ar.x2} y2={ar.y2}
              stroke={ar.color} strokeWidth={sevW} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            <polygon points={`${ar.x2},${ar.y2} ${b1x},${b1y} ${b2x},${b2y}`} fill={ar.color} />
            {ar.loud && (
              <text x={lx} y={ly} textAnchor="middle" dominantBaseline="central"
                fontFamily="var(--font-mono)" fontSize={u * 0.85} fill={ar.color}>
                {SI[ar.sense]} {ar.worse.toFixed(2)}
              </text>
            )}
          </g>
        );
      })}
    </>
  );
}
