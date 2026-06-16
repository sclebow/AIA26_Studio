/**
 * Compact React Flow nodes for the non-brief decision-graph types:
 * intent · action · branch · select · state.
 *
 * Each is a small accented card sharing one shell so the whole reasoning DAG
 * reads consistently alongside the richer BriefNode. Payloads are read
 * defensively (the compact SSE node has no payload until /decisions hydrates).
 */
import React from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

import type { RFNodeData } from './types';

interface Accent {
  color: string;
  icon: string;
  title: string;
}

const ACCENTS: Record<string, Accent> = {
  intent: { color: '#2980b9', icon: '👤', title: 'USER INTENT' },
  clarify: { color: '#2980b9', icon: '✋', title: 'CLARIFY' },
  action: { color: '#e67e22', icon: '🔧', title: 'TOOL' },
  branch: { color: '#8e44ad', icon: '⑂', title: 'PARETO FORK' },
  select: { color: '#27ae60', icon: '✓', title: 'SELECTED' },
  state: { color: '#16a085', icon: '▣', title: 'STATE' },
};

function str(payload: Record<string, unknown>, key: string): string | null {
  const v = payload?.[key];
  return v == null ? null : String(v);
}

function NodeShell({
  data,
  selected,
  accent,
  detail,
  hasTarget = true,
  hasSource = true,
}: {
  data: RFNodeData;
  selected: boolean;
  accent: Accent;
  detail?: React.ReactNode;
  hasTarget?: boolean;
  hasSource?: boolean;
}): JSX.Element {
  return (
    <div
      style={{
        minWidth: 150,
        maxWidth: 230,
        borderRadius: 8,
        border: `2px solid ${data.isHead ? '#f39c12' : accent.color}`,
        background: '#fff',
        boxShadow: selected || data.isSelected ? `0 0 0 3px ${accent.color}22` : '0 1px 3px rgba(0,0,0,0.12)',
        opacity: data.isSelected ? 1 : 0.55,
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      {hasTarget && <Handle type="target" position={Position.Top} style={{ background: accent.color }} />}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 8px',
          background: accent.color,
          color: '#fff',
          borderTopLeftRadius: 6,
          borderTopRightRadius: 6,
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: 0.5,
        }}
      >
        <span>{accent.icon}</span>
        <span>{accent.title}</span>
      </div>
      <div style={{ padding: '6px 8px' }}>
        <div style={{ fontSize: 11, color: '#2c3e50', fontWeight: 600, wordBreak: 'break-word' }}>{data.label}</div>
        {detail != null && <div style={{ marginTop: 4, fontSize: 10, color: '#5d6d7e' }}>{detail}</div>}
      </div>
      {data.isHead && (
        <div style={{ textAlign: 'center', fontSize: 9, color: '#f39c12', fontWeight: 700, paddingBottom: 3 }}>▼ HEAD</div>
      )}
      {hasSource && <Handle type="source" position={Position.Bottom} style={{ background: accent.color }} />}
    </div>
  );
}

export function IntentNode({ data, selected }: NodeProps<RFNodeData>): JSX.Element {
  return <NodeShell data={data} selected={selected} accent={ACCENTS.intent} />;
}

export function ClarifyNode({ data, selected }: NodeProps<RFNodeData>): JSX.Element {
  const req = data.payload?.clarification_request as
    | { summary?: string; fields?: Array<{ key?: string }> }
    | undefined;
  const keys = (req?.fields ?? []).map((f) => f.key).filter(Boolean).join(', ');
  return (
    <NodeShell
      data={data}
      selected={selected}
      accent={ACCENTS.clarify}
      detail={keys ? `asking: ${keys}` : 'awaiting user answer'}
    />
  );
}

export function ActionNode({ data, selected }: NodeProps<RFNodeData>): JSX.Element {
  const tool = str(data.payload, 'tool_name');
  const preview = str(data.payload, 'input_preview');
  return (
    <NodeShell
      data={data}
      selected={selected}
      accent={ACCENTS.action}
      detail={
        tool ? (
          <>
            <code style={{ fontSize: 10 }}>{tool}</code>
            {preview ? <div style={{ marginTop: 2, opacity: 0.75 }}>{preview.slice(0, 80)}</div> : null}
          </>
        ) : undefined
      }
    />
  );
}

export function BranchNode({ data, selected }: NodeProps<RFNodeData>): JSX.Element {
  const count = str(data.payload, 'option_count');
  return (
    <NodeShell
      data={data}
      selected={selected}
      accent={ACCENTS.branch}
      detail={count ? `${count} Pareto options — pick one to continue` : undefined}
    />
  );
}

export function SelectNode({ data, selected }: NodeProps<RFNodeData>): JSX.Element {
  const reason = str(data.payload, 'reason');
  const backtrack = data.payload?.backtrack === true;
  return (
    <NodeShell
      data={data}
      selected={selected}
      accent={ACCENTS.select}
      detail={
        <>
          {backtrack && <span style={{ color: '#c0392b', fontWeight: 700 }}>↩ backtrack · </span>}
          {reason || null}
        </>
      }
    />
  );
}

export function StateNode({ data, selected }: NodeProps<RFNodeData>): JSX.Element {
  const score = str(data.payload, 'combined_score');
  const rotation = str(data.payload, 'rotation_degrees');
  const buildingCount = str(data.payload, 'building_count');
  const detail = buildingCount
    ? `${buildingCount} building(s) placed`
    : [score ? `score ${Number(score).toFixed(3)}` : null, rotation ? `${rotation}°` : null]
        .filter(Boolean)
        .join(' · ') || undefined;
  return <NodeShell data={data} selected={selected} accent={ACCENTS.state} detail={detail} />;
}
