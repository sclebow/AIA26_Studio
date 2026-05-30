import { polyPoints, centroid, dims } from "../lib/geometry.js";

// Furniture footprints + a type label on pieces large enough to carry one.
export default function FurnitureLayer({ furniture = [], fy, u }) {
  return furniture.map((f, i) => {
    const g = f.geometry || [];
    if (g.length < 3) return null;
    const a = f.attributes || {};
    const { cx, w, h } = dims(g);
    const [, fcy] = centroid(g);
    return (
      <g key={"fn" + i} className="spln-furn">
        <polygon className="spln-furn-fill" points={polyPoints(g, fy)} vectorEffect="non-scaling-stroke" />
        {a.type && (w >= 0.8 || h >= 0.8) && (
          <text className="spln-furn-label" x={cx} y={fy(fcy)} textAnchor="middle" dominantBaseline="central" fontSize={u * 0.85}>{a.type}</text>
        )}
      </g>
    );
  });
}
