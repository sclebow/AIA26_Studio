<script setup>
import { ref, watch } from 'vue'
import { Stage, Layer, Group, Line, Text } from 'vue-konva'
const props = defineProps({
  layout: {
    type: Object,
    default: null
  }
})

const stageConfig = ref({ width: 600, height: 600 })

const roomColors = {
  bed: '#4A7CA8',
  bath: '#C8F4F0',
  kitchen: '#00C7D4',
  living: '#009FA6',
  foyer: '#0082C2',
  extra: '#7A8FA3',
}


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
  allPoints.value = rooms.flatMap(room => room.geometry);
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
    <v-layer>
      <v-group v-for="room in props.layout?.rooms || []" :key="room.id">
        <v-line
          :points="flattenAndScale(room.geometry)"
          :closed="true"
          :fill="roomColors[room.attributes.program] || '#ddd'"
          :stroke="'#333'"
          :strokeWidth="2"
        />
        <v-text
          :x="getLabelX(room.geometry)"
          :y="getLabelY(room.geometry)"
          :text="room.attributes.program"
          fontFamily="Inter"
          fontSize="18"
          fill="#222"
          :offsetX="getTextWidth(room.attributes.program, 18) / 2"
          :offsetY="18 / 2"
        />
        <v-text
          :x="getLabelX(room.geometry)"
          :y="getLabelY(room.geometry) + 16"
          :text="room.attributes.area ? `${room.attributes.area.toFixed(1)} m²` : ''"
          fontFamily="Inter"
          fontSize="14"
          fill="#222"
          :offsetX="getTextWidth(room.attributes.area ? `${room.attributes.area.toFixed(1)} m²` : '', 14) / 2"
          :offsetY="14 / 2"
        />
      </v-group>
    </v-layer>
  </v-stage>
</template>


<style scoped>
</style>