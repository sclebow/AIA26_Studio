import { memo, useMemo } from "react";
import { deriveWalls } from "../lib/walls.js";

// Structural shell as luminous CAD walls. Walls are DERIVED from the room polygons +
// outline (the `structure` array is sparse), then each unique segment is rendered as a
// band: a wide low-opacity "mass" stroke whose width is in MODEL units (so it scales
// with zoom = real wall thickness) UNDER a crisp non-scaling centerline. Each wall is an
// addressable <g data-wall-id> so later edit tools (B3) can target it. Door/window gaps
// are knocked out by the bg-coloured masks painted on top in OpeningsLayer.
//
// NOTE: never put vectorEffect="non-scaling-stroke" on the mass stroke — that would lock
// it to pixels and the wall would stop reading as thickness.
const BAND = { ext: 0.12, in: 0.08 }; // model metres

function WallsLayer({ outline = [], rooms = [], structure = [], fy }) {
  const { segments } = useMemo(
    () => deriveWalls({ outline, rooms, structure }),
    [outline, rooms, structure],
  );
  return (
    <g className="spln-walls">
      {segments.map((s) => {
        const ext = s.kind === "ext";
        const x1 = s.x1, y1 = fy(s.y1), x2 = s.x2, y2 = fy(s.y2);
        return (
          <g key={s.id} data-wall-id={s.id} data-kind={s.kind}>
            <line className={ext ? "spln-wall-ext-mass" : "spln-wall-in-mass"}
              x1={x1} y1={y1} x2={x2} y2={y2}
              strokeWidth={ext ? BAND.ext : BAND.in} strokeLinecap="round" />
            <line className={ext ? "spln-wall-ext" : "spln-wall-in"}
              x1={x1} y1={y1} x2={x2} y2={y2} vectorEffect="non-scaling-stroke" />
          </g>
        );
      })}
    </g>
  );
}

// Pure + props stable across hover (refs from `layout`, `fy` memoized) → skip the
// per-mousemove re-render that SensePlan's hover state would otherwise trigger.
export default memo(WallsLayer);
