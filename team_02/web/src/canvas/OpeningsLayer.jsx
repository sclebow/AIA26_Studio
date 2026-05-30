import { polyPoints, swingPath } from "../lib/geometry.js";

// Openings in the shell: doors (gap + swing arc) and windows.
export default function OpeningsLayer({ doors = [], windows = [], fy }) {
  return (
    <>
      {doors.map((d, i) => {
        const g = d.geometry || [];
        if (g.length < 2) return null;
        const A = g[0], B = g[g.length - 1];
        const arc = swingPath(A, B, fy);
        const arcEnd = arc.split(" ").at(-1).split(",");
        return (
          <g key={"dr" + i} className="spln-door">
            <line className="spln-door-gap" x1={A[0]} y1={fy(A[1])} x2={B[0]} y2={fy(B[1])} vectorEffect="non-scaling-stroke" />
            <polyline className="spln-door-swing" points={arc} fill="none" vectorEffect="non-scaling-stroke" />
            <line className="spln-door-swing" x1={A[0]} y1={fy(A[1])} x2={arcEnd[0]} y2={arcEnd[1]} vectorEffect="non-scaling-stroke" />
          </g>
        );
      })}
      {windows.map((wn, i) => {
        const g = wn.geometry || [];
        return g.length > 1 ? <polyline key={"wn" + i} className="spln-window" points={polyPoints(g, fy)} fill="none" vectorEffect="non-scaling-stroke" /> : null;
      })}
    </>
  );
}
