/**
 * RoadOverlay — Phase 2 road context overlay (lockstep frontend counterpart
 * of agent/tools/road_context.py).
 *
 * Renders, in one north-up SVG plan:
 *   - the site boundary,
 *   - each road centreline coloured by hierarchy (main=red, secondary=orange, path=teal),
 *   - the road width as a semi-transparent buffer strip,
 *   - each site side coloured by its nearest adjacent road (grey when none),
 *   - the main road side highlighted with a bold stroke.
 *
 * Pure SVG; mirrors SiteCanvas's projection so the two compose.  The visual
 * story: the agent knows which side faces the street and uses that to orient
 * the grid and place parking near the main road.
 *
 * Backend source: agent/tools/road_context.py
 * API:           POST /tools/road_context → RoadContextResult
 * Contract:      decision-graph/CONTRACT.md §9
 */
import type { RoadContextResult, SiteInfo } from '../api/types';
import { computeBBox, makeProjector, polygonToPath } from './geometry';

export interface RoadOverlayProps {
  site: SiteInfo | null;
  roadContext: RoadContextResult | null;
  width?: number;
  height?: number;
}

const HIER_COLOUR: Record<string, string> = {
  main:      '#E63946',
  secondary: '#F4A261',
  path:      '#2A9D8F',
};
const HIER_STROKE_W: Record<string, number> = {
  main: 4,
  secondary: 2.5,
  path: 1.5,
};

export function RoadOverlay({
  site,
  roadContext,
  width = 600,
  height = 500,
}: RoadOverlayProps): JSX.Element | null {
  if (!site || !roadContext) return null;

  const bbox = computeBBox([site.boundary]);
  const project = makeProjector(bbox, width, height, 24);

  const sitePath = polygonToPath(site.boundary, project);
  const sides = roadContext.updated_sides ?? [];
  const roads = roadContext.roads ?? [];
  const mainSi = roadContext.main_road_side_index;

  // Project a centerline (list of [x,y]) to SVG path
  function clPath(cl: number[][]): string {
    return cl
      .map((p, i) => {
        const [sx, sy] = project(p);
        return `${i === 0 ? 'M' : 'L'}${sx.toFixed(1)},${sy.toFixed(1)}`;
      })
      .join(' ');
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ overflow: 'visible' }}
    >
      {/* Site fill */}
      <path d={sitePath} fill="#457B9D" fillOpacity={0.08} stroke="#1D3557" strokeWidth={1.5} />

      {/* Site sides coloured by adjacent road */}
      {sides.map((side, i) => {
        const adj = side.adjacent_road as {
          hierarchy: string; name?: string | null; width_m: number; distance_m: number
        } | null;
        const colour = adj ? (HIER_COLOUR[adj.hierarchy] ?? '#888') : '#AAAAAA';
        const isMain = i === mainSi;
        // Find corner coordinates from site boundary
        const n = site.boundary.length - 1; // last == first
        const p1 = site.boundary[i % n];
        const p2 = site.boundary[(i + 1) % n];
        const [x1, y1] = project(p1);
        const [x2, y2] = project(p2);
        return (
          <line
            key={`side-${i}`}
            x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={colour}
            strokeWidth={isMain ? 7 : 4}
            strokeOpacity={isMain ? 0.8 : 0.55}
            strokeLinecap="round"
          >
            <title>
              {adj
                ? `side ${i}: ${adj.name ?? adj.hierarchy} — ${adj.hierarchy}, ${adj.width_m} m, ${adj.distance_m} m away`
                : `side ${i}: no adjacent road`}
            </title>
          </line>
        );
      })}

      {/* Road centrelines + width buffers */}
      {roads.map((road, i) => {
        const colour = HIER_COLOUR[road.hierarchy] ?? '#888';
        const sw = HIER_STROKE_W[road.hierarchy] ?? 2;
        const path = clPath(road.centerline);
        return (
          <g key={`road-${i}`}>
            {/* Width buffer (visual approximation — not an exact offset) */}
            <path
              d={path}
              stroke={colour}
              strokeWidth={Math.max(sw, 4)}
              strokeOpacity={0.12}
              fill="none"
              strokeLinecap="round"
            />
            {/* Centreline */}
            <path
              d={path}
              stroke={colour}
              strokeWidth={sw}
              fill="none"
              strokeDasharray={road.hierarchy === 'path' ? '4 3' : undefined}
              strokeLinecap="round"
            >
              <title>
                {`${road.name ?? road.hierarchy} — ${road.hierarchy}, ${road.width_m} m wide, ${road.frontage_m.toFixed(0)} m frontage`}
              </title>
            </path>
          </g>
        );
      })}

      {/* Legend */}
      {(['main', 'secondary', 'path'] as const).map((h, i) => (
        <g key={`legend-${h}`} transform={`translate(${width - 160}, ${16 + i * 20})`}>
          <line x1={0} y1={8} x2={24} y2={8} stroke={HIER_COLOUR[h]} strokeWidth={HIER_STROKE_W[h]} />
          <text x={28} y={12} fontSize={10} fill="#333">{h}</text>
        </g>
      ))}
      {roadContext.ambiguity && (
        <text x={8} y={height - 8} fontSize={10} fill="#E63946">
          ⚠ {roadContext.ambiguity_message ?? roadContext.ambiguity}
        </text>
      )}
    </svg>
  );
}
