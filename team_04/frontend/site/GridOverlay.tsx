/**
 * GridOverlay — Phase 3 site-grid & side-alignment overlay (the lockstep
 * frontend counterpart of agent/tools/site_grid.py).
 *
 * Renders, in one north-up SVG plan:
 *   - the site boundary + buildable zone,
 *   - the derived grid (lines + seed nodes) aligned to the chosen side,
 *   - the chosen side highlighted (the frontage buildings line up parallel to),
 *   - grid-aligned placement options (from optimize_aligned_placement), best
 *     option solid, the rest as dashed ghosts.
 *
 * Pure SVG; mirrors SiteCanvas's projection so the two compose. The point this
 * makes visually: buildings sit on the grid, parallel to the chosen side — they
 * are never at a random angle.
 */
import type { AlignedOption, SiteGrid, SiteInfo } from '../api/types';
import { computeBBox, makeProjector, polygonToPath } from './geometry';

export interface GridOverlayProps {
  site: SiteInfo | null;
  grid: SiteGrid | null;
  /** Grid-aligned placement options; options[0] is drawn solid (the best). */
  options?: AlignedOption[];
  /** option_id to highlight instead of options[0]. */
  selectedOptionId?: string;
  width?: number;
  height?: number;
}

export function GridOverlay({
  site,
  grid,
  options = [],
  selectedOptionId,
  width = 560,
  height = 460,
}: GridOverlayProps): JSX.Element {
  const lineEndpoints = (grid?.grid_lines ?? []).flat();
  const bbox = computeBBox([site?.boundary, site?.buildable_boundary ?? undefined, lineEndpoints, ...options.map((o) => o.boundary)]);
  const project = makeProjector(bbox, width, height);

  const chosen = chosenSideSegment(site, grid);
  const selectedId = selectedOptionId ?? options[0]?.option_id;
  const hasGeometry = Boolean(site?.boundary?.length || grid?.available);

  return (
    <svg
      width={width}
      height={height}
      style={{ background: '#f8f9fa', border: '1px solid #e2e6ea', borderRadius: 8, fontFamily: 'system-ui, sans-serif' }}
      role="img"
      aria-label="Site grid and alignment overlay"
    >
      {/* site boundary */}
      {site?.boundary?.length ? (
        <path d={polygonToPath(site.boundary, project)} fill="#ffffff" stroke="#2c3e50" strokeWidth={1.5} />
      ) : null}

      {/* buildable zone */}
      {site?.buildable_boundary?.length ? (
        <path d={polygonToPath(site.buildable_boundary, project)} fill="none" stroke="#27ae60" strokeWidth={1.2} strokeDasharray="6 4" />
      ) : null}

      {/* grid lines */}
      {(grid?.grid_lines ?? []).map((seg, i) => {
        const [x1, y1] = project(seg[0]);
        const [x2, y2] = project(seg[1]);
        return <line key={`gl-${i}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#b0c4de" strokeWidth={0.6} />;
      })}

      {/* grid nodes */}
      {(grid?.grid_nodes ?? []).map((n, i) => {
        const [x, y] = project(n);
        return <circle key={`gn-${i}`} cx={x} cy={y} r={1.6} fill="#5d6d7e" />;
      })}

      {/* chosen side (the frontage) */}
      {chosen ? (
        <line
          x1={project(chosen[0])[0]}
          y1={project(chosen[0])[1]}
          x2={project(chosen[1])[0]}
          y2={project(chosen[1])[1]}
          stroke="#e67e22"
          strokeWidth={4}
        />
      ) : null}

      {/* aligned placement options */}
      {options.map((o) => {
        const best = o.option_id === selectedId;
        return (
          <path
            key={o.option_id}
            d={polygonToPath(o.boundary, project)}
            fill={best ? (o.use === 'commercial' ? 'rgba(192,57,43,0.7)' : 'rgba(41,128,185,0.65)') : 'none'}
            stroke={best ? '#1b2631' : '#aab'}
            strokeWidth={best ? 1.6 : 0.8}
            strokeDasharray={best ? undefined : '4 3'}
          />
        );
      })}

      {grid?.available ? (
        <text x={10} y={height - 10} fontSize={10} fill="#7f8c8d">
          grid {grid.angle_deg?.toFixed(1)}° · side {grid.alignment_side_label ?? grid.alignment_side_index} · {grid.node_count ?? grid.grid_nodes?.length ?? 0} nodes
        </text>
      ) : null}

      {!hasGeometry && (
        <text x={width / 2} y={height / 2} textAnchor="middle" fontSize={13} fill="#95a5a6">
          Derive a site grid to populate the overlay.
        </text>
      )}
    </svg>
  );
}

/** The chosen side as a [start, end] segment, read off the site boundary. */
function chosenSideSegment(site: SiteInfo | null, grid: SiteGrid | null): [number[], number[]] | null {
  if (!site?.boundary?.length || !grid?.available || grid.alignment_side_index == null) return null;
  const ring = closedRing(site.boundary) ? site.boundary.slice(0, -1) : site.boundary;
  const i = grid.alignment_side_index % ring.length;
  return [ring[i], ring[(i + 1) % ring.length]];
}

function closedRing(poly: number[][]): boolean {
  if (poly.length < 2) return false;
  const a = poly[0];
  const b = poly[poly.length - 1];
  return a[0] === b[0] && a[1] === b[1];
}

export default GridOverlay;
