import React, { useState, useMemo, useRef, useEffect, useCallback, useLayoutEffect } from 'react';
import { useTheme } from '../common/ThemeToggle';
import type { VersionInfo } from '../../hooks/useLayoutState';

export interface VersionHistoryProps {
  versions: VersionInfo[];
  selectedVersionId: string | null;
  layoutName: string | null;
  onSelect: (versionId: string, file: string | null) => void;
  onDeleted: (deletedId: string) => void;
  disabled?: boolean;
}

const TrashIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
);

const VersionHistory: React.FC<VersionHistoryProps> = ({
  versions,
  selectedVersionId,
  layoutName,
  onSelect,
  onDeleted,
  disabled = false,
}) => {
  const { colors, theme } = useTheme();
  const isDark = theme === 'dark';
  const [open, setOpen] = useState(false);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [dropdownRect, setDropdownRect] = useState<DOMRect | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const selectedIndex = useMemo(() => {
    const i = versions.findIndex(v => v.id === selectedVersionId);
    return i >= 0 ? i : Math.max(0, versions.length - 1);
  }, [versions, selectedVersionId]);

  const current = versions[selectedIndex];
  const total = versions.length;

  // Measure trigger button position so the fixed dropdown lands correctly.
  useLayoutEffect(() => {
    if (open && triggerRef.current) {
      setDropdownRect(triggerRef.current.getBoundingClientRect());
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      const inTrigger = triggerRef.current?.contains(target);
      const inDropdown = dropdownRef.current?.contains(target);
      if (!inTrigger && !inDropdown) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleDelete = useCallback(async (v: VersionInfo) => {
    if (!layoutName || !v.file) return;
    console.log('[VersionHistory] deleting', layoutName, v.file);
    try {
      const res = await fetch(
        `/api/layouts/${encodeURIComponent(layoutName)}/versions/${encodeURIComponent(v.file)}`,
        { method: 'DELETE' },
      );
      console.log('[VersionHistory] DELETE status', res.status);
      if (res.ok) onDeleted(v.id);
    } catch (err) { console.error('[VersionHistory] DELETE error', err); }
  }, [layoutName, onDeleted]);

  if (total === 0) {
    return (
      <div style={{ padding: '8px 12px', fontSize: 10, color: colors.muted, fontFamily: colors.font }}>
        No versions yet.
      </div>
    );
  }

  const handleSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = versions[Number(e.target.value)];
    if (v) { onSelect(v.id, v.file); setOpen(false); }
  };

  const labelText = !current ? '—'
    : current.kind === 'original' ? 'Original'
    : current.label;

  const isLatestSelected = current?.kind === 'version' && selectedIndex === total - 1;

  return (
    <div style={{ padding: '8px 12px 10px', position: 'relative' }}>

      {/* Slider */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 9, color: colors.muted, fontFamily: colors.font, flexShrink: 0 }}>
          {selectedIndex + 1}/{total}
        </span>
        <input
          type="range"
          min={0}
          max={Math.max(0, total - 1)}
          step={1}
          value={selectedIndex}
          onChange={handleSlider}
          disabled={disabled || total === 1}
          style={{
            flex: 1,
            accentColor: colors.accent,
            cursor: disabled || total === 1 ? 'not-allowed' : 'pointer',
            opacity: total === 1 ? 0.5 : 1,
          }}
        />
      </div>

      {/* Current version label + dropdown toggle */}
      <button
        ref={triggerRef}
        onClick={() => !disabled && setOpen(o => !o)}
        disabled={disabled}
        style={{
          width: '100%',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6,
          padding: '5px 8px', borderRadius: 6,
          border: `1px solid ${open ? colors.accent + '66' : colors.border}`,
          background: open ? colors.accent + '14' : (isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)'),
          color: colors.text, cursor: disabled ? 'not-allowed' : 'pointer',
          fontFamily: colors.font, fontSize: 11, textAlign: 'left',
          transition: 'border-color 0.15s, background 0.15s',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
            background: isLatestSelected ? colors.success : colors.accent,
          }} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {labelText}
          </span>
          {isLatestSelected && (
            <span style={{
              flexShrink: 0, fontSize: 8, fontWeight: 700, padding: '1px 4px',
              borderRadius: 3, background: colors.success + '22', color: colors.success,
              letterSpacing: '0.05em', textTransform: 'uppercase',
            }}>latest</span>
          )}
        </span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
          stroke={colors.muted} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          style={{ flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Floating dropdown — position:fixed escapes any ancestor overflow:hidden */}
      {open && dropdownRect && (
        <div
          ref={dropdownRef}
          style={{
            position: 'fixed',
            top: dropdownRect.bottom + 4,
            left: dropdownRect.left,
            width: dropdownRect.width,
            zIndex: 2000,
            borderRadius: 8, border: `1px solid ${colors.accent}44`,
            background: isDark ? 'rgba(15,9,32,0.97)' : 'rgba(248,249,251,0.98)',
            backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
            boxShadow: isDark
              ? '0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px rgba(139,92,246,0.12)'
              : '0 8px 32px rgba(0,0,0,0.14)',
            overflowY: 'auto', maxHeight: 220,
          }}
        >
          {versions.slice().reverse().map((v, ri) => {
            const active = v.id === selectedVersionId;
            const isLatest = v.kind === 'version' && v.id === versions[total - 1].id;
            const origIndex = total - 1 - ri;
            const hovered = hoveredId === v.id;
            const canDelete = v.kind === 'version';

            return (
              <div
                key={v.id}
                onMouseEnter={() => setHoveredId(v.id)}
                onMouseLeave={() => setHoveredId(null)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 0,
                  borderBottom: `1px solid ${colors.border}33`,
                  background: active
                    ? colors.accent + '18'
                    : hovered
                    ? (isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)')
                    : 'transparent',
                  transition: 'background 0.1s',
                }}
              >
                {/* Clickable area (select version) */}
                <button
                  onClick={() => { onSelect(v.id, v.file); setOpen(false); }}
                  style={{
                    flex: 1, display: 'flex', alignItems: 'center', gap: 8,
                    padding: '7px 10px', border: 'none', background: 'transparent',
                    color: active ? colors.accent : colors.text,
                    cursor: 'pointer', fontFamily: colors.font, fontSize: 11, textAlign: 'left',
                  }}
                >
                  <span style={{
                    fontSize: 9, color: colors.muted, flexShrink: 0,
                    fontFamily: colors.font, minWidth: 18, textAlign: 'right',
                  }}>
                    {origIndex + 1}
                  </span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {v.kind === 'original' ? 'Original' : v.label}
                  </span>
                  {isLatest && (
                    <span style={{
                      flexShrink: 0, fontSize: 8, fontWeight: 700, padding: '1px 4px',
                      borderRadius: 3, background: colors.success + '22', color: colors.success,
                      letterSpacing: '0.05em', textTransform: 'uppercase',
                    }}>latest</span>
                  )}
                  {active && (
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none"
                      stroke={colors.accent} strokeWidth="3" strokeLinecap="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </button>

                {/* Delete button — always in DOM, fades in on row hover */}
                {canDelete && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      handleDelete(v);
                    }}
                    title="Delete this version"
                    style={{
                      flexShrink: 0,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      width: 24, height: 24, marginRight: 6, borderRadius: 4,
                      border: `1px solid ${hovered ? colors.error + '55' : 'transparent'}`,
                      background: 'transparent',
                      color: hovered ? colors.error : 'transparent',
                      cursor: 'pointer',
                      opacity: hovered ? 1 : 0,
                      transition: 'opacity 0.15s, color 0.15s, border-color 0.15s',
                      padding: 0,
                      // Always keep pointer-events on so mouse entering the button
                      // doesn't drop the parent hover state before the click fires.
                      pointerEvents: 'auto',
                    }}
                  >
                    <TrashIcon />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default React.memo(VersionHistory);
