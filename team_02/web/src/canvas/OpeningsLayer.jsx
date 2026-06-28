import { memo } from "react";
import { swingPath } from "../lib/geometry.js";

// Openings in the shell. Both knock a bg-coloured gap in the wall band (model-unit width
// so the mask scales WITH the band), then draw their symbol on top:
//   doors   — swing arc + leaf
//   windows — glass symbol: crisp blue mullion + offset glazing panes + jamb ticks,
//             built from the opening's own normal so it works along x OR y.
const GAP = 0.18; // model metres — a touch wider than the exterior wall band (0.12)

function OpeningsLayer({ doors = [], windows = [], fy, u = 0.1 }) {
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
            <line className="spln-door-gap" x1={A[0]} y1={fy(A[1])} x2={B[0]} y2={fy(B[1])} strokeWidth={GAP} />
            <polyline className="spln-door-swing" points={arc} fill="none" vectorEffect="non-scaling-stroke" />
            <line className="spln-door-swing" x1={A[0]} y1={fy(A[1])} x2={arcEnd[0]} y2={arcEnd[1]} vectorEffect="non-scaling-stroke" />
          </g>
        );
      })}
      {windows.map((wn, i) => {
        const g = wn.geometry || [];
        if (g.length < 2) return null;
        const A = g[0], B = g[g.length - 1];
        const ax = A[0], ay = fy(A[1]), bx = B[0], by = fy(B[1]);
        const dx = bx - ax, dy = by - ay;
        const L = Math.hypot(dx, dy) || 1;
        const nx = -dy / L, ny = dx / L;                 // unit normal to the opening
        const jamb = u * 0.9;                            // tick half-length (model units)
        const spread = (wn.attributes?.glazingType === "double") ? 0.62 : 0.46;
        const panes = [-spread, spread];
        return (
          <g key={"wn" + i} className="spln-window">
            <line className="spln-window-gap" x1={ax} y1={ay} x2={bx} y2={by} strokeWidth={GAP} />
            <line className="spln-window-glow" x1={ax} y1={ay} x2={bx} y2={by} vectorEffect="non-scaling-stroke" />
            <line className="spln-window-glass" x1={ax} y1={ay} x2={bx} y2={by} vectorEffect="non-scaling-stroke" />
            {panes.map((o, j) => (
              <line key={j} className="spln-window-pane"
                x1={ax + nx * o * jamb} y1={ay + ny * o * jamb}
                x2={bx + nx * o * jamb} y2={by + ny * o * jamb} vectorEffect="non-scaling-stroke" />
            ))}
            <line className="spln-window-jamb" x1={ax - nx * jamb} y1={ay - ny * jamb} x2={ax + nx * jamb} y2={ay + ny * jamb} vectorEffect="non-scaling-stroke" />
            <line className="spln-window-jamb" x1={bx - nx * jamb} y1={by - ny * jamb} x2={bx + nx * jamb} y2={by + ny * jamb} vectorEffect="non-scaling-stroke" />
          </g>
        );
      })}
    </>
  );
}

// Props stable across hover → memo avoids the per-mousemove re-render.
export default memo(OpeningsLayer);
