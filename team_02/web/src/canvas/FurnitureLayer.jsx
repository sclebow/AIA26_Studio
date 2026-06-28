import { memo } from "react";
import { polyPoints, centroid, dims, pointInPoly } from "../lib/geometry.js";
import { furnitureSymbol, hasSymbol, facingOf } from "../lib/furnitureSymbols.jsx";

// Furniture as recognizable plan symbols (bed, sofa, toilet, …) drawn over a faint
// footprint, with the footprint also serving as the hover hit area. Unknown types fall
// back to the labelled footprint (previous behaviour). The room a piece sits in is
// resolved by its centroid so directional symbols can face the room interior.
function FurnitureLayer({ furniture = [], rooms = [], fy, u, onHover }) {
  return furniture.map((f, i) => {
    const g = f.geometry || [];
    if (g.length < 3) return null;
    const a = f.attributes || {};
    const type = a.type;
    const { cx, w, h } = dims(g);
    const [pcx, pcy] = centroid(g);

    let sym = null;
    if (hasSymbol(type)) {
      const room = rooms.find((r) => pointInPoly(pcx, pcy, r.geometry || []));
      const facing = facingOf(g, room ? centroid(room.geometry) : [pcx, pcy]);
      sym = furnitureSymbol(g, fy, u, { type, facing });
    }

    const hover = (e) => onHover && onHover({ x: e.clientX, y: e.clientY, kind: "furniture", title: type || f.name || "furniture", attrs: a });
    return (
      <g key={"fn" + i} className="spln-furn" onMouseMove={hover} onMouseLeave={() => onHover && onHover(null)}>
        <polygon className="spln-furn-fill" points={polyPoints(g, fy)} vectorEffect="non-scaling-stroke" />
        {sym}
        {!sym && type && (w >= 0.8 || h >= 0.8) && (
          <text className="spln-furn-label" x={cx} y={fy(pcy)} textAnchor="middle" dominantBaseline="central" fontSize={u * 0.85}>{type}</text>
        )}
      </g>
    );
  });
}

// Symbol construction is non-trivial; props are stable across hover → memo skips the
// per-mousemove rebuild SensePlan's hover state would trigger.
export default memo(FurnitureLayer);
