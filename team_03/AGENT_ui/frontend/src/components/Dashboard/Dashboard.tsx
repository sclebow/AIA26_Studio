import React from 'react';
import GlassPanel from '../common/GlassPanel';
import { useTheme } from '../common/ThemeToggle';
import ScoreCard from './ScoreCard';
import GradeDisplay from './GradeDisplay';
import Histogram from './Histogram';
import WeightBar from './WeightBar';

export interface ScoreData {
  overall: number;
  grade: string;
  collision: number;
  visibility: number;
  path: number;
  reachability: number;
  orientation: number;
  weights: {
    collision: number;
    visibility: number;
    path: number;
    reachability: number;
    orientation: number;
  };
  histogramData?: {
    clearance: number[];
    pathDistances: number[];
  };
}

export interface DashboardProps {
  scores: ScoreData | null;
}

const TOOL_SCORES: Array<{
  key: keyof Pick<ScoreData, 'collision' | 'visibility' | 'path' | 'reachability' | 'orientation'>;
  label: string;
  weightKey: keyof ScoreData['weights'];
  icon: string;
}> = [
  { key: 'collision', label: 'Collision', weightKey: 'collision', icon: 'M12 9v2m0 4h.01M3.464 20.536L12 4l8.536 16.536H3.464z' },
  { key: 'visibility', label: 'Visibility', weightKey: 'visibility', icon: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z' },
  { key: 'path', label: 'Path', weightKey: 'path', icon: 'M13 17l5-5-5-5M6 17l5-5-5-5' },
  { key: 'reachability', label: 'Reach', weightKey: 'reachability', icon: 'M22 11.08V12a10 10 0 1 1-5.93-9.14' },
  { key: 'orientation', label: 'Orient', weightKey: 'orientation', icon: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5' },
];

const EmptyState: React.FC = () => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      padding: '4px 0',
    }}>
      {/* Placeholder KPI row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        gap: '4px',
      }}>
        {TOOL_SCORES.map(tool => (
          <div key={tool.key} style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            padding: '8px 2px',
            borderRadius: '8px',
            background: isDark ? 'rgba(139, 92, 246, 0.02)' : 'rgba(0,0,0,0.02)',
            border: `1px solid ${isDark ? 'rgba(139, 92, 246, 0.05)' : 'rgba(0,0,0,0.04)'}`,
            gap: '6px',
          }}>
            <span style={{
              fontSize: 16,
              fontWeight: 800,
              color: isDark ? 'rgba(139, 92, 246, 0.15)' : 'rgba(0,0,0,0.08)',
              letterSpacing: '-0.03em',
            }}>--</span>
            <span style={{
              fontSize: 8,
              fontWeight: 600,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: colors.muted,
              opacity: 0.5,
            }}>{tool.label}</span>
          </div>
        ))}
      </div>

      {/* Placeholder overall */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '16px',
        flex: 1,
        color: colors.muted,
        fontFamily: colors.font,
      }}>
        <div style={{
          width: 56,
          height: 56,
          borderRadius: '50%',
          border: `2px solid ${isDark ? 'rgba(139, 92, 246, 0.08)' : 'rgba(0,0,0,0.06)'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <span style={{ fontSize: 28, fontWeight: 800, opacity: 0.12 }}>?</span>
        </div>
        <div>
          <div style={{ fontSize: 11, opacity: 0.6, letterSpacing: '0.04em' }}>
            Run the agent to generate
          </div>
          <div style={{ fontSize: 11, opacity: 0.6, letterSpacing: '0.04em' }}>
            layout analysis scores
          </div>
        </div>
      </div>
    </div>
  );
};

const Dashboard: React.FC<DashboardProps> = ({ scores }) => {
  const { colors } = useTheme();

  const panelStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'auto',
  };

  return (
    <div style={{ ...panelStyle, padding: '12px' }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginBottom: '12px',
        flexShrink: 0,
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={colors.accent} strokeWidth="2">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
        </svg>
        <span style={{
          color: colors.text,
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          fontFamily: colors.font,
        }}>Analysis Dashboard</span>
      </div>

      {!scores ? (
        <EmptyState />
      ) : (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(5, 1fr)',
            gap: '4px',
          }}>
            {TOOL_SCORES.map(tool => (
              <div key={tool.key} style={{ display: 'flex', justifyContent: 'center' }}>
                <ScoreCard
                  name={tool.label}
                  score={scores[tool.key] as number}
                  weight={scores.weights[tool.weightKey] as number}
                />
              </div>
            ))}
          </div>

          <div style={{ height: '1px', background: colors.border, margin: '8px 0' }} />

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <GradeDisplay grade={scores.grade} score={scores.overall} />
            <div style={{ flex: 1 }}>
              <WeightBar scores={scores} />
            </div>
          </div>

          {scores.histogramData && (
            <>
              <div style={{ height: '1px', background: colors.border, margin: '12px 0' }} />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <Histogram data={scores.histogramData.clearance} label="Clearance" color={colors.accent} />
                <Histogram data={scores.histogramData.pathDistances} label="Path Dist." color={colors.success} />
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
};

export default React.memo(Dashboard);
