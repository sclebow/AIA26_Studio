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

export interface OverlayToggles {
  collision: boolean;
  visibility: boolean;
  path: boolean;
}

export type ToolLoadState = 'idle' | 'loading' | 'active' | 'error';
export interface ToolStatus { state: ToolLoadState; message?: string }
export type OverlayLoadStatus = Record<keyof OverlayToggles, ToolStatus>;

// Inject the pulse keyframe once into the document head.
if (typeof document !== 'undefined' && !document.getElementById('overlay-pulse-kf')) {
  const s = document.createElement('style');
  s.id = 'overlay-pulse-kf';
  s.textContent = `
    @keyframes overlay-pulse {
      0%,100% { opacity: 1; }
      50%      { opacity: 0.4; }
    }
  `;
  document.head.appendChild(s);
}

export interface DashboardProps {
  scores: ScoreData | null;
  /** Tool gauge to highlight. */
  focusMetric?: string | null;
  /** Current on/off state of each viewport overlay. */
  overlayToggles?: OverlayToggles;
  /** Per-tool load / error state for visual feedback. */
  overlayLoadStatus?: OverlayLoadStatus;
  /** Toggle a specific overlay on or off. */
  onToggleOverlay?: (key: keyof OverlayToggles) => void;
  /** True when a person/path observer is placed and ready to run. */
  observerReady?: boolean;
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
        width: '100%',
      }}>
        {TOOL_SCORES.map(tool => (
          <div key={tool.key} style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            minWidth: 0,
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
              fontSize: 9,
              fontWeight: 600,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              color: colors.muted,
              opacity: 0.5,
              maxWidth: '100%',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
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
          <div style={{ fontSize: 12, opacity: 0.6, letterSpacing: '0.04em' }}>
            Run the agent to generate
          </div>
          <div style={{ fontSize: 12, opacity: 0.6, letterSpacing: '0.04em' }}>
            layout analysis scores
          </div>
        </div>
      </div>
    </div>
  );
};

const OVERLAY_TOOLS: Array<{ key: keyof OverlayToggles; label: string; title: string }> = [
  { key: 'visibility', label: 'Visibility', title: 'Toggle visibility / isovist overlay in viewport' },
  { key: 'path',       label: 'Paths',      title: 'Toggle path analysis overlay in viewport' },
  { key: 'collision',  label: 'Collision',  title: 'Toggle collision heatmap overlay in viewport' },
];

const Dashboard: React.FC<DashboardProps> = ({ scores, focusMetric, overlayToggles, overlayLoadStatus, onToggleOverlay, observerReady }) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';

  const panelStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflowY: 'auto',
    overflowX: 'hidden',
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
          fontSize: 12,
          fontWeight: 600,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          fontFamily: colors.fontHeading,
        }}>Analysis</span>
      </div>

      {/* Viewport overlay toggles — always visible, independent of scores */}
      {onToggleOverlay && (
        <div style={{
          display: 'flex', gap: 5, marginBottom: 10, flexShrink: 0,
        }}>
          {OVERLAY_TOOLS.map(t => {
            const active   = overlayToggles?.[t.key] ?? false;
            const status   = overlayLoadStatus?.[t.key] ?? { state: 'idle' as ToolLoadState };
            const loading  = status.state === 'loading';
            const hasError = status.state === 'error';
            const ready    = t.key === 'visibility' && observerReady && !active && !loading && !hasError;

            // Border / background / text color
            const borderColor = hasError ? colors.error + '99'
              : active        ? colors.accent + '88'
              : ready         ? colors.success + '66'
              : loading       ? colors.accent + '55'
              : colors.border;

            const bgColor = hasError ? colors.error + '14'
              : active    ? colors.accent + '1f'
              : ready     ? colors.success + '12'
              : loading   ? colors.accent + '0d'
              : isDark    ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)';

            const textColor = hasError ? colors.error
              : active    ? colors.accent
              : ready     ? colors.success
              : loading   ? colors.accent
              : colors.muted;

            const dotColor = hasError ? colors.error
              : active    ? colors.accent
              : ready     ? colors.success
              : loading   ? colors.accent
              : colors.muted;

            const tooltipTitle = hasError && status.message
              ? `Error: ${status.message}`
              : ready
              ? 'Observer placed — click to run visibility analysis'
              : loading
              ? 'Running…'
              : t.title;

            return (
              <button
                key={t.key}
                onClick={() => onToggleOverlay(t.key)}
                title={tooltipTitle}
                style={{
                  flex: 1, position: 'relative',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                  padding: '5px 4px',
                  borderRadius: 7,
                  border: `1px solid ${borderColor}`,
                  background: bgColor,
                  color: textColor,
                  fontSize: 9.5, fontWeight: 700, letterSpacing: '0.05em',
                  textTransform: 'uppercase', fontFamily: colors.font,
                  cursor: loading ? 'default' : 'pointer',
                  transition: 'background 0.15s, border-color 0.15s, color 0.15s',
                  animation: loading ? 'overlay-pulse 1s ease-in-out infinite' : 'none',
                }}
              >
                {/* Status dot */}
                <span style={{
                  width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
                  background: dotColor,
                  opacity: active || ready || loading || hasError ? 1 : 0.35,
                  transition: 'background 0.15s',
                }} />

                {t.label}

                {/* Error badge — small "!" in top-right corner */}
                {hasError && (
                  <span style={{
                    position: 'absolute', top: 2, right: 3,
                    fontSize: 7, fontWeight: 900, color: colors.error,
                    lineHeight: 1, letterSpacing: 0,
                  }}>!</span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {!scores ? (
        <EmptyState />
      ) : (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(5, 1fr)',
            gap: '4px',
            width: '100%',
          }}>
            {TOOL_SCORES.map(tool => (
              <div key={tool.key} style={{
                display: 'flex', justifyContent: 'center', minWidth: 0, borderRadius: 8,
                boxShadow: focusMetric === tool.key ? `0 0 0 2px ${colors.accent}` : 'none',
                transition: 'box-shadow 0.2s',
              }}>
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
