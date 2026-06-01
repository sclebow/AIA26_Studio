import React, { useMemo, useCallback, useState, useRef, useEffect } from 'react'
import { Canvas, useThree, useFrame } from '@react-three/fiber'
import { OrbitControls, Grid, ContactShadows } from '@react-three/drei'
import * as THREE from 'three'
import FloorPlanRenderer from './FloorPlanRenderer'
import PulseHighlight from './PulseHighlight'
import Labels3D from './Labels3D'
import ViewCube from './ViewCube'
import SelectionPanel from './SelectionPanel'
import { useTheme } from '../common/ThemeToggle'
import { LayoutJSON, LayerVisibility } from '../../types'
import type { NodeLinkData } from '../GraphPanel/graphDataMapper'

const EMPTY_SET = new Set<string>()

interface ThreeViewportProps {
  layout: LayoutJSON
  selectedId: string | null
  onSelect: (id: string | null) => void
  layers: LayerVisibility
  graphData?: NodeLinkData | null
  modifiedIds?: Set<string>
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

// ── Auto-fit: set orbit target to geometry center on layout change ─────
function BoundsFitter({ layout, onFit }: { layout: LayoutJSON; onFit: () => void }) {
  const threeState = useThree()
  const fittedRef = useRef<string | null>(null)

  useEffect(() => {
    if (fittedRef.current === layout.layoutId) return
    fittedRef.current = layout.layoutId

    const { controls } = threeState

    // Compute center of geometry
    const pts = layout.outline
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const [x, y] of pts) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x)
      minY = Math.min(minY, y); maxY = Math.max(maxY, y)
    }
    const cx = (minX + maxX) / 2
    const cz = (minY + maxY) / 2

    // Set orbit target to geometry center
    if (controls) {
      const ctrl = controls as any
      ctrl.target.set(cx, 0, cz)
      ctrl.update()
    }

    // Trigger Center view (top-front-right) after target is set
    requestAnimationFrame(() => onFit())
  }) // Runs every render but guarded by ref

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
    const offsets: Record<string, { off: [number, number, number]; up?: [number, number, number] }> = {
      top: { off: [0, dist, 0.001], up: [0, 0, -1] },
      bottom: { off: [0, -dist, 0.001], up: [0, 0, 1] },
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
    if (view.up) camera.up.set(...view.up)
    else camera.up.set(0, 1, 0)
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
        position={[0, 0.01, 0]}
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
        target={[0, 0, 0]}
      />
    </>
  )
}

export default function ThreeViewport({ layout, selectedId, onSelect, layers, graphData, modifiedIds }: ThreeViewportProps) {
  const { theme, colors } = useTheme()
  const isDark = theme === 'dark'
  const [showLabels, setShowLabels] = useState(true)
  const [isOrtho, setIsOrtho] = useState(true)
  const [viewCommand, setViewCommand] = useState<string | null>(null)
  const cameraAnglesRef = useRef({ azimuth: 0.75, elevation: 0.6 })
  const clickScreenPosRef = useRef<{ x: number; y: number } | null>(null)
  const [clickScreenPos, setClickScreenPos] = useState<{ x: number; y: number } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const viewCounter = useRef(0)

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

  const handleMissedClick = useCallback(() => {
    onSelect(null)
  }, [onSelect])

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

  const handleContainerClick = useCallback((e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (rect) {
      // Store in ref (no re-render); SelectionPanel reads it via prop only when selectedId changes
      const pos = { x: e.clientX - rect.left, y: e.clientY - rect.top }
      clickScreenPosRef.current = pos
      setClickScreenPos(pos)
    }
  }, [])

  const bgColor = isDark ? '#1a1b24' : '#ffffff'

  return (
    <div ref={containerRef} onClick={handleContainerClick} style={{ width: '100%', height: '100%', position: 'relative' }}>
      <Canvas
        camera={{ position: cameraConfig.position, fov: cameraConfig.fov, near: 0.1, far: 500 }}
        style={{ width: '100%', height: '100%', background: bgColor, transition: 'background 0.3s ease' }}
        shadows
        gl={{ antialias: true, alpha: false }}
        onPointerMissed={handleMissedClick}
      >
        <CameraTracker anglesRef={cameraAnglesRef} />
        <CameraController viewCommand={viewCommand} />
        <OrthoController isOrtho={isOrtho} />
        <BoundsFitter layout={layout} onFit={() => handleViewChange('top-front-right')} />
        <SceneContent
          layout={layout}
          selectedId={selectedId}
          onSelect={onSelect}
          layers={layers}
          isDark={isDark}
          showLabels={showLabels}
          modifiedIds={modifiedIds}
        />
      </Canvas>

      {/* Labels toggle button */}
      <button
        onClick={() => setShowLabels(v => !v)}
        title={showLabels ? 'Hide labels' : 'Show labels'}
        style={{
          position: 'absolute',
          top: 12,
          right: 468,
          zIndex: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          background: colors.panelBg,
          border: `1px solid ${showLabels ? colors.accent + '44' : colors.border}`,
          borderRadius: 8,
          padding: '5px 10px',
          color: showLabels ? colors.accent : colors.muted,
          fontSize: 9,
          fontWeight: 600,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          cursor: 'pointer',
          fontFamily: colors.font,
          transition: 'color 0.2s, border-color 0.2s',
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

      {/* Center/fit button */}
      <button
        onClick={() => handleViewChange('top-front-right')}
        title="Center geometry"
        style={{
          position: 'absolute',
          top: 12,
          right: 556,
          zIndex: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          background: colors.panelBg,
          border: `1px solid ${colors.border}`,
          borderRadius: 8,
          padding: '5px 10px',
          color: colors.muted,
          fontSize: 9,
          fontWeight: 600,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          cursor: 'pointer',
          fontFamily: colors.font,
          transition: 'color 0.2s, border-color 0.2s',
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

      {/* ViewCube + Ortho toggle */}
      <ViewCube
        onViewChange={handleViewChange}
        isOrtho={isOrtho}
        onToggleOrtho={handleToggleOrtho}
        cameraAnglesRef={cameraAnglesRef}
      />

      {/* Selection detail panel */}
      <SelectionPanel
        selectedId={selectedId}
        layout={layout}
        graphData={graphData || null}
        onClose={handleClosePanel}
        clickPosition={clickScreenPos}
      />
    </div>
  )
}
