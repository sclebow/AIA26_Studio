// The concentric six-sense ring mark, reused as the brand avatar everywhere.
// Ring colors come from the sense registry (lib/senses.js) — single source of
// truth — paired with the fixed radius ladder below. `animate={false}` renders
// the static mark; strokeWidth / centerR / centerOpacity let callers (e.g. the
// loading Overlay) match their exact weight without re-drawing the SVG.
import { SENSES, SC } from "../lib/senses.js";

const RADII = [14.5, 12, 9.5, 7, 4.5, 2]; // outer → inner, one per sense

export default function SensiAvatar({
  size = 28,
  className = "sensi-avatar",
  animate = true,
  strokeWidth = 0.8,
  centerR = 1.2,
  centerOpacity = 0.8,
}) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 32 32" fill="none">
      {RADII.map((r, i) => (
        <circle
          key={i}
          cx="16"
          cy="16"
          r={r}
          stroke={SC[SENSES[i]]}
          strokeWidth={strokeWidth}
          style={animate ? { animation: `srg${i} 3s ease-in-out infinite`, animationDelay: `${i * 0.5}s` } : undefined}
        />
      ))}
      <circle cx="16" cy="16" r={centerR} fill="var(--fg)" opacity={centerOpacity} />
    </svg>
  );
}
