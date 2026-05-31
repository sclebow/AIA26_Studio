import { useMemo } from "react";
import { SC, SI, SENSES } from "../lib/constants.js";
import { SENSE_SENSE, basisDash } from "../lib/senseModel.js";
import { useSelection } from "../lib/selection.jsx";

/*
 * SenseGraph — the sense-coupling graph (senses-only, pure SVG; replaces Cytoscape).
 * 6 sense nodes in a ring; node size/vividness = how many rooms fail that sense;
 * edges = the canonical couplings, line-styled by provenance (verified=research=solid,
 * inferred=physics=dashed). Bus-wired: click a node to solo that sense everywhere.
 */
const tierBasis = (tier) => (tier === "verified" ? "research" : "physics");

export default function SenseGraph({ rooms, size = 320 }) {
  const { focusSense, toggleSense } = useSelection();
  const cx = size / 2, cy = size / 2, R = size * 0.34;

  const pos = useMemo(() => {
    const m = {};
    SENSES.forEach((s, i) => {
      const a = (i * 60 - 90) * Math.PI / 180;   // start at top
      m[s] = [cx + R * Math.cos(a), cy + R * Math.sin(a)];
    });
    return m;
  }, []);

  const failCount = useMemo(() => {
    const c = {}; SENSES.forEach(s => { c[s] = 0; });
    (rooms || []).forEach(r => SENSES.forEach(s => { if ((r.comfortScores?.[s] ?? 1) < 0.5) c[s]++; }));
    return c;
  }, [rooms]);

  const nRooms = (rooms || []).length || 1;

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="sense-graph-svg" width="100%" height="100%">
      {/* edges */}
      {SENSE_SENSE.filter(e => e[3] !== "0").map(([a, b, , sign, tier], i) => {
        const [ax, ay] = pos[a], [bx, by] = pos[b];
        const dim = focusSense && focusSense !== a && focusSense !== b;
        const col = sign === "+" ? SC[b] : "rgba(var(--fg-rgb),0.5)";
        return (
          <line key={i} x1={ax} y1={ay} x2={bx} y2={by}
            stroke={col} strokeOpacity={dim ? 0.12 : 0.5} strokeWidth={1.8}
            strokeDasharray={basisDash(tierBasis(tier))} />
        );
      })}
      {/* nodes */}
      {SENSES.map((s) => {
        const [x, y] = pos[s];
        const frac = failCount[s] / nRooms;             // 0..1 of rooms failing this sense
        const r = 12 + frac * 16;
        const active = focusSense === s;
        const dim = focusSense && !active;
        return (
          <g key={s} style={{ cursor: "pointer" }} onClick={() => toggleSense(s)} opacity={dim ? 0.4 : 1}>
            <circle cx={x} cy={y} r={r} fill={SC[s]} fillOpacity={0.18 + frac * 0.5}
              stroke={SC[s]} strokeWidth={active ? 3 : 1.5} />
            <text x={x} y={y} textAnchor="middle" dominantBaseline="central"
              fontFamily="var(--font-mono)" fontSize="13" fill="rgba(var(--fg-rgb),0.95)">{SI[s]}</text>
            <text x={x} y={y + r + 11} textAnchor="middle"
              fontFamily="var(--font-mono)" fontSize="9" fill="rgba(var(--fg-rgb),0.6)">{s}</text>
          </g>
        );
      })}
    </svg>
  );
}
