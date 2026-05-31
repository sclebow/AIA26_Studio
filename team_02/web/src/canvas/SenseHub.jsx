import { SENSES, SC, SI } from "../lib/constants.js";
import { basisDash } from "../lib/senseModel.js";
import { VALENCE, signOf, edgeWidth } from "../lib/relationships.js";
import { arc } from "../lib/geometry.js";
import GraphEdge from "./GraphEdge.jsx";

// SenseHub — the focused room's RELATIONSHIPS as a graph, anchored on the plan.
// Six sense nodes in a ring (hue = sense, size = score, CLICK to solo); edges =
// that room's real sense→sense cross-modal adjustments, each colored by source,
// line-styled by provenance, widthed by magnitude, arrow at the target's rim,
// and marked with a valence glyph (helps/harms/±). Hover an edge → the mechanism.
// Edges are trimmed to the node rims so arrowheads read; personality/non-sense
// adjustments (which would converge at the centre) are left to the FocusCard.
export default function SenseHub({ room, cx, cy, R, u, activeSense, onSelectSense, onHoverEdge }) {
  if (!room) return null;
  const eff = room.comfortScores || {};
  const adjustments = (room.adjustments || []).filter((a) => SENSES.includes(a.from) && SENSES.includes(a.sense));

  const pos = {}, rad = {};
  SENSES.forEach((s, i) => {
    const ang = (i * 60) * Math.PI / 180;                 // 0 = top, clockwise
    pos[s] = [cx + R * Math.sin(ang), cy - R * Math.cos(ang)];
    rad[s] = u * 0.6 + (typeof eff[s] === "number" ? eff[s] : 0) * u * 0.8;
  });

  return (
    <g className="sense-hub">
      <circle cx={cx} cy={cy} r={R + u * 2} fill="rgba(13,13,13,0.6)" stroke="rgba(var(--fg-rgb),0.1)" strokeWidth={1} vectorEffect="non-scaling-stroke" />

      {/* relationship edges, trimmed to the node rims */}
      {adjustments.map((adj, i) => {
        const [sx, sy] = pos[adj.from], [tx, ty] = pos[adj.sense];
        let dx = tx - sx, dy = ty - sy; const dl = Math.hypot(dx, dy) || 1; dx /= dl; dy /= dl;
        const ax = sx + dx * rad[adj.from], ay = sy + dy * rad[adj.from];
        const bx = tx - dx * (rad[adj.sense] + u * 0.5), by = ty - dy * (rad[adj.sense] + u * 0.5);
        const sign = signOf(adj.delta);
        const a = arc(ax, ay, bx, by, 0.18);
        const dim = activeSense && activeSense !== adj.from && activeSense !== adj.sense;
        return (
          <g key={i} opacity={dim ? 0.15 : 1}>
            <GraphEdge ax={ax} ay={ay} bx={bx} by={by} color={SC[adj.from]} width={edgeWidth(adj.delta)}
              dash={basisDash(adj.basis)} arrow headSize={u * 0.95} curvature={0.18}
              onHover={(e) => onHoverEdge && onHoverEdge({ x: e.clientX, y: e.clientY, kind: "edge", adj, sign })}
              onLeave={() => onHoverEdge && onHoverEdge(null)} />
            <text x={a.midx} y={a.midy} textAnchor="middle" dominantBaseline="central"
              fontFamily="var(--font-mono)" fontSize={u} fill={VALENCE[sign].tint}>{VALENCE[sign].glyph}</text>
          </g>
        );
      })}

      {/* sense nodes — click to solo */}
      {SENSES.map((s) => {
        const [x, y] = pos[s];
        const sc = typeof eff[s] === "number" ? eff[s] : 0;
        const on = activeSense === s;
        const dim = activeSense && !on;
        return (
          <g key={s} className="spln-gnode" onClick={(e) => { e.stopPropagation(); onSelectSense && onSelectSense(s); }}
            style={onSelectSense ? { cursor: "pointer" } : undefined} opacity={dim ? 0.4 : 1}>
            <circle cx={x} cy={y} r={rad[s] + u * 0.9} fill="transparent" />
            <circle cx={x} cy={y} r={rad[s]} fill={SC[s]} fillOpacity={0.25 + sc * 0.5}
              stroke={SC[s]} strokeWidth={on ? 2.4 : 1.2} vectorEffect="non-scaling-stroke" />
            <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontFamily="var(--font-mono)" fontSize={u * 0.95} fill="rgb(var(--fg-rgb))">{SI[s]}</text>
          </g>
        );
      })}
    </g>
  );
}
