import React, { useMemo } from 'react'
import * as THREE from 'three'

interface IsovistSurfaceProps {
  /** Isovist polygon in layout metres (x,y). */
  points: [number, number][]
  /** Geometry centre (same as the floor/observer) so it aligns with the layout. */
  center: { x: number; z: number }
  color: string
  opacity?: number
}

/** Flat, semi-transparent visibility surface (isovist polygon) drawn on the floor.
 *  The polygon comes from Grasshopper's `set_observer` (the `boundary` value), in
 *  layout metres on the XY plane — we drop it onto the floor (XZ) like ObserverMarker
 *  does (layout.y → world z). */
const IsovistSurface: React.FC<IsovistSurfaceProps> = ({ points, center, color, opacity = 0.25 }) => {
  const shape = useMemo(() => {
    if (!points || points.length < 3) return null
    const s = new THREE.Shape()
    points.forEach(([x, y], i) => (i === 0 ? s.moveTo(x, y) : s.lineTo(x, y)))
    s.closePath()
    return s
  }, [points])

  // Closed outline drawn directly in world coords (x, y_offset, layout_y).
  const outline = useMemo(() => {
    if (!points || points.length < 3) return new Float32Array(0)
    const closed = [...points, points[0]]
    return new Float32Array(closed.flatMap(([x, y]) => [x, 0.035, y]))
  }, [points])

  if (!shape) return null

  return (
    <group position={[-center.x, 0, -center.z]}>
      <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
        <shapeGeometry args={[shape]} />
        <meshBasicMaterial color={color} transparent opacity={opacity} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <line>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[outline, 3]} />
        </bufferGeometry>
        <lineBasicMaterial color={color} transparent opacity={0.7} />
      </line>
    </group>
  )
}

export default React.memo(IsovistSurface)
