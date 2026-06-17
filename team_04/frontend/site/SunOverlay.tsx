/**
 * SunOverlay — Phase 1 sun-analysis overlay (the lockstep frontend counterpart
 * of agent/tools/sun_analysis.py).
 *
 * Renders, in one north-up SVG plan:
 *   - the site boundary, with each side tinted by its worst-sun exposure and the
 *     worst side called out (from POST /tools/worst_sun_side),
 *   - the focused building footprint with its facade test points coloured by
 *     exposure (from POST /tools/sun_exposure) — yellow = shaded, red = hit,
 *   - the dominant sun vector drawn as a diagonal arrow (light direction).
 *
 * Pure SVG; no chart dependency. Mirrors SiteCanvas's projection conventions so
 * the two can sit side by side. Lower exposure = better (avoid the worst sun).
 */
import type { SiteInfo, SunExposureResult, SunVector, WorstSunSide } from '../api/types';
import { computeBBox, makeProjector, polygonToPath } from './geometry';

export interface SunOverlayProps {
  site: SiteInfo | null;
  /** The focused building's footprint (so its facades can be scored). */
  buildingBoundary?: number[][];
  exposure?: SunExposureResult | null;
  worstSide?: WorstSunSide | null;
  /** Dominant sun vector to draw as the arrow (defaults to the first in exposure). */
  sun?: SunVector | null;
  width?: number;
  height?: number;
}

/** Yellow (shaded, good) → red (fully hit, bad) ramp for a 0–1 exposure value. */
function exposureColor(t: number): string {
  const c = Math.max(0, Math.min(1, t));
  const r = 255;
  const g = Math.round(225 - 185 * c);
  const b = Math.round(60 - 60 * c);
  return `rgb(${r},${g},${b})`;
}

/** Horizontal unit vector pointing toward the sun (compass bearing CW from North). */
function sunUnit(azimuthDeg: number): [number, number] {
  const a = (azimuthDeg * Math.PI) / 180;
  return [Math.sin(a), Math.cos(a)];
}

export function SunOverlay({
  site,
  buildingBoundary,
  exposure,
  worstSide,
  sun,
  width = 560,
  height = 460,
}: SunOverlayProps): JSX.Element {
  const bbox = computeBBox([site?.boundary, buildingBoundary]);
  const project = makeProjector(bbox, width, height);

  const sunVector = sun ?? exposure?.sun_vectors?.[0] ?? worstSide?.sun_vectors?.[0] ?? null;
  const hasGeometry = Boolean(site?.boundary?.length || buildingBoundary?.length);

  // Sun arrow: light flies FROM the sun toward the site centre.
  let arrow: { x1: number; y1: number; x2: number; y2: number } | null = null;
  if (sunVector && site?.boundary?.length) {
    const xs = site.boundary.map((p) => Number(p[0]));
    const ys = site.boundary.map((p) => Number(p[1]));
    const cx = xs.reduce((a, b) => a + b, 0) / xs.length;
    const cy = ys.reduce((a, b) => a + b, 0) / ys.length;
    const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    const [ux, uy] = sunUnit(sunVector.azimuth);
    const [x2, y2] = project([cx, cy]);
    const [x1, y1] = project([cx + ux * span * 0.55, cy + uy * span * 0.55]);
    arrow = { x1, y1, x2, y2 };
  }

  return (
    <svg
      width={width}
      height={height}
      style={{ background: '#f8f9fa', border: '1px solid #e2e6ea', borderRadius: 8, fontFamily: 'system-ui, sans-serif' }}
      role="img"
      aria-label="Sun exposure overlay"
    >
      <defs>
        <marker id="sun-arrow" markerWidth="10" markerHeight="10" refX="7" refY="3" orient="auto">
          <path d="M0,0 L7,3 L0,6 Z" fill="#e67e22" />
        </marker>
      </defs>

      {/* site boundary */}
      {site?.boundary?.length ? (
        <path d={polygonToPath(site.boundary, project)} fill="#ffffff" stroke="#2c3e50" strokeWidth={1.5} />
      ) : null}

      {/* per-side exposure tint + worst-side callout */}
      {worstSide?.per_side?.map((s) => {
        if (!site?.boundary) return null;
        const a = site.boundary[s.edge_index];
        const b = site.boundary[(s.edge_index + 1) % (site.boundary.length - (closedRing(site.boundary) ? 1 : 0))];
        if (!a || !b) return null;
        const [x1, y1] = project(a);
        const [x2, y2] = project(b);
        const isWorst = worstSide.worst_side?.edge_index === s.edge_index;
        const [mx, my] = project(s.midpoint);
        return (
          <g key={`side-${s.edge_index}`}>
            <line
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={exposureColor(s.sun_exposure_score)}
              strokeWidth={2 + 6 * s.sun_exposure_score}
              strokeLinecap="round"
            />
            <text x={mx} y={my} textAnchor="middle" fontSize={9} fontWeight={isWorst ? 700 : 400} fill="#34495e">
              {s.compass_sector} {s.sun_exposure_score.toFixed(2)}
              {isWorst ? ' ☀' : ''}
            </text>
          </g>
        );
      })}

      {/* focused building footprint */}
      {buildingBoundary?.length ? (
        <path d={polygonToPath(buildingBoundary, project)} fill="#ecf0f1" stroke="#7f8c8d" strokeWidth={1} />
      ) : null}

      {/* facade test points coloured by exposure */}
      {exposure?.per_test_point?.map((p, i) => {
        const [px, py] = project(p.point);
        return (
          <circle
            key={`pt-${i}`}
            cx={px}
            cy={py}
            r={3.5}
            fill={exposureColor(p.normalized_exposure)}
            stroke="#2c3e50"
            strokeWidth={0.4}
          />
        );
      })}

      {/* sun arrow */}
      {arrow ? (
        <g>
          <line
            x1={arrow.x1}
            y1={arrow.y1}
            x2={arrow.x2}
            y2={arrow.y2}
            stroke="#e67e22"
            strokeWidth={3}
            markerEnd="url(#sun-arrow)"
          />
          <circle cx={arrow.x1} cy={arrow.y1} r={9} fill="#f1c40f" stroke="#e67e22" />
          {sunVector ? (
            <text x={arrow.x1} y={arrow.y1 - 12} textAnchor="middle" fontSize={9} fill="#b9770e">
              sun az {sunVector.azimuth}° alt {sunVector.altitude}°
            </text>
          ) : null}
        </g>
      ) : null}

      {exposure ? (
        <text x={10} y={height - 10} fontSize={10} fill="#7f8c8d">
          building exposure {exposure.sun_exposure_score.toFixed(3)} (lower = better)
        </text>
      ) : null}

      {!hasGeometry && (
        <text x={width / 2} y={height / 2} textAnchor="middle" fontSize={13} fill="#95a5a6">
          Run a sun analysis to populate the overlay.
        </text>
      )}
    </svg>
  );
}

/** Whether a polygon's first and last vertex coincide (a closed ring). */
function closedRing(poly: number[][]): boolean {
  if (poly.length < 2) return false;
  const a = poly[0];
  const b = poly[poly.length - 1];
  return a[0] === b[0] && a[1] === b[1];
}

export default SunOverlay;
