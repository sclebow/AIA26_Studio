<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { Stage, Layer, Group, Line, Text } from 'vue-konva'
import { getRoomColor, getRoomSecondaryLabel, TOD_COLORS, getRoomDisplayName, hexToRgba } from '../utils/roomAnalysis.js'
import catWhiteUrl from '../assets/icons/cat-white.svg'
import dogWhiteUrl from '../assets/icons/dog-white.svg'
import userWhiteUrl from '../assets/icons/user-white.svg'

const ROOM_ALPHA = 0.35
const CIRCLE_ALPHA = 0.88

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
onUnmounted(() => resizeObserver?.disconnect())




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

// Outline points for boundary-only mode (no rooms)
const outlinePoints = computed(() => {
  const outline = props.layout?.outline
  if (!outline || (props.layout?.rooms?.length ?? 0) > 0) return null
  return flattenAndScale(outline)
})

// Computed room render data — explicitly tracks props.viewMode so Vue re-evaluates
// when the toggle changes, even inside vue-konva's non-VDOM rendering path.
const roomRenderData = computed(() => {
  const rooms = props.layout?.rooms || []
  const vm = props.viewMode
  const hovered = props.hoveredRoomId
  const todHex = vm === 'routine' ? TOD_COLORS[props.activeStep] ?? TOD_COLORS[0] : null
  const occupiedIds = vm === 'routine'
    ? new Set(Object.keys(props.activeRooms || {}).filter(id => props.activeRooms[id]?.length > 0))
    : null
  return rooms.map(room => {
    const isHovered = room.id === hovered
    const isOccupied = occupiedIds?.size > 0 && occupiedIds.has(String(room.id))
    let alpha
    if (vm === 'routine' && occupiedIds) {
      alpha = occupiedIds.size > 0 ? (isOccupied ? 0.65 : 0.15) : ROOM_ALPHA
    } else if (hovered) {
      alpha = isHovered ? 0.65 : 0.15
    } else {
      alpha = ROOM_ALPHA
    }
    const baseColor = todHex ?? getRoomColor(room, vm)
    return {
      id: room.id,
      points: flattenAndScale(room.geometry),
      fill: hexToRgba(baseColor, alpha),
      stroke: (isHovered || isOccupied) ? '#222' : '#555',
      strokeWidth: (isHovered || isOccupied) ? 2.5 : 1.5,
      labelX: getLabelX(room.geometry),
      labelY: getLabelY(room.geometry),
      nameText: getRoomDisplayName(room),
      nameOffsetX: getTextWidth(getRoomDisplayName(room), 13) / 2,
      secondaryText: getRoomSecondaryLabel(room, vm),
    }
  })
})

// Routine circles — one circle per persona per occupied room, offset when sharing
const routineCircleData = computed(() => {
  const rooms = props.layout?.rooms || []
  const active = props.activeRooms || {}  // { roomId: [color, ...] }
  if (!Object.keys(active).length) return []

  // Build a map of personaIndex → persona name from the routine prop (passed via activeRooms colors)
  // We need to correlate colors back to names — build color→name map from layout rooms isn't possible
  // so we pass persona names alongside colors by extending activeRooms to { roomId: [{color, name}] }
  // For now activeRooms is { roomId: [color] } — we enrich with room program name
  const circles = []
  for (const room of rooms) {
    const entries = active[String(room.id)]  // array of { color, name } or just colors
    if (!entries?.length) continue
    const cx = getLabelX(room.geometry)
    const cy = getLabelY(room.geometry)
    const roomName = getRoomDisplayName(room)
    const count = entries.length
    const totalWidth = (count - 1) * CIRCLE_SPACING
    entries.forEach((entry, i) => {
      const color = typeof entry === 'object' ? entry.color : entry
      const personaName = typeof entry === 'object' ? entry.name : ''
      const kind = (typeof entry === 'object' && entry.kind) ? entry.kind : inferKind(personaName)
      circles.push({
        key: `${room.id}-${i}`,
        x: cx - totalWidth / 2 + i * CIRCLE_SPACING,
        y: cy,
        color: hexToRgba(color, CIRCLE_ALPHA),
        personaName,
        roomName,
        kind,
      })
    })
  }
  return circles
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
const windowsRenderData = computed(() => buildCurveRenderData(props.layout?.windows || []))

function getTextWidth(text, fontSize) {
  if (!text) return 0;
  // Use a canvas context for more accurate measurement
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  ctx.font = `${fontSize}px Arial`;
  return ctx.measureText(String(text)).width;
}
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
        <!-- Boundary outline (shown when no rooms yet) -->
        <v-line
          v-if="outlinePoints"
          :points="outlinePoints"
          :closed="true"
          fill="rgba(0,103,181,0.06)"
          stroke="#0067B5"
          :strokeWidth="2"
          :dash="[8, 6]"
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
      <!-- Doors layer -->
      <v-layer v-if="doorsRenderData.length">
        <v-line
          v-for="curve in doorsRenderData"
          :key="curve.key"
          :config="{
            points: curve.points,
            closed: curve.closed,
            stroke: '#3a6ea8',
            strokeWidth: 1.0,
            listening: false,
          }"
        />
      </v-layer>
      <!-- Windows layer -->
      <v-layer v-if="windowsRenderData.length">
        <v-line
          v-for="curve in windowsRenderData"
          :key="curve.key"
          :config="{
            points: curve.points,
            closed: curve.closed,
            stroke: '#5BC8F5',
            strokeWidth: 1.2,
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
      <span class="room-tooltip-detail">{{ hoveredRoom.secondaryText }}</span>
    </div>
  </div>
</template>


<style scoped>
</style>