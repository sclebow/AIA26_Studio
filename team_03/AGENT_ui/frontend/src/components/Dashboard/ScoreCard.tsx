import React from 'react';
import { useTheme } from '../common/ThemeToggle';

export interface ScoreCardProps {
  name: string;
  score: number;
  weight: number;
  maxScore?: number;
}

const getScoreColor = (score: number, accent: string, warning: string, error: string): string => {
  if (score > 75) return accent;
  if (score >= 40) return warning;
  return error;
};

const ScoreCard: React.FC<ScoreCardProps> = ({ name, score, weight, maxScore = 100 }) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';

  const size = 56;
  const strokeWidth = 3.5;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clampedScore = Math.max(0, Math.min(maxScore, score));
  const progress = clampedScore / maxScore;
  const dashOffset = circumference * (1 - progress);
  const color = getScoreColor(score, colors.accent, colors.warning, colors.error);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '2px',
      fontFamily: colors.font,
      padding: '4px 2px',
      borderRadius: '8px',
      background: isDark ? 'rgba(139, 92, 246, 0.02)' : 'rgba(0,0,0,0.02)',
      border: `1px solid ${isDark ? 'rgba(139, 92, 246, 0.06)' : 'rgba(0,0,0,0.04)'}`,
      transition: 'background 0.2s, border-color 0.2s',
    }}>
      <div style={{ position: 'relative', width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle
            cx={size / 2} cy={size / 2} r={radius} fill="none"
            stroke={isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.06)'}
            strokeWidth={strokeWidth}
          />
          <circle
            cx={size / 2} cy={size / 2} r={radius} fill="none"
            stroke={color} strokeWidth={strokeWidth} strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={dashOffset}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ transition: 'stroke-dashoffset 0.8s ease, stroke 0.4s ease' }}
            filter={isDark ? `drop-shadow(0 0 6px ${color}50)` : 'none'}
          />
        </svg>
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)', textAlign: 'center', lineHeight: 1,
        }}>
          <span style={{
            fontSize: 16,
            fontWeight: 800,
            color,
            letterSpacing: '-0.03em',
            display: 'block',
            textShadow: isDark ? `0 0 12px ${color}40` : 'none',
          }}>
            {Math.round(score)}
          </span>
        </div>
      </div>
      <div style={{
        color: colors.text,
        fontSize: 9,
        fontWeight: 600,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        textAlign: 'center',
        opacity: 0.9,
      }}>
        {name}
      </div>
      <div style={{
        color: colors.muted,
        fontSize: 8,
        textAlign: 'center',
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
      }}>
        {Math.round(weight * 100)}% weight
      </div>
    </div>
  );
};

export default React.memo(ScoreCard);
