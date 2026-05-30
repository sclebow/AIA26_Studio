import { SC } from "../lib/constants.js";
import { failingTransmissive } from "../lib/senseModel.js";

// Room-adjacency graph: an edge between connected room centroids (colored by a
// shared failing transmissive sense, else neutral) plus a node per room.
export default function TopologyLayer({ doors = [], roomById, fy, u }) {
  return (
    <>
      {doors.map((d, i) => {
        const conn = d.attributes?.connectsRooms || [];
        const a = roomById[conn[0]], b = roomById[conn[1]];
        if (!a || !b) return null;
        const conflict = [...failingTransmissive(a.scored), ...failingTransmissive(b.scored)];
        const col = conflict.length ? SC[conflict[0]] : "rgba(var(--fg-rgb),0.3)";
        return <line key={"tp" + i} x1={a.c[0]} y1={fy(a.c[1])} x2={b.c[0]} y2={fy(b.c[1])}
          stroke={col} strokeOpacity={0.55} strokeWidth={2.5} vectorEffect="non-scaling-stroke" />;
      })}
      {Object.values(roomById).map((rm, i) => (
        <circle key={"tn" + i} cx={rm.c[0]} cy={fy(rm.c[1])} r={u * 0.7}
          fill="rgb(var(--fg-rgb))" fillOpacity={0.5} stroke="rgb(var(--fg-rgb))" strokeOpacity={0.3} vectorEffect="non-scaling-stroke" />
      ))}
    </>
  );
}
