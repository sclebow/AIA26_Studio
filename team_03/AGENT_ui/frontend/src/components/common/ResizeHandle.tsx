import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTheme } from './ThemeToggle';

// ─── Types ────────────────────────────────────────────────────────────────────

type Orientation = 'vertical' | 'horizontal';

interface ResizeHandleProps {
  orientation: Orientation;
  /** Called continuously during drag with the new pixel size for the leading panel */
  onResize: (newSize: number) => void;
  /**
   * A ref attached to the element whose dimension we are controlling.
   * The handle queries its current size as the drag baseline.
   */
  panelRef: React.RefObject<HTMLElement | null>;
}

// ─── Component ────────────────────────────────────────────────────────────────

const ResizeHandle: React.FC<ResizeHandleProps> = ({ orientation, onResize, panelRef }) => {
  const { colors } = useTheme();
  const [hovered, setHovered] = useState(false);
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef<{ pos: number; size: number } | null>(null);

  const isVertical = orientation === 'vertical';

  // ── Drag start ──────────────────────────────────────────────────────────────
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const panel = panelRef.current;
      if (!panel) return;

      const rect = panel.getBoundingClientRect();
      const currentSize = isVertical ? rect.width : rect.height;

      dragStart.current = {
        pos: isVertical ? e.clientX : e.clientY,
        size: currentSize,
      };
      setDragging(true);
    },
    [isVertical, panelRef],
  );

  // ── Drag move / end — attached to window so cursor can leave the handle ─────
  useEffect(() => {
    if (!dragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!dragStart.current) return;
      const delta = (isVertical ? e.clientX : e.clientY) - dragStart.current.pos;
      const newSize = Math.max(24, dragStart.current.size + delta);
      onResize(newSize);
    };

    const handleMouseUp = () => {
      setDragging(false);
      dragStart.current = null;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [dragging, isVertical, onResize]);

  // ── Styles ──────────────────────────────────────────────────────────────────

  const active = hovered || dragging;

  const barStyle: React.CSSProperties = isVertical
    ? {
        width: 4,
        minWidth: 4,
        height: '100%',
        cursor: 'col-resize',
        flexShrink: 0,
        position: 'relative',
        background: active ? colors.accent : colors.border,
        transition: 'background 0.15s ease',
        zIndex: 10,
        userSelect: 'none',
      }
    : {
        height: 4,
        minHeight: 4,
        width: '100%',
        cursor: 'row-resize',
        flexShrink: 0,
        position: 'relative',
        background: active ? colors.accent : colors.border,
        transition: 'background 0.15s ease',
        zIndex: 10,
        userSelect: 'none',
      };

  // Subtle centre line (lighter stripe) — purely decorative
  const lineStyle: React.CSSProperties = isVertical
    ? {
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 1,
        height: 32,
        borderRadius: 1,
        background: active ? colors.accent : colors.muted,
        opacity: active ? 0.9 : 0.4,
        transition: 'background 0.15s ease, opacity 0.15s ease',
        pointerEvents: 'none',
      }
    : {
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        height: 1,
        width: 32,
        borderRadius: 1,
        background: active ? colors.accent : colors.muted,
        opacity: active ? 0.9 : 0.4,
        transition: 'background 0.15s ease, opacity 0.15s ease',
        pointerEvents: 'none',
      };

  return (
    <div
      style={barStyle}
      onMouseDown={handleMouseDown}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div style={lineStyle} />
    </div>
  );
};

export default ResizeHandle;
