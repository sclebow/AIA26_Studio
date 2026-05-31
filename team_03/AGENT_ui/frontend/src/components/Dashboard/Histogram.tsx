import React, { useMemo } from 'react';
import { useTheme } from '../common/ThemeToggle';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

export interface HistogramProps {
  data: number[];
  label: string;
  color?: string;
}

interface BinEntry {
  range: string;
  count: number;
  binStart: number;
}

const autoBin = (data: number[], numBins = 10): BinEntry[] => {
  if (!data || data.length === 0) return [];
  const min = Math.min(...data);
  const max = Math.max(...data);
  if (min === max) {
    return [{ range: String(min.toFixed(2)), count: data.length, binStart: min }];
  }
  const binWidth = (max - min) / numBins;
  const bins: BinEntry[] = Array.from({ length: numBins }, (_, i) => {
    const start = min + i * binWidth;
    const end = start + binWidth;
    return { range: `${start.toFixed(1)}-${end.toFixed(1)}`, count: 0, binStart: start };
  });
  for (const val of data) {
    let idx = Math.floor((val - min) / binWidth);
    if (idx >= numBins) idx = numBins - 1;
    bins[idx].count += 1;
  }
  return bins;
};

const Histogram: React.FC<HistogramProps> = ({ data, label, color }) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const barColor = color ?? colors.accent;
  const bins = useMemo(() => autoBin(data ?? [], 10), [data]);

  const tooltipStyle: React.CSSProperties = {
    background: isDark ? 'rgba(10, 14, 23, 0.95)' : 'rgba(255,255,255,0.95)',
    border: `1px solid ${colors.border}`,
    borderRadius: '6px',
    padding: '6px 10px',
    fontSize: '11px',
    fontFamily: colors.font,
    color: colors.text,
  };

  if (!data || data.length === 0) {
    return (
      <div style={{ fontFamily: colors.font }}>
        <div style={{ color: colors.muted, fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 10 }}>{label}</div>
        <div style={{ color: colors.muted, fontSize: 12, textAlign: 'center', padding: 20 }}>No data available</div>
      </div>
    );
  }

  return (
    <div style={{ fontFamily: colors.font }}>
      <div style={{ color: colors.muted, fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 10 }}>{label}</div>
      <ResponsiveContainer width="100%" height={130}>
        <BarChart data={bins} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="range"
            tick={{ fill: colors.muted, fontSize: 9 }}
            tickLine={false}
            axisLine={{ stroke: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)' }}
            interval="preserveStartEnd"
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: colors.muted, fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            width={30}
          />
          <Tooltip
            content={({ active, payload, label: tlabel }) => {
              if (!active || !payload || payload.length === 0) return null;
              return (
                <div style={tooltipStyle}>
                  <div style={{ color: colors.muted, marginBottom: 2 }}>{tlabel}</div>
                  <div style={{ color: colors.accent, fontWeight: 600 }}>{payload[0].value} entries</div>
                </div>
              );
            }}
            cursor={{ fill: isDark ? 'rgba(139,92,246,0.05)' : 'rgba(0,144,176,0.05)' }}
          />
          <Bar dataKey="count" radius={[3, 3, 0, 0]}>
            {bins.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={barColor}
                fillOpacity={0.6 + (entry.count / Math.max(...bins.map(b => b.count))) * 0.4}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default React.memo(Histogram);
