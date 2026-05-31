import React, { useRef, useEffect } from 'react';
import { useTheme } from '../common/ThemeToggle';

export interface LogEntry {
  id: string;
  timestamp: number;
  type: 'node_start' | 'node_complete' | 'node_error' | 'info' | 'tool_call' | 'reasoning';
  node?: string;
  message: string;
  data?: unknown;
}

export interface ReasoningLogProps {
  entries: LogEntry[];
  visible: boolean;
  onToggle: () => void;
  isRunning?: boolean;
}

const NODE_LABELS: Record<string, string> = {
  profile_agent: 'Profile Agent',
  space_type_agent: 'Space Type Agent',
  reason: 'Reasoning',
  add_objects: 'Place Objects',
  collision: 'Collision Analysis',
  visibility: 'Visibility Analysis',
  orientation: 'Orientation Check',
  path_analysis: 'Path Analysis',
  reachability: 'Reachability Check',
  scoring: 'Scoring',
  checkpoint: 'Checkpoint',
  explain: 'Explain',
};

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

const ReasoningLog: React.FC<ReasoningLogProps> = ({ entries, visible, onToggle, isRunning = false }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries.length]);

  const colors = {
    node_start: '#8B5CF6',
    node_complete: '#34D399',
    node_error: '#F87171',
    info: '#6b7b8d',
    tool_call: '#FBBF24',
    reasoning: '#7C6FAA',
  };

  const bg = isDark ? 'rgba(6, 9, 15, 0.95)' : 'rgba(240, 244, 248, 0.95)';
  const text = isDark ? '#b0c0d0' : '#2a3a4a';
  const muted = isDark ? '#3a4a5e' : '#8a9aaa';
  const border = isDark ? 'rgba(139, 92, 246, 0.10)' : 'rgba(0, 140, 180, 0.12)';
  const headerBg = isDark ? 'rgba(139, 92, 246, 0.03)' : 'rgba(0, 140, 180, 0.04)';

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: bg,
      borderLeft: `1px solid ${border}`,
      overflow: 'hidden',
      transition: 'background 0.3s ease',
    }}>
      {/* Progress bar when collapsed and running */}
      {!visible && isRunning && (
        <>
          <style>{`
            @keyframes logSlide {
              0% { transform: translateX(-100%); }
              100% { transform: translateX(200%); }
            }
          `}</style>
          <div style={{
            height: 2,
            width: '100%',
            overflow: 'hidden',
            flexShrink: 0,
          }}>
            <div style={{
              height: '100%',
              width: '50%',
              background: `linear-gradient(90deg, transparent, #8B5CF6, transparent)`,
              animation: 'logSlide 1.5s ease-in-out infinite',
            }} />
          </div>
        </>
      )}
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 14px',
        borderBottom: `1px solid ${border}`,
        background: headerBg,
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8B5CF6" strokeWidth="2" strokeLinecap="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          </svg>
          <span style={{
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: isDark ? '#e0e6ed' : '#2a3a4a',
          }}>
            Agent Log
          </span>
          <span style={{
            fontSize: 10,
            color: muted,
            marginLeft: 4,
          }}>
            {entries.length} events
          </span>
        </div>
        <button
          onClick={onToggle}
          style={{
            background: 'none',
            border: `1px solid ${border}`,
            borderRadius: 6,
            color: isDark ? '#6b7b8d' : '#6a7a8a',
            cursor: 'pointer',
            padding: '3px 8px',
            fontSize: 10,
            fontFamily: '"SF Mono", "Fira Code", monospace',
            transition: 'color 0.2s',
          }}
          title={visible ? 'Collapse log' : 'Expand log'}
        >
          {visible ? 'HIDE' : 'SHOW'}
        </button>
      </div>

      {/* Log entries */}
      {visible && (
        <div
          ref={scrollRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '8px 0',
            fontFamily: '"SF Mono", "Fira Code", "Cascadia Code", monospace',
            fontSize: 11,
            lineHeight: 1.6,
          }}
        >
          {entries.length === 0 && (
            <div style={{ padding: '20px 14px', color: muted, textAlign: 'center', fontSize: 11 }}>
              Waiting for agent activity...
            </div>
          )}
          {entries.map(entry => (
            <div
              key={entry.id}
              style={{
                display: 'flex',
                gap: 8,
                padding: '3px 14px',
                alignItems: 'flex-start',
                borderLeft: `2px solid ${colors[entry.type] || muted}`,
                marginLeft: 8,
                transition: 'background 0.15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = isDark ? 'rgba(139,92,246,0.03)' : 'rgba(0,140,180,0.04)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <span style={{ color: muted, flexShrink: 0, minWidth: 60 }}>
                {formatTime(entry.timestamp)}
              </span>
              <span style={{ color: colors[entry.type] || muted, flexShrink: 0, minWidth: 12 }}>
                {entry.type === 'node_start' && '\u25B6'}
                {entry.type === 'node_complete' && '\u2713'}
                {entry.type === 'node_error' && '\u2717'}
                {entry.type === 'tool_call' && '\u2192'}
                {entry.type === 'reasoning' && '\u2022'}
                {entry.type === 'info' && '\u2014'}
              </span>
              <span style={{ color: text, wordBreak: 'break-word' }}>
                {entry.node && (
                  <span style={{ color: colors[entry.type], fontWeight: 500 }}>
                    [{NODE_LABELS[entry.node] || entry.node}]
                  </span>
                )}{' '}
                {entry.message}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default React.memo(ReasoningLog);
