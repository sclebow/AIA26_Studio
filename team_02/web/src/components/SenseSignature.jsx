import { SC, SI, SENSES, scoreOpacity } from "../lib/constants.js";

/*
 * SenseSignature — the lingua franca of Sensi.
 *
 * A room's six-sense comfort profile drawn as a radial "rose" fingerprint:
 *   - one petal per sense, in SENSES order, evenly spaced around the circle
 *   - petal HUE  = the sense        (principle: hue = sense)
 *   - petal LENGTH + OPACITY = the score (principle: intensity = health)
 *
 * Pure SVG on purpose — no chart library — so it renders identically at any
 * size (timeline chip, plan overlay, analysis panel) and shares one hover/
 * select idiom with the rest of the app.
 *
 * Props:
 *   scores       {thermal:0..1, ...}  the room's comfortScores (null → empty ring)
 *   size         number (px)          square viewport, default 64
 *   showGlyphs   bool                 draw the sense glyph at each petal tip
 *   activeSense  string|null          emphasize this sense, dim the others
 *   onSelectSense(sense)              makes petals interactive (selection bus)
 *   title        string               accessible label (e.g. room name)
 */
export default function SenseSignature({
  scores,
  baseScores = null,   // optional: draw the design-only score as a faint ghost outline
  size = 64,
  showGlyphs = false,
  activeSense = null,
  onSelectSense = null,
  title,
  x,            // optional: position when nested inside another <svg> (parent units)
  y,
  calm = false, // plan variant: quieter fill, thinner strokes, no reference ring
}) {
  const cx = size / 2;
  const cy = size / 2;
  const pad = showGlyphs ? size * 0.18 : size * 0.08;
  const rMax = size / 2 - pad;
  const rMin = rMax * 0.12;           // a small hub so even 0-scores read as a nub
  const half = 24;                    // petal half-angle (deg); 60° slots, ~12° gaps
  const interactive = typeof onSelectSense === "function";

  // angle measured from straight up, increasing clockwise (screen y-down)
  const polar = (r, deg) => {
    const t = (deg * Math.PI) / 180;
    return [cx + r * Math.sin(t), cy - r * Math.cos(t)];
  };

  const petal = (r, center) => {
    const [sx, sy] = polar(r, center - half);
    const [ex, ey] = polar(r, center + half);
    return `M ${cx} ${cy} L ${sx.toFixed(2)} ${sy.toFixed(2)} `
         + `A ${r.toFixed(2)} ${r.toFixed(2)} 0 0 1 ${ex.toFixed(2)} ${ey.toFixed(2)} Z`;
  };

  // faint reference ring at the 0.65 "good" threshold
  const refR = rMin + 0.65 * (rMax - rMin);

  return (
    <svg
      className="sense-signature"
      x={x}
      y={y}
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={title ? `Sense signature for ${title}` : "Sense signature"}
    >
      {!calm && (
        <circle
          cx={cx} cy={cy} r={refR}
          fill="none"
          stroke="rgba(var(--fg-rgb), var(--o-hairline))"
          strokeWidth="1"
          strokeDasharray="2 3"
        />
      )}
      {SENSES.map((s, i) => {
        const v = scores?.[s];
        const score = typeof v === "number" ? v : 0;
        const r = rMin + score * (rMax - rMin);
        const angle = i * 60;               // 0=top, clockwise
        const dim = activeSense && activeSense !== s;
        const op = scoreOpacity(score) * (dim ? 0.28 : 1) * (calm ? 0.7 : 1);
        const [gx, gy] = polar(rMax + size * 0.10, angle);
        // base (design-only) score as a faint ghost outline — only when it differs
        const bv = baseScores?.[s];
        const rBase = typeof bv === "number" ? rMin + bv * (rMax - rMin) : null;
        const showGhost = rBase != null && Math.abs(rBase - r) > size * 0.02;
        return (
          <g
            key={s}
            className={"ss-petal" + (interactive ? " ss-clickable" : "") + (activeSense === s ? " ss-active" : "")}
            onClick={interactive ? (e) => { e.stopPropagation(); onSelectSense(s); } : undefined}
          >
            {showGhost && (
              <path
                d={petal(rBase, angle)}
                fill="none"
                stroke={SC[s]}
                strokeOpacity={dim ? 0.12 : 0.32}
                strokeWidth="0.75"
                strokeDasharray="2 2"
              />
            )}
            <path
              d={petal(r, angle)}
              fill={SC[s]}
              fillOpacity={op}
              stroke={SC[s]}
              strokeOpacity={dim ? 0.2 : (calm ? 0.45 : 0.7)}
              strokeWidth={calm ? 0.5 : 1}
            />
            {showGlyphs && (
              <text
                x={gx} y={gy}
                fill={SC[s]}
                fillOpacity={dim ? 0.3 : 0.85}
                fontSize={size * 0.13}
                fontFamily="'IBM Plex Mono', monospace"
                textAnchor="middle"
                dominantBaseline="central"
              >{SI[s]}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
