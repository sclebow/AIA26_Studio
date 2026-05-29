import { useRef } from 'react'
import { useThree, useFrame } from '@react-three/fiber'
import * as THREE from 'three'

interface PulseHighlightProps {
  modifiedIds: Set<string>
}

/**
 * Applies a pulsing emissive glow to modified/new elements.
 */
export default function PulseHighlight({ modifiedIds }: PulseHighlightProps) {
  const { scene } = useThree()
  const tracked = useRef(new Map<string, { emissive: number; ei: number }>())

  useFrame(({ clock }) => {
    if (modifiedIds.size === 0 && tracked.current.size === 0) return

    const t = clock.getElapsedTime()
    const pulse = 0.5 + 0.5 * Math.sin(t * 4.2)

    scene.traverse((obj) => {
      if (!(obj instanceof THREE.Mesh)) return
      const eid = obj.userData.elementId as string | undefined
      if (!eid) return

      const mat = obj.material as THREE.MeshStandardMaterial
      if (!mat || !('emissive' in mat)) return

      const isModified = modifiedIds.has(eid)
      const isTracked = tracked.current.has(eid)

      if (isModified) {
        if (!isTracked) {
          tracked.current.set(eid, {
            emissive: mat.emissive.getHex(),
            ei: mat.emissiveIntensity,
          })
        }
        mat.emissive.setHex(0x6B7B9E)
        mat.emissiveIntensity = 0.1 + pulse * 0.3
      } else if (isTracked) {
        const orig = tracked.current.get(eid)!
        mat.emissive.setHex(orig.emissive)
        mat.emissiveIntensity = orig.ei
        tracked.current.delete(eid)
      }
    })
  })

  return null
}
