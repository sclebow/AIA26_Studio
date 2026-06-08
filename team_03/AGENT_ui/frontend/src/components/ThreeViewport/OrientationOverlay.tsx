import React, { useMemo, useEffect, useRef } from 'react'
import * as THREE from 'three'
import type { LayoutJSON } from '../../types'

export interface OrientationResult {
  object_id: string
  name: string
  facing_ok: boolean
  angle_diff: number
  orientation_deg: number
  target_direction_deg: number
}

interface OrientationOverlayProps {
  results: OrientationResult[]
  layout: LayoutJSON
  center: { x: number; z: number }
}

const ARROW_LEN     = 1.4    // metres
const HEAD_LEN      = 0.35
const HEAD_WIDTH    = 0.22
const TARGET_SCALE  = 0.65   // target arrow is shorter than the facing arrow
const Y             = 0.06   // elevation above floor

const COLOR_OK      = new THREE.Color('#22c55e')   // green
const COLOR_WRONG   = new THREE.Color('#ef4444')   // red
const COLOR_TARGET  = new THREE.Color('#94a3b8')   // slate — "where it should face"

/** Look up an object's use_point or geometry centroid in layout coords. */
function resolvePosition(objectId: string, layout: LayoutJSON): [number, number] | null {
  const pool = [...(layout.furniture || []), ...(layout.mep || [])]
  const obj = pool.find(e => e.id === objectId) as (typeof pool[0] & { use_point?: [number, number] }) | undefined
  if (!obj) return null

  if (obj.use_point && obj.use_point.length >= 2) {
    return [obj.use_point[0], obj.use_point[1]]
  }

  const geom = obj.geometry || []
  if (geom.length === 0) return null
  const cx = geom.reduce((s, p) => s + p[0], 0) / geom.length
  const cy = geom.reduce((s, p) => s + p[1], 0) / geom.length
  return [cx, cy]
}

/**
 * Convert an orientation angle (layout convention: degrees from +X axis,
 * counterclockwise in the layout XY plane) to a Three.js world direction vector
 * on the XZ plane. Layout Y → world Z.
 */
function toWorldDir(deg: number): THREE.Vector3 {
  const rad = deg * (Math.PI / 180)
  return new THREE.Vector3(Math.cos(rad), 0, Math.sin(rad)).normalize()
}

/** Create and dispose a THREE.ArrowHelper cleanly. */
function makeArrow(dir: THREE.Vector3, origin: THREE.Vector3, length: number, color: THREE.Color, headLen: number, headWidth: number): THREE.ArrowHelper {
  return new THREE.ArrowHelper(dir, origin, length, color, headLen, headWidth)
}

function disposeArrow(a: THREE.ArrowHelper) {
  a.line.geometry.dispose()
  a.cone.geometry.dispose()
  ;(a.line.material as THREE.Material).dispose()
  ;(a.cone.material as THREE.Material).dispose()
}

const OrientationOverlay: React.FC<OrientationOverlayProps> = ({ results, layout, center }) => {
  // Build all ArrowHelper instances — one facing arrow per object,
  // plus a target arrow for objects that are facing the wrong way.
  const arrows = useMemo<THREE.ArrowHelper[]>(() => {
    const out: THREE.ArrowHelper[] = []
    for (const r of results) {
      const pos = resolvePosition(r.object_id, layout)
      if (!pos) continue

      const origin = new THREE.Vector3(pos[0] - center.x, Y, pos[1] - center.z)
      const facingDir = toWorldDir(r.orientation_deg)
      const facingColor = r.facing_ok ? COLOR_OK : COLOR_WRONG

      out.push(makeArrow(facingDir, origin, ARROW_LEN, facingColor, HEAD_LEN, HEAD_WIDTH))

      // Grey target arrow only when facing is wrong (shows where it SHOULD face).
      if (!r.facing_ok) {
        const targetDir = toWorldDir(r.target_direction_deg)
        out.push(makeArrow(
          targetDir, origin,
          ARROW_LEN * TARGET_SCALE,
          COLOR_TARGET,
          HEAD_LEN * TARGET_SCALE,
          HEAD_WIDTH * TARGET_SCALE,
        ))
      }
    }
    return out
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results, layout, center.x, center.z])

  // Dispose GPU resources when arrows change or component unmounts.
  const prevArrows = useRef<THREE.ArrowHelper[]>([])
  useEffect(() => {
    prevArrows.current.forEach(disposeArrow)
    prevArrows.current = arrows
    return () => { arrows.forEach(disposeArrow) }
  }, [arrows])

  return (
    <>
      {arrows.map((arrow, i) => (
        <primitive key={i} object={arrow} />
      ))}
    </>
  )
}

export default React.memo(OrientationOverlay)
