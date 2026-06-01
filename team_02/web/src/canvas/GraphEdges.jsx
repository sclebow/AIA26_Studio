import { SC } from "../lib/constants.js";
import { failingTransmissive } from "../lib/senseModel.js";
import GraphEdge from "./GraphEdge.jsx";

// Unified room-relationship edges — ONE arc per room-pair (centroid→centroid), so
// structure and flow always align (no door-segment/centroid mismatch):
//   healthy connection → faint neutral arc.
//   conflicted        → the SAME arc becomes a colored, animated directional
//                        arrow (worse→better) for the worst bleeding sense.
// Every bleeding sense + scores live in the hover tooltip — nothing painted on the
// canvas to overlap. Prefers backend graph_data.edges (conflict tags), else derives.
export default function GraphEdges({ roomById, graphData = null, doors = [], focusSense, u, fy, onHoverEdge }) {
  const pairs = (graphData?.edges?.length)
    ? graphData.edges.map((e) => ({ a: roomById[e.source], b: roomById[e.target], conflicts: e.transmissive_conflicts || null }))
    : doors.map((d) => { const c = d.attributes?.connectsRooms || []; return { a: roomById[c[0]], b: roomById[c[1]], conflicts: null }; });

  return pairs.map((e, i) => {
    if (!e.a || !e.b) return null;
    const ax = e.a.c[0], ay = fy(e.a.c[1]), bx = e.b.c[0], by = fy(e.b.c[1]);
    const conflicts = e.conflicts != null ? e.conflicts
      : [...new Set([...failingTransmissive(e.a.scored), ...failingTransmissive(e.b.scored)])];

    if (!conflicts.length) {
      return <GraphEdge key={"e" + i} ax={ax} ay={ay} bx={bx} by={by}
        color="rgba(var(--fg-rgb),0.28)" width={1.4} curvature={0.16} opacity={0.5} glow={false} />;
    }

    const sev = conflicts.map((s) => {
      const sa = e.a.scored?.comfortScores?.[s] ?? 1, sb = e.b.scored?.comfortScores?.[s] ?? 1;
      return { s, sa, sb, worse: Math.min(sa, sb) };
    }).sort((x, y) => x.worse - y.worse);
    const worst = sev[0];
    const srcIsA = worst.sa <= worst.sb;                    // bleed leaves the worse room
    const sx = srcIsA ? ax : bx, sy = srcIsA ? ay : by;
    const tx = srcIsA ? bx : ax, ty = srcIsA ? by : ay;
    const dim = focusSense && !conflicts.includes(focusSense);

    return <GraphEdge key={"e" + i} ax={sx} ay={sy} bx={tx} by={ty} color={SC[worst.s]}
      width={2 + (1 - worst.worse) * 3} arrow headSize={u * 0.9} curvature={0.16} live opacity={dim ? 0.12 : 0.9}
      onHover={(ev) => onHoverEdge && onHoverEdge({ x: ev.clientX, y: ev.clientY, kind: "bleed", src: srcIsA ? e.a : e.b, tgt: srcIsA ? e.b : e.a, sev })}
      onLeave={() => onHoverEdge && onHoverEdge(null)} />;
  });
}
