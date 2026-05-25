import React from 'react';
import { useTheme } from '../common/ThemeToggle';

export interface GradeDisplayProps {
  grade: string;
  score: number;
}

const GradeDisplay: React.FC<GradeDisplayProps> = ({ grade, score }) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';

  const gradeColors: Record<string, string> = {
    A: '#6B7B9E',
    B: '#7EA68B',
    C: '#C4896E',
    D: '#B8986A',
    F: '#C06060',
  };

  const normalizedGrade = grade?.toUpperCase() ?? 'F';
  const color = gradeColors[normalizedGrade] ?? colors.muted;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '4px',
      fontFamily: colors.font,
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '52px',
        height: '52px',
        borderRadius: '50%',
        background: isDark
          ? `radial-gradient(circle at 35% 35%, ${color}18, ${color}05)`
          : `radial-gradient(circle at 35% 35%, ${color}15, ${color}05)`,
        border: `2px solid ${color}`,
        boxShadow: isDark
          ? `0 0 20px ${color}25, 0 0 40px ${color}10, inset 0 0 12px ${color}08`
          : `0 0 12px ${color}15`,
        transition: 'all 0.4s ease',
      }}>
        <span style={{
          fontSize: 28,
          fontWeight: 800,
          color,
          lineHeight: 1,
          letterSpacing: '-0.03em',
          textShadow: isDark ? `0 0 24px ${color}50` : 'none',
        }}>
          {normalizedGrade}
        </span>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          color: colors.text,
          fontSize: 20,
          fontWeight: 800,
          letterSpacing: '-0.03em',
          lineHeight: 1,
        }}>
          {Math.round(score)}
        </div>
        <div style={{
          color: colors.muted,
          fontSize: 9,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          marginTop: 2,
          fontWeight: 500,
        }}>
          Overall Score
        </div>
      </div>
    </div>
  );
};

export default React.memo(GradeDisplay);
