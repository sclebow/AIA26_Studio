import React from 'react';
import { useTheme } from '../common/ThemeToggle';
import { ScoreData } from './Dashboard';

export interface WeightBarProps {
  scores: ScoreData;
}

interface Tool {
  key: keyof Pick<ScoreData, 'collision' | 'visibility' | 'path' | 'reachability' | 'orientation'>;
  label: string;
  weightKey: keyof ScoreData['weights'];
}

const TOOLS: Tool[] = [
  { key: 'collision', label: 'Collision', weightKey: 'collision' },
  { key: 'visibility', label: 'Visibility', weightKey: 'visibility' },
  { key: 'path', label: 'Path', weightKey: 'path' },
  { key: 'reachability', label: 'Reach', weightKey: 'reachability' },
  { key: 'orientation', label: 'Orient', weightKey: 'orientation' },
];

const WeightBar: React.FC<WeightBarProps> = ({ scores }) => {
  const { colors } = useTheme();

  const getScoreColor = (score: number): string => {
    if (score > 75) return colors.accent;
    if (score >= 40) return colors.warning;
    return colors.error;
  };

  const contributions = TOOLS.map(tool => ({
    ...tool,
    score: scores[tool.key] as number,
    weight: scores.weights[tool.weightKey] as number,
    contribution: (scores[tool.key] as number) * (scores.weights[tool.weightKey] as number),
  }));

  const totalContribution = contributions.reduce((sum, t) => sum + t.contribution, 0);

  return (
    <div style={{ fontFamily: colors.font }}>
      <div style={{ color: colors.muted, fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 10 }}>
        Score Contributions
      </div>
      <div style={{ display: 'flex', height: 20, borderRadius: 6, overflow: 'hidden', gap: 1 }}>
        {contributions.map(tool => {
          const pct = totalContribution > 0 ? (tool.contribution / totalContribution) * 100 : 20;
          return (
            <div
              key={tool.key}
              title={`${tool.label}: ${Math.round(tool.contribution)} pts (${Math.round(tool.weight * 100)}% weight)`}
              style={{ width: `${pct}%`, background: getScoreColor(tool.score), opacity: 0.7, transition: 'width 0.5s ease' }}
            />
          );
        })}
      </div>
      <div style={{ display: 'flex', marginTop: 6, gap: 1 }}>
        {contributions.map(tool => {
          const pct = totalContribution > 0 ? (tool.contribution / totalContribution) * 100 : 20;
          return (
            <div key={tool.key} style={{ width: `${pct}%`, overflow: 'hidden' }}>
              <div style={{ color: getScoreColor(tool.score), fontSize: 9, letterSpacing: '0.03em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {tool.label}
              </div>
              <div style={{ color: colors.muted, fontSize: 9 }}>{Math.round(tool.contribution)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default React.memo(WeightBar);
