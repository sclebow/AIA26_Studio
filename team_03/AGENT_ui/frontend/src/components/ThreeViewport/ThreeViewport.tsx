import React, { useMemo, useCallback, useState, useRef, useEffect } from 'react'
import { Canvas, useThree, useFrame } from '@react-three/fiber'
import { OrbitControls, Grid, ContactShadows } from '@react-three/drei'
import * as THREE from 'three'
import FloorPlanRenderer from './FloorPlanRenderer'
import PulseHighlight from './PulseHighlight'
import Labels3D from './Labels3D'
import ViewCube from './ViewCube'
import ObserverMarker from './ObserverMarker'
import { useTheme } from '../common/ThemeToggle'
import { LayoutJSON, LayerVisibility } from '../../types'
import type { NodeLinkData } from '../GraphPanel/graphDataMapper'

const EMPTY_SET = new Set<string>()
const PERSON_HEIGHT = 1.7

interface ThreeViewportProps {
  layout: LayoutJSON
  selectedId: string | null
  onSelect: (id: string | null) => void
  layers: LayerVisibility
  graphData?: NodeLinkData | null
  modifiedIds?: Set<string>
  /** Push the observer point to the backend (→ MCP → Grasshopper) on release. */
  onObserverPoint?: (x: number, y: number, height: number, pointStr: string) => void
  /** Push an ordered path of floor points to the backend on finish. */
  onObserverPath?: (points: Array<{ x: number; y: number }>) => void
  /** Controlled labels toggle (shared with the graph). Falls back to internal state. */
  showLabels?: boolean
  onToggleLabels?: () => void
}

interface SceneProps extends ThreeViewportProps {
  isDark: boolean
  showLabels: boolean
}

// ── Camera angle tracker — writes to a ref, never triggers re-renders ──
function CameraTracker({ anglesRef }: { anglesRef: React.MutableRefObject<{ azimuth: number; elevation: number }> }) {
  const { camera } = useThree()

  useFrame(() => {
    const pos = camera.position
    const dist = Math.sqrt(pos.x * pos.x + pos.z * pos.z)
    anglesRef.current.azimuth = Math.atan2(pos.x, pos.z)
    anglesRef.current.elevation = Math.atan2(pos.y, dist)
  })

  return null
}

// ── Exposes the live camera + renderer to the parent so DOM-level handlers
//    (e.g. click-to-place) can raycast against the floor. Updates on camera
//    swaps (ortho/persp). ──────────────────────────────────────────────────
function ViewportRefBridge({ threeRef }: { threeRef: React.MutableRefObject<{ camera: THREE.Camera; gl: THREE.WebGLRenderer } | null> }) {
  const camera = useThree(s => s.camera)
  const gl = useThree(s => s.gl)
  useEffect(() => {
    threeRef.current = { camera, gl }
  }, [camera, gl, threeRef])
  return null
}

// ── Auto-fit: center camera on layout change ───────────────────────────
function BoundsFitter({ layout }: { layout: LayoutJSON }) {
  const { camera, controls } = useThree()
  const fittedRef = useRef<object | null>(null)

  useEffect(() => {
    if (fittedRef.current === layout) return
    fittedRef.current = layout

    const pts = layout.outline
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const [x, y] of pts) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x)
      minY = Math.min(minY, y); maxY = Math.max(maxY, y)
    }
    const cx = (minX + maxX) / 2
    const cz = (minY + maxY) / 2
    const maxDim = Math.max(maxX - minX, maxY - minY)
    const dist = maxDim * 1.0

    if (!controls) return
    const ctrl = controls as any
    ctrl.target.set(cx, 0, cz)
    camera.position.set(cx + dist * 0.577, dist * 0.577, cz + dist * 0.577)
    camera.up.set(0, 1, 0)
    camera.lookAt(cx, 0, cz)
    ctrl.update()
  })

  return null
}

// ── Camera view controller — receives view commands from ViewCube ───────
function CameraController({ viewCommand }: { viewCommand: string | null }) {
  const { camera, controls } = useThree()

  useEffect(() => {
    if (!viewCommand || !controls) return
    const ctrl = controls as any
    const target = ctrl.target as THREE.Vector3
    const dist = camera.position.distanceTo(target) || 40
    const viewName = viewCommand.split('__')[0]

    // Offsets relative to the current orbit target (geometry center)
    const offsets: Record<string, { off: [number, number, number] }> = {
      top: { off: [0, dist, 0.001] },
      bottom: { off: [0, -dist, 0.001] },
      front: { off: [0, 0, dist] },
      back: { off: [0, 0, -dist] },
      right: { off: [dist, 0, 0] },
      left: { off: [-dist, 0, 0] },
      'top-front': { off: [0, dist * 0.7, dist * 0.7] },
      'top-right': { off: [dist * 0.7, dist * 0.7, 0] },
      'front-right': { off: [dist * 0.7, 0, dist * 0.7] },
      'top-front-right': { off: [dist * 0.58, dist * 0.58, dist * 0.58] },
      'top-front-left': { off: [-dist * 0.58, dist * 0.58, dist * 0.58] },
      'top-back-right': { off: [dist * 0.58, dist * 0.58, -dist * 0.58] },
      'top-back-left': { off: [-dist * 0.58, dist * 0.58, -dist * 0.58] },
    }

    const view = offsets[viewName]
    if (!view) return

    camera.position.set(
      target.x + view.off[0],
      target.y + view.off[1],
      target.z + view.off[2]
    )
    camera.up.set(0, 1, 0)
    camera.lookAt(target)
    ctrl.update()
  }, [viewCommand, camera, controls])

  return null
}

// ── Ortho/Persp switch — modifies the camera in-place ──────────────────
function OrthoController({ isOrtho }: { isOrtho: boolean }) {
  const { camera, gl, controls, set } = useThree()
  // Start as null so it runs on first mount
  const prevIsOrtho = useRef<boolean | null>(null)

  useEffect(() => {
    // Skip if value hasn't changed
    if (prevIsOrtho.current === isOrtho) return
    prevIsOrtho.current = isOrtho

    const pos = camera.position.clone()
    const target = controls ? (controls as any).target.clone() : new THREE.Vector3(0, 0, 0)
    const up = camera.up.clone()
    const canvas = gl.domElement
    const aspect = canvas.clientWidth / canvas.clientHeight

    if (isOrtho) {
      const dist = pos.distanceTo(target)
      const frustumSize = dist * 0.8
      const ortho = new THREE.OrthographicCamera(
        -frustumSize * aspect, frustumSize * aspect,
        frustumSize, -frustumSize,
        0.1, 500
      )
      ortho.position.copy(pos)
      ortho.up.copy(up)
      ortho.lookAt(target)
      ortho.updateProjectionMatrix()
      set({ camera: ortho })
    } else {
      const persp = new THREE.PerspectiveCamera(50, aspect, 0.1, 500)
      persp.position.copy(pos)
      persp.up.copy(up)
      persp.lookAt(target)
      persp.updateProjectionMatrix()
      set({ camera: persp })
    }
  }, [isOrtho, camera, gl, controls, set])

  return null
}

// ── Renderer config — ACES Filmic for dark mode, flat/no-tonemapping for light ──
function RendererConfig({ isDark }: { isDark: boolean }) {
  const { gl, scene } = useThree()
  useEffect(() => {
    if (isDark) {
      gl.toneMapping = THREE.ACESFilmicToneMapping
      gl.toneMappingExposure = 1.0
    } else {
      gl.toneMapping = THREE.NoToneMapping
      gl.toneMappingExposure = 1.0
      // Force pure white at WebGL level — bypasses R3F color management
      gl.setClearColor(0xffffff, 1)
      scene.background = new THREE.Color(0xffffff)
    }
    gl.outputColorSpace = THREE.SRGBColorSpace
  }, [gl, scene, isDark])
  return null
}

function SceneContent({ layout, selectedId, onSelect, layers, isDark, showLabels, modifiedIds }: SceneProps & { modifiedIds?: Set<string> }) {
  const bounds = useMemo(() => {
    const pts = layout.outline
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const [x, y] of pts) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x)
      minY = Math.min(minY, y); maxY = Math.max(maxY, y)
    }
    const w = maxX - minX
    const h = maxY - minY
    return { cx: (minX + maxX) / 2, cz: (minY + maxY) / 2, w, h, maxDim: Math.max(w, h) }
  }, [layout])

  const center = useMemo(() => ({ x: bounds.cx, z: bounds.cz }), [bounds])

  const bgColor = isDark ? '#1a1b24' : '#ffffff'

  return (
    <>
      {/* Renderer config */}
      <RendererConfig isDark={isDark} />

      {/* Background + fog — dark uses declarative, light uses imperative (RendererConfig) to avoid color management darkening */}
      {isDark && <color attach="background" args={[bgColor]} />}
      <fog attach="fog" args={[bgColor, 120, 280]} />

      {/* Lighting — neutral colors, strong directional for dark mode, pure white for light */}
      <ambientLight intensity={isDark ? 0.45 : 0.9} color={isDark ? '#b0b4bc' : '#ffffff'} />
      <directionalLight
        position={[bounds.w * 0.4, bounds.maxDim * 1.5, bounds.h * 0.6]}
        intensity={isDark ? 1.4 : 0.6}
        color={isDark ? '#e8e6ef' : '#ffffff'}
        castShadow={isDark}
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-left={-bounds.maxDim}
        shadow-camera-right={bounds.maxDim}
        shadow-camera-top={bounds.maxDim}
        shadow-camera-bottom={-bounds.maxDim}
        shadow-camera-near={0.5}
        shadow-camera-far={bounds.maxDim * 3}
        shadow-bias={-0.0005}
      />
      <directionalLight
        position={[-bounds.w * 0.3, bounds.maxDim * 0.5, -bounds.h * 0.5]}
        intensity={isDark ? 0.25 : 0.3}
        color={isDark ? '#8892a0' : '#ffffff'}
      />

      {/* Accent point lights — only for dark mode */}
      <pointLight
        position={[0, bounds.maxDim * 0.4, 0]}
        intensity={isDark ? 0.20 : 0}
        color={isDark ? '#a0a8b8' : '#ffffff'}
        distance={bounds.maxDim * 2.5}
        decay={2}
      />
      <pointLight
        position={[bounds.w * 0.3, 1, bounds.h * 0.3]}
        intensity={isDark ? 0.15 : 0}
        color={isDark ? '#b0a898' : '#ffffff'}
        distance={bounds.maxDim * 2}
        decay={2}
      />


      {/* Contact shadows for light mode — above ground, below grid */}
      {!isDark && (
        <ContactShadows
          position={[0, -0.05, 0]}
          opacity={0.35}
          scale={bounds.maxDim * 2}
          blur={2.5}
          far={10}
          resolution={512}
          color="#4a5568"
        />
      )}

      {/* Floor grid — above ground plane to prevent z-fighting */}
      <Grid
        args={[200, 200]}
        cellSize={1}
        cellThickness={0.5}
        cellColor={isDark ? '#1e2028' : '#e0e2e6'}
        sectionSize={5}
        sectionThickness={1}
        sectionColor={isDark ? '#282a34' : '#d0d2d6'}
        fadeDistance={100}
        fadeStrength={2.0}
        infiniteGrid
        // Sit ~6mm BELOW the room floor (which is at y=0.01) so the grid never
        // shares the floor plane — avoids z-fighting/clipping with the geometry.
        position={[0, 0.004, 0]}
      />

      {/* Floor plan */}
      <FloorPlanRenderer
        layout={layout}
        layers={layers}
        selectedId={selectedId}
        onSelect={onSelect}
        isDark={isDark}
      />

      {/* 3D Labels */}
      {showLabels && (
        <Labels3D layout={layout} isDark={isDark} center={center} />
      )}

      {/* Pulse highlight for modified/new elements */}
      <PulseHighlight modifiedIds={modifiedIds || EMPTY_SET} />

      {/* Controls */}
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.12}
        minDistance={5}
        maxDistance={150}
        maxPolarAngle={Math.PI / 2.1}
        mouseButtons={{
          LEFT: undefined as any,
          MIDDLE: THREE.MOUSE.PAN,
          RIGHT: THREE.MOUSE.ROTATE,
        }}
      />
    </>
  )
}

export default function ThreeViewport({ layout, selectedId, onSelect, layers, graphData, modifiedIds, onObserverPoint, onObserverPath, showLabels: showLabelsProp, onToggleLabels }: ThreeViewportProps) {
  const { theme, colors } = useTheme()
  const isDark = theme === 'dark'
  const [internalShowLabels, setInternalShowLabels] = useState(true)
  // Controlled by App (shared with the graph) when provided; else internal.
  const showLabels = showLabelsProp ?? internalShowLabels
  const toggleLabels = onToggleLabels ?? (() => setInternalShowLabels(v => !v))
  const [isOrtho, setIsOrtho] = useState(true)
  const [viewCommand, setViewCommand] = useState<string | null>(null)
  const [personMode, setPersonMode] = useState(false)
  const [personPos, setPersonPos] = useState<{ x: number; y: number } | null>(null)
  const [placing, setPlacing] = useState(false)
  const [pathMode, setPathMode] = useState(false)
  const [pathPoints, setPathPoints] = useState<Array<{ x: number; y: number }>>([])
  const threeRef = useRef<{ camera: THREE.Camera; gl: THREE.WebGLRenderer } | null>(null)
  const cameraAnglesRef = useRef({ azimuth: 0.75, elevation: 0.6 })
  const containerRef = useRef<HTMLDivElement>(null)
  const viewCounter = useRef(0)

  // Geometry centre — same formula as FloorPlanRenderer's centred group.
  const geoCenter = useMemo(() => {
    const pts = layout.outline
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const [x, y] of pts) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x)
      minY = Math.min(minY, y); maxY = Math.max(maxY, y)
    }
    return { x: (minX + maxX) / 2, z: (minY + maxY) / 2 }
  }, [layout])

  const cameraConfig = useMemo(() => {
    const pts = layout.outline
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const [x, y] of pts) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x)
      minY = Math.min(minY, y); maxY = Math.max(maxY, y)
    }
    const maxDim = Math.max(maxX - minX, maxY - minY)
    const dist = maxDim * 0.6
    return {
      position: [dist * 0.577, dist * 0.577, dist * 0.577] as [number, number, number],
      fov: 50,
    }
  }, [layout])

  const personStr = personPos
    ? `${personPos.x.toFixed(2)},${personPos.y.toFixed(2)},${PERSON_HEIGHT.toFixed(2)}`
    : ''

  const sendObserver = useCallback((x: number, y: number) => {
    const str = `${x.toFixed(2)},${y.toFixed(2)},${PERSON_HEIGHT.toFixed(2)}`
    onObserverPoint?.(x, y, PERSON_HEIGHT, str)
  }, [onObserverPoint])

  const handleTogglePerson = useCallback(() => {
    setPersonMode(prev => {
      const next = !prev
      // Turning it on enters placement mode (click the floor to place);
      // turning it off hides the marker.
      setPlacing(next)
      return next
    })
  }, [])

  const raycastFloor = useCallback((e: React.MouseEvent): { x: number; y: number } | null => {
    const t = threeRef.current
    if (!t) return null
    const rect = t.gl.domElement.getBoundingClientRect()
    const ndcX = ((e.clientX - rect.left) / rect.width) * 2 - 1
    const ndcY = -((e.clientY - rect.top) / rect.height) * 2 + 1
    const rc = new THREE.Raycaster()
    rc.setFromCamera(new THREE.Vector2(ndcX, ndcY), t.camera)
    const hit = new THREE.Vector3()
    if (rc.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), hit)) {
      return { x: hit.x + geoCenter.x, y: hit.z + geoCenter.z }
    }
    return null
  }, [geoCenter])

  // Click anywhere on the floor to (re)place the person.
  const handlePlacementClick = useCallback((e: React.MouseEvent) => {
    const pt = raycastFloor(e)
    if (pt) {
      setPersonPos(pt)
      sendObserver(pt.x, pt.y)
      setPlacing(false)
    }
  }, [raycastFloor, sendObserver])

  const handleObserverMove = useCallback((x: number, y: number) => {
    setPersonPos({ x, y })
  }, [])

  const handleObserverRelease = useCallback((x: number, y: number) => {
    setPersonPos({ x, y })
    sendObserver(x, y)
  }, [sendObserver])

  // While dragging the person, suppress geometry selection — otherwise the
  // synthesized click on pointer-up (over a room) would open its detail panel.
  const draggingObserverRef = useRef(false)
  const handleObserverDragStart = useCallback(() => { draggingObserverRef.current = true }, [])
  const handleObserverDragEnd = useCallback(() => {
    // Keep the guard up briefly so the trailing click is swallowed too.
    setTimeout(() => { draggingObserverRef.current = false }, 150)
  }, [])
  const guardedSelect = useCallback((id: string | null) => {
    if (draggingObserverRef.current) return
    onSelect(id)
  }, [onSelect])

  const handleCopyPersonStr = useCallback(() => {
    if (personStr) navigator.clipboard?.writeText(personStr).catch(() => {})
  }, [personStr])

  const handleMissedClick = useCallback(() => {
    if (draggingObserverRef.current) return
    onSelect(null)
  }, [onSelect])

  const finishPath = useCallback(() => {
    if (pathPoints.length >= 2) onObserverPath?.(pathPoints)
    setPathMode(false)   // keep points → ghost remains visible
  }, [pathPoints, onObserverPath])

  const handlePathClick = useCallback((e: React.MouseEvent) => {
    if (e.detail > 1) return
    const pt = raycastFloor(e)
    if (pt) setPathPoints(prev => [...prev, pt])
  }, [raycastFloor])

  const handlePathDoubleClick = useCallback((e: React.MouseEvent) => {
    if (pathPoints.length >= 2) {
      onObserverPath?.(pathPoints)
      setPathMode(false) // keep points → ghost remains visible
    }
  }, [pathPoints, onObserverPath])

  const handleTogglePath = useCallback(() => {
    setPathMode(prev => {
      const next = !prev
      if (next) {
        setPersonMode(false)
        setPlacing(false)
        // Keep existing pathPoints so user resumes where they left off
      }
      // Turning OFF: keep points so ghost persists
      return next
    })
  }, [])

  const handleUpdatePathPoint = useCallback((index: number, x: number, y: number) => {
    setPathPoints(prev => prev.map((pt, i) => i === index ? { x, y } : pt))
  }, [])

  const handleReleasePathPoint = useCallback((index: number, x: number, y: number) => {
    setPathPoints(prev => {
      const updated = prev.map((pt, i) => i === index ? { x, y } : pt)
      if (updated.length >= 2) onObserverPath?.(updated)
      return updated
    })
  }, [onObserverPath])

  useEffect(() => {
    if (!pathMode) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setPathPoints([]); setPathMode(false) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [pathMode])

  const handleViewChange = useCallback((view: string) => {
    viewCounter.current++
    setViewCommand(view + '__' + viewCounter.current)
  }, [])

  const handleToggleOrtho = useCallback(() => {
    setIsOrtho(prev => !prev)
  }, [])

  const handleClosePanel = useCallback(() => {
    onSelect(null)
  }, [onSelect])


  const bgColor = isDark ? '#1a1b24' : '#ffffff'

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
      <Canvas
        camera={{ position: cameraConfig.position, fov: cameraConfig.fov, near: 0.1, far: 500 }}
        style={{ width: '100%', height: '100%', background: bgColor, transition: 'background 0.3s ease' }}
        shadows
        gl={{ antialias: true, alpha: false }}
        onPointerMissed={handleMissedClick}
      >
        <CameraTracker anglesRef={cameraAnglesRef} />
        <ViewportRefBridge threeRef={threeRef} />
        <CameraController viewCommand={viewCommand} />
        <OrthoController isOrtho={isOrtho} />
        <BoundsFitter layout={layout} />
        <SceneContent
          layout={layout}
          selectedId={selectedId}
          onSelect={guardedSelect}
          layers={layers}
          isDark={isDark}
          showLabels={showLabels}
          modifiedIds={modifiedIds}
        />
        {personPos && (
          <ObserverMarker
            center={geoCenter}
            position={personPos}
            isDark={isDark}
            ghost={!personMode}
            onMove={personMode ? handleObserverMove : () => {}}
            onRelease={personMode ? handleObserverRelease : () => {}}
            onDragStart={personMode ? handleObserverDragStart : undefined}
            onDragEnd={personMode ? handleObserverDragEnd : undefined}
          />
        )}
        {pathPoints.length > 0 && (
          <ObserverMarker
            center={geoCenter}
            position={{ x: 0, y: 0 }}
            isDark={isDark}
            ghost={!pathMode}
            onMove={() => {}}
            onRelease={() => {}}
            pathMode
            pathPoints={pathPoints}
            onUpdatePathPoint={handleUpdatePathPoint}
            onReleasePathPoint={handleReleasePathPoint}
          />
        )}
      </Canvas>

      {/* Placement overlay — while picking a spot, capture clicks here so the
          viewport geometry (and orbit/deselect) never react to the click. */}
      {personMode && placing && (
        <div
          onClick={handlePlacementClick}
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 15,
            cursor: 'crosshair',
          }}
        />
      )}

      {/* Path drawing overlay — captures all clicks while path mode is active. */}
      {pathMode && (
        <div
          onClick={handlePathClick}
          onDoubleClick={handlePathDoubleClick}
          style={{
            position: 'absolute',
            inset: 0,
            zIndex: 15,
            cursor: 'crosshair',
          }}
        />
      )}

      {/* Compact controls row — top-right, left of ViewCube */}
      <div style={{
        position: 'absolute',
        top: 12,
        right: 102,
        zIndex: 20,
        display: 'flex',
        flexDirection: 'row',
        gap: 4,
        alignItems: 'center',
      }}>
        {/* Clear path — only visible when path exists */}
        {pathPoints.length > 0 && (
          <button
            onClick={() => setPathPoints([])}
            title="Clear path"
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              background: colors.panelBg,
              border: `1px solid ${colors.border}`,
              borderRadius: 8, padding: '5px 8px',
              color: colors.muted, fontSize: 9, fontWeight: 600,
              letterSpacing: '0.04em', textTransform: 'uppercase',
              cursor: 'pointer', fontFamily: colors.font,
              transition: 'color 0.2s, border-color 0.2s',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = '#ef4444'; (e.currentTarget as HTMLElement).style.borderColor = '#ef4444' }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = colors.muted; (e.currentTarget as HTMLElement).style.borderColor = colors.border }}
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}

        {/* Path toggle */}
        <button
          onClick={handleTogglePath}
          title={pathMode ? 'Pause path drawing' : pathPoints.length > 0 ? 'Resume path drawing' : 'Draw an observer path (click points, dbl-click to finish)'}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: colors.panelBg,
            border: `1px solid ${pathMode ? colors.accent + '44' : colors.border}`,
            borderRadius: 8, padding: '5px 10px',
            color: pathMode ? colors.accent : colors.muted,
            fontSize: 9, fontWeight: 600, letterSpacing: '0.04em',
            textTransform: 'uppercase', cursor: 'pointer',
            fontFamily: colors.font, transition: 'color 0.2s, border-color 0.2s',
          }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="4" cy="20" r="2" fill="currentColor" stroke="none" />
            <circle cx="12" cy="4" r="2" fill="currentColor" stroke="none" />
            <circle cx="20" cy="14" r="2" fill="currentColor" stroke="none" />
            <path d="M5.5 18.5L10.5 5.5M13.5 5.5L18.5 12.5" />
          </svg>
          {pathMode ? 'Path ON' : 'Path'}
        </button>

        {/* Person toggle */}
        <button
          onClick={handleTogglePerson}
          title={personMode ? 'Hide observer point' : 'Place a draggable 1.7m person'}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: colors.panelBg,
            border: `1px solid ${personMode ? colors.accent + '44' : colors.border}`,
            borderRadius: 8, padding: '5px 10px',
            color: personMode ? colors.accent : colors.muted,
            fontSize: 9, fontWeight: 600, letterSpacing: '0.04em',
            textTransform: 'uppercase', cursor: 'pointer',
            fontFamily: colors.font, transition: 'color 0.2s, border-color 0.2s',
          }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="6" r="3" />
            <path d="M12 9v8" /><path d="M8 13h8" /><path d="M9 21l3-4 3 4" />
          </svg>
          {personMode ? 'Person ON' : 'Person'}
        </button>

        {/* Center/fit */}
        <button
          onClick={() => handleViewChange('top-front-right')}
          title="Center geometry"
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: colors.panelBg,
            border: `1px solid ${colors.border}`,
            borderRadius: 8, padding: '5px 10px',
            color: colors.muted,
            fontSize: 9, fontWeight: 600, letterSpacing: '0.04em',
            textTransform: 'uppercase', cursor: 'pointer',
            fontFamily: colors.font, transition: 'color 0.2s, border-color 0.2s',
          }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <circle cx="12" cy="12" r="3" />
            <line x1="12" y1="2" x2="12" y2="6" />
            <line x1="12" y1="18" x2="12" y2="22" />
            <line x1="2" y1="12" x2="6" y2="12" />
            <line x1="18" y1="12" x2="22" y2="12" />
          </svg>
          Center
        </button>

        {/* Labels toggle */}
        <button
          onClick={toggleLabels}
          title={showLabels ? 'Hide labels' : 'Show labels'}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: colors.panelBg,
            border: `1px solid ${showLabels ? colors.accent + '44' : colors.border}`,
            borderRadius: 8, padding: '5px 10px',
            color: showLabels ? colors.accent : colors.muted,
            fontSize: 9, fontWeight: 600, letterSpacing: '0.04em',
            textTransform: 'uppercase', cursor: 'pointer',
            fontFamily: colors.font, transition: 'color 0.2s, border-color 0.2s',
          }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 7V5a2 2 0 012-2h2" /><path d="M17 3h2a2 2 0 012 2v2" />
            <path d="M21 17v2a2 2 0 01-2 2h-2" /><path d="M7 21H5a2 2 0 01-2-2v-2" />
            <line x1="7" y1="12" x2="17" y2="12" /><line x1="7" y1="8" x2="13" y2="8" />
            <line x1="7" y1="16" x2="15" y2="16" />
          </svg>
          {showLabels ? 'Labels ON' : 'Labels'}
        </button>
      </div>

      {/* ViewCube + Ortho toggle */}
      <ViewCube
        onViewChange={handleViewChange}
        isOrtho={isOrtho}
        onToggleOrtho={handleToggleOrtho}
        cameraAnglesRef={cameraAnglesRef}
      />

      {/* Selection detail panel */}
      {/* Path HUD — mutually exclusive with observer point HUD (personMode and pathMode can't both be true) */}
      {pathMode && (
        <div style={{
          position: 'absolute',
          bottom: 16,
          left: 16,
          zIndex: 240,
          background: colors.panelBg,
          border: `1px solid ${colors.accent}44`,
          borderRadius: 10,
          padding: '10px 12px',
          fontFamily: colors.font,
          minWidth: 210,
          boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
        }}>
          <div style={{
            fontSize: 9,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: colors.accent,
            marginBottom: 6,
          }}>
            Observer Path
          </div>
          <div style={{ fontSize: 11, color: colors.text, marginBottom: 6 }}>
            {pathPoints.length} point{pathPoints.length !== 1 ? 's' : ''} placed
          </div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
            {pathPoints.length >= 2 && (
              <button
                onClick={finishPath}
                style={{
                  flex: 1,
                  padding: '4px 8px',
                  borderRadius: 6,
                  border: `1px solid ${colors.accent}`,
                  background: colors.accentDim,
                  color: colors.accent,
                  fontSize: 9,
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                  cursor: 'pointer',
                  fontFamily: colors.font,
                }}
              >
                Done
              </button>
            )}
            {pathPoints.length > 0 && (
              <button
                onClick={() => setPathPoints([])}
                style={{
                  flex: 1,
                  padding: '4px 8px',
                  borderRadius: 6,
                  border: `1px solid ${colors.border}`,
                  background: 'transparent',
                  color: colors.muted,
                  fontSize: 9,
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                  cursor: 'pointer',
                  fontFamily: colors.font,
                }}
              >
                Clear
              </button>
            )}
          </div>
          <div style={{ fontSize: 8.5, color: colors.muted, letterSpacing: '0.02em' }}>
            {pathPoints.length < 2
              ? 'Click to add points. Dbl-click or Done (min 2 pts).'
              : 'Click to add more. Dbl-click or Done to finish. Esc to cancel.'}
          </div>
        </div>
      )}

      {/* Observer point output HUD — high z-index so floating panels never cover it */}
      {personMode && (
        <div style={{
          position: 'absolute',
          bottom: 16,
          left: 16,
          zIndex: 240,
          background: colors.panelBg,
          border: `1px solid ${colors.accent}44`,
          borderRadius: 10,
          padding: '10px 12px',
          fontFamily: colors.font,
          minWidth: 210,
          boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
        }}>
          <div style={{
            fontSize: 9,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: colors.accent,
            marginBottom: 6,
          }}>
            Observer Point (person 1.7m)
          </div>
          {personPos ? (
            <>
              <div style={{ display: 'flex', gap: 12, fontSize: 11, color: colors.text, marginBottom: 6 }}>
                <span>X <b>{personPos.x.toFixed(2)}</b></span>
                <span>Y <b>{personPos.y.toFixed(2)}</b></span>
                <span style={{ color: colors.muted }}>h 1.70</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <code style={{
                  flex: 1,
                  fontSize: 11,
                  padding: '4px 6px',
                  borderRadius: 6,
                  background: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)',
                  color: colors.text,
                  userSelect: 'all',
                }}>
                  "{personStr}"
                </code>
                <button
                  onClick={handleCopyPersonStr}
                  title="Copy string"
                  style={{
                    background: 'transparent',
                    border: `1px solid ${colors.border}`,
                    borderRadius: 6,
                    padding: '4px 6px',
                    color: colors.muted,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                </button>
              </div>
              <div style={{ fontSize: 8.5, color: colors.muted, marginTop: 6, letterSpacing: '0.02em' }}>
                {placing ? 'Click on the floor to place.' : 'Drag the figure, or toggle again to re-place. Sent to MCP on release.'}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 11, color: colors.muted, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                background: colors.accent, boxShadow: `0 0 6px ${colors.accent}`,
              }} />
              Click on the floor to place the person.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
