import React, { useMemo } from 'react'
import { useTheme } from '../common/ThemeToggle'
import { LayoutJSON } from '../../types'
import type { NodeLinkData } from '../GraphPanel/graphDataMapper'

interface SelectionPanelProps {
  selectedId: string | null
  layout: LayoutJSON | null
  graphData: NodeLinkData | null
  onClose: () => void
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
  for (const room of layout.rooms) {
    if (room.id === id) return { id, name: room.name, type: 'room', description: TYPE_DESCRIPTIONS.room, properties: { 'Area': `${room.attributes.area?.toFixed?.(1) ?? room.attributes.area} m²`, 'Vertices': `${room.geometry.length}` }, connections: [] }
  }
  for (const door of layout.doors) {
    if (door.id === id) return { id, name: door.name, type: 'door', description: TYPE_DESCRIPTIONS.door, properties: { 'Type': door.type, 'Connects': (door.attributes.connectsRooms || []).join(', ') }, connections: [] }
  }
  for (const win of layout.windows) {
    if (win.id === id) return { id, name: win.name, type: 'window', description: TYPE_DESCRIPTIONS.window, properties: { 'Type': win.type, 'Room': win.attributes.roomId || '-' }, connections: [] }
  }
  for (const item of layout.furniture) {
    if (item.id === id) {
      const props: Record<string, string> = {}
      if (item.attributes.roomId) props['Room'] = item.attributes.roomId
      if (item.attributes.height) props['Height'] = `${item.attributes.height}m`
      const [cx, cy] = item.geometry.reduce((acc, [x, y]) => [acc[0] + x / item.geometry.length, acc[1] + y / item.geometry.length], [0, 0])
      props['Position'] = `(${cx.toFixed(1)}, ${cy.toFixed(1)})`
      return { id, name: item.name, type: 'furniture', description: TYPE_DESCRIPTIONS.furniture, properties: props, connections: [] }
    }
  }
  for (const item of layout.mep) {
    if (item.id === id) {
      const props: Record<string, string> = {}
      if (item.attributes.system) props['System'] = item.attributes.system
      if (item.attributes.height) props['Height'] = `${item.attributes.height}m`
      return { id, name: item.name, type: 'mep', description: TYPE_DESCRIPTIONS.mep, properties: props, connections: [] }
    }
  }
  for (const item of layout.structure) {
    if (item.id === id) return { id, name: item.name, type: 'structure', description: TYPE_DESCRIPTIONS.structure, properties: { 'Material': item.attributes.material || '-' }, connections: [] }
  }
  return null
}

const TYPE_COLORS: Record<string, string> = {
  room: '#3D3270', door: '#D4976A', window: '#8B5CF6',
  furniture: '#7C6FAA', mep: '#34D399', structure: '#2A2838',
}

export default function SelectionPanel({ selectedId, layout, graphData, onClose }: SelectionPanelProps) {
  const { colors, theme } = useTheme()
  const isDark = theme === 'dark'

  const info = useMemo(() => {
    if (!selectedId || !layout) return null
    const el = findElement(layout, selectedId)
    if (!el) return null
    if (graphData) {
      const links = graphData.links || []
      for (const link of links) {
        const src = link.source, tgt = link.target
        if (src === selectedId || tgt === selectedId) {
          const otherId = src === selectedId ? tgt : src
          const otherNode = graphData.nodes.find(n => n.id === otherId)
          el.connections.push({ name: otherNode?.name || otherId, type: otherNode?.ntype || 'unknown', edgeType: link.etype || 'connected' })
        }
      }
      if (el.connections.length > 6) {
        const total = el.connections.length
        el.connections = el.connections.slice(0, 6)
        el.connections.push({ name: `+${total - 6} more`, type: '', edgeType: '' })
      }
    }
    return el
  }, [selectedId, layout, graphData])

  const typeColor = info ? (TYPE_COLORS[info.type] || colors.accent) : colors.muted

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header — matches App's sectionHeaderStyle (same size/font as Layers/Pipeline) */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '7px 12px', borderBottom: `1px solid ${colors.border}`,
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
          {info && (
            <span style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
              padding: '2px 6px', borderRadius: 4, background: typeColor + '22', color: typeColor,
            }}>
              {info.type}
            </span>
          )}
          <span style={{
            fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase',
            fontFamily: colors.fontHeading, color: colors.muted,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {info ? info.name : 'Properties'}
          </span>
        </div>
        {info && (
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: colors.muted,
            cursor: 'pointer', fontSize: 12, padding: '2px 4px', borderRadius: 4,
          }}>✕</button>
        )}
      </div>

      {/* Body */}
      {info ? (
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 12px' }}>
          <div style={{ fontSize: 10, color: colors.muted, lineHeight: 1.5, marginBottom: 8 }}>
            {info.description}
          </div>
          {Object.keys(info.properties).length > 0 && (
            <>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: colors.muted, marginBottom: 5 }}>
                Properties
              </div>
              {Object.entries(info.properties).map(([key, val]) => (
                <div key={key} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                  <span style={{ fontSize: 10, color: colors.muted }}>{key}</span>
                  <span style={{ fontSize: 10, color: colors.text }}>{val}</span>
                </div>
              ))}
            </>
          )}
          {info.connections.length > 0 && (
            <>
              <div style={{ height: 1, background: colors.border, margin: '8px 0' }} />
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: colors.muted, marginBottom: 5 }}>
                Connections ({info.connections.length})
              </div>
              {info.connections.map((conn, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', borderBottom: i < info.connections.length - 1 ? `1px solid ${colors.border}` : 'none' }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', flexShrink: 0, background: TYPE_COLORS[conn.type] || colors.muted }} />
                  <span style={{ flex: 1, fontSize: 10, color: colors.text }}>{conn.name}</span>
                  <span style={{ fontSize: 10, color: TYPE_COLORS[conn.type] || colors.muted }}>{conn.edgeType}</span>
                </div>
              ))}
            </>
          )}
        </div>
      ) : (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8 }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={colors.border} strokeWidth="1.5">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
          </svg>
          <span style={{ fontSize: 10, color: colors.muted, textAlign: 'center', lineHeight: 1.4 }}>
            Click an object<br />to see its properties
          </span>
        </div>
      )}
    </div>
  )
}
