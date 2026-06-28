/**
 * BriefNode — the Phase 0 "comprehension" node in the decision graph.
 *
 * Renders the typed DesignBrief the agent extracted from the user's prompt
 * (`payload.design_brief`), so the UI shows *what the agent understood* between
 * the user `intent` and the first tool `action`.
 *
 * Drop-in React Flow custom node. Register it in nodeTypes.ts under the key
 * `brief`. Dependency: `reactflow` (v11) — for `@xyflow/react` (v12) change the
 * import below to `@xyflow/react`; the API used here (Handle, Position,
 * NodeProps) is identical across both.
 *
 * Self-contained: inline styles only, no CSS import required. Tolerant of a
 * missing/partial payload (the compact SSE node has no payload until the full
 * graph is fetched) — it renders a minimal header in that case.
 */
import React from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

import { isBriefPayload, type DesignBrief, type RFNodeData } from './types';

const INDIGO = '#5b4b9e';
const INDIGO_SOFT = '#ece9f6';
const HEAD_RING = '#f39c12';

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

/** A 0..1 objective weight as a labelled mini-bar. */
function WeightBar({ label, value }: { label: string; value: number }): JSX.Element {
  const pct = Math.round(clamp01(value) * 100);
  const emphasised = value >= 0.65; // brief raises a weight above 0.5 on emphasis
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10 }}>
      <span style={{ width: 34, color: '#555' }}>{label}</span>
      <div style={{ flex: 1, height: 6, background: '#e6e6e6', borderRadius: 3 }}>
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            borderRadius: 3,
            background: emphasised ? INDIGO : '#9b8fc4',
          }}
        />
      </div>
      <span style={{ width: 26, textAlign: 'right', color: emphasised ? INDIGO : '#777' }}>
        {value.toFixed(2)}
      </span>
    </div>
  );
}

function Chip({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'accent' | 'warn' }): JSX.Element {
  const palette = {
    neutral: { bg: '#eef0f3', fg: '#3a3f47' },
    accent: { bg: INDIGO_SOFT, fg: INDIGO },
    warn: { bg: '#fdecea', fg: '#c0392b' },
  }[tone];
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '1px 7px',
        borderRadius: 10,
        fontSize: 10,
        fontWeight: 600,
        background: palette.bg,
        color: palette.fg,
      }}
    >
      {children}
    </span>
  );
}

function BriefBody({ brief }: { brief: DesignBrief }): JSX.Element {
  const shapes = brief.buildings.map((b) => b.shape_preference);
  const shapeLabel = shapes.length ? shapes.join(' + ') : 'auto';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      {/* count + shapes */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <Chip tone="accent">
          {brief.building_count} building{brief.building_count === 1 ? '' : 's'}
        </Chip>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#2c3e50', letterSpacing: 0.5 }}>
          {shapeLabel}
        </span>
      </div>

      {/* per-building use / area / storeys, only when known */}
      {brief.buildings.some((b) => b.use || b.footprint_area_sqm || b.storeys) && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {brief.buildings.map((b, i) => (
            <Chip key={i}>
              {[
                b.use,
                b.footprint_area_sqm ? `${Math.round(b.footprint_area_sqm)} m²` : null,
                b.storeys ? `${b.storeys}f` : null,
              ]
                .filter(Boolean)
                .join(' · ') || 'auto'}
            </Chip>
          ))}
        </div>
      )}

      {/* feature flags */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {brief.courtyard_requested && (
          <Chip tone="accent">
            courtyard{brief.courtyard_qualities.length ? `: ${brief.courtyard_qualities.join(', ')}` : ''}
          </Chip>
        )}
        {brief.parking_requested && <Chip tone="accent">parking</Chip>}
        {brief.requested_rotation_deg != null && (
          <Chip>{brief.requested_rotation_deg}° rotation</Chip>
        )}
      </div>

      {/* objective weights */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <WeightBar label="view" value={brief.view_weight} />
        <WeightBar label="sun" value={brief.sun_weight} />
        <WeightBar label="align" value={brief.alignment_weight} />
      </div>

      {/* ambiguities — soft warning, never an error */}
      {brief.ambiguities.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <Chip tone="warn">{brief.ambiguities.length} ambiguity{brief.ambiguities.length === 1 ? '' : 's'}</Chip>
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 10, color: '#a04030' }}>
            {brief.ambiguities.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function BriefNode({ data, selected }: NodeProps<RFNodeData>): JSX.Element {
  const brief = isBriefPayload(data.payload) ? data.payload.design_brief : null;
  const source = brief?.source ?? 'fallback';

  return (
    <div
      style={{
        minWidth: 220,
        maxWidth: 280,
        borderRadius: 10,
        border: `2px solid ${data.isHead ? HEAD_RING : INDIGO}`,
        boxShadow: selected || data.isSelected ? `0 0 0 3px ${INDIGO_SOFT}` : '0 1px 4px rgba(0,0,0,0.12)',
        background: '#fff',
        opacity: data.isSelected ? 1 : 0.6,
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: INDIGO }} />

      {/* header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 10px',
          background: INDIGO,
          color: '#fff',
          borderTopLeftRadius: 8,
          borderTopRightRadius: 8,
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.6 }}>◆ DESIGN BRIEF</span>
        <span
          title={source === 'llm' ? 'Extracted by the LLM' : 'Deterministic regex fallback (no LLM)'}
          style={{
            fontSize: 9,
            fontWeight: 700,
            padding: '1px 6px',
            borderRadius: 8,
            background: source === 'llm' ? '#27ae60' : '#7f8c8d',
            color: '#fff',
          }}
        >
          {source === 'llm' ? 'LLM' : 'REGEX'}
        </span>
      </div>

      {/* body */}
      <div style={{ padding: '8px 10px' }}>
        {brief ? (
          <BriefBody brief={brief} />
        ) : (
          // Compact SSE node (no payload yet) — show the label until /decisions loads.
          <div style={{ fontSize: 11, color: '#555' }}>{data.label || 'Comprehending prompt…'}</div>
        )}
      </div>

      {data.isHead && (
        <div style={{ textAlign: 'center', fontSize: 9, color: HEAD_RING, fontWeight: 700, paddingBottom: 4 }}>
          ▼ HEAD
        </div>
      )}

      <Handle type="source" position={Position.Bottom} style={{ background: INDIGO }} />
    </div>
  );
}

export default BriefNode;
