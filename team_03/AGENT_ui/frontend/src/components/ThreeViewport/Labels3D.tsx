import React, { useMemo, useRef, useState } from 'react'
import { Html } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { LayoutJSON } from '../../types'

interface Labels3DProps {
  layout: LayoutJSON
  isDark: boolean
  center: { x: number; z: number }
  bgOpacity?: number
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

export default function Labels3D({ layout, isDark, center, bgOpacity = 0.75 }: Labels3DProps) {
  const labels = useMemo(() => {
    const items: LabelItem[] = []

    // Rooms
    for (const room of layout.rooms) {
      const [cx, cy] = computeCenter(room.geometry)
      items.push({ id: room.id, name: room.name, type: 'room', position: [cx - center.x, 0.6, cy - center.z] })
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

  // Geometry size — drives the zoom threshold for swapping label sets.
  const maxDim = useMemo(() => {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const [x, y] of layout.outline) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x)
      minY = Math.min(minY, y); maxY = Math.max(maxY, y)
    }
    return Math.max(maxX - minX, maxY - minY) || 1
  }, [layout])

  // Zoom-driven label swap: far away → only room titles; close in → only
  // element tags. A hysteresis band (near/far) prevents flicker at the edge.
  const [showElements, setShowElements] = useState(false)
  const showElementsRef = useRef(false)
  const controls = useThree(s => s.controls) as { target: THREE.Vector3 } | null
  const tmpTarget = useRef(new THREE.Vector3())

  useFrame(({ camera }) => {
    const target = controls?.target ?? tmpTarget.current
    // Visible world height — zoom-agnostic, works for both ortho (wheel changes
    // camera.zoom) and perspective (wheel changes distance).
    let visH: number
    const ortho = camera as THREE.OrthographicCamera
    if (ortho.isOrthographicCamera) {
      visH = (ortho.top - ortho.bottom) / ortho.zoom
    } else {
      const persp = camera as THREE.PerspectiveCamera
      const dist = camera.position.distanceTo(target)
      visH = 2 * dist * Math.tan((persp.fov * Math.PI / 180) / 2)
    }
    const near = maxDim * 0.72   // less of the scene visible than this → element tags
    const far = maxDim * 0.92    // more visible than this → room titles
    if (!showElementsRef.current && visH < near) {
      showElementsRef.current = true; setShowElements(true)
    } else if (showElementsRef.current && visH > far) {
      showElementsRef.current = false; setShowElements(false)
    }
  })

  const typeColors: Record<string, string> = {
    room: isDark ? '#B5A898' : '#8a7e72',
    door: isDark ? '#C4896E' : '#a06848',
    furniture: isDark ? '#9888AD' : '#7a6890',
    mep: isDark ? '#7EA68B' : '#5a8068',
    structure: isDark ? '#8B8F96' : '#686c72',
    window: isDark ? '#7A9DB8' : '#5a7a92',
  }

  const roomLabels = labels.filter(l => l.type === 'room')
  const elementLabels = labels.filter(l => l.type !== 'room')

  return (
    <group>
      {/* Element tags — only when zoomed IN. Constant screen size so they're
          clearly readable. */}
      {showElements && elementLabels.map(label => (
        <Html
          key={label.id}
          position={label.position}
          center
          zIndexRange={[90, 0]}
          style={{ pointerEvents: 'none' }}
        >
          <div style={{
            background: isDark ? `rgba(22,24,32,${bgOpacity})` : `rgba(255,255,255,${bgOpacity})`,
            color: typeColors[label.type] || (isDark ? '#aabbcc' : '#334455'),
            padding: '1px 4px',
            borderRadius: 4,
            fontSize: 8,
            fontWeight: 600,
            fontFamily: '-apple-system, system-ui, sans-serif',
            whiteSpace: 'nowrap',
            letterSpacing: '0.02em',
            border: `1px solid ${isDark ? 'rgba(120,130,150,0.20)' : 'rgba(100,110,130,0.15)'}`,
            maxWidth: 160,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            userSelect: 'none',
          }}>
            {label.name}
          </div>
        </Html>
      ))}

      {/* Room titles — only when zoomed OUT. Constant screen size. */}
      {!showElements && roomLabels.map(label => (
        <Html
          key={label.id}
          position={label.position}
          center
          zIndexRange={[100, 0]}
          style={{ pointerEvents: 'none' }}
        >
          <div style={{
            background: isDark ? `rgba(22,24,32,${bgOpacity})` : `rgba(255,255,255,${bgOpacity})`,
            color: typeColors.room,
            padding: '2px 8px',
            borderRadius: 5,
            fontSize: 8,
            fontWeight: 700,
            fontFamily: '-apple-system, system-ui, sans-serif',
            whiteSpace: 'nowrap',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            border: `1px solid ${isDark ? 'rgba(140,150,170,0.30)' : 'rgba(100,110,130,0.20)'}`,
            boxShadow: isDark ? '0 2px 10px rgba(0,0,0,0.35)' : '0 2px 8px rgba(0,0,0,0.12)',
            userSelect: 'none',
          }}>
            {label.name}
          </div>
        </Html>
      ))}
    </group>
  )
}
