import React, { useMemo } from 'react'
import * as THREE from 'three'
import { Edges } from '@react-three/drei'
import { LayoutJSON, LayerVisibility } from '../../types'

// ── Height lookup ──────────────────────────────────────────────────────
const KEYWORD_HEIGHTS: Record<string, number> = {
  shelf: 1.6, rack: 1.6, shelving: 1.6,
  table: 0.85, desk: 0.85, counter: 0.85, workbench: 0.85, bench: 0.85,
  machine: 1.0, cnc: 1.2, conveyor: 0.7, press: 1.3,
  assembly: 0.9, packaging: 0.9, labeling: 0.85,
  toilet: 0.45, sink: 0.85, urinal: 0.6,
  hvac: 0.6, panel: 1.8, riser: 2.0, duct: 0.4,
  bin: 1.2,
}

function resolveHeight(name: string, attrs: Record<string, unknown>, fallback: number): number {
  if (typeof attrs.height === 'number') return attrs.height
  const lower = name.toLowerCase()
  for (const [kw, h] of Object.entries(KEYWORD_HEIGHTS)) {
    if (lower.includes(kw)) return h
  }
  return fallback
}

// ── Geometry helpers ───────────────────────────────────────────────────
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

/** Compute the perpendicular offset points for a wall segment with thickness. */
function wallRectFromLine(
  p1: [number, number], p2: [number, number], thickness: number
): [number, number][] {
  const dx = p2[0] - p1[0]
  const dy = p2[1] - p1[1]
  const len = Math.sqrt(dx * dx + dy * dy)
  if (len === 0) return [p1, p2, p2, p1]
  const nx = (-dy / len) * thickness / 2
  const ny = (dx / len) * thickness / 2
  return [
    [p1[0] + nx, p1[1] + ny],
    [p2[0] + nx, p2[1] + ny],
    [p2[0] - nx, p2[1] - ny],
    [p1[0] - nx, p1[1] - ny],
  ]
}

// ── Sub-components ─────────────────────────────────────────────────────

interface FloorPlanRendererProps {
  layout: LayoutJSON
  layers: LayerVisibility
  selectedId: string | null
  onSelect: (id: string | null) => void
  isDark?: boolean
}

export default function FloorPlanRenderer({ layout, layers, selectedId, onSelect, isDark = true }: FloorPlanRendererProps) {
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
      {layers.rooms && <RoomsLayer rooms={layout.rooms} selectedId={selectedId} onSelect={onSelect} isDark={isDark} />}
      {layers.structure && <StructureLayer items={layout.structure} selectedId={selectedId} onSelect={onSelect} isDark={isDark} />}
      {layers.doors && <DoorsLayer items={layout.doors} selectedId={selectedId} onSelect={onSelect} isDark={isDark} />}
      {layers.windows && <WindowsLayer items={layout.windows} selectedId={selectedId} onSelect={onSelect} isDark={isDark} />}
      {layers.furniture && <FurnitureLayer items={layout.furniture} selectedId={selectedId} onSelect={onSelect} isDark={isDark} />}
      {layers.mep && <MEPLayer items={layout.mep} selectedId={selectedId} onSelect={onSelect} isDark={isDark} />}
    </group>
  )
}

// ── Shared types ──────────────────────────────────────────────────────
type DarkProp = { isDark: boolean }

// ── Arctic palette — muted Scandinavian tones matching layer dot colors ──
// Outline #6B7B9E  Rooms #B5A898  Walls #8B8F96  Doors #C4896E
// Windows #7A9DB8  Furniture #9888AD  MEP #7EA68B
const ARCTIC = {
  room:      { dark: '#2a2c36', light: '#eae6e2', edge: '#d4cec8' },   // warm sand tint
  wall:      { dark: '#4a4f58', light: '#c5c7cb', edge: '#a0a3a8' },   // cool gray
  door:      { dark: '#8a7060', light: '#edddd0', edge: '#d4b8a0' },   // terracotta tint
  window:    { dark: '#607088', light: '#dce8f0', edge: '#b0c8d8' },   // steel blue tint
  furniture: { dark: '#5a5060', light: '#e6e0ec', edge: '#c4b8d0' },   // dusty lavender
  mep:       { dark: '#4a5850', light: '#deeae2', edge: '#b0c8b8' },   // sage tint
}

// ── Outline ────────────────────────────────────────────────────────────
function OutlineLayer({ outline, isDark }: { outline: [number, number][]; selectedId: string | null; isDark: boolean }) {
  const points = useMemo(() => outline.map(([x, y]) => new THREE.Vector3(x, 0.02, y)), [outline])
  const geo = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points])
  return (
    <lineLoop geometry={geo}>
      <lineBasicMaterial color={isDark ? '#6B7B9E' : '#9aa8bc'} linewidth={1.5} />
    </lineLoop>
  )
}

// ── Rooms ──────────────────────────────────────────────────────────────
function RoomsLayer({ rooms, selectedId, onSelect, isDark }: {
  rooms: LayoutJSON['rooms']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {rooms.map(room => (
        <RoomMesh key={room.id} room={room} isSelected={selectedId === room.id} onSelect={onSelect} isDark={isDark} />
      ))}
    </group>
  )
}

function RoomMesh({ room, isSelected, onSelect, isDark }: {
  room: LayoutJSON['rooms'][0]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  const geo = useMemo(() => {
    const shape = shapeFromPolygon(room.geometry)
    const g = new THREE.ShapeGeometry(shape)
    g.rotateX(-Math.PI / 2)
    g.translate(0, 0.01, 0)
    return g
  }, [room.geometry])

  return (
    <mesh geometry={geo} userData={{ elementId: room.id, type: 'room', name: room.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(room.id) }}>
      <meshStandardMaterial
        color={isDark ? ARCTIC.room.dark : ARCTIC.room.light}
        transparent opacity={0.85} side={THREE.DoubleSide}
        roughness={0.95} metalness={0}
        emissive={isSelected ? '#6B7B9E' : '#000000'}
        emissiveIntensity={isSelected ? 0.35 : 0}
      />
    </mesh>
  )
}

// ── Structure (walls) — always white, 80% transparency ────────────────
function StructureLayer({ items, selectedId, onSelect, isDark }: {
  items: LayoutJSON['structure']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {items.map(wall => (
        <WallMesh key={wall.id} wall={wall} isSelected={selectedId === wall.id} onSelect={onSelect} isDark={isDark} />
      ))}
    </group>
  )
}

function WallMesh({ wall, isSelected, onSelect, isDark }: {
  wall: LayoutJSON['structure'][0]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  const WALL_HEIGHT = 3.0
  const WALL_THICKNESS = 0.2
  const geo = useMemo(() => {
    const [p1, p2] = wall.geometry
    const rect = wallRectFromLine(p1, p2, WALL_THICKNESS)
    const shape = shapeFromPolygon(rect)
    const g = new THREE.ExtrudeGeometry(shape, { depth: WALL_HEIGHT, bevelEnabled: false })
    g.rotateX(-Math.PI / 2)
    return g
  }, [wall.geometry])

  return (
    <mesh geometry={geo} castShadow userData={{ elementId: wall.id, type: 'structure', name: wall.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(wall.id) }}>
      {isDark ? (
        <meshStandardMaterial
          color={ARCTIC.wall.dark}
          transparent opacity={0.80}
          roughness={0.95} metalness={0}
          emissive={isSelected ? '#6B7B9E' : '#000000'}
          emissiveIntensity={isSelected ? 0.35 : 0}
        />
      ) : (
        <meshBasicMaterial
          color={isSelected ? '#d0d8e4' : ARCTIC.wall.light}
          transparent opacity={0.80}
        />
      )}
      <Edges threshold={15} color={isDark ? '#6B7B9E' : ARCTIC.wall.edge} />
    </mesh>
  )
}

// ── Doors ──────────────────────────────────────────────────────────────
function DoorsLayer({ items, selectedId, onSelect, isDark }: {
  items: LayoutJSON['doors']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {items.map(door => (
        <DoorMesh key={door.id} door={door} isSelected={selectedId === door.id} onSelect={onSelect} isDark={isDark} />
      ))}
    </group>
  )
}

function DoorMesh({ door, isSelected, onSelect, isDark }: {
  door: LayoutJSON['doors'][0]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  const DOOR_HEIGHT = 2.2
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
    <mesh position={position} rotation={rotation} castShadow
      userData={{ elementId: door.id, type: 'door', name: door.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(door.id) }}>
      <boxGeometry args={size} />
      <meshStandardMaterial
        color={isDark ? ARCTIC.door.dark : ARCTIC.door.light}
        transparent opacity={0.92}
        roughness={0.95} metalness={0}
        emissive={isSelected ? '#6B7B9E' : '#000000'}
        emissiveIntensity={isSelected ? 0.35 : 0}
      />
      <Edges threshold={15} color={isDark ? '#C4896E' : ARCTIC.door.edge} />
    </mesh>
  )
}

// ── Windows ────────────────────────────────────────────────────────────
function WindowsLayer({ items, selectedId, onSelect, isDark }: {
  items: LayoutJSON['windows']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {items.map(win => (
        <WindowMesh key={win.id} win={win} isSelected={selectedId === win.id} onSelect={onSelect} isDark={isDark} />
      ))}
    </group>
  )
}

function WindowMesh({ win, isSelected, onSelect, isDark }: {
  win: LayoutJSON['windows'][0]; isSelected: boolean; onSelect: (id: string | null) => void
} & DarkProp) {
  const WIN_BOTTOM = 1.0, WIN_HEIGHT = 1.0
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
    <mesh position={position} rotation={rotation} castShadow
      userData={{ elementId: win.id, type: 'window', name: win.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(win.id) }}>
      <boxGeometry args={size} />
      <meshStandardMaterial
        color={isDark ? ARCTIC.window.dark : ARCTIC.window.light}
        transparent opacity={0.78}
        roughness={0.95} metalness={0}
        emissive={isSelected ? '#6B7B9E' : '#000000'}
        emissiveIntensity={isSelected ? 0.35 : 0}
      />
      <Edges threshold={15} color={isDark ? '#7A9DB8' : ARCTIC.window.edge} />
    </mesh>
  )
}

// ── Furniture ──────────────────────────────────────────────────────────
function FurnitureLayer({ items, selectedId, onSelect, isDark }: {
  items: LayoutJSON['furniture']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {items.map(item => (
        <FurnitureMesh key={item.id} item={item} isSelected={selectedId === item.id} onSelect={onSelect} isDark={isDark} />
      ))}
    </group>
  )
}

function FurnitureMesh({ item, isSelected, onSelect, isDark }: {
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
    <mesh geometry={geo} castShadow userData={{ elementId: item.id, type: 'furniture', name: item.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(item.id) }}>
      <meshStandardMaterial
        color={isDark ? ARCTIC.furniture.dark : ARCTIC.furniture.light}
        roughness={0.95} metalness={0}
        emissive={isSelected ? '#6B7B9E' : '#000000'}
        emissiveIntensity={isSelected ? 0.35 : 0}
        transparent opacity={0.92}
      />
      <Edges threshold={15} color={isDark ? '#9888AD' : ARCTIC.furniture.edge} />
    </mesh>
  )
}

// ── MEP ────────────────────────────────────────────────────────────────
function MEPLayer({ items, selectedId, onSelect, isDark }: {
  items: LayoutJSON['mep']; selectedId: string | null; onSelect: (id: string | null) => void
} & DarkProp) {
  return (
    <group>
      {items.map(item => (
        <MEPMesh key={item.id} item={item} isSelected={selectedId === item.id} onSelect={onSelect} isDark={isDark} />
      ))}
    </group>
  )
}

function MEPMesh({ item, isSelected, onSelect, isDark }: {
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
    <mesh geometry={geo} castShadow userData={{ elementId: item.id, type: 'mep', name: item.name }}
      onClick={(e) => { e.stopPropagation(); onSelect(item.id) }}>
      <meshStandardMaterial
        color={isDark ? ARCTIC.mep.dark : ARCTIC.mep.light}
        roughness={0.95} metalness={0}
        emissive={isSelected ? '#6B7B9E' : '#000000'}
        emissiveIntensity={isSelected ? 0.35 : 0}
        transparent opacity={0.92}
      />
      <Edges threshold={15} color={isDark ? '#7EA68B' : ARCTIC.mep.edge} />
    </mesh>
  )
}
