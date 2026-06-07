import React, { useState, useRef, useCallback } from 'react'
import { useTheme } from './ThemeToggle'

export interface FloatingPanelProps {
  id: string
  title: string
  icon?: React.ReactNode
  defaultPosition: { x: number; y: number }
  defaultSize?: { width: number; height?: number }
  minimizable?: boolean
  draggable?: boolean
  children: React.ReactNode
  visible?: boolean
  zIndex?: number
  onFocus?: () => void
  maxHeight?: number
}

export default function FloatingPanel({
  id,
  title,
  icon,
  defaultPosition,
  defaultSize,
  minimizable = true,
  draggable = true,
  children,
  visible = true,
  zIndex = 100,
  onFocus,
  maxHeight,
}: FloatingPanelProps) {
  const { colors, theme } = useTheme()
  const isDark = theme === 'dark'
  const [position, setPosition] = useState(defaultPosition)
  const [minimized, setMinimized] = useState(false)
  const dragRef = useRef<{ startX: number; startY: number; startPosX: number; startPosY: number } | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (!draggable) {
      onFocus?.()
      return
    }
    e.preventDefault()
    e.stopPropagation()
    onFocus?.()
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      startPosX: position.x,
      startPosY: position.y,
    }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }, [position, onFocus, draggable])

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    const newX = Math.max(0, Math.min(window.innerWidth - 100, dragRef.current.startPosX + dx))
    const newY = Math.max(0, Math.min(window.innerHeight - 40, dragRef.current.startPosY + dy))
    setPosition({ x: newX, y: newY })
  }, [])

  const handlePointerUp = useCallback(() => {
    dragRef.current = null
  }, [])

  if (!visible) return null

  const width = defaultSize?.width ?? 280

  // Minimized pill
  if (minimized) {
    return (
      <div
        style={{
          position: 'fixed',
          left: position.x,
          top: position.y,
          zIndex,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 12px',
          background: isDark ? 'rgba(18, 19, 26, 0.94)' : 'rgba(245, 245, 247, 0.95)',
          border: `1px solid ${colors.border}`,
          borderRadius: 10,
          cursor: 'pointer',
          color: colors.muted,
          fontSize: 11,
          fontWeight: 500,
          fontFamily: colors.font,
          transition: 'background 0.2s, border-color 0.2s',
          userSelect: 'none',
        }}
        onClick={() => setMinimized(false)}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        {icon}
        <span>{title}</span>
      </div>
    )
  }

  // Full panel
  return (
    <div
      ref={panelRef}
      style={{
        position: 'fixed',
        left: position.x,
        top: position.y,
        width,
        height: defaultSize?.height,
        maxHeight: maxHeight ?? 'calc(100vh - 80px)',
        zIndex,
        display: 'flex',
        flexDirection: 'column',
        background: isDark ? 'rgba(18, 19, 26, 0.94)' : 'rgba(245, 245, 247, 0.95)',
        border: `1px solid ${colors.border}`,
        borderRadius: 14,
        boxShadow: isDark
          ? '0 8px 32px rgba(0,0,0,0.4), 0 0 1px rgba(139,92,246,0.08)'
          : '0 4px 16px rgba(0,0,0,0.08)',
        overflow: 'hidden',
        fontFamily: colors.font,
        transition: 'background 0.3s, border-color 0.3s, box-shadow 0.3s',
      }}
      onPointerDown={() => onFocus?.()}
    >
      {/* Header bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 12px',
          flexShrink: 0,
          cursor: draggable ? 'grab' : 'default',
          userSelect: 'none',
          borderBottom: `1px solid ${colors.border}`,
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 11,
          fontWeight: 600,
          color: colors.muted,
          letterSpacing: '0.03em',
          textTransform: 'uppercase',
        }}>
          {icon}
          {title}
        </div>
        {minimizable && (
          <button
            onClick={(e) => { e.stopPropagation(); setMinimized(true) }}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 18,
              height: 18,
              borderRadius: 4,
              border: 'none',
              background: 'transparent',
              color: colors.muted,
              cursor: 'pointer',
              padding: 0,
              fontSize: 14,
              lineHeight: 1,
            }}
            title="Minimize"
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
        )}
      </div>

      {/* Content */}
      <div style={{
        flex: 1,
        minHeight: 0,
        overflow: 'auto',
      }}>
        {children}
      </div>
    </div>
  )
}
