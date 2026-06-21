import React, { useCallback, useMemo, useState } from 'react';
import { useTheme } from '../common/ThemeToggle';
import MiniPlan from './MiniPlan';
import type { LayoutJSON } from '../../types';

// ── Types ────────────────────────────────────────────────────────────────
type LayoutType = 'residential' | 'industrial';

interface ProgramPill {
  name: string;
  count: number; // 0 = not included
}

interface LibraryItem {
  id: string;
  layout: LayoutJSON;
  name: string;       // editable save-name (prefilled)
  saved: boolean;
  savedName: string | null;
}

export interface AILayoutGeneratorProps {
  /** Preview a candidate in the viewport; null restores the committed layout. */
  onPreview: (layout: LayoutJSON | null) => void;
  /** Persist a candidate to AI_GENERATED and load it as active. Returns saved name or null. */
  onSave: (name: string, layout: LayoutJSON) => Promise<string | null>;
  /** Close the generator and return to the original left panel. */
  onClose: () => void;
}

// ── Constants ──────────────────────────────────────────────────────────────
const MAX_LIBRARY = 4;
const AREA_MIN = 10;
const AREA_MAX = 2000;

const DEFAULT_PROGRAMS: Record<LayoutType, ProgramPill[]> = {
  residential: [
    { name: 'Bedroom', count: 1 },
    { name: 'Bathroom', count: 1 },
    { name: 'Kitchen', count: 1 },
    { name: 'Living', count: 1 },
    { name: 'Dining', count: 0 },
    { name: 'Corridor', count: 0 },
    { name: 'Storage', count: 0 },
  ],
  industrial: [
    { name: 'Warehouse', count: 1 },
    { name: 'Loading Dock', count: 1 },
    { name: 'Assembly', count: 0 },
    { name: 'Office', count: 1 },
    { name: 'WC', count: 1 },
    { name: 'Locker Room', count: 0 },
    { name: 'Storage', count: 0 },
    { name: 'Mechanical', count: 0 },
  ],
};

const DEFAULT_RANGE: Record<LayoutType, [number, number]> = {
  residential: [60, 120],
  industrial: [400, 1000],
};

// ── Spinner ──────────────────────────────────────────────────────────────
const Spinner: React.FC<{ size?: number; color: string }> = ({ size = 14, color }) => (
  <span
    style={{
      width: size, height: size, borderRadius: '50%',
      border: `2px solid ${color}33`, borderTopColor: color,
      display: 'inline-block', animation: 'spin 0.7s linear infinite',
    }}
  />
);

// ── Helpers ──────────────────────────────────────────────────────────────
const uid = () => Math.random().toString(36).slice(2, 9);

function defaultName(type: LayoutType): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  const stamp = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
  return `AI_${type}_${stamp}_${Math.random().toString(36).slice(2, 5)}`;
}

function polyArea(pts: [number, number][]): number {
  if (!pts || pts.length < 3) return 0;
  let a = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[i + 1];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}

function layoutArea(l: LayoutJSON): number {
  const outline = (l.outline ?? []) as [number, number][];
  if (outline.length >= 3) return polyArea(outline);
  return (l.rooms ?? []).reduce((s, r) => s + (Number(r.attributes?.area) || 0), 0);
}

// ── Component ──────────────────────────────────────────────────────────────
const AILayoutGenerator: React.FC<AILayoutGeneratorProps> = ({ onPreview, onSave, onClose }) => {
  const { colors, theme } = useTheme();
  const isLight = theme === 'light';

  const [layoutType, setLayoutType] = useState<LayoutType>('residential');
  const [areaMin, setAreaMin] = useState<number>(DEFAULT_RANGE.residential[0]);
  const [areaMax, setAreaMax] = useState<number>(DEFAULT_RANGE.residential[1]);
  const [programs, setPrograms] = useState<ProgramPill[]>(DEFAULT_PROGRAMS.residential);
  const [brief, setBrief] = useState('');
  const [customPill, setCustomPill] = useState('');

  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const libraryFull = library.length >= MAX_LIBRARY;
  const selected = useMemo(() => library.find(i => i.id === selectedId) ?? null, [library, selectedId]);

  // ── Type switch — reseed program defaults + sensible range ────────────────
  const switchType = useCallback((t: LayoutType) => {
    if (t === layoutType) return;
    setLayoutType(t);
    setPrograms(DEFAULT_PROGRAMS[t].map(p => ({ ...p })));
    setAreaMin(DEFAULT_RANGE[t][0]);
    setAreaMax(DEFAULT_RANGE[t][1]);
  }, [layoutType]);

  // ── Program pills ─────────────────────────────────────────────────────────
  const togglePill = useCallback((name: string) => {
    setPrograms(prev => prev.map(p => p.name === name ? { ...p, count: p.count > 0 ? 0 : 1 } : p));
  }, []);
  const bumpPill = useCallback((name: string, delta: number) => {
    setPrograms(prev => prev.map(p => p.name === name ? { ...p, count: Math.max(0, p.count + delta) } : p));
  }, []);
  const removePill = useCallback((name: string) => {
    setPrograms(prev => prev.filter(p => p.name !== name));
  }, []);
  const addCustomPill = useCallback(() => {
    const name = customPill.trim();
    if (!name) return;
    setPrograms(prev =>
      prev.some(p => p.name.toLowerCase() === name.toLowerCase())
        ? prev.map(p => p.name.toLowerCase() === name.toLowerCase() ? { ...p, count: Math.max(1, p.count) } : p)
        : [...prev, { name, count: 1 }]
    );
    setCustomPill('');
  }, [customPill]);

  // ── Range clamping ─────────────────────────────────────────────────────────
  const onMinChange = useCallback((v: number) => setAreaMin(Math.min(v, areaMax)), [areaMax]);
  const onMaxChange = useCallback((v: number) => setAreaMax(Math.max(v, areaMin)), [areaMin]);

  // ── Generate one ───────────────────────────────────────────────────────────
  const handleGenerate = useCallback(async () => {
    if (generating || libraryFull) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch('/api/layouts/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layoutType,
          areaMin,
          areaMax,
          programs: programs.filter(p => p.count > 0).map(p => ({ name: p.name, count: p.count })),
          brief: brief.trim(),
          variantIndex: library.length,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `Generation failed (${res.status})`);
      }
      const data = await res.json();
      const layout = data.layout as LayoutJSON;
      const item: LibraryItem = {
        id: uid(), layout, name: defaultName(layoutType), saved: false, savedName: null,
      };
      setLibrary(prev => [...prev, item]);
      setSelectedId(item.id);
      onPreview(layout);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setGenerating(false);
    }
  }, [generating, libraryFull, layoutType, areaMin, areaMax, programs, brief, library.length, onPreview]);

  // ── Library card actions ─────────────────────────────────────────────────
  const selectCard = useCallback((item: LibraryItem) => {
    setSelectedId(item.id);
    onPreview(item.layout);
  }, [onPreview]);

  const removeCard = useCallback((id: string) => {
    setLibrary(prev => prev.filter(i => i.id !== id));
    if (selectedId === id) {
      setSelectedId(null);
      onPreview(null);
    }
  }, [selectedId, onPreview]);

  const setCardName = useCallback((id: string, name: string) => {
    setLibrary(prev => prev.map(i => i.id === id ? { ...i, name } : i));
  }, []);

  const saveCard = useCallback(async (item: LibraryItem) => {
    setSavingId(item.id);
    setError(null);
    const savedName = await onSave(item.name.trim() || defaultName(layoutType), item.layout);
    setSavingId(null);
    if (savedName) {
      setLibrary(prev => prev.map(i => i.id === item.id ? { ...i, saved: true, savedName } : i));
    } else {
      setError('Could not save the layout to AI_GENERATED.');
    }
  }, [onSave, layoutType]);

  // ── Styles ───────────────────────────────────────────────────────────────
  const sectionHeader: React.CSSProperties = {
    fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
    color: colors.muted, fontFamily: colors.fontHeading, marginBottom: 8,
  };
  const card: React.CSSProperties = {
    background: colors.cardBg, border: `1px solid ${colors.border}`, borderRadius: 10, padding: 12,
  };
  const segBtn = (active: boolean): React.CSSProperties => ({
    flex: 1, padding: '7px 0', borderRadius: 8, border: 'none', cursor: 'pointer',
    fontSize: 12, fontWeight: 600, fontFamily: colors.font, transition: 'all 0.15s',
    // Light: translucent accent + accent text (matches the view-mode pills / Analyze).
    // Dark: solid accent fill (reads well on the dark panel).
    background: active ? (isLight ? colors.accentDim : colors.accent) : 'transparent',
    color: active ? (isLight ? colors.accent : '#0a0612') : colors.muted,
  });
  const inputStyle: React.CSSProperties = {
    width: '100%', background: colors.inputBg, border: `1px solid ${colors.border}`,
    borderRadius: 8, padding: '8px 10px', color: colors.text, fontSize: 12,
    fontFamily: colors.font, outline: 'none', boxSizing: 'border-box',
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '9px 12px', borderBottom: `1px solid ${colors.border}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={colors.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 3v4M3 5h4M6 17v4M4 19h4M13 3l2.5 6.5L22 12l-6.5 2.5L13 21l-2.5-6.5L4 12l6.5-2.5z" />
          </svg>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: colors.text, fontFamily: colors.fontHeading }}>
            AI Layout Generator
          </span>
        </div>
        <button onClick={onClose} title="Close generator" style={{
          background: 'transparent', border: `1px solid ${colors.border}`, borderRadius: 6,
          width: 24, height: 24, cursor: 'pointer', color: colors.muted, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Scrollable body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* 1. Layout type */}
        <div>
          <div style={sectionHeader}>Layout type</div>
          <div style={{ display: 'flex', gap: 4, background: colors.inputBg, padding: 3, borderRadius: 10, border: `1px solid ${colors.border}` }}>
            <button style={segBtn(layoutType === 'residential')} onClick={() => switchType('residential')}>Residential</button>
            <button style={segBtn(layoutType === 'industrial')} onClick={() => switchType('industrial')}>Industrial</button>
          </div>
        </div>

        {/* 2. Area range */}
        <div>
          <div style={sectionHeader}>Ideal total area (m²)</div>
          <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: colors.text, fontFamily: colors.font }}>
              <span>{Math.round(areaMin)} m²</span>
              <span style={{ color: colors.muted }}>–</span>
              <span>{Math.round(areaMax)} m²</span>
            </div>
            <div className="dual-range">
              <div className="dual-range__track" style={{ background: colors.border }} />
              <div className="dual-range__fill" style={{
                background: colors.accent,
                left: `${((areaMin - AREA_MIN) / (AREA_MAX - AREA_MIN)) * 100}%`,
                width: `${((areaMax - areaMin) / (AREA_MAX - AREA_MIN)) * 100}%`,
              }} />
              <input type="range" min={AREA_MIN} max={AREA_MAX} step={5} value={areaMin}
                onChange={e => onMinChange(Number(e.target.value))} aria-label="Start area (m²)" />
              <input type="range" min={AREA_MIN} max={AREA_MAX} step={5} value={areaMax}
                onChange={e => onMaxChange(Number(e.target.value))} aria-label="End area (m²)" />
            </div>
          </div>
        </div>

        {/* 3. Programs */}
        <div>
          <div style={sectionHeader}>Program</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {programs.map(p => {
              const on = p.count > 0;
              return (
                <div key={p.name} style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  background: on ? colors.accentDim : colors.inputBg,
                  border: `1px solid ${on ? colors.accent : colors.border}`,
                  borderRadius: 20, padding: '3px 4px 3px 10px',
                }}>
                  <button onClick={() => togglePill(p.name)} style={{
                    background: 'transparent', border: 'none', cursor: 'pointer', padding: 0,
                    fontSize: 11, fontFamily: colors.font, color: on ? colors.accent : colors.muted, fontWeight: on ? 600 : 400,
                  }}>
                    {p.name}{on ? ` ×${p.count}` : ''}
                  </button>
                  {on && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                      <button onClick={() => bumpPill(p.name, -1)} style={stepperStyle(colors)}>−</button>
                      <button onClick={() => bumpPill(p.name, +1)} style={stepperStyle(colors)}>+</button>
                    </span>
                  )}
                  <button onClick={() => removePill(p.name)} title="Remove pill" style={{
                    background: 'transparent', border: 'none', cursor: 'pointer', padding: '0 2px',
                    color: colors.muted, fontSize: 13, lineHeight: 1,
                  }}>×</button>
                </div>
              );
            })}
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <input
              value={customPill}
              onChange={e => setCustomPill(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustomPill(); } }}
              placeholder="Add a program…"
              style={{ ...inputStyle, flex: 1 }}
            />
            <button onClick={addCustomPill} style={{
              background: colors.inputBg, border: `1px solid ${colors.border}`, borderRadius: 8,
              padding: '0 12px', cursor: 'pointer', color: colors.text, fontSize: 12, fontFamily: colors.font,
            }}>Add</button>
          </div>
        </div>

        {/* 4. Brief */}
        <div>
          <div style={sectionHeader}>Brief</div>
          <textarea
            value={brief}
            onChange={e => setBrief(e.target.value)}
            placeholder="Describe briefly what you want…"
            rows={3}
            style={{ ...inputStyle, resize: 'vertical', minHeight: 56 }}
          />
        </div>

        {/* 5. Generate */}
        <div>
          <button
            onClick={handleGenerate}
            disabled={generating || libraryFull}
            style={{
              width: '100%', padding: '11px 0', borderRadius: 10,
              border: isLight && !(generating || libraryFull) ? `1px solid ${colors.accent}` : 'none',
              cursor: generating || libraryFull ? 'not-allowed' : 'pointer',
              fontSize: 13, fontWeight: 700, letterSpacing: '0.06em', fontFamily: colors.font,
              background: generating || libraryFull ? colors.inputBg : (isLight ? colors.accentDim : colors.accent),
              color: generating || libraryFull ? colors.muted : (isLight ? colors.accent : '#0a0612'),
              transition: 'all 0.15s',
            }}
          >
            {generating ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <Spinner size={14} color={colors.muted} />
                Generating…
              </span>
            ) : libraryFull ? 'Library full (4/4)' : 'Generate'}
          </button>
          {libraryFull && !generating && (
            <div style={{ fontSize: 10, color: colors.muted, marginTop: 6, textAlign: 'center' }}>
              Discard a candidate below to generate more.
            </div>
          )}
          {error && (
            <div style={{ fontSize: 11, color: colors.error, marginTop: 8, lineHeight: 1.4 }}>{error}</div>
          )}
        </div>

        {/* 6. Library */}
        {(library.length > 0 || generating) && (
          <div>
            <div style={sectionHeader}>Library ({library.length}/{MAX_LIBRARY})</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {library.map(item => {
                const isSel = item.id === selectedId;
                return (
                  <div key={item.id} onClick={() => selectCard(item)} style={{
                    ...card, padding: 6, cursor: 'pointer', position: 'relative',
                    borderColor: isSel ? colors.accent : colors.border,
                    boxShadow: isSel ? `0 0 0 1px ${colors.accent}` : 'none',
                  }}>
                    <MiniPlan
                      layout={item.layout}
                      width={120}
                      height={84}
                      roomColor={colors.accent}
                      outlineColor={colors.accent}
                      bg={colors.inputBg}
                    />
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 5 }}>
                      <span style={{ fontSize: 10, color: colors.muted, fontFamily: colors.font }}>
                        {Math.round(layoutArea(item.layout))} m² · {item.layout.rooms?.length ?? 0} rooms
                      </span>
                      {item.saved && (
                        <span title="Saved to AI_GENERATED" style={{ color: colors.success, display: 'flex' }}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </span>
                      )}
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeCard(item.id); }}
                      title="Discard"
                      style={{
                        position: 'absolute', top: 4, right: 4, width: 18, height: 18, borderRadius: 5,
                        background: colors.bg, border: `1px solid ${colors.border}`, cursor: 'pointer',
                        color: colors.muted, fontSize: 11, lineHeight: 1, display: 'flex',
                        alignItems: 'center', justifyContent: 'center',
                      }}
                    >×</button>
                  </div>
                );
              })}
              {generating && (
                <div style={{ ...card, padding: 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{
                    width: '100%', height: 84, borderRadius: 6,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: `linear-gradient(110deg, ${colors.inputBg} 25%, ${colors.accentDim} 50%, ${colors.inputBg} 75%)`,
                    backgroundSize: '200% 100%', animation: 'genShimmer 1.4s ease-in-out infinite',
                  }}>
                    <Spinner size={20} color={colors.accent} />
                  </div>
                  <span style={{ fontSize: 10, color: colors.muted, fontFamily: colors.font, textAlign: 'center' }}>
                    Generating layout…
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 7. Save / accept the selected candidate */}
        {selected && (
          <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={sectionHeader}>Save selected as project layout</div>
            <input
              value={selected.name}
              onChange={e => setCardName(selected.id, e.target.value)}
              placeholder="AI_layout_name"
              style={inputStyle}
            />
            <button
              onClick={() => saveCard(selected)}
              disabled={savingId === selected.id}
              style={{
                width: '100%', padding: '9px 0', borderRadius: 8,
                cursor: savingId === selected.id ? 'not-allowed' : 'pointer',
                fontSize: 12, fontWeight: 700, fontFamily: colors.font,
                background: selected.saved ? colors.inputBg : (isLight ? colors.success + '22' : colors.success),
                color: selected.saved ? colors.success : (isLight ? colors.success : '#0a0612'),
                border: (selected.saved || isLight) ? `1px solid ${colors.success}` : 'none',
              }}
            >
              {savingId === selected.id ? 'Saving…' : selected.saved ? 'Saved — save again' : 'Accept & use this layout'}
            </button>
            <div style={{ fontSize: 10, color: colors.muted, textAlign: 'center' }}>
              Saved layouts appear under “AI_GENERATED” in the Layout Loader. You can keep several.
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{ flexShrink: 0, padding: 10, borderTop: `1px solid ${colors.border}` }}>
        <button onClick={onClose} style={{
          width: '100%', padding: '8px 0', borderRadius: 8, cursor: 'pointer',
          background: 'transparent', border: `1px solid ${colors.border}`,
          color: colors.muted, fontSize: 12, fontFamily: colors.font,
        }}>Done — back to layouts</button>
      </div>
    </div>
  );
};

function stepperStyle(colors: ReturnType<typeof useTheme>['colors']): React.CSSProperties {
  return {
    width: 18, height: 18, borderRadius: 5, border: `1px solid ${colors.border}`,
    background: colors.bg, color: colors.text, cursor: 'pointer', fontSize: 12,
    lineHeight: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
  };
}

export default AILayoutGenerator;
