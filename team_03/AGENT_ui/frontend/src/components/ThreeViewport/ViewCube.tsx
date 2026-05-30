import React, { useCallback, useRef, useEffect } from 'react'
import { useTheme } from '../common/ThemeToggle'

interface ViewCubeProps {
  onViewChange: (view: string) => void
  isOrtho: boolean
  onToggleOrtho: () => void
  /** Ref to camera angles updated by CameraTracker (never triggers re-renders) */
  cameraAnglesRef?: React.RefObject<{ azimuth: number; elevation: number }>
  /** Drag-to-orbit: called with absolute azimuth/elevation while dragging the cube. */
  onOrbitDrag?: (azimuth: number, elevation: number) => void
}

// ── 3D Cube projected with the camera's actual basis so it matches the view ──

const CUBE_SIZE = 80
const S = 0.48
const PROJ = CUBE_SIZE * 0.42

interface Vec3 { x: number; y: number; z: number }

const dot = (a: Vec3, b: Vec3) => a.x * b.x + a.y * b.y + a.z * b.z
const cross = (a: Vec3, b: Vec3): Vec3 => ({
  x: a.y * b.z - a.z * b.y,
  y: a.z * b.x - a.x * b.z,
  z: a.x * b.y - a.y * b.x,
})
const norm = (a: Vec3): Vec3 => {
  const m = Math.hypot(a.x, a.y, a.z) || 1
  return { x: a.x / m, y: a.y / m, z: a.z / m }
}

// Camera basis from orbit angles — must match CameraTracker:
// azimuth = atan2(pos.x, pos.z), elevation = atan2(pos.y, horizontalDist).
function cameraBasis(az: number, el: number): { r: Vec3; u: Vec3; f: Vec3 } {
  const dir: Vec3 = {
    x: Math.cos(el) * Math.sin(az),
    y: Math.sin(el),
    z: Math.cos(el) * Math.cos(az),
  }
  const f: Vec3 = { x: -dir.x, y: -dir.y, z: -dir.z } // view direction (toward target)
  // Avoid a degenerate cross product when looking straight up/down.
  const worldUp: Vec3 = Math.abs(f.y) > 0.999 ? { x: 0, y: 0, z: 1 } : { x: 0, y: 1, z: 0 }
  const r = norm(cross(f, worldUp))
  const u = cross(r, f) // unit (r ⟂ f)
  return { r, u, f }
}

interface FaceDef {
  name: string
  corners: Vec3[]
  normal: Vec3
  label: string
  color: string
}

const FACES: FaceDef[] = [
  { name: 'top',    corners: [{x:-S,y:S,z:-S},{x:S,y:S,z:-S},{x:S,y:S,z:S},{x:-S,y:S,z:S}],     normal: {x:0,y:1,z:0},  label: 'T',  color: 'top' },
  { name: 'bottom', corners: [{x:-S,y:-S,z:S},{x:S,y:-S,z:S},{x:S,y:-S,z:-S},{x:-S,y:-S,z:-S}],  normal: {x:0,y:-1,z:0}, label: 'B',  color: 'bottom' },
  { name: 'front',  corners: [{x:-S,y:S,z:S},{x:S,y:S,z:S},{x:S,y:-S,z:S},{x:-S,y:-S,z:S}],      normal: {x:0,y:0,z:1},  label: 'F',  color: 'front' },
  { name: 'back',   corners: [{x:S,y:S,z:-S},{x:-S,y:S,z:-S},{x:-S,y:-S,z:-S},{x:S,y:-S,z:-S}],  normal: {x:0,y:0,z:-1}, label: 'Bk', color: 'back' },
  { name: 'right',  corners: [{x:S,y:S,z:S},{x:S,y:S,z:-S},{x:S,y:-S,z:-S},{x:S,y:-S,z:S}],      normal: {x:1,y:0,z:0},  label: 'R',  color: 'right' },
  { name: 'left',   corners: [{x:-S,y:S,z:-S},{x:-S,y:S,z:S},{x:-S,y:-S,z:S},{x:-S,y:-S,z:-S}],  normal: {x:-1,y:0,z:0}, label: 'L',  color: 'left' },
]

// Project a cube point onto the screen using the camera basis. SVG y grows down,
// so screen-up (the camera up vector) maps to negative y.
function project(v: Vec3, b: { r: Vec3; u: Vec3; f: Vec3 }): { x: number; y: number; depth: number } {
  return { x: dot(v, b.r) * PROJ, y: -dot(v, b.u) * PROJ, depth: dot(v, b.f) }
}

interface ComputedFace extends FaceDef {
  pts: { x: number; y: number }[]
  center2d: [number, number]
  avgDepth: number
  visible: boolean
}

function computeFaces(az: number, el: number): ComputedFace[] {
  const b = cameraBasis(az, el)
  return FACES.map(face => {
    const projected = face.corners.map(c => project(c, b))
    const pts = projected.map(p => ({ x: p.x, y: p.y }))
    const avgDepth = projected.reduce((s, p) => s + p.depth, 0) / projected.length
    const cx2d = pts.reduce((s, p) => s + p.x, 0) / pts.length
    const cy2d = pts.reduce((s, p) => s + p.y, 0) / pts.length
    // Front-facing when the face normal points back toward the camera.
    const visible = dot(face.normal, b.f) < -0.0001
    return { ...face, pts, center2d: [cx2d, cy2d] as [number, number], avgDepth, visible }
  }).sort((a, b2) => b2.avgDepth - a.avgDepth) // farthest first
}

const FACE_COLORS: Record<string, { fill: string; fillHover: string }> = {
  top:    { fill: 'rgba(139,92,246,0.18)', fillHover: 'rgba(139,92,246,0.30)' },
  bottom: { fill: 'rgba(139,92,246,0.05)', fillHover: 'rgba(139,92,246,0.15)' },
  front:  { fill: 'rgba(139,92,246,0.10)', fillHover: 'rgba(139,92,246,0.22)' },
  back:   { fill: 'rgba(139,92,246,0.06)', fillHover: 'rgba(139,92,246,0.18)' },
  right:  { fill: 'rgba(139,92,246,0.08)', fillHover: 'rgba(139,92,246,0.20)' },
  left:   { fill: 'rgba(139,92,246,0.06)', fillHover: 'rgba(139,92,246,0.18)' },
}

const EL_MIN = 0.09
const EL_MAX = 1.50
const DRAG_SENS = 0.011

export default function ViewCube({ onViewChange, isOrtho, onToggleOrtho, cameraAnglesRef, onOrbitDrag }: ViewCubeProps) {
  const { colors } = useTheme()
  const svgRef = useRef<SVGSVGElement>(null)
  const rafId = useRef(0)
  const prevAz = useRef(NaN)
  const prevEl = useRef(NaN)
  const drag = useRef<{ startX: number; startY: number; az: number; el: number; moved: boolean } | null>(null)
  const justDragged = useRef(false)

  const handleFaceClick = useCallback((face: string) => {
    if (justDragged.current) { justDragged.current = false; return }
    onViewChange(face)
  }, [onViewChange])

  const cx = CUBE_SIZE / 2
  const cy = CUBE_SIZE / 2

  // Animate cube by reading the angles ref directly — no React state/renders.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg || !cameraAnglesRef) return

    function update() {
      const az = cameraAnglesRef!.current.azimuth
      const el = cameraAnglesRef!.current.elevation

      if (Math.abs(az - prevAz.current) < 0.004 && Math.abs(el - prevEl.current) < 0.004) {
        rafId.current = requestAnimationFrame(update)
        return
      }
      prevAz.current = az
      prevEl.current = el

      const faces = computeFaces(az, el)
      const parent = svg!.querySelector('g[data-faces]')

      faces.forEach(data => {
        const g = svg!.querySelector(`g[data-face="${data.name}"]`) as SVGGElement | null
        if (!g) return
        if (!data.visible) { g.style.display = 'none'; return }
        g.style.display = ''
        const polygon = g.querySelector('polygon')
        const text = g.querySelector('text')
        if (polygon) {
          polygon.setAttribute('points', data.pts.map(p => `${cx + p.x},${cy + p.y}`).join(' '))
        }
        if (text) {
          text.setAttribute('x', String(cx + data.center2d[0]))
          text.setAttribute('y', String(cy + data.center2d[1]))
        }
        if (parent) parent.appendChild(g) // re-append in farthest-first order
      })

      rafId.current = requestAnimationFrame(update)
    }

    rafId.current = requestAnimationFrame(update)
    return () => cancelAnimationFrame(rafId.current)
  }, [cameraAnglesRef, cx, cy])

  // ── Drag-to-orbit ───────────────────────────────────────────────────────
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    const az = cameraAnglesRef?.current.azimuth ?? 0.75
    const el = cameraAnglesRef?.current.elevation ?? 0.6
    drag.current = { startX: e.clientX, startY: e.clientY, az, el, moved: false }
    svgRef.current?.setPointerCapture?.(e.pointerId)
  }, [cameraAnglesRef])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const ds = drag.current
    if (!ds) return
    const dx = e.clientX - ds.startX
    const dy = e.clientY - ds.startY
    if (!ds.moved && Math.hypot(dx, dy) < 4) return
    ds.moved = true
    justDragged.current = true
    const az = ds.az - dx * DRAG_SENS
    const el = Math.max(EL_MIN, Math.min(EL_MAX, ds.el + dy * DRAG_SENS))
    onOrbitDrag?.(az, el)
  }, [onOrbitDrag])

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    drag.current = null
    svgRef.current?.releasePointerCapture?.(e.pointerId)
    // justDragged stays true so the trailing click is swallowed, then resets.
    if (justDragged.current) setTimeout(() => { justDragged.current = false }, 0)
  }, [])

  // First render uses the current/default angles.
  const initAz = cameraAnglesRef?.current.azimuth ?? 0.75
  const initEl = cameraAnglesRef?.current.elevation ?? 0.6
  const initialFaces = computeFaces(initAz, initEl)

  return (
    <div style={{
      position: 'relative',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 6,
      pointerEvents: 'auto',
    }}>
      {/* Rotating View Cube — drag to orbit, click a face to snap. */}
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
          style={{ display: 'block', cursor: 'grab', touchAction: 'none' }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <g data-faces="">
            {initialFaces.map(face => {
              const pts = face.pts.map(p => `${cx + p.x},${cy + p.y}`).join(' ')
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
          fontSize: 10,
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
              fontSize: 10,
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
