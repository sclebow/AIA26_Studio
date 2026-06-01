import { polyPoints } from "../lib/geometry.js";

// Structural shell: the exterior outline + interior structure walls.
export default function WallsLayer({ outline = [], structure = [], fy }) {
  return (
    <>
      {outline.length > 1 && (
        <polyline className="spln-wall-ext" points={polyPoints(outline, fy)} fill="none" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      )}
      {structure.map((w, i) => {
        const g = w.geometry || [];
        return g.length > 1 ? <polyline key={"st" + i} className="spln-wall-in" points={polyPoints(g, fy)} fill="none" vectorEffect="non-scaling-stroke" /> : null;
      })}
    </>
  );
}
