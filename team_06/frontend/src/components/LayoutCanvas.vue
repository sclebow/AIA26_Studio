
<template>
  <v-stage :config="stageConfig">
    <v-layer>
      <v-group v-for="room in rooms" :key="room.id">
        <v-line
          :points="flattenAndScale(room.geometry)"
          :closed="true"
          :fill="roomColors[room.type] || '#ddd'"
          :stroke="'#333'"
          :strokeWidth="2"
        />
        <v-text
          :x="getLabelX(room.geometry)"
          :y="getLabelY(room.geometry)"
          :text="room.type"
          fontSize="18"
          fill="#222"
        />
      </v-group>
    </v-layer>
  </v-stage>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Stage, Layer, Group, Line, Text } from 'vue-konva'
import layoutData from '../assets/dummy/team_06_edited_layout.json'

const stageConfig = ref({ width: 600, height: 600 })
const rooms = ref(layoutData.rooms)

const roomColors = {
  bed: '#b3c6ff',
  bath: '#ffd6d6',
  kitchen: '#ffe6b3',
  living: '#d6ffd6',
  circulation: '#e0e0e0',
}

const scale = 60; // 1 meter = 60 pixels
const offset = { x: 40, y: 40 }; // Padding from top-left

function flattenAndScale(geometry) {
  // Converts [[x, y], ...] to [x*scale+offset, y*scale+offset, ...]
  return geometry.flatMap(([x, y]) => [x * scale + offset.x, y * scale + offset.y]);
}

function getLabelX(geometry) {
  // Average X for label, scaled and offset
  return (
    geometry.reduce((sum, pt) => sum + pt[0], 0) / geometry.length
  ) * scale + offset.x - 20;
}
function getLabelY(geometry) {
  // Average Y for label, scaled and offset
  return (
    geometry.reduce((sum, pt) => sum + pt[1], 0) / geometry.length
  ) * scale + offset.y - 10;
}
</script>

<style scoped>
</style>
