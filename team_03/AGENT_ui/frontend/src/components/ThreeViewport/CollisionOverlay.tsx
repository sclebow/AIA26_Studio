import React, { useMemo, useEffect } from 'react'
import * as THREE from 'three'

export interface GridViz {
  violation_cells: number[]
  warning_cells: number[]
  ox: number
  oy: number
  cols: number
  rows: number
  cs: number
}

interface CollisionOverlayProps {
  gridViz: GridViz
  center: { x: number; z: number }
}

/**
 * Build a single merged BufferGeometry from a flat array of grid cell indices.
 * Each cell becomes a small quad (90% of cell size, leaving a thin gap so
 * individual cells are distinguishable). Quads sit on the XZ plane at y = 0
 * in local space; the parent group sets the elevation.
 *
 * Layout coords → Three.js world:  layout (x, y) → world (x - center.x, 0, y - center.z)
 * Cell (col, row): layout origin = (ox + col*cs, oy + row*cs)
 */
function buildCellGeometry(
  cells: number[],
  cols: number,
  ox: number,
  oy: number,
  cs: number,
  cx: number,
  cz: number,
): THREE.BufferGeometry {
  const geo = new THREE.BufferGeometry()
  if (cells.length === 0) return geo

  const w = cs * 0.88                        // cell render size (leaves a gap)
  const pos = new Float32Array(cells.length * 12) // 4 verts × 3 floats
  const idx: number[] = []

  cells.forEach((cellIdx, i) => {
    const col = cellIdx % cols
    const row = Math.floor(cellIdx / cols)
    const x0 = ox + col * cs - cx
    const z0 = oy + row * cs - cz
    const x1 = x0 + w
    const z1 = z0 + w

    const b = i * 12
    // quad in XZ plane (y = 0 in local space)
    pos[b + 0] = x0; pos[b + 1] = 0; pos[b + 2] = z0
    pos[b + 3] = x1; pos[b + 4] = 0; pos[b + 5] = z0
    pos[b + 6] = x1; pos[b + 7] = 0; pos[b + 8] = z1
    pos[b + 9] = x0; pos[b + 10] = 0; pos[b + 11] = z1

    const v = i * 4
    idx.push(v, v + 1, v + 2, v, v + 2, v + 3)
  })

  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setIndex(idx)
  return geo
}

const CollisionOverlay: React.FC<CollisionOverlayProps> = ({ gridViz, center }) => {
  const { violation_cells, warning_cells, ox, oy, cols, cs } = gridViz

  const violationGeo = useMemo(
    () => buildCellGeometry(violation_cells, cols, ox, oy, cs, center.x, center.z),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [violation_cells, cols, ox, oy, cs, center.x, center.z],
  )

  const warningGeo = useMemo(
    () => buildCellGeometry(warning_cells, cols, ox, oy, cs, center.x, center.z),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [warning_cells, cols, ox, oy, cs, center.x, center.z],
  )

  // Dispose GPU resources when geometries change or component unmounts.
  useEffect(() => () => { violationGeo.dispose() }, [violationGeo])
  useEffect(() => () => { warningGeo.dispose() }, [warningGeo])

  return (
    // Elevate quads to sit just above the floor grid (y=0.004) and below labels.
    // No rotation needed — buildCellGeometry already places quads in the XZ plane.
    <group position={[0, 0.028, 0]}>
      {violation_cells.length > 0 && (
        <mesh geometry={violationGeo} renderOrder={2}>
          <meshBasicMaterial
            color="#ef4444"
            transparent
            opacity={0.55}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      )}
      {warning_cells.length > 0 && (
        <mesh geometry={warningGeo} renderOrder={2}>
          <meshBasicMaterial
            color="#f59e0b"
            transparent
            opacity={0.40}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      )}
    </group>
  )
}

export default React.memo(CollisionOverlay)
