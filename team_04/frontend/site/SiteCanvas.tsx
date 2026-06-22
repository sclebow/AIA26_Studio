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
import type { BuildingInfo, ParkingZone, PlacementOption, SiteInfo } from '../api/types';
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
  const parkingZones: ParkingZone[] = site?.parking_zones ?? [];

  const allPolys = [
    site?.boundary,
    site?.buildable_boundary ?? undefined,
    ...buildings.map((b) => b.boundary),
    ...ghostOptions.map((o) => o.boundary),
    ...parkingZones.map((z) => z.boundary),
  ];
  const bbox = computeBBox(allPolys);
  const project = makeProjector(bbox, width, height);

  const hasGeometry = Boolean(site?.boundary?.length || buildings.length);

  // Unique SVG pattern id for parking hatch (scoped to avoid global collisions)
  const hatchId = 'parking-hatch';

  return (
    <svg
      width={width}
      height={height}
      style={{ background: '#f8f9fa', border: '1px solid #e2e6ea', borderRadius: 8, fontFamily: 'system-ui, sans-serif' }}
      role="img"
      aria-label="Site plan"
    >
      {/* SVG defs: parking hatch pattern */}
      <defs>
        <pattern id={hatchId} patternUnits="userSpaceOnUse" width={8} height={8} patternTransform="rotate(45)">
          <line x1={0} y1={0} x2={0} y2={8} stroke="#b8860b" strokeWidth={2} strokeOpacity={0.55} />
        </pattern>
      </defs>

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

      {/* Phase 4 — parking zones (hatched yellow-gold fill) */}
      {parkingZones.map((z) => {
        const [pcx, pcy] = centroidOf(z.boundary);
        const [ppx, ppy] = project([pcx, pcy]);
        const roadBadge = z.is_main_road_side ? '★ ' : '';
        return (
          <g key={z.zone_id}>
            <path
              d={polygonToPath(z.boundary, project)}
              fill={`url(#${hatchId})`}
              stroke="#b8860b"
              strokeWidth={1.5}
              strokeDasharray="5 3"
            />
            <text x={ppx} y={ppy - 3} textAnchor="middle" fontSize={9} fontWeight={700} fill="#7d6008">
              {roadBadge}P {z.stalls_allocated}
            </text>
            <text x={ppx} y={ppy + 9} textAnchor="middle" fontSize={8} fill="#7d6008">
              {z.area_sqm.toFixed(0)} m²
            </text>
          </g>
        );
      })}

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

      {/* Legend — only when parking zones are present */}
      {parkingZones.length > 0 && (
        <g transform={`translate(${width - 110}, ${height - 28})`}>
          <rect x={0} y={0} width={12} height={12} fill={`url(#${hatchId})`} stroke="#b8860b" strokeWidth={1} />
          <text x={16} y={10} fontSize={9} fill="#7d6008">
            Parking ({parkingZones.reduce((s, z) => s + z.stalls_allocated, 0)} stalls)
          </text>
        </g>
      )}
    </svg>
  );
}

export default SiteCanvas;
