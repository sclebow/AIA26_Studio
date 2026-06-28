/**
 * ExplorerPanel — the agent's object hierarchy as a collapsible tree.
 *
 * Site → buildings → (wings, view score, Pareto placement options). Maps the
 * GET /sessions/{id}/explorer payload. Selecting a building focuses it on the
 * SiteCanvas; selecting an option highlights that Pareto ghost.
 */
import React from 'react';

import type { BuildingInfo, ExplorerTree, PlacementOption } from '../api/types';
import { buildingColor } from '../site/geometry';

export interface ExplorerPanelProps {
  tree: ExplorerTree | null;
  focusedBuildingId?: string;
  selectedOptionId?: string;
  onFocusBuilding?: (buildingId: string) => void;
  onSelectOption?: (buildingId: string, option: PlacementOption) => void;
}

function Row({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, padding: '1px 0' }}>
      <span style={{ color: '#7f8c8d' }}>{label}</span>
      <span style={{ color: '#2c3e50', fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function OptionsTable({
  building,
  selectedOptionId,
  onSelectOption,
}: {
  building: BuildingInfo;
  selectedOptionId?: string;
  onSelectOption?: (buildingId: string, option: PlacementOption) => void;
}): JSX.Element | null {
  if (!building.placement_options.length) return null;
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10, marginTop: 4 }}>
      <thead>
        <tr style={{ color: '#7f8c8d', textAlign: 'left' }}>
          <th style={{ padding: '2px 4px' }}>#</th>
          <th style={{ padding: '2px 4px' }}>score</th>
          <th style={{ padding: '2px 4px' }}>view</th>
          <th style={{ padding: '2px 4px' }}>rot</th>
          <th style={{ padding: '2px 4px' }}>fit</th>
        </tr>
      </thead>
      <tbody>
        {building.placement_options.map((o) => {
          const sel = o.option_id === selectedOptionId;
          return (
            <tr
              key={o.option_id}
              onClick={() => onSelectOption?.(building.building_id, o)}
              style={{
                cursor: onSelectOption ? 'pointer' : 'default',
                background: sel ? '#fef5e7' : 'transparent',
                color: o.fits_within_site ? '#2c3e50' : '#c0392b',
              }}
            >
              <td style={{ padding: '2px 4px' }}>{o.rank}</td>
              <td style={{ padding: '2px 4px' }}>{o.combined_score.toFixed(3)}</td>
              <td style={{ padding: '2px 4px' }}>{o.unblocked_view_score.toFixed(2)}</td>
              <td style={{ padding: '2px 4px' }}>{o.rotation_degrees}°</td>
              <td style={{ padding: '2px 4px' }}>{o.fits_within_site ? '✓' : '✗'}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function BuildingItem({
  building,
  focused,
  selectedOptionId,
  onFocusBuilding,
  onSelectOption,
}: {
  building: BuildingInfo;
  focused: boolean;
  selectedOptionId?: string;
  onFocusBuilding?: (buildingId: string) => void;
  onSelectOption?: (buildingId: string, option: PlacementOption) => void;
}): JSX.Element {
  return (
    <details open style={{ marginBottom: 6, border: `1px solid ${focused ? '#f39c12' : '#e2e6ea'}`, borderRadius: 6 }}>
      <summary
        onClick={(e) => {
          // Let the disclosure toggle, but also focus the building.
          onFocusBuilding?.(building.building_id);
          e.stopPropagation();
        }}
        style={{
          listStyle: 'none',
          cursor: 'pointer',
          padding: '5px 8px',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          background: focused ? '#fef9e7' : '#fbfcfd',
          borderRadius: 6,
        }}
      >
        <span style={{ width: 10, height: 10, borderRadius: 2, background: buildingColor(building.building_type) }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: '#1b2631' }}>{building.label}</span>
        <span style={{ fontSize: 10, color: '#7f8c8d' }}>{building.building_type ?? 'auto'}</span>
      </summary>
      <div style={{ padding: '6px 10px' }}>
        <Row label="footprint" value={`${building.area_sqm.toFixed(0)} m²`} />
        {building.height_m != null && <Row label="height" value={`${building.height_m} m`} />}
        {building.view_score != null && <Row label="view score" value={building.view_score.toFixed(3)} />}
        {building.wings.length > 0 && (
          <Row label="wings" value={building.wings.map((w) => w.role).join(', ')} />
        )}
        {building.placement_options.length > 0 && (
          <>
            <div style={{ fontSize: 10, color: '#7f8c8d', marginTop: 6 }}>
              Pareto placements (view analysis):
            </div>
            <OptionsTable building={building} selectedOptionId={selectedOptionId} onSelectOption={onSelectOption} />
          </>
        )}
      </div>
    </details>
  );
}

export function ExplorerPanel({
  tree,
  focusedBuildingId,
  selectedOptionId,
  onFocusBuilding,
  onSelectOption,
}: ExplorerPanelProps): JSX.Element {
  if (!tree) {
    return <div style={{ fontSize: 12, color: '#95a5a6', padding: 8 }}>No session loaded.</div>;
  }
  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', fontSize: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: '#34495e', marginBottom: 6 }}>
        EXPLORER
      </div>

      {/* Site */}
      <div style={{ border: '1px solid #e2e6ea', borderRadius: 6, padding: '6px 10px', marginBottom: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#1b2631', marginBottom: 2 }}>Site</div>
        {tree.site ? (
          <>
            <Row label="area" value={`${tree.site.area_sqm.toFixed(0)} m²`} />
            {tree.site.buildable_area_sqm != null && (
              <Row label="buildable" value={`${tree.site.buildable_area_sqm.toFixed(0)} m²`} />
            )}
            <Row label="edges" value={tree.site.edge_count} />
          </>
        ) : (
          <div style={{ color: '#95a5a6' }}>No site read yet.</div>
        )}
      </div>

      {/* Buildings */}
      <div style={{ fontSize: 11, color: '#7f8c8d', marginBottom: 4 }}>
        Buildings ({tree.buildings.length})
      </div>
      {tree.buildings.length === 0 && <div style={{ color: '#95a5a6' }}>None placed yet.</div>}
      {tree.buildings.map((b) => (
        <BuildingItem
          key={b.building_id}
          building={b}
          focused={b.building_id === focusedBuildingId}
          selectedOptionId={selectedOptionId}
          onFocusBuilding={onFocusBuilding}
          onSelectOption={onSelectOption}
        />
      ))}
    </div>
  );
}

export default ExplorerPanel;
