
<script setup>
import { ref, onMounted } from 'vue'
import { Stage, Layer, Group, Line, Text } from 'vue-konva'
import layoutData from '../assets/dummy/layouts.json'

const props = defineProps({
  index: Number
})

const stageConfig = ref({ width: 600, height: 600 })
const layout = layoutData[props.index] || {}
const layoutId = layout.layoutId || 'Layout'
const rooms = layout.rooms || []

const roomColors = {
  bed: '#4A7CA8',
  bath: '#C8F4F0',
  kitchen: '#00C7D4',
  living: '#009FA6',
  foyer: '#0082C2',
  storage: '#7A8FA3',
}

const scale = 60; // 1 meter = 60 pixels

// Compute bounding box for all rooms
function getAllPoints() {
  return rooms.flatMap(room => room.geometry)
}
const allPoints = getAllPoints();
const xs = allPoints.map(pt => pt[0]);
const ys = allPoints.map(pt => pt[1]);
const minX = Math.min(...xs);
const maxX = Math.max(...xs);
const minY = Math.min(...ys);
const maxY = Math.max(...ys);
const layoutWidth = (maxX - minX) * scale;
const layoutHeight = (maxY - minY) * scale;
const stageWidth = stageConfig.value.width;
const stageHeight = stageConfig.value.height;
const offset = {
  x: (stageWidth - layoutWidth) / 2 - minX * scale,
  y: (stageHeight - layoutHeight) / 2 - minY * scale
};

function flattenAndScale(geometry) {
  // Converts [[x, y], ...] to [x*scale+offset, y*scale+offset, ...]
  return geometry.flatMap(([x, y]) => [x * scale + offset.x, y * scale + offset.y]);
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
  return cx * scale + offset.x;
}
function getLabelY(geometry) {
  const [cx, cy] = getCentroid(geometry);
  return cy * scale + offset.y;
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

<template>
  <v-stage :config="stageConfig">
    <v-layer>
      <v-group v-for="room in rooms" :key="room.id">
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
