/**
 * UrbanAnalysisOverlay — Phase 2b urban context overlay.
 *
 * Renders in a north-up SVG plan:
 *   - Road network coloured by hierarchy (main / secondary / path)
 *   - Intersection markers coloured by type (crossroads / T-junction / Y / …)
 *   - Site boundary with frontage sides highlighted by visibility score
 *   - Access point arrows (vehicle / pedestrian / service)
 *   - Corner condition dots (larger = higher visibility; red border = gateway)
 *   - Urban response badge showing the classified site type
 *
 * Composes with RoadOverlay and SiteCanvas (same projector convention).
 *
 * Backend source: agent/tools/urban_analysis.py + osm_context.py
 * API:           POST /tools/urban_analysis → UrbanAnalysisResult
 * Contract:      decision-graph/CONTRACT.md §10
 */
import type { UrbanAnalysisResult, SiteInfo, FrontageInfo } from '../api/types';
import { computeBBox, makeProjector, polygonToPath } from './geometry';

export interface UrbanAnalysisOverlayProps {
  site: SiteInfo | null;
  analysis: UrbanAnalysisResult | null;
  width?: number;
  height?: number;
  showAccess?: boolean;
  showIntersections?: boolean;
  showResponse?: boolean;
}

// Hierarchy palette (matches RoadOverlay)
const HIER_COLOUR: Record<string, string> = {
  main:      '#E63946',
  secondary: '#F4A261',
  path:      '#2A9D8F',
};

// Intersection type palette
const IX_COLOUR: Record<string, string> = {
  crossroads:      '#9B2226',
  t_junction:      '#AE2012',
  y_junction:      '#CA6702',
  complex_junction:'#6A0572',
  dead_end:        '#555555',
  bend:            '#AAAAAA',
};

const IX_LABEL: Record<string, string> = {
  crossroads:       '✕',
  t_junction:       'T',
  y_junction:       'Y',
  complex_junction: '✦',
  dead_end:         '·',
  bend:             '·',
};

// Access point palette
const ACCESS_COLOUR: Record<string, string> = {
  vehicle:    '#264653',
  pedestrian: '#2A9D8F',
  service:    '#E9C46A',
};

// Visibility score → green heatmap
function _visColour(score: number): string {
  // score 0..1 → yellow (#F4E285) to green (#2A9D8F)
  const r = Math.round(244 + (42 - 244) * score);
  const g = Math.round(226 + (157 - 226) * score);
  const b = Math.round(133 + (143 - 133) * score);
  return `rgb(${r},${g},${b})`;
}

export function UrbanAnalysisOverlay({
  site,
  analysis,
  width = 700,
  height = 560,
  showAccess = true,
  showIntersections = true,
  showResponse = true,
}: UrbanAnalysisOverlayProps): JSX.Element | null {
  if (!site || !analysis) return null;

  const bbox = computeBBox([site.boundary]);
  const project = makeProjector(bbox, width, height, 28);
  const sitePath = polygonToPath(site.boundary, project);
  const n = site.boundary.length - 1; // closed polygon: last == first

  const frontages = analysis.frontages ?? [];
  const frontagesBySide = new Map<number, FrontageInfo>(frontages.map(f => [f.side_index, f]));
  const corners = analysis.corner_conditions ?? [];
  const access = analysis.access ?? { vehicle: [], pedestrian: [], service: [] };
  const ixs = showIntersections ? (analysis.nearby_intersections ?? []) : [];

  // --- Site boundary sides with frontage highlighting ---
  const sideLines = Array.from({ length: n }, (_, i) => {
    const p1 = site.boundary[i];
    const p2 = site.boundary[(i + 1) % n];
    const [x1, y1] = project(p1);
    const [x2, y2] = project(p2);
    const f = frontagesBySide.get(i);
    const colour = f ? _visColour(f.visibility_score) : '#CCCCCC';
    const sw = f ? 6 + f.visibility_score * 4 : 2;
    return { i, x1, y1, x2, y2, f, colour, sw };
  });

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ overflow: 'visible', fontFamily: 'sans-serif' }}
    >
      {/* ── Site fill ─────────────────────────────────────────────── */}
      <path d={sitePath} fill="#457B9D" fillOpacity={0.08} stroke="none" />

      {/* ── Road centrelines (from analysis frontages + nearby) ───── */}
      {frontages.map((f, fi) => {
        // We draw a pseudo-centreline parallel to the frontage side, offset outward
        const si = f.side_index;
        if (si >= n) return null;
        const p1 = site.boundary[si];
        const p2 = site.boundary[(si + 1) % n];
        const [x1, y1] = project(p1);
        const [x2, y2] = project(p2);
        const dx = x2 - x1; const dy = y2 - y1;
        const L = Math.hypot(dx, dy) || 1;
        // Outward normal: offset by ~16px
        const ox = (-dy / L) * 16;
        const oy = (dx / L) * 16;
        const colour = HIER_COLOUR[f.road_hierarchy] ?? '#888';
        const sw = f.road_hierarchy === 'main' ? 4 : (f.road_hierarchy === 'secondary' ? 2.5 : 1.5);
        return (
          <g key={`road-${fi}`}>
            {/* Width buffer */}
            <line x1={x1 + ox} y1={y1 + oy} x2={x2 + ox} y2={y2 + oy}
              stroke={colour} strokeWidth={Math.max(sw, 3) * 2.5}
              strokeOpacity={0.12} strokeLinecap="round" />
            {/* Centreline */}
            <line x1={x1 + ox} y1={y1 + oy} x2={x2 + ox} y2={y2 + oy}
              stroke={colour} strokeWidth={sw} strokeLinecap="round"
              strokeDasharray={f.road_hierarchy === 'path' ? '5 3' : undefined}>
              <title>{`${f.road_name ?? f.road_hierarchy} — ${f.road_hierarchy}, ${f.road_width_m} m`}</title>
            </line>
          </g>
        );
      })}

      {/* ── Site sides coloured by frontage visibility ────────────── */}
      {sideLines.map(({ i, x1, y1, x2, y2, f, colour, sw }) => (
        <line key={`side-${i}`}
          x1={x1} y1={y1} x2={x2} y2={y2}
          stroke={colour} strokeWidth={sw}
          strokeOpacity={f ? 0.85 : 0.35}
          strokeLinecap="round">
          <title>
            {f
              ? `side ${i}: ${f.road_name ?? f.road_hierarchy} | vis ${(f.visibility_score * 100).toFixed(0)}%`
              : `side ${i}: no frontage`}
          </title>
        </line>
      ))}

      {/* ── Site boundary outline ────────────────────────────────────*/}
      <path d={sitePath} fill="none" stroke="#1D3557" strokeWidth={1.5} strokeDasharray="3 3" />

      {/* ── Intersection markers ──────────────────────────────────── */}
      {showIntersections && ixs.map((ix, ii) => {
        const [sx, sy] = project(ix.point);
        const col = IX_COLOUR[ix.type] ?? '#888';
        const lbl = IX_LABEL[ix.type] ?? '?';
        return (
          <g key={`ix-${ii}`}>
            <circle cx={sx} cy={sy} r={10} fill={col} fillOpacity={0.15} stroke={col} strokeWidth={1.5} />
            <text x={sx} y={sy + 4} textAnchor="middle" fontSize={9} fontWeight="bold" fill={col}>{lbl}</text>
            <title>{`${ix.type} (degree ${ix.degree}) — ${ix.distance_to_site_m} m from site`}</title>
          </g>
        );
      })}

      {/* ── Corner condition dots ─────────────────────────────────── */}
      {corners.map((c, ci) => {
        const [sx, sy] = project(c.point);
        const r = 6 + c.visibility_score * 7;
        const fill = _visColour(c.visibility_score);
        return (
          <g key={`corner-${ci}`}>
            <circle cx={sx} cy={sy} r={r} fill={fill} fillOpacity={0.8}
              stroke={c.is_gateway ? '#E63946' : '#2A9D8F'} strokeWidth={c.is_gateway ? 2.5 : 1} />
            {c.is_gateway && (
              <text x={sx} y={sy + 4} textAnchor="middle" fontSize={8} fontWeight="bold" fill="#E63946">G</text>
            )}
            <title>
              {`Corner ${c.corner_index}: vis ${(c.visibility_score * 100).toFixed(0)}%` +
               (c.is_gateway ? ' — GATEWAY' : '')}
            </title>
          </g>
        );
      })}

      {/* ── Access points ─────────────────────────────────────────── */}
      {showAccess && (
        <g>
          {(['vehicle', 'pedestrian', 'service'] as const).map(cat =>
            access[cat].map((ap, ai) => {
              const [sx, sy] = project(ap.point);
              const col = ACCESS_COLOUR[cat];
              const sym = cat === 'vehicle' ? '▶' : (cat === 'pedestrian' ? '♟' : '⚙');
              return (
                <g key={`${cat}-${ai}`}>
                  <circle cx={sx} cy={sy} r={9} fill={col} fillOpacity={0.9} />
                  <text x={sx} y={sy + 4} textAnchor="middle" fontSize={8} fill="white">{sym}</text>
                  <title>{`${cat}: ${ap.notes}`}</title>
                </g>
              );
            })
          )}
        </g>
      )}

      {/* ── Urban response badge ──────────────────────────────────── */}
      {showResponse && analysis.urban_response && (
        <g transform={`translate(8, ${height - 64})`}>
          <rect x={0} y={0} width={220} height={56} rx={4}
            fill="#1D3557" fillOpacity={0.85} />
          <text x={8} y={18} fontSize={10} fontWeight="bold" fill="#F1FAEE">
            {analysis.urban_response.site_type_label}
          </text>
          <text x={8} y={34} fontSize={8} fill="#A8DADC" style={{ fontSize: '8px' }}>
            {analysis.urban_response.building_response.slice(0, 60)}…
          </text>
          <text x={8} y={50} fontSize={8} fill="#A8DADC">
            {`${analysis.frontage_count} frontage${analysis.frontage_count !== 1 ? 's' : ''} · ${ixs.length} junction${ixs.length !== 1 ? 's' : ''} nearby`}
          </text>
        </g>
      )}

      {/* ── Legend ────────────────────────────────────────────────── */}
      <g transform={`translate(${width - 148}, 12)`}>
        <rect x={-4} y={-4} width={152} height={120} rx={3}
          fill="white" fillOpacity={0.88} stroke="#ddd" strokeWidth={0.5} />
        {/* Road hierarchy */}
        {(['main', 'secondary', 'path'] as const).map((h, i) => (
          <g key={h} transform={`translate(0,${i * 16})`}>
            <line x1={0} y1={6} x2={18} y2={6} stroke={HIER_COLOUR[h]}
              strokeWidth={h === 'main' ? 3.5 : (h === 'secondary' ? 2 : 1.5)} />
            <text x={22} y={10} fontSize={9} fill="#333">{h} road</text>
          </g>
        ))}
        {/* Intersection types */}
        {(['crossroads', 't_junction', 'y_junction'] as const).map((t, i) => (
          <g key={t} transform={`translate(0,${(i + 4) * 16})`}>
            <circle cx={8} cy={6} r={7} fill={IX_COLOUR[t]} fillOpacity={0.2}
              stroke={IX_COLOUR[t]} strokeWidth={1} />
            <text x={8} y={10} textAnchor="middle" fontSize={7} fill={IX_COLOUR[t]}>
              {IX_LABEL[t]}
            </text>
            <text x={22} y={10} fontSize={9} fill="#333">
              {t.replace('_', ' ')}
            </text>
          </g>
        ))}
        {/* Access */}
        {(['vehicle', 'pedestrian', 'service'] as const).map((cat, i) => (
          <g key={cat} transform={`translate(0,${(i + 8) * 16 - 4})`}>
            <circle cx={8} cy={6} r={6} fill={ACCESS_COLOUR[cat]} />
            <text x={22} y={10} fontSize={9} fill="#333">{cat} access</text>
          </g>
        ))}
      </g>

      {/* ── Ambiguity warning ─────────────────────────────────────── */}
      {!analysis.available && analysis.ambiguity_message && (
        <text x={8} y={height - 8} fontSize={10} fill="#E63946">
          ⚠ {analysis.ambiguity_message}
        </text>
      )}
    </svg>
  );
}
