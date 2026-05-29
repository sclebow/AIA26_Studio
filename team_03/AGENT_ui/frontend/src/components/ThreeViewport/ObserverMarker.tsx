import React, { useRef, useMemo, useCallback } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'

// Person proxy height in metres.
const PERSON_HEIGHT = 1.7
const HEAD_RADIUS = 0.16

interface ObserverMarkerProps {
  /** Geometry centre offset — matches FloorPlanRenderer's centred group so the
   *  marker's local coords equal layout coords. */
  center: { x: number; z: number }
  /** Current position in LAYOUT coordinates (metres, origin bottom-left). Used only when pathMode is false. */
  position: { x: number; y: number }
  isDark: boolean
  /** Fired continuously while dragging (layout coords). */
  onMove: (x: number, y: number) => void
  /** Fired once on pointer-up (layout coords). */
  onRelease: (x: number, y: number) => void
  /** Fired when a drag starts — lets the parent suppress geometry selection. */
  onDragStart?: () => void
  /** Fired when a drag ends. */
  onDragEnd?: () => void
  /** When true, renders the path visualization instead of the draggable person. */
  pathMode?: boolean
  /** Ordered path points in LAYOUT coordinates. Rendered when pathMode is true. */
  pathPoints?: Array<{ x: number; y: number }>
}

/**
 * A draggable point representing a 1.7m-tall person, constrained to the floor
 * plane (XZ). Lives inside a group offset by -center so its local (x, z) map
 * directly onto layout (x, y) in metres.
 */
function PathRenderer({ center, pathPoints }: { center: { x: number; z: number }; pathPoints: Array<{ x: number; y: number }> }) {
  const linePositions = useMemo(() => {
    return new Float32Array(pathPoints.flatMap(pt => [pt.x, 0.15, pt.y]))
  }, [pathPoints])

  return (
    <group position={[-center.x, 0, -center.z]}>
      {pathPoints.map((pt, i) => (
        <mesh key={i} position={[pt.x, 0.15, pt.y]}>
          <sphereGeometry args={[0.15, 12, 12]} />
          <meshStandardMaterial color="#ef4444" roughness={0.5} emissive="#ef4444" emissiveIntensity={0.4} />
        </mesh>
      ))}
      {pathPoints.length >= 2 && (
        <line>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[linePositions, 3]} />
          </bufferGeometry>
          <lineBasicMaterial color="#ef4444" transparent opacity={0.7} />
        </line>
      )}
    </group>
  )
}

export default function ObserverMarker({ center, position, isDark, onMove, onRelease, onDragStart, onDragEnd, pathMode, pathPoints }: ObserverMarkerProps) {
  const { camera, gl, controls } = useThree()
  const groupRef = useRef<THREE.Group>(null)
  const draggingRef = useRef(false)

  // Reusable raycasting scratch objects.
  const raycaster = useMemo(() => new THREE.Raycaster(), [])
  const groundPlane = useMemo(() => new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), [])
  const hitPoint = useMemo(() => new THREE.Vector3(), [])
  const ndc = useMemo(() => new THREE.Vector2(), [])

  if (pathMode) {
    return <PathRenderer center={center} pathPoints={pathPoints ?? []} />
  }

  const accent = isDark ? '#8b5cf6' : '#7c3aed'

  // ── Convert a pointer event to a layout-coordinate hit on the floor ──────
  const pointerToLayout = useCallback((e: PointerEvent): { x: number; y: number } | null => {
    const rect = gl.domElement.getBoundingClientRect()
    ndc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
    ndc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(ndc, camera)
    const hit = raycaster.ray.intersectPlane(groundPlane, hitPoint)
    if (!hit) return null
    // World coords → layout coords (undo the centred-group offset).
    return { x: hit.x + center.x, y: hit.z + center.z }
  }, [camera, gl, raycaster, groundPlane, hitPoint, ndc, center])

  const handlePointerMove = useCallback((e: PointerEvent) => {
    if (!draggingRef.current) return
    const layout = pointerToLayout(e)
    if (layout) onMove(layout.x, layout.y)
  }, [pointerToLayout, onMove])

  const handlePointerUp = useCallback((e: PointerEvent) => {
    if (!draggingRef.current) return
    draggingRef.current = false
    if (controls) (controls as any).enabled = true
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', handlePointerUp)
    const layout = pointerToLayout(e)
    if (layout) onRelease(layout.x, layout.y)
    onDragEnd?.()
  }, [controls, pointerToLayout, onRelease, handlePointerMove, onDragEnd])

  const handlePointerDown = useCallback((e: any) => {
    e.stopPropagation()
    draggingRef.current = true
    onDragStart?.()
    // Disable orbit so dragging the marker doesn't rotate the camera.
    if (controls) (controls as any).enabled = false
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
  }, [controls, handlePointerMove, handlePointerUp, onDragStart])

  // The outer group already applies the -center offset, so inside it the local
  // position is simply the raw layout coords (matches FloorPlanRenderer, where
  // a layout point [x,y] is drawn at local (x, h, y) inside the same group).
  const localX = position.x
  const localZ = position.y

  return (
    <group ref={groupRef} position={[-center.x, 0, -center.z]}>
      <group
        position={[localX, 0, localZ]}
        onPointerDown={handlePointerDown}
        onPointerOver={() => { gl.domElement.style.cursor = 'grab' }}
        onPointerOut={() => { gl.domElement.style.cursor = 'auto' }}
      >
        {/* Base disc on the floor */}
        <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.18, 0.32, 32]} />
          <meshBasicMaterial color={accent} transparent opacity={0.9} side={THREE.DoubleSide} />
        </mesh>

        {/* Body — tapered cylinder up to shoulder height */}
        <mesh position={[0, (PERSON_HEIGHT - HEAD_RADIUS * 2) / 2, 0]} castShadow>
          <cylinderGeometry args={[0.12, 0.20, PERSON_HEIGHT - HEAD_RADIUS * 2, 16]} />
          <meshStandardMaterial color={accent} roughness={0.6} metalness={0} emissive={accent} emissiveIntensity={0.25} />
        </mesh>

        {/* Head */}
        <mesh position={[0, PERSON_HEIGHT - HEAD_RADIUS, 0]} castShadow>
          <sphereGeometry args={[HEAD_RADIUS, 16, 16]} />
          <meshStandardMaterial color={accent} roughness={0.6} metalness={0} emissive={accent} emissiveIntensity={0.25} />
        </mesh>

        {/* Vertical guide line base → head top */}
        <line>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              args={[new Float32Array([0, 0, 0, 0, PERSON_HEIGHT, 0]), 3]}
            />
          </bufferGeometry>
          <lineBasicMaterial color={accent} transparent opacity={0.5} />
        </line>
      </group>
    </group>
  )
}
