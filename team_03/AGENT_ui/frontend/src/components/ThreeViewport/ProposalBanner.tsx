import React from 'react';
import { useTheme } from '../common/ThemeToggle';

interface ProposalBannerProps {
  onAccept: () => void;
  onReject: () => void;
}

const btnBase: React.CSSProperties = {
  padding: '5px 14px',
  borderRadius: 6,
  border: 'none',
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: '0.03em',
  textTransform: 'uppercase',
  cursor: 'pointer',
  transition: 'opacity 0.2s',
};

export default function ProposalBanner({ onAccept, onReject }: ProposalBannerProps) {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <div style={{
      position: 'absolute',
      top: 16,
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: 30,
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      padding: '10px 20px',
      borderRadius: 12,
      background: isDark ? 'rgba(18, 19, 26, 0.94)' : 'rgba(255, 255, 255, 0.96)',
      border: `1px solid ${colors.accent}44`,
      boxShadow: isDark
        ? `0 4px 24px rgba(0,0,0,0.4), 0 0 16px ${colors.accent}10`
        : `0 4px 16px rgba(0,0,0,0.08)`,
      fontFamily: colors.font,
    }}>
      <span style={{
        fontSize: 12,
        fontWeight: 600,
        color: colors.accent,
        letterSpacing: '0.02em',
        whiteSpace: 'nowrap',
      }}>
        Temporary layout — pending acceptance
      </span>

      <button
        onClick={onAccept}
        style={{
          ...btnBase,
          background: colors.success,
          color: '#fff',
          fontFamily: colors.font,
        }}
      >
        Accept
      </button>

      <button
        onClick={onReject}
        style={{
          ...btnBase,
          background: colors.error,
          color: '#fff',
          fontFamily: colors.font,
        }}
      >
        Reject
      </button>
    </div>
  );
}
