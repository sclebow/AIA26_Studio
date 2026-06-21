import React, { useMemo } from 'react'
import * as THREE from 'three'
import { Edges } from '@react-three/drei'
import { LayoutJSON, LayerVisibility } from '../../types'
import {
  DOOR_HEIGHT, WIN_BOTTOM, WIN_HEIGHT,
  type Pt, type Opening,
  resolveHeight, assignOpenings, buildWallPieces,
} from './geometry'

// ── Geometry helpers (Three.js-specific) ────────────────────────────────
/** Build a THREE.Shape from a polygon (closed polyline, [x,y] coords).
 *  Y is negated because rotateX(-PI/2) maps shape-y to -z in world space.
 *  With -y in the shape, after rotation z' = -(-y) = +y, matching doors/windows. */
function shapeFromPolygon(coords: [number, number][]): THREE.Shape {
  const shape = new THREE.Shape()
  shape.moveTo(coords[0][0], -coords[0][1])
  for (let i = 1; i < coords.length; i++) {
    shape.lineTo(coords[i][0], -coords[i][1])
  }
  shape.closePath()
  return shape
}

// ── Sub-components ─────────────────────────────────────────────────────

interface FloorPlanRendererProps {
  layout: LayoutJSON
  layers: LayerVisibility
  selectedId: string | null
  onSelect: (id: string | null) => void
  isDark?: boolean
  renderMode?: RenderMode
}

export default function FloorPlanRenderer({ layout, layers, selectedId, onSelect, isDark = true, renderMode = 'rendered' }: FloorPlanRendererProps) {
  // Compute center offset so layout is centered at origin
  const center = useMemo(() => {
    const outline = layout.outline
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const [x, y] of outline) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x)
      minY = Math.min(minY, y); maxY = Math.max(maxY, y)
    }
    return { x: (minX + maxX) / 2, z: (minY + maxY) / 2 }
  }, [layout])

  return (
    <group position={[-center.x, 0, -center.z]}>
      {layers.outline && <OutlineLayer outline={layout.outline} selectedId={selectedId} isDark={isDark} />}
      {layers.rooms && <RoomsLayer rooms={layout.rooms} selectedId={selectedId} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />}
      {layers.structure && <StructureLayer items={layout.structure} doors={layout.doors} windows={layout.windows} selectedId={selectedId} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />}
      {layers.doors && <DoorsLayer items={layout.doors} selectedId={selectedId} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />}
      {layers.windows && <WindowsLayer items={layout.windows} selectedId={selectedId} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />}
      {layers.furniture && <FurnitureLayer items={layout.furniture} selectedId={selectedId} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />}
      {layers.mep && <MEPLayer items={layout.mep} selectedId={selectedId} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />}
    </group>
  )
}

// ── Shared types ──────────────────────────────────────────────────────
type DarkProp = { isDark: boolean; renderMode: RenderMode }

// Viewport render styles (Rhino-like).
export type RenderMode = 'rendered' | 'wireframe' | 'shaded' | 'ghosted'

// ── Palette — sci-fi purple family. Dark variants brightened for contrast so the
// geometry reads clearly over the #15101f viewport background; light unchanged. ──
const ARCTIC = {
  room:      { dark: '#322b4a', light: '#eae6e2', edge: '#d4cec8' },   // indigo-tinted floor
  wall:      { dark: '#564f74', light: '#c5c7cb', edge: '#a0a3a8' },   // slate-purple
  door:      { dark: '#a06f8e', light: '#edddd0', edge: '#d4b8a0' },   // warm orchid (contrast)
  window:    { dark: '#6b7ca8', light: '#dce8f0', edge: '#b0c8d8' },   // lavender-steel
  furniture: { dark: '#7a6aa0', light: '#e6e0ec', edge: '#c4b8d0' },   // violet
  mep:       { dark: '#4f7e6e', light: '#deeae2', edge: '#b0c8b8' },   // cool teal-green
}

// Sci-fi edge/selection accents (dark mode).
const EDGE_DARK = {
  outline:   '#9a78ff',
  wall:      '#9d8de0',
  door:      '#e8aacf',
  window:    '#96acec',
  furniture: '#b89cff',
  mep:       '#6df0d8',
}
const SELECT_EMISSIVE = '#a78bfa'

// Shadows only make sense for solid fills (rendered/shaded).
const castsShadow = (m: RenderMode) => m === 'rendered' || m === 'shaded'

/** Material for solid layers, styled per render mode. */
function SolidMaterial({ mode, color, roughness, metalness, selected }: {
  mode: RenderMode; color: string; roughness: number; metalness: number; selected: boolean
}) {
  const emissive = selected ? SELECT_EMISSIVE : '#000000'
  // `key={mode}` forces a fresh material instance per mode so toggled props
  // (transparent/opacity/depthWrite, which need a shader recompile) never get
  // stuck when returning to a previous mode — e.g. ghosted → rendered.
  if (mode === 'wireframe') {
    // No fill — only the <Edges> contours show.
    return <meshBasicMaterial key={mode} color={color} transparent opacity={0} depthWrite={false} />
  }
  const ghosted = mode === 'ghosted'
  return (
    <meshStandardMaterial
      key={mode}
      color={color}
      transparent={ghosted}
      opacity={ghosted ? 0.26 : 1}
      depthWrite={!ghosted}
      roughness={mode === 'shaded' ? 1 : ghosted ? 0.9 : roughness}
      metalness={mode === 'rendered' ? metalness : 0}
      emissive={emissive}
      emissiveIntensity={selected ? (mode === 'rendered' ? 0.75 : mode === 'shaded' ? 0.55 : 0.6) : 0}
    />
  )
}

// ── Outline ────────────────────────────────────────────────────────────
function OutlineLayer({ outline, isDark }: { outline: [number, number][]; selectedId: string | null; isDark: boolean }) {
  const points = useMemo(() => outline.map(([x, y]) => new THREE.Vector3(x, 0.02, y)), [outline])
  const geo = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points])
  return (
    <lineLoop geometry={geo}>
      <lineBasicMaterial color={isDark ? EDGE_DARK.outline : '#9aa8bc'} linewidth={1.5} />
    </lineLoop>
  )
}

// ── Rooms ──────────────────────────────────────────────────────────────
function RoomsLayer({ rooms, selectedId, onSelect, isDark, renderMode }: {
  rooms: LayoutJSON['rooms']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {rooms.map(room => (
        <RoomMesh key={room.id} room={room} isSelected={selectedId === room.id} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />
      ))}
    </group>
  )
}

function RoomMesh({ room, isSelected, onSelect, isDark, renderMode }: {
  room: LayoutJSON['rooms'][0]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  const geo = useMemo(() => {
    const shape = shapeFromPolygon(room.geometry)
    const g = new THREE.ShapeGeometry(shape)
    g.rotateX(-Math.PI / 2)
    g.translate(0, 0.01, 0)
    return g
  }, [room.geometry])

  // Floor: only receives shadows; wireframe shows just its outline.
  return (
    <mesh geometry={geo} receiveShadow={castsShadow(renderMode)} userData={{ elementId: room.id, type: 'room', name: room.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(room.id) }}>
      {renderMode === 'wireframe' ? (
        <meshBasicMaterial key="wireframe" color={isDark ? ARCTIC.room.dark : ARCTIC.room.light} transparent opacity={0} depthWrite={false} side={THREE.DoubleSide} />
      ) : (
        <meshStandardMaterial
          key={renderMode}
          color={isDark ? ARCTIC.room.dark : ARCTIC.room.light}
          side={THREE.DoubleSide}
          transparent={renderMode === 'ghosted'} opacity={renderMode === 'ghosted' ? 0.26 : 1}
          depthWrite={renderMode !== 'ghosted'}
          roughness={renderMode === 'shaded' ? 1 : 0.82} metalness={renderMode === 'shaded' ? 0 : 0.04}
          emissive={isSelected ? SELECT_EMISSIVE : '#000000'}
          emissiveIntensity={isSelected ? 0.5 : 0}
        />
      )}
    </mesh>
  )
}

// ── Structure (walls) — extruded with door/window openings cut out ────────
function StructureLayer({ items, doors, windows, selectedId, onSelect, isDark, renderMode }: {
  items: LayoutJSON['structure']
  doors: LayoutJSON['doors']
  windows: LayoutJSON['windows']
  selectedId: string | null
  onSelect: (id: string | null) => void
} & DarkProp) {
  // Match every opening to its host wall once, in wall-local coordinates.
  const openingsByWall = useMemo(
    () => assignOpenings(items, doors, windows),
    [items, doors, windows],
  )
  return (
    <group>
      {items.map(wall => (
        <WallMesh
          key={wall.id}
          wall={wall}
          openings={openingsByWall.get(wall.id) || []}
          isSelected={selectedId === wall.id}
          onSelect={onSelect}
          isDark={isDark}
          renderMode={renderMode}
        />
      ))}
    </group>
  )
}

function WallMesh({ wall, openings, isSelected, onSelect, isDark, renderMode }: {
  wall: LayoutJSON['structure'][0]; openings: Opening[]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  // One extruded box per solid sub-piece (segments between openings + sills/lintels).
  const geos = useMemo(() => {
    const [p1, p2] = wall.geometry as Pt[]
    const pieces = buildWallPieces(p1, p2, openings)
    return pieces.map(pc => {
      const shape = shapeFromPolygon(pc.rect)
      const g = new THREE.ExtrudeGeometry(shape, { depth: pc.depth, bevelEnabled: false })
      g.rotateX(-Math.PI / 2)
      g.translate(0, pc.zBottom, 0)
      return g
    })
  }, [wall.geometry, openings])

  const shadow = castsShadow(renderMode)
  return (
    <group userData={{ elementId: wall.id, type: 'structure', name: wall.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(wall.id) }}>
      {geos.map((g, i) => (
        <mesh key={i} geometry={g} castShadow={shadow} receiveShadow={shadow}
          userData={{ elementId: wall.id, type: 'structure', name: wall.name }}>
          <SolidMaterial mode={renderMode}
            color={isDark ? ARCTIC.wall.dark : (isSelected ? '#d0d8e4' : ARCTIC.wall.light)}
            roughness={0.7} metalness={0.12} selected={isSelected} />
          <Edges threshold={15} color={isDark ? EDGE_DARK.wall : ARCTIC.wall.edge} />
        </mesh>
      ))}
    </group>
  )
}

// ── Doors ──────────────────────────────────────────────────────────────
function DoorsLayer({ items, selectedId, onSelect, isDark, renderMode }: {
  items: LayoutJSON['doors']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {items.map(door => (
        <DoorMesh key={door.id} door={door} isSelected={selectedId === door.id} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />
      ))}
    </group>
  )
}

function DoorMesh({ door, isSelected, onSelect, isDark, renderMode }: {
  door: LayoutJSON['doors'][0]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  const { position, size, rotation } = useMemo(() => {
    const [p1, p2] = door.geometry
    const cx = (p1[0] + p2[0]) / 2, cy = (p1[1] + p2[1]) / 2
    const dx = p2[0] - p1[0], dy = p2[1] - p1[1]
    const length = Math.sqrt(dx * dx + dy * dy)
    return {
      position: [cx, DOOR_HEIGHT / 2, cy] as [number, number, number],
      size: [length, DOOR_HEIGHT, 0.08] as [number, number, number],
      rotation: [0, -Math.atan2(dy, dx), 0] as [number, number, number],
    }
  }, [door.geometry])

  return (
    <mesh position={position} rotation={rotation} castShadow={castsShadow(renderMode)} receiveShadow={castsShadow(renderMode)}
      userData={{ elementId: door.id, type: 'door', name: door.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(door.id) }}>
      <boxGeometry args={size} />
      <SolidMaterial mode={renderMode}
        color={isDark ? ARCTIC.door.dark : ARCTIC.door.light}
        roughness={0.6} metalness={0.1} selected={isSelected} />
      <Edges threshold={15} color={isDark ? EDGE_DARK.door : ARCTIC.door.edge} />
    </mesh>
  )
}

// ── Windows ────────────────────────────────────────────────────────────
function WindowsLayer({ items, selectedId, onSelect, isDark, renderMode }: {
  items: LayoutJSON['windows']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {items.map(win => (
        <WindowMesh key={win.id} win={win} isSelected={selectedId === win.id} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />
      ))}
    </group>
  )
}

function WindowMesh({ win, isSelected, onSelect, isDark, renderMode }: {
  win: LayoutJSON['windows'][0]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  const { position, size, rotation } = useMemo(() => {
    const [p1, p2] = win.geometry
    const cx = (p1[0] + p2[0]) / 2, cy = (p1[1] + p2[1]) / 2
    const dx = p2[0] - p1[0], dy = p2[1] - p1[1]
    const length = Math.sqrt(dx * dx + dy * dy)
    return {
      position: [cx, WIN_BOTTOM + WIN_HEIGHT / 2, cy] as [number, number, number],
      size: [length, WIN_HEIGHT, 0.06] as [number, number, number],
      rotation: [0, -Math.atan2(dy, dx), 0] as [number, number, number],
    }
  }, [win.geometry])

  return (
    <mesh position={position} rotation={rotation} castShadow={castsShadow(renderMode)} receiveShadow={castsShadow(renderMode)}
      userData={{ elementId: win.id, type: 'window', name: win.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(win.id) }}>
      <boxGeometry args={size} />
      {renderMode === 'rendered' ? (
        // Glassy, reflective material for windows (rendered only)
        <meshStandardMaterial
          key="rendered-glass"
          color={isDark ? ARCTIC.window.dark : ARCTIC.window.light}
          transparent opacity={0.55} roughness={0.12} metalness={0.2}
          emissive={isSelected ? SELECT_EMISSIVE : '#000000'}
          emissiveIntensity={isSelected ? 0.5 : 0}
        />
      ) : (
        <SolidMaterial mode={renderMode}
          color={isDark ? ARCTIC.window.dark : ARCTIC.window.light}
          roughness={0.5} metalness={0.1} selected={isSelected} />
      )}
      <Edges threshold={15} color={isDark ? EDGE_DARK.window : ARCTIC.window.edge} />
    </mesh>
  )
}

// ── Furniture ──────────────────────────────────────────────────────────
function FurnitureLayer({ items, selectedId, onSelect, isDark, renderMode }: {
  items: LayoutJSON['furniture']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {items.map(item => (
        <FurnitureMesh key={item.id} item={item} isSelected={selectedId === item.id} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />
      ))}
    </group>
  )
}

function FurnitureMesh({ item, isSelected, onSelect, isDark, renderMode }: {
  item: LayoutJSON['furniture'][0]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  const height = resolveHeight(item.name, item.attributes as Record<string, unknown>, 0.9)
  const geo = useMemo(() => {
    const shape = shapeFromPolygon(item.geometry)
    const g = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false })
    g.rotateX(-Math.PI / 2)
    return g
  }, [item.geometry, height])

  return (
    <mesh geometry={geo} castShadow={castsShadow(renderMode)} receiveShadow={castsShadow(renderMode)} userData={{ elementId: item.id, type: 'furniture', name: item.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(item.id) }}>
      <SolidMaterial mode={renderMode}
        color={isDark ? ARCTIC.furniture.dark : ARCTIC.furniture.light}
        roughness={0.55} metalness={0.18} selected={isSelected} />
      <Edges threshold={15} color={isDark ? EDGE_DARK.furniture : ARCTIC.furniture.edge} />
    </mesh>
  )
}

// ── MEP ────────────────────────────────────────────────────────────────
function MEPLayer({ items, selectedId, onSelect, isDark, renderMode }: {
  items: LayoutJSON['mep']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {items.map(item => (
        <MEPMesh key={item.id} item={item} isSelected={selectedId === item.id} onSelect={onSelect} isDark={isDark} renderMode={renderMode} />
      ))}
    </group>
  )
}

function MEPMesh({ item, isSelected, onSelect, isDark, renderMode }: {
  item: LayoutJSON['mep'][0]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  const height = resolveHeight(item.name, item.attributes as Record<string, unknown>, 0.5)
  const geo = useMemo(() => {
    const shape = shapeFromPolygon(item.geometry)
    const g = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false })
    g.rotateX(-Math.PI / 2)
    return g
  }, [item.geometry, height])

  return (
    <mesh geometry={geo} castShadow={castsShadow(renderMode)} receiveShadow={castsShadow(renderMode)} userData={{ elementId: item.id, type: 'mep', name: item.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(item.id) }}>
      {/* Metallic look for MEP (ducts/equipment) */}
      <SolidMaterial mode={renderMode}
        color={isDark ? ARCTIC.mep.dark : ARCTIC.mep.light}
        roughness={0.4} metalness={0.35} selected={isSelected} />
      <Edges threshold={15} color={isDark ? EDGE_DARK.mep : ARCTIC.mep.edge} />
    </mesh>
  )
}
