import React from 'react';
import { useTheme } from '../common/ThemeToggle';
import ToolStatusCard, { NodeStatus } from './ToolStatusCard';

export interface ProcessPanelProps {
  nodeStatuses: Record<string, NodeStatus>;
}

type PipelineEntry =
  | { type: 'single'; name: string }
  | { type: 'parallel'; names: string[] };

const PIPELINE: PipelineEntry[] = [
  { type: 'single',   name: 'profile_agent' },
  { type: 'single',   name: 'space_type_agent' },
  { type: 'single',   name: 'reason' },
  { type: 'single',   name: 'add_objects' },
  { type: 'parallel', names: ['collision', 'visibility', 'orientation'] },
  { type: 'parallel', names: ['path_analysis', 'reachability'] },
  { type: 'single',   name: 'scoring' },
  { type: 'single',   name: 'checkpoint' },
  { type: 'single',   name: 'explain' },
];

// ── Connector line between sequential steps ──────────────────────────────────

const ConnectorLine: React.FC<{ color: string }> = ({ color }) => (
  <div style={{
    width: '0.5px',
    height: '12px',
    background: color,
    margin: '0 auto',
    flexShrink: 0,
  }} />
);

// ── Fan-out SVG (single node → parallel group) ───────────────────────────────

const FanConnector: React.FC<{ count: number; color: string }> = ({ count, color }) => {
  if (count <= 1) return <ConnectorLine color={color} />;
  return (
    <div style={{ position: 'relative', height: '14px', width: '100%' }}>
      <svg width="100%" height="14" preserveAspectRatio="none" style={{ display: 'block' }}>
        {Array.from({ length: count }, (_, i) => {
          const pct = ((i + 0.5) / count) * 100;
          return (
            <line
              key={i}
              x1="50%" y1="0"
              x2={`${pct}%`} y2="14"
              stroke={color}
              strokeWidth="0.5"
            />
          );
        })}
      </svg>
    </div>
  );
};

// ── Fan-in SVG (parallel group → single node) ────────────────────────────────

const FanInConnector: React.FC<{ count: number; color: string }> = ({ count, color }) => {
  if (count <= 1) return <ConnectorLine color={color} />;
  return (
    <div style={{ position: 'relative', height: '14px', width: '100%' }}>
      <svg width="100%" height="14" preserveAspectRatio="none" style={{ display: 'block' }}>
        {Array.from({ length: count }, (_, i) => {
          const pct = ((i + 0.5) / count) * 100;
          return (
            <line
              key={i}
              x1={`${pct}%`} y1="0"
              x2="50%" y2="14"
              stroke={color}
              strokeWidth="0.5"
            />
          );
        })}
      </svg>
    </div>
  );
};

// ── Main component ───────────────────────────────────────────────────────────

const ProcessPanel: React.FC<ProcessPanelProps> = ({ nodeStatuses }) => {
  const { colors } = useTheme();

  const getStatus = (name: string): NodeStatus =>
    nodeStatuses[name] ?? 'pending';

  const lineColor = colors.border ?? 'rgba(128,128,128,0.25)';
  const muteColor = colors.muted;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflowY: 'auto',
      overflowX: 'hidden',
      scrollbarWidth: 'thin',
      scrollbarColor: `${lineColor} transparent`,
      padding: '12px 8px',
      boxSizing: 'border-box',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        marginBottom: '12px',
        flexShrink: 0,
      }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={colors.accent} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" />
        </svg>
        <span style={{
          color: colors.text,
          fontSize: '11px',
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          fontFamily: colors.font,
        }}>
          Pipeline
        </span>
      </div>

      {/* Steps */}
      <div style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
        {PIPELINE.map((entry, idx) => {
          const isLast = idx === PIPELINE.length - 1;
          const nextEntry = PIPELINE[idx + 1];

          if (entry.type === 'single') {
            return (
              <React.Fragment key={entry.name}>
                <ToolStatusCard name={entry.name} status={getStatus(entry.name)} />
                {!isLast && (
                  nextEntry?.type === 'parallel'
                    ? <FanConnector count={nextEntry.names.length} color={lineColor} />
                    : <ConnectorLine color={lineColor} />
                )}
              </React.Fragment>
            );
          } else {
            // parallel group
            return (
              <React.Fragment key={entry.names.join('|')}>
                {/* "parallel" micro-label */}
                <div style={{
                  color: muteColor,
                  fontSize: '8px',
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  textAlign: 'center',
                  marginBottom: '2px',
                  opacity: 0.6,
                  fontFamily: colors.font,
                }}>
                  parallel
                </div>

                {/* Cards stacked vertically for compact fit */}
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0px',
                  paddingLeft: '6px',
                  borderLeft: `0.5px solid ${lineColor}`,
                  marginLeft: '6px',
                }}>
                  {entry.names.map((name, ni) => (
                    <React.Fragment key={name}>
                      <ToolStatusCard name={name} status={getStatus(name)} />
                      {ni < entry.names.length - 1 && (
                        <div style={{
                          height: '0.5px',
                          background: lineColor,
                          margin: '0 8px',
                          opacity: 0.5,
                        }} />
                      )}
                    </React.Fragment>
                  ))}
                </div>

                {!isLast && <FanInConnector count={1} color={lineColor} />}
              </React.Fragment>
            );
          }
        })}
      </div>
    </div>
  );
};

export default React.memo(ProcessPanel);
