import React, { useRef, useMemo, useCallback } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'

const PERSON_HEIGHT = 1.7
const HEAD_RADIUS = 0.16

interface ObserverMarkerProps {
  center: { x: number; z: number }
  position: { x: number; y: number }
  isDark: boolean
  onMove: (x: number, y: number) => void
  onRelease: (x: number, y: number) => void
  onDragStart?: () => void
  onDragEnd?: () => void
  pathMode?: boolean
  pathPoints?: Array<{ x: number; y: number }>
  /** Called continuously while dragging a path node. */
  onUpdatePathPoint?: (index: number, x: number, y: number) => void
  /** Called on pointer-up after dragging a path node. */
  onReleasePathPoint?: (index: number, x: number, y: number) => void
  /** When true: visible ghost — semi-transparent, non-interactive. */
  ghost?: boolean
}

// ── Draggable path node ──────────────────────────────────────────────────────

function DraggablePathNode({
  center, pt, index, onMove, onRelease, ghost,
}: {
  center: { x: number; z: number }
  pt: { x: number; y: number }
  index: number
  onMove: (i: number, x: number, y: number) => void
  onRelease: (i: number, x: number, y: number) => void
  ghost?: boolean
}) {
  const { camera, gl, controls } = useThree()
  const dragging = useRef(false)
  const raycaster = useMemo(() => new THREE.Raycaster(), [])
  const plane = useMemo(() => new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), [])
  const hitVec = useMemo(() => new THREE.Vector3(), [])
  const ndc = useMemo(() => new THREE.Vector2(), [])

  // cbRef avoids stale closures inside event listeners
  const cbRef = useRef({ onMove, onRelease, center, camera, gl, controls, raycaster, plane, hitVec, ndc })
  cbRef.current = { onMove, onRelease, center, camera, gl, controls, raycaster, plane, hitVec, ndc }

  const getLayout = (e: PointerEvent): { x: number; y: number } | null => {
    const { gl: g, ndc: n, raycaster: rc, plane: pl, hitVec: h, camera: cam, center: c } = cbRef.current
    const rect = g.domElement.getBoundingClientRect()
    n.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
    n.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    rc.setFromCamera(n, cam)
    if (!rc.ray.intersectPlane(pl, h)) return null
    return { x: h.x + c.x, y: h.z + c.z }
  }

  const handlePointerDown = useCallback((e: any) => {
    if (ghost) return
    e.stopPropagation()
    dragging.current = true
    const ctrl = cbRef.current.controls as any
    if (ctrl) ctrl.enabled = false

    const move = (ev: PointerEvent) => {
      if (!dragging.current) return
      const p = getLayout(ev)
      if (p) cbRef.current.onMove(index, p.x, p.y)
    }
    const up = (ev: PointerEvent) => {
      dragging.current = false
      if (ctrl) ctrl.enabled = true
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      const p = getLayout(ev)
      if (p) cbRef.current.onRelease(index, p.x, p.y)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }, [ghost, index])

  return (
    <mesh
      position={[pt.x, 0.15, pt.y]}
      onPointerDown={handlePointerDown}
      onPointerOver={ghost ? undefined : () => { cbRef.current.gl.domElement.style.cursor = 'grab' }}
      onPointerOut={ghost ? undefined : () => { cbRef.current.gl.domElement.style.cursor = 'auto' }}
    >
      <sphereGeometry args={[0.18, 12, 12]} />
      <meshStandardMaterial
        color="#ef4444" roughness={0.5} emissive="#ef4444"
        emissiveIntensity={ghost ? 0.1 : 0.4}
        transparent opacity={ghost ? 0.2 : 1.0}
      />
    </mesh>
  )
}

// ── Path renderer ────────────────────────────────────────────────────────────

function PathRenderer({
  center, pathPoints, ghost, onUpdatePoint, onReleasePoint,
}: {
  center: { x: number; z: number }
  pathPoints: Array<{ x: number; y: number }>
  ghost?: boolean
  onUpdatePoint?: (i: number, x: number, y: number) => void
  onReleasePoint?: (i: number, x: number, y: number) => void
}) {
  const linePositions = useMemo(() => {
    return new Float32Array(pathPoints.flatMap(pt => [pt.x, 0.15, pt.y]))
  }, [pathPoints])

  return (
    <group position={[-center.x, 0, -center.z]}>
      {pathPoints.map((pt, i) => (
        <DraggablePathNode
          key={i}
          center={center}
          pt={pt}
          index={i}
          onMove={onUpdatePoint ?? (() => {})}
          onRelease={onReleasePoint ?? (() => {})}
          ghost={ghost}
        />
      ))}
      {pathPoints.length >= 2 && (
        <line>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[linePositions, 3]} />
          </bufferGeometry>
          <lineBasicMaterial color="#ef4444" transparent opacity={ghost ? 0.25 : 0.7} />
        </line>
      )}
    </group>
  )
}

// ── Main component (person marker) ──────────────────────────────────────────

export default function ObserverMarker({
  center, position, isDark, onMove, onRelease, onDragStart, onDragEnd,
  pathMode, pathPoints, onUpdatePathPoint, onReleasePathPoint, ghost,
}: ObserverMarkerProps) {
  const { camera, gl, controls } = useThree()
  const groupRef = useRef<THREE.Group>(null)
  const draggingRef = useRef(false)

  const raycaster = useMemo(() => new THREE.Raycaster(), [])
  const groundPlane = useMemo(() => new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), [])
  const hitPoint = useMemo(() => new THREE.Vector3(), [])
  const ndc = useMemo(() => new THREE.Vector2(), [])

  if (pathMode) {
    return (
      <PathRenderer
        center={center}
        pathPoints={pathPoints ?? []}
        ghost={ghost}
        onUpdatePoint={onUpdatePathPoint}
        onReleasePoint={onReleasePathPoint}
      />
    )
  }

  const accent = isDark ? '#8b5cf6' : '#7c3aed'
  const matOpacity = ghost ? 0.22 : 1.0
  const emissiveInt = ghost ? 0.0 : 0.25

  const pointerToLayout = (e: PointerEvent): { x: number; y: number } | null => {
    const rect = gl.domElement.getBoundingClientRect()
    ndc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
    ndc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(ndc, camera)
    const hit = raycaster.ray.intersectPlane(groundPlane, hitPoint)
    if (!hit) return null
    return { x: hitPoint.x + center.x, y: hitPoint.z + center.z }
  }

  const handlePointerMove = (e: PointerEvent) => {
    if (!draggingRef.current) return
    const layout = pointerToLayout(e)
    if (layout) onMove(layout.x, layout.y)
  }

  const handlePointerUp = (e: PointerEvent) => {
    if (!draggingRef.current) return
    draggingRef.current = false
    if (controls) (controls as any).enabled = true
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', handlePointerUp)
    const layout = pointerToLayout(e)
    if (layout) onRelease(layout.x, layout.y)
    onDragEnd?.()
  }

  const handlePointerDown = (e: any) => {
    if (ghost) return
    e.stopPropagation()
    draggingRef.current = true
    onDragStart?.()
    if (controls) (controls as any).enabled = false
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
  }

  const localX = position.x
  const localZ = position.y

  return (
    <group ref={groupRef} position={[-center.x, 0, -center.z]}>
      <group
        position={[localX, 0, localZ]}
        onPointerDown={ghost ? undefined : handlePointerDown}
        onPointerOver={ghost ? undefined : () => { gl.domElement.style.cursor = 'grab' }}
        onPointerOut={ghost ? undefined : () => { gl.domElement.style.cursor = 'auto' }}
      >
        <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.18, 0.32, 32]} />
          <meshBasicMaterial color={accent} transparent opacity={ghost ? 0.2 : 0.9} side={THREE.DoubleSide} />
        </mesh>
        <mesh position={[0, (PERSON_HEIGHT - HEAD_RADIUS * 2) / 2, 0]} castShadow>
          <cylinderGeometry args={[0.12, 0.20, PERSON_HEIGHT - HEAD_RADIUS * 2, 16]} />
          <meshStandardMaterial color={accent} roughness={0.6} metalness={0} emissive={accent} emissiveIntensity={emissiveInt} transparent opacity={matOpacity} />
        </mesh>
        <mesh position={[0, PERSON_HEIGHT - HEAD_RADIUS, 0]} castShadow>
          <sphereGeometry args={[HEAD_RADIUS, 16, 16]} />
          <meshStandardMaterial color={accent} roughness={0.6} metalness={0} emissive={accent} emissiveIntensity={emissiveInt} transparent opacity={matOpacity} />
        </mesh>
        <line>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[new Float32Array([0, 0, 0, 0, PERSON_HEIGHT, 0]), 3]} />
          </bufferGeometry>
          <lineBasicMaterial color={accent} transparent opacity={ghost ? 0.15 : 0.5} />
        </line>
      </group>
    </group>
  )
}
