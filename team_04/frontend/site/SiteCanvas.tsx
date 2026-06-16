/**
 * SiteCanvas — 2D plan view of what the agent has built.
 *
 * Renders, from the backend explorer payload:
 *   - the site boundary and (dashed) buildable zone after setbacks,
 *   - every placed building footprint, coloured by footprint family
 *     (I/L/T/U/H/Y/X/O) with its label, type, and view score,
 *   - optionally, the Pareto placement options for a focused building as faint
 *     ghosts (this is the "placed based on view analysis" story), with the
 *     selected option highlighted.
 *
 * Pure SVG — no chart dependency. Auto-fits all geometry, north-up.
 */
import type { BuildingInfo, PlacementOption, SiteInfo } from '../api/types';
import {
  buildingColor,
  centroidOf,
  computeBBox,
  makeProjector,
  polygonToPath,
} from './geometry';

export interface SiteCanvasProps {
  site: SiteInfo | null;
  buildings: BuildingInfo[];
  /** Pareto options to overlay as ghosts (e.g. for the focused building). */
  ghostOptions?: PlacementOption[];
  /** option_id of the highlighted ghost. */
  selectedOptionId?: string;
  /** building_id currently focused (drawn with an accent outline). */
  focusedBuildingId?: string;
  width?: number;
  height?: number;
  onSelectBuilding?: (buildingId: string) => void;
}

export function SiteCanvas({
  site,
  buildings,
  ghostOptions = [],
  selectedOptionId,
  focusedBuildingId,
  width = 560,
  height = 460,
  onSelectBuilding,
}: SiteCanvasProps): JSX.Element {
  const allPolys = [
    site?.boundary,
    site?.buildable_boundary ?? undefined,
    ...buildings.map((b) => b.boundary),
    ...ghostOptions.map((o) => o.boundary),
  ];
  const bbox = computeBBox(allPolys);
  const project = makeProjector(bbox, width, height);

  const hasGeometry = Boolean(site?.boundary?.length || buildings.length);

  return (
    <svg
      width={width}
      height={height}
      style={{ background: '#f8f9fa', border: '1px solid #e2e6ea', borderRadius: 8, fontFamily: 'system-ui, sans-serif' }}
      role="img"
      aria-label="Site plan"
    >
      {/* site boundary */}
      {site?.boundary?.length ? (
        <path d={polygonToPath(site.boundary, project)} fill="#ffffff" stroke="#2c3e50" strokeWidth={2} />
      ) : null}

      {/* buildable zone after setbacks */}
      {site?.buildable_boundary?.length ? (
        <path
          d={polygonToPath(site.buildable_boundary, project)}
          fill="none"
          stroke="#27ae60"
          strokeWidth={1.4}
          strokeDasharray="6 4"
        />
      ) : null}

      {/* Pareto ghosts for the focused building */}
      {ghostOptions.map((o) => {
        const selected = o.option_id === selectedOptionId;
        return (
          <path
            key={`ghost-${o.option_id}`}
            d={polygonToPath(o.boundary, project)}
            fill={selected ? 'rgba(243,156,18,0.18)' : 'none'}
            stroke={selected ? '#f39c12' : '#b0a8c0'}
            strokeWidth={selected ? 2 : 1}
            strokeDasharray={selected ? undefined : '4 3'}
          />
        );
      })}

      {/* placed buildings */}
      {buildings.map((b, i) => {
        const color = buildingColor(b.building_type);
        const focused = b.building_id === focusedBuildingId;
        const [cx, cy] = b.boundary?.length ? centroidOf(b.boundary) : [b.centroid[0], b.centroid[1]];
        const [px, py] = project([cx, cy]);
        return (
          <g
            key={b.building_id || i}
            onClick={() => onSelectBuilding?.(b.building_id)}
            style={{ cursor: onSelectBuilding ? 'pointer' : 'default' }}
          >
            <path
              d={polygonToPath(b.boundary, project)}
              fill={color}
              fillOpacity={0.55}
              stroke={focused ? '#f39c12' : color}
              strokeWidth={focused ? 3 : 1.5}
            />
            <text x={px} y={py} textAnchor="middle" fontSize={11} fontWeight={700} fill="#1b2631">
              {b.label}
            </text>
            <text x={px} y={py + 13} textAnchor="middle" fontSize={9} fill="#2c3e50">
              {[b.building_type ?? '?', b.view_score != null ? `view ${b.view_score.toFixed(2)}` : null]
                .filter(Boolean)
                .join(' · ')}
            </text>
          </g>
        );
      })}

      {!hasGeometry && (
        <text x={width / 2} y={height / 2} textAnchor="middle" fontSize={13} fill="#95a5a6">
          No site or buildings yet — run a prompt to populate the plan.
        </text>
      )}
    </svg>
  );
}

export default SiteCanvas;
