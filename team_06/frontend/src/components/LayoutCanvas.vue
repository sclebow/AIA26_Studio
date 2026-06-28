<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { Stage, Layer, Group, Line, Text } from 'vue-konva'
import { getRoomColor, getRoomSecondaryLabel, TOD_COLORS, getRoomDisplayName, hexToRgba, toNumericValue } from '../utils/roomAnalysis.js'
import catWhiteUrl from '../assets/icons/cat-white.svg'
import dogWhiteUrl from '../assets/icons/dog-white.svg'
import userWhiteUrl from '../assets/icons/user-white.svg'

const ROOM_ALPHA = 0.30
const CIRCLE_ALPHA = 0.95

const wrapperRef = ref(null)
const hoveredRoom = ref(null)
const tooltipX = ref(0)
const tooltipY = ref(0)

function onRoomHover(konvaEvent, room) {
  if (props.viewMode === 'routine') return
  const { clientX, clientY } = konvaEvent.evt
  const rect = wrapperRef.value?.getBoundingClientRect()
  if (!rect) return
  hoveredRoom.value = room
  tooltipX.value = clientX - rect.left + 14
  tooltipY.value = clientY - rect.top + 14
  emit('roomHover', room.id)
}

function onRoomLeave() {
  hoveredRoom.value = null
  emit('roomLeave')
}

const props = defineProps({
  layout:        { type: Object, default: null },
  viewMode:      { type: String, default: 'layout' },
  activeRooms:   { type: Object, default: () => ({}) },
  activeStep:    { type: Number, default: 0 },
  hoveredRoomId: { type: String, default: null },
})
const emit = defineEmits(['roomHover', 'roomLeave'])

const CIRCLE_RADIUS = 14
const CIRCLE_SPACING = 32  // horizontal gap between circles when multiple personas
const CIRCLE_ICON_SIZE = 14

const stageConfig = ref({ width: 600, height: 600 })
const iconImages = ref({ person: null, cat: null, dog: null })

function inferKind(name) {
  const n = (name || '').toLowerCase()
  if (/\b(dog|puppy|hound)\b/.test(n)) return 'dog'
  if (/\b(cat|kitty|feline)\b/.test(n)) return 'cat'
  return 'person'
}

function loadIcon(src) {
  return new Promise(resolve => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null)
    img.src = src
  })
}

let resizeObserver = null
onMounted(async () => {
  if (!wrapperRef.value) return
  resizeObserver = new ResizeObserver(entries => {
    const { width, height } = entries[0]?.contentRect ?? {}
    if (width > 0 && height > 0) stageConfig.value = { width: Math.floor(width), height: Math.floor(height) }
  })
  resizeObserver.observe(wrapperRef.value)
  const rect = wrapperRef.value.getBoundingClientRect()
  if (rect.width > 0 && rect.height > 0) stageConfig.value = { width: Math.floor(rect.width), height: Math.floor(rect.height) }

  const [person, cat, dog] = await Promise.all([
    loadIcon(userWhiteUrl),
    loadIcon(catWhiteUrl),
    loadIcon(dogWhiteUrl),
  ])
  iconImages.value = { person, cat, dog }
})
onUnmounted(() => {
  resizeObserver?.disconnect()
  stopFlux()
})




// --- Watcher-based geometry/scaling logic ---
const allPoints = ref([])
const minX = ref(0)
const maxX = ref(0)
const minY = ref(0)
const maxY = ref(0)
const layoutWidth = ref(0)
const layoutHeight = ref(0)
const scale = ref(60)
const offset = ref({ x: 0, y: 0 })

function recalcGeometry() {
  const rooms = props.layout?.rooms || [];
  const outline = props.layout?.outline || [];
  // Use room geometry if available, fall back to outline for bounds calculation
  const sourcePoints = rooms.length > 0
    ? rooms.flatMap(room => room.geometry)
    : outline
  allPoints.value = sourcePoints;
  if (allPoints.value.length > 0) {
    const xs = allPoints.value.map(pt => pt[0]);
    const ys = allPoints.value.map(pt => pt[1]);
    minX.value = Math.min(...xs);
    maxX.value = Math.max(...xs);
    minY.value = Math.min(...ys);
    maxY.value = Math.max(...ys);
    layoutWidth.value = maxX.value - minX.value;
    layoutHeight.value = maxY.value - minY.value;
    if (layoutWidth.value === 0 || layoutHeight.value === 0) {
      scale.value = 60;
      offset.value = { x: 0, y: 0 };
      console.warn('LayoutCanvas: degenerate geometry (line or point), using scale=60 and offset=0');
    } else {
      const scaleX = (stageConfig.value.width - 40) / layoutWidth.value;
      const scaleY = (stageConfig.value.height - 40) / layoutHeight.value;
      scale.value = Math.min(scaleX, scaleY, 60);
      offset.value = {
        x: (stageConfig.value.width - layoutWidth.value * scale.value) / 2 - minX.value * scale.value,
        y: (stageConfig.value.height - layoutHeight.value * scale.value) / 2 - minY.value * scale.value
      };
    }
  } else {
    minX.value = maxX.value = minY.value = maxY.value = layoutWidth.value = layoutHeight.value = 0;
    scale.value = 60;
    offset.value = { x: 0, y: 0 };
    console.warn('LayoutCanvas: no geometry points found');
  }
  console.log('LayoutCanvas DEBUG', {
    minX: minX.value, maxX: maxX.value, minY: minY.value, maxY: maxY.value,
    layoutWidth: layoutWidth.value, layoutHeight: layoutHeight.value,
    scale: scale.value, offset: offset.value, allPoints: allPoints.value
  });
}

watch([() => props.layout, stageConfig], recalcGeometry, { immediate: true, deep: true })

// Returns true if `pt` lies on any segment in `facadeList`
function _pointOnFacadeSegments(pt, facadeList) {
  const tol = 0.05
  for (const f of facadeList) {
    const geom = f.geometry || []
    for (let i = 0; i < geom.length - 1; i++) {
      const [ax, ay] = geom[i], [bx, by] = geom[i + 1]
      const dx = bx - ax, dy = by - ay
      const len = Math.hypot(dx, dy)
      if (len < tol) continue
      const cross = Math.abs((pt[0] - ax) * dy - (pt[1] - ay) * dx)
      if (cross > tol * len) continue
      const dot = (pt[0] - ax) * dx + (pt[1] - ay) * dy
      if (dot >= -tol * len && dot <= len * len + tol * len) return true
    }
  }
  return false
}

// Boundary rendering data: fill polygon + per-edge solid/dashed lines
const boundaryData = computed(() => {
  const outline = props.layout?.outline
  if (!outline || (props.layout?.rooms?.length ?? 0) > 0) return null
  const isClosed = outline.length > 2 &&
    outline[0][0] === outline[outline.length - 1][0] &&
    outline[0][1] === outline[outline.length - 1][1]
  const pts = isClosed ? outline.slice(0, -1) : outline
  const facades = props.layout?.facades || []
  const solidEdges = [], dashedEdges = []
  for (let i = 0; i < pts.length; i++) {
    const p1 = pts[i], p2 = pts[(i + 1) % pts.length]
    const mid = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2]
    const edge = { key: `edge-${i}`, points: flattenAndScale([p1, p2]) }
    if (_pointOnFacadeSegments(mid, facades)) dashedEdges.push(edge)
    else solidEdges.push(edge)
  }
  return { fillPoints: flattenAndScale(pts), solidEdges, dashedEdges }
})

const boundaryCirculationData = computed(() => {
  if ((props.layout?.rooms?.length ?? 0) > 0) return []
  const outline = props.layout?.outline || []
  const circs = props.layout?.circulation || []
  if (!circs.length) return []
  const raw = outline.length > 2 &&
    outline[0][0] === outline[outline.length - 1][0] &&
    outline[0][1] === outline[outline.length - 1][1]
    ? outline.slice(0, -1) : outline
  const cx = raw.reduce((s, p) => s + p[0], 0) / (raw.length || 1)
  const cy = raw.reduce((s, p) => s + p[1], 0) / (raw.length || 1)
  return circs.map((c, i) => {
    const geom = c.geometry
    if (!geom || geom.length < 2) return null
    const [p1, p2] = geom
    const mx = (p1[0] + p2[0]) / 2
    const my = (p1[1] + p2[1]) / 2
    const dx = p2[0] - p1[0], dy = p2[1] - p1[1]
    const len = Math.hypot(dx, dy)
    if (len === 0) return null
    const candA = [-dy, dx]
    const inward = (candA[0] * (cx - mx) + candA[1] * (cy - my) > 0) ? candA : [dy, -dx]
    const rotation = Math.atan2(inward[1], inward[0]) * 180 / Math.PI + 90
    return {
      key: `circ-${i}`,
      x: mx * scale.value + offset.value.x,
      y: my * scale.value + offset.value.y,
      rotation,
    }
  }).filter(Boolean)
})

// Computed room render data — explicitly tracks props.viewMode so Vue re-evaluates
// when the toggle changes, even inside vue-konva's non-VDOM rendering path.
const roomRenderData = computed(() => {
  const rooms = props.layout?.rooms || []
  const vm = props.viewMode
  const todHex = vm === 'routine' ? TOD_COLORS[props.activeStep] ?? TOD_COLORS[0] : null
  const occupiedIds = vm === 'routine'
    ? new Set(Object.keys(props.activeRooms || {}).filter(id => props.activeRooms[id]?.length > 0))
    : null
  const hovered = props.hoveredRoomId
  return rooms.map(room => {
    const rid = String(room.id)
    const isHovered = rid === hovered
    const isOccupied = occupiedIds?.size > 0 && occupiedIds.has(rid)
    let alpha
    if (vm === 'routine' && occupiedIds) {
      alpha = occupiedIds.size > 0 ? (isOccupied ? ROOM_ALPHA : ROOM_ALPHA * 0.25) : ROOM_ALPHA
    } else if (hovered && !isHovered) {
      alpha = ROOM_ALPHA * 0.25
    } else {
      alpha = ROOM_ALPHA
    }
    const baseColor = todHex ?? getRoomColor(room, vm)
    return {
      id: room.id,
      points: flattenAndScale(room.geometry),
      fill: hexToRgba(baseColor, alpha),
      stroke: isHovered ? '#222' : isOccupied ? '#222' : '#555',
      strokeWidth: isHovered ? 2.5 : isOccupied ? 2.5 : 1.5,
      labelX: getLabelX(room.geometry),
      labelY: getLabelY(room.geometry),
      nameText: getRoomDisplayName(room),
      nameOffsetX: getTextWidth(getRoomDisplayName(room), 13) / 2,
      secondaryText: getRoomSecondaryLabel(room, vm),
      sizeLabel: roomSizeLabel(toNumericValue(room.attributes?.area)),
    }
  })
})

// Per-persona destination positions (centroid + sharing offset when co-located)
const personaTargets = computed(() => {
  if (props.viewMode !== 'routine') return {}
  const active = props.activeRooms || {}
  const cmap = centroidMap.value
  const targets = {}
  for (const [roomId, entries] of Object.entries(active)) {
    const c = cmap[String(roomId)]
    if (!c || !entries?.length) continue
    const count = entries.length
    const totalWidth = (count - 1) * CIRCLE_SPACING
    entries.forEach((entry, i) => {
      const color = typeof entry === 'object' ? entry.color : entry
      const name  = typeof entry === 'object' ? entry.name : String(i)
      const kind  = typeof entry === 'object' && entry.kind ? entry.kind : inferKind(name)
      targets[name] = { x: c.x - totalWidth / 2 + i * CIRCLE_SPACING, y: c.y, color, kind }
    })
  }
  return targets
})

// Animated positions: personas glide along graph edges to their next room
const personaPositions = ref({})
let moveAnimFrame = null
const MOVE_DURATION = 600

function movePersonas(targets) {
  const starts = {}
  for (const [name, target] of Object.entries(targets)) {
    const cur = personaPositions.value[name]
    starts[name] = cur ? { x: cur.x, y: cur.y } : { x: target.x, y: target.y }
  }
  const t0 = performance.now()
  function frame(now) {
    const raw = Math.min(1, (now - t0) / MOVE_DURATION)
    const ease = raw < 0.5 ? 2 * raw * raw : -1 + (4 - 2 * raw) * raw
    const next = {}
    for (const [name, target] of Object.entries(targets)) {
      const s = starts[name]
      next[name] = { x: s.x + (target.x - s.x) * ease, y: s.y + (target.y - s.y) * ease, color: target.color, kind: target.kind }
    }
    personaPositions.value = next
    if (raw < 1) moveAnimFrame = requestAnimationFrame(frame)
  }
  if (moveAnimFrame) cancelAnimationFrame(moveAnimFrame)
  moveAnimFrame = requestAnimationFrame(frame)
}

watch(personaTargets, (targets) => {
  if (!Object.keys(targets).length) { personaPositions.value = {}; return }
  movePersonas(targets)
}, { deep: true })

// Routine circles read from animated positions
const routineCircleData = computed(() => {
  const positions = personaPositions.value
  return Object.entries(positions).map(([name, p]) => ({
    key: name,
    x: p.x,
    y: p.y,
    color: hexToRgba(p.color, CIRCLE_ALPHA),
    personaName: name,
    kind: p.kind,
  }))
})

function flattenAndScale(geometry) {
  // Converts [[x, y], ...] to [x*scale+offset, y*scale+offset, ...]
  return geometry.flatMap(([x, y]) => [x * scale.value + offset.value.x, y * scale.value + offset.value.y]);
}

function getCentroid(geometry) {
  // Polygon centroid formula
  let x = 0, y = 0, area = 0;
  for (let i = 0, j = geometry.length - 1; i < geometry.length; j = i++) {
    const f = geometry[i][0] * geometry[j][1] - geometry[j][0] * geometry[i][1];
    x += (geometry[i][0] + geometry[j][0]) * f;
    y += (geometry[i][1] + geometry[j][1]) * f;
    area += f;
  }
  area /= 2;
  if (area === 0) return [geometry[0][0], geometry[0][1]];
  x /= (6 * area);
  y /= (6 * area);
  return [x, y];
}

function getLabelX(geometry) {
  // Center label at centroid
  const [cx, cy] = getCentroid(geometry);
  return cx * scale.value + offset.value.x;
}
function getLabelY(geometry) {
  const [cx, cy] = getCentroid(geometry);
  return cy * scale.value + offset.value.y;
}

function buildCurveRenderData(items) {
  return items.flatMap(item =>
    (item.all_curves || []).map((curve, i) => {
      if (!Array.isArray(curve) || curve.length < 2) return null
      const isClosed = curve.length > 2 &&
        curve[0][0] === curve[curve.length - 1][0] &&
        curve[0][1] === curve[curve.length - 1][1]
      return {
        key: `${item.id}-${i}`,
        points: flattenAndScale(isClosed ? curve.slice(0, -1) : curve),
        closed: isClosed,
      }
    }).filter(Boolean)
  )
}

const furnitureRenderData = computed(() => buildCurveRenderData(props.layout?.furniture || []))
const doorsRenderData = computed(() => buildCurveRenderData(props.layout?.doors || []))
const windowsRenderData = computed(() => {
  const rooms = props.layout?.rooms || []
  const facades = props.layout?.facades || []
  if (!facades.length || !rooms.length) return []
  const result = []
  let idx = 0
  for (const room of rooms) {
    const geom = room.geometry || []
    if (geom.length < 3) continue
    for (let i = 0; i < geom.length; i++) {
      const p1 = geom[i], p2 = geom[(i + 1) % geom.length]
      const mid = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2]
      if (!_pointOnFacadeSegments(mid, facades)) continue
      const dx = p2[0] - p1[0], dy = p2[1] - p1[1]
      const len = Math.hypot(dx, dy)
      if (len === 0) continue
      const ax = dx / len, ay = dy / len      // along edge (unit)
      const px = -ay * 0.07, py = ax * 0.07  // perpendicular half-thickness
      const hw = len * 0.25                   // half-window = 25% of edge = 50% total
      const [mx, my] = mid
      const rect = [
        [mx + ax * hw + px, my + ay * hw + py],
        [mx + ax * hw - px, my + ay * hw - py],
        [mx - ax * hw - px, my - ay * hw - py],
        [mx - ax * hw + px, my - ay * hw + py],
      ]
      result.push({
        key: `win-${idx++}`,
        points: flattenAndScale(rect),
        centerPoints: flattenAndScale([[mx - ax * hw, my - ay * hw], [mx + ax * hw, my + ay * hw]]),
      })
    }
  }
  return result
})
// 2-point straight lines in each door = the aperture crossing the wall
const doorAperturesData = computed(() =>
  doorsRenderData.value.filter(c => !c.closed && c.points.length === 4)
)
const entryDoorRenderData = computed(() => {
  const curves = props.layout?.entry_door_curves
  if (!curves?.length) return []
  return buildCurveRenderData([{ id: 'entry-door', all_curves: curves }])
})
const entryDoorMarker = computed(() => {
  const pt = props.layout?.door_point
  if (!pt) return null

  // Derive entry direction from the 2-pt leaf line in entry_door_curves
  const rawCurves = props.layout?.entry_door_curves || []
  const leaf = rawCurves.find(c => Array.isArray(c) && c.length === 2)
  let rotation = -30  // fallback
  if (leaf) {
    const [p1, p2] = leaf
    const dx = p2[0] - p1[0]
    const dy = p2[1] - p1[1]
    // Two candidate perpendiculars
    const candA = [-dy, dx]
    const candB = [dy, -dx]
    // Pick the one pointing toward the building interior (avg room centroid)
    const rooms = props.layout?.rooms || []
    let cx = 0, cy = 0, n = 0
    for (const r of rooms) {
      for (const [x, y] of (r.geometry || [])) { cx += x; cy += y; n++ }
    }
    const inward = n > 0 && (candA[0] * (cx / n - pt[0]) + candA[1] * (cy / n - pt[1]) > 0)
      ? candA : candB
    // atan2 in world space (y-down = canvas), +90 to convert to Konva's up-is-0 convention
    rotation = Math.atan2(inward[1], inward[0]) * 180 / Math.PI + 90
  }

  return {
    x: pt[0] * scale.value + offset.value.x,
    y: pt[1] * scale.value + offset.value.y,
    rotation,
  }
})

function roomSizeLabel(area) {
  if (area == null) return ''
  if (area < 10) return 'small'
  if (area < 20) return 'medium'
  return 'large'
}

function getTextWidth(text, fontSize) {
  if (!text) return 0;
  // Use a canvas context for more accurate measurement
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  ctx.font = `${fontSize}px Arial`;
  return ctx.measureText(String(text)).width;
}

// --- Graph overlay (always-visible access edges + centroid nodes) ---
const centroidMap = computed(() => {
  const rooms = props.layout?.rooms || []
  const map = {}
  for (const room of rooms) {
    if (!room.geometry?.length) continue
    const [cx, cy] = getCentroid(room.geometry)
    map[String(room.id)] = {
      x: cx * scale.value + offset.value.x,
      y: cy * scale.value + offset.value.y,
    }
  }
  return map
})

// Connects rooms that have no door edges to the nearest circulation room,
// falling back to the nearest living room if no circulation exists.
function inferMissingEdges(rooms, centroidMapValue, connectedRoomIds, seen) {
  const edges = []
  const circulationRooms = rooms.filter(r => r.attributes?.program === 'circulation')
  const livingRooms = rooms.filter(r => r.attributes?.program === 'living')
  const fallbackPool = circulationRooms.length ? circulationRooms : livingRooms
  if (!fallbackPool.length) return edges
  for (const room of rooms) {
    const rid = String(room.id)
    if (connectedRoomIds.has(rid)) continue
    const s = centroidMapValue[rid]
    if (!s) continue
    let bestId = null, bestDist = Infinity
    for (const fb of fallbackPool) {
      const fid = String(fb.id)
      if (fid === rid) continue
      const t = centroidMapValue[fid]
      if (!t) continue
      const d = Math.hypot(t.x - s.x, t.y - s.y)
      if (d < bestDist) { bestDist = d; bestId = fid }
    }
    if (!bestId) continue
    const key = [rid, bestId].sort().join('|')
    if (seen.has(key)) continue
    seen.add(key)
    const t = centroidMapValue[bestId]
    edges.push({ key, source: rid, target: bestId, sx: s.x, sy: s.y, tx: t.x, ty: t.y, virtual: true })
  }
  return edges
}

const graphEdges = computed(() => {
  const doors = props.layout?.doors || []
  const rooms = props.layout?.rooms || []
  const edges = []
  const seen = new Set()
  const connectedRoomIds = new Set()
  for (const door of doors) {
    const connected = (door.attributes?.connectsRooms ?? []).map(String)
    for (let i = 0; i < connected.length; i++) {
      connectedRoomIds.add(connected[i])
      for (let j = i + 1; j < connected.length; j++) {
        connectedRoomIds.add(connected[j])
        const key = [connected[i], connected[j]].sort().join('|')
        if (seen.has(key)) continue
        seen.add(key)
        const s = centroidMap.value[connected[i]]
        const t = centroidMap.value[connected[j]]
        if (!s || !t) continue
        edges.push({ key, source: connected[i], target: connected[j], sx: s.x, sy: s.y, tx: t.x, ty: t.y, virtual: false })
      }
    }
  }
  edges.push(...inferMissingEdges(rooms, centroidMap.value, connectedRoomIds, seen))
  return edges
})

const realGraphEdges = computed(() => graphEdges.value.filter(e => !e.virtual))
const virtualGraphEdges = computed(() => graphEdges.value.filter(e => e.virtual))

// Edges connected to hovered room, direction reversed so flux flows toward it
const hoveredEdges = computed(() => {
  const hovered = props.hoveredRoomId
  if (!hovered) return []
  return graphEdges.value
    .filter(e => e.source === hovered || e.target === hovered)
    .map(e => e.source === hovered ? { ...e, sx: e.tx, sy: e.ty, tx: e.sx, ty: e.sy } : e)
})

const graphNodes = computed(() => {
  const rooms = props.layout?.rooms || []
  const hovered = props.hoveredRoomId
  return rooms.map(room => {
    const rid = String(room.id)
    const c = centroidMap.value[rid]
    if (!c) return null
    const isHovered = rid === hovered
    return {
      id: rid,
      x: c.x,
      y: c.y,
      radius: isHovered ? 8 : 4,
      fill: getRoomColor(room, 'layout'),
      stroke: '#fff',
      strokeWidth: isHovered ? 2 : 1,
      opacity: isHovered ? 1.0 : 0.35,
    }
  }).filter(Boolean)
})

const roomConnectivityMap = computed(() => {
  const degree = {}
  for (const edge of graphEdges.value) {
    degree[edge.source] = (degree[edge.source] ?? 0) + 1
    degree[edge.target] = (degree[edge.target] ?? 0) + 1
  }
  const label = (d) => d >= 3 ? 'central' : d === 2 ? 'connected' : 'peripheral'
  return Object.fromEntries(Object.entries(degree).map(([k, d]) => [k, label(d)]))
})

const graphDashOffset = ref(0)
let animFrameId = null

function startFlux() {
  if (animFrameId) return
  const tick = () => {
    graphDashOffset.value -= 0.3
    animFrameId = requestAnimationFrame(tick)
  }
  animFrameId = requestAnimationFrame(tick)
}

function stopFlux() {
  if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null }
  graphDashOffset.value = 0
}

watch(() => props.hoveredRoomId, id => {
  if (id) startFlux()
  else stopFlux()
})
</script>

<style scoped>
.canvas-wrapper {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
}
.room-tooltip {
  position: absolute;
  pointer-events: none;
  background: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 6px 10px;
  box-shadow: var(--shadow-card);
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 10;
  white-space: nowrap;
}
.room-tooltip-name {
  font-size: var(--font-size-small);
  font-weight: 600;
  color: var(--color-text);
}
.room-tooltip-detail {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
}
</style>

<template>
  <div ref="wrapperRef" class="canvas-wrapper">
    <v-stage :config="stageConfig">
      <v-layer :key="`rooms-${props.viewMode}-${props.activeStep}`">
        <!-- Boundary fill (no stroke — edges drawn separately to avoid overlap) -->
        <v-line
          v-if="boundaryData"
          :points="boundaryData.fillPoints"
          :closed="true"
          fill="rgba(0,130,194,0.06)"
          :strokeWidth="0"
          :listening="false"
        />
        <!-- Non-facade edges: solid -->
        <v-line
          v-for="e in boundaryData?.solidEdges"
          :key="e.key"
          :points="e.points"
          stroke="#0082c2"
          :strokeWidth="2"
          :listening="false"
        />
        <!-- Facade edges: dashed -->
        <v-line
          v-for="e in boundaryData?.dashedEdges"
          :key="e.key"
          :points="e.points"
          stroke="#0082c2"
          :strokeWidth="2"
          :dash="[8, 6]"
          :listening="false"
        />
        <!-- Circulation side: inward-pointing triangle at midpoint -->
        <v-regular-polygon
          v-for="c in boundaryCirculationData"
          :key="c.key"
          :config="{
            x: c.x,
            y: c.y,
            sides: 3,
            radius: 8,
            fill: '#0082c2',
            stroke: 'white',
            strokeWidth: 1.5,
            rotation: c.rotation,
            listening: false,
          }"
        />
        <v-group
          v-for="room in roomRenderData"
          :key="room.id"
          @mousemove="onRoomHover($event, room)"
          @mouseleave="onRoomLeave"
        >
          <v-line
            :config="{ points: room.points, closed: true, fill: room.fill, stroke: room.stroke, strokeWidth: room.strokeWidth }"
          />
          <v-text
            :x="room.labelX"
            :y="room.labelY"
            :text="room.nameText"
            fontFamily="Inter"
            fontSize="13"
            fill="#444"
            :offsetX="room.nameOffsetX"
            :offsetY="13 / 2"
          />
        </v-group>
      </v-layer>
      <!-- Furniture layer (layout + evaluate modes only) -->
      <v-layer v-if="furnitureRenderData.length">
        <v-line
          v-for="curve in furnitureRenderData"
          :key="curve.key"
          :config="{
            points: curve.points,
            closed: curve.closed,
            stroke: '#999',
            strokeWidth: 0.8,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Door apertures: white lines to visually break the wall at each opening -->
      <v-layer v-if="doorAperturesData.length">
        <v-line
          v-for="curve in doorAperturesData"
          :key="`apt-${curve.key}`"
          :config="{
            points: curve.points,
            closed: false,
            stroke: '#ffffff',
            strokeWidth: 5,
            lineCap: 'butt',
            listening: false,
          }"
        />
      </v-layer>
      <!-- Doors layer -->
      <v-layer v-if="doorsRenderData.length">
        <v-line
          v-for="curve in doorsRenderData"
          :key="curve.key"
          :config="{
            points: curve.points,
            closed: curve.closed,
            stroke: '#0082c2',
            strokeWidth: 1.0,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Entry door aperture: white line to break the wall at the opening -->
      <v-layer v-if="entryDoorRenderData.some(c => !c.closed && c.points.length === 4)">
        <v-line
          v-for="curve in entryDoorRenderData.filter(c => !c.closed && c.points.length === 4)"
          :key="`entry-apt-${curve.key}`"
          :config="{
            points: curve.points,
            closed: false,
            stroke: '#ffffff',
            strokeWidth: 5,
            lineCap: 'butt',
            listening: false,
          }"
        />
      </v-layer>
      <!-- Entry door layer -->
      <v-layer v-if="entryDoorRenderData.length || entryDoorMarker">
        <v-line
          v-for="curve in entryDoorRenderData"
          :key="curve.key"
          :config="{
            points: curve.points,
            closed: curve.closed,
            stroke: '#0082c2',
            strokeWidth: 1.0,
            listening: false,
          }"
        />
        <v-regular-polygon
          v-if="entryDoorMarker"
          :config="{
            x: entryDoorMarker.x,
            y: entryDoorMarker.y,
            sides: 3,
            radius: 7,
            fill: '#00E0CD',
            stroke: '#fff',
            strokeWidth: 1.2,
            rotation: entryDoorMarker.rotation,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Windows layer (room edges on facade) -->
      <v-layer v-if="windowsRenderData.length">
        <v-line
          v-for="win in windowsRenderData"
          :key="`win-rect-${win.key}`"
          :config="{
            points: win.points,
            closed: true,
            fill: '#ffffff',
            stroke: '#0082c2',
            strokeWidth: 1.0,
            listening: false,
          }"
        />
        <v-line
          v-for="win in windowsRenderData"
          :key="`win-cl-${win.key}`"
          :config="{
            points: win.centerPoints,
            closed: false,
            stroke: '#0082c2',
            strokeWidth: 1.0,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Graph overlay: layout + evaluate modes only (not routine, not daylight) -->
      <v-layer v-if="graphEdges.length && props.viewMode !== 'routine' && props.viewMode !== 'daylight'">
        <!-- Real door edges -->
        <v-line
          v-for="edge in realGraphEdges"
          :key="`g-${edge.key}`"
          :config="{
            points: [edge.sx, edge.sy, edge.tx, edge.ty],
            stroke: '#0082c2',
            strokeWidth: 1.5,
            opacity: 0.32,
            dash: [4, 5],
            listening: false,
          }"
        />
        <!-- Virtual edges for disconnected rooms (inferred — same visibility, sparser dash) -->
        <v-line
          v-for="edge in virtualGraphEdges"
          :key="`gv-${edge.key}`"
          :config="{
            points: [edge.sx, edge.sy, edge.tx, edge.ty],
            stroke: '#0082c2',
            strokeWidth: 1.5,
            opacity: 0.32,
            dash: [4, 5],
            listening: false,
          }"
        />
        <!-- Flux edges: animated dashes flowing toward hovered room -->
        <v-line
          v-for="edge in hoveredEdges"
          :key="`flux-${edge.key}`"
          :config="{
            points: [edge.sx, edge.sy, edge.tx, edge.ty],
            stroke: '#0082c2',
            strokeWidth: 2,
            opacity: 0.85,
            dash: [6, 5],
            dashOffset: graphDashOffset,
            listening: false,
          }"
        />
        <!-- Centroid nodes: small dots, hovered one enlarges -->
        <v-circle
          v-for="node in graphNodes"
          :key="`gn-${node.id}`"
          :config="{
            x: node.x,
            y: node.y,
            radius: node.radius,
            fill: node.fill,
            stroke: node.stroke,
            strokeWidth: node.strokeWidth,
            opacity: node.opacity,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Routine persona circles only -->
      <v-layer v-if="routineCircleData.length">
        <template v-for="circle in routineCircleData" :key="circle.key">
          <v-circle
            :config="{
              x: circle.x,
              y: circle.y,
              radius: CIRCLE_RADIUS,
              fill: circle.color,
              stroke: '#ffffff',
              strokeWidth: 3,
              listening: false,
            }"
          />
          <v-image
            v-if="iconImages[circle.kind]"
            :config="{
              x: circle.x - CIRCLE_ICON_SIZE / 2,
              y: circle.y - CIRCLE_ICON_SIZE / 2,
              width: CIRCLE_ICON_SIZE,
              height: CIRCLE_ICON_SIZE,
              image: iconImages[circle.kind],
              listening: false,
              opacity: 0.85,
            }"
          />
        </template>
      </v-layer>
    </v-stage>

    <!-- Room hover tooltip -->
    <div
      v-if="hoveredRoom"
      class="room-tooltip"
      :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }"
    >
      <span class="room-tooltip-name">{{ hoveredRoom.nameText }}</span> 
    <span v-if="hoveredRoom.secondaryText" class="room-tooltip-detail">{{ hoveredRoom.secondaryText }}</span>
      <span v-if="hoveredRoom.sizeLabel" class="room-tooltip-detail">{{ hoveredRoom.sizeLabel }}</span>
      <span v-if="roomConnectivityMap[String(hoveredRoom.id)]" class="room-tooltip-detail">{{ roomConnectivityMap[String(hoveredRoom.id)] }}</span>
    </div>
  </div>
</template>


<style scoped>
</style>