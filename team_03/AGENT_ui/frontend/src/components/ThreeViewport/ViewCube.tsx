import React, { useCallback, useRef, useEffect, useState } from 'react'
import { useTheme } from '../common/ThemeToggle'

interface ViewCubeProps {
  onViewChange: (view: string) => void
  isOrtho: boolean
  onToggleOrtho: () => void
  /** Ref to camera angles updated by CameraTracker (never triggers re-renders) */
  cameraAnglesRef?: React.RefObject<{ azimuth: number; elevation: number }>
}

// ── 3D Cube projection with camera-relative rotation ──────────────────────

const CUBE_SIZE = 80
const S = 0.48

interface Vec3 { x: number; y: number; z: number }

function rotateY(v: Vec3, angle: number): Vec3 {
  const c = Math.cos(angle), s = Math.sin(angle)
  return { x: v.x * c + v.z * s, y: v.y, z: -v.x * s + v.z * c }
}

function rotateX(v: Vec3, angle: number): Vec3 {
  const c = Math.cos(angle), s = Math.sin(angle)
  return { x: v.x, y: v.y * c - v.z * s, z: v.y * s + v.z * c }
}

function projectPt(v: Vec3): [number, number] {
  const scale = CUBE_SIZE * 0.42
  return [v.x * scale, -v.y * scale]
}

interface FaceDef {
  name: string
  corners: Vec3[]
  label: string
  color: string
}

const FACES: FaceDef[] = [
  { name: 'top',    corners: [{x:-S,y:S,z:-S},{x:S,y:S,z:-S},{x:S,y:S,z:S},{x:-S,y:S,z:S}],     label: 'T', color: 'top' },
  { name: 'bottom', corners: [{x:-S,y:-S,z:S},{x:S,y:-S,z:S},{x:S,y:-S,z:-S},{x:-S,y:-S,z:-S}],  label: 'B', color: 'bottom' },
  { name: 'front',  corners: [{x:-S,y:S,z:S},{x:S,y:S,z:S},{x:S,y:-S,z:S},{x:-S,y:-S,z:S}],      label: 'F', color: 'front' },
  { name: 'back',   corners: [{x:S,y:S,z:-S},{x:-S,y:S,z:-S},{x:-S,y:-S,z:-S},{x:S,y:-S,z:-S}],  label: 'Bk', color: 'back' },
  { name: 'right',  corners: [{x:S,y:S,z:S},{x:S,y:S,z:-S},{x:S,y:-S,z:-S},{x:S,y:-S,z:S}],      label: 'R', color: 'right' },
  { name: 'left',   corners: [{x:-S,y:S,z:-S},{x:-S,y:S,z:S},{x:-S,y:-S,z:S},{x:-S,y:-S,z:-S}],  label: 'L', color: 'left' },
]

function faceNormal(corners: Vec3[]): Vec3 {
  const a = corners[0], b = corners[1], c = corners[2]
  const u = { x: b.x - a.x, y: b.y - a.y, z: b.z - a.z }
  const v = { x: c.x - a.x, y: c.y - a.y, z: c.z - a.z }
  return {
    x: u.y * v.z - u.z * v.y,
    y: u.z * v.x - u.x * v.z,
    z: u.x * v.y - u.y * v.x,
  }
}

const FACE_COLORS: Record<string, { fill: string; fillHover: string }> = {
  top:    { fill: 'rgba(139,92,246,0.18)', fillHover: 'rgba(139,92,246,0.30)' },
  bottom: { fill: 'rgba(139,92,246,0.05)', fillHover: 'rgba(139,92,246,0.15)' },
  front:  { fill: 'rgba(139,92,246,0.10)', fillHover: 'rgba(139,92,246,0.22)' },
  back:   { fill: 'rgba(139,92,246,0.06)', fillHover: 'rgba(139,92,246,0.18)' },
  right:  { fill: 'rgba(139,92,246,0.08)', fillHover: 'rgba(139,92,246,0.20)' },
  left:   { fill: 'rgba(139,92,246,0.06)', fillHover: 'rgba(139,92,246,0.18)' },
}

export default function ViewCube({ onViewChange, isOrtho, onToggleOrtho, cameraAnglesRef }: ViewCubeProps) {
  const { colors } = useTheme()
  const svgRef = useRef<SVGSVGElement>(null)
  const rafId = useRef(0)
  const prevAz = useRef(0)
  const prevEl = useRef(0)

  const handleFaceClick = useCallback((face: string) => {
    onViewChange(face)
  }, [onViewChange])

  // Animate cube rotation by reading the ref directly — no React state/renders
  useEffect(() => {
    const svg = svgRef.current
    if (!svg || !cameraAnglesRef) return

    const cx = CUBE_SIZE / 2
    const cy = CUBE_SIZE / 2

    function update() {
      const az = cameraAnglesRef!.current.azimuth
      const el = cameraAnglesRef!.current.elevation

      // Skip DOM update if angles haven't changed enough
      if (Math.abs(az - prevAz.current) < 0.005 && Math.abs(el - prevEl.current) < 0.005) {
        rafId.current = requestAnimationFrame(update)
        return
      }
      prevAz.current = az
      prevEl.current = el

      const transformed = FACES.map(face => {
        const rotated = face.corners.map(c => {
          let v = rotateY(c, -az)
          v = rotateX(v, -el)
          return v
        })
        const projected = rotated.map(projectPt)
        const normal = faceNormal(rotated)
        const avgZ = rotated.reduce((s, v) => s + v.z, 0) / rotated.length
        const cx2d = projected.reduce((s, p) => s + p[0], 0) / projected.length
        const cy2d = projected.reduce((s, p) => s + p[1], 0) / projected.length
        return { ...face, projected, normal, avgZ, center2d: [cx2d, cy2d], visible: normal.z < 0 }
      })

      const sorted = [...transformed].sort((a, b) => b.avgZ - a.avgZ)

      // Update SVG DOM directly
      const groups = svg!.querySelectorAll('g[data-face]')
      const orderMap = new Map(sorted.map((f, i) => [f.name, { data: f, order: i }]))

      groups.forEach(g => {
        const name = g.getAttribute('data-face')!
        const entry = orderMap.get(name)
        if (!entry) return
        const { data } = entry

        if (!data.visible) {
          ;(g as HTMLElement).style.display = 'none'
          return
        }
        ;(g as HTMLElement).style.display = ''

        const polygon = g.querySelector('polygon')
        const text = g.querySelector('text')
        if (polygon) {
          const pts = data.projected.map(([px, py]: [number, number]) => `${cx + px},${cy + py}`).join(' ')
          polygon.setAttribute('points', pts)
        }
        if (text) {
          text.setAttribute('x', String(cx + data.center2d[0]))
          text.setAttribute('y', String(cy + data.center2d[1]))
        }
      })

      // Reorder DOM elements for correct depth sorting
      const parent = svg!.querySelector('g[data-faces]')
      if (parent) {
        sorted.forEach(f => {
          const el = parent.querySelector(`g[data-face="${f.name}"]`)
          if (el) parent.appendChild(el)
        })
      }

      rafId.current = requestAnimationFrame(update)
    }

    rafId.current = requestAnimationFrame(update)
    return () => cancelAnimationFrame(rafId.current)
  }, [cameraAnglesRef])

  const initAz = cameraAnglesRef?.current.azimuth ?? 0.75
  const initEl = cameraAnglesRef?.current.elevation ?? 0.6

  // Initial face computation for first render
  const initialFaces = FACES.map(face => {
    const rotated = face.corners.map(c => {
      let v = rotateY(c, -initAz)
      v = rotateX(v, -initEl)
      return v
    })
    const projected = rotated.map(projectPt)
    const normal = faceNormal(rotated)
    const avgZ = rotated.reduce((s, v) => s + v.z, 0) / rotated.length
    const cx2d = projected.reduce((s, p) => s + p[0], 0) / projected.length
    const cy2d = projected.reduce((s, p) => s + p[1], 0) / projected.length
    return { ...face, projected, avgZ, center2d: [cx2d, cy2d], visible: normal.z < 0 }
  }).sort((a, b) => b.avgZ - a.avgZ)

  const cx = CUBE_SIZE / 2
  const cy = CUBE_SIZE / 2

  return (
    <div style={{
      position: 'absolute',
      top: 12,
      right: 370,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 6,
      zIndex: 20,
      pointerEvents: 'auto',
    }}>
      {/* Rotating View Cube */}
      <div style={{
        background: colors.panelBg,
        border: `1px solid ${colors.border}`,
        borderRadius: 10,
        padding: 4,
        width: CUBE_SIZE + 8,
        height: CUBE_SIZE + 8,
      }}>
        <svg
          ref={svgRef}
          width={CUBE_SIZE}
          height={CUBE_SIZE}
          viewBox={`0 0 ${CUBE_SIZE} ${CUBE_SIZE}`}
          style={{ display: 'block' }}
        >
          <g data-faces="">
            {initialFaces.map(face => {
              const pts = face.projected.map(([px, py]) => `${cx + px},${cy + py}`).join(' ')
              const fc = FACE_COLORS[face.color] || FACE_COLORS.front
              return (
                <g key={face.name} data-face={face.name} style={{ cursor: 'pointer', display: face.visible ? '' : 'none' }} onClick={() => handleFaceClick(face.name)}>
                  <polygon
                    points={pts}
                    fill={fc.fill}
                    stroke={colors.accent + '55'}
                    strokeWidth="0.8"
                    strokeLinejoin="round"
                  >
                    <title>{face.name}</title>
                  </polygon>
                  <text
                    x={cx + face.center2d[0]}
                    y={cy + face.center2d[1]}
                    fill={colors.accent}
                    fontSize="8"
                    fontWeight="700"
                    fontFamily="-apple-system, system-ui, sans-serif"
                    textAnchor="middle"
                    dominantBaseline="central"
                    style={{ pointerEvents: 'none', letterSpacing: '0.06em', opacity: 0.8 }}
                  >
                    {face.label}
                  </text>
                </g>
              )
            })}
          </g>
        </svg>
      </div>

      {/* Ortho/Perspective toggle */}
      <button
        onClick={onToggleOrtho}
        title={isOrtho ? 'Switch to perspective' : 'Switch to orthographic'}
        style={{
          background: isOrtho ? colors.accent + '18' : colors.panelBg,
          border: `1px solid ${isOrtho ? colors.accent + '44' : colors.border}`,
          borderRadius: 6,
          padding: '4px 10px',
          color: isOrtho ? colors.accent : colors.muted,
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          cursor: 'pointer',
          fontFamily: colors.font,
          transition: 'all 0.2s',
        }}
      >
        {isOrtho ? 'ORTHO' : 'PERSP'}
      </button>

      {/* Quick view buttons */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        background: colors.panelBg,
        border: `1px solid ${colors.border}`,
        borderRadius: 6,
        padding: 3,
      }}>
        {['top', 'front', 'right', 'back', 'left'].map(view => (
          <button
            key={view}
            onClick={() => onViewChange(view)}
            style={{
              background: 'transparent',
              border: 'none',
              color: colors.muted,
              fontSize: 8,
              fontWeight: 600,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              cursor: 'pointer',
              padding: '3px 8px',
              borderRadius: 4,
              fontFamily: colors.font,
              transition: 'color 0.15s, background 0.15s',
            }}
            onMouseEnter={e => {
              (e.target as HTMLElement).style.color = colors.accent;
              (e.target as HTMLElement).style.background = colors.accent + '15';
            }}
            onMouseLeave={e => {
              (e.target as HTMLElement).style.color = colors.muted;
              (e.target as HTMLElement).style.background = 'transparent';
            }}
          >
            {view}
          </button>
        ))}
      </div>
    </div>
  )
}
