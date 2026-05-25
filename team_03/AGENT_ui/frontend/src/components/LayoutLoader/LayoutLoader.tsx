import React, { useCallback } from 'react';
import GlassPanel from '../common/GlassPanel';
import { useTheme } from '../common/ThemeToggle';
import LayoutDropzone from './LayoutDropzone';

export interface LayoutInfo {
  name: string;
  path: string;
  category: string;
}

export interface LayoutLoaderProps {
  layouts: LayoutInfo[];
  selectedLayout: string | null;
  onSelect: (name: string) => void;
  onUpload: (file: File) => void;
}

const ChevronIcon: React.FC<{ color: string }> = ({ color }) => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="6 9 12 15 18 9" />
  </svg>
);

const LayoutLoader: React.FC<LayoutLoaderProps> = ({
  layouts,
  selectedLayout,
  onSelect,
  onUpload,
}) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';

  const handleSelectChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const val = e.target.value;
      if (val) onSelect(val);
    },
    [onSelect]
  );

  const grouped = layouts.reduce<Record<string, LayoutInfo[]>>((acc, layout) => {
    const cat = layout.category || 'Other';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(layout);
    return acc;
  }, {});

  const selectStyle: React.CSSProperties = {
    width: '100%',
    appearance: 'none',
    WebkitAppearance: 'none',
    background: colors.inputBg,
    border: `1px solid ${colors.border}`,
    borderRadius: '8px',
    padding: '9px 36px 9px 12px',
    color: selectedLayout ? colors.text : colors.muted,
    fontSize: '13px',
    fontFamily: colors.font,
    cursor: 'pointer',
    outline: 'none',
    transition: 'border-color 0.15s, background 0.3s, color 0.3s',
  };

  const optionBg = isDark ? '#0d1120' : '#f0f4f8';
  const optionColor = isDark ? '#e0e6ed' : '#1a2a3a';

  return (
    <div style={{ padding: '12px' }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginBottom: '14px',
        fontFamily: colors.font,
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={colors.accent} strokeWidth="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
        <span style={{
          color: colors.text,
          fontSize: '13px',
          fontWeight: 600,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
        }}>Layout Loader</span>
      </div>

      {layouts.length > 0 ? (
        <div>
          <label style={{
            color: colors.muted,
            fontSize: '11px',
            letterSpacing: '0.04em',
            marginBottom: '6px',
            display: 'block',
            fontFamily: colors.font,
          }}>Select a layout</label>
          <div style={{ position: 'relative', marginBottom: '14px' }}>
            <select
              style={selectStyle}
              value={selectedLayout ?? ''}
              onChange={handleSelectChange}
            >
              <option value="" disabled style={{ background: optionBg, color: colors.muted }}>
                Choose a layout...
              </option>
              {Object.entries(grouped).map(([category, items]) => (
                <optgroup key={category} label={category} style={{ background: optionBg, color: colors.muted }}>
                  {items.map(layout => (
                    <option
                      key={layout.name}
                      value={layout.name}
                      style={{ background: optionBg, color: optionColor }}
                    >
                      {layout.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <span style={{
              position: 'absolute',
              right: '10px',
              top: '50%',
              transform: 'translateY(-50%)',
              pointerEvents: 'none',
            }}>
              <ChevronIcon color={colors.muted} />
            </span>
          </div>

          {selectedLayout && (
            <div style={{
              padding: '6px 10px',
              borderRadius: '6px',
              background: colors.accentDim,
              border: `1px solid ${colors.border}`,
              color: colors.accent,
              fontSize: '11px',
              fontFamily: '"SF Mono", "Fira Code", monospace',
              marginBottom: '14px',
            }}>
              {layouts.find(l => l.name === selectedLayout)?.path ?? selectedLayout}
            </div>
          )}
        </div>
      ) : (
        <div style={{
          color: colors.muted,
          fontSize: '12px',
          marginBottom: '14px',
          fontFamily: colors.font,
        }}>
          No layouts found on server.
        </div>
      )}

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        margin: '12px 0',
        fontFamily: colors.font,
      }}>
        <div style={{ flex: 1, height: '1px', background: colors.border }} />
        <span style={{ color: colors.muted, fontSize: '10px', letterSpacing: '0.06em', textTransform: 'uppercase', flexShrink: 0 }}>
          or upload
        </span>
        <div style={{ flex: 1, height: '1px', background: colors.border }} />
      </div>

      <LayoutDropzone onUpload={onUpload} />
    </div>
  );
};

export default React.memo(LayoutLoader);
