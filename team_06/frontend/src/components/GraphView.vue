<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { PROGRAM_COLORS, hexToRgba, getRoomDisplayName, getRoomColor } from '../utils/roomAnalysis.js'

const props = defineProps({
  layout:        { type: Object, default: null },
  hoveredRoomId: { type: String, default: null },
})
const emit = defineEmits(['roomHover', 'roomLeave'])

const wrapperRef = ref(null)
const stageConfig = ref({ width: 600, height: 600 })
const hoveredNode = ref(null)
const tooltipX = ref(0)
const tooltipY = ref(0)

const EDGE_COLOR_ACCESS = '#0067B5'
const EDGE_COLOR_ADJACENCY = '#0067B5'
const NODE_MIN_RADIUS = 4
const NODE_MAX_RADIUS = 14
const ARC_OFFSET = 0.15

let resizeObserver = null
onMounted(() => {
  if (!wrapperRef.value) return
  resizeObserver = new ResizeObserver(entries => {
    const { width, height } = entries[0]?.contentRect ?? {}
    if (width > 0 && height > 0) stageConfig.value = { width: Math.floor(width), height: Math.floor(height) }
  })
  resizeObserver.observe(wrapperRef.value)
  const rect = wrapperRef.value.getBoundingClientRect()
  if (rect.width > 0 && rect.height > 0) stageConfig.value = { width: Math.floor(rect.width), height: Math.floor(rect.height) }
})
onUnmounted(() => resizeObserver?.disconnect())

// --- Scaling (same logic as LayoutCanvas) ---
const scale = ref(60)
const offset = ref({ x: 0, y: 0 })

function recalcGeometry() {
  const rooms = props.layout?.rooms || []
  const outline = props.layout?.outline || []
  const sourcePoints = rooms.length > 0 ? rooms.flatMap(r => r.geometry) : outline
  if (!sourcePoints.length) { scale.value = 60; offset.value = { x: 0, y: 0 }; return }

  const xs = sourcePoints.map(p => p[0])
  const ys = sourcePoints.map(p => p[1])
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const lw = maxX - minX, lh = maxY - minY
  if (lw === 0 || lh === 0) { scale.value = 60; offset.value = { x: 0, y: 0 }; return }

  const scaleX = (stageConfig.value.width - 40) / lw
  const scaleY = (stageConfig.value.height - 40) / lh
  scale.value = Math.min(scaleX, scaleY, 60)
  offset.value = {
    x: (stageConfig.value.width - lw * scale.value) / 2 - minX * scale.value,
    y: (stageConfig.value.height - lh * scale.value) / 2 - minY * scale.value,
  }
}

watch([() => props.layout, stageConfig], recalcGeometry, { immediate: true, deep: true })

function flattenAndScale(geometry) {
  return geometry.flatMap(([x, y]) => [x * scale.value + offset.value.x, y * scale.value + offset.value.y])
}

function getCentroid(geometry) {
  let x = 0, y = 0, area = 0
  for (let i = 0, j = geometry.length - 1; i < geometry.length; j = i++) {
    const f = geometry[i][0] * geometry[j][1] - geometry[j][0] * geometry[i][1]
    x += (geometry[i][0] + geometry[j][0]) * f
    y += (geometry[i][1] + geometry[j][1]) * f
    area += f
  }
  area /= 2
  if (area === 0) return [geometry[0][0], geometry[0][1]]
  return [x / (6 * area), y / (6 * area)]
}

function scaledCentroid(geometry) {
  const [cx, cy] = getCentroid(geometry)
  return { x: cx * scale.value + offset.value.x, y: cy * scale.value + offset.value.y }
}

// --- Room polygons (background layer) ---
const roomRenderData = computed(() => {
  const rooms = props.layout?.rooms || []
  return rooms.map(room => {
    const color = getRoomColor(room, 'layout')
    return {
      id: room.id,
      points: flattenAndScale(room.geometry),
      fill: hexToRgba(color, 0.12),
      stroke: '#ddd',
      strokeWidth: 0.8,
    }
  })
})

// --- Furniture / doors / windows ---
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
const windowsRenderData = computed(() => buildCurveRenderData(props.layout?.windows || []))

// --- Graph edges ---
function buildEdges(layout) {
  if (!layout) return []
  const rooms = layout.rooms || []
  const doors = layout.doors || []
  const edgeMap = new Map()
  const edgeKey = (a, b) => [a, b].sort().join('|')

  for (const door of doors) {
    const connected = door.attributes?.connectsRooms ?? []
    for (let i = 0; i < connected.length; i++) {
      for (let j = i + 1; j < connected.length; j++) {
        const key = edgeKey(String(connected[i]), String(connected[j]))
        if (!edgeMap.has(key)) edgeMap.set(key, { source: String(connected[i]), target: String(connected[j]), types: [] })
        const e = edgeMap.get(key)
        if (!e.types.includes('access')) e.types.push('access')
      }
    }
  }

  for (let i = 0; i < rooms.length; i++) {
    for (let j = i + 1; j < rooms.length; j++) {
      if (sharesWall(rooms[i], rooms[j])) {
        const key = edgeKey(String(rooms[i].id), String(rooms[j].id))
        if (!edgeMap.has(key)) edgeMap.set(key, { source: String(rooms[i].id), target: String(rooms[j].id), types: [] })
        const e = edgeMap.get(key)
        if (!e.types.includes('adjacency')) e.types.push('adjacency')
      }
    }
  }

  return Array.from(edgeMap.values())
}

function sharesWall(roomA, roomB) {
  const gA = roomA.geometry, gB = roomB.geometry
  if (!gA?.length || !gB?.length) return false
  const EPS = 0.01
  for (const sA of segments(gA)) {
    for (const sB of segments(gB)) {
      if (segmentsOverlap(sA, sB, EPS)) return true
    }
  }
  return false
}

function segments(pts) {
  const segs = []
  for (let i = 0; i < pts.length; i++) segs.push([pts[i], pts[(i + 1) % pts.length]])
  return segs
}

function segmentsOverlap([a1, a2], [b1, b2], eps) {
  const collinear = (p, q, r) => Math.abs((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])) < eps
  if (!collinear(a1, a2, b1) || !collinear(a1, a2, b2)) return false
  const horizontal = Math.abs(a2[0] - a1[0]) >= Math.abs(a2[1] - a1[1])
  const project = p => horizontal ? p[0] : p[1]
  const [aMin, aMax] = [project(a1), project(a2)].sort((x, y) => x - y)
  const [bMin, bMax] = [project(b1), project(b2)].sort((x, y) => x - y)
  return Math.min(aMax, bMax) - Math.max(aMin, bMin) > eps
}

// --- Computed centroids for nodes ---
const centroidMap = computed(() => {
  const rooms = props.layout?.rooms || []
  const map = {}
  for (const room of rooms) {
    if (!room.geometry?.length) continue
    map[String(room.id)] = scaledCentroid(room.geometry)
  }
  return map
})

const edges = computed(() => buildEdges(props.layout))

const adjacencyEdges = computed(() => {
  return edges.value.map((edge, i) => {
    const s = centroidMap.value[edge.source]
    const t = centroidMap.value[edge.target]
    if (!s || !t || !edge.types.includes('adjacency')) return null
    const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2
    const dx = t.x - s.x, dy = t.y - s.y
    const len = Math.sqrt(dx * dx + dy * dy) || 1
    const cx = mx + (-dy / len) * len * ARC_OFFSET
    const cy = my + (dx / len) * len * ARC_OFFSET
    return {
      key: `adj-${i}`,
      points: [s.x, s.y, cx, cy, t.x, t.y],
      stroke: EDGE_COLOR_ADJACENCY,
      strokeWidth: 1.5,
      dash: [5, 4],
    }
  }).filter(Boolean)
})

const accessEdges = computed(() => {
  return edges.value.map((edge, i) => {
    const s = centroidMap.value[edge.source]
    const t = centroidMap.value[edge.target]
    if (!s || !t || !edge.types.includes('access')) return null
    const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2
    const dx = t.x - s.x, dy = t.y - s.y
    const len = Math.sqrt(dx * dx + dy * dy) || 1
    const cx = mx + (dy / len) * len * ARC_OFFSET
    const cy = my + (-dx / len) * len * ARC_OFFSET
    return {
      key: `access-${i}`,
      points: [s.x, s.y, cx, cy, t.x, t.y],
      stroke: EDGE_COLOR_ACCESS,
      strokeWidth: 1.5,
    }
  }).filter(Boolean)
})

// --- Size classification (matches Python thresholds) ---
const SIZE_THRESHOLDS = {
  living: [25, 45], bed: [11, 17], bath: [4, 7], wc: [2, 5],
  extra: [4, 10], circulation: [5, 12], storage: [3, 6], walkincloset: [3, 6],
}
const SIZE_DEFAULT = [10, 20]

function classifySize(program, area) {
  const [s, m] = SIZE_THRESHOLDS[program] ?? SIZE_DEFAULT
  return area < s ? 'small' : area < m ? 'medium' : 'large'
}

function classifyBetweenness(bc) {
  if (bc === 0) return 'peripheral'
  return bc <= 0.4 ? 'connected' : 'hub'
}

// --- Betweenness centrality on access graph ---
function computeBetweenness(nodeIds, accessEdgeList) {
  const adj = {}
  for (const id of nodeIds) adj[id] = []
  for (const e of accessEdgeList) {
    adj[e.source].push(e.target)
    adj[e.target].push(e.source)
  }
  const bc = {}
  for (const id of nodeIds) bc[id] = 0
  for (const s of nodeIds) {
    const stack = []
    const pred = {}; for (const id of nodeIds) pred[id] = []
    const sigma = {}; for (const id of nodeIds) sigma[id] = 0
    sigma[s] = 1
    const dist = {}; for (const id of nodeIds) dist[id] = -1
    dist[s] = 0
    const queue = [s]
    while (queue.length) {
      const v = queue.shift()
      stack.push(v)
      for (const w of adj[v]) {
        if (dist[w] < 0) { dist[w] = dist[v] + 1; queue.push(w) }
        if (dist[w] === dist[v] + 1) { sigma[w] += sigma[v]; pred[w].push(v) }
      }
    }
    const delta = {}; for (const id of nodeIds) delta[id] = 0
    while (stack.length) {
      const w = stack.pop()
      for (const v of pred[w]) delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
      if (w !== s) bc[w] += delta[w]
    }
  }
  const n = nodeIds.length
  const norm = n > 2 ? (n - 1) * (n - 2) : 1
  for (const id of nodeIds) bc[id] = Math.round((bc[id] / norm) * 1000) / 1000
  return bc
}

// --- Per-room graph stats ---
const roomStats = computed(() => {
  const rooms = props.layout?.rooms || []
  const facades = props.layout?.facades || []
  const edgeList = edges.value
  const nodeIds = rooms.map(r => String(r.id))
  const accessEdgeList = edgeList.filter(e => e.types.includes('access'))
  const bc = computeBetweenness(nodeIds, accessEdgeList)

  const stats = {}
  for (const room of rooms) {
    const rid = String(room.id)
    const program = room.attributes?.program ?? ''
    const area = room.attributes?.area ?? 0
    stats[rid] = {
      size: classifySize(program, area),
      windows: countFacadeExposures(room, facades),
      betweenness: bc[rid] ?? 0,
      connectivity: classifyBetweenness(bc[rid] ?? 0),
    }
  }
  return stats
})

function countFacadeExposures(room, facades) {
  if (!room.geometry?.length || !facades.length) return 0
  const roomSegs = segments(room.geometry)
  let count = 0
  for (const facade of facades) {
    const facadeGeom = facade.geometry || facade
    if (!Array.isArray(facadeGeom) || facadeGeom.length < 2) continue
    const facadeSegs = []
    for (let i = 0; i < facadeGeom.length - 1; i++) facadeSegs.push([facadeGeom[i], facadeGeom[i + 1]])
    let touches = false
    for (const rs of roomSegs) {
      for (const fs of facadeSegs) {
        if (segmentsOverlap(rs, fs, 0.01)) { touches = true; break }
      }
      if (touches) break
    }
    if (touches) count++
  }
  return count
}

// --- Node dots at centroids (radius proportional to area) ---
const nodeRenderData = computed(() => {
  const rooms = props.layout?.rooms || []
  const areas = rooms.map(r => r.attributes?.area ?? 0).filter(a => a > 0)
  const minArea = areas.length ? Math.min(...areas) : 1
  const maxArea = areas.length ? Math.max(...areas) : 1
  const range = maxArea - minArea || 1
  const hovered = props.hoveredRoomId
  return rooms.map(room => {
    const c = centroidMap.value[String(room.id)]
    if (!c) return null
    const rid = String(room.id)
    const area = room.attributes?.area ?? 0
    const t = area > 0 ? (area - minArea) / range : 0
    const radius = NODE_MIN_RADIUS + t * (NODE_MAX_RADIUS - NODE_MIN_RADIUS)
    const isHovered = rid === hovered
    const color = PROGRAM_COLORS[room.attributes?.program] ?? '#888'
    const s = roomStats.value[rid] || { size: '–', windows: 0, betweenness: 0, connectivity: '–' }
    return {
      id: rid,
      x: c.x,
      y: c.y,
      radius,
      fill: color,
      stroke: isHovered ? '#333' : '#fff',
      strokeWidth: isHovered ? 2 : 1.5,
      name: getRoomDisplayName(room),
      program: room.attributes?.program ?? '',
      area,
      size: s.size,
      windows: s.windows,
      betweenness: s.betweenness,
      connectivity: s.connectivity,
    }
  }).filter(Boolean)
})

const tooltipRef = ref(null)

function onNodeHover(konvaEvent, node) {
  const { clientX, clientY } = konvaEvent.evt
  const rect = wrapperRef.value?.getBoundingClientRect()
  if (!rect) return
  hoveredNode.value = node

  const gap = 14
  let x = clientX - rect.left + gap
  let y = clientY - rect.top + gap

  const tw = tooltipRef.value?.offsetWidth ?? 180
  const th = tooltipRef.value?.offsetHeight ?? 100
  if (x + tw > rect.width) x = clientX - rect.left - tw - gap
  if (y + th > rect.height) y = clientY - rect.top - th - gap

  tooltipX.value = x
  tooltipY.value = y
  emit('roomHover', node.id)
}

function onNodeLeave() {
  hoveredNode.value = null
  emit('roomLeave')
}
</script>

<template>
  <div class="graph-outer">
    <div ref="wrapperRef" class="graph-canvas">
    <v-stage :config="stageConfig">
      <!-- Background: room polygons -->
      <v-layer>
        <v-line
          v-for="room in roomRenderData"
          :key="room.id"
          :config="{
            points: room.points,
            closed: true,
            fill: room.fill,
            stroke: room.stroke,
            strokeWidth: room.strokeWidth,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Furniture -->
      <v-layer v-if="furnitureRenderData.length">
        <v-line
          v-for="curve in furnitureRenderData"
          :key="curve.key"
          :config="{
            points: curve.points,
            closed: curve.closed,
            stroke: '#ddd',
            strokeWidth: 0.5,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Doors -->
      <v-layer v-if="doorsRenderData.length">
        <v-line
          v-for="curve in doorsRenderData"
          :key="curve.key"
          :config="{
            points: curve.points,
            closed: curve.closed,
            stroke: '#ccc',
            strokeWidth: 0.5,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Windows -->
      <v-layer v-if="windowsRenderData.length">
        <v-line
          v-for="curve in windowsRenderData"
          :key="curve.key"
          :config="{
            points: curve.points,
            closed: curve.closed,
            stroke: '#a8e4f8',
            strokeWidth: 1,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Adjacency edges (curved, below) -->
      <v-layer>
        <v-line
          v-for="edge in adjacencyEdges"
          :key="edge.key"
          :config="{
            points: edge.points,
            stroke: edge.stroke,
            strokeWidth: edge.strokeWidth,
            dash: edge.dash,
            tension: 1,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Access edges (on top) -->
      <v-layer>
        <v-line
          v-for="edge in accessEdges"
          :key="edge.key"
          :config="{
            points: edge.points,
            stroke: edge.stroke,
            strokeWidth: edge.strokeWidth,
            tension: 1,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Node dots at centroids -->
      <v-layer>
        <v-circle
          v-for="node in nodeRenderData"
          :key="node.id"
          :config="{
            x: node.x,
            y: node.y,
            radius: node.radius,
            fill: node.fill,
            stroke: node.stroke,
            strokeWidth: node.strokeWidth,
          }"
          @mousemove="onNodeHover($event, node)"
          @mouseleave="onNodeLeave"
        />
      </v-layer>
    </v-stage>

    <!-- Tooltip -->
    <div
      v-if="hoveredNode"
      ref="tooltipRef"
      class="graph-tooltip"
      :style="{ left: tooltipX + 'px', top: tooltipY + 'px' }"
    >
      <span class="graph-tooltip-name">{{ hoveredNode.name }}</span>
      <span class="graph-tooltip-detail" v-if="hoveredNode.area">{{ hoveredNode.area.toFixed(1) }} m² · {{ hoveredNode.size }}</span>
      <span class="graph-tooltip-detail">Windows: {{ hoveredNode.windows }}</span>
      <span class="graph-tooltip-detail">Betweenness: {{ hoveredNode.betweenness.toFixed(2) }}</span>
      <span class="graph-tooltip-detail">Connectivity: {{ hoveredNode.connectivity }}</span>
    </div>
    </div>

    <!-- Legend (outside canvas) -->
    <div class="graph-legend">
      <div class="legend-item">
        <span class="legend-line legend-access"></span>
        <span class="legend-label">Access (door)</span>
      </div>
      <div class="legend-item">
        <span class="legend-line legend-adjacency"></span>
        <span class="legend-label">Adjacency (shared wall)</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.graph-outer {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}
.graph-canvas {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
}
.graph-legend {
  flex-shrink: 0;
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 8px 12px;
  border-top: 1px solid var(--color-border);
  font-size: 11px;
  color: var(--color-text-secondary);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.legend-line {
  display: inline-block;
  width: 20px;
  height: 0;
  border-top: 2px solid;
}
.legend-access {
  border-color: #0067B5;
}
.legend-adjacency {
  border-color: #0067B5;
  border-top-style: dashed;
}
.legend-label {
  white-space: nowrap;
}
.graph-tooltip {
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
.graph-tooltip-name {
  font-size: var(--font-size-small);
  font-weight: 600;
  color: var(--color-text);
}
.graph-tooltip-detail {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
}
</style>
