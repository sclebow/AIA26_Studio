import { polyPoints, centroid, dims } from "../lib/geometry.js";

// Furniture footprints + a type label on pieces large enough to carry one.
// Hovering a piece raises its attributes (type, material) via onHover.
export default function FurnitureLayer({ furniture = [], fy, u, onHover }) {
  return furniture.map((f, i) => {
    const g = f.geometry || [];
    if (g.length < 3) return null;
    const a = f.attributes || {};
    const { cx, w, h } = dims(g);
    const [, fcy] = centroid(g);
    const hover = (e) => onHover && onHover({ x: e.clientX, y: e.clientY, kind: "furniture", title: a.type || f.name || "furniture", attrs: a });
    return (
      <g key={"fn" + i} className="spln-furn" onMouseMove={hover} onMouseLeave={() => onHover && onHover(null)}>
        <polygon className="spln-furn-fill" points={polyPoints(g, fy)} vectorEffect="non-scaling-stroke" />
        {a.type && (w >= 0.8 || h >= 0.8) && (
          <text className="spln-furn-label" x={cx} y={fy(fcy)} textAnchor="middle" dominantBaseline="central" fontSize={u * 0.85}>{a.type}</text>
        )}
      </g>
    );
  });
}
