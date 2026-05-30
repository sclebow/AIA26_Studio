import { SC } from "../lib/constants.js";
import { failingTransmissive } from "../lib/senseModel.js";

// Transmissive bleed: for each door, draw a line per failing transmissive sense
// (acoustic/olfactory/thermal) of the rooms it connects — sound/smell/heat
// leaking across the opening. Dims senses other than the soloed one.
export default function FlowLayer({ doors = [], roomById, focusSense, fy, u }) {
  return doors.map((d, i) => {
    const g = d.geometry || [];
    if (g.length < 2) return null;
    const A = g[0], B = g[g.length - 1];
    const conn = d.attributes?.connectsRooms || [];
    const failing = [...new Set([...failingTransmissive(roomById[conn[0]]?.scored), ...failingTransmissive(roomById[conn[1]]?.scored)])];
    const dx = B[0] - A[0], dy = (fy(B[1]) - fy(A[1])); const len = Math.hypot(dx, dy) || 1;
    const px = -dy / len, py = dx / len;
    return failing.map((s, k) => {
      const off = (k - (failing.length - 1) / 2) * u * 1.1;
      const loud = !focusSense || focusSense === s;
      return (
        <line key={"fl" + i + s} x1={A[0] + px * off} y1={fy(A[1]) + py * off} x2={B[0] + px * off} y2={fy(B[1]) + py * off}
          stroke={SC[s]} strokeOpacity={loud ? 0.8 : 0.15} strokeWidth={focusSense === s ? 4.5 : 3}
          strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      );
    });
  });
}
