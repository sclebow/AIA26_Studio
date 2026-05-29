import React, { useState } from 'react';
import { useTheme } from '../common/ThemeToggle';

export interface ToolCallCardProps {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  args?: unknown;
  result?: unknown;
}

const ToolCallCard: React.FC<ToolCallCardProps> = ({ name, status, args, result }) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const [expanded, setExpanded] = useState(false);

  const statusColors: Record<string, string> = {
    pending: colors.muted,
    running: colors.warning,
    completed: colors.success,
    error: colors.error,
  };

  const dotColor = statusColors[status] ?? colors.muted;

  const cardStyle: React.CSSProperties = {
    background: colors.accentDim,
    border: `1px solid ${colors.border}`,
    borderRadius: '8px',
    padding: '8px 10px',
    marginTop: '6px',
    cursor: 'pointer',
    transition: 'background 0.15s',
    fontFamily: colors.font,
  };

  const nameStyle: React.CSSProperties = {
    color: colors.accent,
    fontSize: '12px',
    fontWeight: 500,
    letterSpacing: '0.02em',
    flex: 1,
    fontFamily: '"SF Mono", "Fira Code", monospace',
  };

  const codeStyle: React.CSSProperties = {
    marginTop: '10px',
    background: isDark ? 'rgba(0, 0, 0, 0.3)' : 'rgba(0, 0, 0, 0.05)',
    borderRadius: '6px',
    padding: '8px',
    fontSize: '11px',
    color: isDark ? '#b0bec5' : '#4a5a6a',
    fontFamily: '"SF Mono", "Fira Code", monospace',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all',
    overflowX: 'auto',
    maxHeight: '200px',
    overflowY: 'auto',
  };

  return (
    <>
      <style>{`
        @keyframes toolcardPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
      <div
        style={cardStyle}
        onClick={() => setExpanded(v => !v)}
        onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = isDark ? 'rgba(139, 92, 246, 0.08)' : 'rgba(0, 144, 176, 0.1)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = ''; }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{
            display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
            backgroundColor: dotColor, boxShadow: status === 'running' ? `0 0 6px ${dotColor}` : 'none',
            animation: status === 'running' ? 'toolcardPulse 1.2s ease-in-out infinite' : 'none',
          }} />
          <span style={nameStyle}>{name}</span>
          <span style={{ color: dotColor, fontSize: '11px', textTransform: 'capitalize' }}>{status}</span>
          <span style={{ color: colors.muted, fontSize: 10, transition: 'transform 0.2s', transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', display: 'inline-block' }}>&#9660;</span>
        </div>

        {expanded && (
          <div>
            {args !== undefined && (
              <>
                <div style={{ color: colors.muted, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 8, marginBottom: 4 }}>Arguments</div>
                <div style={codeStyle}>{JSON.stringify(args, null, 2)}</div>
              </>
            )}
            {result !== undefined && (
              <>
                <div style={{ color: colors.muted, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 8, marginBottom: 4 }}>Result</div>
                <div style={codeStyle}>{typeof result === 'string' ? result : JSON.stringify(result, null, 2)}</div>
              </>
            )}
            {args === undefined && result === undefined && (
              <div style={{ ...codeStyle, color: colors.muted, fontStyle: 'italic' }}>No data available</div>
            )}
          </div>
        )}
      </div>
    </>
  );
};

export default React.memo(ToolCallCard);
