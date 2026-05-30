import { SC } from "../lib/constants.js";
import { failingTransmissive } from "../lib/senseModel.js";

// Topology EDGES — room adjacency (doors), colored by a shared failing
// transmissive sense, else neutral. Nodes are drawn by the shared RoomGraph.
// Prefers the backend's graph_data.edges (which carry the conflict tag); falls
// back to deriving from doors + live scores.
export default function TopologyLayer({ doors = [], roomById, graphData = null, fy }) {
  const edges = (graphData?.edges?.length)
    ? graphData.edges.map((e) => ({ a: roomById[e.source], b: roomById[e.target], conflicts: e.transmissive_conflicts || [] }))
    : doors.map((d) => {
        const conn = d.attributes?.connectsRooms || [];
        const a = roomById[conn[0]], b = roomById[conn[1]];
        const conflicts = a && b ? [...new Set([...failingTransmissive(a.scored), ...failingTransmissive(b.scored)])] : [];
        return { a, b, conflicts };
      });

  return edges.map((e, i) => {
    if (!e.a || !e.b) return null;
    const col = e.conflicts.length ? SC[e.conflicts[0]] : "rgba(var(--fg-rgb),0.3)";
    return <line key={"tp" + i} x1={e.a.c[0]} y1={fy(e.a.c[1])} x2={e.b.c[0]} y2={fy(e.b.c[1])}
      stroke={col} strokeOpacity={0.55} strokeWidth={2.5} vectorEffect="non-scaling-stroke" />;
  });
}
