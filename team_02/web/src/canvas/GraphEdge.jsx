import { arc } from "../lib/geometry.js";

// One relationship edge, the shared visual primitive: a glowing Bézier arc with
// an optional arrowhead, a provenance line-style (dash), and a hover state that
// brightens + marches. Width = px stroke (non-scaling). headSize = user units.
export default function GraphEdge({
  ax, ay, bx, by, color, width = 2, dash, arrow = false, headSize = 0,
  glow = true, curvature = 0.18, opacity = 0.85, live = false, onHover, onLeave, hitWidth,
}) {
  const a = arc(ax, ay, bx, by, curvature);
  let head = null;
  if (arrow && headSize > 0) {
    const px = -a.edy, py = a.edx;
    const b1x = bx - a.edx * headSize + px * headSize * 0.55, b1y = by - a.edy * headSize + py * headSize * 0.55;
    const b2x = bx - a.edx * headSize - px * headSize * 0.55, b2y = by - a.edy * headSize - py * headSize * 0.55;
    head = <polygon points={`${bx},${by} ${b1x},${b1y} ${b2x},${b2y}`} fill={color} pointerEvents="none" />;
  }
  // Decorative strokes are pointer-transparent; the single wide transparent path
  // below is the ONLY hit target, so adjacent edges don't fight over hover.
  const hit = hitWidth ?? Math.max(width * 4, 10);
  return (
    <g opacity={opacity} onMouseMove={onHover} onMouseLeave={onLeave} style={onHover ? { cursor: "help" } : undefined}>
      {glow && <path d={a.d} fill="none" stroke={color} strokeWidth={width * 3} strokeOpacity={0.16} strokeLinecap="round" vectorEffect="non-scaling-stroke" pointerEvents="none" />}
      <path className={"graph-edge" + (live ? " is-live" : "")} d={a.d} fill="none" stroke={color}
        strokeWidth={width} strokeDasharray={live ? undefined : dash} strokeLinecap="round" vectorEffect="non-scaling-stroke" pointerEvents="none" />
      {head}
      {onHover && <path d={a.d} fill="none" stroke="transparent" strokeWidth={hit} vectorEffect="non-scaling-stroke" />}
    </g>
  );
}
