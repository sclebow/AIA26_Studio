import { useEffect, useRef } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'

interface SelectionHighlightProps {
  selectedId: string | null
}

export default function SelectionHighlight({ selectedId }: SelectionHighlightProps) {
  const { scene } = useThree()
  const prevId = useRef<string | null>(null)

  useEffect(() => {
    // Reset previous selection
    if (prevId.current) {
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh && obj.userData.elementId === prevId.current) {
          const mat = obj.material as THREE.MeshStandardMaterial
          if (obj.userData._selOrigEmissive !== undefined) {
            mat.emissive.setHex(obj.userData._selOrigEmissive)
            mat.emissiveIntensity = obj.userData._selOrigEI
            delete obj.userData._selOrigEmissive
            delete obj.userData._selOrigEI
            obj.userData._isSelected = false
          }
        }
      })
    }

    if (!selectedId) {
      prevId.current = null
      return
    }

    // Apply highlight to selected mesh
    scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh && obj.userData.elementId === selectedId) {
        const mat = obj.material as THREE.MeshStandardMaterial
        if (!mat || !('emissive' in mat)) return
        // Save originals only if not already being pulsed
        if (!obj.userData._isPulsing) {
          obj.userData._selOrigEmissive = mat.emissive.getHex()
          obj.userData._selOrigEI = mat.emissiveIntensity
        }
        obj.userData._isSelected = true
        mat.emissive = new THREE.Color('#8B5CF6')
        mat.emissiveIntensity = 0.35
      }
    })

    prevId.current = selectedId
  }, [selectedId, scene])

  return null
}
