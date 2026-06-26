import React, { useMemo, useRef, useState, useCallback } from 'react';
import { toPng } from 'html-to-image';
import { useTheme } from '../common/ThemeToggle';
import type { BenchRun, BenchmarkData, BenchModelAgg } from '../../utils/wsProtocol';

// Stable colors per model family so the same model keeps its hue across charts.
const MODEL_COLORS: Record<string, string> = {
  'Gemini Flash': '#0ea5e9',
  'Gemini Pro': '#2563eb',
  'Gemini': '#38bdf8',
  'Haiku': '#a78bfa',
  'Sonnet': '#7c3aed',
  'Opus': '#6d28d9',
};
const FALLBACK_COLORS = ['#7c3aed', '#0ea5e9', '#059669', '#d97706', '#dc2626', '#db2777'];

function colorForModel(label: string, idx: number): string {
  return MODEL_COLORS[label] || FALLBACK_COLORS[idx % FALLBACK_COLORS.length];
}

const METRIC_LABELS: Record<string, string> = {
  collision: 'Collision',
  visibility: 'Visibility',
  path: 'Path',
  reachability: 'Reach',
  orientation: 'Orient',
};

// Friendly node names for the Gantt / timeline.
const NODE_LABELS: Record<string, string> = {
  profile_agent: 'Profile Agent',
  space_type_agent: 'Space Type Agent',
  populate_agent: 'Populate Plan',
  populate_check: 'Populate Check',
  memory: 'Memory',
  reason: 'Reason (LLM)',
  tool: 'Tool Call',
  add_objects: 'Place Objects',
  collision: 'Collision',
  visibility: 'Visibility',
  orientation: 'Orientation',
  path: 'Path Analysis',
  path_analysis: 'Path Analysis',
  reachability: 'Reachability',
  enrich_graph: 'Enrich Graph',
  scoring: 'Scoring',
  checkpoint: 'Checkpoint',
  user_checkpoint: 'Checkpoint',
  explain: 'Explain',
  output: 'Save Output',
};
const nodeLabel = (n: string) => NODE_LABELS[n] || n.replace(/_/g, ' ');

const CATEGORY_LABELS: Record<string, string> = {
  profile: 'Profile', space: 'Space', populate: 'Populate', memory: 'Memory',
  reason: 'Reason', tools: 'Tools', analysis: 'Analysis', other: 'Other', setup: 'Setup',
};

type Tab = 'models' | 'workflow';

// Inject spin keyframe once (for the PNG export spinner)
if (typeof document !== 'undefined' && !document.getElementById('bench-spin-kf')) {
  const s = document.createElement('style');
  s.id = 'bench-spin-kf';
  s.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
  document.head.appendChild(s);
}

function timestamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}-${p(d.getMinutes())}`;
}

export interface BenchmarkDashboardProps {
  data: BenchmarkData;
  loading: boolean;
  onRefresh: () => void;
  onClear: () => void;
}

const BenchmarkDashboard: React.FC<BenchmarkDashboardProps> = ({ data, loading, onRefresh, onClear }) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const [tab, setTab] = useState<Tab>('models');
  const [modelFilter, setModelFilter] = useState<string>('all');
  const [confirmClear, setConfirmClear] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportDone, setExportDone] = useState(false);
  const exportTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const handleExportPng = useCallback(async () => {
    if (!contentRef.current || exporting) return;
    setExporting(true);
    try {
      // Temporarily expand the scroll container so the full page is captured
      // (html-to-image can't scroll — it renders what fits in the DOM node bounds).
      const el = contentRef.current;
      const prevOverflow = el.style.overflow;
      const prevHeight = el.style.height;
      el.style.overflow = 'visible';
      el.style.height = 'auto';

      const tabLabel = tab === 'models' ? 'Models_Scores' : 'Workflow';
      const filename = `SpatialFlow_Benchmark_${tabLabel}_${timestamp()}.png`;

      const dataUrl = await toPng(el, {
        pixelRatio: 3,          // 3× → crisp on any screen
        backgroundColor: isDark ? '#0a0612' : '#F5F5F7',
        skipFonts: false,
        style: {
          fontFamily: colors.font,
        },
      });

      // Restore scroll
      el.style.overflow = prevOverflow;
      el.style.height = prevHeight;

      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);

      setExportDone(true);
      if (exportTimerRef.current) clearTimeout(exportTimerRef.current);
      exportTimerRef.current = setTimeout(() => setExportDone(false), 2000);
    } catch (err) {
      console.error('[benchmark] PNG export failed:', err);
      // Restore on error too
      if (contentRef.current) {
        contentRef.current.style.overflow = '';
        contentRef.current.style.height = '';
      }
    } finally {
      setExporting(false);
    }
  }, [exporting, tab, isDark, colors.font]);

  const allRuns = data.runs;
  const modelLabels = useMemo(
    () => Array.from(new Set(allRuns.map(r => r.model_label).filter(Boolean))),
    [allRuns],
  );

  // Runs in scope (filtered by model), chronological (oldest → newest).
  const scopedRuns = useMemo(() => {
    const filtered = modelFilter === 'all' ? allRuns : allRuns.filter(r => r.model_label === modelFilter);
    return [...filtered].reverse(); // server returns newest-first
  }, [allRuns, modelFilter]);

  const scoredRuns = useMemo(() => scopedRuns.filter(r => r.scoring?.overall != null), [scopedRuns]);

  // Scope-level summary KPIs.
  const summary = useMemo(() => {
    const n = scopedRuns.length;
    const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
    return {
      runs: n,
      avgScore: avg(scoredRuns.map(r => r.scoring!.overall)),
      avgDuration: avg(scopedRuns.map(r => r.workflow.duration_s)),
      avgApi: avg(scopedRuns.map(r => r.workflow.api_calls)),
      avgTurns: avg(scopedRuns.map(r => r.workflow.reason_turns)),
      recursion: scopedRuns.reduce((a, r) => a + (r.workflow.recursion_hits || 0), 0),
    };
  }, [scopedRuns, scoredRuns]);

  // ── shared styles ─────────────────────────────────────────────────────
  const card: React.CSSProperties = {
    background: colors.cardBg,
    border: `1px solid ${colors.border}`,
    borderRadius: 10,
    padding: '16px 18px',
  };
  const cardLabel: React.CSSProperties = {
    fontSize: 9, letterSpacing: '0.18em', textTransform: 'uppercase',
    color: colors.muted, marginBottom: 8, fontFamily: colors.font,
  };
  const sectionHeader: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 14, margin: '4px 0 14px',
  };
  const sectionTitle: React.CSSProperties = {
    fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
    color: colors.muted, whiteSpace: 'nowrap', fontFamily: colors.fontHeading,
  };
  const rule: React.CSSProperties = { flex: 1, height: 1, background: colors.border };

  const empty = allRuns.length === 0;

  return (
    <div ref={contentRef} style={{
      width: '100%', height: '100%', overflowY: 'auto', overflowX: 'hidden',
      padding: '24px 28px', fontFamily: colors.font, color: colors.text,
    }}>
      {/* ── Header ───────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 22, paddingBottom: 16, borderBottom: `1px solid ${colors.border}` }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <div style={{
              fontSize: 9, letterSpacing: '0.2em', textTransform: 'uppercase',
              color: colors.accent, background: colors.accentDim,
              padding: '3px 10px', display: 'inline-block', marginBottom: 10, borderRadius: 4,
            }}>Benchmark</div>
            <div style={{
              fontSize: 30, fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1,
              fontFamily: colors.fontHeading,
            }}>
              MODEL <span style={{ color: colors.accent }}>PERFORMANCE</span>
            </div>
            <div style={{ fontSize: 11, color: colors.muted, marginTop: 8 }}>
              {empty
                ? 'No runs recorded yet — run the agent from the chat to populate this dashboard.'
                : `${data.count} run${data.count === 1 ? '' : 's'} recorded · auto-captured per pipeline session`}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            {/* Export PNG — captures the current tab at 3× pixel ratio */}
            <button
              onClick={() => { void handleExportPng(); }}
              disabled={exporting || empty}
              title={empty ? 'No data to export' : `Export current view as high-res PNG (${tab === 'models' ? 'Models & Scores' : 'Workflow'} tab)`}
              style={{
                ...btn(colors, isDark),
                display: 'flex', alignItems: 'center', gap: 6,
                borderColor: exportDone ? colors.accent + '66' : exporting ? colors.border : colors.border,
                color: exportDone ? colors.accent : exporting ? colors.muted : colors.muted,
                opacity: empty ? 0.4 : 1,
                cursor: empty || exporting ? 'not-allowed' : 'pointer',
              }}
            >
              {exporting ? (
                <>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ animation: 'spin 1s linear infinite' }}>
                    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                  </svg>
                  Exporting…
                </>
              ) : exportDone ? (
                <>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  Saved
                </>
              ) : (
                <>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <circle cx="8.5" cy="8.5" r="1.5" />
                    <polyline points="21 15 16 10 5 21" />
                  </svg>
                  PNG
                </>
              )}
            </button>
            <button onClick={onRefresh} title="Reload history" style={btn(colors, isDark)}>
              {loading ? 'Loading…' : 'Refresh'}
            </button>
            <button
              onClick={() => {
                if (!confirmClear) { setConfirmClear(true); setTimeout(() => setConfirmClear(false), 3000); return; }
                setConfirmClear(false); onClear();
              }}
              title="Delete all recorded runs"
              style={{ ...btn(colors, isDark), borderColor: confirmClear ? colors.error + '88' : colors.border, color: confirmClear ? colors.error : colors.muted }}
            >
              {confirmClear ? 'Clear all?' : 'Clear'}
            </button>
          </div>
        </div>

        {/* Model filter + internal tabs */}
        {!empty && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 16, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {['all', ...modelLabels].map((m, i) => {
                const active = modelFilter === m;
                const c = m === 'all' ? colors.accent : colorForModel(m, i - 1);
                return (
                  <button key={m} onClick={() => setModelFilter(m)} style={{
                    padding: '4px 12px', borderRadius: 20, cursor: 'pointer',
                    fontSize: 10, fontWeight: 600, letterSpacing: '0.04em',
                    fontFamily: colors.font, transition: 'all 0.15s',
                    border: `1px solid ${active ? c : colors.border}`,
                    background: active ? c + '22' : 'transparent',
                    color: active ? c : colors.muted,
                  }}>
                    {m === 'all' ? 'All models' : m}
                  </button>
                );
              })}
            </div>
            <div style={{ flex: 1 }} />
            <div style={{ display: 'flex', gap: 2, background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)', borderRadius: 8, padding: 3 }}>
              {(['models', 'workflow'] as Tab[]).map(t => (
                <button key={t} onClick={() => setTab(t)} style={{
                  padding: '5px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
                  fontSize: 11, fontWeight: 600, fontFamily: colors.font, transition: 'all 0.15s',
                  background: tab === t ? colors.accentDim : 'transparent',
                  color: tab === t ? colors.accent : colors.muted,
                }}>
                  {t === 'models' ? 'Models & Scores' : 'Workflow'}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {empty ? (
        <EmptyState colors={colors} />
      ) : (
        <>
          {/* ── Summary KPI row ─────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10, marginBottom: 26 }}>
            <Kpi colors={colors} label="Runs" value={summary.runs} />
            <Kpi colors={colors} label="Avg Score" value={fmt(summary.avgScore)} unit="/100" accent />
            <Kpi colors={colors} label="Avg Time" value={fmt(summary.avgDuration != null ? summary.avgDuration / 60 : null, 1)} unit="min" />
            <Kpi colors={colors} label="Avg API Calls" value={fmt(summary.avgApi, 0)} />
            <Kpi colors={colors} label="Avg Turns" value={fmt(summary.avgTurns, 0)} />
            <Kpi colors={colors} label="Recursion Hits" value={summary.recursion} danger={summary.recursion > 0} />
          </div>

          {tab === 'models' ? (
            <ModelsModule
              colors={colors} isDark={isDark}
              models={data.aggregate.models} metrics={data.aggregate.metrics}
              scoredRuns={scoredRuns}
              card={card} cardLabel={cardLabel} sectionHeader={sectionHeader} sectionTitle={sectionTitle} rule={rule}
            />
          ) : (
            <WorkflowModule
              colors={colors} isDark={isDark}
              scopedRuns={scopedRuns}
              card={card} cardLabel={cardLabel} sectionHeader={sectionHeader} sectionTitle={sectionTitle} rule={rule}
            />
          )}
        </>
      )}
    </div>
  );
};

// ════════════════════════════════════════════════════════════════════════
// MODELS & SCORES MODULE (prototype module 02)
// ════════════════════════════════════════════════════════════════════════
interface ModuleCommon {
  colors: ReturnType<typeof useTheme>['colors'];
  isDark: boolean;
  card: React.CSSProperties;
  cardLabel: React.CSSProperties;
  sectionHeader: React.CSSProperties;
  sectionTitle: React.CSSProperties;
  rule: React.CSSProperties;
}

const ModelsModule: React.FC<ModuleCommon & {
  models: BenchModelAgg[];
  metrics: string[];
  scoredRuns: BenchRun[];
}> = ({ colors, isDark, models, metrics, scoredRuns, card, cardLabel, sectionHeader, sectionTitle, rule }) => {
  return (
    <>
      <div style={sectionHeader}><span style={sectionTitle}>Score Trend &amp; Model Comparison</span><span style={rule} /></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 28 }}>
        {/* Score trend */}
        <div style={card}>
          <div style={cardLabel}>Score Trend</div>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 2 }}>Overall Score Over Runs</div>
          <div style={{ fontSize: 10, color: colors.muted, marginBottom: 14, fontFamily: colors.font }}>
            Each point is one recorded run, colored by model
          </div>
          <ScoreTrend runs={scoredRuns} colors={colors} />
        </div>

        {/* Model comparison */}
        <div style={card}>
          <div style={cardLabel}>Model Comparison</div>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 2 }}>Avg Score per Metric</div>
          <div style={{ fontSize: 10, color: colors.muted, marginBottom: 14, fontFamily: colors.font }}>
            Averaged across all recorded runs per model
          </div>
          <ModelCompare models={models} metrics={metrics} colors={colors} isDark={isDark} />
        </div>
      </div>

      {/* Per-model leaderboard table */}
      <div style={sectionHeader}><span style={sectionTitle}>Model Leaderboard</span><span style={rule} /></div>
      <div style={card}>
        <ModelTable models={models} metrics={metrics} colors={colors} isDark={isDark} />
      </div>
    </>
  );
};

const ScoreTrend: React.FC<{ runs: BenchRun[]; colors: ModuleCommon['colors'] }> = ({ runs, colors }) => {
  const W = 460, H = 200, pad = { l: 34, r: 14, t: 18, b: 26 };
  if (runs.length === 0) return <NoData colors={colors} text="No scored runs yet" />;
  const scores = runs.map(r => r.scoring!.overall);
  const yMin = Math.max(0, Math.floor(Math.min(...scores) / 10) * 10 - 5);
  const yMax = 100;
  const n = runs.length;
  const xS = (W - pad.l - pad.r) / Math.max(n - 1, 1);
  const toX = (i: number) => pad.l + i * xS;
  const toY = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - (v - yMin) / (yMax - yMin));
  const grid = [yMin, Math.round((yMin + yMax) / 2), yMax];
  const lineD = scores.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i)},${toY(v)}`).join(' ');

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={200} style={{ overflow: 'visible' }}>
      {grid.map(v => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={toY(v)} y2={toY(v)} stroke={colors.border} strokeWidth={1} />
          <text x={pad.l - 5} y={toY(v) + 3} textAnchor="end" fontSize={8} fill={colors.muted} fontFamily={colors.font}>{v}</text>
        </g>
      ))}
      <path d={lineD} fill="none" stroke={colors.accent} strokeWidth={2} opacity={0.5} />
      {runs.map((r, i) => {
        const c = colorForModel(r.model_label, 0);
        return (
          <g key={r.run_id}>
            <circle cx={toX(i)} cy={toY(scores[i])} r={4.5} fill={c} stroke={colors.cardBg} strokeWidth={2}>
              <title>{`${r.model_label} · ${scores[i]}/100 · ${r.scoring!.grade}\n${r.prompt}`}</title>
            </circle>
            <text x={toX(i)} y={toY(scores[i]) - 9} textAnchor="middle" fontSize={8} fill={c} fontFamily={colors.font}>{scores[i]}</text>
          </g>
        );
      })}
    </svg>
  );
};

const ModelCompare: React.FC<{ models: BenchModelAgg[]; metrics: string[]; colors: ModuleCommon['colors']; isDark: boolean }> =
({ models, metrics, colors }) => {
  if (models.length === 0) return <NoData colors={colors} text="No model data yet" />;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {metrics.map(metric => (
        <div key={metric}>
          <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 5 }}>{METRIC_LABELS[metric] || metric}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {models.map((m, i) => {
              const v = m.metrics[metric];
              const c = colorForModel(m.label, i);
              return (
                <div key={m.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 78, fontSize: 9, color: c, fontFamily: colors.font, textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.label}</span>
                  <div style={{ flex: 1, height: 6, background: colors.inputBg, borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${v ?? 0}%`, background: c, transition: 'width 0.6s ease' }} />
                  </div>
                  <span style={{ width: 30, textAlign: 'right', fontSize: 9, color: colors.muted, fontFamily: colors.font }}>{v == null ? '—' : v}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};

const ModelTable: React.FC<{ models: BenchModelAgg[]; metrics: string[]; colors: ModuleCommon['colors']; isDark: boolean }> =
({ models, metrics, colors, isDark }) => {
  const th: React.CSSProperties = {
    fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: colors.muted,
    padding: '8px 10px', textAlign: 'left', borderBottom: `1.5px solid ${colors.border}`, fontFamily: colors.font, fontWeight: 700,
  };
  const td: React.CSSProperties = {
    padding: '9px 10px', fontSize: 11, fontFamily: colors.font, borderBottom: `1px solid ${colors.border}`,
  };
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={th}>Model</th>
            <th style={th}>Runs</th>
            <th style={th}>Overall</th>
            {metrics.map(m => <th key={m} style={th}>{METRIC_LABELS[m] || m}</th>)}
            <th style={th}>Avg Time</th>
            <th style={th}>Avg Turns</th>
            <th style={th}>Avg API</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m, i) => {
            const c = colorForModel(m.label, i);
            return (
              <tr key={m.label} style={{ background: i % 2 && !isDark ? 'rgba(0,0,0,0.015)' : 'transparent' }}>
                <td style={{ ...td, fontWeight: 700, color: c }}>{m.label}</td>
                <td style={td}>{m.runs}</td>
                <td style={{ ...td, fontWeight: 700 }}>{m.overall == null ? '—' : `${m.overall}`}</td>
                {metrics.map(metric => <td key={metric} style={td}>{m.metrics[metric] == null ? '—' : m.metrics[metric]}</td>)}
                <td style={td}>{m.avg_duration_s == null ? '—' : `${(m.avg_duration_s / 60).toFixed(1)}m`}</td>
                <td style={td}>{m.avg_turns == null ? '—' : m.avg_turns}</td>
                <td style={td}>{m.avg_api_calls == null ? '—' : m.avg_api_calls}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ════════════════════════════════════════════════════════════════════════
// WORKFLOW MODULE (prototype module 03)
// ════════════════════════════════════════════════════════════════════════
const WorkflowModule: React.FC<ModuleCommon & { scopedRuns: BenchRun[] }> =
({ colors, isDark, scopedRuns, card, cardLabel, sectionHeader, sectionTitle, rule }) => {
  // The Gantt / breakdown / timeline show the most recent run in scope.
  const latest = scopedRuns.length ? scopedRuns[scopedRuns.length - 1] : null;

  return (
    <>
      <div style={sectionHeader}><span style={sectionTitle}>Pipeline Timing &amp; API Distribution</span><span style={rule} /></div>
      {latest && (
        <div style={{ fontSize: 10, color: colors.muted, marginBottom: 12, fontFamily: colors.font }}>
          Latest run · <span style={{ color: colorForModel(latest.model_label, 0) }}>{latest.model_label}</span> · {latest.layout_name} · {latest.workflow.duration_s}s
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 28 }}>
        <div style={card}>
          <div style={cardLabel}>Pipeline Stage Duration</div>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Time per Node (ms)</div>
          {latest ? <Gantt run={latest} colors={colors} /> : <NoData colors={colors} text="No run in scope" />}
        </div>
        <div style={card}>
          <div style={cardLabel}>API Calls Breakdown</div>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Calls per Pipeline Category</div>
          {latest ? <CategoryBreakdown run={latest} colors={colors} /> : <NoData colors={colors} text="No run in scope" />}
        </div>
      </div>

      <div style={sectionHeader}><span style={sectionTitle}>Run Timeline &amp; Multi-Run Trend</span><span style={rule} /></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div style={card}>
          <div style={cardLabel}>Event Log — Latest Run</div>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Node Events with Offsets</div>
          {latest ? <Timeline run={latest} colors={colors} /> : <NoData colors={colors} text="No run in scope" />}
        </div>
        <div style={card}>
          <div style={cardLabel}>Multi-Run Performance</div>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Turns &amp; Duration Across Runs</div>
          <PerfTrend runs={scopedRuns} colors={colors} isDark={isDark} />
        </div>
      </div>
    </>
  );
};

const Gantt: React.FC<{ run: BenchRun; colors: ModuleCommon['colors'] }> = ({ run, colors }) => {
  const g = run.workflow.gantt;
  if (!g.length) return <NoData colors={colors} text="No stage timings" />;
  const max = Math.max(...g.map(d => d.total_ms));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {g.map((d, i) => {
        const pct = max > 0 ? (d.total_ms / max) * 100 : 0;
        return (
          <div key={`${d.node}-${i}`} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ width: 120, fontSize: 9, color: colors.muted, textAlign: 'right', fontFamily: colors.font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {nodeLabel(d.node)}{d.count > 1 ? ` ×${d.count}` : ''}
            </span>
            <div style={{ flex: 1, height: 18, background: colors.inputBg, borderRadius: 3, position: 'relative' }}>
              <div style={{
                position: 'absolute', top: 2, bottom: 2, left: 0, width: `${pct}%`,
                background: colors.accent, borderRadius: 2, minWidth: 2,
                display: 'flex', alignItems: 'center', paddingLeft: 5,
              }} />
            </div>
            <span style={{ width: 52, textAlign: 'right', fontSize: 9, color: colors.muted, fontFamily: colors.font }}>
              {d.total_ms >= 1000 ? `${(d.total_ms / 1000).toFixed(1)}s` : `${Math.round(d.total_ms)}ms`}
            </span>
          </div>
        );
      })}
    </div>
  );
};

const CategoryBreakdown: React.FC<{ run: BenchRun; colors: ModuleCommon['colors'] }> = ({ run, colors }) => {
  const cats = run.workflow.category_calls;
  const entries = Object.entries(cats).filter(([k]) => k !== 'setup').sort((a, b) => b[1] - a[1]);
  if (!entries.length) return <NoData colors={colors} text="No calls recorded" />;
  const max = Math.max(...entries.map(([, v]) => v));
  const total = entries.reduce((a, [, v]) => a + v, 0);
  const CAT_COLORS: Record<string, string> = {
    reason: colors.accent, tools: '#d97706', analysis: '#059669',
    profile: '#7c3aed', space: '#7c3aed', populate: '#a78bfa', memory: '#0ea5e9', other: '#9ca3af',
  };
  return (
    <div>
      <div style={{ fontSize: 10, color: colors.muted, marginBottom: 10, fontFamily: colors.font }}>Total: {total} pipeline calls</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {entries.map(([cat, v]) => {
          const c = CAT_COLORS[cat] || colors.accent;
          return (
            <div key={cat} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ width: 70, fontSize: 10, fontWeight: 600, fontFamily: colors.font }}>{CATEGORY_LABELS[cat] || cat}</span>
              <div style={{ flex: 1, height: 8, background: colors.inputBg, borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${(v / max) * 100}%`, background: c, transition: 'width 0.5s ease' }} />
              </div>
              <span style={{ width: 26, textAlign: 'right', fontSize: 10, color: colors.muted, fontFamily: colors.font }}>{v}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const Timeline: React.FC<{ run: BenchRun; colors: ModuleCommon['colors'] }> = ({ run, colors }) => {
  // Show node "started" events (the meaningful steps) with their offsets.
  const events = run.timeline.filter(e => e.status === 'started').slice(0, 24);
  if (!events.length) return <NoData colors={colors} text="No events" />;
  return (
    <div style={{ position: 'relative', paddingLeft: 16, maxHeight: 240, overflowY: 'auto' }}>
      <div style={{ position: 'absolute', left: 4, top: 4, bottom: 4, width: 1.5, background: colors.border }} />
      {events.map((e, i) => (
        <div key={i} style={{ position: 'relative', marginBottom: 11 }}>
          <div style={{
            position: 'absolute', left: -15, top: 4, width: 7, height: 7, borderRadius: '50%',
            background: e.status === 'error' ? colors.error : colors.accent,
          }} />
          <div style={{ fontSize: 8, color: colors.muted, fontFamily: colors.font }}>
            +{(e.t_ms / 1000).toFixed(2)}s
          </div>
          <div style={{ fontSize: 11, fontWeight: 600 }}>{nodeLabel(e.node)}</div>
        </div>
      ))}
    </div>
  );
};

const PerfTrend: React.FC<{ runs: BenchRun[]; colors: ModuleCommon['colors']; isDark: boolean }> = ({ runs, colors }) => {
  const W = 460, H = 210, pad = { l: 34, r: 34, t: 22, b: 28 };
  if (runs.length === 0) return <NoData colors={colors} text="No runs in scope" />;
  const turns = runs.map(r => r.workflow.reason_turns);
  const times = runs.map(r => r.workflow.duration_min);
  const n = runs.length;
  const xS = (W - pad.l - pad.r) / Math.max(n - 1, 1);
  const toX = (i: number) => pad.l + i * xS;
  const mxT = Math.max(...turns, 1) * 1.2;
  const mxTm = Math.max(...times, 0.1) * 1.2;
  const toYT = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / mxT);
  const toYTm = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / mxTm);
  const turnsD = turns.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i)},${toYT(v)}`).join(' ');
  const timeD = times.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i)},${toYTm(v)}`).join(' ');
  const COL_TURNS = colors.accent, COL_TIME = colors.success;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={210} style={{ overflow: 'visible' }}>
      {[0.25, 0.5, 0.75, 1].map(p => (
        <line key={p} x1={pad.l} x2={W - pad.r} y1={pad.t + (H - pad.t - pad.b) * (1 - p)} y2={pad.t + (H - pad.t - pad.b) * (1 - p)} stroke={colors.border} strokeWidth={1} />
      ))}
      <path d={turnsD} fill="none" stroke={COL_TURNS} strokeWidth={2} />
      <path d={timeD} fill="none" stroke={COL_TIME} strokeWidth={2} />
      {runs.map((r, i) => (
        <g key={r.run_id}>
          <circle cx={toX(i)} cy={toYT(turns[i])} r={3.5} fill={COL_TURNS} stroke={colors.cardBg} strokeWidth={1.5} />
          <circle cx={toX(i)} cy={toYTm(times[i])} r={3.5} fill={COL_TIME} stroke={colors.cardBg} strokeWidth={1.5} />
          <text x={toX(i)} y={H - 8} textAnchor="middle" fontSize={8} fill={colors.muted} fontFamily={colors.font}>{i + 1}</text>
        </g>
      ))}
      {/* legend */}
      <rect x={W - 120} y={6} width={9} height={4} fill={COL_TURNS} />
      <text x={W - 107} y={11} fontSize={8} fill={colors.muted} fontFamily={colors.font}>Reason turns</text>
      <rect x={W - 120} y={18} width={9} height={4} fill={COL_TIME} />
      <text x={W - 107} y={23} fontSize={8} fill={colors.muted} fontFamily={colors.font}>Duration (min)</text>
    </svg>
  );
};

// ════════════════════════════════════════════════════════════════════════
// Small shared bits
// ════════════════════════════════════════════════════════════════════════
const Kpi: React.FC<{ colors: ModuleCommon['colors']; label: string; value: React.ReactNode; unit?: string; accent?: boolean; danger?: boolean }> =
({ colors, label, value, unit, accent, danger }) => (
  <div style={{ background: colors.cardBg, border: `1px solid ${colors.border}`, borderRadius: 10, padding: '12px 14px' }}>
    <div style={{ fontSize: 8.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: colors.muted, marginBottom: 6, fontFamily: colors.font, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</div>
    <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1, color: danger ? colors.error : accent ? colors.accent : colors.text, fontFamily: colors.fontHeading }}>
      {value}{unit && <span style={{ fontSize: 11, color: colors.muted, fontWeight: 400, marginLeft: 3 }}>{unit}</span>}
    </div>
  </div>
);

const NoData: React.FC<{ colors: ModuleCommon['colors']; text: string }> = ({ colors, text }) => (
  <div style={{ height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center', color: colors.muted, fontSize: 11, fontFamily: colors.font }}>
    {text}
  </div>
);

const EmptyState: React.FC<{ colors: ModuleCommon['colors'] }> = ({ colors }) => (
  <div style={{ height: '60%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, color: colors.muted }}>
    <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke={colors.accent} strokeWidth={1.5} opacity={0.5}>
      <path d="M3 3v18h18" /><path d="M18 17V9M13 17V5M8 17v-3" />
    </svg>
    <div style={{ fontSize: 13, textAlign: 'center', maxWidth: 340, lineHeight: 1.5 }}>
      No benchmark runs yet. Each time you run the agent from the chat, this dashboard records its
      model, timing, API calls and scores automatically — then compares models here.
    </div>
  </div>
);

function btn(colors: ModuleCommon['colors'], _isDark: boolean): React.CSSProperties {
  return {
    padding: '6px 14px', borderRadius: 7, cursor: 'pointer',
    fontSize: 10, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase',
    fontFamily: colors.font, border: `1px solid ${colors.border}`,
    background: 'transparent', color: colors.muted, transition: 'all 0.15s',
  };
}

function fmt(v: number | null | undefined, dp = 1): string {
  if (v == null) return '—';
  return dp === 0 ? String(Math.round(v)) : v.toFixed(dp);
}

export default BenchmarkDashboard;
