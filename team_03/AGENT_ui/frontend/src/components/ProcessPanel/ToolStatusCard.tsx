import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useTheme } from '../common/ThemeToggle';

export type NodeStatus = 'pending' | 'running' | 'completed' | 'error';

export interface ToolStatusCardProps {
  name: string;
  status: NodeStatus;
  duration?: number;
}

const formatDuration = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
};

// ── Step icons (14×14, stroke only, 1.5px) ──────────────────────────────────

const ICONS: Record<string, React.FC> = {
  profile_agent: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
    </svg>
  ),
  space_type_agent: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </svg>
  ),
  reason: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="10" r="6" />
      <path d="M9 10a3 3 0 0 1 6 0c0 2-2 3-2 5" />
      <circle cx="12" cy="19" r="0.5" fill="currentColor" />
    </svg>
  ),
  add_objects: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="12" y1="8" x2="12" y2="16" />
      <line x1="8" y1="12" x2="16" y2="12" />
    </svg>
  ),
  collision: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2l9 18H3z" />
      <line x1="12" y1="9" x2="12" y2="14" />
      <circle cx="12" cy="17" r="0.5" fill="currentColor" />
    </svg>
  ),
  visibility: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ),
  orientation: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <polygon points="12,5 14.5,14 12,12.5 9.5,14" fill="currentColor" stroke="none" />
      <polygon points="12,19 9.5,10 12,11.5 14.5,10" />
    </svg>
  ),
  path_analysis: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="5" cy="19" r="2" />
      <circle cx="19" cy="5" r="2" />
      <path d="M7 17c2-2 4-4 6-4s4-2 6-4" />
    </svg>
  ),
  reachability: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="5" cy="12" r="2" />
      <circle cx="19" cy="12" r="2" />
      <circle cx="12" cy="5" r="2" />
      <line x1="7" y1="12" x2="17" y2="12" />
      <line x1="12" y1="7" x2="12" y2="12" />
    </svg>
  ),
  scoring: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="4" y1="20" x2="4" y2="14" />
      <line x1="9" y1="20" x2="9" y2="10" />
      <line x1="14" y1="20" x2="14" y2="16" />
      <line x1="19" y1="20" x2="19" y2="7" />
    </svg>
  ),
  checkpoint: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 4h12v10l-6 4-6-4z" />
      <line x1="12" y1="18" x2="12" y2="22" />
    </svg>
  ),
  explain: () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
};

const DESCRIPTIONS: Record<string, string> = {
  profile_agent:     'Analyzes user requirements and space profile',
  space_type_agent:  'Classifies zone types and spatial categories',
  reason:            'Strategic reasoning about layout approach',
  add_objects:       'Places furniture and equipment in the space',
  collision:         'Checks clearance between objects',
  visibility:        'Analyzes sightlines between elements',
  orientation:       'Verifies object facing directions',
  path_analysis:     'Calculates navigation paths and distances',
  reachability:      'Ensures all areas are accessible',
  scoring:           'Computes overall layout quality score',
  checkpoint:        'Saves progress and validates state',
  explain:           'Generates summary explanation',
};

// ── Tiny status dot ──────────────────────────────────────────────────────────

const StatusDot: React.FC<{ status: NodeStatus; accent: string; success: string; error: string; muted: string }> = ({
  status, accent, success, error, muted,
}) => {
  const color =
    status === 'running'   ? accent  :
    status === 'completed' ? success :
    status === 'error'     ? error   : muted;

  return (
    <>
      {status === 'running' && (
        <style>{`
          @keyframes _sdPulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(.75)} }
        `}</style>
      )}
      <span style={{
        display: 'inline-block',
        width: '5px',
        height: '5px',
        borderRadius: '50%',
        background: color,
        flexShrink: 0,
        animation: status === 'running' ? '_sdPulse 1.1s ease-in-out infinite' : undefined,
      }} />
    </>
  );
};

// ── Popover description ──────────────────────────────────────────────────────

const Popover: React.FC<{ text: string; onClose: () => void; colors: ReturnType<typeof useTheme>['colors'] }> = ({
  text, onClose, colors,
}) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);

  return (
    <div
      ref={ref}
      style={{
        position: 'absolute',
        bottom: 'calc(100% + 6px)',
        left: 0,
        zIndex: 999,
        background: colors.cardBg,
        border: `1px solid ${colors.border}`,
        borderRadius: '6px',
        padding: '7px 10px',
        fontSize: '10px',
        color: colors.muted,
        lineHeight: 1.5,
        maxWidth: '200px',
        whiteSpace: 'normal',
        pointerEvents: 'auto',
        fontFamily: colors.font,
        boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
      }}
    >
      {text}
    </div>
  );
};

// ── Main card ────────────────────────────────────────────────────────────────

const ToolStatusCard: React.FC<ToolStatusCardProps> = ({ name, status, duration }) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const [hovered, setHovered] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);

  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setPopoverOpen(v => !v);
  }, []);

  const accentLine =
    status === 'running'   ? colors.accent  :
    status === 'completed' ? colors.success :
    status === 'error'     ? colors.error   : 'transparent';

  const IconComp = ICONS[name];
  const description = DESCRIPTIONS[name];

  const iconColor =
    status === 'running'   ? colors.accent  :
    status === 'completed' ? colors.success :
    status === 'error'     ? colors.error   : colors.muted;

  return (
    <div
      style={{ position: 'relative' }}
      onClick={handleClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <style>{`
        @keyframes _cardPulse {
          0%,100%{opacity:1} 50%{opacity:.6}
        }
      `}</style>

      {/* Left accent bar */}
      <div style={{
        position: 'absolute',
        left: 0,
        top: '4px',
        bottom: '4px',
        width: '2px',
        borderRadius: '1px',
        background: accentLine,
        boxShadow: status === 'running' ? `0 0 6px ${colors.accent}` : undefined,
        transition: 'background 0.3s',
        animation: status === 'running' ? '_cardPulse 1.2s ease-in-out infinite' : undefined,
      }} />

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '7px',
        padding: '5px 8px 5px 10px',
        borderRadius: '5px',
        background: hovered
          ? (isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)')
          : 'transparent',
        transition: 'background 0.15s',
        cursor: 'pointer',
        userSelect: 'none',
      }}>
        {/* Step icon */}
        <span style={{ color: iconColor, display: 'flex', alignItems: 'center', flexShrink: 0, transition: 'color 0.3s' }}>
          {IconComp ? <IconComp /> : null}
        </span>

        {/* Name */}
        <span style={{
          flex: 1,
          color: status === 'pending' ? colors.muted : colors.text,
          fontSize: '10px',
          fontWeight: 500,
          letterSpacing: '0.02em',
          fontFamily: '"SF Mono", "Fira Code", monospace',
          transition: 'color 0.3s',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {name}
        </span>

        {/* Duration */}
        {duration !== undefined && status === 'completed' && (
          <span style={{
            color: colors.muted,
            fontSize: '9px',
            letterSpacing: '0.02em',
            flexShrink: 0,
          }}>
            {formatDuration(duration)}
          </span>
        )}

        {/* Status dot */}
        <StatusDot
          status={status}
          accent={colors.accent}
          success={colors.success}
          error={colors.error}
          muted={isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.15)'}
        />
      </div>

      {/* Popover */}
      {popoverOpen && description && (
        <Popover text={description} onClose={() => setPopoverOpen(false)} colors={colors} />
      )}
    </div>
  );
};

export default React.memo(ToolStatusCard);
