import React, { useMemo, useState, useRef, useCallback, useEffect } from 'react'
import { useTheme } from '../common/ThemeToggle'
import { LayoutJSON } from '../../types'
import type { NodeLinkData } from '../GraphPanel/graphDataMapper'

interface SelectionPanelProps {
  selectedId: string | null
  layout: LayoutJSON
  graphData: NodeLinkData | null
  onClose: () => void
  clickPosition?: { x: number; y: number } | null
}

interface ElementInfo {
  id: string
  name: string
  type: string
  description: string
  properties: Record<string, string>
  connections: { name: string; type: string; edgeType: string }[]
}

const TYPE_DESCRIPTIONS: Record<string, string> = {
  room: 'Enclosed space defined by walls and accessible through doors.',
  door: 'Opening element connecting two adjacent spaces.',
  window: 'Wall opening for natural light and ventilation.',
  furniture: 'Placed object with clearance and orientation requirements.',
  mep: 'Mechanical, Electrical, or Plumbing system element.',
  structure: 'Structural wall or boundary element.',
}

function findElement(layout: LayoutJSON, id: string): ElementInfo | null {
  // Search all layers
  for (const room of layout.rooms) {
    if (room.id === id) {
      return {
        id, name: room.name, type: 'room',
        description: TYPE_DESCRIPTIONS.room,
        properties: {
          'Area': `${room.attributes.area?.toFixed?.(1) ?? room.attributes.area} m2`,
          'Vertices': `${room.geometry.length}`,
        },
        connections: [],
      }
    }
  }
  for (const door of layout.doors) {
    if (door.id === id) {
      return {
        id, name: door.name, type: 'door',
        description: TYPE_DESCRIPTIONS.door,
        properties: {
          'Type': door.type,
          'Connects': (door.attributes.connectsRooms || []).join(', '),
        },
        connections: [],
      }
    }
  }
  for (const win of layout.windows) {
    if (win.id === id) {
      return {
        id, name: win.name, type: 'window',
        description: TYPE_DESCRIPTIONS.window,
        properties: {
          'Type': win.type,
          'Room': win.attributes.roomId || '-',
        },
        connections: [],
      }
    }
  }
  for (const item of layout.furniture) {
    if (item.id === id) {
      const props: Record<string, string> = {}
      if (item.attributes.roomId) props['Room'] = item.attributes.roomId
      if (item.attributes.height) props['Height'] = `${item.attributes.height}m`
      const [cx, cy] = item.geometry.reduce(
        (acc, [x, y]) => [acc[0] + x / item.geometry.length, acc[1] + y / item.geometry.length],
        [0, 0]
      )
      props['Position'] = `(${cx.toFixed(1)}, ${cy.toFixed(1)})`
      return {
        id, name: item.name, type: 'furniture',
        description: TYPE_DESCRIPTIONS.furniture,
        properties: props,
        connections: [],
      }
    }
  }
  for (const item of layout.mep) {
    if (item.id === id) {
      const props: Record<string, string> = {}
      if (item.attributes.system) props['System'] = item.attributes.system
      if (item.attributes.height) props['Height'] = `${item.attributes.height}m`
      return {
        id, name: item.name, type: 'mep',
        description: TYPE_DESCRIPTIONS.mep,
        properties: props,
        connections: [],
      }
    }
  }
  for (const item of layout.structure) {
    if (item.id === id) {
      return {
        id, name: item.name, type: 'structure',
        description: TYPE_DESCRIPTIONS.structure,
        properties: {
          'Material': item.attributes.material || '-',
        },
        connections: [],
      }
    }
  }
  return null
}

const TYPE_COLORS: Record<string, string> = {
  room: '#3D3270',
  door: '#D4976A',
  window: '#8B5CF6',
  furniture: '#7C6FAA',
  mep: '#34D399',
  structure: '#2A2838',
}

export default function SelectionPanel({ selectedId, layout, graphData, onClose, clickPosition }: SelectionPanelProps) {
  const { colors, theme } = useTheme()
  const isDark = theme === 'dark'
  const PANEL_W = 260
  const PANEL_H = 320
  const [position, setPosition] = useState({ x: 300, y: 200 })
  const dragRef = useRef<{ startX: number; startY: number; startPosX: number; startPosY: number } | null>(null)

  // Position panel near clicked element when selection changes
  useEffect(() => {
    if (clickPosition && selectedId) {
      const pw = window.innerWidth
      const ph = window.innerHeight
      let px = clickPosition.x + 20
      let py = clickPosition.y - 40
      if (px + PANEL_W > pw) px = clickPosition.x - PANEL_W - 20
      if (py + PANEL_H > ph) py = ph - PANEL_H - 16
      if (py < 16) py = 16
      if (px < 16) px = 16
      setPosition({ x: px, y: py })
    }
  }, [selectedId, clickPosition])

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      startPosX: position.x,
      startPosY: position.y,
    }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }, [position])

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    setPosition({
      x: Math.max(0, Math.min(window.innerWidth - 100, dragRef.current.startPosX + dx)),
      y: Math.max(0, Math.min(window.innerHeight - 40, dragRef.current.startPosY + dy)),
    })
  }, [])

  const handlePointerUp = useCallback(() => {
    dragRef.current = null
  }, [])

  const info = useMemo(() => {
    if (!selectedId) return null
    const el = findElement(layout, selectedId)
    if (!el) return null

    // Add graph connections
    if (graphData) {
      const links = graphData.links || []
      for (const link of links) {
        const src = link.source
        const tgt = link.target
        if (src === selectedId || tgt === selectedId) {
          const otherId = src === selectedId ? tgt : src
          // Find the other element's name
          const otherNode = graphData.nodes.find(n => n.id === otherId)
          el.connections.push({
            name: otherNode?.name || otherId,
            type: otherNode?.ntype || 'unknown',
            edgeType: link.etype || 'connected',
          })
        }
      }
      // Limit to 8 connections
      if (el.connections.length > 8) {
        const total = el.connections.length
        el.connections = el.connections.slice(0, 8)
        el.connections.push({ name: `+${total - 8} more`, type: '', edgeType: '' })
      }
    }

    return el
  }, [selectedId, layout, graphData])

  if (!info) return null

  const typeColor = TYPE_COLORS[info.type] || colors.accent

  return (
    <div style={{
      position: 'absolute',
      top: position.y,
      left: position.x,
      width: 260,
      background: isDark ? 'rgba(18, 19, 26, 0.94)' : 'rgba(245, 245, 247, 0.95)',
      border: `1px solid ${colors.border}`,
      borderRadius: 12,
      overflow: 'hidden',
      zIndex: 20,
      fontFamily: colors.font,
      transition: 'background 0.3s, border-color 0.3s',
    }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 14px',
          borderBottom: `1px solid ${colors.border}`,
          cursor: 'grab',
          userSelect: 'none',
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
          <span style={{
            fontSize: 9,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            padding: '2px 7px',
            borderRadius: 5,
            background: typeColor + '22',
            color: typeColor,
          }}>
            {info.type}
          </span>
          <span style={{
            fontSize: 12,
            fontWeight: 600,
            color: colors.text,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}>
            {info.name}
          </span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: colors.muted,
            cursor: 'pointer',
            fontSize: 13,
            padding: '2px 6px',
            borderRadius: 4,
          }}
        >
          {'\u2715'}
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: '10px 14px 14px', maxHeight: 280, overflowY: 'auto' }}>
        {/* Description */}
        <div style={{ fontSize: 10, color: colors.muted, lineHeight: 1.5, marginBottom: 10 }}>
          {info.description}
        </div>

        {/* Properties */}
        {Object.keys(info.properties).length > 0 && (
          <>
            <div style={{
              fontSize: 9, fontWeight: 600, letterSpacing: '0.08em',
              textTransform: 'uppercase', color: colors.muted, marginBottom: 6,
            }}>
              Properties
            </div>
            {Object.entries(info.properties).map(([key, val]) => (
              <div key={key} style={{
                display: 'flex', justifyContent: 'space-between', marginBottom: 3,
              }}>
                <span style={{ fontSize: 10, color: colors.muted }}>{key}</span>
                <span style={{ fontSize: 10, color: colors.text }}>{val}</span>
              </div>
            ))}
          </>
        )}

        {/* Connections */}
        {info.connections.length > 0 && (
          <>
            <div style={{
              height: 1, background: colors.border, margin: '10px 0',
            }} />
            <div style={{
              fontSize: 9, fontWeight: 600, letterSpacing: '0.08em',
              textTransform: 'uppercase', color: colors.muted, marginBottom: 6,
            }}>
              Connections ({info.connections.length})
            </div>
            {info.connections.map((conn, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '3px 0',
                borderBottom: i < info.connections.length - 1 ? `1px solid ${colors.border}` : 'none',
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                  background: TYPE_COLORS[conn.type] || colors.muted,
                }} />
                <span style={{ flex: 1, fontSize: 10, color: colors.text }}>
                  {conn.name}
                </span>
                <span style={{ fontSize: 9, color: TYPE_COLORS[conn.type] || colors.muted }}>
                  {conn.edgeType}
                </span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
