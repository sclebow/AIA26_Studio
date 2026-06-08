<script setup>
import { ref, watch, computed } from 'vue'
import { Stage, Layer, Group, Line, Text } from 'vue-konva'
import { getRoomColor, getRoomSecondaryLabel, TOD_COLORS, getRoomDisplayName } from '../utils/roomAnalysis.js'

const props = defineProps({
  layout:      { type: Object, default: null },
  viewMode:    { type: String, default: 'layout' },
  activeRooms: { type: Object, default: () => ({}) },  // { roomId: [color, ...] }
  activeStep:  { type: Number, default: 0 }            // 0–8 for time-of-day colour
})

const CIRCLE_RADIUS = 14
const CIRCLE_SPACING = 32  // horizontal gap between circles when multiple personas

const stageConfig = ref({ width: 600, height: 600 })




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

watch(() => props.layout, recalcGeometry, { immediate: true, deep: true })

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
  const todFill = vm === 'routine' ? TOD_COLORS[props.activeStep] ?? TOD_COLORS[0] : null
  return rooms.map(room => ({
    id: room.id,
    points: flattenAndScale(room.geometry),
    fill: todFill ?? getRoomColor(room, vm),
    labelX: getLabelX(room.geometry),
    labelY: getLabelY(room.geometry),
    nameText: getRoomDisplayName(room),
    nameOffsetX: getTextWidth(getRoomDisplayName(room), 18) / 2,
    secondaryText: getRoomSecondaryLabel(room, vm),
    secondaryOffsetX: getTextWidth(getRoomSecondaryLabel(room, vm), 14) / 2,
  }))
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
      circles.push({
        key: `${room.id}-${i}`,
        x: cx - totalWidth / 2 + i * CIRCLE_SPACING,
        y: cy,
        color,
        personaName,
        roomName,
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
</style>

<template>
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
      <v-group v-for="room in roomRenderData" :key="room.id">
        <v-line
          :config="{ points: room.points, closed: true, fill: room.fill, stroke: '#333', strokeWidth: 2 }"
        />
        <v-text
          :x="room.labelX"
          :y="room.labelY"
          :text="room.nameText"
          fontFamily="Inter"
          fontSize="18"
          fill="#222"
          :offsetX="room.nameOffsetX"
          :offsetY="18 / 2"
        />
        <v-text
          :x="room.labelX"
          :y="room.labelY + 16"
          :text="room.secondaryText"
          fontFamily="Inter"
          fontSize="14"
          fill="#222"
          :offsetX="room.secondaryOffsetX"
          :offsetY="14 / 2"
        />
      </v-group>
    </v-layer>
    <!-- Routine persona circles only -->
    <v-layer v-if="routineCircleData.length">
      <v-circle
        v-for="circle in routineCircleData"
        :key="circle.key"
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
    </v-layer>
  </v-stage>
</template>


<style scoped>
</style>