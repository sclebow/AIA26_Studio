import React, { useMemo } from 'react'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { LayoutJSON } from '../../types'

interface Labels3DProps {
  layout: LayoutJSON
  isDark: boolean
  center: { x: number; z: number }
}

interface LabelItem {
  id: string
  name: string
  type: string
  position: [number, number, number]
}

function computeCenter(geometry: [number, number][]): [number, number] {
  let sx = 0, sy = 0
  for (const [x, y] of geometry) { sx += x; sy += y }
  return [sx / geometry.length, sy / geometry.length]
}

function getHeight(name: string, type: string): number {
  if (type === 'room') return 0.3
  if (type === 'door') return 2.5
  if (type === 'window') return 2.2
  if (type === 'structure') return 3.2
  // Furniture/MEP: use a height above the element
  const lower = name.toLowerCase()
  if (lower.includes('shelf') || lower.includes('rack')) return 2.0
  if (lower.includes('machine') || lower.includes('cnc')) return 1.5
  if (lower.includes('conveyor')) return 1.1
  if (lower.includes('panel')) return 2.2
  return 1.3
}

export default function Labels3D({ layout, isDark, center }: Labels3DProps) {
  const labels = useMemo(() => {
    const items: LabelItem[] = []

    // Rooms
    for (const room of layout.rooms) {
      const [cx, cy] = computeCenter(room.geometry)
      items.push({ id: room.id, name: room.name, type: 'room', position: [cx - center.x, 0.3, cy - center.z] })
    }

    // Doors
    for (const door of layout.doors) {
      const [p1, p2] = door.geometry
      const cx = (p1[0] + p2[0]) / 2
      const cy = (p1[1] + p2[1]) / 2
      items.push({ id: door.id, name: door.name, type: 'door', position: [cx - center.x, 2.5, cy - center.z] })
    }

    // Furniture
    for (const item of layout.furniture) {
      const [cx, cy] = computeCenter(item.geometry)
      const h = getHeight(item.name, 'furniture')
      items.push({ id: item.id, name: item.name, type: 'furniture', position: [cx - center.x, h, cy - center.z] })
    }

    // MEP
    for (const item of layout.mep) {
      const [cx, cy] = computeCenter(item.geometry)
      const h = getHeight(item.name, 'mep')
      items.push({ id: item.id, name: item.name, type: 'mep', position: [cx - center.x, h, cy - center.z] })
    }

    return items
  }, [layout, center])

  const typeColors: Record<string, string> = {
    room: isDark ? '#B5A898' : '#8a7e72',
    door: isDark ? '#C4896E' : '#a06848',
    furniture: isDark ? '#9888AD' : '#7a6890',
    mep: isDark ? '#7EA68B' : '#5a8068',
    structure: isDark ? '#8B8F96' : '#686c72',
    window: isDark ? '#7A9DB8' : '#5a7a92',
  }

  return (
    <group>
      {labels.map(label => (
        <Html
          key={label.id}
          position={label.position}
          center
          sprite
          transform
          scale={0.4}
          style={{ pointerEvents: 'none' }}
        >
          <div style={{
            background: isDark ? 'rgba(22,24,32,0.82)' : 'rgba(255,255,255,0.88)',
            color: typeColors[label.type] || (isDark ? '#aabbcc' : '#334455'),
            padding: '2px 6px',
            borderRadius: 4,
            fontSize: 9,
            fontWeight: 500,
            fontFamily: '-apple-system, system-ui, sans-serif',
            whiteSpace: 'nowrap',
            letterSpacing: '0.02em',
            border: `1px solid ${isDark ? 'rgba(120,130,150,0.20)' : 'rgba(100,110,130,0.15)'}`,
            maxWidth: 120,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            userSelect: 'none',
          }}>
            {label.name}
          </div>
        </Html>
      ))}
    </group>
  )
}
